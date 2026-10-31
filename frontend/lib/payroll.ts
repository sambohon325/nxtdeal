// Payroll client (Phase 5, 2026-07-25): time clock, pay plans, payroll runs, pay statements.
// Talks to backend/api/routers/payroll.py (/payroll/*).
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type TimeEntry = { id: string; employee_id: string; clock_in_at: string; clock_out_at: string | null; hours: number | null };

export type PayStatement = {
  id: string;
  run_id: string;
  employee_id: string;
  employee_name: string;
  period_start: string;
  period_end: string;
  plan_type: string;
  state: string;
  hours: number;
  earnings: { hourly: number; salary: number; commission: number };
  commission_detail: { deal_id: string; amount: number; front_gross: number | null }[];
  gross_pay: number;
  taxes: { federal: number; fica: number; state: number; state_rate: number; total: number };
  net_pay: number;
  tax_model: string;
};

export type PayrollRun = {
  id: string;
  period_start: string;
  period_end: string;
  statement_count: number;
  total_gross: number;
  total_net: number;
};

export type PayrollRunResult = PayrollRun & { run_id: string; statements: { id: string; employee_id: string; gross_pay: number; net_pay: number }[] };

export async function getClockStatus(): Promise<{ open_entry: TimeEntry | null }> {
  const res = await fetch(`${API_BASE}/payroll/clock`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function clockIn(): Promise<TimeEntry> {
  const res = await fetch(`${API_BASE}/payroll/clock-in`, { method: "POST", headers: { ...authHeaders() } });
  return handle(res);
}

export async function clockOut(): Promise<TimeEntry> {
  const res = await fetch(`${API_BASE}/payroll/clock-out`, { method: "POST", headers: { ...authHeaders() } });
  return handle(res);
}

export async function setPayPlan(employeeId: string, input: {
  plan_type: string;
  hourly_rate?: number;
  annual_salary?: number;
  per_deal_commission?: number;
  pct_front_gross?: number;
  state?: string;
}): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/payroll/plans/${encodeURIComponent(employeeId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function runPayroll(periodStart: string, periodEnd: string): Promise<PayrollRunResult> {
  const res = await fetch(`${API_BASE}/payroll/runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ period_start: periodStart, period_end: periodEnd }),
  });
  return handle(res);
}

export async function listPayrollRuns(): Promise<{ runs: PayrollRun[] }> {
  const res = await fetch(`${API_BASE}/payroll/runs`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listPayStatements(opts?: { employee_id?: string; run_id?: string }): Promise<{ statements: PayStatement[] }> {
  const qs = new URLSearchParams();
  if (opts?.employee_id) qs.set("employee_id", opts.employee_id);
  if (opts?.run_id) qs.set("run_id", opts.run_id);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const res = await fetch(`${API_BASE}/payroll/statements${suffix}`, { headers: { ...authHeaders() } });
  return handle(res);
}
