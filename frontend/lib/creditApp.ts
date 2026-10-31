// Credit Application (session 104 follow-up) -- the fifth of Sam's ~10 "completely
// missing" dealership workflows: a real applicant-level pre-qualification record
// (income/employment, FCRA consent, a simulated decision), tied to a Customer and
// optionally a Deal. Backend: core/credit_app.py / credit_app_api.py.
//
// Honest scope note (see core/credit_app.py's module docstring for the full version):
// there is no live credit-bureau connection in this sandbox. The "decision" reuses
// the Customer's on-file CreditScore as input to a deterministic, rules-based
// simulated engine, not a real Experian/Equifax/TransUnion pull.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type CreditAppStatus = "draft" | "decisioned" | "withdrawn";
export type CreditAppDecisionType = "approved" | "conditional" | "declined";
export type EmploymentStatus = "employed" | "self_employed" | "unemployed" | "retired" | "other";
export type HousingStatus = "own" | "rent" | "other";

export type ApplicantInfo = {
  employment_status: EmploymentStatus | null;
  employer_name: string | null;
  monthly_income: number | null;
  years_at_employer: number | null;
  monthly_housing_payment: number | null;
  housing_status: HousingStatus | null;
};

export type CoApplicantInfo = ApplicantInfo & {
  first_name?: string | null;
  last_name?: string | null;
};

export type CreditAppDecision = {
  decision: CreditAppDecisionType;
  score_band: string;
  simulated_score: number | null;
  estimated_apr: number | null;
  stipulations: string[];
  reasons: string[];
  decisioned_at: string;
};

export type CustomerBrief = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  credit_score: number | string | null;
};

export type CreditApplication = {
  id: string;
  customer_id: string;
  customer: CustomerBrief | null;
  linked_deal_id: string | null;
  status: CreditAppStatus;
  applicant: ApplicantInfo;
  co_applicant: CoApplicantInfo | null;
  requested_amount: number | null;
  ssn_last4: string;
  fcra_consent: boolean;
  fcra_consent_at: string | null;
  decision: CreditAppDecision | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  withdrawn_at: string | null;
};

export type CreditAppStats = {
  total: number;
  draft: number;
  decisioned: number;
  withdrawn: number;
  approved: number;
  conditional: number;
  declined: number;
  approval_rate_pct: number | null;
};

export type CreditAppDashboard = {
  recent: CreditApplication[];
  stats: CreditAppStats;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getCreditAppDashboard(): Promise<CreditAppDashboard> {
  const res = await fetch(`${API_BASE}/credit-apps/dashboard`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listCreditApplications(params?: {
  customer_id?: string;
  status?: CreditAppStatus;
  linked_deal_id?: string;
}): Promise<CreditApplication[]> {
  const q = new URLSearchParams();
  if (params?.customer_id) q.set("customer_id", params.customer_id);
  if (params?.status) q.set("status", params.status);
  if (params?.linked_deal_id) q.set("linked_deal_id", params.linked_deal_id);
  const res = await fetch(`${API_BASE}/credit-apps?${q.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getCreditApplication(appId: string): Promise<CreditApplication> {
  const res = await fetch(`${API_BASE}/credit-apps/${encodeURIComponent(appId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createCreditApplication(input: {
  customer_id: string;
  linked_deal_id?: string | null;
  requested_amount?: number | null;
}): Promise<CreditApplication> {
  const res = await fetch(`${API_BASE}/credit-apps`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function updateCreditApplicant(
  appId: string,
  input: {
    applicant_patch?: Partial<ApplicantInfo>;
    co_applicant_patch?: Partial<CoApplicantInfo> | Record<string, never>;
    requested_amount?: number | null;
  },
): Promise<CreditApplication> {
  const res = await fetch(`${API_BASE}/credit-apps/${encodeURIComponent(appId)}/applicant`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function setCreditAppSsnLast4(appId: string, ssnLast4: string): Promise<CreditApplication> {
  const res = await fetch(`${API_BASE}/credit-apps/${encodeURIComponent(appId)}/ssn`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ ssn_last4: ssnLast4 }),
  });
  return handle(res);
}

export async function giveCreditAppConsent(appId: string): Promise<CreditApplication> {
  const res = await fetch(`${API_BASE}/credit-apps/${encodeURIComponent(appId)}/consent`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function submitCreditApplication(appId: string): Promise<CreditApplication> {
  const res = await fetch(`${API_BASE}/credit-apps/${encodeURIComponent(appId)}/submit`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function withdrawCreditApplication(appId: string): Promise<CreditApplication> {
  const res = await fetch(`${API_BASE}/credit-apps/${encodeURIComponent(appId)}/withdraw`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function linkCreditAppToDeal(appId: string, dealId: string): Promise<CreditApplication> {
  const res = await fetch(`${API_BASE}/credit-apps/${encodeURIComponent(appId)}/link-deal`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ deal_id: dealId }),
  });
  return handle(res);
}

export async function getCreditAppFieldOptions(): Promise<{ employment_statuses: EmploymentStatus[]; housing_statuses: HousingStatus[] }> {
  const res = await fetch(`${API_BASE}/credit-apps/field-options`, { headers: { ...authHeaders() } });
  return handle(res);
}

// Generic customer search, same pattern as lib/deals.ts's searchCustomers -- filters
// the shared /search endpoint client-side to Customer records.
export type CustomerSearchResult = { id: string; entity_type: string; attributes: Record<string, unknown> };

export async function searchCustomersForCreditApp(query: string): Promise<CustomerBrief[]> {
  if (!query.trim()) return [];
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`, { headers: { ...authHeaders() } });
  const results = await handle<CustomerSearchResult[]>(res);
  return results
    .filter((r) => r.entity_type === "Customer")
    .slice(0, 20)
    .map((r) => ({
      id: r.id,
      name: `${r.attributes.FirstName || ""} ${r.attributes.LastName || ""}`.trim() || r.id,
      email: (r.attributes.Email as string) || null,
      phone: (r.attributes.Phone as string) || null,
      credit_score: (r.attributes.CreditScore as number) ?? null,
    }));
}
