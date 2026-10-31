// Communications Hub -- core/communications_hub.py's first-class Communication
// log (real logging across Phone/Text/Email/Chat/Social, honestly-simulated
// phone recording/transcript/sentiment, real embedded follow-up tasks, and a
// real, isolated-OpenAI-backed AI summary with an honest fallback). Composes
// alongside, and does not replace, lib/unifiedCommunications.ts's own
// pre-existing Sales/Service/Finance FieldNote-backed feed -- see
// core/communications_hub.py's own module docstring for the full
// reuse-not-duplicate reasoning. Backed by 7 dedicated /communications-hub/*
// routes (api/routers/communications_hub.py), not the generic /menu/data
// dispatch -- same "bespoke board bypasses /menu/data for its own extra
// views" precedent every other rebuild in this codebase established.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { UnifiedCommunicationsOverview } from "@/lib/unifiedCommunications";

export const COMM_CHANNELS = ["phone", "text", "email", "chat", "social"] as const;
export type CommChannel = (typeof COMM_CHANNELS)[number];

export const COMM_DIRECTIONS = ["inbound", "outbound"] as const;
export type CommDirection = (typeof COMM_DIRECTIONS)[number];

export type SentimentLabel = "positive" | "neutral" | "negative";

export type SimulatedRecording = {
  basis: string;
  disclaimer: string;
  duration_seconds: number;
  recording_url: string;
  transcript: string;
  sentiment_score: number;
  sentiment_label: SentimentLabel;
};

export type CommFollowUp = {
  required: boolean;
  due_at: string | null;
  completed: boolean;
  completed_at: string | null;
  completed_by: string | null;
  note: string | null;
};

export type AiSummary = {
  summary: string;
  key_points: string[];
  suggested_follow_up: string;
  ai_generated: boolean;
  disabled?: boolean;
  fallback_reason?: string;
  error?: string;
};

export type Communication = {
  id: string;
  channel: CommChannel;
  direction: CommDirection;
  department: string | null;
  body: string;
  linked_entity_id: string | null;
  created_by: string | null;
  created_at: string | null;
  duration_seconds: number | null;
  follow_up: CommFollowUp | null;
  ai_summary: AiSummary | null;
  recording: SimulatedRecording | null;
};

export type CommunicationsStats = {
  total_communications: number;
  by_channel: Record<string, number>;
  by_direction: Record<string, number>;
  open_follow_ups: number;
  phone_calls_with_simulated_recording: number;
  recording_basis_note: string;
};

export type CommunicationsHubOverview = {
  hub_stats: CommunicationsStats;
  hub_recent_communications: Communication[];
  hub_open_follow_ups: Communication[];
  legacy_unified_feed: UnifiedCommunicationsOverview;
  note: string;
  error?: string;
};

export type LogCommunicationInput = {
  department: string;
  channel: CommChannel;
  direction: CommDirection;
  body: string;
  linked_entity_id?: string | null;
  duration_seconds?: number | null;
  follow_up_required?: boolean;
  follow_up_due_at?: string | null;
  follow_up_note?: string | null;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function getCommunicationsHubOverview(opts?: {
  department?: string;
  channel?: string;
}): Promise<CommunicationsHubOverview> {
  const params = new URLSearchParams();
  if (opts?.department) params.set("department", opts.department);
  if (opts?.channel) params.set("channel", opts.channel);
  const query = params.toString();
  return fetch(`${API_BASE}/communications-hub/overview${query ? `?${query}` : ""}`, {
    headers: { ...authHeaders() },
  }).then(handle<CommunicationsHubOverview>);
}

export function getCommunicationsStats(department?: string): Promise<CommunicationsStats> {
  const params = new URLSearchParams();
  if (department) params.set("department", department);
  const query = params.toString();
  return fetch(`${API_BASE}/communications-hub/stats${query ? `?${query}` : ""}`, {
    headers: { ...authHeaders() },
  }).then(handle<CommunicationsStats>);
}

export function listCommunications(opts?: {
  department?: string;
  channel?: string;
  linkedEntityId?: string;
  followUpPendingOnly?: boolean;
  limit?: number;
}): Promise<Communication[]> {
  const params = new URLSearchParams();
  if (opts?.department) params.set("department", opts.department);
  if (opts?.channel) params.set("channel", opts.channel);
  if (opts?.linkedEntityId) params.set("linked_entity_id", opts.linkedEntityId);
  if (opts?.followUpPendingOnly) params.set("follow_up_pending_only", "true");
  if (opts?.limit) params.set("limit", String(opts.limit));
  const query = params.toString();
  return fetch(`${API_BASE}/communications-hub/list${query ? `?${query}` : ""}`, {
    headers: { ...authHeaders() },
  }).then(handle<Communication[]>);
}

export function getCommunication(commId: string): Promise<Communication> {
  return fetch(`${API_BASE}/communications-hub/${encodeURIComponent(commId)}`, {
    headers: { ...authHeaders() },
  }).then(handle<Communication>);
}

export function logCommunication(input: LogCommunicationInput): Promise<Communication> {
  return fetch(`${API_BASE}/communications-hub/log`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  }).then(handle<Communication>);
}

export function completeFollowUp(commId: string): Promise<Communication> {
  return fetch(`${API_BASE}/communications-hub/${encodeURIComponent(commId)}/complete-follow-up`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  }).then(handle<Communication>);
}

export function generateAiSummary(commId: string): Promise<AiSummary> {
  return fetch(`${API_BASE}/communications-hub/${encodeURIComponent(commId)}/generate-ai-summary`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  }).then(handle<AiSummary>);
}
