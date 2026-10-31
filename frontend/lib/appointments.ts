// The real Appointment/calendar entity (session 96 follow-up), closing the
// single most-repeated "not_yet_tracked" gap across Sales/Service dashboards.
// Backend: core/appointments.py / core/appointments_api.py, department-agnostic
// (Sales and Service share the same entity, distinguished by `department`).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type AppointmentDepartment = "Sales" | "Service";
export type AppointmentStatus = "scheduled" | "confirmed" | "arrived" | "completed" | "no_show" | "cancelled";
export type AppointmentType =
  | "showroom_visit" | "test_drive" | "delivery" | "credit_app" | "paperwork" | "trade_appraisal"
  | "service" | "waiter" | "drop_off" | "recall" | "other";

export type Appointment = {
  id: string;
  department: AppointmentDepartment;
  appointment_type: AppointmentType;
  customer_id: string | null;
  lead_id: string | null;
  vehicle_id: string | null;
  assigned_to: string | null;
  scheduled_start: string;
  scheduled_end: string | null;
  status: AppointmentStatus;
  notes: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  status_history: { status: string; at: string; by: string }[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function listAppointmentTypes(): Promise<Record<AppointmentDepartment, AppointmentType[]>> {
  const res = await fetch(`${API_BASE}/appointments/types`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createAppointment(input: {
  department: AppointmentDepartment;
  appointment_type: AppointmentType;
  scheduled_start: string;
  assigned_to?: string | null;
  customer_id?: string | null;
  lead_id?: string | null;
  vehicle_id?: string | null;
  scheduled_end?: string | null;
  notes?: string;
}): Promise<Appointment> {
  const res = await fetch(`${API_BASE}/appointments`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function listAppointments(opts: {
  department?: AppointmentDepartment;
  assignedTo?: string;
  status?: AppointmentStatus;
  appointmentType?: AppointmentType;
  linkedEntityId?: string;
  date?: string;
  scope?: "today" | "this_week" | "upcoming";
  hours?: number;
} = {}): Promise<Appointment[]> {
  const params = new URLSearchParams();
  if (opts.department) params.set("department", opts.department);
  if (opts.assignedTo) params.set("assigned_to", opts.assignedTo);
  if (opts.status) params.set("status", opts.status);
  if (opts.appointmentType) params.set("appointment_type", opts.appointmentType);
  if (opts.linkedEntityId) params.set("linked_entity_id", opts.linkedEntityId);
  if (opts.date) params.set("date", opts.date);
  if (opts.scope) params.set("scope", opts.scope);
  if (opts.hours) params.set("hours", String(opts.hours));
  const res = await fetch(`${API_BASE}/appointments?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getAppointment(id: string): Promise<Appointment> {
  const res = await fetch(`${API_BASE}/appointments/${encodeURIComponent(id)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateAppointmentStatus(id: string, status: AppointmentStatus): Promise<Appointment> {
  const res = await fetch(`${API_BASE}/appointments/${encodeURIComponent(id)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status }),
  });
  return handle(res);
}

export async function rescheduleAppointment(id: string, newStart: string, newEnd?: string | null): Promise<Appointment> {
  const res = await fetch(`${API_BASE}/appointments/${encodeURIComponent(id)}/reschedule`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_start: newStart, new_end: newEnd || null }),
  });
  return handle(res);
}

// Service-department roster (technicians/advisors), the dedicated Service
// Appointments board's "Assign to..." picker's data source -- same shape as
// lib/salesOverview.ts's SalesEmployeeBrief/getSalesEmployees.
export type ServiceEmployeeBrief = { id: string; name: string; title: string | null };

export async function getServiceEmployees(): Promise<ServiceEmployeeBrief[]> {
  const res = await fetch(`${API_BASE}/service/employees`, { headers: { ...authHeaders() } });
  return handle(res);
}
