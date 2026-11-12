"""Reproduce the committed 30-day retail demo, without external services."""
import csv
from datetime import date, timedelta
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / 'data' / 'retail'
OUT.mkdir(parents=True, exist_ok=True)
ITEMS = [
    ('NS-COFFEE-250', 'House blend coffee 250g', 18, 3, 0, 10, 5),
    ('NS-MUG-BLUE', 'Blue ceramic mug', 28, 0, 0, 7, 2),
    ('NS-TEA-100', 'Breakfast tea 100g', 160, 10, 0, 14, 3),
    ('NS-FILTER-100', 'Coffee filters 100 pack', 0, 0, 0, 7, 1),
    ('NS-BOTTLE-750', 'Steel bottle 750ml', 8, 0, 40, 14, 1),
    ('NS-GIFT-TIN', 'Seasonal gift tin', 30, 0, 0, 10, 0),
    ('NS-NEW-SKU', 'New seasonal product', 12, 0, 0, '', None),
    ('NS-TRAVEL-CUP', 'Travel cup', 90, 0, 0, 7, 3),
]
with (OUT / 'inventory.csv').open('w', newline='', encoding='utf-8') as stream:
    writer = csv.writer(stream)
    writer.writerow(['sku', 'product_name', 'on_hand', 'reserved', 'on_order', 'lead_time_days'])
    writer.writerows(item[:-1] for item in ITEMS)
with (OUT / 'sales.csv').open('w', newline='', encoding='utf-8') as stream:
    writer = csv.writer(stream)
    writer.writerow(['date', 'sku', 'units_sold'])
    for offset in range(30):
        day = date(2026, 10, 12) + timedelta(days=offset)
        for sku, *_, daily in ITEMS:
            if daily is not None:
                writer.writerow([day.isoformat(), sku, daily])
