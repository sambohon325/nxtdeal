// Administration's "Roles & Permissions" item (Administration Control Center
// rebuild, first slice). Backend: core/permissions_registry.py / _api.py.
// A real ADDITIVE layer on top of the platform's 6 core roles -- a granular
// permission catalog, per-employee overrides, field-level security (already
// wired into Customer 360's CreditScore / Credit Applications' ssn_last4 on
// the backend), and a real 3-tier (staff/manager/executive) approval-hierarchy
// engine off each employee's real Employee.Title.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type PermissionEntry = {
  key: string;
  label: string;
  roles?: string[];
  category?: string;
};

export type PermissionCatalog = {
  categories: { category: string; permissions: PermissionEntry[] }[];
  roles: string[];
};

export type EffectivePermission = {
  key: string;
  label: string;
  category: string;
  role_default: boolean;
  effective: boolean;
  overridden: boolean;
};

export type PermissionOverride = {
  id: string;
  employee_id: string;
  permission_key: string;
  granted: boolean;
  reason: string;
  active: boolean;
  granted_by: string;
  created_at: string;
  superseded_at: string | null;
};

export type TierBucket = {
  count: number;
  employees: { id: string; name: string; title: string | null; department: string | null }[];
};

export type TierDistribution = Record<"staff" | "manager" | "executive", TierBucket>;

export type ApprovalChain = { key: string; label: string; steps: string[] };

export type ApprovalRequest = {
  id: string;
  chain_key: string;
  chain_label: string;
  steps: string[];
  current_step_index: number;
  status: "pending" | "approved" | "rejected" | "cancelled";
  subject: string;
  details: string;
  entity_id: string | null;
  requested_by: string;
  created_at: string;
  updated_at: string;
  history: { action: string; by: string; at: string; [k: string]: unknown }[];
};

export type RolesPermissionsOverview = {
  permission_catalog: PermissionCatalog;
  tier_distribution: Record<string, number>;
  tier_breakdown: TierDistribution;
  active_overrides: { count: number; overrides: PermissionOverride[] };
  approval_chains: ApprovalChain[];
  approval_requests: { by_status: Record<string, number>; total: number };
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
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

export function getPermissionCatalog(): Promise<PermissionCatalog> {
  return get("/permissions/catalog");
}

export function getTierDistribution(): Promise<TierDistribution> {
  return get("/permissions/tier-distribution");
}

export function listAllOverrides(): Promise<{ overrides: PermissionOverride[] }> {
  return get("/permissions/overrides");
}

export function setPermissionOverride(
  employeeId: string,
  permissionKey: string,
  granted: boolean,
  reason: string
): Promise<PermissionOverride> {
  return post("/permissions/overrides", { employee_id: employeeId, permission_key: permissionKey, granted, reason });
}

export function revokeOverride(overrideId: string): Promise<PermissionOverride> {
  return post(`/permissions/overrides/${overrideId}/revoke`);
}

export function getEmployeeEffectivePermissions(
  employeeId: string
): Promise<{ employee_id: string; permissions: EffectivePermission[] }> {
  return get(`/permissions/employees/${employeeId}/effective`);
}

export function getEmployeeOverrides(employeeId: string): Promise<{ employee_id: string; overrides: PermissionOverride[] }> {
  return get(`/permissions/employees/${employeeId}/overrides`);
}

export function listApprovalChains(): Promise<{ chains: ApprovalChain[] }> {
  return get("/approval-requests/chains");
}

export function listApprovalRequests(opts?: {
  status?: string;
  mine?: boolean;
  pendingForMe?: boolean;
}): Promise<{ requests: ApprovalRequest[] }> {
  const params = new URLSearchParams();
  if (opts?.status) params.set("status", opts.status);
  if (opts?.mine) params.set("mine", "true");
  if (opts?.pendingForMe) params.set("pending_for_me", "true");
  const qs = params.toString();
  return get(`/approval-requests${qs ? `?${qs}` : ""}`);
}

export function createApprovalRequest(
  chainKey: string,
  subject: string,
  details?: string,
  entityId?: string
): Promise<ApprovalRequest> {
  return post("/approval-requests", { chain_key: chainKey, subject, details: details || "", entity_id: entityId || null });
}

export function getApprovalRequest(requestId: string): Promise<ApprovalRequest> {
  return get(`/approval-requests/${requestId}`);
}

export function approveApprovalStep(requestId: string, note?: string): Promise<ApprovalRequest> {
  return post(`/approval-requests/${requestId}/approve`, { note: note || "" });
}

export function rejectApprovalStep(requestId: string, reason: string): Promise<ApprovalRequest> {
  return post(`/approval-requests/${requestId}/reject`, { reason });
}

export function cancelApprovalRequest(requestId: string): Promise<ApprovalRequest> {
  return post(`/approval-requests/${requestId}/cancel`);
}
