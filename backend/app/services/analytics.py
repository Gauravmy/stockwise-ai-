"""Dashboard summary and insights, computed from stored data (no hardcoded metrics)."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import Dataset, ForecastRun, Product, SalesRecord
from app.services.datasets import get_active_dataset
from app.services.forecasts import run_summary
from app.services.inventory import build_recommendations
from app.services.products import latest_forecast_ids


def _latest_runs(db: Session, dataset_id: int) -> list[ForecastRun]:
    ids = list(latest_forecast_ids(db, dataset_id).values())
    if not ids:
        return []
    return list(
        db.scalars(
            select(ForecastRun)
            .where(ForecastRun.id.in_(ids))
            .options(selectinload(ForecastRun.points), selectinload(ForecastRun.product))
        )
    )


def _risk_counts(recs: list[dict]) -> dict[str, int]:
    counts = {"critical": 0, "high": 0, "moderate": 0, "low": 0}
    for r in recs:
        if r["status"] == "ok":
            counts[r["recommendation"]["stockout_risk"]] += 1
    return counts


def dashboard_summary(
    db: Session, period_days: int = 30, history_days: int = 90, category: str | None = None
) -> dict:
    active = get_active_dataset(db)
    recent_datasets = db.scalars(select(Dataset).order_by(Dataset.id.desc()).limit(5)).all()
    recent_runs = db.scalars(
        select(ForecastRun)
        .options(selectinload(ForecastRun.evaluations), selectinload(ForecastRun.product))
        .order_by(ForecastRun.id.desc())
        .limit(5)
    ).all()
    base = {
        "active_dataset": active,
        "recent_datasets": recent_datasets,
        "recent_forecasts": [run_summary(r) for r in recent_runs],
        "period_days": period_days,
        "category": category,
    }
    if active is None:
        return {
            **base,
            "total_products": 0,
            "products_at_risk": 0,
            "products_requiring_reorder": 0,
            "products_overstocked": 0,
            "products_without_forecast": 0,
            "products_not_configured": 0,
            "forecast_demand": 0.0,
            "forecast_products_covered": 0,
            "forecast_period_warnings": [],
            "risk_counts": _risk_counts([]),
            "demand_series": [],
            "highest_risk": [],
            "data_quality_warnings": [],
        }

    recs = build_recommendations(db)
    if category:
        recs = [r for r in recs if r["category"] == category]
    in_scope = {r["product_id"] for r in recs}
    ok = [r for r in recs if r["status"] == "ok"]
    risk = _risk_counts(recs)

    runs = [r for r in _latest_runs(db, active.id) if r.product.product_id in in_scope]
    forecast_total = 0.0
    period_warnings = []
    forecast_by_date: dict = defaultdict(float)
    for run in runs:
        pts = run.points[:period_days]
        forecast_total += sum(p.predicted_quantity for p in pts)
        if run.horizon_days < period_days:
            period_warnings.append(
                f"{run.product.product_id}: latest forecast covers only {run.horizon_days} of {period_days} days."
            )
        for p in pts:
            forecast_by_date[p.date] += p.predicted_quantity

    # Aggregate history over the last `history_days` of the active dataset.
    product_fks = select(Product.id).where(Product.product_id.in_(in_scope))
    hist_start = active.date_end - timedelta(days=history_days - 1) if active.date_end else None
    hist_rows = db.execute(
        select(SalesRecord.date, func.sum(SalesRecord.quantity))
        .where(
            SalesRecord.dataset_id == active.id,
            SalesRecord.product_fk.in_(product_fks),
            SalesRecord.date >= hist_start,
        )
        .group_by(SalesRecord.date)
    ).all()
    hist = {d: q for d, q in hist_rows}
    series = []
    if hist_start:
        d = hist_start
        while d <= active.date_end:
            series.append({"date": d, "actual": float(hist.get(d, 0.0)), "forecast": None})
            d += timedelta(days=1)
    for d in sorted(forecast_by_date):
        series.append({"date": d, "actual": None, "forecast": round(forecast_by_date[d], 3)})

    highest = [
        {
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "stockout_risk": r["recommendation"]["stockout_risk"],
            "days_until_stockout": r["recommendation"]["days_until_stockout"],
            "current_stock": r["recommendation"]["current_stock"],
            "reorder_point": r["recommendation"]["reorder_point"],
            "recommended_order_quantity": r["recommendation"]["recommended_order_quantity"],
        }
        for r in ok
        if r["recommendation"]["stockout_risk"] in ("critical", "high", "moderate")
    ][:5]

    return {
        **base,
        "total_products": len(recs),
        "products_at_risk": risk["critical"] + risk["high"],
        "products_requiring_reorder": sum(1 for r in ok if r["recommendation"]["reorder_needed"]),
        "products_overstocked": sum(1 for r in ok if r["recommendation"]["overstock"]),
        "products_without_forecast": sum(1 for r in recs if r["status"] == "no_forecast"),
        "products_not_configured": sum(1 for r in recs if r["status"] == "not_configured"),
        "forecast_demand": round(forecast_total, 2),
        "forecast_products_covered": len(runs),
        "forecast_period_warnings": period_warnings,
        "risk_counts": risk,
        "demand_series": series,
        "highest_risk": highest,
        "data_quality_warnings": (active.validation_report or {}).get("warnings", []),
    }


def insights(db: Session, window_days: int = 28) -> dict:
    active = get_active_dataset(db)
    if active is None or active.date_end is None:
        return {
            "window_days": window_days,
            "trends": [],
            "monthly_by_category": [],
            "categories": [],
            "top_forecast": [],
            "risk_counts": _risk_counts([]),
            "overstock": [],
            "reorder_priorities": [],
        }
    end = active.date_end
    recent_start = end - timedelta(days=window_days - 1)
    prior_start = recent_start - timedelta(days=window_days)

    rows = db.execute(
        select(Product.product_id, Product.name, Product.category, SalesRecord.date, SalesRecord.quantity)
        .join(Product, Product.id == SalesRecord.product_fk)
        .where(SalesRecord.dataset_id == active.id)
    ).all()
    recent: dict[str, float] = defaultdict(float)
    prior: dict[str, float] = defaultdict(float)
    first_seen: dict[str, object] = {}
    names: dict[str, tuple] = {}
    monthly: dict[tuple, float] = defaultdict(float)
    for pid, name, cat, d, q in rows:
        names[pid] = (name, cat)
        first_seen[pid] = min(d, first_seen.get(pid, d))
        if d >= recent_start:
            recent[pid] += q
        elif d >= prior_start:
            prior[pid] += q
        monthly[(d.strftime("%Y-%m"), cat or "Uncategorised")] += q

    trends = []
    for pid, (name, cat) in sorted(names.items()):
        has_prior = first_seen[pid] <= prior_start
        change = None
        if has_prior and prior[pid] > 0:
            change = round((recent[pid] - prior[pid]) / prior[pid] * 100, 1)
        trends.append(
            {
                "product_id": pid,
                "product_name": name,
                "category": cat,
                "recent_total": round(recent[pid], 2),
                "prior_total": round(prior[pid], 2) if has_prior else None,
                "change_pct": change,
                "recent_avg_daily": round(recent[pid] / window_days, 3),
            }
        )

    categories = sorted({c for _, c in monthly})
    months = sorted({m for m, _ in monthly})
    monthly_rows = [
        {"month": m, **{c: round(monthly.get((m, c), 0.0), 2) for c in categories}} for m in months
    ]

    runs = _latest_runs(db, active.id)
    top = sorted(
        (
            {
                "product_id": r.product.product_id,
                "product_name": r.product.name,
                "horizon_days": r.horizon_days,
                "total_forecast": r.total_forecast,
                "avg_daily_forecast": round(r.total_forecast / r.horizon_days, 3),
                "selected_model": r.selected_model,
                "confidence": r.confidence,
            }
            for r in runs
        ),
        key=lambda x: -x["avg_daily_forecast"],
    )

    recs = build_recommendations(db)
    ok = [r for r in recs if r["status"] == "ok"]

    def brief(r):
        rec = r["recommendation"]
        return {
            "product_id": r["product_id"],
            "product_name": r["product_name"],
            "stockout_risk": rec["stockout_risk"],
            "current_stock": rec["current_stock"],
            "days_of_cover": rec["days_of_cover"],
            "days_until_stockout": rec["days_until_stockout"],
            "reorder_point": rec["reorder_point"],
            "target_stock": rec["target_stock"],
            "recommended_order_quantity": rec["recommended_order_quantity"],
            "explanation": rec["explanation"],
        }

    return {
        "window_days": window_days,
        "trends": trends,
        "monthly_by_category": monthly_rows,
        "categories": categories,
        "top_forecast": top,
        "risk_counts": _risk_counts(recs),
        "overstock": [brief(r) for r in ok if r["recommendation"]["overstock"]],
        "reorder_priorities": [brief(r) for r in ok if r["recommendation"]["reorder_needed"]],
    }
