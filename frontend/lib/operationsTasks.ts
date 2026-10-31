// Operations Tasks -- the "Universal Operations Work Queue" (session 106 follow-up
// #3, "keep going" autonomous continuation). Backend: core/operations_tasks.py /
// _api.py. Sam's spec: "Assign Owner, SLA Tracking with auto-escalation, Bulk
// Actions, Workflow Actions." hours_open/is_overdue are computed live on every
// fetch (server-side), same "compute live" convention as Vehicle Lifecycle's
// expires_at -- no client-side polling loop needed to keep them fresh, just
// refetch on demand.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type TaskType =
  | "transfer_to_wholesale" | "confirm_lot_audit" | "review_compliance_exception"
  | "title_processing" | "recon_followup" | "custom";
export type TaskStatus = "open" | "in_progress" | "closed";
export type TaskPriority = "low" | "normal" | "high" | "urgent";
export type OwnerBucket = "Inventory Manager" | "Title Clerk" | "Service Manager" | "Lot Manager" | "Accounting" | "Unassigned";

export type OperationsTaskCatalog = {
  task_types: TaskType[];
  statuses: TaskStatus[];
  priorities: TaskPriority[];
  owner_buckets: OwnerBucket[];
};

export type OperationsTask = {
  id: string;
  task_type: TaskType;
  detail: string;
  status: TaskStatus;
  priority: TaskPriority;
  owner_bucket: OwnerBucket;
  assigned_to: string | null;
  linked_entity_id: string | null;
  source_entity_id: string | null;
  derived: boolean;
  created_by: string;
  created_at: string;
  started_at: string | null;
  closed_at: string | null;
  closed_by: string | null;
  resolution_notes: string;
  hours_open: number | null;
  sla_hours: number;
  is_overdue: boolean;
};

export type OperationsTaskStats = {
  total: number;
  open: number;
  closed: number;
  overdue: number;
  by_owner_bucket: Record<string, number>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getOperationsTaskCatalog(): Promise<OperationsTaskCatalog> {
  const res = await fetch(`${API_BASE}/operations-tasks/catalog`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getOperationsTaskStats(): Promise<OperationsTaskStats> {
  const res = await fetch(`${API_BASE}/operations-tasks/stats`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listOperationsTasks(filters: {
  status?: TaskStatus; owner_bucket?: OwnerBucket; assigned_to?: string;
  priority?: TaskPriority; overdue_only?: boolean;
} = {}): Promise<{ tasks: OperationsTask[]; count: number }> {
  const params = new URLSearchParams();
  if (filters.status) params.set("status", filters.status);
  if (filters.owner_bucket) params.set("owner_bucket", filters.owner_bucket);
  if (filters.assigned_to) params.set("assigned_to", filters.assigned_to);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.overdue_only) params.set("overdue_only", "true");
  const qs = params.toString();
  const res = await fetch(`${API_BASE}/operations-tasks${qs ? `?${qs}` : ""}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createOperationsTask(input: {
  task_type: TaskType; detail?: string; priority?: TaskPriority; owner_bucket?: OwnerBucket;
  assigned_to?: string | null; linked_entity_id?: string | null;
}): Promise<OperationsTask> {
  const res = await fetch(`${API_BASE}/operations-tasks`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function updateOperationsTask(taskId: string, input: {
  status?: TaskStatus; priority?: TaskPriority; owner_bucket?: OwnerBucket; assigned_to?: string;
}): Promise<OperationsTask> {
  const res = await fetch(`${API_BASE}/operations-tasks/${encodeURIComponent(taskId)}/update`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function closeOperationsTask(taskId: string, resolutionNotes = ""): Promise<OperationsTask> {
  const res = await fetch(`${API_BASE}/operations-tasks/${encodeURIComponent(taskId)}/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ resolution_notes: resolutionNotes }),
  });
  return handle(res);
}

export async function escalateOperationsTask(taskId: string, notes = ""): Promise<OperationsTask> {
  const res = await fetch(`${API_BASE}/operations-tasks/${encodeURIComponent(taskId)}/escalate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ notes }),
  });
  return handle(res);
}

export async function bulkAssignOperationsTasks(taskIds: string[], ownerBucket: OwnerBucket, assignedTo?: string | null): Promise<{ results: OperationsTask[] }> {
  const res = await fetch(`${API_BASE}/operations-tasks/bulk/assign`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ task_ids: taskIds, owner_bucket: ownerBucket, assigned_to: assignedTo ?? null }),
  });
  return handle(res);
}

export async function bulkCloseOperationsTasks(taskIds: string[], resolutionNotes = ""): Promise<{ results: OperationsTask[] }> {
  const res = await fetch(`${API_BASE}/operations-tasks/bulk/close`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ task_ids: taskIds, resolution_notes: resolutionNotes }),
  });
  return handle(res);
}

export async function bulkReprioritizeOperationsTasks(taskIds: string[], priority: TaskPriority): Promise<{ results: OperationsTask[] }> {
  const res = await fetch(`${API_BASE}/operations-tasks/bulk/reprioritize`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ task_ids: taskIds, priority }),
  });
  return handle(res);
}

export async function syncOperationsTasks(): Promise<Record<string, number>> {
  const res = await fetch(`${API_BASE}/operations-tasks/sync`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}
