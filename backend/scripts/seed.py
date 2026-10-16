"""Load the synthetic sample dataset, demo inventory settings and initial forecasts.

Usage (from backend/):  python -m scripts.seed [--reset] [--horizon 60]

Runs the same service functions the API uses. Inventory values below are demo
*configuration* (stock on hand, lead times) chosen to show different risk situations;
all forecasts, metrics and recommendations are computed from the data.
"""

import argparse

from app.config import get_settings
from app.db.migrate import upgrade_to_head
from app.db.session import SessionLocal
from app.errors import ConflictError
from app.services import forecasts, inventory
from app.services.csv_validation import validate_sales_csv
from app.services.datasets import activate_dataset, commit_dataset
from app.services.sample_data import SAMPLE_FILENAME, sample_csv_bytes
from scripts.init_db import reset_sqlite

DEMO_INVENTORY = {
    "SKU-1001": dict(current_stock=250, supplier_lead_time_days=10, safety_stock_days=5,
                     minimum_order_quantity=100, order_pack_size=24),
    "SKU-1002": dict(current_stock=500, supplier_lead_time_days=14, safety_stock_days=4),
    "SKU-1003": dict(current_stock=220, supplier_lead_time_days=7, safety_stock_days=5),
    "SKU-1004": dict(current_stock=400, supplier_lead_time_days=21, safety_stock_quantity=5),
    "SKU-1005": dict(current_stock=600, supplier_lead_time_days=10, safety_stock_days=3),
    "SKU-1006": dict(current_stock=400, supplier_lead_time_days=5, safety_stock_quantity=100,
                     order_pack_size=50),
    "SKU-1007": dict(current_stock=1500, supplier_lead_time_days=30, safety_stock_days=7,
                     minimum_order_quantity=50, order_pack_size=25),
    "SKU-1008": dict(current_stock=60, supplier_lead_time_days=7, safety_stock_days=3),
}
DEFAULTS = dict(
    safety_stock_days=None,
    safety_stock_quantity=None,
    minimum_order_quantity=None,
    order_pack_size=None,
    coverage_days=14,
    overstock_threshold_days=90,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reset", action="store_true", help="delete the SQLite file first")
    parser.add_argument("--horizon", type=int, default=60)
    args = parser.parse_args()

    url = get_settings().database_url
    if args.reset:
        reset_sqlite(url)
    upgrade_to_head(url)

    db = SessionLocal()
    try:
        raw = sample_csv_bytes()
        result = validate_sales_csv(raw, SAMPLE_FILENAME, "text/csv")
        try:
            ds = commit_dataset(db, result, raw, SAMPLE_FILENAME, is_synthetic=True)
            print(f"Imported synthetic sample as dataset {ds.id}: {result.report['accepted_rows']} rows")
        except ConflictError as exc:
            ds = activate_dataset(db, exc.details["dataset_id"])
            print(f"Sample already imported; activated dataset {ds.id}")

        for pid, values in DEMO_INVENTORY.items():
            payload = {**DEFAULTS, **values}
            try:
                inventory.create_setting(db, pid, payload)
            except ConflictError:
                inventory.update_setting(db, pid, payload)
        print(f"Configured inventory for {len(DEMO_INVENTORY)} products")

        created, failed = forecasts.create_batch(db, args.horizon, None)
        for run in created:
            print(f"  forecast #{run.id} {run.product.product_id}: {run.selected_model} ({run.confidence})")
        for f in failed:
            print(f"  forecast failed {f['product_id']}: {f['message']}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
