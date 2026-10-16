from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import (
    BatchForecastRequest,
    BatchForecastResponse,
    ForecastRequest,
    ForecastRunDetail,
    ForecastRunSummary,
    Page,
)
from app.services import forecasts as svc

router = APIRouter(prefix="/forecasts", tags=["forecasts"])


@router.post("", response_model=ForecastRunDetail, status_code=status.HTTP_201_CREATED)
def create_forecast(body: ForecastRequest, db: Session = Depends(get_db)):
    """Evaluate baseline and candidate models on a chronological holdout, select one,
    forecast the requested horizon and persist the run."""
    run = svc.create_forecast(db, body.product_id, body.horizon_days)
    return svc.run_detail(svc.get_forecast(db, run.id))


@router.post("/batch", response_model=BatchForecastResponse, status_code=status.HTTP_201_CREATED)
def create_batch(body: BatchForecastRequest, db: Session = Depends(get_db)):
    """Forecast every product in the active dataset (or the listed product_ids)."""
    created, failed = svc.create_batch(db, body.horizon_days, body.product_ids)
    return {"created": [svc.run_summary(r) for r in created], "failed": failed}


@router.get("", response_model=Page[ForecastRunSummary])
def list_forecasts(
    product_id: str | None = Query(default=None, max_length=64),
    dataset_id: int | None = Query(default=None, ge=1),
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    runs, total = svc.list_forecasts(db, product_id, dataset_id, limit, offset)
    return {
        "items": [svc.run_summary(r) for r in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/{forecast_id}", response_model=ForecastRunDetail)
def get_forecast(forecast_id: int, db: Session = Depends(get_db)):
    return svc.run_detail(svc.get_forecast(db, forecast_id))
