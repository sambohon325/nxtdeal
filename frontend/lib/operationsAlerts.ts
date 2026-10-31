// Operations' "Alerts" item (session 106 follow-up #7) -- the nervous system
// unifying seven real signal types into one severity-ranked feed. Backend:
// core/operations_alerts.py / _api.py. Most alert types deep-link to an
// already-built action living in another lib client (operationsTasks,
// operationsScheduling, inventoryAging, documentWorkflows) -- this file only
// covers the feed/stats/acknowledge routes plus the one compliance action
// with no existing frontend client anywhere yet.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type AlertSeverity = "red" | "yellow";
export type AlertType =
  | "compliance"
  | "ownership_mismatch"
  | "stalled_deal"
  | "missing_deal_jacket"
  | "overdue_task"
  | "at_risk_delivery"
  | "critical_aging";

export type SuggestedAction =
  | "resolve_compliance"
  | "acknowledge"
  | "request_deal_jacket"
  | "escalate_task"
  | "schedule_delivery"
  | "reduce_price";

export type Alert = {
  alert_type: AlertType;
  severity: AlertSeverity;
  title: string;
  detail: string;
  source_id: string;
  linked_entity_id: string | null;
  suggested_action: SuggestedAction;
};

export type AlertFeed = {
  count: number;
  red_count: number;
  yellow_count: number;
  alerts: Alert[];
};

export type AlertStats = {
  total: number;
  red: number;
  yellow: number;
  by_type: Record<string, number>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getAlertFeed(): Promise<AlertFeed> {
  const res = await fetch(`${API_BASE}/operations-alerts/feed`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getAlertStats(): Promise<AlertStats> {
  const res = await fetch(`${API_BASE}/operations-alerts/stats`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function acknowledgeAlert(alertType: AlertType, sourceId: string, notes = ""): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/operations-alerts/acknowledge`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ alert_type: alertType, source_id: sourceId, notes }),
  });
  return handle(res);
}

// The one action here with no existing lib client anywhere in the frontend --
// core/compliance_api.py's resolve_alert_api has been live since session 89,
// just never had a frontend caller.
export async function resolveComplianceAlert(alertId: string, notes = ""): Promise<{ id: string }> {
  const res = await fetch(`${API_BASE}/compliance/alerts/${encodeURIComponent(alertId)}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ notes }),
  });
  return handle(res);
}
