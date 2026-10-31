// Readiness' "Performance Readiness" item (item #4 of Sam's 10-item
// proposed structure) -- "Goal Tracking against real pace." Backend:
// core/performance_readiness.py / _api.py. Viewing open to every real role;
// goal-setting itself lives on lib/systemConfig.ts's department-goals
// functions (ADMIN/OPERATIONS-only), not duplicated here.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type Basis = "real" | "ledger" | "blended" | "industry_estimate" | string;

export type CurrentMonthPace = {
  department: string;
  actual_to_date: number;
  days_elapsed: number;
  days_in_month: number;
  projected_month_total: number;
  basis: Basis;
  note: string;
};

export type LedgerForecast = {
  department: string;
  metric: string;
  unit: string;
  predicted_value: number;
  confidence_pct: number;
  basis: Basis;
  note: string;
};

export type DepartmentPerformanceReadiness = {
  department: string;
  label: string;
  unit: string;
  goal: number | null;
  goal_set: boolean;
  current_month_pace: CurrentMonthPace | null;
  ledger_forecast: LedgerForecast | null;
  readiness_pct: number | null;
  readiness_source: "current_month_pace" | "ledger_forecast" | null;
  status: string;
  error?: string;
};

export type PerformanceReadinessOverview = {
  departments: DepartmentPerformanceReadiness[];
  tracked_departments: string[];
  not_yet_tracked: Record<string, string>;
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

export function getPerformanceReadinessOverview(): Promise<PerformanceReadinessOverview> {
  return get("/performance-readiness/overview");
}

export function getPerformanceReadinessDepartment(department: string): Promise<DepartmentPerformanceReadiness> {
  return get(`/performance-readiness/${encodeURIComponent(department)}`);
}

// The pre-existing confidence-score content (current/target %, variance,
// risk factors against the 90% go-live threshold, core/prediction.py's
// department_readiness()) is a genuinely different concept from Goal
// Tracking above -- data trustworthiness, not business performance vs. a
// goal. It still comes through the generic GET /menu/data?department=
// Readiness&item_key=readiness route (core/readiness_menu.py's readiness()),
// reused here rather than duplicated, same "general dashboard stays behind
// /menu/data" precedent lib/governance.ts's getGovernanceMenuOverview()
// established.

export type DataConfidenceScore = {
  department: string;
  current_score_pct: number;
  target_score_pct: number;
  variance_pct: number;
  status: string;
  risk_factors: string[];
};

export type ReadinessMenuOverview = {
  goal_tracking?: PerformanceReadinessOverview;
  data_confidence_scores?: DataConfidenceScore[];
  not_yet_tracked?: Record<string, string>;
  error?: string;
};

export function getReadinessMenuOverview(): Promise<ReadinessMenuOverview> {
  const params = new URLSearchParams({ department: "Readiness", item_key: "readiness" });
  return get(`/menu/data?${params.toString()}`);
}
