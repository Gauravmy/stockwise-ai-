"""Pydantic request/response schemas for the REST API."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Generic, Literal, TypeVar

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.ml.forecasting import MAX_HORIZON_DAYS, MIN_HORIZON_DAYS

T = TypeVar("T")


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    database: Literal["ok"]
    version: str


# ------------------------------------------------------------------ products


class ProductSummary(BaseModel):
    product_id: str
    name: str | None
    category: str | None
    unit_price: float | None
    history_days: int
    observed_days: int
    first_date: date | None
    last_date: date | None
    total_quantity: float
    avg_daily_quantity: float
    has_inventory: bool
    latest_forecast_id: int | None


class DailySale(BaseModel):
    date: date
    quantity: float
    observed: bool


class ProductDetail(ProductSummary):
    dataset_id: int | None
    sales: list[DailySale]


# ------------------------------------------------------------------ datasets


class DatasetSummary(ORMModel):
    id: int
    filename: str
    is_active: bool
    is_synthetic: bool
    total_rows: int
    accepted_rows: int
    rejected_rows: int
    duplicate_rows: int
    daily_records: int
    product_count: int
    date_start: date | None
    date_end: date | None
    duplicate_policy: str
    created_at: datetime


class DatasetDetail(DatasetSummary):
    validation_report: dict[str, Any]


class ValidationPreview(BaseModel):
    report: dict[str, Any]


class UploadResponse(BaseModel):
    dataset: DatasetDetail
    report: dict[str, Any]


# ------------------------------------------------------------------ forecasts


class ForecastRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=64)
    horizon_days: int = Field(default=30, ge=MIN_HORIZON_DAYS, le=MAX_HORIZON_DAYS)


class BatchForecastRequest(BaseModel):
    horizon_days: int = Field(default=30, ge=MIN_HORIZON_DAYS, le=MAX_HORIZON_DAYS)
    product_ids: list[str] | None = Field(default=None, max_length=500)


class ForecastPointOut(ORMModel):
    date: date
    predicted_quantity: float


class HoldoutPoint(BaseModel):
    date: date
    actual: float
    predicted: float


class ModelEvaluationOut(ORMModel):
    model_name: str
    role: str
    is_selected: bool
    evaluated: bool
    mae: float | None
    rmse: float | None
    test_samples: int
    train_start: date | None
    train_end: date | None
    test_start: date | None
    test_end: date | None
    holdout: list[HoldoutPoint]
    warnings: list[str]


class ForecastRunSummary(BaseModel):
    id: int
    product_id: str
    product_name: str | None
    dataset_id: int
    horizon_days: int
    selected_model: str
    confidence: str
    history_days: int
    forecast_start: date
    forecast_end: date
    total_forecast: float
    selected_mae: float | None
    baseline_mae: float | None
    created_at: datetime


class ForecastRunDetail(ForecastRunSummary):
    selection_reason: str
    observed_days: int
    history_start: date
    history_end: date
    warnings: list[str]
    limitations: list[str]
    points: list[ForecastPointOut]
    evaluations: list[ModelEvaluationOut]


class BatchForecastItemError(BaseModel):
    product_id: str
    code: str
    message: str


class BatchForecastResponse(BaseModel):
    created: list[ForecastRunSummary]
    failed: list[BatchForecastItemError]


# ------------------------------------------------------------------ inventory


class InventoryBase(BaseModel):
    current_stock: float = Field(ge=0, le=1e9, allow_inf_nan=False)
    supplier_lead_time_days: int = Field(ge=0, le=365)
    safety_stock_days: float | None = Field(default=None, ge=0, le=365, allow_inf_nan=False)
    safety_stock_quantity: float | None = Field(default=None, ge=0, le=1e9, allow_inf_nan=False)
    minimum_order_quantity: float | None = Field(default=None, ge=0, le=1e9, allow_inf_nan=False)
    order_pack_size: float | None = Field(default=None, gt=0, le=1e9, allow_inf_nan=False)
    coverage_days: int = Field(default=14, ge=1, le=365)
    overstock_threshold_days: int = Field(default=90, ge=1, le=3650)

    @model_validator(mode="after")
    def _one_safety_stock_method(self):
        if self.safety_stock_days is not None and self.safety_stock_quantity is not None:
            raise ValueError("Provide either safety_stock_days or safety_stock_quantity, not both.")
        return self


class InventoryCreate(InventoryBase):
    product_id: str = Field(min_length=1, max_length=64)


class InventoryUpdate(InventoryBase):
    pass


class InventoryOut(InventoryBase):
    product_id: str
    product_name: str | None
    category: str | None
    created_at: datetime
    updated_at: datetime


class RecommendationOut(BaseModel):
    product_id: str
    product_name: str | None
    category: str | None
    status: Literal["ok", "no_forecast", "not_configured"]
    message: str | None = None
    inventory: InventoryOut | None = None
    forecast_run_id: int | None = None
    forecast_horizon_days: int | None = None
    forecast_confidence: str | None = None
    forecast_selected_model: str | None = None
    forecast_created_at: datetime | None = None
    forecast_total: float | None = None
    recommendation: dict[str, Any] | None = None
