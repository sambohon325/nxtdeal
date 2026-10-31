// Administration's "Users" item, enriched (Administration Control Center
// rebuild, closing slice, 2026-07-19). Backend: core/administration_menu.py's
// users() -- reached via the same generic GET /menu/data?department=
// Administration&item_key=users route every prior Administration slice's
// less-elaborate items already use. This client only covers the read side
// (the roster + per-employee combined identity/access/security detail) --
// every mutating action (unlock an account, set an IP allowlist, grant/
// revoke a permission override, generate/revoke an API key) reuses the
// already-real, already-built clients those individual items shipped with:
// lib/securityAdmin.ts, lib/rolesPermissions.ts, lib/apiKeys.ts. Nothing here
// duplicates that logic.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type UserAdministrationRow = {
  employee_id: string;
  name: string | null;
  title: string | null;
  department: string | null;
  role: string;
  must_change_password: boolean;
  locked: boolean;
  failed_attempts: number;
  active_permission_overrides: number;
  active_api_keys: number;
};

export type PermissionRequestBrief = {
  id: string;
  chain_key: string;
  chain_label?: string;
  status: string;
  subject: string;
  requested_by: string;
  created_at: string;
  [k: string]: unknown;
};

export type UsersOverview = {
  active_employees: { count: number | null; error?: string };
  department_access: Record<string, { with_login?: number; without_login?: number; total?: number }>;
  employees_without_login: { count: number; employees: unknown[] };
  role_assignments: Record<string, number>;
  user_administration: {
    count: number;
    rows: UserAdministrationRow[];
    locked_count: number;
    with_active_overrides_count: number;
    with_active_api_keys_count: number;
    note: string;
  };
  permission_requests: {
    count: number;
    by_status: Record<string, number>;
    requests: PermissionRequestBrief[];
    note: string;
  };
  not_yet_tracked: Record<string, string>;
};

export type EffectivePermissionEntry = {
  key: string;
  label: string;
  category: string;
  role_default: boolean;
  effective: boolean;
  overridden: boolean;
};

export type UserDetail = {
  employee: { id: string; entity_type: string; attributes: Record<string, unknown> };
  related_entities: unknown[];
  identity_and_access: {
    role: string | null;
    must_change_password: boolean;
    created_at: string | null;
    email: string | null;
    lockout: { locked: boolean; locked_until: string | null; failed_attempts: number };
    ip_allowlist: string[];
    effective_permissions: EffectivePermissionEntry[];
    active_permission_overrides: Record<string, unknown>[];
    api_keys: Record<string, unknown>[];
  };
  recent_activity: {
    actor: string;
    total_events: number;
    events: { id: string; event_type: string; entity_id: string | null; timestamp: string; [k: string]: unknown }[];
  };
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

export function getUsersOverview(): Promise<UsersOverview> {
  const params = new URLSearchParams({ department: "Administration", item_key: "users" });
  return get(`/menu/data?${params.toString()}`);
}

export function getUserDetail(employeeId: string): Promise<UserDetail> {
  const params = new URLSearchParams({ department: "Administration", item_key: "users", query: employeeId });
  return get(`/menu/data?${params.toString()}`);
}
