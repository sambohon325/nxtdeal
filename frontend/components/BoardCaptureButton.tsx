"use client";

// Board-level "Add view to Workspace" control (2026-07-23, Workspace grab-all rollout).
// Mounted ONCE in MenuDashPanel over every board (generic + bespoke). On open it scrapes
// the rendered board DOM (lib/captureBoardFrames.ts) for its KPI tiles + tables and lets
// the user grab any of them into their Workspace as a snapshot -- so every dash across
// the platform is grabbable without wiring a button into each of the ~93 board components.

import { useEffect, useRef, useState } from "react";
import { captureBoardFrames, type CapturedFrame } from "@/lib/captureBoardFrames";
import { addSnapshotToWorkspace } from "@/lib/workspaceGrab";

type Theme = "dark" | "light";

type Props = {
  // Lazily resolves the board's rendered container element (scraped on open).
  getEl: () => HTMLElement | null;
  title: string;
  sourceLabel?: string;
  theme?: Theme;
  // Open the menu upward (for a bottom-anchored placement).
  openUp?: boolean;
};

export default function BoardCaptureButton({ getEl, title, sourceLabel, theme = "dark", openUp = false }: Props) {
  const [open, setOpen] = useState(false);
  const [frames, setFrames] = useState<CapturedFrame[]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [doneKey, setDoneKey] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function toggle() {
    if (open) {
      setOpen(false);
      return;
    }
    setError(null);
    setDoneKey(null);
    setFrames(captureBoardFrames(getEl()));
    setOpen(true);
  }

  async function grab(f: CapturedFrame) {
    setBusyKey(f.key);
    setError(null);
    try {
      await addSnapshotToWorkspace({
        title: `${title} — ${f.title}`,
        source_label: sourceLabel,
        data_kind: "table",
        columns: f.columns,
        rows: f.rows,
      });
      setDoneKey(f.key);
      setTimeout(() => setDoneKey(null), 1500);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to add to workspace.");
    } finally {
      setBusyKey(null);
    }
  }

  const panelCls =
    theme === "dark"
      ? "border-zinc-700 bg-brand-charcoal text-zinc-200"
      : "border-zinc-200 bg-white text-zinc-800";
  const chip =
    theme === "dark"
      ? "bg-zinc-800/90 text-zinc-200 hover:bg-zinc-700 border-zinc-700"
      : "bg-white/90 text-zinc-700 hover:bg-zinc-100 border-zinc-300";

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={toggle}
        title="Add this view to your Workspace"
        className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded-md border shadow-sm backdrop-blur ${chip}`}
      >
        <span aria-hidden>➕</span> Workspace
      </button>

      {open && (
        <div className={`absolute right-0 z-40 w-64 rounded-lg border shadow-xl p-2 ${openUp ? "bottom-full mb-1" : "mt-1"} ${panelCls}`}>
          <div className="text-[10px] uppercase tracking-wide text-zinc-500 px-1 pb-1">Add to Workspace</div>
          {frames.length === 0 ? (
            <div className="text-[11px] text-zinc-500 px-1 py-2">
              No grabbable data detected on this view. Tables and KPI tiles can be captured.
            </div>
          ) : (
            <div className="space-y-1">
              {frames.map((f) => (
                <button
                  key={f.key}
                  onClick={() => grab(f)}
                  disabled={busyKey === f.key}
                  className={`w-full flex items-center justify-between text-left text-[11px] px-2 py-1.5 rounded border disabled:opacity-50 ${chip}`}
                >
                  <span className="truncate">
                    {f.title} <span className="text-zinc-500">· {f.rows.length} row{f.rows.length === 1 ? "" : "s"}</span>
                  </span>
                  {doneKey === f.key ? (
                    <span className="text-emerald-400 shrink-0 ml-2">✓</span>
                  ) : busyKey === f.key ? (
                    <span className="text-zinc-500 shrink-0 ml-2">…</span>
                  ) : null}
                </button>
              ))}
            </div>
          )}
          {error && <div className="text-[11px] text-red-400 px-1 pt-1">{error}</div>}
        </div>
      )}
    </div>
  );
}
