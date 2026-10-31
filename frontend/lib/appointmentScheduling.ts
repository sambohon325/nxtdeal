// Appointments' smart-scheduling upgrades -- the last item from Sam's
// original Service spec. Capacity Planning and Technician/Rep Matching are
// real (computed off real Appointment counts vs. an assumed daily
// capacity). Automated Customer Communication is an honestly SIMULATED
// on-demand reminder send. Pre-Visit Check-In is a real public
// unauthenticated link, same pattern as lib/approvalCenter.ts.
// Backend: core/appointment_scheduling.py / _api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type SchedulingDepartment = "Sales" | "Service";
export type ReminderChannel = "sms" | "email" | "call";
export type DropOffOrWait = "drop_off" | "wait";

export type CapacityEmployeeRow = {
  employee_id: string;
  name: string | null;
  title: string | null;
  booked_count: number;
  capacity: number;
  available_slots: number;
  at_capacity: boolean;
};

export type CapacityPlan = {
  department: SchedulingDepartment;
  date: string;
  assumed_daily_capacity_per_employee: number;
  employees: CapacityEmployeeRow[];
  total_booked: number;
  total_capacity: number;
  pct_booked: number;
  note: string;
};

export type AssigneeSuggestion = {
  department: SchedulingDepartment;
  date: string;
  recommended_employee_id: string;
  name: string | null;
  booked_count: number;
  capacity: number;
  available_slots: number;
  at_capacity: boolean;
  note: string;
};

export type ReminderRecord = { channel: ReminderChannel; sent_by: string; sent_at: string; basis: string };

export type CheckinLinkStatus = {
  appointment_id: string;
  exists: boolean;
  token?: string;
  created_by?: string;
  created_at?: string;
  revoked?: boolean;
  revoked_by?: string;
  revoked_at?: string;
  path?: string;
};

export type PublicCheckinView = {
  revoked: boolean;
  department: string;
  appointment_type: string;
  scheduled_start: string;
  status: string;
  person_name: string | null;
  vehicle: string | null;
  checkin: {
    drop_off_or_wait: DropOffOrWait;
    contact_preference: string;
    notes: string;
    submitted_at: string;
    submitted_by: string;
  } | null;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getCapacityPlanning(department: SchedulingDepartment, date?: string): Promise<CapacityPlan> {
  const params = new URLSearchParams({ department });
  if (date) params.set("date", date);
  const res = await fetch(`${API_BASE}/appointment-scheduling/capacity?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function suggestAssignee(department: SchedulingDepartment, date?: string): Promise<AssigneeSuggestion> {
  const params = new URLSearchParams({ department });
  if (date) params.set("date", date);
  const res = await fetch(`${API_BASE}/appointment-scheduling/suggest-assignee?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function sendAppointmentReminder(appointmentId: string, channel: ReminderChannel): Promise<{ appointment_id: string; reminders_sent: ReminderRecord[]; disclaimer: string }> {
  const res = await fetch(`${API_BASE}/appointments/${encodeURIComponent(appointmentId)}/reminder`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ channel }),
  });
  return handle(res);
}

export async function getReminderHistory(appointmentId: string): Promise<{ appointment_id: string; reminders_sent: ReminderRecord[] }> {
  const res = await fetch(`${API_BASE}/appointments/${encodeURIComponent(appointmentId)}/reminder`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function generateCheckinLink(appointmentId: string): Promise<CheckinLinkStatus> {
  const res = await fetch(`${API_BASE}/appointments/${encodeURIComponent(appointmentId)}/checkin-link`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function getCheckinLinkStatus(appointmentId: string): Promise<CheckinLinkStatus> {
  const res = await fetch(`${API_BASE}/appointments/${encodeURIComponent(appointmentId)}/checkin-link`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function revokeCheckinLink(appointmentId: string): Promise<{ appointment_id: string; revoked: boolean }> {
  const res = await fetch(`${API_BASE}/appointments/${encodeURIComponent(appointmentId)}/checkin-link/revoke`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

// ---- Public (unauthenticated) ----

export async function publicGetCheckinView(token: string): Promise<PublicCheckinView> {
  const res = await fetch(`${API_BASE}/public/checkin/${encodeURIComponent(token)}`);
  return handle(res);
}

export async function publicSubmitCheckin(
  token: string,
  dropOffOrWait: DropOffOrWait,
  contactPreference = "",
  notes = ""
): Promise<PublicCheckinView> {
  const res = await fetch(`${API_BASE}/public/checkin/${encodeURIComponent(token)}/submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ drop_off_or_wait: dropOffOrWait, contact_preference: contactPreference, notes }),
  });
  return handle(res);
}
