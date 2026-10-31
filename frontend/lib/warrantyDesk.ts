// Service department's "Warranty" item, sixth slice of Service's rebuild --
// Warranty Eligibility Check, a real Submission Workflow (draft -> submitted
// -> approved/rejected -> paid), a Rejected Claims Queue, and Recall
// Management (real per-vehicle recall-completion tracking, genuinely new).
// Backend: core/warranty_desk.py / _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type WarrantyClaimStatus = "draft" | "submitted" | "approved" | "rejected" | "paid";

export type WarrantyClaim = {
  ro_id: string;
  service_number: string | null;
  ro_description: string | null;
  vin: string | null;
  customer_name: string | null;
  status: WarrantyClaimStatus;
  oem_claim_number: string | null;
  submitted_by: string | null;
  submitted_at: string | null;
  decided_by: string | null;
  decided_at: string | null;
  rejection_reason: string | null;
  paid_amount: number | null;
  paid_at: string | null;
  paid_by: string | null;
  cost?: string | number | null;
};

export type ClaimsQueue = {
  count: number;
  by_status: Record<string, number>;
  claims: WarrantyClaim[];
};

export type WarrantyEligibility = {
  vehicle_id: string;
  vin: string | null;
  general_warranty: { status: string; condition: string | null; note: string };
  recall_eligible_repairs: { id: string; recall_number: string; description: string }[];
  note: string;
};

export type RecallVehicleBrief = { vehicle_id: string; vin: string | null; customer_id: string; customer_name: string };

export type RecallCampaign = {
  recall_id: string;
  recall_number: string;
  make: string;
  model: string;
  description: string;
  needs_repair: RecallVehicleBrief[];
  completed: RecallVehicleBrief[];
};

export type RecallManagementQueue = {
  campaign_count: number;
  total_needs_repair: number;
  total_completed: number;
  campaigns: RecallCampaign[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getClaimsQueue(status?: string): Promise<ClaimsQueue> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  const res = await fetch(`${API_BASE}/warranty-desk/claims${params}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getRejectedClaims(): Promise<ClaimsQueue> {
  const res = await fetch(`${API_BASE}/warranty-desk/claims/rejected`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getRecallManagementQueue(): Promise<RecallManagementQueue> {
  const res = await fetch(`${API_BASE}/warranty-desk/recalls`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getWarrantyEligibility(vehicleId: string): Promise<WarrantyEligibility> {
  const res = await fetch(`${API_BASE}/warranty-desk/eligibility/${encodeURIComponent(vehicleId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function markRecallCompleted(vehicleId: string, recallId: string, roId: string) {
  const res = await fetch(`${API_BASE}/warranty-desk/recalls/mark-completed`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ vehicle_id: vehicleId, recall_id: recallId, ro_id: roId }),
  });
  return handle(res);
}

export async function submitWarrantyClaim(roId: string, oemClaimNumber?: string): Promise<WarrantyClaim> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/warranty-claim/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ oem_claim_number: oemClaimNumber || null }),
  });
  return handle(res);
}

export async function recordWarrantyDecision(roId: string, approved: boolean, rejectionReason?: string): Promise<WarrantyClaim> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/warranty-claim/decision`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ approved, rejection_reason: rejectionReason || "" }),
  });
  return handle(res);
}

export async function recordWarrantyPayment(roId: string, paidAmount: number): Promise<WarrantyClaim> {
  const res = await fetch(`${API_BASE}/repair-orders/${encodeURIComponent(roId)}/warranty-claim/payment`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ paid_amount: paidAmount }),
  });
  return handle(res);
}
