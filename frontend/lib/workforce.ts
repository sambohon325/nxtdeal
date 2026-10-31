// Operations' new "Workforce" Top Menu item (2026-07-19). Backend:
// core/workforce.py / workforce_api.py -- Directory, Shift Scheduling,
// Time-Off Requests (a real manager-tier approval gate), Coverage (a
// computed-live shift-vs-approved-time-off conflict check), and Performance
// (reuses the real lead-workload and employee $ effectiveness engines).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type EmployeeBrief = {
  id: string;
  name: string;
  department: string | null;
  title: string | null;
  tier: "staff" | "manager" | "executive" | null;
};

export type Directory = {
  total: number;
  by_department: Record<string, number>;
  by_tier: Record<string, number>;
  employees: EmployeeBrief[];
};

export type ShiftStatus = "scheduled" | "completed" | "no_show" | "cancelled";

export type Shift = {
  id: string;
  employee: EmployeeBrief;
  shift_date: string;
  start_time: string;
  end_time: string;
  department: string | null;
  status: ShiftStatus;
  notes: string;
};

export type TimeOffStatus = "pending" | "approved" | "denied" | "cancelled";

export type TimeOffRequest = {
  id: string;
  employee: EmployeeBrief;
  start_date: string;
  end_date: string;
  reason: string;
  status: TimeOffStatus;
  requested_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
};

export type Coverage = {
  date: string;
  scheduled_count: number;
  conflict_count: number;
  on_approved_time_off_count: number;
  scheduled: Shift[];
  conflicts: Shift[];
  on_approved_time_off: TimeOffRequest[];
};

export type WorkforcePerformance = {
  lead_workload: { note: string; employees: { employee_id: string; active_workload: number }[] };
  employee_value: Record<string, unknown> & { error?: string };
  credential_coverage: Record<string, unknown> & { error?: string };
  not_yet_tracked: Record<string, string>;
};

export type WorkforceOverview = {
  directory: Directory;
  coverage_today: Coverage;
  pending_time_off_count: number;
  pending_time_off: TimeOffRequest[];
  upcoming_shift_count: number;
  performance: WorkforcePerformance;
  error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

function post<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body ?? {}),
  }).then(handle<T>);
}

export function getWorkforceOverview(): Promise<WorkforceOverview> {
  return get("/workforce/overview");
}

export function getDirectory(department?: string): Promise<Directory> {
  const params = department ? `?department=${encodeURIComponent(department)}` : "";
  return get(`/workforce/directory${params}`);
}

export function getCoverage(onDate?: string): Promise<Coverage> {
  const params = onDate ? `?on_date=${encodeURIComponent(onDate)}` : "";
  return get(`/workforce/coverage${params}`);
}

export function getPerformance(): Promise<WorkforcePerformance> {
  return get("/workforce/performance");
}

export function listShifts(params?: {
  employee_id?: string;
  department?: string;
  date_from?: string;
  date_to?: string;
  status?: string;
}): Promise<{ shifts: Shift[] }> {
  const q = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => v && q.set(k, v));
  const qs = q.toString();
  return get(`/workforce/shifts${qs ? `?${qs}` : ""}`);
}

export function scheduleShift(input: {
  employee_id: string;
  shift_date: string;
  start_time: string;
  end_time: string;
  department?: string;
  notes?: string;
}): Promise<Shift> {
  return post("/workforce/shifts", input);
}

export function completeShift(shiftId: string): Promise<Shift> {
  return post(`/workforce/shifts/${encodeURIComponent(shiftId)}/complete`);
}

export function markNoShow(shiftId: string): Promise<Shift> {
  return post(`/workforce/shifts/${encodeURIComponent(shiftId)}/no-show`);
}

export function cancelShift(shiftId: string): Promise<Shift> {
  return post(`/workforce/shifts/${encodeURIComponent(shiftId)}/cancel`);
}

export function listTimeOff(params?: { employee_id?: string; status?: string }): Promise<{ requests: TimeOffRequest[] }> {
  const q = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => v && q.set(k, v));
  const qs = q.toString();
  return get(`/workforce/time-off${qs ? `?${qs}` : ""}`);
}

export function requestTimeOff(input: {
  employee_id: string;
  start_date: string;
  end_date: string;
  reason?: string;
}): Promise<TimeOffRequest> {
  return post("/workforce/time-off", input);
}

export function approveTimeOff(requestId: string, note?: string): Promise<TimeOffRequest> {
  return post(`/workforce/time-off/${encodeURIComponent(requestId)}/approve`, { note });
}

export function denyTimeOff(requestId: string, note?: string): Promise<TimeOffRequest> {
  return post(`/workforce/time-off/${encodeURIComponent(requestId)}/deny`, { note });
}

export function cancelTimeOff(requestId: string): Promise<TimeOffRequest> {
  return post(`/workforce/time-off/${encodeURIComponent(requestId)}/cancel`);
}
