// lib/fleetKnowledge.ts — client for the agent FLEET's SHARED AI KNOWLEDGE (Pillar 5,
// 2026-07-23). NB: distinct from lib/sharedKnowledge.ts, which is the human-facing
// "Shared Knowledge" pins (core/knowledge_pins.py). This one is the AGENT fleet's single
// shared knowledge pool — talks to the /shared-knowledge* routes in backend/api/app.py
// (backed by core/shared_knowledge.py / shared_knowledge_api.py).
//
// Same reuse-the-shared-helpers shape every lib/*.ts client follows: API_BASE +
// authHeaders() + a local handle<T> that surfaces the backend's {"error": ...} convention
// as a thrown Error. Caller identity (role for the ADMIN gate on publish/delete,
// employee_id on a contributed insight) is derived server-side from the Authorization
// header — never passed in a request body.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type SharedEntryKind = "workflow" | "insight";

// One entry in the shared pool, matching core/shared_knowledge._serialize().
export type SharedEntry = {
  id: string;
  kind: SharedEntryKind;
  source_section: string;
  source_display: string | null;
  title: string | null;
  body: string | null;
  steps: string[];
  occurrences: number | null;
  contributor: string | null;
  contributed_at: string | null;
  updated_at: string | null;
};

// A sequence 2+ teams have INDEPENDENTLY recognized right now (live cross-team analysis).
export type CrossTeamWorkflow = {
  steps: string[];
  length: number;
  teams: string[];
  team_count: number;
  total_occurrences: number;
};

export type FleetKnowledge = {
  entries: SharedEntry[];
  entry_count: number;
  cross_team_workflows: CrossTeamWorkflow[];
  note: string;
  // Present only when read for a specific section — the point of the pillar.
  for_section?: string;
  for_display?: string;
  own?: SharedEntry[];
  from_other_teams?: SharedEntry[];
};

export type KnowledgeSummary = {
  total_entries: number;
  workflow_entries: number;
  insight_entries: number;
  contributing_sections: string[];
  entries_per_section: Record<string, number>;
  cross_team_pattern_count: number;
};

export type FleetKnowledgeResponse = {
  knowledge: FleetKnowledge;
  summary: KnowledgeSummary;
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

export function fetchFleetKnowledge(section?: string): Promise<FleetKnowledgeResponse> {
  const qs = section ? `?section=${encodeURIComponent(section)}` : "";
  return fetch(`${API_BASE}/shared-knowledge${qs}`, {
    headers: { ...authHeaders() },
  }).then(handle<FleetKnowledgeResponse>);
}

export function contributeInsight(
  section: string,
  title: string,
  body: string
): Promise<{ entry: SharedEntry; created: boolean }> {
  return fetch(`${API_BASE}/shared-knowledge/contribute`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ section, title, body }),
  }).then(handle<{ entry: SharedEntry; created: boolean }>);
}

// ADMIN-only server-side: promote every team's recognized workflows into the shared pool.
export function publishWorkflows(): Promise<{
  published: number;
  updated: number;
  sections: string[];
  total_entries: number;
}> {
  return fetch(`${API_BASE}/shared-knowledge/publish`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({}),
  }).then(handle<{ published: number; updated: number; sections: string[]; total_entries: number }>);
}

// ADMIN-only server-side: curate the pool.
export function deleteEntry(entryId: string): Promise<{ deleted: string }> {
  return fetch(`${API_BASE}/shared-knowledge/${encodeURIComponent(entryId)}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  }).then(handle<{ deleted: string }>);
}
