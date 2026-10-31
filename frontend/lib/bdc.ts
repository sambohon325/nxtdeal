// BDC / Internet Leads (session 100 follow-up) -- a real untouched-lead queue with
// genuine speed-to-lead measurement. Backend: core/bdc.py / bdc_api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type BdcLeadBrief = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  source: string | null;
  pipeline_state: string | null;
  created_date: string | null;
  minutes_since_created: number | null;
  precise_timestamp: boolean;
  urgency: "ok" | "warning" | "critical" | "unknown";
};

export type BdcDashboard = {
  untouched_queue: { count: number; leads: BdcLeadBrief[] };
  response_time: { sample_size: number; average_minutes: number | null; under_target_pct: number | null };
  sla_thresholds: { urgent_minutes: number; warning_minutes: number };
  internet_sources: string[];
  not_yet_tracked: Record<string, string>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getBdcDashboard(): Promise<BdcDashboard> {
  const res = await fetch(`${API_BASE}/bdc/dashboard`, { headers: { ...authHeaders() } });
  return handle(res);
}

// Session 102 follow-up -- Qualification (contacted but not yet appointment-set) and
// Handoff to Floor (appointment-set/visited, ready to transfer off BDC) candidate
// lists, both real live filters over the same internet-lead pool the untouched queue
// already scans.
export async function getQualificationQueue(): Promise<{ count: number; leads: BdcLeadBrief[] }> {
  const res = await fetch(`${API_BASE}/bdc/qualification`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getHandoffCandidates(): Promise<{ count: number; leads: BdcLeadBrief[] }> {
  const res = await fetch(`${API_BASE}/bdc/handoff-candidates`, { headers: { ...authHeaders() } });
  return handle(res);
}
