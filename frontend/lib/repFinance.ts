// Client for MySales self-accounting (/finance/*, core/rep_finance.py).
// Same shape every lib/*.ts client follows: API_BASE + authHeaders() + a local handle<T>.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type BankAccount = {
  id: string;
  institution: string | null;
  name: string | null;
  mask: string | null;
  type: string | null;
  balance: number;
  source: string | null;
};

export type Budget = {
  id: string;
  category: string;
  limit: number;
  spent: number;
  remaining: number;
  pct: number;
  over: boolean;
};

export type Commission = {
  id: string;
  amount: number;
  status: "projected" | "pending" | "paid";
  source: string | null;
  deal_id: string | null;
  date: string;
};

export type AdvisorInsight = { type: "warning" | "tip" | "win"; title: string; detail: string };

export type FinanceOverview = {
  linked: boolean;
  provider_live: boolean;
  cash_total: number;
  accounts: BankAccount[];
  budgets: Budget[];
  commissions: { totals: Record<string, number>; recent: Commission[] };
  advisor: AdvisorInsight[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function fetchFinanceOverview(): Promise<FinanceOverview> {
  return fetch(`${API_BASE}/finance/overview`, { headers: authHeaders() }).then(handle<FinanceOverview>);
}

export function linkBank(institution?: string): Promise<{ accounts: BankAccount[]; simulated: boolean; already_linked: boolean }> {
  return fetch(`${API_BASE}/finance/link-bank`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ institution: institution ?? null }),
  }).then(handle<{ accounts: BankAccount[]; simulated: boolean; already_linked: boolean }>);
}

export function setBudget(category: string, limit: number): Promise<{ category: string; limit: number }> {
  return fetch(`${API_BASE}/finance/budgets`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ category, limit }),
  }).then(handle<{ category: string; limit: number }>);
}

export function recordCommission(input: {
  amount: number;
  status?: "projected" | "pending" | "paid";
  source?: string;
}): Promise<Commission> {
  return fetch(`${API_BASE}/finance/commissions`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  }).then(handle<Commission>);
}
