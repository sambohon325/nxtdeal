// Finance's "Payments" item -- the real payment ledger, the second slice of Sam's
// Retail Automotive Lending Platform expansion (2026-07-17), right after Portfolio.
// Backend: core/payments.py / _api.py. Recording a payment is real; the gateway
// approval/decline itself is honestly SIMULATED (basis: "simulated_payment_gateway")
// -- no real ACH/card processor is connected in this system. Once real payments
// exist for a loan, core/loan_servicing.py's balance/delinquency computation prefers
// this real ledger over its own simulated estimate automatically.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type PaymentMethod = "ach" | "debit_card" | "credit_card" | "cash" | "cash_app" | "venmo" | "apple_pay" | "google_pay";
export type PaymentStatus = "approved" | "declined";
export type AutoDraftStatus = "active" | "paused";
export type PromiseStatus = "pending" | "kept" | "broken";

export const PAYMENT_METHODS: PaymentMethod[] = ["ach", "debit_card", "credit_card", "cash", "cash_app", "venmo", "apple_pay", "google_pay"];

export type Payment = {
  id: string;
  loan_id: string;
  amount: number;
  method: PaymentMethod;
  status: PaymentStatus;
  decline_reason: string | null;
  principal_portion: number;
  interest_portion: number;
  balance_before: number;
  balance_after: number;
  recorded_by: string;
  payment_date: string;
  notes: string;
  created_at: string;
  basis: string;
  disclaimer: string;
};

export type PaymentsForLoan = { loan_id: string; count: number; payments: Payment[] };

export type RealPaymentSummary = {
  loan_id: string;
  has_real_payments: boolean;
  total_paid?: number;
  total_principal_paid?: number;
  total_interest_paid?: number;
  real_balance?: number;
  last_payment_date?: string;
  payment_count?: number;
  expected_cumulative?: number;
  shortfall?: number;
  bucket?: string;
  days_past_due?: number;
  amount_past_due?: number;
  basis?: string;
  disclaimer?: string;
};

export type AutoDraft = {
  id: string;
  loan_id: string;
  amount: number;
  method: PaymentMethod;
  day_of_month: number;
  status: AutoDraftStatus;
  created_by: string;
  created_at: string;
  last_run_at: string | null;
  last_run_month: string | null;
  run_history: { payment_id: string | null; status: string; run_at: string }[];
};

export type AutoDraftsList = { count: number; drafts: AutoDraft[] };

export type PromiseToPay = {
  id: string;
  loan_id: string;
  promise_date: string;
  amount: number;
  reason: string;
  created_by: string;
  created_at: string;
  paid_since_promise: number;
  status: PromiseStatus;
};

export type PaymentAdjustment = {
  type: "extension" | "deferral";
  new_next_due_date?: string;
  months?: number;
  reason: string;
  recorded_by: string;
  recorded_at: string;
};

export type PayoffRequest = {
  id: string;
  loan_id?: string;
  requested_by: string;
  requested_at: string;
  notes: string;
  status: "requested" | "fulfilled";
  fulfilled_by?: string;
  fulfilled_at?: string;
};

export type PaymentsDashboard = {
  total_payments: number;
  approved_payments: number;
  declined_payments: number;
  total_collected: number;
  by_method: Record<string, number>;
  active_auto_drafts: number;
  paused_auto_drafts: number;
  promises_to_pay: { pending: number; kept: number; broken: number };
  pending_payoff_requests: number;
  basis: string;
  disclaimer: string;
};

export type PublicPortalView = {
  revoked: boolean;
  finance_number: string | null;
  customer_name: string | null;
  vehicle: string | null;
  balance: number | null;
  balance_basis: string;
  monthly_payment: number;
  recent_payments: { amount: number; method: string; payment_date: string; status: string }[];
  active_auto_drafts: { id: string; amount: number; method: string; day_of_month: number }[];
  not_yet_tracked: Record<string, string>;
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

function publicGet<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`).then(handle<T>);
}

function publicPost<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

// ---- Staff (authenticated) ----

export function getPaymentsDashboard(): Promise<PaymentsDashboard> {
  return get(`/payments/dashboard`);
}

export function recordPayment(loanId: string, amount: number, method: PaymentMethod, notes = "", paymentDate?: string): Promise<Payment> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/payments`, { amount, method, notes, payment_date: paymentDate ?? null });
}

export function listPaymentsForLoan(loanId: string, includeDeclined = true): Promise<PaymentsForLoan> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/payments?include_declined=${includeDeclined}`);
}

export function getRealPaymentSummary(loanId: string): Promise<RealPaymentSummary> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/payment-summary`);
}

export function createAutoDraft(loanId: string, amount: number, method: PaymentMethod, dayOfMonth: number): Promise<AutoDraft> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/auto-drafts`, { amount, method, day_of_month: dayOfMonth });
}

export function setAutoDraftStatus(draftId: string, status: AutoDraftStatus): Promise<AutoDraft> {
  return post(`/auto-drafts/${encodeURIComponent(draftId)}/status`, { status });
}

export function listAutoDrafts(loanId?: string, status?: AutoDraftStatus): Promise<AutoDraftsList> {
  const params = new URLSearchParams();
  if (loanId) params.set("loan_id", loanId);
  if (status) params.set("status", status);
  return get(`/auto-drafts?${params.toString()}`);
}

export function runDueAutoDrafts(): Promise<{ processed_count: number; results: unknown[] }> {
  return post(`/auto-drafts/run-due`, {});
}

export function createPromiseToPay(loanId: string, promiseDate: string, amount: number, reason = ""): Promise<PromiseToPay> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/promises`, { promise_date: promiseDate, amount, reason });
}

export function listPromisesToPay(loanId?: string, status?: PromiseStatus): Promise<{ promises: PromiseToPay[] }> {
  const params = new URLSearchParams();
  if (loanId) params.set("loan_id", loanId);
  if (status) params.set("status", status);
  return get(`/promises?${params.toString()}`);
}

export function recordExtension(loanId: string, newNextDueDate: string, reason = ""): Promise<unknown> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/extension`, { new_next_due_date: newNextDueDate, reason });
}

export function recordDeferral(loanId: string, months: number, reason = ""): Promise<unknown> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/deferral`, { months, reason });
}

export function listPaymentAdjustments(loanId: string): Promise<{ loan_id: string; adjustments: PaymentAdjustment[] }> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/adjustments`);
}

export function requestPayoff(loanId: string, notes = ""): Promise<{ loan_id: string; request: PayoffRequest }> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/payoff-request`, { notes });
}

export function fulfillPayoffRequest(loanId: string, requestId: string): Promise<{ loan_id: string; request: PayoffRequest }> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/payoff-request/fulfill`, { request_id: requestId });
}

export function listPayoffRequests(loanId?: string, status?: string): Promise<{ requests: PayoffRequest[] }> {
  const params = new URLSearchParams();
  if (loanId) params.set("loan_id", loanId);
  if (status) params.set("status", status);
  return get(`/payoff-requests?${params.toString()}`);
}

export function generatePaymentPortalLink(loanId: string): Promise<{ loan_id: string; token: string; path: string }> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/payment-portal-link`, {});
}

export function getPaymentPortalLinkStatus(loanId: string): Promise<{ loan_id: string; exists: boolean; token?: string; revoked?: boolean; path?: string }> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/payment-portal-link`);
}

export function revokePaymentPortalLink(loanId: string): Promise<{ loan_id: string; revoked: boolean }> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/payment-portal-link/revoke`, {});
}

// ---- Public (unauthenticated) ----

export function publicGetPortalView(token: string): Promise<PublicPortalView> {
  return publicGet(`/public/pay/${encodeURIComponent(token)}`);
}

export function publicSubmitPayment(token: string, amount: number, method: PaymentMethod): Promise<PublicPortalView> {
  return publicPost(`/public/pay/${encodeURIComponent(token)}/submit`, { amount, method });
}

export function publicSubmitPayoffRequest(token: string, notes = ""): Promise<unknown> {
  return publicPost(`/public/pay/${encodeURIComponent(token)}/payoff`, { notes });
}
