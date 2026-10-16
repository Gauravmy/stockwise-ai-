from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.db.session import get_db
from app.schemas import HealthResponse

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)):
    """Liveness and database connectivity check."""
    db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "ok", "version": __version__}
