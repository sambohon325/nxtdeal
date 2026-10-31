// lib/customerComms.ts — client for the customer side of Communications (2026-07-24). Talks to
// the /comms/* routes (core/customer_comms.py): search the CRM, place a call, send a text, pull a
// conversation timeline, and read the AI analysis. Same shared-helper shape as every lib/*.ts.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ProviderStatus = {
  capability: string;
  live: boolean;
  recommended_provider: string;
  marketplace_category: string;
  note: string;
};

export type ContactBrief = {
  id: string;
  type: string;
  name: string;
  phone: string | null;
  email: string | null;
  pipeline_state?: string | null;
};

export type CallView = {
  id: string;
  status: string;
  direction: string;
  to_number?: string | null;
  from_number?: string | null;
  linked_entity_id?: string | null;
  communication_id?: string | null;
  duration_seconds?: number | null;
};

export type Intelligence = {
  sentiment: "positive" | "neutral" | "at_risk" | "escalation";
  score: number;
  dimensions: Record<string, number>;
  suggested_action: string | null;
  basis: string;
} | null;

export type CommunicationView = {
  id: string;
  channel: string;
  direction: string;
  body: string | null;
  ai_summary?: string | null;
  recording?: { transcript?: string | null; sentiment?: string | null } | null;
  created_at?: string | null;
} | null;

export type PlaceCallResult = { call: CallView; customer: ContactBrief; provider: ProviderStatus } | { error: string };
export type EndCallResult = { call: CallView; communication: CommunicationView; intelligence: Intelligence } | { error: string };
export type SendTextResult = { communication: CommunicationView; dispatch: Record<string, unknown>; intelligence: Intelligence; provider: ProviderStatus } | { error: string };

export type TimelineEvent = {
  kind: string;
  at: string | null;
  channel: string | null;
  direction: string | null;
  handled_by_ai: boolean;
  sentiment?: string;
  summary: string | null;
  ref_id: string;
};

export type Conversation = { customer: ContactBrief; timeline: { entity_id: string; event_count: number; events: TimelineEvent[] } };

export type RecentActivity = { count: number; items: Array<{ kind: string; id: string; at: string | null; direction: string | null; status?: string; number?: string | null; summary?: string | null; linked_entity_id: string | null; communication_id: string | null }> };

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

// Note: install/dispatch results legitimately carry an "error"-free body; the guard above only
// throws when `error` is truthy, so simulated dispatch payloads pass through fine.

export function fetchProviderStatus(): Promise<ProviderStatus> {
  return fetch(`${API_BASE}/comms/provider`, { headers: { ...authHeaders() } }).then(handle<ProviderStatus>);
}

type SearchResult = { query: string; count: number; results: ContactBrief[] };
export function searchCustomers(q: string, limit = 25): Promise<SearchResult> {
  return fetch(`${API_BASE}/comms/customers/search?q=${encodeURIComponent(q)}&limit=${limit}`, {
    headers: { ...authHeaders() },
  }).then(handle<SearchResult>);
}

export function saveContact(number: string, name?: string, email?: string): Promise<ContactBrief> {
  return fetch(`${API_BASE}/comms/contacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ number, name, email }),
  }).then(handle<ContactBrief>);
}

export function placeCall(opts: { customer_id?: string; number?: string; department?: string }): Promise<PlaceCallResult> {
  return fetch(`${API_BASE}/comms/call`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(opts),
  }).then(handle<PlaceCallResult>);
}

export function endCall(callId: string, notes?: string, durationSeconds?: number): Promise<EndCallResult> {
  return fetch(`${API_BASE}/comms/call/${encodeURIComponent(callId)}/end`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ notes, duration_seconds: durationSeconds }),
  }).then(handle<EndCallResult>);
}

export function sendText(opts: { body: string; customer_id?: string; number?: string; department?: string }): Promise<SendTextResult> {
  return fetch(`${API_BASE}/comms/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(opts),
  }).then(handle<SendTextResult>);
}

export function fetchConversation(customerId: string): Promise<Conversation> {
  return fetch(`${API_BASE}/comms/conversation/${encodeURIComponent(customerId)}`, {
    headers: { ...authHeaders() },
  }).then(handle<Conversation>);
}

export function fetchRecent(limit = 25): Promise<RecentActivity> {
  return fetch(`${API_BASE}/comms/recent?limit=${limit}`, { headers: { ...authHeaders() } }).then(handle<RecentActivity>);
}
