// Network's rebuilt "Overview" + "Opportunities" Top Menu items -- the first
// slice of Sam's "NXTDeal Intelligence Network" reframe. Backend: core/
// network_opportunity_value.py / core/network_overview_api.py -- a pure
// composition layer that turns core/network_menu.py's existing peer-average-
// vs-you gap math into REAL, honest dollar figures: every gap is either
// direct_currency (already dollar-shaped), derived_per_unit_real_value (a
// count gap x this dealer's own real per-unit dollar value, both real, both
// shown), or not_convertible_to_dollars (a percent/ratio gap with no real
// multiplier anywhere in this codebase -- reported honestly, never guessed).
// The base overview()/opportunities() payloads still come through the
// existing generic GET /menu/data?department=Network&item_key=... route
// (core/menu_data.py's unchanged network_overview/network_opportunities
// aliases, which now return this real dollar layer alongside the existing
// content) -- this client also covers the one new dedicated action route,
// POST /network-overview/regenerate-summary.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ConversionMethod =
  | "direct_currency"
  | "derived_per_unit_real_value"
  | "not_convertible_to_dollars";

export type DollarGap = {
  department: string;
  department_title: string;
  kpi: string;
  label: string;
  this_store: number;
  peer_average: number;
  gap: number;
  peer_gap_pct: number | null;
  format: string | null;
  is_opportunity: boolean;
  dollar_impact_monthly: number | null;
  annualized_dollar_impact: number | null;
  conversion_method: ConversionMethod;
  real_inputs_used: Record<string, unknown> | null;
  not_convertible_reason: string | null;
  excluded_from_grand_total: boolean;
};

export type DepartmentDollarOpportunity = {
  department: string;
  department_title: string;
  monthly_opportunity: number;
  annualized_opportunity: number;
  convertible_gap_count: number;
  not_convertible_gap_count: number;
  excluded_from_grand_total: boolean;
  excluded_reason: string | null;
};

export type DollarOpportunityBlock = {
  monthly: number | null;
  annualized: number | null;
  by_department: DepartmentDollarOpportunity[] | null;
  excluded_departments: string[] | null;
  basis_notice: string | null;
};

export type ExecutiveSummaryFacts = {
  avg_percentile: number | null;
  top_pct: number | null;
  top_gaps: DollarGap[];
  top_recommendations: { department?: string; finding?: string; recommendation?: string; severity?: string }[];
  total_annualized_opportunity: number | null;
};

export type NetworkExecutiveSummary = {
  text: string;
  summary: string;
  basis: "real";
  ai_generated: boolean;
  ai_polish_note?: string;
  facts: ExecutiveSummaryFacts;
};

export type DepartmentRanking = {
  department: string;
  title: string;
  percentile_rank: number | null;
};

export type PeerSnapshotEntry = {
  department: string;
  kpi: string | null;
  you: number;
  average_peer: number;
  best_peer: number;
  best_peer_note: string;
};

export type NetworkOverview = {
  network_percentile_rank: { avg_pct: number | null };
  benchmark_score: { avg_pct: number | null };
  department_rankings: DepartmentRanking[];
  peer_comparison_snapshot: PeerSnapshotEntry[];
  opportunity_tracker: { potential_gross_opportunity_monthly: number | null; basis: string; note: string };
  dollar_opportunity: DollarOpportunityBlock;
  largest_opportunities: DollarGap[] | null;
  executive_summary: NetworkExecutiveSummary;
  active_recommendations: { count: number | null };
  not_yet_tracked: Record<string, string>;
  error?: string;
};

export type NetworkOpportunitiesDollarBlock = {
  by_department: DepartmentDollarOpportunity[] | null;
  grand_total_monthly: number | null;
  grand_total_annualized: number | null;
  excluded_departments: string[] | null;
  largest_opportunities: DollarGap[] | null;
  basis_notice: string | null;
};

export type RecommendationEntry = {
  category: string;
  department: string;
  severity: "high" | "medium" | "low";
  finding: string;
  recommendation: string;
  basis: string;
};

export type NetworkOpportunities = {
  revenue_opportunities: RecommendationEntry[];
  cost_reduction_opportunities: RecommendationEntry[];
  operational_improvements: RecommendationEntry[];
  staffing_recommendations: RecommendationEntry[];
  process_improvements: RecommendationEntry[];
  note: string;
  recommendation_count: number;
  dollar_opportunities: NetworkOpportunitiesDollarBlock;
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

function post<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function getNetworkOverview(): Promise<NetworkOverview> {
  const params = new URLSearchParams({ department: "Network", item_key: "overview" });
  return get(`/menu/data?${params.toString()}`);
}

export function getNetworkOpportunities(): Promise<NetworkOpportunities> {
  const params = new URLSearchParams({ department: "Network", item_key: "opportunities" });
  return get(`/menu/data?${params.toString()}`);
}

export function regenerateNetworkSummary(polish: boolean): Promise<NetworkExecutiveSummary> {
  return post("/network-overview/regenerate-summary", { polish });
}
