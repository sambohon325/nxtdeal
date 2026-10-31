"use client";
import { WorkField } from "./WorkField";

// Collapsible "Communications" sidebar block (session 28 -- Sam: "it needs to be in a
// collapsable with + option to expand it (to look like it does now)"). Replaces the
// static #sales/#service/#managers + Sarah/John chips that used to be hardcoded in
// /workspace only -- now real, graph-native channels/DMs (core/messaging.py), rolled out
// to all four authenticated pages via the shared lib/useMessaging.ts hook. Clicking a
// channel or a person opens (or focuses) that thread in ChatDock, which renders right
// alongside this same `messaging` instance so unread counts / open state always match.
//
// Session 72 additions, both Sam asks in the same message:
//   1. "on the direct messages (and #Departments) there should be a search function so
//      you can look for other employees to begin an conversation" -- a search box that
//      filters channels by name and the full employee directory (not just people
//      you've already messaged) by name/id/role.
//   2. "You can drag and rop the knowledge piece into the Direct messages, or
//      communications, where it will ask if you want to change the access so that you
//      know that its going to be accessible." -- channel/DM buttons are now real drop
//      targets for a dragged Knowledge pin (components/KnowledgeSidebar.tsx). Dropping
//      shows a confirmation naming exactly who gains access before anything changes:
//      dropping on a channel widens (or creates) that pin's Shared Knowledge visibility
//      to the channel's real roles (core/messaging.py's CHANNEL_DEFS, not a guess), then
//      opens that thread with the pin pre-attached; dropping on a DM just opens that
//      thread with the pin attached (a DM's own 1:1 privacy already limits exposure, so
//      there's no sharing-visibility change to make -- the confirmation there is purely
//      "this becomes visible to this one person once you send it").

import { useState, type DragEvent } from "react";
import type { Messaging } from "@/lib/useMessaging";
import { createSharedPin, widenSharedPinAccess, ROLE_LABELS } from "@/lib/sharedKnowledge";
import type { PinKind } from "@/lib/pins";
import { CustomerCommsPanel, CommsWorkspaceMount } from "@/components/CustomerCommsPanel";

// Angled brand-color "flag" accent (matching components/DepartmentWorkflowButtons.tsx's
// job-workflow buttons on the right side of the page -- session 72, Sam: "can we make
// the buttons on the left look like the ones on the right - so add the slant / right
// font?") in place of the old plain border-l-2 + font-brand uppercase labels instead of
// the previous plain-weight text.
function FlagAccent({ color }: { color: string }) {
  return (
    <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
      style={{ background: color, clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
    />
  );
}

// The JSON payload components/KnowledgeSidebar.tsx's draggable pin cards set --
// `sharedPinId`/`currentRoles`/`currentVisibility` are only present when dragging from
// the "Shared Knowledge" tab (see that file's session-72 changes); a "My Knowledge" pin
// drag carries just kind/label/refId, same shape this always had.
type DraggedPin = {
  kind: PinKind;
  label: string;
  refId?: string;
  sharedPinId?: string;
  currentRoles?: string[];
  currentVisibility?: "all" | "roles";
};

type DropTarget =
  | { kind: "channel"; key: string; label: string; roles: string[] }
  | { kind: "dm"; key: string; label: string };

export function CommunicationsPanel({ messaging }: { messaging: Messaging }) {
  const [collapsed, setCollapsed] = useState(false);
  // Split (like the Knowledge panel above): Company = internal Slack-style channels/DMs;
  // Customers = phone + text with real customers (CustomerCommsPanel). Sam's 2026-07-24 spec.
  const [mode, setMode] = useState<"company" | "customers">("company");
  const [query, setQuery] = useState("");
  const [dragOverKey, setDragOverKey] = useState<string | null>(null);
  const [pending, setPending] = useState<{ target: DropTarget; pin: DraggedPin } | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [confirmError, setConfirmError] = useState<string | null>(null);

  const totalUnread = Object.values(messaging.unread).reduce((sum, n) => sum + n, 0);

  const q = query.trim().toLowerCase();
  const filteredChannels = q
    ? messaging.channels.filter((c) => c.name.toLowerCase().includes(q))
    : messaging.channels;

  const directoryMatches = q
    ? messaging.directory.filter(
        (d) =>
          d.employee_id !== messaging.myEmployeeId &&
          (
            (d.name || "").toLowerCase().includes(q) ||
            d.employee_id.toLowerCase().includes(q) ||
            d.role.toLowerCase().includes(q)
          )
      )
    : [];

  function readDragPayload(e: DragEvent): DraggedPin | null {
    const raw = e.dataTransfer.getData("application/json");
    if (!raw) return null;
    try {
      return JSON.parse(raw) as DraggedPin;
    } catch {
      return null;
    }
  }

  function handleDrop(e: DragEvent, target: DropTarget) {
    e.preventDefault();
    setDragOverKey(null);

    const pin = readDragPayload(e);
    if (!pin) return;

    setConfirmError(null);
    setPending({ target, pin });
  }

  async function confirmShare() {
    if (!pending) return;

    const { target, pin } = pending;
    setConfirming(true);
    setConfirmError(null);

    try {
      if (target.kind === "channel") {
        if (pin.sharedPinId) {
          await widenSharedPinAccess(pin.sharedPinId, { addRoles: target.roles });
        } else {
          await createSharedPin({
            kind: pin.kind,
            ref_id: pin.refId ?? null,
            label: pin.label,
            visibility: "roles",
            roles: target.roles,
          });
        }
        messaging.openThread("channel", target.key, target.label, {
          kind: pin.kind,
          label: pin.label,
          refId: pin.refId,
        });
      } else {
        messaging.openThread("dm", target.key, target.label, {
          kind: pin.kind,
          label: pin.label,
          refId: pin.refId,
        });
      }

      setPending(null);
    } catch (err) {
      setConfirmError(err instanceof Error ? err.message : "Unable to share.");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div>
      {/* The call/text workspace lives here (mounted once, on every page) and is driven by the
          global comms store, so any dashboard's Call/Text button can open it. */}
      <CommsWorkspaceMount />
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="w-full flex items-center justify-between text-xs uppercase tracking-wider text-zinc-500 mb-3 hover:text-white transition"
      >
        <span>
          Communications
          {totalUnread > 0 && <span className="ml-2 text-[#EE3C25]">({totalUnread})</span>}
        </span>
        <span>{collapsed ? "+" : "−"}</span>
      </button>

      {!collapsed && (
        <div className="space-y-2 text-sm">
          <div className="mb-3 flex gap-1 rounded-lg bg-zinc-950 p-0.5">
            {(["company", "customers"] as const).map((m) => (
              <button
                key={m}
                onClick={() => setMode(m)}
                className={
                  mode === m
                    ? "flex-1 rounded-md bg-zinc-800 py-1 text-[11px] font-brand uppercase tracking-wide text-white transition"
                    : "flex-1 rounded-md py-1 text-[11px] font-brand uppercase tracking-wide text-zinc-500 hover:text-white transition"
                }
              >
                {m === "company" ? "Company" : "Customers"}
              </button>
            ))}
          </div>

          {mode === "customers" ? (
            <CustomerCommsPanel />
          ) : (
          <>
          <WorkField label="Search channels or people"><input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search channels or people..."
            className="w-full h-8 px-3 mb-4 text-xs rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none focus:border-brand-teal"
          /></WorkField>

          {filteredChannels.length === 0 && !q && (
            <div className="text-xs text-zinc-600">No channels available for your role.</div>
          )}

          {filteredChannels.map((channel) => {
            const key = `channel:${channel.key}`;
            const unread = messaging.unread[key];
            const dragKey = `channel-${channel.key}`;

            return (
              <button
                key={channel.key}
                onClick={() => messaging.openThread("channel", channel.key, `#${channel.name}`)}
                onDragOver={(e) => {
                  e.preventDefault();
                  setDragOverKey(dragKey);
                }}
                onDragLeave={() => setDragOverKey((prev) => (prev === dragKey ? null : prev))}
                onDrop={(e) =>
                  handleDrop(e, { kind: "channel", key: channel.key, label: `#${channel.name}`, roles: channel.roles })
                }
                className={
                  "relative w-full text-left bg-zinc-900 rounded-lg pl-4 pr-3 py-3 overflow-hidden border transition flex items-center justify-between " +
                  (dragOverKey === dragKey ? "border-brand-teal bg-brand-teal/10" : "border-transparent hover:border-brand-teal")
                }
              >
                <FlagAccent color="#2B68AB" />
                <span className="font-brand font-semibold uppercase tracking-wide text-[11px]">#{channel.name}</span>
                {unread ? <span className="text-[#EE3C25] text-xs">{unread}</span> : null}
              </button>
            );
          })}

          {q ? (
            <>
              <div className="pt-2 text-zinc-500">People</div>

              {directoryMatches.length === 0 && (
                <div className="text-xs text-zinc-600">No employees match &quot;{query}&quot;.</div>
              )}

              {directoryMatches.map((entry) => {
                const label = entry.name || entry.employee_id;
                const key = `dm:${entry.employee_id}`;
                const unread = messaging.unread[key];
                const dragKey = `dm-${entry.employee_id}`;

                return (
                  <button
                    key={entry.employee_id}
                    onClick={() => messaging.openThread("dm", entry.employee_id, label)}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragOverKey(dragKey);
                    }}
                    onDragLeave={() => setDragOverKey((prev) => (prev === dragKey ? null : prev))}
                    onDrop={(e) => handleDrop(e, { kind: "dm", key: entry.employee_id, label })}
                    className={
                      "relative w-full text-left bg-zinc-900 rounded-lg pl-4 pr-3 py-3 overflow-hidden border transition flex items-center justify-between " +
                      (dragOverKey === dragKey ? "border-brand-teal bg-brand-teal/10" : "border-transparent hover:border-brand-teal")
                    }
                  >
                    <FlagAccent color="#3FBCC4" />
                    <span className="font-brand font-semibold uppercase tracking-wide text-[11px] truncate">
                      {label}
                      <span className="ml-2 text-zinc-500 normal-case font-normal">{entry.role}</span>
                    </span>
                    {unread ? <span className="text-[#EE3C25] text-xs shrink-0">{unread}</span> : null}
                  </button>
                );
              })}
            </>
          ) : (
            <>
              <div className="pt-2 text-zinc-500">Direct Messages</div>

              {messaging.conversations.length === 0 && (
                <div className="text-xs text-zinc-600">No conversations yet.</div>
              )}

              {messaging.conversations.map((conversation) => {
                const key = `dm:${conversation.employee_id}`;
                const unread = messaging.unread[key];
                const entry = messaging.directory.find((d) => d.employee_id === conversation.employee_id);
                const label = entry?.name || conversation.employee_id;
                const dragKey = `dm-${conversation.employee_id}`;

                return (
                  <button
                    key={conversation.employee_id}
                    onClick={() => messaging.openThread("dm", conversation.employee_id, label)}
                    onDragOver={(e) => {
                      e.preventDefault();
                      setDragOverKey(dragKey);
                    }}
                    onDragLeave={() => setDragOverKey((prev) => (prev === dragKey ? null : prev))}
                    onDrop={(e) => handleDrop(e, { kind: "dm", key: conversation.employee_id, label })}
                    className={
                      "relative w-full text-left bg-zinc-900 rounded-lg pl-4 pr-3 py-3 overflow-hidden border transition flex items-center justify-between " +
                      (dragOverKey === dragKey ? "border-brand-teal bg-brand-teal/10" : "border-transparent hover:border-brand-teal")
                    }
                  >
                    <FlagAccent color="#2B68AB" />
                    <span className="font-brand font-semibold uppercase tracking-wide text-[11px] truncate">{label}</span>
                    {unread ? <span className="text-[#EE3C25] text-xs shrink-0">{unread}</span> : null}
                  </button>
                );
              })}
            </>
          )}
          </>
          )}
        </div>
      )}

      {pending && (
        <div className="fixed inset-0 z-[200] flex items-center justify-center bg-black/60 p-4">
          <div className="bg-zinc-900 border border-zinc-700 rounded-xl p-5 w-full max-w-sm text-sm">
            <div className="font-brand font-bold uppercase tracking-wide text-xs text-zinc-400 mb-3">
              Change access?
            </div>

            {pending.target.kind === "channel" ? (
              <p className="text-zinc-300 mb-3">
                Sharing <span className="text-white font-medium">&quot;{pending.pin.label}&quot;</span> in{" "}
                <span className="text-white font-medium">{pending.target.label}</span> will make it visible to
                everyone there ({pending.target.roles.map((r) => ROLE_LABELS[r] ?? r).join(", ")}) via Shared
                Knowledge.
              </p>
            ) : (
              <p className="text-zinc-300 mb-3">
                Attaching <span className="text-white font-medium">&quot;{pending.pin.label}&quot;</span> here will
                make it accessible to <span className="text-white font-medium">{pending.target.label}</span> once
                you send it.
              </p>
            )}

            {confirmError && <div className="text-xs text-[#EE3C25] mb-3">{confirmError}</div>}

            <div className="flex items-center justify-end gap-3">
              <button
                onClick={() => setPending(null)}
                className="text-xs text-zinc-500 hover:text-white transition"
              >
                Cancel
              </button>
              <button
                onClick={confirmShare}
                disabled={confirming}
                className="text-xs px-4 py-2 brand-cta disabled:opacity-50"
              >
                {confirming ? "Sharing..." : "Share & attach"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
