"""Product queries scoped to the active dataset."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.db.models import Dataset, ForecastRun, InventorySetting, Product, SalesRecord
from app.errors import NotFoundError
from app.services.datasets import get_active_dataset


def get_product(db: Session, product_id: str) -> Product:
    product = db.scalar(select(Product).where(Product.product_id == product_id))
    if product is None:
        raise NotFoundError(f"Product '{product_id}' was not found.")
    return product


def _stats_query(dataset_id: int):
    return (
        select(
            SalesRecord.product_fk,
            func.min(SalesRecord.date),
            func.max(SalesRecord.date),
            func.count(SalesRecord.id),
            func.sum(SalesRecord.quantity),
        )
        .where(SalesRecord.dataset_id == dataset_id)
        .group_by(SalesRecord.product_fk)
    )


def latest_forecast_ids(db: Session, dataset_id: int) -> dict[int, int]:
    rows = db.execute(
        select(ForecastRun.product_fk, func.max(ForecastRun.id))
        .where(ForecastRun.dataset_id == dataset_id)
        .group_by(ForecastRun.product_fk)
    ).all()
    return {pfk: rid for pfk, rid in rows}


def _summary(
    product: Product, stats, has_inventory: bool, latest_id: int | None, dataset_end: date | None = None
) -> dict:
    if stats:
        first, last, observed, total = stats
        if dataset_end and dataset_end > last:
            last = dataset_end
        span = (last - first).days + 1
    else:
        first = last = None
        observed, total, span = 0, 0.0, 0
    return {
        "product_id": product.product_id,
        "name": product.name,
        "category": product.category,
        "unit_price": product.unit_price,
        "history_days": span,
        "observed_days": int(observed),
        "first_date": first,
        "last_date": last,
        "total_quantity": float(total or 0.0),
        "avg_daily_quantity": round(float(total or 0.0) / span, 4) if span else 0.0,
        "has_inventory": has_inventory,
        "latest_forecast_id": latest_id,
    }


def list_products(
    db: Session,
    *,
    search: str | None = None,
    category: str | None = None,
    include_inactive: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict], int]:
    """Products in the active dataset (or all products when include_inactive)."""
    active = get_active_dataset(db)
    stats: dict[int, tuple] = {}
    latest: dict[int, int] = {}
    if active is not None:
        stats = {row[0]: row[1:] for row in db.execute(_stats_query(active.id)).all()}
        latest = latest_forecast_ids(db, active.id)

    query = select(Product)
    if not include_inactive:
        query = query.where(Product.id.in_(list(stats)) if stats else Product.id.is_(None))
    if search:
        pattern = f"%{search.strip()}%"
        query = query.where(or_(Product.product_id.ilike(pattern), Product.name.ilike(pattern)))
    if category:
        query = query.where(Product.category == category)

    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    products = db.scalars(query.order_by(Product.product_id).limit(limit).offset(offset)).all()
    inv = set(db.scalars(select(InventorySetting.product_fk)).all())
    dataset_end = active.date_end if active else None
    items = [
        _summary(p, stats.get(p.id), p.id in inv, latest.get(p.id), dataset_end) for p in products
    ]
    return items, int(total)


def list_categories(db: Session) -> list[str]:
    rows = db.scalars(
        select(Product.category).where(Product.category.is_not(None)).distinct().order_by(Product.category)
    ).all()
    return [r for r in rows if r]


def product_sales(
    db: Session, product: Product, dataset: Dataset, start: date | None, end: date | None
) -> list[dict]:
    """Daily sales for a product, zero-filled between first and last date (observed flag)."""
    rows = db.execute(
        select(SalesRecord.date, SalesRecord.quantity)
        .where(SalesRecord.dataset_id == dataset.id, SalesRecord.product_fk == product.id)
        .order_by(SalesRecord.date)
    ).all()
    if not rows:
        return []
    by_date = {d: q for d, q in rows}
    # Zero-fill up to the dataset end, matching how the forecasting series is built.
    first, last = rows[0][0], max(rows[-1][0], dataset.date_end or rows[-1][0])
    lo = max(first, start) if start else first
    hi = min(last, end) if end else last
    out = []
    d = lo
    while d <= hi:
        out.append({"date": d, "quantity": float(by_date.get(d, 0.0)), "observed": d in by_date})
        d += timedelta(days=1)
    return out


def product_detail(db: Session, product_id: str, start: date | None, end: date | None) -> dict:
    product = get_product(db, product_id)
    active = get_active_dataset(db)
    stats = None
    latest_id = None
    sales: list[dict] = []
    if active is not None:
        row = db.execute(_stats_query(active.id).where(SalesRecord.product_fk == product.id)).first()
        stats = row[1:] if row else None
        latest_id = latest_forecast_ids(db, active.id).get(product.id)
        sales = product_sales(db, product, active, start, end)
    has_inv = db.scalar(select(InventorySetting.id).where(InventorySetting.product_fk == product.id))
    detail = _summary(
        product, stats, has_inv is not None, latest_id, active.date_end if active else None
    )
    detail["dataset_id"] = active.id if active else None
    detail["sales"] = sales
    return detail
