// core/bank_reconciliation.py's client (2026-07-17, session 112 follow-up) -- Bank
// Reconciliation against a SIMULATED bank feed (no real bank connection exists in this
// sandbox), auto-matched against real+simulated General Ledger cash entries via a real
// amount/date-proximity matching algorithm. Per Sam's direct instruction: "lets keep
// going, simply create the fake data that is needed to build them." Routes live at
// /bank-reconciliation/*.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type BankTransaction = {
  id: string;
  transaction_date: string;
  description: string;
  amount: number;
  transaction_type: string;
  status: "unmatched" | "matched" | "reviewed";
  matched_gl_entry_id: string | null;
  reviewed_by: string | null;
  reviewed_note: string | null;
  basis: string;
  disclaimer: string | null;
};

export type ReconciliationStatus = {
  bank_account: { name: string; bank: string; account_last4: string; starting_balance: number };
  book_balance: number;
  bank_balance: number;
  difference: number;
  matched_count: number;
  unmatched_bank_count: number;
  unmatched_gl_count: number;
  unmatched_bank_transactions: BankTransaction[];
  unmatched_gl_entries: { id: string; entry_date: string; description: string; amount: number }[];
  note: string;
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

export function generateSimulatedBankFeed(startDate?: string, endDate?: string): Promise<{ generated_count: number; generated_transaction_ids: string[] }> {
  return post(`/bank-reconciliation/generate-feed`, { start_date: startDate || "", end_date: endDate || "" });
}

export function getReconciliationStatus(startDate?: string, endDate?: string): Promise<ReconciliationStatus> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString();
  return get(`/bank-reconciliation/status${qs ? `?${qs}` : ""}`);
}

export function listBankTransactions(status?: string, startDate?: string, endDate?: string): Promise<{ transactions: BankTransaction[] }> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString();
  return get(`/bank-reconciliation/transactions${qs ? `?${qs}` : ""}`);
}

export function confirmBankMatch(transactionId: string, glEntryId: string): Promise<BankTransaction> {
  return post(`/bank-reconciliation/transactions/${encodeURIComponent(transactionId)}/confirm-match`, { gl_entry_id: glEntryId });
}

export function markBankTransactionReviewed(transactionId: string, note?: string): Promise<BankTransaction> {
  return post(`/bank-reconciliation/transactions/${encodeURIComponent(transactionId)}/mark-reviewed`, { note: note || "" });
}
