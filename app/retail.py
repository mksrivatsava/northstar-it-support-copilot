"""Local, auditable inventory planning. CSV contents never enter an LLM workflow."""
import csv
import hashlib
import io
import json
import math
import re
import secrets
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from fractions import Fraction
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import ROOT

MAX_BYTES = 2 * 1024 * 1024
COOKIE = 'northstar_retail_session'


class Assumptions(BaseModel):
    as_of_date: date
    lookback_days: int = Field(default=30, ge=1, le=365)
    default_lead_time_days: int = Field(default=14, ge=0, le=365)
    safety_days: int = Field(default=7, ge=0, le=60)
    review_days: int = Field(default=7, ge=1, le=90)
    demand_multiplier: float = Field(default=1, ge=0.25, le=4, allow_inf_nan=False)


class Evidence(BaseModel):
    inventory_line: int
    sales_record_count: int
    sales_line_sample: list[int]


class DailySale(BaseModel):
    date: date
    units: int


class StockRow(BaseModel):
    sku: str
    location: str
    product_name: str
    on_hand: int
    reserved: int
    on_order: int
    available: int
    inventory_position: int
    lead_time_days: int
    units_sold: int | None
    observed_days: int
    historical_daily_demand: float | None
    daily_demand: float | None
    days_cover: float | None
    risk: Literal['out_of_stock', 'critical', 'reorder', 'healthy', 'no_recent_sales', 'no_demand_data']
    demand_status: Literal['unknown', 'zero', 'observed']
    needs_reorder: bool
    reorder_point: int | None
    target_stock: int | None
    recommended_order: int | None
    projected_stockout_date: date | None
    reorder_due_date: date | None
    reason: str
    recommended_action: str
    evidence: Evidence
    daily_sales: list[DailySale]


class Summary(BaseModel):
    total_skus: int
    attention: int
    reorder_skus: int
    suggested_units: int
    unknown_demand_skus: int
    counts: dict[str, int]


class AnalysisSummary(BaseModel):
    id: str
    created_at: str
    assumptions: Assumptions
    summary: Summary


class Source(BaseModel):
    kind: Literal['sales', 'inventory']
    filename: str
    sha256: str
    rows: int


class AnalysisReport(AnalysisSummary):
    window: dict[str, date]
    sources: list[Source]
    warnings: list[str]
    rows: list[StockRow]
    limitations: list[str]


class CSVError(ValueError):
    def __init__(self, issues):
        self.issues = issues[:50]
        super().__init__('CSV validation failed. No analysis was saved.')


def issue(file, line, column, message):
    return dict(file=file, line=line, column=column, message=message)


def parse_csv(raw, kind):
    if len(raw) > MAX_BYTES:
        raise CSVError([issue(kind, 0, '', 'File exceeds the 2 MB limit.')])
    try:
        content = raw.decode('utf-8-sig')
    except UnicodeDecodeError:
        raise CSVError([issue(kind, 0, '', 'Save as UTF-8 comma-separated CSV.')])
    if '\x00' in content or not content.strip():
        raise CSVError([issue(kind, 0, '', 'Empty or binary file; upload UTF-8 CSV.')])
    errors, warnings, rows, seen = [], [], [], set()
    required = {'date', 'sku', 'units_sold'} if kind == 'sales' else {'sku', 'on_hand'}
    allowed = required | {'location'}
    if kind == 'inventory':
        allowed |= {'product_name', 'reserved', 'on_order', 'lead_time_days'}
    reader = csv.reader(io.StringIO(content, newline=''), strict=True)
    try:
        headers = [re.sub(r'[ -]+', '_', h.strip().lower()) for h in next(reader)]
        if len(headers) != len(set(headers)) or not required <= set(headers):
            raise CSVError([issue(kind, 1, '', 'Use unique headers including: ' + ', '.join(sorted(required)))])
        extras = sorted(set(headers) - allowed)
        if extras:
            warnings.append(f'{kind}: ignored columns: ' + ', '.join(extras))
        for values in reader:
            line = reader.line_num
            if not values or all(not value.strip() for value in values):
                continue
            if len(rows) >= (50000 if kind == 'sales' else 5000):
                raise CSVError([issue(kind, line, '', 'Too many rows (sales: 50,000; inventory: 5,000).')])
            if len(values) != len(headers):
                errors.append(issue(kind, line, '', 'Column count does not match the header.'))
                if len(errors) >= 50:
                    break
                continue
            row = {k: v.strip() for k, v in zip(headers, values) if k in allowed}
            row['_line'] = line
            row['location'] = row.get('location') or 'main'
            if not row.get('sku') or len(row['sku']) > 120 or len(row['location']) > 120:
                errors.append(issue(kind, line, 'sku/location', 'Use a nonempty SKU and identifiers of at most 120 characters.'))
            if len(row.get('product_name', '')) > 240:
                errors.append(issue(kind, line, 'product_name', 'Maximum length is 240 characters.'))
            numeric = ['units_sold'] if kind == 'sales' else ['on_hand', 'reserved', 'on_order', 'lead_time_days']
            for field in numeric:
                value = row.get(field, '')
                if field == 'lead_time_days' and not value:
                    row[field] = None
                    continue
                if field in {'reserved', 'on_order'} and not value:
                    value = '0'
                if not re.fullmatch(r'[0-9]+', value) or len(value) > 10 or int(value) > (365 if field == 'lead_time_days' else 10**9):
                    errors.append(issue(kind, line, field, 'Use a nonnegative whole number (lead time ≤365; units ≤1 billion).'))
                    row[field] = 0
                else:
                    row[field] = int(value)
            if kind == 'sales':
                try:
                    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', row['date']):
                        raise ValueError()
                    date.fromisoformat(row['date'])
                except ValueError:
                    errors.append(issue(kind, line, 'date', 'Use a valid YYYY-MM-DD date.'))
            elif row['reserved'] > row['on_hand']:
                errors.append(issue(kind, line, 'reserved', 'Reserved units cannot exceed on-hand units.'))
            key = (row['sku'], row['location'], row.get('date'))
            if key in seen:
                errors.append(issue(kind, line, '', 'Duplicate SKU/location' + ('/date. Aggregate daily sales first.' if kind == 'sales' else '.')))
            seen.add(key)
            rows.append(row)
            if len(errors) >= 50:
                break
    except (csv.Error, StopIteration):
        raise CSVError([issue(kind, reader.line_num, '', 'Malformed CSV. Check quoting, headers and commas.')])
    if not rows and not errors:
        errors.append(issue(kind, 1, '', 'Include at least one data row.'))
    if errors:
        raise CSVError(errors)
    if kind == 'sales' and sum(r['units_sold'] for r in rows) > 10**12:
        raise CSVError([issue(kind, 0, 'units_sold', 'Total units exceed the supported limit of 1 trillion.')])
    return rows, warnings, 'location' in headers


def shifted(day, offset):
    ordinal = day.toordinal() + offset
    return date.fromordinal(ordinal).isoformat() if 1 <= ordinal <= date.max.toordinal() else None


def analyze(sales_raw, inventory_raw, assumptions, sales_name='sales.csv', inventory_name='inventory.csv'):
    sales, sw, sl = parse_csv(sales_raw, 'sales')
    inventory, iw, il = parse_csv(inventory_raw, 'inventory')
    if sl != il and any(r['location'] != 'main' for r in sales + inventory):
        raise CSVError([issue('both', 1, 'location', 'Provide matching location columns in both files for location-specific data.')])
    start = shifted(assumptions.as_of_date, -assumptions.lookback_days)
    if start is None:
        raise CSVError([issue('settings', 0, 'as_of_date', 'Date is too early for the selected lookback window.')])
    end = shifted(assumptions.as_of_date, -1)
    known = {(r['sku'], r['location']) for r in inventory}
    groups = defaultdict(list)
    outside, unmatched = 0, set()
    for row in sales:
        key = (row['sku'], row['location'])
        if key not in known:
            unmatched.add(key)
        if not start <= row['date'] <= end:
            outside += 1
        elif key in known:
            groups[key].append(row)
    warnings = sw + iw
    if outside:
        warnings.append(f'{outside} sales rows outside the completed-day window were excluded (including any snapshot-day or future sales).')
    if unmatched:
        warnings.append(f'{len(unmatched)} sales SKU/location pairs have no inventory match and were excluded: ' + ', '.join(f'{s} / {l}' for s, l in sorted(unmatched)[:5]))
    rows, low_coverage = [], 0
    for inv in inventory:
        records = groups[(inv['sku'], inv['location'])]
        observed = len(records)
        units = sum(r['units_sold'] for r in records)
        historical = Fraction(units, assumptions.lookback_days) if observed else None
        demand = historical * Fraction(str(assumptions.demand_multiplier)) if observed else None
        available = inv['on_hand'] - inv['reserved']
        position = available + inv['on_order']
        lead = inv['lead_time_days'] if inv['lead_time_days'] is not None else assumptions.default_lead_time_days
        cover = Fraction(available, 1) / demand if demand else None
        reorder_point = math.ceil(demand * (lead + assumptions.safety_days)) if demand is not None else None
        target = math.ceil(demand * (lead + assumptions.safety_days + assumptions.review_days)) if demand is not None else None
        needs_reorder = bool(demand and position <= reorder_point)
        quantity = max(0, target - position) if needs_reorder else (None if demand is None else 0)
        if not available:
            risk = 'out_of_stock'
        elif demand is None:
            risk = 'no_demand_data'
        elif not demand:
            risk = 'no_recent_sales'
        elif cover <= lead:
            risk = 'critical'
        elif cover <= lead + assumptions.safety_days:
            risk = 'reorder'
        else:
            risk = 'healthy'
        if observed and observed < assumptions.lookback_days:
            low_coverage += 1
        if demand is None:
            reason = 'No matching sales records in the analysis window; demand and order quantity are unknown.'
            action = 'Check the SKU/location mapping and supply recent sales before estimating an order.'
        elif not demand:
            reason = 'Matching sales records total zero units in the analysis window.'
            action = 'Review demand and product status before replenishing.'
        else:
            reason = f'{available} available units / {float(demand):.3f} units per day = {float(cover):.2f} days of cover; lead time {lead} days, safety buffer {assumptions.safety_days} days.'
            if quantity:
                action = f'Plan an order of {quantity} units.'
                if risk in {'critical', 'out_of_stock'}:
                    action += ' Stock may run out before normal replenishment; review expedited supply or transfers.'
            elif inv['on_order'] and risk in {'critical', 'out_of_stock', 'reorder'}:
                action = 'Confirm or expedite inbound stock. Its arrival date is unknown; the inventory position does not trigger another order.'
            else:
                action = 'Monitor stock and demand at the next review.'
        if not available:
            reason = 'No unreserved stock is available. ' + reason
        rows.append(dict(sku=inv['sku'], location=inv['location'], product_name=inv.get('product_name') or inv['sku'],
                         on_hand=inv['on_hand'], reserved=inv['reserved'], on_order=inv['on_order'], available=available,
                         inventory_position=position, lead_time_days=lead, units_sold=units if observed else None,
                         observed_days=observed, historical_daily_demand=round(float(historical), 6) if historical is not None else None,
                         daily_demand=round(float(demand), 6) if demand is not None else None,
                         days_cover=round(float(cover), 2) if cover is not None else None,
                         risk=risk, demand_status='unknown' if demand is None else ('zero' if not demand else 'observed'),
                         needs_reorder=needs_reorder, reorder_point=reorder_point, target_stock=target,
                         recommended_order=quantity, projected_stockout_date=assumptions.as_of_date.isoformat() if not available else (shifted(assumptions.as_of_date, math.floor(cover)) if cover is not None else None),
                         reorder_due_date=shifted(assumptions.as_of_date, math.floor(cover) - lead - assumptions.safety_days) if cover is not None else None,
                         reason=reason, recommended_action=action,
                         evidence=dict(inventory_line=inv['_line'], sales_record_count=observed, sales_line_sample=[r['_line'] for r in records[:10]]),
                         daily_sales=[dict(date=r['date'], units=r['units_sold']) for r in sorted(records, key=lambda r: r['date'])]))
    if low_coverage:
        warnings.append(f'{low_coverage} inventory rows have fewer recorded sales days than the window. Missing days are treated as zero sales; confirm export completeness.')
    priority = {status: i for i, status in enumerate(['out_of_stock', 'critical', 'reorder', 'healthy', 'no_recent_sales', 'no_demand_data'])}
    rows.sort(key=lambda r: (priority[r['risk']], r['days_cover'] if r['days_cover'] is not None else float('inf'), r['sku'], r['location']))
    counts = {status: sum(r['risk'] == status for r in rows) for status in priority}
    summary = dict(total_skus=len(rows), attention=sum(counts[s] for s in ('out_of_stock', 'critical', 'reorder')), unknown_demand_skus=sum(r['demand_status'] == 'unknown' for r in rows),
                   reorder_skus=sum(r['needs_reorder'] for r in rows), suggested_units=sum(r['recommended_order'] or 0 for r in rows), counts=counts)
    return dict(id=uuid.uuid4().hex, created_at=datetime.now(timezone.utc).isoformat(),
                assumptions=assumptions.model_dump(mode='json'), window=dict(start=start, end=end),
                sources=[dict(kind=k, filename=(n.replace('\\', '/').split('/')[-1])[:200], sha256=hashlib.sha256(raw).hexdigest(), rows=len(parsed)) for k, n, raw, parsed in [('sales', sales_name, sales_raw, sales), ('inventory', inventory_name, inventory_raw, inventory)]],
                summary=summary, warnings=warnings, rows=rows,
                limitations=['Deterministic planning heuristic, not a stockout probability or a demand forecast.',
                             'Inventory is a snapshot at the start of the selected date. Sales use completed calendar days; missing days count as zero only when a SKU has a matching record.',
                             'Incoming orders have no arrival date: they reduce new order quantities but do not extend available-stock cover.',
                             'Sales can understate demand during earlier stockouts. Seasonality, promotions, transfers, pack sizes and supplier constraints are not modeled.'])


def export_csv(report):
    output = io.StringIO(newline='')
    fields = ['sku', 'location', 'product_name', 'risk', 'available', 'on_order', 'inventory_position', 'daily_demand', 'days_cover', 'lead_time_days', 'reorder_point', 'target_stock', 'recommended_order', 'projected_stockout_date', 'recommended_action']
    writer = csv.writer(output)
    writer.writerow(fields)
    for row in report['rows']:
        values = []
        for field in fields:
            value = row[field]
            if isinstance(value, str) and (value.lstrip().startswith(('=', '+', '-', '@')) or any(c in value for c in '\t\r\n')):
                value = "'" + value
            values.append(value)
        writer.writerow(values)
    return '\ufeff' + output.getvalue()


def retail_router(store):
    router = APIRouter(prefix='/api/retail', tags=['Retail stockout analysis'])
    with store.connection() as con:
        con.execute('CREATE TABLE IF NOT EXISTS retail_analyses (id TEXT PRIMARY KEY, owner_hash TEXT NOT NULL, created_at TEXT NOT NULL, report TEXT NOT NULL)')
        con.execute('CREATE INDEX IF NOT EXISTS retail_owner_created ON retail_analyses(owner_hash, created_at)')

    def token_for(request):
        token = request.cookies.get(COOKIE, '')
        return token if re.fullmatch('[a-f0-9]{64}', token) else None

    def owner(token):
        return hashlib.sha256((token or '').encode()).hexdigest()

    def decode_report(raw):
        report = json.loads(raw)
        # Earlier local preview reports predate the cross-status data-quality count.
        report['summary'].setdefault('unknown_demand_skus', sum(r['demand_status'] == 'unknown' for r in report['rows']))
        return report

    def owned_report(request, report_id):
        with store.connection() as con:
            row = con.execute('SELECT report FROM retail_analyses WHERE id=? AND owner_hash=?', (report_id, owner(token_for(request)))).fetchone()
        if not row:
            raise HTTPException(404, 'Analysis not found in this browser session.')
        return decode_report(row[0])

    @router.post('/analyses', status_code=201, response_model=AnalysisReport)
    async def upload(request: Request, response: Response, sales_file: UploadFile = File(...), inventory_file: UploadFile = File(...),
                     as_of_date: date = Form(...), lookback_days: int = Form(30, ge=1, le=365),
                     default_lead_time_days: int = Form(14, ge=0, le=365), safety_days: int = Form(7, ge=0, le=60),
                     review_days: int = Form(7, ge=1, le=90), demand_multiplier: float = Form(1, ge=0.25, le=4, allow_inf_nan=False)):
        settings = Assumptions(as_of_date=as_of_date, lookback_days=lookback_days, default_lead_time_days=default_lead_time_days,
                               safety_days=safety_days, review_days=review_days, demand_multiplier=demand_multiplier)
        try:
            sales_raw = await sales_file.read(MAX_BYTES + 1)
            inventory_raw = await inventory_file.read(MAX_BYTES + 1)
            report = analyze(sales_raw, inventory_raw, settings, sales_file.filename or 'sales.csv', inventory_file.filename or 'inventory.csv')
        except CSVError as error:
            raise HTTPException(422, dict(message=str(error), issues=error.issues))
        finally:
            await sales_file.close()
            await inventory_file.close()
        token = token_for(request) or secrets.token_hex(32)
        with store.connection() as con:
            con.execute('INSERT INTO retail_analyses VALUES (?,?,?,?)', (report['id'], owner(token), report['created_at'], json.dumps(report, allow_nan=False)))
        response.set_cookie(COOKIE, token, max_age=604800, httponly=True, samesite='strict', secure=request.url.scheme == 'https', path='/api/retail')
        return report

    @router.get('/analyses', response_model=list[AnalysisSummary])
    def history(request: Request):
        with store.connection() as con:
            records = con.execute('SELECT report FROM retail_analyses WHERE owner_hash=? ORDER BY created_at DESC LIMIT 10', (owner(token_for(request)),)).fetchall()
        return [dict(id=r['id'], created_at=r['created_at'], assumptions=r['assumptions'], summary=r['summary']) for record in records for r in [decode_report(record[0])]]

    @router.get('/analyses/{report_id}', response_model=AnalysisReport)
    def detail(report_id: str, request: Request):
        return owned_report(request, report_id)

    @router.get('/analyses/{report_id}/export.csv')
    def export(report_id: str, request: Request):
        report = owned_report(request, report_id)
        return Response(export_csv(report), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="stockout-{report["id"]}.csv"'})

    @router.get('/sample')
    def sample():
        return dict(as_of_date='2026-11-11', sales_url='/api/retail/templates/sales.csv', inventory_url='/api/retail/templates/inventory.csv')

    @router.get('/templates/{kind}.csv')
    def template(kind: str):
        if kind not in {'sales', 'inventory'}:
            raise HTTPException(404, 'Template not found.')
        return FileResponse(ROOT / 'data' / 'retail' / f'{kind}.csv', media_type='text/csv', filename=f'sample-{kind}.csv')

    return router
