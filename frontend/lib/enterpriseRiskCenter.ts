// Readiness' reimagined "Exceptions" Top Menu item, which is ALSO Sam's
// separately-named "Enterprise Risk Center" capstone feature ("Monitor
// Compliance, Funding, Collections, Inventory, Security, Data from one
// dashboard") -- confirmed to be the same real feature before building, so
// built once. Backend: core/enterprise_risk_center.py / _api.py -- a pure
// composition layer over 9 already-real signals plus one genuinely new
// per-deal check (negative_gross_deals). Open to every real role; individual
// sub-signals degrade gracefully per their own already-real ACL.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type Severity = "low" | "medium" | "high" | "critical";

export type RiskItem = {
  id: string;
  label: string;
  severity?: Severity;
  gross?: number;
  [key: string]: unknown;
};

export type ResolveReference = {
  department: string;
  item_key: string;
  hint: string;
};

export type ExceptionEntry = {
  key: string;
  title: string;
  category: "critical" | "financial" | "operational";
  severity: Severity | null;
  count: number | null;
  basis: "real" | "heuristic";
  items: RiskItem[];
  note?: string;
  total_loss?: number;
  access_error?: string;
  resolve: ResolveReference;
};

export type RiskCenterOverview = {
  categories: {
    critical_issues: ExceptionEntry[];
    financial_exceptions: ExceptionEntry[];
    operational_exceptions: ExceptionEntry[];
  };
  kpi: {
    total_exception_types_active: number;
    total_exception_types: number;
    total_affected_entities: number;
    by_severity: Record<Severity, number>;
  };
  overall_risk_score: null;
  overall_risk_score_note: string;
};

export type ReadinessExceptions = {
  risk_center: RiskCenterOverview;
  readiness_drops: { count: number; departments: unknown[] };
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

export function getRiskCenterOverview(): Promise<RiskCenterOverview> {
  return get("/enterprise-risk/overview");
}

export function getRiskCenterCategory(category: "critical" | "financial" | "operational"): Promise<{ category: string; items: ExceptionEntry[] }> {
  return get(`/enterprise-risk/${encodeURIComponent(category)}`);
}
