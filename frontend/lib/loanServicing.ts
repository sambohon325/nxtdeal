// Finance's "Portfolio" item -- Loan Management, the first slice of Sam's "Retail
// Automotive Lending Platform" expansion (2026-07-17). Backend:
// core/loan_servicing.py / _api.py. The real amortization schedule/balance/terms-
// remaining are real math over real contract terms (AmountFinanced/APR/TermMonths).
// The delinquency-bucket payment status is SIMULATED per Sam's standing instruction
// ("when a lack of data is a problem, lets simply make up simulated data to
// accommodate it") -- no real payment ledger exists yet, that's the next slice
// (Payments). Every simulated figure carries basis: "simulated_payment_status" plus
// a disclaimer, surfaced as-is rather than hidden.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type LoanStatus = "active" | "paid_off" | "repossessed" | "charged_off";
export type DelinquencyBucket = "current" | "30_day" | "60_day" | "90_day" | "repossessed" | "charged_off";

export type CustomerBrief = {
  id: string;
  name: string;
  email: string | null;
  phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  zip: string | null;
  credit_score: string | number | null;
};

export type VehicleBrief = {
  id: string;
  vin: string | null;
  stock_number: string | null;
  year: string | number | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  color: string | null;
  mileage: string | number | null;
};

export type LenderBrief = { id: string; name: string | null };

export type EmploymentInfo = {
  on_file: boolean;
  note?: string;
  source_credit_application_id?: string;
  employment_status?: string | null;
  employer_name?: string | null;
  years_at_employer?: number | null;
  monthly_income?: number | null;
  housing_status?: string | null;
  monthly_housing_payment?: number | null;
};

export type ReferencesInfo = { on_file: boolean; note: string };

export type LoanBorrower = {
  customer: CustomerBrief | null;
  employment: EmploymentInfo;
  references: ReferencesInfo;
};

export type LoanVehicleSection = {
  vehicle: VehicleBrief | null;
  collateral_status: LoanStatus;
};

export type AmortizationRow = {
  period: number;
  payment: number;
  principal_portion: number;
  interest_portion: number;
  balance: number;
};

export type LoanFinancials = {
  loan_id: string;
  original_amount: number;
  apr: number;
  term_months: number;
  monthly_payment: number;
  contract_date: string | null;
  months_elapsed: number;
  terms_remaining: number;
  schedule_implied_balance: number;
  current_balance?: number;
  current_balance_basis?: string;
  schedule_implied_paid_off: boolean;
  note: string;
  payment_schedule: AmortizationRow[];
};

export type PaymentStatus = {
  loan_id: string;
  bucket: DelinquencyBucket;
  days_past_due: number;
  amount_past_due: number;
  last_payment_date: string;
  basis: string;
  disclaimer: string;
};

export type LoanTimelineEvent = { type: string; at: string | null; note: string };

export type LoanTimeline = {
  loan_id: string;
  events: LoanTimelineEvent[];
  payment_history: { entries: unknown[]; note: string };
  collection_activity: { entries: unknown[]; note: string };
  repossession_events: { entries: unknown[]; note: string };
};

export type LoanDetail = {
  loan_id: string;
  finance_number: string | null;
  loan_status: LoanStatus;
  borrower: LoanBorrower;
  vehicle: LoanVehicleSection;
  lender: LenderBrief | null;
  contract: LoanFinancials;
  payment_status: PaymentStatus;
  timeline: LoanTimeline;
};

export type LoanBrief = {
  id: string;
  finance_number: string | null;
  customer: CustomerBrief | null;
  vehicle: VehicleBrief | null;
  amount_financed: number;
  monthly_payment: number;
  apr: number;
  loan_status: LoanStatus;
  bucket: DelinquencyBucket | null;
  days_past_due: number | null;
};

export type PortfolioDashboard = {
  total_loans: number;
  active_loans: number;
  payoffs: number;
  delinquency_buckets: Record<DelinquencyBucket, number>;
  total_amount_past_due: number;
  total_outstanding_balance: number;
  basis: string;
  disclaimer: string;
  loans: LoanBrief[];
  loans_count: number;
};

export type AmortizationResult = {
  principal: number;
  apr: number;
  term_months: number;
  schedule: AmortizationRow[];
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

export function getPortfolioDashboard(bucket?: DelinquencyBucket, limit = 100): Promise<PortfolioDashboard> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (bucket) params.set("bucket", bucket);
  return get(`/loan-servicing/portfolio?${params.toString()}`);
}

export function getLoanDetail(loanId: string): Promise<LoanDetail> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}`);
}

export function getLoanFinancials(loanId: string): Promise<LoanFinancials> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/financials`);
}

export function getLoanTimeline(loanId: string): Promise<LoanTimeline> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/timeline`);
}

export function getPaymentStatus(loanId: string): Promise<PaymentStatus> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/payment-status`);
}

export function setLoanStatus(loanId: string, status: LoanStatus, reason = ""): Promise<unknown> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/status`, { status, reason });
}

export function computeAmortizationSchedule(principal: number, apr: number, termMonths: number): Promise<AmortizationResult> {
  return post(`/loan-servicing/amortize`, { principal, apr, term_months: termMonths });
}
