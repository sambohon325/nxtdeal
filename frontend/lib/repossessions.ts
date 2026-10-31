// Finance's "Repossessions" item -- the fourth slice of Sam's Retail Automotive
// Lending Platform expansion (2026-07-17), the direct continuation of Collections'
// own "repossession_referral" collection stage and Sam's own stated loan lifecycle
// (...Collections -> Repossession -> Recovery -> Payoff). Backend:
// core/repossessions.py / _api.py. A real Referral Queue, a real case lifecycle
// (referred -> assigned -> located -> recovered -> stored -> disposed, with
// redeemed/cancelled as terminal off-ramps), a real Deficiency Balance calculation
// (Sam's own "Recovery" stage -- real math, no simulation), and a redemption path
// that reactivates the loan. Disposition/redemption both cascade real loan_status
// updates back onto Portfolio via core/loan_servicing.py's own set_loan_status().

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type CaseStage = "referred" | "assigned" | "located" | "recovered" | "stored" | "disposed" | "redeemed" | "cancelled";
export type DispositionType = "auction_sale" | "private_sale" | "dealer_retail";

export const CASE_STAGES: CaseStage[] = ["referred", "assigned", "located", "recovered", "stored", "disposed"];
export const TERMINAL_STAGES: CaseStage[] = ["disposed", "redeemed", "cancelled"];
export const DISPOSITION_TYPES: DispositionType[] = ["auction_sale", "private_sale", "dealer_retail"];

export const STAGE_LABELS: Record<CaseStage, string> = {
  referred: "Referred",
  assigned: "Agent Assigned",
  located: "Located",
  recovered: "Recovered",
  stored: "In Storage",
  disposed: "Disposed",
  redeemed: "Redeemed",
  cancelled: "Cancelled",
};

export type ReferralRow = {
  loan_id: string;
  finance_number: string | null;
  customer_name: string | null;
  vehicle: string | null;
  current_balance: number | null;
  current_balance_basis: string | null;
};

export type ReferralQueue = { count: number; loans: ReferralRow[] };

export type CaseBrief = {
  id: string;
  loan_id: string;
  stage: CaseStage;
  stage_label: string;
  referred_at: string;
  referred_by: string;
  agent_name: string | null;
};

export type CasesList = { count: number; cases: CaseBrief[] };

export type StageHistoryEntry = { stage: CaseStage; by: string; reason: string; at: string };

export type Disposition = {
  disposition_type: DispositionType;
  sale_price: number;
  sale_date: string;
  buyer: string;
  notes: string;
  recorded_by: string;
};

export type DeficiencyCalc = {
  case_id: string;
  loan_id: string;
  outstanding_balance: number;
  outstanding_balance_basis: string;
  storage_fees_accrued: number;
  transport_cost: number;
  sale_price: number;
  deficiency_balance: number;
  note: string;
};

export type CaseDetail = {
  id: string;
  loan_id: string;
  customer: Record<string, unknown> | null;
  vehicle: Record<string, unknown> | null;
  current_balance: number | null;
  current_balance_basis: string | null;
  stage: CaseStage;
  reason: string;
  referred_by: string;
  referred_at: string;
  balance_at_referral: number | null;
  balance_at_referral_basis: string | null;
  agent_name: string | null;
  agent_agency: string | null;
  agent_phone: string | null;
  location: string | null;
  recovered_at: string | null;
  recovered_condition: string | null;
  recovered_odometer: number | null;
  storage_facility: string | null;
  storage_start_date: string | null;
  storage_daily_rate: number | null;
  transport_cost: number;
  disposition: Disposition | null;
  redemption_amount: number | null;
  stage_history: StageHistoryEntry[];
  storage_fees_accrued: number;
  deficiency: DeficiencyCalc | null;
};

export type RepossessionsDashboard = {
  referral_queue_count: number;
  open_cases: number;
  stage_counts: Record<CaseStage, number>;
  disposed_count: number;
  redeemed_count: number;
  total_deficiency_outstanding: number;
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

function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

export function getReferralQueue(): Promise<ReferralQueue> {
  return get(`/repossessions/referral-queue`);
}

export function getRepossessionsDashboard(): Promise<RepossessionsDashboard> {
  return get(`/repossessions/dashboard`);
}

export function listCases(status?: CaseStage, loanId?: string): Promise<CasesList> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (loanId) params.set("loan_id", loanId);
  const qs = params.toString();
  return get(`/repossessions/cases${qs ? `?${qs}` : ""}`);
}

export function createCase(loanId: string, reason = ""): Promise<CaseDetail> {
  return post(`/repossessions/cases`, { loan_id: loanId, reason });
}

export function getCase(caseId: string): Promise<CaseDetail> {
  return get(`/repossessions/cases/${encodeURIComponent(caseId)}`);
}

export function assignAgent(caseId: string, agentName: string, agency = "", phone = ""): Promise<CaseDetail> {
  return post(`/repossessions/cases/${encodeURIComponent(caseId)}/assign-agent`, { agent_name: agentName, agency, phone });
}

export function recordLocation(caseId: string, location: string, notes = ""): Promise<CaseDetail> {
  return post(`/repossessions/cases/${encodeURIComponent(caseId)}/location`, { location, notes });
}

export function recordRecovery(caseId: string, recoveredDate?: string, condition = "", odometer?: number): Promise<CaseDetail> {
  return post(`/repossessions/cases/${encodeURIComponent(caseId)}/recovery`, { recovered_date: recoveredDate ?? null, condition, odometer: odometer ?? null });
}

export function recordStorage(caseId: string, storageFacility: string, storageStartDate?: string, dailyRate = 0, transportCost = 0): Promise<CaseDetail> {
  return post(`/repossessions/cases/${encodeURIComponent(caseId)}/storage`, {
    storage_facility: storageFacility,
    storage_start_date: storageStartDate ?? null,
    daily_rate: dailyRate,
    transport_cost: transportCost,
  });
}

export function recordDisposition(caseId: string, dispositionType: DispositionType, salePrice: number, saleDate?: string, buyer = "", notes = ""): Promise<CaseDetail> {
  return post(`/repossessions/cases/${encodeURIComponent(caseId)}/disposition`, {
    disposition_type: dispositionType,
    sale_price: salePrice,
    sale_date: saleDate ?? null,
    buyer,
    notes,
  });
}

export function redeemCase(caseId: string, redemptionAmount: number, notes = ""): Promise<CaseDetail> {
  return post(`/repossessions/cases/${encodeURIComponent(caseId)}/redeem`, { redemption_amount: redemptionAmount, notes });
}

export function cancelCase(caseId: string, reason = ""): Promise<CaseDetail> {
  return post(`/repossessions/cases/${encodeURIComponent(caseId)}/cancel`, { reason });
}

export function getDeficiency(caseId: string): Promise<DeficiencyCalc> {
  return get(`/repossessions/cases/${encodeURIComponent(caseId)}/deficiency`);
}
