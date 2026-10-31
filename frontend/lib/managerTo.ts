// Manager TO / Turn-Over (session 101 follow-up) -- a real, timed hand-off queue for
// when a salesperson can't close and asks a manager to take a fresh crack at the
// customer. Backend: core/manager_to.py / manager_to_api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ToReason = "price" | "payment" | "trade_value" | "financing" | "just_looking" | "spouse_approval" | "product_objection" | "other";
export type ToStatus = "requested" | "claimed" | "resolved";
export type ToOutcome = "saved" | "lost" | "escalated";

export type TurnOver = {
  id: string;
  linked_entity_id: string;
  linked_entity_type: string;
  linked_entity_label: string;
  requested_by: string;
  requested_by_name: string | null;
  reason: ToReason;
  notes: string;
  status: ToStatus;
  requested_at: string;
  claimed_by: string | null;
  claimed_by_name: string | null;
  claimed_at: string | null;
  resolved_by: string | null;
  resolved_by_name: string | null;
  resolved_at: string | null;
  outcome: ToOutcome | null;
  resolution_notes: string;
};

export type ToStats = {
  sample_size: number;
  save_rate_pct: number | null;
  avg_claim_wait_minutes: number | null;
  avg_resolution_minutes: number | null;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function requestTO(linkedEntityId: string, reason: ToReason, notes?: string): Promise<TurnOver> {
  const res = await fetch(`${API_BASE}/manager-to/request`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ linked_entity_id: linkedEntityId, reason, notes: notes || "" }),
  });
  return handle(res);
}

export async function claimTO(toId: string): Promise<TurnOver> {
  const res = await fetch(`${API_BASE}/manager-to/${encodeURIComponent(toId)}/claim`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function resolveTO(toId: string, outcome: ToOutcome, notes?: string): Promise<TurnOver> {
  const res = await fetch(`${API_BASE}/manager-to/${encodeURIComponent(toId)}/resolve`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ outcome, notes: notes || "" }),
  });
  return handle(res);
}

export async function getOpenTOs(): Promise<TurnOver[]> {
  const res = await fetch(`${API_BASE}/manager-to/open`, { headers: { ...authHeaders() } });
  return handle(res);
}
