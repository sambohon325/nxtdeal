// Administration's "Workflow Automation" item (Administration Control
// Center rebuild, continuing 2026-07-18/19). Backend: core/
// workflow_automation.py / _api.py -- a real, admin-configurable "if this
// real condition, then this real action" rule engine over real graph
// signals (a Deal stalled in financing/contract, a Lead with no contact
// logged, an unsold Vehicle priced at/above a threshold), firing a real
// action (create a real, trackable OperationsTask, or send a real
// notification DM via core/messaging.py) the moment a rule's condition is
// met. Deliberately NOT a third live background scheduler -- evaluated
// on-demand ("Run Rules Now") or implicitly on every dashboard fetch, same
// "compute live on read" convention this codebase uses throughout (see
// core/workflow_automation.py's own docstring for the full reasoning: this
// codebase has exactly two real scheduler precedents, both narrow, and a
// third was judged out of scope without a dedicated sign-off).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type TriggerParam = {
  key: string;
  label: string;
  kind: "text" | "number" | "enum";
  options?: string[];
  default?: unknown;
};

export type TriggerCatalogEntry = {
  type: string;
  label: string;
  description: string;
  params: TriggerParam[];
};

export type ActionCatalogEntry = {
  type: string;
  label: string;
  description: string;
  params: TriggerParam[];
};

export type AutomationRule = {
  id: string;
  name: string;
  description: string;
  trigger_type: string;
  trigger_params: Record<string, unknown>;
  action_type: string;
  action_params: Record<string, unknown>;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string;
  last_run_at: string | null;
  times_fired: number;
};

export type AutomationExecution = {
  id: string;
  rule_id: string;
  rule_name: string;
  trigger_type: string;
  action_type: string;
  target_entity_id: string;
  target_entity_type: string;
  detail: string;
  action_result: Record<string, unknown>;
  fired_at: string;
};

export type EvaluationResult = {
  rules_evaluated: number;
  fired_count: number;
  fired: {
    rule_id: string;
    rule_name: string;
    entity_id: string;
    entity_type: string;
    detail: string;
    action_result: Record<string, unknown>;
  }[];
  errors: { rule_id: string; entity_id?: string; error: string }[];
  evaluated_at: string;
};

export type AutomationDashboard = {
  rules: AutomationRule[];
  active_rule_count: number;
  trigger_catalog: TriggerCatalogEntry[];
  action_catalog: ActionCatalogEntry[];
  last_evaluation: EvaluationResult;
  recent_executions: AutomationExecution[];
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

function del<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { method: "DELETE", headers: { ...authHeaders() } }).then(handle<T>);
}

export function getAutomationDashboard(runNow = true): Promise<AutomationDashboard> {
  return get(`/automation/dashboard?run_now=${runNow ? "true" : "false"}`);
}

export function getAutomationCatalog(): Promise<{ triggers: TriggerCatalogEntry[]; actions: ActionCatalogEntry[] }> {
  return get("/automation/catalog");
}

export function runRulesNow(ruleId?: string): Promise<EvaluationResult> {
  const qs = ruleId ? `?rule_id=${encodeURIComponent(ruleId)}` : "";
  return post(`/automation/run-now${qs}`);
}

export function listAutomationRules(activeOnly = false): Promise<{ rules: AutomationRule[] }> {
  return get(`/automation-rules?active_only=${activeOnly ? "true" : "false"}`);
}

export function createAutomationRule(payload: {
  name: string;
  trigger_type: string;
  trigger_params: Record<string, unknown>;
  action_type: string;
  action_params: Record<string, unknown>;
  description?: string;
}): Promise<AutomationRule> {
  return post("/automation-rules", payload);
}

export function getAutomationRule(ruleId: string): Promise<AutomationRule> {
  return get(`/automation-rules/${ruleId}`);
}

export function setAutomationRuleActive(ruleId: string, isActive: boolean): Promise<AutomationRule> {
  return post(`/automation-rules/${ruleId}/active`, { is_active: isActive });
}

export function updateAutomationRule(
  ruleId: string,
  payload: {
    name?: string;
    description?: string;
    trigger_params?: Record<string, unknown>;
    action_params?: Record<string, unknown>;
  }
): Promise<AutomationRule> {
  return post(`/automation-rules/${ruleId}/update`, payload);
}

export function deleteAutomationRule(ruleId: string): Promise<{ deleted: string }> {
  return del(`/automation-rules/${ruleId}`);
}

export function runSingleAutomationRule(ruleId: string): Promise<EvaluationResult> {
  return post(`/automation-rules/${ruleId}/run-now`);
}

export function listAutomationExecutions(opts?: { ruleId?: string; limit?: number }): Promise<{ executions: AutomationExecution[] }> {
  const params = new URLSearchParams();
  if (opts?.ruleId) params.set("rule_id", opts.ruleId);
  if (opts?.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return get(`/automation-executions${qs ? `?${qs}` : ""}`);
}
