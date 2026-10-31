// Orphan Owner Mining (session 105 follow-up) -- the ninth of Sam's ~10 "completely
// missing" dealership workflows. Real signal: a Customer who owns a Vehicle (a real
// OWNS relationship) with zero traceable salesperson attribution on file (no funded
// Deal.created_by ties the ownership back to a rep). This codebase has no Employee
// termination/departure field anywhere, so "the rep who sold this left" can't be
// computed -- "orphan" here honestly means "nobody is currently working this
// relationship," not a fabricated departure signal. Backend:
// core/orphan_owner_mining.py / orphan_owner_mining_api.py.
//
// claim_orphan_owner() creates a real new Lead (Source="Orphan Owner Mining"),
// auto-assigned to the claiming salesperson, tied back to the Customer via a real
// GENERATED_LEAD relationship -- the same promote-to-CRM mechanism sessions 84/85
// already established.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type CustomerBrief = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
};

export type VehicleBrief = {
  id: string;
  vin: string | null;
  description: string;
};

export type ServiceHistorySummary = {
  visit_count: number;
  most_recent_service_date: string | null;
};

export type OrphanOwnerEntry = {
  customer: CustomerBrief;
  vehicles_owned: { count: number; vehicles: VehicleBrief[] };
  service_history: ServiceHistorySummary;
  claimed: boolean;
  claimed_lead_id: string | null;
  claimed_by: string | null;
  has_salesperson_attribution?: boolean;
};

export type OrphanOwnerStats = {
  total_orphan_owners: number;
  unclaimed: number;
  claimed: number;
  total_vehicles_represented: number;
};

export type OrphanOwnerDashboard = {
  queue: OrphanOwnerEntry[];
  stats: OrphanOwnerStats;
};

export type ClaimOrphanOwnerResult = {
  lead_id: string;
  customer_id: string;
  vehicle_id: string;
  assigned_to: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getOrphanOwnerDashboard(): Promise<OrphanOwnerDashboard> {
  const res = await fetch(`${API_BASE}/orphan-owners/dashboard`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getOrphanOwners(limit = 50, includeClaimed = false): Promise<OrphanOwnerEntry[]> {
  const res = await fetch(
    `${API_BASE}/orphan-owners/queue?limit=${limit}&include_claimed=${includeClaimed}`,
    { headers: { ...authHeaders() } },
  );
  return handle(res);
}

export async function getOrphanOwnerDetail(customerId: string): Promise<OrphanOwnerEntry> {
  const res = await fetch(`${API_BASE}/orphan-owners/${encodeURIComponent(customerId)}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function getOrphanOwnerStats(): Promise<OrphanOwnerStats> {
  const res = await fetch(`${API_BASE}/orphan-owners/stats`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function claimOrphanOwner(customerId: string, note?: string): Promise<ClaimOrphanOwnerResult> {
  const res = await fetch(`${API_BASE}/orphan-owners/${encodeURIComponent(customerId)}/claim`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ note }),
  });
  return handle(res);
}
