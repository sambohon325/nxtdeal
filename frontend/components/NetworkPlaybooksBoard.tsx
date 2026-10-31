"use client";
import { WorkButton } from "./WorkspaceUi";

// Network's "Playbooks" item -- a real curated best-practice library, each
// entry grounded in a real NXTDeal screen/workflow, live-checked against a
// real diagnostic (is_currently_active), and scored against the real
// Workflow Automation rule engine (automation_score).
import { useEffect, useState } from "react";
import {
  getNetworkPlaybooks,
  type NetworkPlaybooks,
  type PlaybookEntry,
} from "@/lib/networkPlaybooks";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const TIER_COLOR: Record<number, string> = {
  0: "#8AA0B0",
  1: "#F4C300",
  2: "#F4C300",
  3: "#39C37B",
};

function AutomationBadge({ p }: { p: PlaybookEntry }) {
  const color = TIER_COLOR[p.automation_score.tier] ?? "#8AA0B0";
  return (
    <span
      className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full border shrink-0"
      style={{ borderColor: color, color }}
      title={p.automation_score.note}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: color }} />
      {p.automation_score.label}
    </span>
  );
}

function PlaybookCard({ theme, p }: { theme: Theme; p: PlaybookEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div
      className={tc(
        theme,
        `relative overflow-hidden rounded-lg border p-3 ${p.is_currently_active ? "border-amber-700/60 bg-brand-charcoal" : "border-zinc-800 bg-brand-charcoal"}`,
        `relative overflow-hidden rounded-lg border p-3 ${p.is_currently_active ? "border-amber-300 bg-white" : "border-zinc-200 bg-white"}`
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">{p.department}</div>
          <div className="text-sm font-brand font-semibold">{p.title}</div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {p.is_currently_active && (
            <span className="text-xs px-1.5 py-0.5 rounded-full border border-amber-500 text-amber-400">
              Active Now
            </span>
          )}
          <AutomationBadge p={p} />
        </div>
      </div>

      <div className="text-xs text-zinc-400 mt-1.5">{p.summary}</div>

      {p.is_currently_active && p.active_finding && (
        <div className={tc(theme, "mt-2 rounded border border-amber-900/40 bg-amber-950/20 p-2", "mt-2 rounded border border-amber-200 bg-amber-50 p-2")}>
          <div className="text-xs uppercase tracking-wide text-amber-500">Currently Active For This Dealer</div>
          <div className="text-xs text-zinc-300 mt-0.5">{p.active_finding.finding}</div>
        </div>
      )}

      <WorkButton type="submit"
        onClick={() => setExpanded((v) => !v)}
        className="text-xs text-zinc-500 mt-2 underline"
      >
        {expanded ? "Hide steps" : "Show steps"}
      </WorkButton>

      {expanded && (
        <ol className="mt-2 space-y-1 list-decimal list-inside">
          {p.steps.map((s, i) => (
            <li key={i} className="text-xs text-zinc-300">{s}</li>
          ))}
        </ol>
      )}
    </div>
  );
}

export function NetworkPlaybooksBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<NetworkPlaybooks | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showAllOnly, setShowAllOnly] = useState(false);

  useEffect(() => {
    getNetworkPlaybooks()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Network Playbooks."))
      .finally(() => setLoading(false));
  }, []);

  const visible = data
    ? showAllOnly
      ? data.library
      : data.library.filter((p) => p.is_currently_active)
    : [];

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">Playbooks</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          A real curated best-practice library -- every entry grounded in a real NXTDeal screen, live-checked
          against your own data, and scored against the real Workflow Automation rule engine.
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loading || !data ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
                <div className="text-xs text-zinc-500">Total Playbooks</div>
                <div className="text-lg font-semibold">{data.playbook_count}</div>
              </div>
              <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
                <div className="text-xs text-zinc-500">Active Now</div>
                <div className="text-lg font-semibold text-amber-400">{data.currently_active_count}</div>
              </div>
              <button
                onClick={() => setShowAllOnly((v) => !v)}
                className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2 text-left", "rounded border border-zinc-200 bg-zinc-50 p-2 text-left")}
              >
                <div className="text-xs text-zinc-500">View</div>
                <div className="text-xs font-medium">{showAllOnly ? "Showing all" : "Active only"} — click to toggle</div>
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {visible.map((p) => (
                <PlaybookCard key={p.key} theme={theme} p={p} />
              ))}
              {visible.length === 0 && (
                <div className="text-xs text-zinc-500 col-span-2">
                  No playbooks are currently active for this dealer -- toggle to &quot;Showing all&quot; to browse
                  the full library as a reference guide.
                </div>
              )}
            </div>

            <div className={tc(theme, "text-xs text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-500 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
              {data.library_note}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
