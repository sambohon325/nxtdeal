// Events dash -- Trigger Alert Timeline + Dealership Events (session 84). Sam: "build
// out the event dash. we want to style it after nxtdeal bumper,
// automotivemastermind.com, and auto alert. this part we absolutely have to nail, and
// has to tightly integrate into the CRM."
//
// Talks to backend/core/trigger_alerts_api.py (via /alerts/* routes) and
// backend/core/dealership_events_api.py (via /events/*, /rsvps/* routes).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// --- Trigger Alerts (AutoAlert / automotiveMastermind-style Timeline) ---

export type AlertType = "lease_maturity" | "service_win_back" | "equity_mining" | "recall_open" | "conquest_match";
export type Urgency = "high" | "medium" | "low";

export type TriggerAlert = {
  id: string;
  alert_type: AlertType;
  alert_type_label: string;
  target_entity_type: "Customer" | "Lead";
  target_entity_id: string;
  target_name: string;
  vehicle_id: string | null;
  headline: string;
  urgency: Urgency;
  basis: "ledger" | "heuristic";
  notes: string | null;
  status: "new" | "promoted" | "dismissed";
  created_at: string;
  promoted_to_lead_id: string | null;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function listAlertTypes(): Promise<Record<string, string>> {
  const res = await fetch(`${API_BASE}/alerts/types`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getAlertFeed(opts: {
  alertType?: AlertType;
  status?: string;
  targetEntityType?: "Customer" | "Lead";
} = {}): Promise<TriggerAlert[]> {
  const params = new URLSearchParams();
  if (opts.alertType) params.set("alert_type", opts.alertType);
  if (opts.status) params.set("status", opts.status);
  if (opts.targetEntityType) params.set("target_entity_type", opts.targetEntityType);
  const res = await fetch(`${API_BASE}/alerts/feed?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function dismissAlert(alertId: string, notes?: string): Promise<TriggerAlert> {
  const res = await fetch(`${API_BASE}/alerts/${encodeURIComponent(alertId)}/dismiss`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ notes: notes || null }),
  });
  return handle(res);
}

export async function promoteAlert(alertId: string, assignToEmployeeId?: string): Promise<TriggerAlert> {
  const res = await fetch(`${API_BASE}/alerts/${encodeURIComponent(alertId)}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ assign_to_employee_id: assignToEmployeeId || null }),
  });
  return handle(res);
}

// --- Dealership Events (NXTDeal Bumper-style) ---

export type EventType = { key: string; name: string };

export type DealershipEvent = {
  id: string;
  name: string;
  description: string;
  event_type: string;
  start_time: string | null;
  end_time: string | null;
  location: string;
  capacity: number | null;
  linked_list_id: string | null;
  status: "draft" | "scheduled" | "live" | "completed" | "cancelled";
  created_by: string;
  created_at: string;
  published_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
};

export type EventRsvp = {
  id: string;
  event_id: string;
  customer_id: string | null;
  lead_id: string | null;
  name: string;
  phone: string;
  email: string;
  status: "invited" | "confirmed" | "attended" | "no_show" | "cancelled";
  source: "invited" | "walk_in" | "self_registered";
  created_at: string;
  promoted_to_lead_id: string | null;
};

export type EventDetail = {
  event: DealershipEvent;
  rsvp_summary: Record<string, number>;
  rsvps: EventRsvp[];
};

export async function listEventTypes(): Promise<EventType[]> {
  const res = await fetch(`${API_BASE}/events/types`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listRsvpStatuses(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/events/rsvp-statuses`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createEvent(input: {
  name: string;
  event_type: string;
  start_time?: string | null;
  end_time?: string | null;
  location?: string;
  capacity?: number | null;
  description?: string;
  linked_list_id?: string | null;
}): Promise<DealershipEvent> {
  const res = await fetch(`${API_BASE}/events`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function listEvents(opts: {
  status?: string;
  eventType?: string;
  mineOnly?: boolean;
} = {}): Promise<DealershipEvent[]> {
  const params = new URLSearchParams();
  if (opts.status) params.set("status", opts.status);
  if (opts.eventType) params.set("event_type", opts.eventType);
  if (opts.mineOnly) params.set("mine_only", "true");
  const res = await fetch(`${API_BASE}/events?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getEventDetail(eventId: string): Promise<EventDetail> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateEvent(eventId: string, patch: Partial<DealershipEvent>): Promise<DealershipEvent> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function publishEvent(eventId: string): Promise<{ event: DealershipEvent; invited_count: number }> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/publish`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function startEvent(eventId: string): Promise<DealershipEvent> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/start`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function completeEvent(eventId: string): Promise<DealershipEvent> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/complete`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function cancelEvent(eventId: string): Promise<DealershipEvent> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/cancel`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function createRsvp(eventId: string, input: {
  name: string;
  phone?: string;
  email?: string;
  customer_id?: string | null;
  lead_id?: string | null;
  source?: "walk_in" | "self_registered";
}): Promise<EventRsvp> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/rsvps`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function listEventRsvps(eventId: string, status?: string): Promise<EventRsvp[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/rsvps?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateRsvpStatus(rsvpId: string, status: EventRsvp["status"]): Promise<EventRsvp> {
  const res = await fetch(`${API_BASE}/rsvps/${encodeURIComponent(rsvpId)}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status }),
  });
  return handle(res);
}

export async function promoteRsvpToLead(rsvpId: string, assignToEmployeeId?: string): Promise<{ rsvp: EventRsvp; lead: Record<string, unknown> }> {
  const res = await fetch(`${API_BASE}/rsvps/${encodeURIComponent(rsvpId)}/promote`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ assign_to_employee_id: assignToEmployeeId || null }),
  });
  return handle(res);
}

// --- Event Project Management (War Room / task checklist) ---

export type EventTaskStatus = "open" | "in_progress" | "done" | "blocked";

export type EventTask = {
  id: string;
  event_id: string;
  title: string;
  assignee_employee_id: string | null;
  due_date: string | null;
  notes: string;
  status: EventTaskStatus;
  created_by: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
};

export type ProjectManagementSummary = {
  event_id: string;
  total_tasks: number;
  by_status: Record<EventTaskStatus, number>;
  completion_pct: number | null;
  overdue_tasks: { id: string; title: string; due_date: string | null; assignee_employee_id: string | null }[];
  overdue_count: number;
};

export type EventWarRoom = {
  outcomes?:{responses:number;completed_outcomes:number;values_by_currency:Record<string,number>;missing_values:number;follow_up_due:number;basis:string};
  event: DealershipEvent;
  is_live: boolean;
  rsvp_summary: Record<string, number>;
  attendance: {
    total_roster: number;
    checked_in_count: number;
    no_show_count: number;
    check_in_rate_pct: number | null;
    basis: string;
  };
  project_management: ProjectManagementSummary;
  campaigns_generated: number;
  recent_campaigns: { id: string; name: string; status: string; channel: string }[];
};

export async function listEventTaskStatuses(): Promise<EventTaskStatus[]> {
  const res = await fetch(`${API_BASE}/event-tasks/statuses`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createEventTask(eventId: string, input: {
  title: string;
  assignee_employee_id?: string | null;
  due_date?: string | null;
  notes?: string;
}): Promise<EventTask> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function listEventTasks(eventId: string, status?: EventTaskStatus): Promise<EventTask[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/tasks?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateEventTaskStatus(taskId: string, status: EventTaskStatus): Promise<EventTask> {
  const res = await fetch(`${API_BASE}/event-tasks/${encodeURIComponent(taskId)}/status`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status }),
  });
  return handle(res);
}

export async function deleteEventTask(taskId: string): Promise<{ deleted: string }> {
  const res = await fetch(`${API_BASE}/event-tasks/${encodeURIComponent(taskId)}/delete`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function getProjectManagementSummary(eventId: string): Promise<ProjectManagementSummary> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/project-management`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getEventWarRoom(eventId: string): Promise<EventWarRoom> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/war-room`, { headers: { ...authHeaders() } });
  return handle(res);
}

// --- Event Campaign Generator ---

export type EventCampaignDraft = {
  event_id: string;
  channel: string;
  goal: string;
  copy: Record<string, string>;
};

export type EventCampaign = {
  id: string;
  name: string;
  channel: string;
  status: string;
  audience_count: number;
  linked_template_id: string | null;
};

export async function generateEventCampaignDraft(eventId: string, channel: string = "email", tone: string = "friendly and professional"): Promise<EventCampaignDraft> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/campaign-generator/draft`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ channel, tone }),
  });
  return handle(res);
}

export async function createEventCampaign(eventId: string, channel: string = "email", tone: string = "friendly and professional"): Promise<{ campaign: EventCampaign; template: Record<string, unknown> }> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/campaign-generator/create`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ channel, tone }),
  });
  return handle(res);
}

export async function listCampaignsForEvent(eventId: string): Promise<EventCampaign[]> {
  const res = await fetch(`${API_BASE}/events/${encodeURIComponent(eventId)}/campaigns`, { headers: { ...authHeaders() } });
  return handle(res);
}
