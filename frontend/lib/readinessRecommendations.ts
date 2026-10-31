// Readiness' reimagined "Recommendations" Top Menu item, item #8 of Sam's
// 10-item Enterprise Readiness & Intelligence structure -- "This is where AI
// becomes truly valuable." Backend: core/readiness_recommendations.py / _api.py
// -- a real, transparent 12-rule engine (same standing convention as core/
// network_audit.py: every recommendation traces to a real condition crossing a
// real, documented threshold, never a fabricated LLM narrative). Open to every
// real role; individual sub-signals degrade gracefully per their own already-
// real ACL (access_error field).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type Severity = "low" | "medium" | "high" | "critical";
export type SignalType = "risk" | "opportunity";
export type Category = "sales" | "service" | "finance" | "inventory" | "marketing";

export type ResolveReference = {
  department: string;
  item_key: string;
  hint: string;
};

export type RecommendationAction = {
  action: string;
  count: number;
  items: { id: string; label: string }[];
  resolve: ResolveReference;
};

export type RecommendationItem = {
  key: string;
  category: Category;
  title: string;
  triggered: boolean;
  severity: Severity | null;
  signal_type: SignalType;
  finding: string;
  recommendation: string | null;
  basis: "real" | "heuristic";
  resolve: ResolveReference;
  access_error?: string;
  // Rule-specific extras (present on some items only)
  actions?: RecommendationAction[];
  all_flagged?: {
    service_type: string;
    recent_count: number;
    recent_revenue: number;
    prior_count: number;
    prior_revenue: number;
    delta_pct: number;
  }[];
  over_performers?: { source: string; conversion_rate: number; lead_count: number; vs_average_pct: number }[];
  under_performers?: { source: string; conversion_rate: number; lead_count: number; vs_average_pct: number }[];
  fleet_average_conversion_pct?: number;
  min_sample_size?: number;
  [key: string]: unknown;
};

export type RecommendationsOverview = {
  categories: Record<Category, RecommendationItem[]>;
  executive_recommendations: RecommendationItem[];
  kpi: {
    total_rules: number;
    triggered_count: number;
    by_severity: Record<Severity, number>;
  };
  overall_recommendation_score: null;
  overall_recommendation_score_note: string;
  generated_at: string;
};

// core/readiness_menu.py's recommendations() composition -- the department
// engine above plus core/network_audit.py's own (genuinely different,
// ADMIN/OPERATIONS/FINANCE-gated) cross-dealer recommendation feed alongside it.
export type NetworkAuditRecommendation = {
  category: string;
  department: string;
  severity: Severity;
  finding: string;
  recommendation: string;
  basis: string;
};

export type ReadinessRecommendationsMenuData = RecommendationsOverview & {
  network_audit_recommendations: NetworkAuditRecommendation[];
  network_audit_note: string | null;
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

export function getRecommendationsOverview(): Promise<RecommendationsOverview> {
  return get("/readiness-recommendations/overview");
}

export function getRecommendationsCategory(category: Category): Promise<{ category: string; items: RecommendationItem[] }> {
  return get(`/readiness-recommendations/${encodeURIComponent(category)}`);
}
