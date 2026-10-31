// The Up System (session 100 follow-up) -- a real walk-in/phone-up log with a
// genuine round-robin floor rotation. Backend: core/up_system.py / up_system_api.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type UpType = "walk_in" | "phone_up";
export type UpStatus = "working" | "demo" | "worksheet" | "be_back" | "sold" | "no_sale";

export type RotationSlot = { employee_id: string; name: string | null; active: boolean };

export type Rotation = {
  board: RotationSlot[];
  next_index: number;
  next_up: { employee_id: string; name: string | null } | null;
  updated_at: string;
};

export type Up = {
  id: string;
  first_name: string | null;
  last_name: string | null;
  phone: string | null;
  email: string | null;
  up_type: UpType;
  up_status: UpStatus;
  up_notes: string;
  up_logged_by: string;
  up_logged_by_name: string | null;
  up_logged_at: string;
  assigned_to: string | null;
  assigned_to_name: string | null;
  pipeline_state: string | null;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function getRotation(): Promise<Rotation> {
  const res = await fetch(`${API_BASE}/up-system/rotation`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function setBoardActive(employeeId: string, active: boolean): Promise<Rotation> {
  const res = await fetch(`${API_BASE}/up-system/rotation/active`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ employee_id: employeeId, active }),
  });
  return handle(res);
}

export async function logUp(input: {
  up_type: UpType;
  first_name: string;
  last_name?: string;
  phone?: string | null;
  email?: string | null;
  notes?: string;
}): Promise<Up> {
  const res = await fetch(`${API_BASE}/up-system/log`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function updateUpStatus(leadId: string, status: UpStatus): Promise<Up> {
  const res = await fetch(`${API_BASE}/up-system/ups/${encodeURIComponent(leadId)}/status`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ status }),
  });
  return handle(res);
}

export async function listUps(opts: { status?: UpStatus } = {}): Promise<Up[]> {
  const params = new URLSearchParams();
  if (opts.status) params.set("status", opts.status);
  const res = await fetch(`${API_BASE}/up-system/ups?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getBeBackBoard(): Promise<Up[]> {
  const res = await fetch(`${API_BASE}/up-system/be-back-board`, { headers: { ...authHeaders() } });
  return handle(res);
}
