// Programming Schedule API client (2026-10-24).
// Backend: core/programming_schedule.py + api/app.py routes /programming-schedule/*.
//
// Staff-only work tracker: features, bugs, security issues, tech-debt across
// phases. Visible to Dealer Admin/Operations. Not customer-facing.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ItemType = "feature" | "bug" | "security" | "tech-debt";
export type Phase = "Phase 0" | "Phase 1" | "Phase 2" | "Phase 3" | "Phase 4" | "Phase 5" | "Phase 6" | "Phase 7";
export type Status = "todo" | "in_progress" | "in_review" | "done" | "deployed" | "pushed_live" | "blocked";
export type Priority = "low" | "medium" | "high" | "critical";
export type Assignee = "backend" | "frontend" | "devops" | "sample" | "unassigned";
export type SecuritySeverity = "low" | "medium" | "high" | "critical";
export type ResourceRoute = "local" | "vps" | "sam_only";
export type ItemOwner = "auto" | "sam" | "backend" | "frontend" | "devops" | "sample";

export interface PSItem {
  id: string;
  title: string;
  description: string;
  type: ItemType;
  phase: Phase;
  status: Status;
  priority: Priority;
  assignee: Assignee;
  est_hours: number;
  logged_hours: number;
  progress: number;
  depends_on: string[];
  security_severity: SecuritySeverity | null;
  work_notes: { timestamp: string; note: string }[];
  resources: string[];
  resource_route: ResourceRoute;
  owner: ItemOwner;
  created_at: string | null;
  updated_at: string | null;
}

export interface ScheduleRun {
  id: string;
  item_id: string;
  worker: string;
  provider: string;
  model: string;
  outcome: "running" | "completed" | "failed" | "released";
  started_at: string | null;
  completed_at: string | null;
  heartbeat_at: string | null;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cost_usd: number;
  commit_sha: string | null;
  tests_summary: string | null;
  notes: string | null;
  progress: number | null;
}

export interface ScheduleEvent {
  id: string;
  item_id: string;
  event_type: string;
  worker: string | null;
  outcome: string | null;
  message: string | null;
  created_at: string;
}

export interface WorkerSummary {
  runs: number;
  runs_completed: number;
  runs_running: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cost_usd: number;
}

export interface ModelSummary {
  runs: number;
  input_tokens: number;
  output_tokens: number;
  cache_read_tokens: number;
  cost_usd: number;
  free: boolean;
}

export interface ResourceSummary {
  workers: Record<string, WorkerSummary>;
  models: Record<string, ModelSummary>;
  mtd_total_cost: number;
  mtd_total_tokens: number;
}

export interface PSDashboardItem {
  id: string;
  title: string;
  description: string;
  type: ItemType;
  phase: Phase;
  status: Status;
  priority: Priority;
  assignee: Assignee;
  est_hours: number;
  logged_hours: number;
  progress: number;
  depends_on: string[];
  security_severity: SecuritySeverity | null;
  work_notes: { timestamp: string; note: string }[];
  resources: string[];
  resource_route: ResourceRoute;
  owner: ItemOwner;
  created_at: string | null;
  updated_at: string | null;
  claimed_by: string | null;
  claimed_at: string | null;
  lease_expires_at: string | null;
  run: ScheduleRun | null;
  event_count: number;
  last_commit?: string | null;
}

export interface PSDashboard {
  dashboard: {
    by_phase: Record<string, { total: number; done: number; remaining_hours: number }>;
    by_assignee: Record<string, number>;
    by_status: Record<string, number>;
    by_type: Record<string, number>;
    by_priority: Record<string, number>;
    completed: number;
    remaining_hours: number;
    logged_hours: number;
    security_issues: number;
    blockers: number;
    total: number;
  };
  by_phase: Record<string, {
    total: number; done: number; remaining_hours: number; total_hours: number; logged_hours: number;
    items: PSDashboardItem[];
  }>;
  phase_order: string[];
  route_labels: Record<string, string>;
  owner_labels: Record<string, string>;
  route_counts: Record<string, number>;
  in_progress: PSDashboardItem[];
  up_next: PSDashboardItem[];
  blocked_on_sam: PSDashboardItem[];
  done: PSDashboardItem[];
  active_runs: ScheduleRun[];
  resources: ResourceSummary;
  target_date: string;
  days_left: number;
  pct_done_by_hours: number;
  total_est_hours: number;
  total_logged_hours: number;
}

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : (data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.",
    );
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

function post<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

function patch<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

// --- Dashboard ---
export function getDashboard(): Promise<PSDashboard> {
  return get<PSDashboard>("/programming-schedule/dashboard");
}

// --- Item list ---
export function listItems(filters?: {
  phase?: string;
  assignee?: string;
  status?: string;
  item_type?: string;
  priority?: string;
  resource_route?: string;
  owner?: string;
    }): Promise<PSItem[]> {
  const params = new URLSearchParams();
  if (filters?.phase) params.set("phase", filters.phase);
  if (filters?.assignee) params.set("assignee", filters.assignee);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.item_type) params.set("item_type", filters.item_type);
  if (filters?.priority) params.set("priority", filters.priority);
  if (filters?.resource_route) params.set("resource_route", filters.resource_route);
  if (filters?.owner) params.set("owner", filters.owner);
  const qs = params.toString();
  return get<PSItem[]>(`/programming-schedule${qs ? `?${qs}` : ""}`);
}

// --- Create ---
export function createItem(item: {
  title: string;
  description?: string;
  item_type?: ItemType;
  phase?: Phase;
  priority?: Priority;
  assignee?: Assignee;
  est_hours?: number;
  depends_on?: string[];
  security_severity?: SecuritySeverity | null;
  resource_route?: ResourceRoute;
  owner?: ItemOwner;
  work_notes?: { timestamp: string; note: string }[];
  resources?: string[];
}): Promise<PSItem> {
  return post<PSItem>("/programming-schedule", item);
}

// --- Get single item ---
export function getItem(item_id: string): Promise<PSItem> {
  return get<PSItem>(`/programming-schedule/${encodeURIComponent(item_id)}`);
}

// --- Update (patch fields) ---
export function updateItem(item_id: string, fields: Partial<PSItem>): Promise<PSItem> {
  return patch<PSItem>(`/programming-schedule/${encodeURIComponent(item_id)}`, fields);
}

// --- Set progress ---
export function setProgress(item_id: string, progress: number): Promise<PSItem> {
  return post<PSItem>(`/programming-schedule/${encodeURIComponent(item_id)}/progress`, { progress });
}

// --- Assign ---
export function assignItem(item_id: string, assignee: Assignee): Promise<PSItem> {
  return post<PSItem>(`/programming-schedule/${encodeURIComponent(item_id)}/assign`, { assignee });
}

// --- Set status ---
export function setStatus(item_id: string, status: Status): Promise<PSItem> {
  return post<PSItem>(`/programming-schedule/${encodeURIComponent(item_id)}/status`, { status });
}

// --- Log hours ---
export function logHours(item_id: string, hours: number): Promise<PSItem> {
  return post<PSItem>(`/programming-schedule/${encodeURIComponent(item_id)}/hours`, { hours });
}

// --- Add work note ---
export function addWorkNote(item_id: string, note: string): Promise<PSItem> {
  return post<PSItem>(`/programming-schedule/${encodeURIComponent(item_id)}/notes`, { note });
}

// --- Add resource ---
export function addResource(item_id: string, resource: string): Promise<PSItem> {
  return post<PSItem>(`/programming-schedule/${encodeURIComponent(item_id)}/resources`, { resource });
}

// --- Get items by route (for VPS agent pickup) ---
export function getByRoute(route: ResourceRoute): Promise<PSItem[]> {
  return get<PSItem[]>(`/programming-schedule/route/${route}`);
}

// --- Set route + owner for an item ---
export function setRoute(item_id: string, resource_route: ResourceRoute, owner?: ItemOwner): Promise<PSItem> {
  return post<PSItem>(`/programming-schedule/${encodeURIComponent(item_id)}/route`, { resource_route, owner });
}

// --- Route badge helpers ---
export const ROUTE_LABELS: Record<ResourceRoute, string> = {
  local: "Local (Desktop)",
  vps: "VPS (Tailscale)",
  sam_only: "Sam Only",
};

export const OWNER_LABELS: Record<ItemOwner, string> = {
  auto: "Auto",
  sam: "Sam",
  backend: "Backend",
  frontend: "Frontend",
  devops: "DevOps",
  sample: "Sample (Sam)",
};

// --- Status badge helpers ---
export const STATUS_COLORS: Record<Status, string> = {
  todo: "text-zinc-400",
  in_progress: "text-sky-400",
  in_review: "text-amber-400",
  done: "text-emerald-400",
  deployed: "text-indigo-400",
  pushed_live: "text-violet-400",
  blocked: "text-red-400",
};

export const PRIORITY_COLORS: Record<Priority, string> = {
  low: "text-zinc-500",
  medium: "text-amber-400",
  high: "text-orange-400",
  critical: "text-red-400",
};

export const TYPE_ICONS: Record<ItemType, string> = {
  feature: "✨",
  bug: "🐛",
  security: "🛡️",
  "tech-debt": "🔧",
};

export const PHASE_ORDER: Phase[] = [
  "Phase 0", "Phase 1", "Phase 2", "Phase 3", "Phase 4", "Phase 5", "Phase 6", "Phase 7",
];

export const ASSIGNEE_LABELS: Record<Assignee, string> = {
  backend: "Backend",
  frontend: "Frontend",
  devops: "DevOps",
  sample: "Sample (Sam)",
  unassigned: "Unassigned",
};
