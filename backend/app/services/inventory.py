"""Inventory settings persistence and recommendation assembly."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.models import ForecastRun, InventorySetting, Product, SalesRecord
from app.errors import ConflictError, NotFoundError
from app.services.datasets import get_active_dataset
from app.services.inventory_policy import RISK_ORDER, InventoryConfig, recommend
from app.services.products import latest_forecast_ids, get_product

logger = logging.getLogger("stockwise.inventory")

SETTING_FIELDS = (
    "current_stock",
    "supplier_lead_time_days",
    "safety_stock_days",
    "safety_stock_quantity",
    "minimum_order_quantity",
    "order_pack_size",
    "coverage_days",
    "overstock_threshold_days",
)


def setting_out(setting: InventorySetting) -> dict:
    return {
        "product_id": setting.product.product_id,
        "product_name": setting.product.name,
        "category": setting.product.category,
        **{f: getattr(setting, f) for f in SETTING_FIELDS},
        "created_at": setting.created_at,
        "updated_at": setting.updated_at,
    }


def list_settings(db: Session) -> list[InventorySetting]:
    return list(
        db.scalars(
            select(InventorySetting)
            .join(Product)
            .options(selectinload(InventorySetting.product))
            .order_by(Product.product_id)
        )
    )


def create_setting(db: Session, product_id: str, values: dict) -> InventorySetting:
    product = get_product(db, product_id)
    if db.scalar(select(InventorySetting).where(InventorySetting.product_fk == product.id)):
        raise ConflictError(
            f"Inventory settings for '{product_id}' already exist; use PUT to update them.",
            code="inventory_exists",
        )
    setting = InventorySetting(product_fk=product.id, **{f: values.get(f) for f in SETTING_FIELDS})
    try:
        db.add(setting)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(setting)
    logger.info("inventory_created product=%s", product_id)
    return setting


def update_setting(db: Session, product_id: str, values: dict) -> InventorySetting:
    product = get_product(db, product_id)
    setting = db.scalar(select(InventorySetting).where(InventorySetting.product_fk == product.id))
    if setting is None:
        raise NotFoundError(
            f"No inventory settings exist for '{product_id}'; create them with POST first.",
            code="inventory_not_found",
        )
    for f in SETTING_FIELDS:
        setattr(setting, f, values.get(f))
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(setting)
    logger.info("inventory_updated product=%s", product_id)
    return setting


def build_recommendations(db: Session) -> list[dict]:
    """One entry per product in the active dataset, using its latest forecast run."""
    active = get_active_dataset(db)
    if active is None:
        return []
    products = db.scalars(
        select(Product)
        .where(
            Product.id.in_(
                select(SalesRecord.product_fk).where(SalesRecord.dataset_id == active.id).distinct()
            )
        )
        .options(selectinload(Product.inventory))
        .order_by(Product.product_id)
    ).all()

    latest = latest_forecast_ids(db, active.id)
    runs = {
        r.product_fk: r
        for r in db.scalars(
            select(ForecastRun)
            .where(ForecastRun.id.in_(list(latest.values())))
            .options(selectinload(ForecastRun.points))
        )
    }

    out = []
    for p in products:
        base = {"product_id": p.product_id, "product_name": p.name, "category": p.category}
        setting = p.inventory
        run = runs.get(p.id)
        if setting is None:
            out.append(
                {
                    **base,
                    "status": "not_configured",
                    "message": "Configure current stock and supplier lead time to get a recommendation.",
                }
            )
            continue
        if run is None:
            out.append(
                {
                    **base,
                    "status": "no_forecast",
                    "message": "Generate a forecast for this product to get a recommendation.",
                    "inventory": setting_out(setting),
                }
            )
            continue
        config = InventoryConfig(**{f: getattr(setting, f) for f in SETTING_FIELDS})
        rec = recommend(config, [pt.predicted_quantity for pt in run.points])
        if run.confidence != "validated":
            rec.warnings.append(
                "The underlying forecast is low confidence (insufficient history for validation)."
            )
        out.append(
            {
                **base,
                "status": "ok",
                "inventory": setting_out(setting),
                "forecast_run_id": run.id,
                "forecast_horizon_days": run.horizon_days,
                "forecast_confidence": run.confidence,
                "forecast_selected_model": run.selected_model,
                "forecast_created_at": run.created_at,
                "forecast_total": run.total_forecast,
                "recommendation": rec.to_dict(),
            }
        )

    def sort_key(item):
        rec = item.get("recommendation")
        if rec is None:
            return (9, float("inf"), item["product_id"])
        stockout = rec["days_until_stockout"]
        return (
            RISK_ORDER[rec["stockout_risk"]],
            stockout if stockout is not None else float("inf"),
            item["product_id"],
        )

    return sorted(out, key=sort_key)
