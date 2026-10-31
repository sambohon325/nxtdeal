"use client";

// Network's "Forecasts" item (new, 2026-07-18) -- this dealer's own real trend,
// projected forward via a real linear (OLS) fit over actual recorded snapshot
// history, compared against the static SIMULATED peer average to estimate
// whether a real gap is closing, widening, or holding. Deliberately NOT a
// competitive forecast -- peers have no real trend of their own to project.
import { useEffect, useState } from "react";
import {
  getNetworkForecasts,
  type NetworkForecasts,
  type GapProjection,
} from "@/lib/networkTrends";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function fmtValue(value: number | null | undefined, format: string | null | undefined): string {
  if (value === null || value === undefined) return "—";
  if (format === "currency") {
    const sign = value < 0 ? "-" : "";
    return `${sign}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }
  if (format === "percent") return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

const TREND_COLOR: Record<string, string> = {
  closing: "#39C37B",
  widening: "#EE3C25",
  holding: "#8AA0B0",
  unknown: "#8AA0B0",
};

const TREND_LABEL: Record<string, string> = {
  closing: "Gap Closing",
  widening: "Gap Widening",
  holding: "Holding Steady",
  unknown: "Unknown",
};

function ProjectionCard({ theme, p }: { theme: Theme; p: GapProjection }) {
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-3")}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">{p.department}</div>
          <div className="text-sm font-brand font-semibold">{p.label}</div>
        </div>
        <span
          className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full border shrink-0"
          style={{ borderColor: TREND_COLOR[p.gap_trend], color: TREND_COLOR[p.gap_trend] }}
        >
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: TREND_COLOR[p.gap_trend] }} />
          {TREND_LABEL[p.gap_trend] ?? p.gap_trend}
        </span>
      </div>

      <div className="grid grid-cols-3 gap-2 mt-2 text-xs">
        <div>
          <div className="text-zinc-500">Current</div>
          <div className="font-semibold">{fmtValue(p.current_value, p.format)}</div>
        </div>
        <div>
          <div className="text-zinc-500">Projected (+{p.project_days}d)</div>
          <div className="font-semibold">{fmtValue(p.projected_value, p.format)}</div>
        </div>
        <div>
          <div className="text-zinc-500">Peer Avg</div>
          <div className="font-semibold">{fmtValue(p.peer_average, p.format)}</div>
        </div>
      </div>

      <div className="text-xs text-zinc-600 mt-2">{p.note}</div>
    </div>
  );
}

function NotProjectableRow({ theme, p }: { theme: Theme; p: GapProjection }) {
  return (
    <div className={tc(theme, "flex items-center justify-between gap-3 rounded border border-zinc-800 bg-zinc-900/60 px-2.5 py-2", "flex items-center justify-between gap-3 rounded border border-zinc-200 bg-zinc-50 px-2.5 py-2")}>
      <div className="min-w-0">
        <div className="text-xs text-zinc-500">{p.department}</div>
        <div className="text-xs text-zinc-300 truncate">{p.label}</div>
      </div>
      <div className="text-xs text-zinc-600 text-right max-w-[55%]">{p.reason}</div>
    </div>
  );
}

export function NetworkForecastsBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<NetworkForecasts | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getNetworkForecasts()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Network Forecasts."))
      .finally(() => setLoading(false));
  }, []);

  const notProjectable = data ? data.all_projections.filter((p) => !p.projectable) : [];
  const holding = data ? data.all_projections.filter((p) => p.projectable && p.gap_trend === "holding") : [];

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">Forecasts</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          This dealer&apos;s own real trend, projected forward against a fixed, simulated peer target -- not a
          competitive race, since peers have no real trend of their own.
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loading || !data ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
              <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
                <div className="text-xs text-zinc-500">Projectable KPIs</div>
                <div className="text-lg font-semibold">{data.projectable_kpi_count}</div>
              </div>
              <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
                <div className="text-xs text-zinc-500">Not Yet Projectable</div>
                <div className="text-lg font-semibold">{data.not_projectable_kpi_count}</div>
              </div>
              <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
                <div className="text-xs text-zinc-500">Closing</div>
                <div className="text-lg font-semibold text-emerald-400">{data.closing_gaps.length}</div>
              </div>
              <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
                <div className="text-xs text-zinc-500">Widening</div>
                <div className="text-lg font-semibold text-red-400">{data.widening_gaps.length}</div>
              </div>
            </div>

            {data.closing_gaps.length > 0 && (
              <div>
                <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Closing Gaps</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {data.closing_gaps.map((p) => (
                    <ProjectionCard key={`${p.department}-${p.kpi}`} theme={theme} p={p} />
                  ))}
                </div>
              </div>
            )}

            {data.widening_gaps.length > 0 && (
              <div>
                <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Widening Gaps</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {data.widening_gaps.map((p) => (
                    <ProjectionCard key={`${p.department}-${p.kpi}`} theme={theme} p={p} />
                  ))}
                </div>
              </div>
            )}

            {holding.length > 0 && (
              <div>
                <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Holding Steady</div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {holding.map((p) => (
                    <ProjectionCard key={`${p.department}-${p.kpi}`} theme={theme} p={p} />
                  ))}
                </div>
              </div>
            )}

            {notProjectable.length > 0 && (
              <div>
                <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">
                  Not Yet Projectable ({notProjectable.length})
                </div>
                <div className="space-y-1.5">
                  {notProjectable.map((p) => (
                    <NotProjectableRow key={`np-${p.department}-${p.kpi}`} theme={theme} p={p} />
                  ))}
                </div>
              </div>
            )}

            <div className={tc(theme, "text-xs text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-500 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
              {data.basis_notice}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
