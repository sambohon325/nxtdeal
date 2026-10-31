// core/lending_compliance.py's client (2026-07-17, session 112 follow-up) -- OFAC/SDN
// screening + IRS Form 8300 cash reporting, the seventh slice of Sam's "Retail
// Automotive Lending Platform" expansion and the last explicitly-named item on his
// original 13-item Finance menu spec. Routes live at /lending-compliance/*, distinct
// from the general /compliance/* rule-catalog/alert system (which this board also
// reads, via the generic /menu/data?department=Finance&item_key=compliance call, for
// rule_catalog/compliance_exceptions/deal_jacket_audits -- no need to duplicate that
// client here).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type OfacStatus = {
  deal_id: string;
  status: "not_screened" | "cleared" | "potential_match";
  cleared: boolean;
  screened_by: string | null;
  screened_at: string | null;
  notes: string | null;
};

export type Form8300Status = {
  deal_id: string;
  total_cash_received: number;
  threshold: number;
  obligation: boolean;
  filed: boolean;
  filing: { filed: boolean; filed_by: string; filed_at: string; filing_date: string; amount: number } | null;
  status: "none" | "pending" | "overdue" | "filed";
  note?: string;
  trigger_date?: string;
  days_elapsed?: number;
  days_remaining?: number;
  days_overdue?: number;
};

export type LendingComplianceDashboard = {
  ofac: {
    unscreened_or_potential_match_count: number;
    deals: OfacStatus[];
  };
  form_8300: {
    overdue_count: number;
    pending_count: number;
    filed_count: number;
    overdue: Form8300Status[];
    pending: Form8300Status[];
  };
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

function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

export function getLendingComplianceDashboard(): Promise<LendingComplianceDashboard> {
  return get(`/lending-compliance/dashboard`);
}

export function getOfacStatus(dealId: string): Promise<OfacStatus> {
  return get(`/lending-compliance/${encodeURIComponent(dealId)}/ofac`);
}

export function recordOfacScreening(dealId: string, cleared: boolean, notes = ""): Promise<OfacStatus> {
  return post(`/lending-compliance/${encodeURIComponent(dealId)}/ofac`, { cleared, notes });
}

export function recordCashPayment(dealId: string, amount: number, paymentDate = ""): Promise<Form8300Status> {
  return post(`/lending-compliance/${encodeURIComponent(dealId)}/cash-payment`, { amount, payment_date: paymentDate });
}

export function getForm8300Status(dealId: string): Promise<Form8300Status> {
  return get(`/lending-compliance/${encodeURIComponent(dealId)}/form-8300`);
}

export function fileForm8300(dealId: string, filingDate = ""): Promise<Form8300Status> {
  return post(`/lending-compliance/${encodeURIComponent(dealId)}/form-8300/file`, { filing_date: filingDate });
}

export function getForm8300Obligations(status?: string): Promise<{ obligations: Form8300Status[] }> {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return get(`/lending-compliance/form-8300/obligations${qs}`);
}

// The general compliance() view (rule catalog / open exceptions / deal jacket audits)
// stays behind the existing generic /menu/data endpoint -- reused here rather than
// duplicated so this board shows the exact same numbers the rest of NXTDeal does.
export type FinanceComplianceOverview = {
  compliance_exceptions?: { alerts?: unknown[]; error?: string } | { error: string };
  deal_jacket_audits?: { count: number; deal_ids: string[] };
  rule_catalog?: { rules: { id: string; law: string; citation: string; category: string; severity: string; applies_to: string[] }[]; notice: string };
  ofac_verification?: unknown;
  irs_form_8300?: unknown;
};

export function getFinanceComplianceOverview(): Promise<FinanceComplianceOverview> {
  const params = new URLSearchParams({ department: "Finance", item_key: "compliance" });
  return get(`/menu/data?${params.toString()}`);
}
