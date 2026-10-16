"""Forecast orchestration: load history from the DB, run the ML engine, persist results."""

from __future__ import annotations

import logging

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.db.models import ForecastPoint, ForecastRun, ModelEvaluation, Product, SalesRecord
from app.errors import AppError, NotFoundError, ValidationFailedError
from app.ml.forecasting import InsufficientHistoryError, forecast_product
from app.services.datasets import get_active_dataset
from app.services.products import get_product

logger = logging.getLogger("stockwise.forecasts")


def _require_active(db: Session):
    active = get_active_dataset(db)
    if active is None:
        raise ValidationFailedError(
            "No dataset is loaded. Upload a CSV or load the sample dataset first.",
            code="no_active_dataset",
        )
    return active


def create_forecast(db: Session, product_id: str, horizon_days: int) -> ForecastRun:
    active = _require_active(db)
    product = get_product(db, product_id)
    rows = db.execute(
        select(SalesRecord.date, SalesRecord.quantity)
        .where(SalesRecord.dataset_id == active.id, SalesRecord.product_fk == product.id)
        .order_by(SalesRecord.date)
    ).all()
    if not rows:
        raise ValidationFailedError(
            f"Product '{product_id}' has no sales in the active dataset (#{active.id}).",
            code="no_history",
        )
    try:
        result = forecast_product(
            product.product_id,
            [r[0] for r in rows],
            [r[1] for r in rows],
            horizon_days,
            end_date=active.date_end,
        )
    except InsufficientHistoryError as exc:
        raise ValidationFailedError(str(exc), code="insufficient_history") from exc

    run = ForecastRun(
        product_fk=product.id,
        dataset_id=active.id,
        horizon_days=horizon_days,
        selected_model=result.selected_model,
        selection_reason=result.selection_reason,
        confidence=result.confidence,
        history_days=result.history_days,
        observed_days=result.observed_days,
        history_start=result.history_start,
        history_end=result.history_end,
        forecast_start=result.dates[0],
        forecast_end=result.dates[-1],
        total_forecast=result.total_forecast,
        warnings=result.warnings,
        limitations=result.limitations,
        points=[
            ForecastPoint(date=d, predicted_quantity=p)
            for d, p in zip(result.dates, result.predictions)
        ],
        evaluations=[
            ModelEvaluation(
                model_name=e.model_name,
                role=e.role,
                is_selected=e.is_selected,
                evaluated=e.evaluated,
                mae=e.mae,
                rmse=e.rmse,
                test_samples=e.test_samples,
                train_start=e.train_start,
                train_end=e.train_end,
                test_start=e.test_start,
                test_end=e.test_end,
                holdout=[{**h, "date": h["date"].isoformat()} for h in e.holdout],
                warnings=e.warnings,
            )
            for e in result.evaluations
        ],
    )
    try:
        db.add(run)
        db.commit()
    except Exception:
        db.rollback()
        raise
    logger.info(
        "forecast_created id=%s product=%s horizon=%s model=%s confidence=%s",
        run.id, product.product_id, horizon_days, run.selected_model, run.confidence,
    )
    return run


def create_batch(db: Session, horizon_days: int, product_ids: list[str] | None):
    active = _require_active(db)
    if product_ids is None:
        product_ids = list(
            db.scalars(
                select(Product.product_id)
                .join(SalesRecord, SalesRecord.product_fk == Product.id)
                .where(SalesRecord.dataset_id == active.id)
                .distinct()
                .order_by(Product.product_id)
            )
        )
    created, failed = [], []
    for pid in product_ids:
        try:
            created.append(create_forecast(db, pid, horizon_days))
        except AppError as exc:
            failed.append({"product_id": pid, "code": exc.code, "message": exc.message})
    return created, failed


def get_forecast(db: Session, forecast_id: int) -> ForecastRun:
    run = db.scalar(
        select(ForecastRun)
        .where(ForecastRun.id == forecast_id)
        .options(selectinload(ForecastRun.points), selectinload(ForecastRun.evaluations))
    )
    if run is None:
        raise NotFoundError(f"Forecast {forecast_id} was not found.")
    return run


def list_forecasts(
    db: Session, product_id: str | None, dataset_id: int | None, limit: int, offset: int
) -> tuple[list[ForecastRun], int]:
    query = select(ForecastRun)
    if product_id:
        product = get_product(db, product_id)
        query = query.where(ForecastRun.product_fk == product.id)
    if dataset_id:
        query = query.where(ForecastRun.dataset_id == dataset_id)
    total = db.scalar(select(func.count()).select_from(query.subquery())) or 0
    runs = db.scalars(
        query.options(selectinload(ForecastRun.evaluations), selectinload(ForecastRun.product))
        .order_by(ForecastRun.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(runs), int(total)


def latest_run_for_product(db: Session, product_fk: int, dataset_id: int) -> ForecastRun | None:
    return db.scalar(
        select(ForecastRun)
        .where(ForecastRun.product_fk == product_fk, ForecastRun.dataset_id == dataset_id)
        .options(selectinload(ForecastRun.points))
        .order_by(ForecastRun.id.desc())
        .limit(1)
    )


def run_summary(run: ForecastRun) -> dict:
    selected = next((e for e in run.evaluations if e.is_selected), None)
    baseline = next((e for e in run.evaluations if e.role == "baseline"), None)
    return {
        "id": run.id,
        "product_id": run.product.product_id,
        "product_name": run.product.name,
        "dataset_id": run.dataset_id,
        "horizon_days": run.horizon_days,
        "selected_model": run.selected_model,
        "confidence": run.confidence,
        "history_days": run.history_days,
        "forecast_start": run.forecast_start,
        "forecast_end": run.forecast_end,
        "total_forecast": run.total_forecast,
        "selected_mae": selected.mae if selected else None,
        "baseline_mae": baseline.mae if baseline else None,
        "created_at": run.created_at,
    }


def run_detail(run: ForecastRun) -> dict:
    return {
        **run_summary(run),
        "selection_reason": run.selection_reason,
        "observed_days": run.observed_days,
        "history_start": run.history_start,
        "history_end": run.history_end,
        "warnings": run.warnings or [],
        "limitations": run.limitations or [],
        "points": run.points,
        "evaluations": run.evaluations,
    }
