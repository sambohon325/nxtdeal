// Readiness' rebuilt "Overview" Top Menu item -- the real Enterprise Readiness
// Dashboard, and ALSO the answer to Sam's separately-named "Readiness Heatmap"
// capstone feature (a real per-department % heatmap with drill-down). Backend:
// core/readiness_overview.py / _api.py -- a pure composition layer over
// core/prediction.py (heatmap), core/enterprise_risk_center.py (Today's Risks,
// reused verbatim), and core/readiness_recommendations.py (the Executive
// Summary's "Recommended actions"). Open to every real role.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { RiskCenterOverview, Severity, ExceptionEntry } from "@/lib/enterpriseRiskCenter";

export type StatusColor = "green" | "yellow" | "red" | "gray";

export type HeatmapCell = {
  department: string;
  confidence_pct: number;
  threshold: number;
  ready: boolean;
  basis: "ledger" | "blended" | "industry_estimate";
  status_color: StatusColor;
};

export type Heatmap = {
  covered: HeatmapCell[];
  covered_count: number;
  uncovered: string[];
  uncovered_note: string;
  avg_confidence_pct: number | null;
  avg_confidence_pct_note: string;
};

export type TopRisk = {
  key: string;
  title: string;
  category: "critical" | "financial" | "operational";
  severity: Severity;
  count: number;
  resolve: { department: string; item_key: string; hint: string };
};

export type TodaysRisks = {
  top_risks: TopRisk[];
  risk_center: RiskCenterOverview;
  kpi: RiskCenterOverview["kpi"];
};

export type ExecutiveSummary = {
  text: string;
  summary: string;
  basis: "real";
  ai_generated: boolean;
  ai_polish_note?: string;
  facts: {
    avg_confidence_pct: number | null;
    confidence_label: string;
    covered_departments: string[];
    top_risks: TopRisk[];
    top_recommendations: { title?: string; recommendation?: string | null; severity?: Severity | null }[];
  };
};

export type ReadinessOverview = {
  heatmap: Heatmap;
  todays_risks: TodaysRisks;
  executive_summary: ExecutiveSummary;
  not_yet_tracked: Record<string, string>;
  generated_at: string;
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

export function getReadinessOverview(polishSummary = true): Promise<ReadinessOverview> {
  return get(`/readiness-overview/overview?polish_summary=${polishSummary}`);
}

export function regenerateExecutiveSummary(polish: boolean): Promise<ExecutiveSummary> {
  return post("/readiness-overview/regenerate-summary", { polish });
}

export type { ExceptionEntry };
