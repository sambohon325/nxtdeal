// lib/aiWorker.ts — client for the NXTDeal AI Workforce (2026-07-24). Talks to the
// /workforce* routes in backend/api/app.py (backed by core/ai_worker.py / ai_worker_api.py).
// Same reuse-the-shared-helpers shape every lib/*.ts client follows: API_BASE +
// authHeaders() + a local handle<T> that surfaces the backend's {"error": ...} convention as
// a thrown Error. Caller identity (role for the ADMIN gate on activate/deactivate/run,
// employee_id for a handled interaction) is derived server-side from the Authorization
// header — never passed in a request body.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type WorkerMode = "draft" | "assisted" | "autonomous";
export type WorkerStatus = "active" | "inactive";

export type AiWorker = {
  id: string;
  role: string;
  display_name: string;
  channels: string[];
  status: WorkerStatus;
  mode: WorkerMode;
  activated_by: string | null;
  activated_at: string | null;
  deactivated_by: string | null;
  deactivated_at: string | null;
  created_at: string | null;
  interactions_handled: number;
  actions_executed: number;
  actions_drafted: number;
};

export type WorkforceSummary = {
  total_workers: number;
  active_workers: number;
  autonomous_workers: number;
  total_interactions: number;
  total_actions_executed: number;
  total_actions_drafted: number;
};

export type Workforce = { workforce: AiWorker[]; summary: WorkforceSummary };

export type WorkerAction = {
  action_key: string;
  intent: string | null;
  channel: string | null;
  status: "executed" | "drafted";
  communication_id: string | null;
  recorded_at: string | null;
};

export type WorkerDetail = AiWorker & {
  available: boolean;
  safe_actions: string[];
  recent_actions: WorkerAction[];
};

export type RunResult = {
  role?: string;
  display_name?: string;
  mode?: WorkerMode;
  status?: WorkerStatus;
  available?: boolean;
  note?: string;
  actions?: { action_key: string; status: "executed" | "drafted"; reason?: string }[];
  summary?: Record<string, number>;
  [k: string]: unknown;
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

export function fetchWorkforce(): Promise<Workforce> {
  return fetch(`${API_BASE}/workforce`, { headers: { ...authHeaders() } }).then(handle<Workforce>);
}

export function fetchWorkerDetail(role: string): Promise<WorkerDetail> {
  return fetch(`${API_BASE}/workforce/${encodeURIComponent(role)}`, {
    headers: { ...authHeaders() },
  }).then(handle<WorkerDetail>);
}

export function activateWorker(role: string, mode: WorkerMode): Promise<{ worker: AiWorker }> {
  return fetch(`${API_BASE}/workforce/${encodeURIComponent(role)}/activate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ mode }),
  }).then(handle<{ worker: AiWorker }>);
}

export function deactivateWorker(role: string): Promise<{ worker: AiWorker }> {
  return fetch(`${API_BASE}/workforce/${encodeURIComponent(role)}/deactivate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({}),
  }).then(handle<{ worker: AiWorker }>);
}

// ADMIN-only server-side: run the worker's outbound queue. Whether each touch executes vs
// drafts is decided server-side by mode + kill switch + capability + WORKER_SAFE_ACTIONS.
export function runWorkerQueue(role: string): Promise<RunResult> {
  return fetch(`${API_BASE}/workforce/${encodeURIComponent(role)}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({}),
  }).then(handle<RunResult>);
}
