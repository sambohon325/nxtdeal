// Operations Workflow Engine v2 (2026-07-19/20) -- the real Workflow ->
// Step -> Task -> Approval -> Automation -> Completion engine, Operations
// pilot only. Backend: core/workflow_engine_v2.py / workflow_engine_v2_api.py
// / api/routers/workflow_engine_v2.py, all routes under /workflows-v2.
//
// This is a DELIBERATELY PARALLEL client to the existing v1 workflow-catalog
// system (lib/workflowCatalog-style consumers, components/
// DepartmentWorkflowButtons.tsx's floating WorkflowWindow manager) -- not a
// replacement. v1 still backs every other department's job-workflow buttons
// and Operations' own pre-existing 4 buttons; this client only talks to the
// new richer per-step v2 engine.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// ---------------------------------------------------------------------------
// Catalog (static definitions)
// ---------------------------------------------------------------------------

export type WorkflowCategory = "vehicle" | "compliance" | "operational" | "employee";

export type AutomationTier = "human_only" | "assisted" | "autonomous";

export type WorkflowStepDef = {
  key: string;
  label: string;
  owner_role: string;
  automation_tier: AutomationTier;
  automation_note: string;
  sla_hours: number;
  real_source_hint: string | null;
};

export type EscalationRules = {
  default_stalled_hours: number;
  escalate_to_role: string;
};

export type WorkflowDefV2 = {
  key: string;
  category: WorkflowCategory;
  title: string;
  purpose: string;
  entity_type: string | null;
  steps: WorkflowStepDef[];
  escalation_rules: EscalationRules;
};

export const INSTANCE_STATUSES = [
  "not_started",
  "in_progress",
  "blocked",
  "waiting_approval",
  "completed",
  "escalated",
] as const;

export type InstanceStatus = (typeof INSTANCE_STATUSES)[number];

export const STEP_STATUSES = ["not_started", "in_progress", "blocked", "completed"] as const;

export type StepStatus = (typeof STEP_STATUSES)[number];

export type CatalogV2 = {
  workflows: WorkflowDefV2[];
  instance_statuses: InstanceStatus[];
  step_statuses: StepStatus[];
};

export const CATEGORY_LABELS: Record<WorkflowCategory, string> = {
  vehicle: "Vehicle Workflows",
  compliance: "Compliance Workflows",
  operational: "Operational Workflows",
  employee: "Employee Workflows",
};

export const TIER_LABELS: Record<AutomationTier, string> = {
  human_only: "Human Only",
  assisted: "Assisted",
  autonomous: "Autonomous",
};

// ---------------------------------------------------------------------------
// Runtime instance shape
// ---------------------------------------------------------------------------

export type StepTask = {
  id: string;
  description: string;
  assigned_to: string | null;
  status: "open" | "completed";
  created_by: string;
  created_at: string;
  completed_at: string | null;
  completed_by?: string;
};

export type StepEvidence = {
  id: string;
  description: string;
  url: string | null;
  added_by: string;
  added_at: string;
};

export type StepComment = {
  id: string;
  text: string;
  by: string;
  at: string;
};

export type ApprovalStatus = "pending" | "approved" | "rejected";

export type StepApproval = {
  id: string;
  status: ApprovalStatus;
  requested_by: string;
  requested_at: string;
  decided_by: string | null;
  decided_at: string | null;
  decision_note: string | null;
  note: string | null;
};

export type RuntimeStep = WorkflowStepDef & {
  status: StepStatus;
  owner: string | null;
  tasks: StepTask[];
  evidence: StepEvidence[];
  approvals: StepApproval[];
  comments: StepComment[];
  started_at: string | null;
  completed_at: string | null;
  blocked_reason: string | null;
};

export type HistoryEntry = {
  step: string | null;
  action: string;
  by: string;
  at: string;
  notes?: string | null;
};

export type WorkflowInstanceV2 = {
  id: string;
  workflow_key: string;
  department: string;
  category: WorkflowCategory;
  title: string;
  purpose: string;
  escalation_rules: EscalationRules;
  current_step_key: string | null;
  steps: RuntimeStep[];
  status: InstanceStatus;
  linked_entity_id: string | null;
  linked_entity_raw: string | null;
  started_by: string;
  started_at: string;
  updated_at: string;
  completed_at: string | null;
  escalated_at: string | null;
  escalated_reason: string | null;
  force_closed: boolean;
  force_close_reason: string | null;
  history: HistoryEntry[];
  error?: string;
};

// ---------------------------------------------------------------------------
// Dashboard / stalled / AI state
// ---------------------------------------------------------------------------

export type DashboardRow = {
  workflow_key: string;
  title: string;
  category: WorkflowCategory;
  purpose: string;
  step_count: number;
  active: number;
  completed: number;
  escalated: number;
  blocked: number;
  waiting_approval: number;
  total: number;
};

export type DashboardV2 = {
  department: string | null;
  workflows: DashboardRow[];
  total_active: number;
  total_completed: number;
  total_escalated: number;
  error?: string;
};

export type StalledInstance = {
  instance_id: string;
  workflow_key: string;
  title: string;
  status: InstanceStatus;
  current_step_key: string;
  current_step_label: string;
  elapsed_hours: number;
  sla_hours: number;
  linked_entity_id: string | null;
};

export type StalledResponse = {
  stalled: StalledInstance[];
  error?: string;
};

export type StepSummary = {
  key: string;
  label: string;
  status: StepStatus;
  owner_role: string;
  owner: string | null;
  automation_tier: AutomationTier;
  automation_note: string;
  sla_hours: number;
  blocked_reason: string | null;
  started_at: string | null;
  completed_at: string | null;
} | null;

export type BlockedStepInfo = {
  key: string;
  label: string;
  blocked_reason: string | null;
};

export type RequiredApproval = {
  step_key: string;
  step_label: string;
  approval_id: string;
  requested_by: string;
  requested_at: string;
  note: string | null;
};

export type StalledInfo = {
  elapsed_hours: number;
  sla_hours: number;
  is_stalled: boolean;
} | null;

export type AiStateV2 = {
  instance_id: string;
  workflow_key: string;
  title: string;
  status: InstanceStatus;
  linked_entity_id: string | null;
  current_step: StepSummary;
  next_step: StepSummary;
  blocked_steps: BlockedStepInfo[];
  required_approvals: RequiredApproval[];
  missing_information: string[];
  stalled: StalledInfo;
  suggested_actions: string[];
  error?: string;
};

export type InstancesListResponse = {
  instances: WorkflowInstanceV2[];
  count: number;
  error?: string;
};

// ---------------------------------------------------------------------------
// Fetch plumbing -- mirrors lib/workforce.ts's established handle<T>/get/post
// ---------------------------------------------------------------------------

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

function post<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body ?? {}),
  }).then(handle<T>);
}

function qs(params: Record<string, string | number | undefined>): string {
  const q = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== undefined && v !== null && v !== "") q.set(k, String(v));
  });
  const s = q.toString();
  return s ? `?${s}` : "";
}

// ---------------------------------------------------------------------------
// Catalog
// ---------------------------------------------------------------------------

export function getCatalogV2(): Promise<CatalogV2> {
  return get("/workflows-v2/catalog");
}

export function getWorkflowDefV2(workflowKey: string): Promise<WorkflowDefV2> {
  return get(`/workflows-v2/catalog/${encodeURIComponent(workflowKey)}`);
}

// ---------------------------------------------------------------------------
// Dashboard / stalled / listing
// ---------------------------------------------------------------------------

export function getDashboardV2(department?: string): Promise<DashboardV2> {
  return get(`/workflows-v2/dashboard${qs({ department })}`);
}

export function getStalledInstancesV2(department?: string): Promise<StalledResponse> {
  return get(`/workflows-v2/stalled${qs({ department })}`);
}

export function listInstancesV2(params?: {
  department?: string;
  workflow_key?: string;
  status?: string;
  category?: string;
  linked_entity_id?: string;
  limit?: number;
}): Promise<InstancesListResponse> {
  return get(`/workflows-v2${qs({ ...(params ?? {}) })}`);
}

// ---------------------------------------------------------------------------
// Instance detail / AI state
// ---------------------------------------------------------------------------

export function getInstanceV2(instanceId: string): Promise<WorkflowInstanceV2> {
  return get(`/workflows-v2/${encodeURIComponent(instanceId)}`);
}

export function getInstanceAiStateV2(instanceId: string): Promise<AiStateV2> {
  return get(`/workflows-v2/${encodeURIComponent(instanceId)}/ai-state`);
}

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------

export function startWorkflowInstanceV2(input: {
  workflow_key: string;
  linked_entity_id?: string;
  notes?: string;
}): Promise<WorkflowInstanceV2> {
  return post("/workflows-v2/start", input);
}

export function advanceStepV2(instanceId: string, notes?: string): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/advance`, { notes });
}

export function addStepTaskV2(
  instanceId: string,
  input: { step_key: string; description: string; assigned_to?: string }
): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/tasks`, input);
}

export function completeStepTaskV2(
  instanceId: string,
  input: { step_key: string; task_id: string }
): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/tasks/complete`, input);
}

export function addStepEvidenceV2(
  instanceId: string,
  input: { step_key: string; description: string; url?: string }
): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/evidence`, input);
}

export function addStepCommentV2(
  instanceId: string,
  input: { step_key: string; text: string }
): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/comments`, input);
}

export function blockStepV2(
  instanceId: string,
  input: { step_key: string; reason: string }
): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/block`, input);
}

export function unblockStepV2(
  instanceId: string,
  input: { step_key: string; notes?: string }
): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/unblock`, input);
}

export function requestStepApprovalV2(
  instanceId: string,
  input: { step_key: string; note?: string }
): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/approvals/request`, input);
}

export function decideStepApprovalV2(
  instanceId: string,
  input: { step_key: string; approval_id: string; approved: boolean; note?: string }
): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/approvals/decide`, input);
}

export function escalateInstanceV2(instanceId: string, reason: string): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/escalate`, { reason });
}

export function resolveEscalationV2(instanceId: string, notes?: string): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/resolve-escalation`, { notes });
}

export function forceCloseInstanceV2(instanceId: string, reason: string): Promise<WorkflowInstanceV2> {
  return post(`/workflows-v2/${encodeURIComponent(instanceId)}/force-close`, { reason });
}
