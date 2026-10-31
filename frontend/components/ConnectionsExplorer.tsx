"use client";

// Multi-hop "Explore Connections" section (session 76 fourth follow-up). Sam:
// "everything that's created in workspace, referenced in chats, group messages as
// well as in the dashes -- all of that knowledge association needs to be
// interconnected into the graph... I should be able to click on a text translation of
// a graph and find lists of the people that its referencing and explore who they are
// individually... the same in reverse."
//
// Mounted once inside components/EntityProfile.tsx's EntityProfileView, for every
// entity type (Customer/Employee/Vehicle/fallback) -- unlike the existing per-type
// Sections above it (Vehicles/Finance Contracts/etc, which are hand-picked one-hop
// relationships from core/queries.py's get_*_360 functions), this fetches
// GET /entity/{id}/explore (core/graph_explore.py) and renders WHATEVER real
// relationships exist, generically, up to 2 hops out -- including the new kinds that
// didn't exist anywhere in the UI before this: chat messages that mention this entity,
// and Knowledge pins that reference it. Same role-based access this whole app already
// uses (core/graph_explore.py's _can_view) -- a node the caller can't see simply isn't
// in the response, not shown as a locked placeholder.

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { displayName, type EntitySummary } from "@/components/EntityProfile";

type ExploreNode = {
  direction: "IN" | "OUT";
  relationship_type: string;
  created_by: string | null;
  created_at: string | null;
  entity: EntitySummary;
  children: ExploreNode[];
  truncated_children: number;
};

type ExploreResult = {
  entity?: EntitySummary;
  children?: ExploreNode[];
  truncated_children?: number;
  depth?: number;
  error?: string;
};

function relationshipLabel(node: ExploreNode): string {
  const verb = node.relationship_type.replace(/_/g, " ").toLowerCase();
  return node.direction === "OUT" ? verb : `${verb} (by)`;
}

function NodeRow({
  node,
  onSelect,
  depthLevel,
}: {
  node: ExploreNode;
  onSelect: (entityId: string) => void;
  depthLevel: number;
}) {
  const [expanded, setExpanded] = useState(depthLevel === 0);

  return (
    <div className={depthLevel > 0 ? "ml-4 border-l border-zinc-800 pl-3" : ""}>
      <div className="flex items-center gap-2 py-1.5">
        {node.children.length > 0 ? (
          <button
            onClick={() => setExpanded((e) => !e)}
            className="text-zinc-600 hover:text-white transition text-xs w-4 shrink-0"
            title={expanded ? "Collapse" : "Expand"}
          >
            {expanded ? "▾" : "▸"}
          </button>
        ) : (
          <span className="w-4 shrink-0" />
        )}

        <span className="text-[10px] uppercase tracking-wide text-zinc-600 shrink-0">
          {relationshipLabel(node)}
        </span>

        <button
          onClick={() => onSelect(node.entity.id)}
          className="text-left text-sm text-zinc-200 hover:text-[#3FBCC4] transition truncate"
        >
          {displayName(node.entity)}
        </button>

        <span className="text-[10px] uppercase tracking-wider text-zinc-600 shrink-0">
          {node.entity.entity_type}
        </span>

        {node.created_by && (
          <span className="text-[10px] text-zinc-700 shrink-0 truncate">
            — linked by {node.created_by}
            {node.created_at ? ` on ${new Date(node.created_at).toLocaleDateString()}` : ""}
          </span>
        )}
      </div>

      {expanded && node.children.length > 0 && (
        <div>
          {node.children.map((child, i) => (
            <NodeRow key={`${child.entity.id}-${i}`} node={child} onSelect={onSelect} depthLevel={depthLevel + 1} />
          ))}
          {node.truncated_children > 0 && (
            <div className="ml-8 text-[11px] text-zinc-700 py-1">
              + {node.truncated_children} more not shown
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export function ConnectionsExplorer({
  entityId,
  onSelect,
}: {
  entityId: string | undefined;
  onSelect: (entityId: string) => void;
}) {
  const [data, setData] = useState<ExploreResult | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!entityId) {
      setData(null);
      setLoading(false);
      return;
    }

    setLoading(true);

    fetch(`${API_BASE}/entity/${entityId}/explore?depth=2`, { headers: { ...authHeaders() } })
      .then((r) => r.json())
      .then(setData)
      .catch(() => setData({ error: "Couldn't reach NXTDeal's graph explorer." }))
      .finally(() => setLoading(false));
  }, [entityId]);

  if (!entityId) return null;

  return (
    <div className="mb-6">
      <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">
        Explore Connections
      </div>

      {loading ? (
        <div className="text-sm text-zinc-600">Loading connections…</div>
      ) : !data || data.error ? (
        <div className="text-sm text-zinc-600">{data?.error || "No connections found."}</div>
      ) : !data.children || data.children.length === 0 ? (
        <div className="text-sm text-zinc-600">
          Nothing else in the graph is connected to this yet.
        </div>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-lg p-3">
          {data.children.map((child, i) => (
            <NodeRow key={`${child.entity.id}-${i}`} node={child} onSelect={onSelect} depthLevel={0} />
          ))}
          {(data.truncated_children ?? 0) > 0 && (
            <div className="ml-8 text-[11px] text-zinc-700 py-1">
              + {data.truncated_children} more not shown
            </div>
          )}
        </div>
      )}
    </div>
  );
}
