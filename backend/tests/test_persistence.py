from datetime import date

import pytest
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.exc import IntegrityError

from app.config import REPO_DIR
from app.db.migrate import upgrade_to_head
from app.db.models import Base, Dataset, ForecastRun, InventorySetting, Product, SalesRecord
from app.errors import ConflictError
from app.services import forecasts, inventory
from app.services.csv_validation import validate_sales_csv
from app.services.datasets import commit_dataset
from app.services.sample_data import generate_sample_dataframe, sample_csv_bytes
from tests.conftest import daily_rows, make_csv


def commit(db, raw, name="s.csv"):
    return commit_dataset(db, validate_sales_csv(raw, name, "text/csv"), raw, name)


def test_alembic_migrations_create_schema_matching_models(tmp_path):
    url = f"sqlite:///{(tmp_path / 'migrated.db').as_posix()}"
    upgrade_to_head(url)
    eng = create_engine(url)
    tables = set(inspect(eng).get_table_names())
    assert set(Base.metadata.tables) <= tables
    assert "alembic_version" in tables
    upgrade_to_head(url)  # idempotent
    eng.dispose()


def test_commit_dataset_persists_products_and_daily_records(db):
    raw = b"date,product_id,quantity,product_name\n2024-01-01,A,2,Apple\n2024-01-01,A,3,Apple\n2024-01-02,B,1,\n"
    ds = commit(db, raw)
    assert ds.is_active
    assert db.scalar(select(Product).where(Product.product_id == "A")).name == "Apple"
    recs = db.scalars(select(SalesRecord).order_by(SalesRecord.id)).all()
    assert [(r.quantity, r.transaction_count) for r in recs] == [(5.0, 2), (1.0, 1)]


def test_duplicate_file_cannot_be_imported_twice(db):
    raw = make_csv(daily_rows("A", 5, lambda i: 1))
    commit(db, raw)
    with pytest.raises(ConflictError):
        commit(db, raw)
    assert db.scalar(select(Dataset).where(Dataset.id == 2)) is None
    assert len(db.scalars(select(SalesRecord)).all()) == 5


def test_only_latest_dataset_active(db):
    commit(db, make_csv(daily_rows("A", 5, lambda i: 1)))
    commit(db, make_csv(daily_rows("A", 6, lambda i: 1)))
    active = db.scalars(select(Dataset).where(Dataset.is_active.is_(True))).all()
    assert [d.id for d in active] == [2]


def test_unique_constraint_on_daily_records(db):
    ds = commit(db, make_csv(daily_rows("A", 2, lambda i: 1)))
    product = db.scalar(select(Product))
    db.add(SalesRecord(dataset_id=ds.id, product_fk=product.id, date=date(2024, 1, 1), quantity=9))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()
    assert len(db.scalars(select(SalesRecord)).all()) == 2


def test_failed_commit_rolls_back(db, monkeypatch):
    raw = make_csv(daily_rows("A", 3, lambda i: 1))
    result = validate_sales_csv(raw, "s.csv", "text/csv")

    def broken(*a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(db, "bulk_insert_mappings", broken)
    with pytest.raises(RuntimeError):
        commit_dataset(db, result, raw, "s.csv")
    assert db.scalars(select(Dataset)).all() == []


def test_forecast_and_inventory_persist(db):
    commit(db, make_csv(daily_rows("A", 80, lambda i: 5 + i % 3)))
    run = forecasts.create_forecast(db, "A", 10)
    stored = db.get(ForecastRun, run.id)
    assert len(stored.points) == 10
    assert len(stored.evaluations) == 3
    inventory.create_setting(db, "A", {"current_stock": 3, "supplier_lead_time_days": 2, "coverage_days": 14,
                                       "overstock_threshold_days": 90})
    assert db.scalar(select(InventorySetting)).current_stock == 3
    recs = inventory.build_recommendations(db)
    assert recs[0]["forecast_run_id"] == run.id


def test_sample_data_is_reproducible_and_matches_committed_file():
    a = generate_sample_dataframe()
    b = generate_sample_dataframe()
    assert a.equals(b)
    assert a["product_id"].nunique() == 8
    committed = REPO_DIR / "data" / "sample_sales.csv"
    if committed.exists():
        assert committed.read_bytes().replace(b"\r\n", b"\n") == sample_csv_bytes()


def test_sample_data_validates_cleanly():
    r = validate_sales_csv(sample_csv_bytes(), "sample_sales.csv", "text/csv")
    assert r.report["rejected_rows"] == 0
    assert r.report["duplicate_rows"] == 0
    assert r.report["aggregated_rows"] > 0  # demonstrates same-day aggregation
