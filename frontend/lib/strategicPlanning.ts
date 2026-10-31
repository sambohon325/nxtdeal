// Readiness reframe -- "Strategic Planning" (item #9 of Sam's 10-item
// proposed structure). Sam's own words: "A completely new area." Backend:
// core/strategic_planning.py / _api.py. Viewing is open to every real role;
// creating/editing Objectives and Initiatives is ADMIN/OPERATIONS-only,
// enforced by the backend (a non-admin caller here will simply see the real
// error message below).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ObjectiveStatus =
  | "not_started" | "on_track" | "at_risk" | "behind" | "achieved" | "missed"
  | "no_target" | "no_data" | "cancelled";

export type QuarterPace = {
  phase: "future" | "in_progress" | "complete";
  actual_to_date: number;
  days_elapsed: number;
  total_days: number;
  projected_quarter_total: number | null;
  basis: string;
  note?: string;
};

export type StrategicObjective = {
  id: string;
  quarter: string;
  year: number;
  department: string;
  title: string;
  description: string;
  target_value: number | null;
  unit: string;
  budget_allocated: number | null;
  budget_spent: number | null;
  manual_progress_pct: number | null;
  is_cancelled: boolean;
  synced_monthly_goal: boolean;
  synced_monthly_target: number | null;
  synced_at: string | null;
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
  // Computed live, never stored -- see core/strategic_planning.py's docstring.
  status: ObjectiveStatus;
  current_value: number | null;
  current_value_basis: "real" | "manual" | null;
  pct_of_target: number | null;
  quarter_phase: "future" | "in_progress" | "complete" | null;
  quarter_pace?: QuarterPace;
  expected_pct_this_far_into_quarter?: number;
  note?: string | null;
};

export type TrackingType = "website_launch" | "gps_rollout" | "manual";

export type InitiativeProgress = {
  progress_pct: number | null;
  basis: string;
  detail?: Record<string, unknown>;
  note?: string;
  error?: string;
};

export type StrategicInitiative = {
  id: string;
  name: string;
  description: string;
  department: string;
  owner_employee_id: string | null;
  status: "planned" | "in_progress" | "completed" | "cancelled";
  status_history: { status: string; by: string; at: string }[];
  start_date: string | null;
  target_completion_date: string | null;
  budget_allocated: number | null;
  budget_spent: number | null;
  tracking_type: TrackingType;
  linked_entity_type: string | null;
  linked_entity_id: string | null;
  target_metric_value: number | null;
  manual_progress_pct: number | null;
  created_by: string;
  created_at: string;
  updated_by: string;
  updated_at: string;
  progress: InitiativeProgress;
};

export type TrackingTypeCatalogEntry = {
  label: string;
  linked_entity_type: string | null;
  requires_linked_entity_id: boolean;
  requires_target_metric: boolean;
  basis: string;
  note: string;
};

export type QuarterlyRollup = {
  quarter: string;
  year: number;
  count: number;
  objectives: StrategicObjective[];
  by_department: Record<string, StrategicObjective[]>;
  status_counts: Record<string, number>;
};

export type StrategicPlanningOverview = {
  quarterly_rollup: QuarterlyRollup;
  current_quarter: string;
  current_year: number;
  initiatives_summary: { count: number; by_status: Record<string, number> };
  initiatives: StrategicInitiative[];
  department_options: string[];
  goal_tracked_departments: string[];
  tracking_type_catalog: Record<TrackingType, TrackingTypeCatalogEntry>;
  not_yet_tracked: Record<string, string>;
};

export type StrategicPlanningCatalog = {
  departments: string[];
  tracking_type_catalog: Record<TrackingType, TrackingTypeCatalogEntry>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && Object.keys(data).length === 1)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
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

export function getStrategicPlanningOverview(quarter?: string, year?: number): Promise<StrategicPlanningOverview> {
  const params = new URLSearchParams();
  if (quarter) params.set("quarter", quarter);
  if (year) params.set("year", String(year));
  const qs = params.toString();
  return get(`/strategic-planning/overview${qs ? `?${qs}` : ""}`);
}

export function getStrategicPlanningCatalog(): Promise<StrategicPlanningCatalog> {
  return get("/strategic-planning/departments");
}

export function getQuarterlyRollup(quarter?: string, year?: number): Promise<QuarterlyRollup> {
  const params = new URLSearchParams();
  if (quarter) params.set("quarter", quarter);
  if (year) params.set("year", String(year));
  const qs = params.toString();
  return get(`/strategic-planning/quarterly-rollup${qs ? `?${qs}` : ""}`);
}

export function createObjective(input: {
  quarter: string;
  year: number;
  department: string;
  title: string;
  description?: string;
  target_value?: number | null;
  unit?: string;
  budget_allocated?: number | null;
}): Promise<StrategicObjective> {
  return post("/strategic-planning/objectives", input);
}

export function updateObjective(objectiveId: string, input: {
  title?: string;
  description?: string;
  target_value?: number | null;
  unit?: string;
  budget_allocated?: number | null;
}): Promise<StrategicObjective> {
  return post(`/strategic-planning/objectives/${objectiveId}/update`, input);
}

export function updateObjectiveProgress(objectiveId: string, progressPct: number): Promise<StrategicObjective> {
  return post(`/strategic-planning/objectives/${objectiveId}/progress`, { progress_pct: progressPct });
}

export function updateObjectiveBudget(objectiveId: string, budgetAllocated?: number | null, budgetSpent?: number | null): Promise<StrategicObjective> {
  return post(`/strategic-planning/objectives/${objectiveId}/budget`, { budget_allocated: budgetAllocated, budget_spent: budgetSpent });
}

export function cancelObjective(objectiveId: string): Promise<StrategicObjective> {
  return post(`/strategic-planning/objectives/${objectiveId}/cancel`);
}

export function reopenObjective(objectiveId: string): Promise<StrategicObjective> {
  return post(`/strategic-planning/objectives/${objectiveId}/reopen`);
}

export function syncObjectiveToMonthlyGoal(objectiveId: string): Promise<StrategicObjective> {
  return post(`/strategic-planning/objectives/${objectiveId}/sync-goal`);
}

export function createInitiative(input: {
  name: string;
  department: string;
  tracking_type: TrackingType;
  description?: string;
  owner_employee_id?: string | null;
  start_date?: string | null;
  target_completion_date?: string | null;
  budget_allocated?: number | null;
  linked_entity_id?: string | null;
  target_metric_value?: number | null;
}): Promise<StrategicInitiative> {
  return post("/strategic-planning/initiatives", input);
}

export function updateInitiativeStatus(initiativeId: string, status: string): Promise<StrategicInitiative> {
  return post(`/strategic-planning/initiatives/${initiativeId}/status`, { status });
}

export function updateInitiativeProgress(initiativeId: string, progressPct: number): Promise<StrategicInitiative> {
  return post(`/strategic-planning/initiatives/${initiativeId}/progress`, { progress_pct: progressPct });
}

export function updateInitiativeBudget(initiativeId: string, budgetAllocated?: number | null, budgetSpent?: number | null): Promise<StrategicInitiative> {
  return post(`/strategic-planning/initiatives/${initiativeId}/budget`, { budget_allocated: budgetAllocated, budget_spent: budgetSpent });
}
