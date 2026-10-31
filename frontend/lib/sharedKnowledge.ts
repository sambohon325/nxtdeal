// Shared Knowledge (session 72) -- the backend-persisted counterpart to
// lib/pins.ts's browser-local "My Knowledge" pins. Sam: "id like there to be a regular
// knowledge and a shared knowledge... if you want to share, you can select a
// department, multiple departments, or all, and it goes into 'Shared Knowledge'."
//
// Talks to core/knowledge_pins_api.py's routes (see backend/api/app.py's
// "Shared Knowledge" section). Departments map onto the same 6 real roles
// core/permissions.py/core/messaging.py already use everywhere else in this app --
// there's no separate "department" concept with real access-control teeth, so this
// reuses the one that actually exists rather than inventing a second one.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { PinKind } from "@/lib/pins";

export type ShareVisibility = "all" | "roles";

export type SharedPin = {
  id: string;
  owner_employee_id: string;
  owner_name: string | null;
  kind: PinKind;
  ref_id: string | null;
  label: string;
  tag: string;
  visibility: ShareVisibility;
  roles: string[];
  shared_at: string;
};

// Friendly labels for the 6 real roles, matching the Top Menu's department casing
// elsewhere in the app (ADMIN reads as "Administration" here, matching how it's
// labeled across the rest of the UI, even though it's also literally the admin role).
export const ROLE_LABELS: Record<string, string> = {
  ADMIN: "Administration",
  OPERATIONS: "Operations",
  SALES: "Sales",
  MARKETING: "Marketing",
  SERVICE: "Service",
  FINANCE: "Finance",
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();

  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && data.error) || "Unable to reach NXTDeal backend.");
  }

  return data as T;
}

export async function fetchShareRoles(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/knowledge/pins/share-roles`, {
    headers: { ...authHeaders() },
  });
  const data = await handle<{ roles: string[] }>(res);
  return data.roles ?? [];
}

export async function fetchSharedPins(): Promise<SharedPin[]> {
  const res = await fetch(`${API_BASE}/knowledge/pins`, {
    headers: { ...authHeaders() },
  });
  const data = await handle<{ pins: SharedPin[] }>(res);
  return data.pins ?? [];
}

export async function createSharedPin(payload: {
  kind: PinKind;
  ref_id?: string | null;
  label: string;
  tag?: string;
  visibility: ShareVisibility;
  roles?: string[];
}): Promise<SharedPin> {
  const res = await fetch(`${API_BASE}/knowledge/pins`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(payload),
  });
  return handle<SharedPin>(res);
}

export async function retagSharedPin(id: string, tag: string): Promise<SharedPin> {
  const res = await fetch(`${API_BASE}/knowledge/pins/${id}/tag`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ tag }),
  });
  return handle<SharedPin>(res);
}

export async function widenSharedPinAccess(
  id: string,
  opts: { addRoles?: string[]; setAll?: boolean }
): Promise<SharedPin> {
  const res = await fetch(`${API_BASE}/knowledge/pins/${id}/share`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ add_roles: opts.addRoles, set_all: opts.setAll }),
  });
  return handle<SharedPin>(res);
}

export async function deleteSharedPin(id: string): Promise<void> {
  const res = await fetch(`${API_BASE}/knowledge/pins/${id}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  await handle<{ ok: boolean }>(res);
}

// Read-only fetch of someone ELSE's Workspace board (session 76 third follow-up) --
// backs opening a "workspace_board" pin whose owner isn't the current session.
// core/workspace_board_api.py's get_shared_workspace_board_api ACLs this against a real
// shared 'workspace_board' KnowledgePin naming ownerEmployeeId, so a 403-shaped
// {"error": ...} here is an expected, honest outcome (access was revoked, or never
// granted), not a bug to swallow silently -- callers should surface it.
export type SharedWorkspaceBoardItem = Record<string, unknown>;

export async function fetchSharedWorkspaceBoard(
  ownerEmployeeId: string
): Promise<{ id: string | null; items: SharedWorkspaceBoardItem[]; updated_at: string | null }> {
  const res = await fetch(`${API_BASE}/workspace-board/shared/${ownerEmployeeId}`, {
    headers: { ...authHeaders() },
  });
  return handle<{ id: string | null; items: SharedWorkspaceBoardItem[]; updated_at: string | null }>(res);
}
