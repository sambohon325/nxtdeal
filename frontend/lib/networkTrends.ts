// Network's "Trends" (real day-over-day deltas + a real 90-day-or-however-many-
// -days-were-actually-recorded snapshot history) and "Forecasts" (a real linear
// projection of this dealer's own trend, compared against the static SIMULATED
// peer average) items -- slice 4 of the Intelligence Network reframe (2026-07-18).
// Backend: core/network_menu.py's trends()/forecasts(), core/network_trends.py.
// Both served via the existing generic GET /menu/data route -- no dedicated
// backend routes were needed for this slice.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type TrendKpi = {
  key: string;
  label: string;
  value: number;
  delta_pct: number | null;
  has_history: boolean;
  compared_to: string | null;
};

export type HistoryPoint = {
  date: string;
  value: number | null;
};

export type KpiHistory = {
  department: string;
  kpi: string;
  days_requested: number;
  days_with_data: number;
  points: HistoryPoint[];
};

export type DepartmentTrendHistory = {
  department: string;
  days_requested: number;
  days_with_data: number;
  kpis: Record<string, KpiHistory>;
};

export type NetworkTrends = {
  department_trends: Record<string, TrendKpi[]>;
  history_days_requested: number;
  department_history: Record<string, DepartmentTrendHistory>;
  note: string;
  not_yet_tracked: Record<string, string>;
  error?: string;
};

export type GapProjection = {
  department: string;
  kpi: string;
  label: string;
  format: string | null;
  projectable: boolean;
  reason: string | null;
  days_with_data: number;
  current_value: number | null;
  current_date?: string;
  projected_value: number | null;
  project_days: number;
  target_date?: string;
  slope_per_day: number | null;
  basis?: string;
  formula?: string;
  peer_average?: number;
  current_gap?: number;
  projected_gap?: number;
  gap_trend: "closing" | "widening" | "holding" | "unknown";
  note: string;
};

export type NetworkForecasts = {
  project_days: number;
  history_days_considered: number;
  projectable_kpi_count: number;
  not_projectable_kpi_count: number;
  closing_gaps: GapProjection[];
  widening_gaps: GapProjection[];
  all_projections: GapProjection[];
  basis_notice: string;
  not_yet_tracked: Record<string, string>;
  error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

export function getNetworkTrends(): Promise<NetworkTrends> {
  const params = new URLSearchParams({ department: "Network", item_key: "trends" });
  return get(`/menu/data?${params.toString()}`);
}

export function getNetworkForecasts(): Promise<NetworkForecasts> {
  const params = new URLSearchParams({ department: "Network", item_key: "forecasts" });
  return get(`/menu/data?${params.toString()}`);
}
