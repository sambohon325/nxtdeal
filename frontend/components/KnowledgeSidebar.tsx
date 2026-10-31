"use client";
import { WorkField } from "./WorkField";

// Shared "Knowledge" sidebar — pinned results, grouped by tag (BUILD_QUEUE.md's
// "Chat-First Admin + Pinned Knowledge" entry, session 26, tags added session 27). Per
// Sam: "in the knowledge section we'll build in a tag system so they can organize
// their chats better so it doesn't just become a wall of bars. They also need to be
// able to delete them." Used identically across /admin, /workspace, /readiness, and
// /network — one component, one behavior, everywhere ("all of NXTDeal needs to
// function with the same ideology").
//
// New pins land under DEFAULT_TAG ("General") with zero extra friction at pin-time;
// organizing happens after the fact by clicking a pin's ✎ to retag it — pin first,
// organize later, rather than interrupting the pin action with a required prompt.
//
// Session 72: split into "My Knowledge" (this original, still purely browser-local via
// lib/pins.ts) and "Shared Knowledge" (lib/sharedKnowledge.ts's backend-persisted
// KnowledgePin, visible to whoever it was shared with) -- Sam: "id like there to be a
// regular knowledge and a shared knowledge... it'll be placed on the same line, and
// you can toggle between the two." Both tabs render the same card style; only their
// data source, permissions, and drag payload differ.

import { useEffect, useState } from "react";
import type { Pin } from "@/lib/pins";
import { DEFAULT_TAG } from "@/lib/pins";
import { getSession } from "@/lib/auth";
import {
  fetchSharedPins,
  retagSharedPin,
  deleteSharedPin,
  ROLE_LABELS,
  type SharedPin,
} from "@/lib/sharedKnowledge";

type CardItem = {
  id: string;
  label: string;
  tag: string;
  // What onDragStart puts on the wire -- components/CommunicationsPanel.tsx reads this
  // same shape to decide whether a channel/DM drop needs to CREATE a new shared pin or
  // WIDEN an existing one's roles.
  dragPayload: Record<string, unknown>;
  canManage: boolean;
  subtitle?: string;
};

function CardList({
  items,
  grouped,
  editingId,
  editValue,
  onStartEdit,
  onEditChange,
  onSaveEdit,
  onCancelEdit,
  onOpen,
  onDelete,
}: {
  items: CardItem[];
  grouped: Record<string, CardItem[]>;
  editingId: string | null;
  editValue: string;
  onStartEdit: (item: CardItem) => void;
  onEditChange: (value: string) => void;
  onSaveEdit: (id: string) => void;
  onCancelEdit: () => void;
  onOpen: (id: string) => void;
  onDelete: (id: string) => void;
}) {
  const [collapsedTags, setCollapsedTags] = useState<Set<string>>(new Set());

  if (items.length === 0) return null;

  const tags = Object.keys(grouped).sort((a, b) => {
    if (a === DEFAULT_TAG) return -1;
    if (b === DEFAULT_TAG) return 1;
    return a.localeCompare(b);
  });

  function toggleTag(tag: string) {
    setCollapsedTags((prev) => {
      const next = new Set(prev);
      if (next.has(tag)) next.delete(tag);
      else next.add(tag);
      return next;
    });
  }

  return (
    <div className="space-y-4">
      {tags.map((tag) => {
        const isCollapsed = collapsedTags.has(tag);

        return (
          <div key={tag}>
            <button
              onClick={() => toggleTag(tag)}
              className="w-full flex items-center justify-between text-xs uppercase tracking-wider text-zinc-500 mb-2 hover:text-white transition"
            >
              <span>
                {tag} ({grouped[tag].length})
              </span>
              <span>{isCollapsed ? "+" : "−"}</span>
            </button>

            {!isCollapsed && (
              <div className="space-y-2 text-sm mb-2">
                {grouped[tag].map((item) => (
                  <div
                    key={item.id}
                    draggable
                    onDragStart={(e) => {
                      // Session 28: "drag it from knowledge into the conversation."
                      // CommunicationsPanel.tsx / ChatDock.tsx both read this same
                      // "application/json" payload.
                      e.dataTransfer.setData("application/json", JSON.stringify(item.dragPayload));
                      e.dataTransfer.effectAllowed = "copy";
                    }}
                    className="group relative bg-zinc-900 pl-4 pr-3 py-3 rounded-lg overflow-hidden cursor-grab active:cursor-grabbing"
                  >
                    {/* Angled brand-color "flag" accent (matching
                        components/DepartmentWorkflowButtons.tsx's job-workflow buttons
                        on the right side -- session 72) in place of the old plain
                        border-l-2. */}
                    <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
                      style={{ background: "#3FBCC4", clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
                    />

                    {editingId === item.id ? (
                      <div className="flex items-center gap-1">
                        <WorkField label="Tag name"><input
                          value={editValue}
                          onChange={(e) => onEditChange(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") onSaveEdit(item.id);
                            if (e.key === "Escape") onCancelEdit();
                          }}
                          autoFocus
                          placeholder="Tag name"
                          className="flex-1 h-7 px-2 text-xs rounded bg-zinc-950 border border-zinc-800"
                        /></WorkField>
                        <button
                          onClick={() => onSaveEdit(item.id)}
                          className="text-xs text-[#3FBCC4] hover:text-white transition shrink-0"
                          title="Save tag"
                        >
                          ✓
                        </button>
                      </div>
                    ) : (
                      <div className="flex items-center justify-between gap-2">
                        <button
                          onClick={() => onOpen(item.id)}
                          className="flex-1 text-left truncate min-w-0"
                          title={item.label}
                        >
                          <span className="block font-brand font-semibold uppercase tracking-wide text-[11px] hover:text-[#3FBCC4] transition truncate">
                            {item.label}
                          </span>
                          {item.subtitle && (
                            <span className="block text-[10px] text-zinc-500 normal-case truncate">
                              {item.subtitle}
                            </span>
                          )}
                        </button>

                        {item.canManage && (
                          <div className="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition shrink-0">
                            <button
                              onClick={() => onStartEdit(item)}
                              className="text-zinc-600 hover:text-white text-xs"
                              title="Change tag"
                            >
                              ✎
                            </button>
                            <button
                              onClick={() => onDelete(item.id)}
                              className="text-zinc-600 hover:text-[#EE3C25] text-xs"
                              title="Delete"
                            >
                              ✕
                            </button>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function KnowledgeSidebar({
  pins,
  onOpen,
  onDelete,
  onRetag,
}: {
  pins: Pin[];
  onOpen: (pin: Pin) => void;
  onDelete: (id: string) => void;
  onRetag: (id: string, tag: string) => void;
}) {
  const [tab, setTab] = useState<"mine" | "shared">("mine");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editValue, setEditValue] = useState("");

  const [sharedPins, setSharedPins] = useState<SharedPin[]>([]);
  const [sharedLoading, setSharedLoading] = useState(false);
  const [sharedError, setSharedError] = useState<string | null>(null);

  const session = getSession();

  useEffect(() => {
    if (tab !== "shared") return;

    let cancelled = false;
    setSharedLoading(true);
    setSharedError(null);

    fetchSharedPins()
      .then((data) => {
        if (!cancelled) setSharedPins(data);
      })
      .catch((err) => {
        if (!cancelled) setSharedError(err instanceof Error ? err.message : "Unable to load Shared Knowledge.");
      })
      .finally(() => {
        if (!cancelled) setSharedLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [tab]);

  function startEditing(id: string, currentTag: string) {
    setEditingId(id);
    setEditValue(currentTag || DEFAULT_TAG);
  }

  function saveEditing(id: string) {
    if (tab === "mine") {
      onRetag(id, editValue);
    } else {
      const tag = editValue.trim() || DEFAULT_TAG;
      retagSharedPin(id, tag)
        .then((updated) => {
          setSharedPins((prev) => prev.map((p) => (p.id === id ? updated : p)));
        })
        .catch((err) => setSharedError(err instanceof Error ? err.message : "Unable to retag."));
    }
    setEditingId(null);
  }

  function handleOpen(id: string) {
    if (tab === "mine") {
      const pin = pins.find((p) => p.id === id);
      if (pin) onOpen(pin);
    } else {
      const shared = sharedPins.find((p) => p.id === id);
      if (shared) {
        onOpen({
          id: shared.id,
          label: shared.label,
          kind: shared.kind,
          refId: shared.ref_id ?? undefined,
          tag: shared.tag,
          pinnedAt: shared.shared_at,
        });
      }
    }
  }

  function handleDelete(id: string) {
    if (tab === "mine") {
      onDelete(id);
    } else {
      deleteSharedPin(id)
        .then(() => setSharedPins((prev) => prev.filter((p) => p.id !== id)))
        .catch((err) => setSharedError(err instanceof Error ? err.message : "Unable to remove."));
    }
  }

  const mineItems: CardItem[] = pins.map((pin) => ({
    id: pin.id,
    label: pin.label,
    tag: pin.tag || DEFAULT_TAG,
    dragPayload: { kind: pin.kind, label: pin.label, refId: pin.refId },
    canManage: true,
  }));

  const sharedItems: CardItem[] = sharedPins.map((sp) => ({
    id: sp.id,
    label: sp.label,
    tag: sp.tag || DEFAULT_TAG,
    subtitle:
      (sp.owner_employee_id === session?.employeeId ? "Shared by you" : sp.owner_name ? `Shared by ${sp.owner_name}` : "Shared") +
      " · " +
      (sp.visibility === "all" ? "Everyone" : sp.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")),
    dragPayload: {
      kind: sp.kind,
      label: sp.label,
      refId: sp.ref_id ?? undefined,
      sharedPinId: sp.id,
      currentRoles: sp.roles,
      currentVisibility: sp.visibility,
    },
    canManage: session?.role === "ADMIN" || sp.owner_employee_id === session?.employeeId,
  }));

  const activeItems = tab === "mine" ? mineItems : sharedItems;

  const grouped: Record<string, CardItem[]> = {};
  for (const item of activeItems) {
    (grouped[item.tag] ??= []).push(item);
  }

  return (
    <div>
      {/* "on the same line, and you can toggle between the two" -- session 72. */}
      <div className="flex items-center gap-4 mb-3 font-brand text-xs font-bold uppercase tracking-wide">
        <button
          onClick={() => setTab("mine")}
          className={tab === "mine" ? "text-brand-teal" : "text-zinc-500 hover:text-white transition"}
        >
          My Knowledge
        </button>
        <button
          onClick={() => setTab("shared")}
          className={tab === "shared" ? "text-brand-teal" : "text-zinc-500 hover:text-white transition"}
        >
          Shared Knowledge
        </button>
      </div>

      {tab === "mine" && pins.length === 0 && (
        <div className="text-sm text-zinc-600">
          Nothing pinned yet. Ask NXTDeal for something, then pin it from the workspace
          panel to keep a shortcut back to it here.
        </div>
      )}

      {tab === "shared" && sharedLoading && (
        <div className="text-sm text-zinc-600">Loading Shared Knowledge…</div>
      )}

      {tab === "shared" && sharedError && (
        <div className="text-xs text-[#EE3C25] mb-2">{sharedError}</div>
      )}

      {tab === "shared" && !sharedLoading && sharedPins.length === 0 && !sharedError && (
        <div className="text-sm text-zinc-600">
          Nothing shared with you yet. When you pin something, choose "Share with
          department(s)..." instead of "Only me" to put it here for others.
        </div>
      )}

      <CardList
        items={activeItems}
        grouped={grouped}
        editingId={editingId}
        editValue={editValue}
        onStartEdit={(item) => startEditing(item.id, item.tag)}
        onEditChange={setEditValue}
        onSaveEdit={saveEditing}
        onCancelEdit={() => setEditingId(null)}
        onOpen={handleOpen}
        onDelete={handleDelete}
      />
    </div>
  );
}
