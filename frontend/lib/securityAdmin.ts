// Administration's "Security" item, expansion (Administration Control Center
// rebuild, continued). Backend: core/auth_api.py's get_lockout_status() /
// unlock_account() / set_ip_allowlist() -- real, computed account-lockout
// state and a real per-employee IP allowlist, layered on top of
// core/auth.py's CredentialStore. Per-employee lookup/unlock is
// ADMIN/OPERATIONS; setting an IP allowlist is ADMIN-only (narrower --
// misconfiguring it can lock an employee out of the platform entirely).
// The roster-wide summary (locked_employees / ip_allowlist_coverage) already
// comes back through the generic GET /menu/data?item_key=security fetch
// (core/administration_menu.py's security()) -- this client only covers the
// per-employee detail + mutating actions layered on top of that.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type LockoutStatus = {
  employee_id: string;
  locked: boolean;
  locked_until: string | null;
  failed_attempts: number;
};

export type IpAllowlistResult = {
  employee_id: string;
  ip_allowlist: string[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function getLockoutStatus(employeeId: string): Promise<LockoutStatus> {
  return fetch(`${API_BASE}/auth/admin/lockout/${employeeId}`, { headers: { ...authHeaders() } }).then(handle<LockoutStatus>);
}

export function unlockAccount(employeeId: string): Promise<{ employee_id: string; locked: boolean }> {
  return fetch(`${API_BASE}/auth/admin/unlock/${employeeId}`, {
    method: "POST",
    headers: { ...authHeaders() },
  }).then(handle<{ employee_id: string; locked: boolean }>);
}

export function setIpAllowlist(employeeId: string, ipAllowlist: string[]): Promise<IpAllowlistResult> {
  return fetch(`${API_BASE}/auth/admin/ip-allowlist/${employeeId}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ ip_allowlist: ipAllowlist }),
  }).then(handle<IpAllowlistResult>);
}
