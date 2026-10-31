// Pinned results (BUILD_QUEUE.md's "Chat-First Admin + Pinned Knowledge" entry, session
// 26, extended session 27 with tags). Per Sam: "the knowledge corner should be where
// pinned results live" — when a chat-triggered panel (employee roster, audit log,
// compliance layer, an entity profile, a department dashboard, a readiness/network
// panel) is worth coming back to, pin it instead of re-asking every time. Session 27
// added tags ("so it doesn't just become a wall of bars") — every pin has a tag, the
// Knowledge sidebar groups by tag, and a pin's tag can be changed after the fact.
//
// Browser-only via localStorage, same lightweight approach already used for the session
// token (frontend/lib/auth.ts) — deliberately NOT saved server-side, so pins won't
// follow someone to a different browser/device yet. Reopening a pin always re-fetches
// fresh data (see each page's handleOpenPin) — a pin is a bookmark to a *kind* of view,
// not a frozen snapshot.
//
// Shared across /admin, /workspace, /readiness, and /network (session 27 — "all of
// NXTDeal needs to function with the same ideology") via one localStorage key, so a
// pin made on one page shows up in the Knowledge sidebar on every other page too.

export type PinKind =
  | "roster"
  | "audit"
  | "compliance"
  | "readiness_score"
  | "performance_rank"
  | "growth_opportunities"
  | "profile"
  | "dashboard"
  | "asset"
  | "campaign"
  | "website"
  | "deal"
  | "department_intelligence"
  | "visualization"
  // A note card from the Workspace board (session 76 follow-up) -- refId is the
  // WorkspaceNoteItem's own id, re-fetched live from GET /workspace-board when opened
  // (same "pin is a bookmark, not a frozen snapshot" rule every other kind follows).
  | "workspace_note"
  // The WHOLE Workspace board, pinned as one Knowledge point (session 76 third
  // follow-up -- Sam: "move the pin to knowledge out of the reports and notes
  // windows and put it into the workspace as a whole... pin everything in their
  // workspace as one knowledge point"). refId is the OWNER's employee_id -- opening a
  // pin where refId matches the current session's own employee_id just brings the
  // Workspace column forward (it's already live), opening one where it doesn't
  // fetches GET /workspace-board/shared/{refId} (core/workspace_board_api.py's
  // get_shared_workspace_board_api, ACL'd against a real shared 'workspace_board'
  // KnowledgePin) and renders it read-only.
  | "workspace_board";

export const DEFAULT_TAG = "General";

export type Pin = {
  id: string;
  label: string;
  kind: PinKind;
  // Entity ID for a "profile" pin, dashboard key for a "dashboard" pin. Not needed for
  // the singleton panel kinds (roster/audit/compliance/readiness_score/
  // performance_rank/growth_opportunities) — there's only one of each.
  refId?: string;
  tag: string;
  pinnedAt: string;
};

const STORAGE_KEY = "dealeros_pins";
const LEGACY_STORAGE_KEY = "dealeros_admin_pins";

function migrateLegacyPins(): Pin[] {
  if (typeof window === "undefined") return [];

  const raw = localStorage.getItem(LEGACY_STORAGE_KEY);

  if (!raw) return [];

  try {
    const parsed = JSON.parse(raw);

    if (!Array.isArray(parsed)) return [];

    // Session 26's pins had no `tag` field — backfill DEFAULT_TAG so old pins (from
    // /admin only, pre-rollout) keep working under the new shared key.
    const migrated: Pin[] = parsed.map((p) => ({ ...p, tag: p.tag || DEFAULT_TAG }));

    localStorage.setItem(STORAGE_KEY, JSON.stringify(migrated));
    localStorage.removeItem(LEGACY_STORAGE_KEY);

    return migrated;
  } catch {
    return [];
  }
}

export function getPins(): Pin[] {
  if (typeof window === "undefined") return [];

  const raw = localStorage.getItem(STORAGE_KEY);

  if (!raw) return migrateLegacyPins();

  try {
    const parsed = JSON.parse(raw);

    if (!Array.isArray(parsed)) return [];

    // Backfill in case anything ever lands without a tag.
    return (parsed as Pin[]).map((p) => ({ ...p, tag: p.tag || DEFAULT_TAG }));
  } catch {
    return [];
  }
}

function savePins(pins: Pin[]) {
  if (typeof window === "undefined") return;

  localStorage.setItem(STORAGE_KEY, JSON.stringify(pins));
}

export function addPin(
  pin: Omit<Pin, "id" | "pinnedAt" | "tag"> & { tag?: string }
): Pin[] {
  const existing = getPins();

  // Re-pinning the same kind+refId is a no-op rather than a duplicate — there's only
  // ever one "current" pin per singleton kind, and one pin per distinct
  // profile/dashboard.
  const alreadyPinned = existing.some(
    (p) => p.kind === pin.kind && p.refId === pin.refId
  );

  if (alreadyPinned) return existing;

  const next: Pin[] = [
    ...existing,
    {
      ...pin,
      tag: pin.tag?.trim() || DEFAULT_TAG,
      id: `${pin.kind}-${pin.refId ?? "default"}-${Date.now()}`,
      pinnedAt: new Date().toISOString(),
    },
  ];

  savePins(next);

  return next;
}

export function removePin(id: string): Pin[] {
  const next = getPins().filter((p) => p.id !== id);

  savePins(next);

  return next;
}

export function retagPin(id: string, tag: string): Pin[] {
  const next = getPins().map((p) =>
    p.id === id ? { ...p, tag: tag.trim() || DEFAULT_TAG } : p
  );

  savePins(next);

  return next;
}

export function getAllTags(pins: Pin[]): string[] {
  return Array.from(new Set(pins.map((p) => p.tag || DEFAULT_TAG))).sort();
}
