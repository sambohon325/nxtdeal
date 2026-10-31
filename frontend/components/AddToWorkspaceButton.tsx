"use client";

// Reusable "➕ Workspace" grab affordance (2026-07-23, Workspace grab-all). Sam wants
// every framable piece of data across NXTDeal -- a report table, a detail record, a KPI
// row -- grabbable into the personal Workspace where you build knowledge for you and your
// team. Drop this next to any data: pass a title + the frame (columns/rows for a table,
// or text) and it captures a snapshot to the Workspace board. Same drop-in ergonomics as
// AiAssistButton / ImageLibraryPicker: presentational, owns no page state.

import { useState } from "react";
import { useWorkspaceTools } from "@/lib/workspaceTools";
import { addSnapshotToWorkspace } from "@/lib/workspaceGrab";

type Theme = "dark" | "light";

type Props = {
  title: string;
  sourceLabel?: string;
  sourceContext?: string;
  // Provide EITHER a table (columns + rows) OR text. If both are empty the button is a
  // no-op guard (won't grab an empty frame).
  columns?: string[];
  rows?: Record<string, unknown>[];
  text?: string;
  theme?: Theme;
  className?: string;
  // Override the chip label; defaults to "Workspace".
  label?: string;
};

export default function AddToWorkspaceButton({
  title,
  sourceLabel,
  sourceContext,
  columns,
  rows,
  text,
  theme = "dark",
  className,
  label = "Workspace",
}: Props) {
  const [state, setState] = useState<"idle" | "saving" | "done" | "error">("idle");

  const workspaceTools = useWorkspaceTools();
  if (!workspaceTools) return null;

  const hasTable = Array.isArray(rows) && rows.length > 0;
  const hasText = Boolean(text && text.trim());
  const empty = !hasTable && !hasText;

  async function grab() {
    if (empty || state === "saving") return;
    setState("saving");
    try {
      await addSnapshotToWorkspace({
        title: title || "Captured data",
        source_label: sourceLabel,
        source_context: sourceContext,
        data_kind: hasTable ? "table" : "text",
        columns: hasTable ? columns : undefined,
        rows: hasTable ? rows : undefined,
        text: hasTable ? undefined : text,
      });
      setState("done");
      setTimeout(() => setState("idle"), 2000);
    } catch {
      setState("error");
      setTimeout(() => setState("idle"), 2500);
    }
  }

  const base =
    theme === "dark"
      ? "bg-zinc-800 text-zinc-200 hover:bg-zinc-700 border-zinc-700"
      : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 border-zinc-200";

  return (
    <button
      type="button"
      onClick={grab}
      disabled={empty || state === "saving"}
      title={empty ? "Nothing to add yet" : "Add this to your Workspace"}
      className={`inline-flex items-center gap-1 text-[10px] font-medium px-1.5 py-0.5 rounded border disabled:opacity-40 ${base} ${className ?? ""}`}
    >
      {state === "done" ? (
        <span className="text-emerald-400">✓ Added</span>
      ) : state === "error" ? (
        <span className="text-red-400">Failed</span>
      ) : (
        <>
          <span aria-hidden>➕</span> {state === "saving" ? "Adding…" : label}
        </>
      )}
    </button>
  );
}
