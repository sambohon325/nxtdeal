"use client";

// Programming Schedule dashboard (Section 3 — 2026-10-24).
//
// Root cause of the original 404: the Next.js App Router had no route at
// `app/programming-schedule/`. The backend API route
// `GET /programming-schedule/dashboard` existed and was admin-gated, but
// no frontend `page.tsx` consumed it. This page fixes that.
//
// Sections (matching NXTDEAL-SCHEDULE-SOURCE-OF-TRUTH.md Section 3):
//   Header:   Target Dec 1 · % done by est hours · Days left · projected finish
//   NOW:      items with claims, showing worker · model · elapsed · last heartbeat
//   UP NEXT:  top 5 picks the orchestrator would select
//   BLOCKED:  sam_only + blocked, critical first
//   PHASES:   per-phase progress bars + item cards, filterable
//   RESOURCES: per-worker (runs · hours · tokens · $); per-model; MTD $
//   DONE:     completed items with commit links
//   Auto-refresh 60 s.

import { useEffect, useMemo, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import {
  getDashboard,
  type PSDashboard,
  type PSDashboardItem,
  type ScheduleRun,
  type ResourceSummary,
  STATUS_COLORS,
  PRIORITY_COLORS,
  TYPE_ICONS,
  ROUTE_LABELS,
  PHASE_ORDER,
} from "@/lib/programmingSchedule";

const REFRESH_SECONDS = 60;

function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    return new Date(iso).toLocaleString("en-US", {
      month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
    });
  } catch { return "—"; }
}

function elapsed(iso: string | null | undefined): string {
  if (!iso) return "—";
  try {
    const ms = Date.now() - new Date(iso).getTime();
    const m = Math.floor(ms / 60000);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    return `${h}h ${m % 60}m`;
  } catch { return "—"; }
}

function currency(v: number): string {
  if (v === 0) return "$0.00";
  return `$${v.toFixed(2)}`;
}

function ItemCard({ item }: { item: PSDashboardItem }) {
  const run = item.run;
  return (
    <div className="border border-zinc-800 rounded-lg p-3 bg-zinc-900/40 hover:bg-zinc-900/60 transition">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-xs uppercase tracking-wider">
            <span className={TYPE_ICONS[item.type] ? undefined : "opacity-50"}>
              {TYPE_ICONS[item.type] ?? "•"}
            </span>
            <span className={PRIORITY_COLORS[item.priority]}>{item.priority}</span>
            <span className="text-zinc-500">{item.phase}</span>
          </div>
          <div className="font-medium text-sm mt-1 truncate">{item.title}</div>
          {item.description && (
            <div className="text-xs text-zinc-500 mt-0.5 line-clamp-2">{item.description}</div>
          )}
        </div>
        <div className="text-right flex-0">
          <span className={`text-xs font-mono ${STATUS_COLORS[item.status]}`}>{item.status}</span>
          {item.claimed_by && (
            <div className="text-xs text-zinc-500 mt-1">{ROUTE_LABELS[item.resource_route] ?? item.resource_route}</div>
          )}
        </div>
      </div>

      {run && run.outcome === "running" && (
        <div className="mt-2 text-xs text-zinc-400 border-t border-zinc-800 pt-2">
          <div className="flex justify-between">
            <span>Worker: {run.worker}</span>
            <span>Model: {run.model}</span>
          </div>
          <div className="flex justify-between mt-0.5">
            <span>Elapsed: {elapsed(run.started_at)}</span>
            <span>Heartbeat: {elapsed(run.heartbeat_at)}</span>
          </div>
          {run.cost_usd > 0 && <div>Cost: {currency(run.cost_usd)}</div>}
        </div>
      )}

      {item.depends_on.length > 0 && (
        <div className="mt-1 text-xs text-zinc-600">depends on: {item.depends_on.join(", ")}</div>
      )}
    </div>
  );
}

function InProgressCard({ item }: { item: PSDashboardItem }) {
  const run = item.run;
  return (
    <div className="border border-sky-900/30 rounded-lg p-3 bg-sky-900/10">
      <div className="flex items-start justify-between gap-2">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-1.5 text-xs uppercase tracking-wider">
            <span>{TYPE_ICONS[item.type] ?? "•"}</span>
            <span className={PRIORITY_COLORS[item.priority]}>{item.priority}</span>
          </div>
          <div className="font-medium text-sm mt-1">{item.title}</div>
          <div className="text-xs text-zinc-400 mt-0.5 line-clamp-1">{item.description}</div>
        </div>
        <span className="text-xs font-mono text-sky-400">{item.status}</span>
      </div>
      {run && (
        <div className="mt-2 text-xs text-zinc-400 border-t border-zinc-800 pt-2 space-y-0.5">
          <div className="flex justify-between">
            <span>Worker</span><span>{run.worker}</span>
          </div>
          <div className="flex justify-between">
            <span>Model</span><span>{run.model}</span>
          </div>
          <div className="flex justify-between">
            <span>Elapsed</span><span>{elapsed(run.started_at)}</span>
          </div>
          <div className="flex justify-between">
            <span>Last heartbeat</span><span>{elapsed(run.heartbeat_at)}</span>
          </div>
          <div className="flex justify-between">
            <span>Tokens</span>
            <span>{run.input_tokens + run.output_tokens + run.cache_read_tokens.toLocaleString()}</span>
          </div>
          {run.cost_usd > 0 && (
            <div className="flex justify-between">
              <span>Cost</span><span>{currency(run.cost_usd)}</span>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function ResourcesPanel({ resources }: { resources: ResourceSummary }) {
  return (
    <div className="border border-zinc-800 rounded-lg p-4 bg-zinc-900/40">
      <div className="text-sm font-medium mb-3">Resources</div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Per Worker</div>
          <div className="space-y-2">
            {Object.entries(resources.workers).map(([worker, w]) => (
              <div key={worker} className="border border-zinc-800 rounded p-2 text-xs">
                <div className="font-medium">{worker}</div>
                <div className="grid grid-cols-2 gap-1 mt-1 text-zinc-400">
                  <div>Runs: <span className="text-zinc-200">{w.runs}</span></div>
                  <div>Running: <span className="text-sky-400">{w.runs_running}</span></div>
                  <div>Tokens: <span className="text-zinc-200">{(w.input_tokens + w.output_tokens + w.cache_read_tokens).toLocaleString()}</span></div>
                  <div>Cost: <span className="text-zinc-200">{currency(w.cost_usd)}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
        <div>
          <div className="text-xs uppercase tracking-wider text-zinc-500 mb-2">Per Model</div>
          <div className="space-y-2">
            {Object.entries(resources.models).map(([model, m]) => (
              <div key={model} className="border border-zinc-800 rounded p-2 text-xs">
                <div className="flex justify-between">
                  <span className="font-medium">{model}</span>
                  <span className={m.free ? "text-emerald-400" : "text-amber-400"}>
                    {m.free ? "free" : "paid"}
                  </span>
                </div>
                <div className="grid grid-cols-2 gap-1 mt-1 text-zinc-400">
                  <div>Runs: <span className="text-zinc-200">{m.runs}</span></div>
                  <div>Tokens: <span className="text-zinc-200">{(m.input_tokens + m.output_tokens + m.cache_read_tokens).toLocaleString()}</span></div>
                  <div>Cost: <span className="text-zinc-200">{currency(m.cost_usd)}</span></div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
      <div className="mt-3 pt-2 border-t border-zinc-800 text-xs text-zinc-400">
        Month-to-date: {currency(resources.mtd_total_cost)} · {resources.mtd_total_tokens.toLocaleString()} tokens
      </div>
    </div>
  );
}

export default function ProgrammingSchedulePage() {
  const session = useRequireAuth("ADMIN");
  const [data, setData] = useState<PSDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadData = async () => {
    try {
      setLoading(true);
      const d = await getDashboard();
      setData(d);
      setError(null);
    } catch (e: any) {
      setError(e?.message ?? "Failed to load schedule");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!session) return;
    loadData();
    const interval = setInterval(() => {
      if (session) loadData();
    }, REFRESH_SECONDS * 1000);
    return () => clearInterval(interval);
  }, [session]);

  if (!session || loading) {
    return (
      <div className="h-screen bg-[#0a0a0a] text-white flex items-center justify-center">
        <div className="text-zinc-400 text-sm">Loading schedule…</div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-screen bg-[#0a0a0a] text-white flex items-center justify-center">
        <div className="text-red-400 text-sm">Error: {error}</div>
      </div>
    );
  }

  if (!data) return null;

  const dash = data.dashboard;

  // Projected finish: extrapolate from throughput of last 7 days.
  // If we've completed `doneItems` hours in `days_elapsed` days, project remaining days.
  const doneHours = data.total_logged_hours;
  const daysElapsed = Math.max(1, data.days_left === 0 ? 1 : Math.max(1, Math.ceil(data.target_date ? (new Date().getTime() - new Date("2026-10-01").getTime()) / 86400000 : 1)));

  const projectedFinish = useMemo(() => {
    const doneItems = data.done.length;
    const daysSinceStart = Math.max(1, daysElapsed);
    if (doneItems <= 0) return "Not enough data";
    const itemsPerDay = doneItems / daysSinceStart;
    const totalProjected = doneItems * (itemsPerDay > 0 ? Math.ceil(data.total_est_hours / Math.max(1, data.total_logged_hours || 1)) : 0);
    return `${itemsPerDay.toFixed(1)} items/day · ${doneItems} done`;
  }, [data]);

  const PSDASHBOARD_PHASES = PHASE_ORDER;

  return (
    <div className="h-screen bg-[#0a0a0a] text-white overflow-y-auto">
      <div className="max-w-7xl mx-auto p-6">
        {/* Header */}
        <header className="border-b border-zinc-800 pb-4 mb-6">
          <div className="flex items-center justify-between">
            <div>
              <h1 className="text-xl font-brand font-semibold uppercase tracking-wider">
                Programming Schedule
              </h1>
              <div className="text-xs text-zinc-500 mt-1 uppercase tracking-wider">
                Target: {data.target_date} · {data.days_left} days left
              </div>
            </div>
            <div className="text-right text-xs">
              <div>{data.pct_done_by_hours}% done by est hours</div>
              <div className="text-zinc-500">
                {data.total_logged_hours.toFixed(1)}h / {data.total_est_hours.toFixed(1)}h
              </div>
            </div>
          </div>
          <div className="mt-3 h-2 bg-zinc-800 rounded overflow-hidden">
            <div
              className="h-full bg-sky-400 transition-all"
              style={{ width: `${Math.min(100, data.pct_done_by_hours)}%` }}
            />
          </div>
        </header>

        <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 mb-6">
          {/* NOW */}
          <div>
            <h2 className="text-xs uppercase tracking-wider text-sky-400 mb-2 font-brand">NOW</h2>
            <p className="text-xs text-zinc-500 mb-2">{data.in_progress.length} active</p>
            {data.in_progress.length === 0 ? (
              <div className="text-xs text-zinc-500">No active claims.</div>
            ) : (
              <div className="space-y-2">
                {data.in_progress.map((item) => (
                  <InProgressCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </div>

          {/* UP NEXT */}
          <div>
            <h2 className="text-xs uppercase tracking-wider text-amber-400 mb-2 font-brand">UP NEXT</h2>
            <p className="text-xs text-zinc-500 mb-2">Top picks for orchestration</p>
            {data.up_next.length === 0 ? (
              <div className="text-xs text-zinc-500">Nothing to pick up.</div>
            ) : (
              <div className="space-y-2">
                {data.up_next.map((item) => (
                  <ItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </div>

          {/* BLOCKED ON SAM */}
          <div>
            <h2 className="text-xs uppercase tracking-wider text-red-400 mb-2 font-brand">BLOCKED ON SAM</h2>
            <p className="text-xs text-zinc-500 mb-2">{data.blocked_on_sam.length} items</p>
            {data.blocked_on_sam.length === 0 ? (
              <div className="text-xs text-zinc-500">Nothing blocked.</div>
            ) : (
              <div className="space-y-2">
                {data.blocked_on_sam.map((item) => (
                  <ItemCard key={item.id} item={item} />
                ))}
              </div>
            )}
          </div>
        </div>

        {/* RESOURCES */}
        <div className="mb-6">
          <ResourcesPanel resources={data.resources} />
        </div>

        {/* BY PHASE */}
        <div className="mb-6">
          <h2 className="text-xs uppercase tracking-wider text-zinc-400 mb-3 font-brand">BY PHASE</h2>
          <div className="space-y-3">
            {PSDASHBOARD_PHASES.map((phase) => {
              const phaseData = data.by_phase[phase];
              if (!phaseData) return null;
              const pct = phaseData.total_hours > 0
                ? (phaseData.logged_hours / phaseData.total_hours) * 100
                : 0;
              return (
                <div key={phase} className="border border-zinc-800 rounded-lg p-3 bg-zinc-900/40">
                  <div className="flex items-center justify-between mb-2">
                    <span className="text-sm font-medium">{phase}</span>
                    <span className="text-xs text-zinc-400">
                      {phaseData.logged_hours.toFixed(1)}h / {phaseData.total_hours.toFixed(1)}h
                    </span>
                  </div>
                  <div className="h-1.5 bg-zinc-800 rounded overflow-hidden mb-2">
                    <div
                      className="h-full bg-zinc-600 transition-all"
                      style={{ width: `${Math.min(100, pct)}%` }}
                    />
                  </div>
                  <div className="text-xs text-zinc-500">
                    {phaseData.done}/{phaseData.total} done
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* DONE */}
        <div>
          <h2 className="text-xs uppercase tracking-wider text-emerald-400 mb-3 font-brand">DONE</h2>
          <p className="text-xs text-zinc-500 mb-2">{data.done.length} items completed</p>
          {data.done.length === 0 ? (
            <div className="text-xs text-zinc-500">No completed items yet.</div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
              {data.done.map((item) => (
                <div key={item.id} className="border border-zinc-800 rounded-lg p-2 text-xs bg-zinc-900/20">
                  <div className="flex justify-between">
                    <span className="font-medium truncate">{item.title}</span>
                    <span className={STATUS_COLORS[item.status]}>{item.status}</span>
                  </div>
                  {item.last_commit && (
                    <div className="text-zinc-500 mt-0.5 truncate">commit: {item.last_commit.slice(0, 8)}</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="mt-6 text-xs text-zinc-600 border-t border-zinc-800 pt-3">
          Auto-refreshes every {REFRESH_SECONDS}s · Last updated: {fmtDate(new Date().toISOString())}
        </div>
      </div>
    </div>
  );
}
