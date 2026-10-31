// Operations' "Communications" Top Menu item -- the Unified Communications
// Hub, a real, read-only, cross-department feed composed from Sales'/Service's/
// Finance's own already-real contact logs (core/unified_communications.py). No
// dedicated routes exist -- this comes entirely through the generic
// GET /menu/data?department=Operations&item_key=communications route
// (core/operations_menu.py's communications()), same "general dashboard stays
// behind /menu/data" precedent lib/governance.ts's getGovernanceMenuOverview()
// already established.
//
// As of 2026-07-22, core/operations_menu.py's communications() composes this
// legacy feed ALONGSIDE the newer, first-class Communications Hub
// (core/communications_hub.py, see lib/communicationsHub.ts) into one nested
// response shape: {legacy_unified, communications_hub, note}. This client's
// own getUnifiedCommunicationsOverview() unwraps .legacy_unified so every
// existing caller of this file keeps working against the same
// UnifiedCommunicationsOverview shape it always has, unaffected by that
// backend composition change.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type CommTouch = {
  id: string;
  department: string | null;
  channel: string | null;
  body: string;
  linked_entity_id: string | null;
  linked_entity_label: string | null;
  created_by: string | null;
  created_at: string | null;
};

export type UnifiedFeed = {
  total: number;
  by_department: Record<string, number>;
  by_channel: Record<string, number>;
  items: CommTouch[];
};

export type MarketingSendCount = {
  total_templates: number;
  attached_to_campaign: number;
};

export type UnifiedCommunicationsOverview = {
  feed: UnifiedFeed;
  marketing_sends: MarketingSendCount;
  not_yet_tracked: Record<string, string>;
  error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

type ComposedCommunicationsMenuResponse =
  | UnifiedCommunicationsOverview
  | {
      legacy_unified: UnifiedCommunicationsOverview;
      communications_hub?: unknown;
      note?: string;
      error?: string;
    };

export function getUnifiedCommunicationsOverview(): Promise<UnifiedCommunicationsOverview> {
  const params = new URLSearchParams({ department: "Operations", item_key: "communications" });
  return fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } })
    .then(handle<ComposedCommunicationsMenuResponse>)
    .then((wrapped) => {
      if (wrapped && typeof wrapped === "object" && "legacy_unified" in wrapped) {
        return wrapped.legacy_unified;
      }
      // Fallback for the pre-2026-07-22 flat shape, in case a stale build is served.
      return wrapped as UnifiedCommunicationsOverview;
    });
}
