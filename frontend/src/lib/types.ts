// Types mirroring the FastAPI response schemas (backend/app/schemas.py).

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ProductSummary {
  product_id: string;
  name: string | null;
  category: string | null;
  unit_price: number | null;
  history_days: number;
  observed_days: number;
  first_date: string | null;
  last_date: string | null;
  total_quantity: number;
  avg_daily_quantity: number;
  has_inventory: boolean;
  latest_forecast_id: number | null;
}

export interface DailySale {
  date: string;
  quantity: number;
  observed: boolean;
}

export interface ProductDetail extends ProductSummary {
  dataset_id: number | null;
  sales: DailySale[];
}

export interface DatasetSummary {
  id: number;
  filename: string;
  is_active: boolean;
  is_synthetic: boolean;
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  daily_records: number;
  product_count: number;
  date_start: string | null;
  date_end: string | null;
  duplicate_policy: string;
  created_at: string;
}

export interface RejectedSample {
  row_number: number;
  reasons: string[];
  values: Record<string, string>;
}

export interface ProductCoverage {
  product_id: string;
  first_date: string;
  last_date: string;
  span_days: number;
  observed_days: number;
  missing_dates: number;
  missing_date_ratio: number;
  total_quantity: number;
}

export interface PreviewRow {
  row_number: number;
  date: string;
  product_id: string;
  quantity: number;
  product_name: string | null;
  category: string | null;
  unit_price: number | null;
}

export interface ValidationReport {
  filename: string;
  is_valid: boolean;
  total_rows: number;
  accepted_rows: number;
  rejected_rows: number;
  duplicate_rows: number;
  duplicate_row_numbers: number[];
  duplicate_policy: "exclude" | "keep";
  aggregated_rows: number;
  daily_records: number;
  product_count: number;
  date_start: string | null;
  date_end: string | null;
  missing_values: Record<string, number>;
  invalid_optional_values: number;
  invalid_dates: number;
  future_dates: number;
  invalid_quantities: number;
  negative_quantities: number;
  invalid_product_ids: number;
  column_mapping: Record<string, string>;
  ignored_columns: string[];
  products: ProductCoverage[];
  rejected_samples: RejectedSample[];
  warnings: string[];
  instructions: string[];
  preview: PreviewRow[];
}

export interface DatasetDetail extends DatasetSummary {
  validation_report: ValidationReport;
}

export interface UploadResponse {
  dataset: DatasetDetail;
  report: ValidationReport;
}

export type ModelName = "moving_average" | "seasonal_naive" | "random_forest";

export interface HoldoutPoint {
  date: string;
  actual: number;
  predicted: number;
}

export interface ModelEvaluation {
  model_name: ModelName;
  role: "baseline" | "candidate";
  is_selected: boolean;
  evaluated: boolean;
  mae: number | null;
  rmse: number | null;
  test_samples: number;
  train_start: string | null;
  train_end: string | null;
  test_start: string | null;
  test_end: string | null;
  holdout: HoldoutPoint[];
  warnings: string[];
}

export interface ForecastRunSummary {
  id: number;
  product_id: string;
  product_name: string | null;
  dataset_id: number;
  horizon_days: number;
  selected_model: ModelName;
  confidence: "validated" | "low";
  history_days: number;
  forecast_start: string;
  forecast_end: string;
  total_forecast: number;
  selected_mae: number | null;
  baseline_mae: number | null;
  created_at: string;
}

export interface ForecastRunDetail extends ForecastRunSummary {
  selection_reason: string;
  observed_days: number;
  history_start: string;
  history_end: string;
  warnings: string[];
  limitations: string[];
  points: { date: string; predicted_quantity: number }[];
  evaluations: ModelEvaluation[];
}

export interface InventoryInput {
  current_stock: number;
  supplier_lead_time_days: number;
  safety_stock_days: number | null;
  safety_stock_quantity: number | null;
  minimum_order_quantity: number | null;
  order_pack_size: number | null;
  coverage_days: number;
  overstock_threshold_days: number;
}

export interface InventorySetting extends InventoryInput {
  product_id: string;
  product_name: string | null;
  category: string | null;
  created_at: string;
  updated_at: string;
}

export type Risk = "critical" | "high" | "moderate" | "low";

export interface RecommendationCalc {
  current_stock: number;
  supplier_lead_time_days: number;
  avg_daily_forecast: number;
  lead_time_demand: number;
  safety_stock: number;
  safety_stock_method: string;
  reorder_point: number;
  protection_period_days: number;
  protection_period_demand: number;
  target_stock: number;
  order_up_to_gap: number;
  reorder_needed: boolean;
  recommended_order_quantity: number;
  days_until_stockout: number | null;
  stockout_within_forecast: boolean;
  days_of_cover: number | null;
  stockout_risk: Risk;
  overstock: boolean;
  explanation: string[];
  warnings: string[];
}

export interface Recommendation {
  product_id: string;
  product_name: string | null;
  category: string | null;
  status: "ok" | "no_forecast" | "not_configured";
  message: string | null;
  inventory: InventorySetting | null;
  forecast_run_id: number | null;
  forecast_horizon_days: number | null;
  forecast_confidence: "validated" | "low" | null;
  forecast_selected_model: ModelName | null;
  forecast_created_at: string | null;
  forecast_total: number | null;
  recommendation: RecommendationCalc | null;
}

export interface RiskCounts {
  critical: number;
  high: number;
  moderate: number;
  low: number;
}

export interface DashboardSummary {
  active_dataset: DatasetSummary | null;
  recent_datasets: DatasetSummary[];
  recent_forecasts: ForecastRunSummary[];
  period_days: number;
  category: string | null;
  total_products: number;
  products_at_risk: number;
  products_requiring_reorder: number;
  products_overstocked: number;
  products_without_forecast: number;
  products_not_configured: number;
  forecast_demand: number;
  forecast_products_covered: number;
  forecast_period_warnings: string[];
  risk_counts: RiskCounts;
  demand_series: { date: string; actual: number | null; forecast: number | null }[];
  highest_risk: {
    product_id: string;
    product_name: string | null;
    stockout_risk: Risk;
    days_until_stockout: number | null;
    current_stock: number;
    reorder_point: number;
    recommended_order_quantity: number;
  }[];
  data_quality_warnings: string[];
}

export interface InsightItem {
  product_id: string;
  product_name: string | null;
  stockout_risk: Risk;
  current_stock: number;
  days_of_cover: number | null;
  days_until_stockout: number | null;
  reorder_point: number;
  target_stock: number;
  recommended_order_quantity: number;
  explanation: string[];
}

export interface Insights {
  window_days: number;
  trends: {
    product_id: string;
    product_name: string | null;
    category: string | null;
    recent_total: number;
    prior_total: number | null;
    change_pct: number | null;
    recent_avg_daily: number;
  }[];
  monthly_by_category: ({ month: string } & Record<string, number | string>)[];
  categories: string[];
  top_forecast: {
    product_id: string;
    product_name: string | null;
    horizon_days: number;
    total_forecast: number;
    avg_daily_forecast: number;
    selected_model: ModelName;
    confidence: "validated" | "low";
  }[];
  risk_counts: RiskCounts;
  overstock: InsightItem[];
  reorder_priorities: InsightItem[];
}

export interface BatchForecastResponse {
  created: ForecastRunSummary[];
  failed: { product_id: string; code: string; message: string }[];
}
