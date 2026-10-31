// core/general_ledger.py's client (2026-07-17, session 112 follow-up) -- General
// Ledger, built with SIMULATED data (floorplan interest, payroll, overhead, other
// income) blended with REAL entries (synced from posted Loan Accounting payments +
// funded Deals' real Vehicle Price/Cost) per Sam's direct instruction: "lets keep
// going, simply create the fake data that is needed to build them." Routes live at
// /general-ledger/*.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type GlAccount = { number: string; name: string; type: "asset" | "liability" | "equity" | "revenue" | "expense" };

export type GlLine = { account: string; debit: number; credit: number };

export type GlEntry = {
  id: string;
  entry_date: string;
  description: string;
  lines: GlLine[];
  source: string;
  source_reference: string;
  created_by: string;
  created_at: string;
  basis: string;
  disclaimer: string | null;
};

export type TrialBalanceRow = { account_number: string; account: string; type: string; debit: number; credit: number };

export type TrialBalance = { rows: TrialBalanceRow[]; total_debit: number; total_credit: number; balanced: boolean };

export type IncomeStatement = {
  start_date: string | null;
  end_date: string | null;
  revenue: { lines: { account: string; amount: number }[]; total: number };
  expenses: { lines: { account: string; amount: number }[]; total: number };
  net_income: number;
  note: string;
};

export type BalanceSheet = {
  as_of_date: string;
  assets: { lines: { account: string; balance: number }[]; total: number };
  liabilities: { lines: { account: string; balance: number }[]; total: number };
  equity: { owners_equity: number; retained_earnings: number; total: number };
  balances: boolean;
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

function del<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { method: "DELETE", headers: { ...authHeaders() } }).then(handle<T>);
}

export function getChartOfAccounts(): Promise<{ accounts: GlAccount[] }> {
  return get(`/general-ledger/chart-of-accounts`);
}

export function syncRealGlEntries(): Promise<{ synced_count: number; synced_entry_ids: string[]; skipped_closed_period: string[] }> {
  return post(`/general-ledger/sync`);
}

export function generateSimulatedGlEntries(year: number, month: number, floorplanExposure: number): Promise<{ period_key: string; generated_count: number; generated_entry_ids: string[] }> {
  return post(`/general-ledger/generate-simulated`, { year, month, floorplan_exposure: floorplanExposure });
}

export function deleteGlEntry(entryId: string): Promise<{ deleted: string }> {
  return del(`/general-ledger/entries/${encodeURIComponent(entryId)}`);
}

export function getGeneralLedgerEntries(accountNumber?: string, startDate?: string, endDate?: string, offset = 0, limit = 200): Promise<{ count: number; entries: GlEntry[] }> {
  const params = new URLSearchParams();
  params.set("offset", String(offset));
  params.set("limit", String(limit));
  if (accountNumber) params.set("account_number", accountNumber);
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString();
  return get(`/general-ledger/entries${qs ? `?${qs}` : ""}`);
}

export function getTrialBalance(startDate?: string, endDate?: string): Promise<TrialBalance> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString();
  return get(`/general-ledger/trial-balance${qs ? `?${qs}` : ""}`);
}

export function getIncomeStatement(startDate?: string, endDate?: string): Promise<IncomeStatement> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const qs = params.toString();
  return get(`/general-ledger/income-statement${qs ? `?${qs}` : ""}`);
}

export function getBalanceSheet(asOfDate?: string): Promise<BalanceSheet> {
  const qs = asOfDate ? `?as_of_date=${encodeURIComponent(asOfDate)}` : "";
  return get(`/general-ledger/balance-sheet${qs}`);
}
