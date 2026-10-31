// lib/botFleet.ts — client for the agentic-bot FLEET (Pillar 4 slice 2, 2026-07-23).
// Talks to the /bot/fleet* routes in backend/api/app.py (backed by core/bot_fleet.py /
// bot_fleet_api.py). Same reuse-the-shared-helpers shape every lib/*.ts client follows:
// API_BASE + authHeaders() + a local handle<T> that surfaces the backend's {"error": ...}
// convention as a thrown Error. Caller identity (role for the ADMIN gate on
// activate/deactivate, employee_id for a recorded step) is derived server-side from the
// Authorization header — never passed in a request body. Fleet management is ADMIN-only
// server-side; the board additionally hides the controls from non-admins for clarity.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type AgentMode = "draft" | "auto";
export type AgentStatus = "active" | "inactive";

// One team agent, matching core/bot_fleet._agent_view().
export type TeamAgent = {
  id: string;
  section: string;
  display_name: string;
  status: AgentStatus;
  mode: AgentMode;
  activated_by: string | null;
  activated_at: string | null;
  deactivated_by: string | null;
  deactivated_at: string | null;
  created_at: string | null;
  workflow_step_count: number;
  recognized_workflow_count: number;
};

export type FleetSummary = {
  total_agents: number;
  active_agents: number;
  auto_agents: number;
  total_workflow_steps: number;
  total_recognized_workflows: number;
};

export type Fleet = {
  fleet: TeamAgent[];
  summary: FleetSummary;
};

// A recurring action sequence the team agent has recognized (real frequent-sequence
// mining over recorded steps — see core/bot_fleet._recognized_workflows()).
export type RecognizedWorkflow = {
  steps: string[];
  length: number;
  occurrences: number;
};

export type WorkflowStep = {
  actor: string | null;
  action_key: string | null;
  step_label: string | null;
  workflow_key: string | null;
  recorded_at: string | null;
};

// One step of a workflow RUN (slice 4e): what the agent actually did with it.
export type RunStep = {
  action_key: string;
  status: "executed" | "drafted";
  result: unknown;
};

// A recorded run of a recognized workflow (TeamAgentRun).
export type WorkflowRun = {
  id?: string;
  section?: string;
  mode: "auto" | "draft";
  workflow: string[];
  steps: RunStep[];
  executed_count: number;
  drafted_count: number;
  run_by?: string;
  created_at?: string;
  run_id?: string;
  note?: string;
};

export type TeamWorkflows = {
  available: boolean;
  section?: string;
  display_name?: string;
  step_count?: number;
  distinct_actors?: string[];
  recognized_workflows?: RecognizedWorkflow[];
  recent_steps?: WorkflowStep[];
  // Slice 4e: whether this agent is armed to auto-execute a whitelisted safe step right
  // now (active + auto + kill switch on + bot.fleet.auto_execute granted), and its recent runs.
  auto_execute_ready?: boolean;
  recent_runs?: WorkflowRun[];
  note?: string;
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

export function fetchFleet(): Promise<Fleet> {
  return fetch(`${API_BASE}/bot/fleet`, {
    headers: { ...authHeaders() },
  }).then(handle<Fleet>);
}

export function fetchTeamWorkflows(section: string): Promise<TeamWorkflows> {
  return fetch(`${API_BASE}/bot/fleet/${encodeURIComponent(section)}/workflows`, {
    headers: { ...authHeaders() },
  }).then(handle<TeamWorkflows>);
}

export function activateAgent(section: string, mode: AgentMode): Promise<{ agent: TeamAgent }> {
  return fetch(`${API_BASE}/bot/fleet/${encodeURIComponent(section)}/activate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ mode }),
  }).then(handle<{ agent: TeamAgent }>);
}

export function deactivateAgent(section: string): Promise<{ agent: TeamAgent }> {
  return fetch(`${API_BASE}/bot/fleet/${encodeURIComponent(section)}/deactivate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({}),
  }).then(handle<{ agent: TeamAgent }>);
}

// Slice 4e: run the agent's top recognized workflow. Steps execute only if the agent is
// armed (active + auto + kill switch + bot.fleet.auto_execute) AND on the fleet safe-action
// whitelist (empty by default) — otherwise each step is drafted for a human. ADMIN-only.
export function runWorkflow(section: string): Promise<WorkflowRun> {
  return fetch(`${API_BASE}/bot/fleet/${encodeURIComponent(section)}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({}),
  }).then(handle<WorkflowRun>);
}
