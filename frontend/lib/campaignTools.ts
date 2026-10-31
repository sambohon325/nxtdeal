// Bumper-parity campaign tooling client (2026-07-25): Duplication Station, Multi-Planner,
// and Recurring Schedule. Talks to the dedicated routes in backend/core/campaigns_api.py
// (POST /campaigns/{id}/duplicate, POST /campaigns/bulk) and the /recurring-schedules/*
// routes. Same handle()/authHeaders() convention as lib/marketingCrm.ts.
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type RecurringSchedule = {
  id: string;
  base_campaign_id: string;
  name: string;
  cadence: "daily" | "weekly" | "monthly";
  interval: number;
  start_date: string;
  end_date: string | null;
  next_run_date: string | null;
  active: boolean;
  runs: { campaign_id: string; run_date: string; at: string }[];
};

export type BulkCreateResult = {
  created: string[];
  created_count: number;
  errors: { index: number; error: string }[];
};

export type RunSchedulesResult = {
  launched: { schedule_id: string; campaign_id: string; run_date: string }[];
  launched_count: number;
  errors: { schedule_id: string; error: string }[];
};

export async function duplicateCampaign(campaignId: string, newName?: string) {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/duplicate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_name: newName ?? null }),
  });
  return handle<Record<string, unknown> & { id: string }>(res);
}

export async function bulkCreateCampaigns(
  specs: { campaign_type: string; name: string; channel: string; params?: Record<string, unknown> }[]
): Promise<BulkCreateResult> {
  const res = await fetch(`${API_BASE}/campaigns/bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ specs }),
  });
  return handle<BulkCreateResult>(res);
}

export async function listRecurringSchedules(activeOnly = false): Promise<RecurringSchedule[]> {
  const res = await fetch(`${API_BASE}/recurring-schedules?active_only=${activeOnly}`, {
    headers: { ...authHeaders() },
  });
  return handle<RecurringSchedule[]>(res);
}

export async function createRecurringSchedule(input: {
  base_campaign_id: string;
  cadence: "daily" | "weekly" | "monthly";
  start_date: string;
  end_date?: string | null;
  interval?: number;
  name?: string | null;
}): Promise<RecurringSchedule> {
  const res = await fetch(`${API_BASE}/recurring-schedules`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle<RecurringSchedule>(res);
}

export async function setScheduleActive(scheduleId: string, active: boolean): Promise<RecurringSchedule> {
  const res = await fetch(`${API_BASE}/recurring-schedules/${encodeURIComponent(scheduleId)}/active`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ active }),
  });
  return handle<RecurringSchedule>(res);
}

export async function deleteSchedule(scheduleId: string) {
  const res = await fetch(`${API_BASE}/recurring-schedules/${encodeURIComponent(scheduleId)}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  return handle<{ ok: boolean; schedule_id: string }>(res);
}

export async function runDueSchedules(today?: string): Promise<RunSchedulesResult> {
  const res = await fetch(`${API_BASE}/recurring-schedules/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ today: today ?? null }),
  });
  return handle<RunSchedulesResult>(res);
}

// Track B: real per-recipient delivery through the provider seam.
export type DeliveryResult = {
  campaign_id: string;
  channel: string;
  mode: "live" | "simulated";
  total_recipients: number;
  sent: number;
  simulated: number;
  no_contact: number;
  failed: number;
  unsupported_channel: number;
  skipped: number;
  delivered: number;
};

export type DeliveryStats = {
  campaign_id: string;
  mode: "live" | "simulated";
  total_sends: number;
  by_status: Record<string, number>;
  delivered: number;
  opened: number;
  clicked: number;
  open_rate: number;
  click_rate: number;
  tracking_note: string;
};

export async function sendCampaign(campaignId: string, resend = false): Promise<DeliveryResult> {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/send`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ resend }),
  });
  return handle<DeliveryResult>(res);
}

export async function getDeliveryStats(campaignId: string): Promise<DeliveryStats> {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/delivery`, {
    headers: { ...authHeaders() },
  });
  return handle<DeliveryStats>(res);
}
