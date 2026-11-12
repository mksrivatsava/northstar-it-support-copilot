# Retail stockout planning · archived v0.5

Version 0.6 restores IT support as the main app and removes this workspace from the UI. The retail backend and examples remain for reference. The interface walkthrough below describes the earlier v0.5 release.

Run `.\.venv\Scripts\python.exe run.py` and open http://127.0.0.1:8000. The **Stockout risks** workspace is the default. No new packages or cloud keys are required. Existing Gemini/Pinecone/Tavily features remain under **Knowledge copilot**.

## Upload two exports

Files must be comma-separated UTF-8 (BOM accepted), at most 2 MB each. Quantities must be nonnegative whole units, at most one billion per field. SKU/location identifiers preserve case and leading zeros; surrounding whitespace is trimmed. Sales dates must be YYYY-MM-DD. Headers accept spaces or hyphens in place of underscores and are case-insensitive.

| File | Required columns | Optional columns |
| --- | --- | --- |
| Sales | `date,sku,units_sold` | `location` |
| Inventory | `sku,on_hand` | `location,product_name,reserved,on_order,lead_time_days` |

Sales are **daily totals**, one row per date/SKU/location (50,000 rows maximum). Aggregate transactional exports first. Inventory has one snapshot row per SKU/location (5,000 maximum). Duplicate keys, invalid dates, negative/fractional quantities, reserved stock above on-hand stock, malformed rows and invalid headers reject the whole analysis. The interface identifies the file, CSV line and column; no partial report is saved. Extra columns are ignored with a warning and their values are not stored. Lead time must be a whole number from 0 through 365 days.

If location is omitted it defaults to `main`. Provide matching location columns in both files for location-specific datasets. Sales keys absent from inventory are ignored with a warning; they cannot establish current stock. An inventory key with no sales records in the window has **unknown demand**, while an explicit record of zero units indicates **no recent sales**. Unknown demand never generates an invented order quantity.

Download examples in the interface, or use [sales.csv](../data/retail/sales.csv) and [inventory.csv](../data/retail/inventory.csv). Reproduce the examples with `python scripts/generate_retail_demo.py`. The fixed sample assumes a snapshot at the start of **2026-11-11** and sales from **2026-10-12 through 2026-11-10**. These are fictional data.

## Calculations

The snapshot is at the **start of the selected date**. The default lookback is the preceding 30 completed calendar days. Snapshot-day and future sales are excluded. Missing days count as zero only if there is at least one matching record in the window; the report warns about incomplete daily coverage. Confirm that missing records actually mean zero sales before using a report.

- Historical daily demand = units sold in window / calendar days in window.
- Adjusted demand = historical daily demand × scenario multiplier (100% by default).
- Available stock = on hand − reserved.
- Inventory position = available stock + on order.
- Days of cover = available stock / adjusted demand, when demand is positive.
- Reorder point = ceil(adjusted demand × (lead time + safety days)).
- Target stock = ceil(adjusted demand × (lead time + safety days + review days)).
- When demand is positive and inventory position ≤ reorder point: suggested order = max(0, target stock − inventory position). Otherwise no new order is suggested; unknown demand yields unknown quantity.

Defaults: lead time 14 days when absent from inventory, safety buffer 7 days, review cycle 7 days. What-if demand scenarios range from 25% to 400%; they are user assumptions, not machine learning forecasts. Calculations use exact fractions for threshold and ceiling decisions; the interface rounds displayed demand and cover.

| Status | Rule |
| --- | --- |
| Out of stock | No available unreserved stock, regardless of demand evidence |
| Critical | Positive demand; cover ≤ lead time |
| Reorder buffer | Positive demand; lead time < cover ≤ lead time + safety days |
| Healthy | Positive demand; cover > lead time + safety days |
| No recent sales | Available stock and matching records totaling zero units |
| Missing demand data | Available stock and no matching sales records in the window |

The first three statuses count as needing attention. Risk reflects immediately available stock; an existing order may cover replenishment needs while its unknown arrival still leaves an immediate risk. Confirm or expedite inbound stock instead of automatically duplicating orders. Projected stockout date uses snapshot date + floor(days of cover). Reorder due date subtracts lead time and safety days from that projection. Dates are planning approximations based on continuous, even demand.

## Evidence, privacy and history

Each immutable report includes assumptions, window dates, source filenames and SHA-256 hashes, row counts, inventory CSV line references, matching sales count and the first up to 10 sales line references. Raw uploaded file bytes and ignored column values are not saved. Per-product numerical sales history and inventory values **are saved** in the same local SQLite database as the app, under `retail_analyses`. The report persists until removed from that database; this version has no automatic retention/deletion policy.

An HttpOnly, SameSite=Strict cookie isolates report listing, retrieval and export by browser session. Its lifetime is seven days and refreshes on a successful analysis; losing the cookie loses access through the interface. This is a local demo boundary, not a public multi-tenant authentication system. Keep the server on loopback. CSV data is not sent to cloud providers. CSV export prefixes spreadsheet formula-like identifiers with an apostrophe while preserving the original identifier in the report.

Changing an assumption and analyzing again creates another report using the files still selected in page memory. Reloading the page does not retain the files; re-upload them to recalculate. Viewing a historical report does not change the form's next-analysis controls. The report header always shows its saved dates and demand scenario.

## Local API

- `POST /api/retail/analyses`: multipart fields `sales_file`, `inventory_file`, `as_of_date`; optional `lookback_days`, `default_lead_time_days`, `safety_days`, `review_days`, `demand_multiplier`. Returns 201. No admin key required.
- `GET /api/retail/analyses`: latest 10 summaries owned by the cookie.
- `GET /api/retail/analyses/{id}`: owned immutable report, or 404.
- `GET /api/retail/analyses/{id}/export.csv`: owned action list.
- `GET /api/retail/sample` and `/api/retail/templates/{sales|inventory}.csv`: public fictional examples.

Use `/docs` for the generated API contract. Retail validation tests run with:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_retail.py -q
```

## Limits of the recommendation

This is an inspectable planning heuristic, not a probabilistic forecast or automatic purchase-order system. Recorded sales can understate demand during prior stockouts. Promotions, seasonality, supplier reliability, pack sizes, returns, transfers and multi-echelon allocation are not modeled. Incoming stock has no ETA. Review data quality and business constraints before making replenishment decisions. A useful next pilot is comparing the ranked review list against one retailer's actual replenishment decisions and later stockouts.
