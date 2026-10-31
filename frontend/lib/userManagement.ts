// Bumper-parity user management client (2026-07-25): create a user (Employee + login +
// role) in one admin action, reassign roles, and the new BDC role. Talks to the /users*
// routes in backend/api/app.py (backend/core/user_management_api.py).
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type RoleInfo = { role: string; description: string; allowed_dashboards: string[] };

export type UserRow = {
  employee_id: string | null;
  name: string | null;
  first_name?: string | null;
  last_name?: string | null;
  email: string | null;
  department: string | null;
  title: string | null;
  role: string | null;
  has_login: boolean;
  must_change_password: boolean;
};

export type CreatedUser = {
  employee_id: string;
  name: string;
  email: string;
  role: string;
  department: string;
  title: string;
  temp_password: string;
  must_change_password: boolean;
};

export async function listRoles(): Promise<{ roles: RoleInfo[] }> {
  const res = await fetch(`${API_BASE}/users/roles`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listUsers(): Promise<{ users: UserRow[]; count: number }> {
  const res = await fetch(`${API_BASE}/users`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createUser(input: {
  first_name: string;
  last_name: string;
  email?: string | null;
  role: string;
  department?: string | null;
  title?: string | null;
  temp_password?: string | null;
}): Promise<CreatedUser> {
  const res = await fetch(`${API_BASE}/users`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function updateUserRole(
  targetEmployeeId: string,
  newRole: string
): Promise<{ employee_id: string; old_role: string; new_role: string; allowed_dashboards: string[] }> {
  const res = await fetch(`${API_BASE}/users/${encodeURIComponent(targetEmployeeId)}/role`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ new_role: newRole }),
  });
  return handle(res);
}
