// Network's "Gap Analysis" item -- the profit leakage center, "this may become
// the most valuable screen in the entire platform" (network.pdf). Enriched
// 2026-07-18 (Intelligence Network reframe, slice 3): backend: core/
// network_menu.py's gap_analysis(), reusing core/network_benchmark.py's real
// gap_direction() (a per-KPI higher-is-better/lower-is-better semantic --
// FIXES a previously-flagged bug where the bhph department's 3 lower-is-better
// rate KPIs, delinquency/repo/charge-off, were mislabeled as an opportunity
// whenever this dealer was actually ahead of peers), core/network_root_cause.py
// (real, threshold-based Root Cause diagnostics, never a fabricated cause), and
// core/network_opportunity_value.py's exact dollar-conversion formulas (reused
// verbatim, not a second formula engine) for Revenue Impact. Served via the
// existing generic GET /menu/data?department=Network&item_key=gap_analysis
// route -- no dedicated backend route was needed for this slice.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type GapDirection = "ahead" | "behind" | "even" | "unknown";
export type GapSeverity = "high" | "medium" | "low";

export type RootCause = {
  key: string;
  label: string;
  finding: string;
  basis: string;
  supporting_data: Record<string, unknown>;
};

export type UnitImpact = {
  additional_units_monthly: number;
  unit_label: string;
  derived_dollar_impact_monthly: number | null;
  derived_dollar_impact_annualized: number | null;
  real_inputs_used: Record<string, unknown>;
};

export type PortfolioExposureImpact = {
  dollars_at_risk_reduction: number;
  basis: string;
  real_inputs_used: Record<string, unknown>;
  note: string;
};

export type RevenueImpact = {
  dollar_impact_monthly: number | null;
  annualized_dollar_impact: number | null;
  conversion_method: string;
  real_inputs_used: Record<string, unknown> | null;
  not_convertible_reason: string | null;
  unit_impact: UnitImpact | null;
  portfolio_exposure_impact: PortfolioExposureImpact | null;
};

export type GapEntry = {
  department: string;
  kpi: string;
  label: string;
  this_store: number;
  peer_average: number;
  gap: number;
  peer_gap_pct: number | null;
  format: string | null;
  higher_is_better: boolean;
  direction: GapDirection;
  is_opportunity: boolean;
  opportunity_gap: number | null;
  severity: GapSeverity | null;
  root_causes: RootCause[] | null;
  root_cause_note: string | null;
  revenue_impact: RevenueImpact | null;
};

export type NetworkGapAnalysis = {
  largest_gaps: GapEntry[];
  largest_opportunity_gaps: GapEntry[];
  all_gaps: GapEntry[];
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

export function getNetworkGapAnalysis(): Promise<NetworkGapAnalysis> {
  const params = new URLSearchParams({ department: "Network", item_key: "gap_analysis" });
  return get(`/menu/data?${params.toString()}`);
}
