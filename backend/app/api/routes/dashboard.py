from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import DatasetSummary
from app.services import analytics

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/summary")
def dashboard_summary(
    period_days: int = Query(default=30, ge=1, le=90),
    history_days: int = Query(default=90, ge=7, le=730),
    category: str | None = Query(default=None, max_length=100),
    db: Session = Depends(get_db),
):
    """KPIs, aggregated history + forecast series, recent activity and risk overview."""
    data = analytics.dashboard_summary(db, period_days, history_days, category)
    active = data["active_dataset"]
    data["active_dataset"] = DatasetSummary.model_validate(active).model_dump() if active else None
    data["recent_datasets"] = [
        DatasetSummary.model_validate(d).model_dump() for d in data["recent_datasets"]
    ]
    return data


@router.get("/insights")
def insights(window_days: int = Query(default=28, ge=7, le=180), db: Session = Depends(get_db)):
    """Demand trends, top forecast demand, overstock and reorder priorities."""
    return analytics.insights(db, window_days)
