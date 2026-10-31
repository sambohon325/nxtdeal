// Readiness' "Forecasts" item (item #5 of Sam's 10-item proposed structure) --
// enriched (2026-07-19) into Sam's own "predictive analytics engine" framing --
// plus the "Readiness Timeline" capstone (Last 7/30/90 Days, Year To Date, "to
// spot trends"). Backend: core/readiness_forecasts.py / _api.py, and
// core/prediction.py's new historical_trend()/all_departments_historical_trend().
// Viewing open to every real role; individual sub-signals (Collections/Portfolio
// Performance) keep their own narrower ADMIN/OPERATIONS/FINANCE gate at their own
// layer and degrade gracefully to that module's own real error.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type Basis =
  | "real"
  | "ledger"
  | "blended"
  | "industry_estimate"
  | "ledger_or_industry_estimate"
  | "real_linear_projection"
  | "heuristic"
  | "heuristic_rules"
  | "simulated_payment_status"
  | "actual"
  | string;

export type HorizonPrediction = {
  department: string;
  horizon: string;
  horizon_days: number;
  metric: string;
  unit: string;
  predicted_value: number;
  confidence_pct: number;
  basis: Basis;
  sample_size: number;
  note: string;
};

export type LedgerForecastField = {
  forecast_by_horizon: HorizonPrediction[];
  basis: Basis;
  note: string;
};

export type LinearProjectionField = {
  month_to_date?: number;
  actual_to_date?: number;
  sales_count_month_to_date?: number;
  days_elapsed: number;
  days_in_month: number;
  projected_month_total: number | null;
  basis: Basis;
  note: string;
};

export type SalesForecast = {
  units: LedgerForecastField;
  gross: LinearProjectionField;
  closing_ratio: { value: number | null; basis: Basis; note: string };
  revenue: LinearProjectionField;
};

export type ServiceForecast = {
  labor_sales: LinearProjectionField | { basis: string; note: string };
  parts_sales: LinearProjectionField;
  ro_count: LedgerForecastField;
  capacity: Record<string, unknown> & { basis: Basis; note: string };
};

export type InventoryVehicleSignal = {
  vehicle_id: string;
  vin?: string;
  stock_number?: string;
  year?: string | number;
  make?: string;
  model?: string;
  price?: number | null;
  estimated_listing_age_days?: number;
  age_band?: string;
  margin_pct?: number | null;
};

export type InventoryForecast = {
  units_likely_to_sell: { count: number; vehicles: InventoryVehicleSignal[]; basis: Basis; note: string };
  units_likely_to_age: { count: number; vehicles: InventoryVehicleSignal[]; basis: Basis; note: string };
  wholesale_candidates: Record<string, unknown> & { count?: number; error?: string };
};

export type FinanceForecast = {
  funding: LedgerForecastField;
  collections: Record<string, unknown> & { error?: string };
  delinquencies: Record<string, unknown> & { error?: string };
  portfolio_performance: Record<string, unknown> & { error?: string };
};

export type ForecastsOverview = {
  sales: SalesForecast;
  service: ServiceForecast;
  inventory: InventoryForecast;
  finance: FinanceForecast;
  not_yet_tracked: Record<string, string>;
  generated_at: string;
  error?: string;
};

export type TrendWindow = {
  label: string;
  window_days: number;
  value: number;
  daily_rate: number;
  basis: Basis;
};

export type DepartmentHistoricalTrend = {
  department: string;
  metric: string;
  unit: string;
  windows: {
    last_7_days: TrendWindow;
    last_30_days: TrendWindow;
    last_90_days: TrendWindow;
    year_to_date: TrendWindow;
  };
  trend_direction: "up" | "down" | "flat";
  trend_basis: string;
  note: string;
  error?: string;
};

export type ReadinessTimelineOverview = {
  departments: Record<string, DepartmentHistoricalTrend>;
  covered_departments: string[];
  not_yet_tracked: Record<string, string>;
  generated_at: string;
  error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && Object.keys(data).length === 1)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

export function getForecastsOverview(): Promise<ForecastsOverview> {
  return get("/readiness-forecasts/overview");
}

export function getForecastsDepartment(department: string): Promise<Record<string, unknown>> {
  return get(`/readiness-forecasts/${encodeURIComponent(department)}`);
}

export function getReadinessTimelineOverview(): Promise<ReadinessTimelineOverview> {
  return get("/readiness-timeline/overview");
}

export function getReadinessTimelineDepartment(department: string): Promise<DepartmentHistoricalTrend> {
  return get(`/readiness-timeline/${encodeURIComponent(department)}`);
}
