// Lost Sale Recovery (session 105 follow-up) -- the eighth of Sam's ~10 "completely
// missing" dealership workflows: a combined recovery queue over every lost Lead
// (PipelineState == "LOST") and cancelled Deal, with real reason-code capture,
// outreach logging, lead reactivation (a deliberate bypass of the strict
// LEAD_WORKFLOW state machine -- LOST has no valid outgoing transition), and
// "save this pool as a real Marketing win-back List." Backend:
// core/lost_sale_recovery.py / lost_sale_recovery_api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type CustomerBrief = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
} | null;

export type VehicleBrief = {
  id: string;
  description: string;
  vin: string | null;
  price: string | number | null;
} | null;

export type PreviousLostReason = {
  reason: string;
  lost_at: string | null;
  lost_by: string | null;
  reactivated_at: string;
  reactivated_by: string;
};

export type LostLead = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  source: string | null;
  assigned_salesperson: string | null;
  lost_reason: string | null;
  lost_at: string | null;
  lost_by: string | null;
  previous_lost_reasons: PreviousLostReason[];
  converted_customer: CustomerBrief;
};

export type CancelledDeal = {
  id: string;
  status: string;
  cancelled_at: string | null;
  cancel_reason: string | null;
  cancel_reason_by: string | null;
  cancel_reason_at: string | null;
  customer: CustomerBrief;
  vehicle: VehicleBrief;
};

export type RecoveryAttempt = {
  id: string;
  body: string;
  created_by: string;
  created_at: string;
};

export type LostSaleStats = {
  total_lost_leads: number;
  total_cancelled_deals: number;
  lost_lead_reasons: Record<string, number>;
  cancelled_deal_reasons: Record<string, number>;
  recovery_rate_pct: number | null;
  leads_ever_lost: number;
  leads_reactivated: number;
};

export type LostSaleRecoveryDashboard = {
  reason_codes: string[];
  lost_leads: LostLead[];
  cancelled_deals: CancelledDeal[];
  stats: LostSaleStats;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getLostSaleRecoveryDashboard(): Promise<LostSaleRecoveryDashboard> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/dashboard`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getLostReasonCodes(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/reason-codes`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getLostLeads(limit = 50): Promise<LostLead[]> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/lost-leads?limit=${limit}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getCancelledDeals(limit = 50): Promise<CancelledDeal[]> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/cancelled-deals?limit=${limit}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getLostSaleStats(): Promise<LostSaleStats> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/stats`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function markLeadLost(leadId: string, reason: string): Promise<LostLead> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/leads/${encodeURIComponent(leadId)}/mark-lost`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ reason }),
  });
  return handle(res);
}

export async function reactivateLostLead(leadId: string, note?: string): Promise<LostLead> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/leads/${encodeURIComponent(leadId)}/reactivate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ note }),
  });
  return handle(res);
}

export async function recordDealLostReason(dealId: string, reason: string): Promise<CancelledDeal> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/deals/${encodeURIComponent(dealId)}/lost-reason`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ reason }),
  });
  return handle(res);
}

export async function logRecoveryAttempt(
  entityId: string,
  entityType: "Lead" | "Deal",
  note: string,
): Promise<RecoveryAttempt> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/log-attempt`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ entity_id: entityId, entity_type: entityType, note }),
  });
  return handle(res);
}

export async function listRecoveryAttempts(entityId: string): Promise<RecoveryAttempt[]> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/${encodeURIComponent(entityId)}/attempts`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export type SaveRecoveryPoolResult = {
  list_id: string;
  source: "lost_leads" | "cancelled_deals";
  requested: number;
  added: number;
};

export async function saveRecoveryPoolAsList(
  name: string,
  source: "lost_leads" | "cancelled_deals",
  description = "",
): Promise<SaveRecoveryPoolResult> {
  const res = await fetch(`${API_BASE}/lost-sale-recovery/save-as-list`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, source, description }),
  });
  return handle(res);
}
