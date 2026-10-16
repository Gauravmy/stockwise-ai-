from typing import Literal

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas import InventoryCreate, InventoryOut, InventoryUpdate, RecommendationOut
from app.services import inventory as svc

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryOut])
def list_inventory(db: Session = Depends(get_db)):
    return [svc.setting_out(s) for s in svc.list_settings(db)]


@router.post("", response_model=InventoryOut, status_code=status.HTTP_201_CREATED)
def create_inventory(body: InventoryCreate, db: Session = Depends(get_db)):
    values = body.model_dump(exclude={"product_id"})
    return svc.setting_out(svc.create_setting(db, body.product_id, values))


@router.get("/recommendations", response_model=list[RecommendationOut])
def recommendations(
    risk: Literal["critical", "high", "moderate", "low"] | None = None,
    reorder_only: bool = False,
    db: Session = Depends(get_db),
):
    """Explainable reorder recommendations from the latest forecast and inventory settings,
    sorted by stockout risk then days until stockout."""
    items = svc.build_recommendations(db)
    if risk:
        items = [
            i for i in items
            if i.get("recommendation") and i["recommendation"]["stockout_risk"] == risk
        ]
    if reorder_only:
        items = [
            i for i in items
            if i.get("recommendation") and i["recommendation"]["reorder_needed"]
        ]
    return items


@router.put("/{product_id}", response_model=InventoryOut)
def update_inventory(product_id: str, body: InventoryUpdate, db: Session = Depends(get_db)):
    return svc.setting_out(svc.update_setting(db, product_id, body.model_dump()))
