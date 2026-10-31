// core/loan_accounting.py's client (2026-07-17, session 112 follow-up) -- Loan
// Accounting, the eighth slice of Sam's "Retail Automotive Lending Platform"
// expansion. A real cash-basis sub-ledger built entirely from core/payments.py's own
// real Payment records: a real Interest Income/Principal Reduction/Cash Collected
// summary, a real daily journal-style ledger with a post/unposted workflow, and a
// real month-end close. Routes live at /loan-accounting/*.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type LoanAccountingSummary = {
  start_date: string | null;
  end_date: string | null;
  payment_count: number;
  interest_income_recognized: number;
  principal_reduction: number;
  cash_collected: number;
  posted_count: number;
  unposted_count: number;
  note: string;
};

export type LedgerLine = { account: string; debit: number; credit: number };

export type LedgerEntry = {
  payment_id: string;
  loan_id: string;
  payment_date: string;
  method: string;
  posting_status: "posted" | "unposted";
  lines: LedgerLine[];
};

export type DailyLedger = {
  date: string;
  period_closed: boolean;
  entries: LedgerEntry[];
  totals: { cash: number; interest_income: number; principal_reduction: number };
};

export type AccountingPeriod = {
  period_key: string;
  status: "open" | "closed";
  closed_by: string | null;
  closed_at: string | null;
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

function post<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function getLoanAccountingSummary(startDate?: string, endDate?: string): Promise<LoanAccountingSummary> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString();
  return get(`/loan-accounting/summary${qs ? `?${qs}` : ""}`);
}

export function getUnpostedPayments(): Promise<{ unposted: LedgerEntry[] }> {
  return get(`/loan-accounting/unposted`);
}

export function getAccountingPeriods(): Promise<{ periods: AccountingPeriod[] }> {
  return get(`/loan-accounting/periods`);
}

export function getDailyLedger(paymentDate: string): Promise<DailyLedger> {
  return get(`/loan-accounting/daily-ledger/${encodeURIComponent(paymentDate)}`);
}

export function postAllDue(paymentDate: string): Promise<{ date: string; posted_count: number; posted_payment_ids: string[] }> {
  return post(`/loan-accounting/daily-ledger/${encodeURIComponent(paymentDate)}/post-all-due`);
}

export function postPaymentToLedger(paymentId: string): Promise<LedgerEntry> {
  return post(`/loan-accounting/payments/${encodeURIComponent(paymentId)}/post`);
}

export function closeAccountingPeriod(year: number, month: number): Promise<AccountingPeriod> {
  return post(`/loan-accounting/periods/close`, { year, month });
}

export function reopenAccountingPeriod(year: number, month: number): Promise<AccountingPeriod> {
  return post(`/loan-accounting/periods/reopen`, { year, month });
}
