import csv
import io
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.config import ROOT, Settings
from app.main import create_app
from app.retail import Assumptions, CSVError, MAX_BYTES, analyze, export_csv, parse_csv


def demo(multiplier=1):
    return analyze((ROOT / 'data/retail/sales.csv').read_bytes(), (ROOT / 'data/retail/inventory.csv').read_bytes(), Assumptions(as_of_date=date(2026, 11, 11), demand_multiplier=multiplier))


def simple(sales='date,sku,units_sold\n2026-11-10,001,30\n', inventory='sku,on_hand\n001,10\n', **kwargs):
    return analyze(sales.encode(), inventory.encode(), Assumptions(as_of_date=date(2026, 11, 11), **kwargs))


def test_hand_calculated_demo():
    report = demo()
    assert report['summary'] == dict(total_skus=8, attention=4, reorder_skus=3, suggested_units=140, unknown_demand_skus=1,
                                  counts=dict(out_of_stock=1, critical=2, reorder=1, healthy=2, no_recent_sales=1, no_demand_data=1))
    rows = {r['sku']: r for r in report['rows']}
    coffee = rows['NS-COFFEE-250']
    assert (coffee['available'], coffee['daily_demand'], coffee['days_cover'], coffee['reorder_point'], coffee['target_stock'], coffee['recommended_order']) == (15, 5, 3, 85, 120, 105)
    assert coffee['projected_stockout_date'] == '2026-11-14'
    assert coffee['evidence']['inventory_line'] == 2
    assert coffee['evidence']['sales_record_count'] == 30
    assert rows['NS-MUG-BLUE']['risk'] == 'reorder'  # inclusive safety threshold
    assert rows['NS-NEW-SKU']['recommended_order'] is None
    assert rows['NS-GIFT-TIN']['recommended_order'] == 0
    assert not report['warnings']


def test_incoming_does_not_extend_cover_or_duplicate_orders():
    row = next(r for r in demo()['rows'] if r['sku'] == 'NS-BOTTLE-750')
    assert (row['days_cover'], row['risk'], row['inventory_position'], row['recommended_order']) == (8, 'critical', 48, 0)
    assert 'expedite inbound' in row['recommended_action']


def test_scenario_exact_ceiling():
    baseline, scenario = demo(), demo(1.5)
    assert baseline['summary']['suggested_units'] == 140
    assert scenario['summary']['suggested_units'] == 232
    assert baseline['id'] != scenario['id']
    assert next(r for r in scenario['rows'] if r['sku'] == 'NS-FILTER-100')['recommended_order'] == 32


def test_calendar_days_zero_and_unknown():
    report = simple(inventory='sku,on_hand\n001,10\nNEW,0\n')
    rows = {r['sku']: r for r in report['rows']}
    assert rows['001']['daily_demand'] == 1  # one observed day / 30 calendar days
    assert rows['001']['sku'] == '001'
    assert rows['NEW']['risk'] == 'out_of_stock'
    assert rows['NEW']['demand_status'] == 'unknown'
    assert rows['NEW']['recommended_order'] is None
    assert report['summary']['unknown_demand_skus'] == 1
    assert report['warnings']
    zero = simple(sales='date,sku,units_sold\n2026-11-10,001,0\n')['rows'][0]
    assert zero['risk'] == 'no_recent_sales'
    assert zero['days_cover'] is None


def test_fraction_threshold_before_display_rounding():
    row = simple(sales='date,sku,units_sold\n2026-11-10,001,3\n', inventory='sku,on_hand,lead_time_days\n001,1,10\n')['rows'][0]
    assert row['days_cover'] == 10
    assert row['risk'] == 'critical'
    assert row['reorder_point'] == 2
    assert row['target_stock'] == 3  # ceil(0.1 * 24) using fractions


@pytest.mark.parametrize('raw,kind', [
    (b'date,sku,units_sold\n2026-11-10,A,1\n2026-11-10,A,2\n', 'sales'),
    (b'sku,on_hand\nA,1\nA,2\n', 'inventory'),
    (b'sku,on_hand\nA,-1\n', 'inventory'),
    (b'sku,on_hand\nA,1.5\n', 'inventory'),
    (b'sku,on_hand\nA,NaN\n', 'inventory'),
    (b'sku,on_hand,reserved\nA,1,2\n', 'inventory'),
    (b'date,sku,units_sold\n2026-02-30,A,1\n', 'sales'),
    (b'sku,on_hand,on hand\nA,1,1\n', 'inventory'),
    (b'sku,on_hand\nA,1,extra\n', 'inventory'),
    (b'sku,on_hand\nA,"broken', 'inventory'),
    (b'\xff\xfe', 'sales'), (b'\x00', 'sales'), (b'', 'sales'),
    (b'x' * (MAX_BYTES + 1), 'sales'),
], ids=[f'invalid-{i}' for i in range(14)])
def test_reject_bad_csv(raw, kind):
    with pytest.raises(CSVError) as error:
        parse_csv(raw, kind)
    assert error.value.issues[0]['message']


def test_window_unknown_pairs_and_extra_fields():
    report = simple(sales='date,sku,units_sold,notes\n2026-11-10,001,30,private\n2026-11-11,001,100,future\n2026-11-09,X,10,unknown\n')
    assert report['rows'][0]['units_sold'] == 30
    assert len(report['warnings']) == 4
    assert 'private' not in str(report)


def test_multilocation_and_mismatch():
    sales = 'date,sku,units_sold,location\n2026-11-10,A,30,EAST\n2026-11-10,A,60,WEST\n'
    inventory = 'sku,on_hand,location\nA,10,EAST\nA,10,WEST\n'
    report = simple(sales=sales, inventory=inventory)
    assert {r['location']: r['daily_demand'] for r in report['rows']} == {'EAST': 1, 'WEST': 2}
    with pytest.raises(CSVError):
        simple(sales=sales, inventory='sku,on_hand\nA,10\n')


def test_csv_export_formula_injection():
    report = simple(sales='date,sku,units_sold\n2026-11-10,=TEST,30\n', inventory='sku,on_hand,product_name\n=TEST,10,@NAME\n')
    assert report['rows'][0]['sku'] == '=TEST'
    rows = list(csv.DictReader(io.StringIO(export_csv(report).lstrip('\ufeff'))))
    assert rows[0]['sku'] == "'=TEST"
    assert rows[0]['product_name'] == "'@NAME"


def upload(client, **params):
    return client.post('/api/retail/analyses', data={'as_of_date': '2026-11-11', **params}, files={
        'sales_file': ('sales.csv', (ROOT / 'data/retail/sales.csv').read_bytes(), 'text/csv'),
        'inventory_file': ('inventory.csv', (ROOT / 'data/retail/inventory.csv').read_bytes(), 'text/csv')})


def test_api_private_history_persistence_and_no_cloud(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('Retail analysis must not invoke cloud services')
    monkeypatch.setattr('httpx.AsyncClient.send', forbidden)
    settings = Settings(database=tmp_path / 'retail.db', admin_key='test', answer_mode='gemini', retrieval_mode='pinecone', gemini_api_key='fake', pinecone_api_key='fake')
    app = create_app(settings, seed=False)
    with TestClient(app) as first, TestClient(app) as stranger:
        response = upload(first)
        assert response.status_code == 201, response.text
        report = response.json()
        path = '/api/retail/analyses/' + report['id']
        assert 'HttpOnly' in response.headers['set-cookie']
        assert first.get(path).json() == report
        assert first.get('/api/retail/analyses').json()[0]['id'] == report['id']
        assert first.get(path + '/export.csv').status_code == 200
        assert stranger.get(path).status_code == 404
        assert stranger.get(path + '/export.csv').status_code == 404
        assert stranger.get('/api/retail/analyses').json() == []
        assert upload(first, demand_multiplier='1.5').json()['summary']['suggested_units'] == 232
        assert first.get(path).json()['summary']['suggested_units'] == 140
        with TestClient(create_app(settings, seed=False)) as restarted:
            restarted.cookies.update(first.cookies)
            assert restarted.get(path).json() == report


def test_api_bad_upload_atomic_and_templates(tmp_path):
    with TestClient(create_app(Settings(database=tmp_path / 'test.db', admin_key='test'), seed=False)) as client:
        response = client.post('/api/retail/analyses', data={'as_of_date': '2026-11-11'}, files={'sales_file': ('sales.csv', b'date,sku,units_sold\n2026-11-10,A,-1'), 'inventory_file': ('inv.csv', b'sku,on_hand\nA,2')})
        assert response.status_code == 422
        assert response.json()['detail']['issues'][0]['line'] == 2
        assert client.get('/api/retail/analyses').json() == []
        assert upload(client, demand_multiplier='nan').status_code == 422
        assert upload(client, lookback_days='0').status_code == 422
        assert client.get('/api/retail/sample').json()['as_of_date'] == '2026-11-11'
        assert client.get('/api/retail/templates/sales.csv').status_code == 200
        assert client.get('/api/retail/templates/secrets.csv').status_code == 404


def test_row_limit_and_bom_headers():
    with pytest.raises(CSVError):
        parse_csv(('sku,on_hand\n' + ''.join(f'{i},1\n' for i in range(5001))).encode(), 'inventory')
    rows, warnings, _ = parse_csv(b'\xef\xbb\xbf SKU ,On Hand\n0001,2\n', 'inventory')
    assert rows[0]['sku'] == '0001'
    assert rows[0]['on_hand'] == 2
    assert not warnings


def test_dates_outside_supported_projection_are_null():
    report = simple(sales='date,sku,units_sold\n2026-11-10,001,1\n', inventory='sku,on_hand\n001,1000000000\n')
    assert report['rows'][0]['days_cover'] == 30000000000
    assert report['rows'][0]['projected_stockout_date'] is None
    with pytest.raises(CSVError):
        analyze(b'date,sku,units_sold\n0001-01-01,A,1\n', b'sku,on_hand\nA,1\n', Assumptions(as_of_date=date.min))
