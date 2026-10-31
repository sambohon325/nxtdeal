// Administration's "Identity & Access" item (Administration Control Center
// rebuild, continued). Backend: core/api_keys.py / _api.py -- real,
// per-employee API keys for programmatic access, already wired into
// api/app.py's _authenticate() bearer-token fallback (a generated key
// genuinely authenticates a request, not just a management screen). An
// employee can manage their own keys; managing another employee's requires
// ADMIN/OPERATIONS.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ApiKey = {
  id: string;
  employee_id: string;
  label: string;
  last4: string;
  active: boolean;
  created_by: string;
  created_at: string;
  expires_at?: string;
  last_used_at: string | null;
  revoked_by: string | null;
  revoked_at: string | null;
};

// Only present on the response from generate_api_key -- the plaintext key is
// never recoverable again after this.
export type NewApiKey = ApiKey & { raw_key: string };

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

export function generateApiKey(label: string, targetEmployeeId?: string): Promise<NewApiKey> {
  return post("/api-keys", { label, target_employee_id: targetEmployeeId || undefined });
}

export function listMyApiKeys(): Promise<{ employee_id: string; keys: ApiKey[] }> {
  return get("/api-keys/mine");
}

export function listAllApiKeys(): Promise<{ keys: ApiKey[] }> {
  return get("/api-keys/all");
}

export function listApiKeysForEmployee(employeeId: string): Promise<{ employee_id: string; keys: ApiKey[] }> {
  return get(`/api-keys/employee/${employeeId}`);
}

export function revokeApiKey(keyId: string): Promise<ApiKey> {
  return post(`/api-keys/${keyId}/revoke`);
}
