// Workspace grab-all client (2026-07-23) -- Sam: "All framable data (reporting modules,
// individual details, etc) need to be grabbable and be able to pull into or be added to
// workspace... across the entire platform." Posts ONE captured frame to the caller's own
// Workspace board via POST /workspace-board/item (core/workspace_board.py's snapshot item
// kind). Standalone (not the useWorkspaceBoard hook) so the reusable AddToWorkspaceButton
// can fire it from anywhere in the app without loading the whole board.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type GrabSnapshot = {
  title: string;
  source_label?: string;
  source_context?: string;
  // "table" (columns + rows) or "text". Inferred by the button when omitted.
  data_kind?: "table" | "text";
  columns?: string[];
  rows?: Record<string, unknown>[];
  text?: string;
};

export async function addSnapshotToWorkspace(snapshot: GrabSnapshot): Promise<void> {
  const item = { kind: "snapshot", ...snapshot };
  const res = await fetch(`${API_BASE}/workspace-board/item`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ item }),
  });
  const data = await res.json().catch(() => ({}));
  if (
    !res.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to add to workspace.");
  }
}
