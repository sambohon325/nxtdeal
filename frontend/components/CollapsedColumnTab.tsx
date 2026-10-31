"use client";

// Generic collapsed-column reopen tab (2026-07-19, Sam: "I would like there to be push
// in and pull out tabs on the right, left, and ai chat bar so that in theory, someone
// could fully expand the sub menu dash to as full screen as possible... Lets add alert
// icons (think red app notifications on iOS) to let people know that things are
// happening on the closed areas"). A generalized sibling of
// components/MenuDashPanel.tsx's own WorkspaceCollapsedTab (session 60, right-column
// -only, no alert dot, reopens the Top Menu Dash's own occupied Workspace slot) --
// built as its own component rather than widening that one, since this one needs a
// configurable border side (a left-hand column borders on its right edge, a right-hand
// column borders on its left edge) and a caller-supplied label/icon instead of the
// fixed "Workspace ▤" pairing. Used for the Knowledge/Communications sidebar's manual
// collapse in app/workspace/page.tsx; the right Workspace panel keeps using
// WorkspaceCollapsedTab directly (it already supports the visualization drag-and-drop
// drop target this one doesn't need to duplicate), and the chat column uses the
// CollapsedChatBar sibling below instead (chat collapses to the bottom, not a side).
import type { ReactNode } from "react";

export function CollapsedColumnTab({
  side,
  label,
  icon = "▤",
  alert = false,
  onReopen,
}: {
  // Which edge of the remaining content this tab sits against -- "left" borders on its
  // own right edge (it's to the left of what's still showing), "right" borders on its
  // own left edge (it's to the right of what's still showing).
  side: "left" | "right";
  label: string;
  // A brand-styled element (e.g. the same angled BrandAngles square used elsewhere for
  // this section's own icon) reads far thinner/on-brand than an emoji glyph -- kept as
  // ReactNode rather than string so a caller can pass either.
  icon?: ReactNode;
  alert?: boolean;
  onReopen: () => void;
}) {
  return (
    <button
      onClick={onReopen}
      title={alert ? `Reopen ${label} -- new activity` : `Reopen ${label}`}
      className={
        side === "left"
          ? "relative w-10 shrink-0 flex flex-col items-center justify-center gap-2 border-r border-zinc-900 bg-zinc-950 hover:bg-zinc-900 transition text-zinc-500 hover:text-white print:hidden"
          : "relative w-10 shrink-0 flex flex-col items-center justify-center gap-2 border-l border-zinc-900 bg-zinc-950 hover:bg-zinc-900 transition text-zinc-500 hover:text-white print:hidden"
      }
    >
      {alert && (
        <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-red-500 ring-2 ring-zinc-950 animate-pulse" />
      )}
      <span className="flex items-center justify-center h-3.5 leading-none">{icon}</span>
      <span
        className="text-[10px] uppercase tracking-wider"
        style={{ writingMode: "vertical-rl" }}
      >
        {label}
      </span>
    </button>
  );
}

// Chat's own collapse target (2026-07-19, Sam: "chat (middle) needs to collapse down to
// the bottom with the chat input bar") -- deliberately NOT a CollapsedColumnTab: chat
// sits in the MIDDLE column, and app/workspace/page.tsx's actual message input lives in
// a separate <footer> below <main> that's already always rendered regardless of this
// state, so "collapsing to the bottom" here just means the transcript/header tucks away
// and this bar sinks to the bottom of the chat column's own flex-1 slot, sitting flush
// with that always-visible input bar -- not a thin vertical strip pinned to a side like
// the Knowledge/Workspace columns use, which would visually orphan it from the input.
export function CollapsedChatBar({ alert = false, onReopen }: { alert?: boolean; onReopen: () => void }) {
  return (
    <div className="flex-1 h-full flex flex-col justify-end print:hidden">
      <button
        onClick={onReopen}
        title={alert ? "Reopen chat -- new activity" : "Reopen chat"}
        className="relative w-full flex items-center justify-center gap-2 h-10 border-t border-zinc-900 bg-zinc-950 hover:bg-zinc-900 transition text-zinc-500 hover:text-white"
      >
        {alert && (
          <span className="absolute top-1.5 right-3 w-2 h-2 rounded-full bg-red-500 ring-2 ring-zinc-950 animate-pulse" />
        )}
        <span className="text-sm leading-none">▲</span>
        <span className="text-[10px] font-semibold uppercase tracking-wider">Reopen Chat</span>
      </button>
    </div>
  );
}
