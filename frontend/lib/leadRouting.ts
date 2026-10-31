// Bumper-parity Leads Configuration client (2026-07-25): named lead-distribution rules.
// Talks to backend/api/routers/lead_routing_rules.py (/lead-routing/*, /lead-routing-rules/*).
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response, preview = false): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && data.error && !(preview && typeof data.matched === "boolean"))) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type RoutingStrategy = "round_robin" | "least_busy" | "specific_employee";

export type RoutingRule = {
  id: string;
  name: string;
  description: string;
  strategy: RoutingStrategy;
  target_department: string;
  target_employee_id: string | null;
  match_sources: string[];
  match_states: string[];
  match_cities: string[];
  endpoint: Record<string, unknown> | null;
  priority: number;
  is_active: boolean;
  times_matched: number;
  last_matched_at: string | null;
};

export type RoutingConfig = { strategies: string[]; sources: string[] };

export type RoutePreview = {
  matched: boolean;
  rule_id?: string;
  rule_name?: string;
  strategy?: string;
  would_assign_to?: string | null;
  error?: string | null;
  endpoint_dispatch?: Record<string, unknown> | null;
};

export async function getRoutingConfig(): Promise<RoutingConfig> {
  const res = await fetch(`${API_BASE}/lead-routing/config`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listRoutingRules(activeOnly = false): Promise<{ rules: RoutingRule[] }> {
  const res = await fetch(`${API_BASE}/lead-routing-rules?active_only=${activeOnly}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function createRoutingRule(input: {
  name: string;
  strategy: RoutingStrategy;
  target_department?: string | null;
  target_employee_id?: string | null;
  match_sources?: string[];
  match_states?: string[];
  match_cities?: string[];
  endpoint?: Record<string, unknown> | null;
  description?: string;
  priority?: number;
}): Promise<RoutingRule> {
  const res = await fetch(`${API_BASE}/lead-routing-rules`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function setRuleActive(ruleId: string, active: boolean): Promise<RoutingRule> {
  const res = await fetch(`${API_BASE}/lead-routing-rules/${encodeURIComponent(ruleId)}/active`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ active }),
  });
  return handle(res);
}

export async function deleteRoutingRule(ruleId: string) {
  const res = await fetch(`${API_BASE}/lead-routing-rules/${encodeURIComponent(ruleId)}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  return handle<{ ok: boolean; rule_id: string }>(res);
}

export async function previewRoute(leadAttrs: Record<string, unknown>): Promise<RoutePreview> {
  const res = await fetch(`${API_BASE}/lead-routing/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ lead_attrs: leadAttrs }),
  });
  return handle(res, true);
}
