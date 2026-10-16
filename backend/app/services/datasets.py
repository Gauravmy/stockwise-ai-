"""Dataset persistence: commit validated uploads as new dataset versions."""

from __future__ import annotations

import hashlib
import logging

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.db.models import Dataset, Product, SalesRecord
from app.errors import ConflictError, NotFoundError, ValidationFailedError
from app.services.csv_validation import ValidationResult

logger = logging.getLogger("stockwise.datasets")


def sha256(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def get_active_dataset(db: Session) -> Dataset | None:
    return db.scalar(select(Dataset).where(Dataset.is_active.is_(True)).order_by(Dataset.id.desc()))


def get_dataset(db: Session, dataset_id: int) -> Dataset:
    ds = db.get(Dataset, dataset_id)
    if ds is None:
        raise NotFoundError(f"Dataset {dataset_id} was not found.")
    return ds


def list_datasets(db: Session, limit: int, offset: int) -> tuple[list[Dataset], int]:
    total = db.scalar(select(func.count()).select_from(Dataset)) or 0
    rows = db.scalars(select(Dataset).order_by(Dataset.id.desc()).limit(limit).offset(offset)).all()
    return list(rows), int(total)


def commit_dataset(
    db: Session,
    result: ValidationResult,
    raw: bytes,
    filename: str,
    *,
    is_synthetic: bool = False,
) -> Dataset:
    """Persist a validated upload as a new active dataset version (single transaction)."""
    report = result.report
    if result.accepted_rows == 0:
        raise ValidationFailedError(
            "No rows passed validation, so nothing was imported.",
            code="no_valid_rows",
            details=report,
        )
    digest = sha256(raw)
    existing = db.scalar(select(Dataset).where(Dataset.file_sha256 == digest))
    if existing is not None:
        raise ConflictError(
            f"This exact file was already imported as dataset {existing.id} "
            f"('{existing.filename}'). Activate that dataset instead of importing it again.",
            code="duplicate_import",
            details={"dataset_id": existing.id},
        )

    try:
        products: dict[str, Product] = {
            p.product_id: p
            for p in db.scalars(
                select(Product).where(Product.product_id.in_(result.products["product_id"].tolist()))
            )
        }
        for row in result.products.itertuples(index=False):
            product = products.get(row.product_id)
            if product is None:
                product = Product(product_id=row.product_id)
                db.add(product)
                products[row.product_id] = product
            # Latest upload wins for descriptive attributes, but never erase with blanks.
            if row.name:
                product.name = row.name
            if row.category:
                product.category = row.category
            if row.unit_price is not None and row.unit_price == row.unit_price:
                product.unit_price = float(row.unit_price)
        db.flush()

        db.execute(update(Dataset).values(is_active=False))
        dataset = Dataset(
            filename=filename[:255],
            file_sha256=digest,
            file_size_bytes=len(raw),
            is_active=True,
            is_synthetic=is_synthetic,
            total_rows=report["total_rows"],
            accepted_rows=report["accepted_rows"],
            rejected_rows=report["rejected_rows"],
            duplicate_rows=report["duplicate_rows"],
            daily_records=report["daily_records"],
            product_count=report["product_count"],
            date_start=report["date_start"],
            date_end=report["date_end"],
            duplicate_policy=report["duplicate_policy"],
            validation_report=_jsonable(report),
        )
        db.add(dataset)
        db.flush()
        db.bulk_insert_mappings(
            SalesRecord,
            [
                {
                    "dataset_id": dataset.id,
                    "product_fk": products[r.product_id].id,
                    "date": r.date,
                    "quantity": float(r.quantity),
                    "transaction_count": int(r.transaction_count),
                }
                for r in result.daily.itertuples(index=False)
            ],
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("dataset_commit_failed filename=%s", filename[:100])
        raise
    logger.info(
        "dataset_committed id=%s rows=%s accepted=%s rejected=%s products=%s",
        dataset.id,
        report["total_rows"],
        report["accepted_rows"],
        report["rejected_rows"],
        report["product_count"],
    )
    return dataset


def activate_dataset(db: Session, dataset_id: int) -> Dataset:
    ds = get_dataset(db, dataset_id)
    try:
        db.execute(update(Dataset).values(is_active=False))
        ds.is_active = True
        db.commit()
    except Exception:
        db.rollback()
        raise
    return ds


def _jsonable(value):
    return jsonable_encoder(value)
