// lib/connect.ts — client for NXTDeal Connect (2026-07-24). Talks to the /connect/* routes
// in backend/api/app.py (backed by core/connect.py / connect_api.py): the unified inbox across
// every channel, a per-customer timeline, and the analytics rollup. All three are read-only and
// open to any authenticated role — the caller's role is derived server-side from the
// Authorization header, never passed in a request body. Same reuse-the-shared-helpers shape
// every lib/*.ts client follows: API_BASE + authHeaders() + a local handle<T>.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type Sentiment = "positive" | "neutral" | "at_risk" | "escalation";

export type ConversationIntelligence = {
  sentiment: Sentiment;
  score: number;
  dimensions: Record<string, number>;
  suggested_action: string | null;
  basis: string;
};

export type InboxItem = {
  id: string;
  channel: string | null;
  direction: string | null;
  department: string | null;
  body: string | null;
  linked_entity_id: string | null;
  created_by: string | null;
  created_at: string | null;
  duration_seconds: number | null;
  ai_summary: string | null;
  handled_by_ai: boolean;
  ai_worker_role: string | null;
  intelligence: ConversationIntelligence;
};

export type Inbox = {
  items: InboxItem[];
  count: number;
  total_matching: number;
  channels: string[];
  note: string;
};

export type TimelineEvent = {
  kind: "communication" | "appointment";
  at: string | null;
  channel: string | null;
  direction: string | null;
  handled_by_ai: boolean;
  ai_worker_role?: string | null;
  sentiment?: Sentiment;
  summary: string | null;
  ref_id: string;
};

export type Timeline = {
  entity_id: string;
  event_count: number;
  events: TimelineEvent[];
};

export type ChannelIntelligence = {
  total_analyzed: number;
  sentiment: Record<Sentiment, number>;
  avg_score: number | null;
  by_channel: Record<string, { count: number; sentiment: Record<Sentiment, number>; avg_score: number | null }>;
  basis: string;
  disclaimer: string;
};

export type CommunicationsStats = {
  total_communications: number;
  by_channel: Record<string, number>;
  by_direction: Record<string, number>;
  open_follow_ups: number;
  phone_calls_with_simulated_recording: number;
  recording_basis_note: string;
};

export type ConnectAnalytics = {
  communications: CommunicationsStats;
  ai_handled: number;
  human_handled: number;
  ai_by_role: Record<string, number>;
  workforce: {
    total_workers: number;
    active_workers: number;
    autonomous_workers: number;
    total_interactions: number;
    total_actions_executed: number;
    total_actions_drafted: number;
  };
  intelligence: ChannelIntelligence;
  note: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error(
      (data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend."
    );
  }
  return data as T;
}

export type InboxFilters = {
  channel?: string;
  direction?: string;
  department?: string;
  linked_entity_id?: string;
  ai_only?: boolean;
  limit?: number;
};

export function fetchInbox(filters: InboxFilters = {}): Promise<Inbox> {
  const q = new URLSearchParams();
  if (filters.channel) q.set("channel", filters.channel);
  if (filters.direction) q.set("direction", filters.direction);
  if (filters.department) q.set("department", filters.department);
  if (filters.linked_entity_id) q.set("linked_entity_id", filters.linked_entity_id);
  if (filters.ai_only) q.set("ai_only", "true");
  if (filters.limit != null) q.set("limit", String(filters.limit));
  const qs = q.toString();
  return fetch(`${API_BASE}/connect/inbox${qs ? `?${qs}` : ""}`, {
    headers: { ...authHeaders() },
  }).then(handle<Inbox>);
}

export function fetchTimeline(entityId: string): Promise<Timeline> {
  return fetch(`${API_BASE}/connect/timeline/${encodeURIComponent(entityId)}`, {
    headers: { ...authHeaders() },
  }).then(handle<Timeline>);
}

export function fetchConnectAnalytics(): Promise<ConnectAnalytics> {
  return fetch(`${API_BASE}/connect/analytics`, { headers: { ...authHeaders() } }).then(
    handle<ConnectAnalytics>
  );
}
