import logging
from typing import Literal

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db
from app.errors import PayloadTooLargeError
from app.schemas import DatasetDetail, DatasetSummary, Page, UploadResponse, ValidationPreview
from app.services import datasets as svc
from app.services.csv_validation import validate_sales_csv
from app.services.sample_data import SAMPLE_FILENAME, sample_csv_bytes

router = APIRouter(prefix="/datasets", tags=["datasets"])
logger = logging.getLogger("stockwise.api.datasets")

DuplicatePolicyParam = Literal["exclude", "keep"]


async def _read_limited(file: UploadFile) -> bytes:
    """Read at most max_upload_bytes + 1 so oversized uploads are rejected without buffering them."""
    limit = get_settings().max_upload_bytes
    raw = await file.read(limit + 1)
    if len(raw) > limit:
        raise PayloadTooLargeError(
            f"File exceeds the maximum upload size of {limit // (1024 * 1024)} MB.",
            details={"max_bytes": limit},
        )
    return raw


def _validate(raw: bytes, file: UploadFile, policy: DuplicatePolicyParam):
    s = get_settings()
    return validate_sales_csv(
        raw,
        file.filename,
        file.content_type,
        max_bytes=s.max_upload_bytes,
        max_rows=s.max_upload_rows,
        duplicate_policy=policy,
    )


@router.post("/validate", response_model=ValidationPreview)
async def validate_upload(
    file: UploadFile = File(...),
    duplicate_policy: DuplicatePolicyParam = Query(default="exclude"),
):
    """Dry run: validate a CSV and return the report and a preview. Nothing is stored."""
    raw = await _read_limited(file)
    result = _validate(raw, file, duplicate_policy)
    logger.info(
        "dataset_validated rows=%s accepted=%s", result.report["total_rows"], result.accepted_rows
    )
    return {"report": result.report}


@router.post("/upload", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_dataset(
    file: UploadFile = File(...),
    duplicate_policy: DuplicatePolicyParam = Query(default="exclude"),
    db: Session = Depends(get_db),
):
    """Validate and commit a CSV as a new active dataset version."""
    raw = await _read_limited(file)
    result = _validate(raw, file, duplicate_policy)
    dataset = svc.commit_dataset(db, result, raw, file.filename or "upload.csv")
    return {"dataset": dataset, "report": dataset.validation_report}


@router.get("/sample", response_class=Response, responses={200: {"content": {"text/csv": {}}}})
def download_sample():
    """Download the deterministic SYNTHETIC sample dataset (seed 42)."""
    return Response(
        content=sample_csv_bytes(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{SAMPLE_FILENAME}"'},
    )


@router.post("/sample/load", response_model=UploadResponse, status_code=status.HTTP_201_CREATED)
def load_sample(db: Session = Depends(get_db)):
    """Import the synthetic sample dataset through the same validation pipeline as uploads."""
    raw = sample_csv_bytes()
    result = validate_sales_csv(raw, SAMPLE_FILENAME, "text/csv")
    dataset = svc.commit_dataset(db, result, raw, SAMPLE_FILENAME, is_synthetic=True)
    return {"dataset": dataset, "report": dataset.validation_report}


@router.get("", response_model=Page[DatasetSummary])
def list_datasets(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
):
    items, total = svc.list_datasets(db, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/{dataset_id}", response_model=DatasetDetail)
def get_dataset(dataset_id: int, db: Session = Depends(get_db)):
    return svc.get_dataset(db, dataset_id)


@router.post("/{dataset_id}/activate", response_model=DatasetSummary)
def activate_dataset(dataset_id: int, db: Session = Depends(get_db)):
    """Make an earlier dataset version the active one used for forecasting."""
    return svc.activate_dataset(db, dataset_id)
