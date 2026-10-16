"""SQLAlchemy ORM models.

Dataset versioning policy: every committed upload creates a new, immutable ``Dataset``
version with its own ``SalesRecord`` rows. Exactly one dataset is *active* at a time;
forecasts and dashboards read the active dataset. Uploading a byte-identical file a second
time is rejected (SHA-256 match) so the same import cannot be stored twice.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class UTCDateTime(TypeDecorator):
    """Stores UTC datetimes; SQLite drops tzinfo, so re-attach UTC when loading."""

    impl = DateTime
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is not None and value.tzinfo is not None:
            value = value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def process_result_value(self, value, dialect):
        if value is not None and value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value


class Base(DeclarativeBase):
    pass


class Product(Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str | None] = mapped_column(String(200))
    category: Mapped[str | None] = mapped_column(String(100), index=True)
    unit_price: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow
    )

    inventory: Mapped[InventorySetting | None] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(255))
    file_sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    file_size_bytes: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    is_synthetic: Mapped[bool] = mapped_column(Boolean, default=False)
    total_rows: Mapped[int] = mapped_column(Integer)
    accepted_rows: Mapped[int] = mapped_column(Integer)
    rejected_rows: Mapped[int] = mapped_column(Integer)
    duplicate_rows: Mapped[int] = mapped_column(Integer)
    daily_records: Mapped[int] = mapped_column(Integer)
    product_count: Mapped[int] = mapped_column(Integer)
    date_start: Mapped[date | None] = mapped_column(Date)
    date_end: Mapped[date | None] = mapped_column(Date)
    duplicate_policy: Mapped[str] = mapped_column(String(20), default="exclude")
    validation_report: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    records: Mapped[list[SalesRecord]] = relationship(
        back_populates="dataset", cascade="all, delete-orphan"
    )


class SalesRecord(Base):
    """One aggregated (product, date) daily total within a dataset version."""

    __tablename__ = "sales_records"
    __table_args__ = (
        UniqueConstraint("dataset_id", "product_fk", "date", name="uq_sales_dataset_product_date"),
        Index("ix_sales_product_date", "product_fk", "date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    product_fk: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    date: Mapped[date] = mapped_column(Date)
    quantity: Mapped[float] = mapped_column(Float)
    transaction_count: Mapped[int] = mapped_column(Integer, default=1)

    dataset: Mapped[Dataset] = relationship(back_populates="records")
    product: Mapped[Product] = relationship()


class ForecastRun(Base):
    __tablename__ = "forecast_runs"
    __table_args__ = (Index("ix_forecast_product_created", "product_fk", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_fk: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"))
    dataset_id: Mapped[int] = mapped_column(ForeignKey("datasets.id", ondelete="CASCADE"), index=True)
    horizon_days: Mapped[int] = mapped_column(Integer)
    selected_model: Mapped[str] = mapped_column(String(50))
    selection_reason: Mapped[str] = mapped_column(Text)
    confidence: Mapped[str] = mapped_column(String(20))
    history_days: Mapped[int] = mapped_column(Integer)
    observed_days: Mapped[int] = mapped_column(Integer)
    history_start: Mapped[date] = mapped_column(Date)
    history_end: Mapped[date] = mapped_column(Date)
    forecast_start: Mapped[date] = mapped_column(Date)
    forecast_end: Mapped[date] = mapped_column(Date)
    total_forecast: Mapped[float] = mapped_column(Float)
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    limitations: Mapped[list] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)

    product: Mapped[Product] = relationship()
    dataset: Mapped[Dataset] = relationship()
    points: Mapped[list[ForecastPoint]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="ForecastPoint.date"
    )
    evaluations: Mapped[list[ModelEvaluation]] = relationship(
        back_populates="run", cascade="all, delete-orphan", order_by="ModelEvaluation.id"
    )


class ForecastPoint(Base):
    __tablename__ = "forecast_points"
    __table_args__ = (UniqueConstraint("run_id", "date", name="uq_forecast_point_run_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id", ondelete="CASCADE"), index=True)
    date: Mapped[date] = mapped_column(Date)
    predicted_quantity: Mapped[float] = mapped_column(Float)

    run: Mapped[ForecastRun] = relationship(back_populates="points")


class ModelEvaluation(Base):
    __tablename__ = "model_evaluations"
    __table_args__ = (UniqueConstraint("run_id", "model_name", name="uq_eval_run_model"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("forecast_runs.id", ondelete="CASCADE"), index=True)
    model_name: Mapped[str] = mapped_column(String(50))
    role: Mapped[str] = mapped_column(String(20))  # "baseline" | "candidate"
    is_selected: Mapped[bool] = mapped_column(Boolean, default=False)
    evaluated: Mapped[bool] = mapped_column(Boolean, default=False)
    mae: Mapped[float | None] = mapped_column(Float)
    rmse: Mapped[float | None] = mapped_column(Float)
    test_samples: Mapped[int] = mapped_column(Integer, default=0)
    train_start: Mapped[date | None] = mapped_column(Date)
    train_end: Mapped[date | None] = mapped_column(Date)
    test_start: Mapped[date | None] = mapped_column(Date)
    test_end: Mapped[date | None] = mapped_column(Date)
    holdout: Mapped[list] = mapped_column(JSON, default=list)  # [{date, actual, predicted}]
    warnings: Mapped[list] = mapped_column(JSON, default=list)

    run: Mapped[ForecastRun] = relationship(back_populates="evaluations")


class InventorySetting(Base):
    __tablename__ = "inventory_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    product_fk: Mapped[int] = mapped_column(
        ForeignKey("products.id", ondelete="CASCADE"), unique=True, index=True
    )
    current_stock: Mapped[float] = mapped_column(Float)
    supplier_lead_time_days: Mapped[int] = mapped_column(Integer)
    safety_stock_days: Mapped[float | None] = mapped_column(Float)
    safety_stock_quantity: Mapped[float | None] = mapped_column(Float)
    minimum_order_quantity: Mapped[float | None] = mapped_column(Float)
    order_pack_size: Mapped[float | None] = mapped_column(Float)
    coverage_days: Mapped[int] = mapped_column(Integer, default=14)
    overstock_threshold_days: Mapped[int] = mapped_column(Integer, default=90)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime(), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime(), default=utcnow, onupdate=utcnow
    )

    product: Mapped[Product] = relationship(back_populates="inventory")
