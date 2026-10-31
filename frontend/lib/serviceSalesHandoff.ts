// Service-to-Sales Opportunity Handoff -- the fourth and final of Sam's
// "completely missing" Service features. Real Service signals (declined
// estimates, high-cost repairs, manual flags) promoted into real Sales
// Leads (Source="Service Handoff"), same GENERATED_LEAD-relationship
// precedent as core/orphan_owner_mining.py/core/trigger_alerts.py.
// Backend: core/service_sales_handoff.py / _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type OpportunityType = "declined_service" | "high_cost_repair" | "manual" | "equity_at_service";

export type OpportunityCandidate = {
  ro_id: string;
  opportunity_type: OpportunityType;
  customer_id: string | null;
  customer_name: string | null;
  vehicle: string | null;
  description: string | null;
  amount: number | null;
  reason: string;
  handoff_status: string;
};

export type OpportunityQueue = {
  count: number;
  declined_service_count: number;
  high_cost_repair_count: number;
  manual_count: number;
  candidates: OpportunityCandidate[];
};

export type HandoffStats = {
  open_opportunities: number;
  declined_service_count: number;
  high_cost_repair_count: number;
  manual_count: number;
  promoted_count: number;
  dismissed_count: number;
};

export type SalesHandoffState = {
  status: "open" | "promoted" | "dismissed";
  opportunity_type?: OpportunityType;
  promoted_lead_id?: string;
  promoted_by?: string;
  assigned_to?: string;
  promoted_at?: string;
  dismissed_by?: string;
  dismissed_at?: string;
  reason?: string;
  notes?: string;
  flagged_by?: string;
  flagged_at?: string;
};

export type RoHandoffStatus = { ro_id: string; sales_handoff: SalesHandoffState };

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getOpportunityQueue(limit = 50): Promise<OpportunityQueue> {
  const res = await fetch(`${API_BASE}/service-sales-handoff/queue?limit=${limit}`, { headers: { ...authHeaders() } });
  return handle(res);
}

// Phase 7: combined queue including the equity/maturity-at-service signal.
export type ConversionQueue = OpportunityQueue & { equity_at_service_count: number };

export async function getConversionQueue(limit = 50): Promise<ConversionQueue> {
  const res = await fetch(`${API_BASE}/service-sales-handoff/conversion-queue?limit=${limit}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getHandoffStats(): Promise<HandoffStats> {
  const res = await fetch(`${API_BASE}/service-sales-handoff/stats`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getRoHandoffStatus(roId: string): Promise<RoHandoffStatus> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/sales-handoff`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function flagManualOpportunity(roId: string, notes = ""): Promise<{ ro_id: string; sales_handoff: SalesHandoffState }> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/sales-handoff/flag`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ notes }),
  });
  return handle(res);
}

export async function promoteToSales(
  roId: string,
  opportunityType?: OpportunityType,
  assignedTo?: string,
  notes = ""
): Promise<{ ro_id: string; lead_id: string; customer_id: string; assigned_to: string }> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/sales-handoff/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ assigned_to: assignedTo || null, notes, opportunity_type: opportunityType || null }),
  });
  return handle(res);
}

export async function dismissOpportunity(
  roId: string,
  reason = "",
  opportunityType?: OpportunityType
): Promise<{ ro_id: string; sales_handoff: SalesHandoffState }> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/sales-handoff/dismiss`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ reason, opportunity_type: opportunityType || null }),
  });
  return handle(res);
}
