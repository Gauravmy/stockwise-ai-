from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.errors import ValidationFailedError
from app.schemas import Page, ProductDetail, ProductSummary
from app.services import products as svc

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=Page[ProductSummary])
def list_products(
    search: str | None = Query(default=None, max_length=100),
    category: str | None = Query(default=None, max_length=100),
    include_inactive: bool = False,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    """Products in the active dataset with history statistics."""
    items, total = svc.list_products(
        db,
        search=search,
        category=category,
        include_inactive=include_inactive,
        limit=limit,
        offset=offset,
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/categories", response_model=list[str])
def list_categories(db: Session = Depends(get_db)):
    return svc.list_categories(db)


@router.get("/{product_id}", response_model=ProductDetail)
def get_product(
    product_id: str,
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
):
    """Product details plus its zero-filled daily sales series (optionally date-filtered)."""
    if start_date and end_date and start_date > end_date:
        raise ValidationFailedError(
            "start_date must be on or before end_date.", code="invalid_date_range"
        )
    return svc.product_detail(db, product_id, start_date, end_date)
