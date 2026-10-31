"use client";

// Network's "Gap Analysis" item -- enriched (Intelligence Network reframe,
// slice 3) with Root Cause Analysis (real, threshold-based diagnostics off
// already-built engines elsewhere in this codebase, never a fabricated
// plausible-sounding cause) and Revenue Impact (core/network_opportunity_
// value.py's exact dollar-conversion formulas, reused verbatim). This slice
// also FIXED a previously-flagged bug: direction/severity now respect each
// KPI's real higher-is-better/lower-is-better semantic -- the bhph
// department's 3 lower-is-better rate KPIs (delinquency/repo/charge-off) are
// no longer mislabeled as an opportunity when this dealer is already ahead of
// peers on them.
import { useEffect, useState } from "react";
import {
  getNetworkGapAnalysis,
  type NetworkGapAnalysis,
  type GapEntry,
  type GapSeverity,
} from "@/lib/networkGapAnalysis";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function fmtCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtValue(value: number | null | undefined, format: string | null): string {
  if (value === null || value === undefined) return "—";
  if (format === "currency") return fmtCurrency(value);
  if (format === "percent") return `${value.toLocaleString(undefined, { maximumFractionDigits: 1 })}%`;
  return value.toLocaleString(undefined, { maximumFractionDigits: 2 });
}

const SEVERITY_DOT: Record<GapSeverity, string> = {
  high: "#EE3C25",
  medium: "#F4C300",
  low: "#8AA0B0",
};

const DIRECTION_LABEL: Record<string, string> = {
  ahead: "Ahead of Peers",
  behind: "Behind Peers",
  even: "Even With Peers",
  unknown: "Unknown",
};

const DIRECTION_COLOR: Record<string, string> = {
  ahead: "#39C37B",
  behind: "#EE3C25",
  even: "#8AA0B0",
  unknown: "#8AA0B0",
};

function DirectionBadge({ gap }: { gap: GapEntry }) {
  return (
    <span
      className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded-full border"
      style={{ borderColor: DIRECTION_COLOR[gap.direction], color: DIRECTION_COLOR[gap.direction] }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: DIRECTION_COLOR[gap.direction] }} />
      {DIRECTION_LABEL[gap.direction] ?? gap.direction}
    </span>
  );
}

function RevenueImpactBlock({ theme, gap }: { theme: Theme; gap: GapEntry }) {
  const ri = gap.revenue_impact;
  if (!ri) return null;

  const hasDirect = ri.dollar_impact_monthly !== null && ri.dollar_impact_monthly !== undefined;
  const hasUnit = !!ri.unit_impact;
  const hasPortfolio = !!ri.portfolio_exposure_impact;

  if (!hasDirect && !hasUnit && !hasPortfolio) {
    return (
      <div className={tc(theme, "text-xs text-zinc-600 mt-1.5", "text-xs text-zinc-400 mt-1.5")}>
        {ri.not_convertible_reason ?? "No real dollar conversion available for this KPI."}
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-1.5">
      <div className="text-xs uppercase tracking-wide text-zinc-500">Revenue Impact</div>

      {hasDirect && (
        <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
          <div className="text-sm font-semibold text-emerald-300">
            {fmtCurrency(ri.dollar_impact_monthly)}/mo
            <span className="text-xs text-zinc-500 font-normal ml-1">
              ({fmtCurrency(ri.annualized_dollar_impact)}/yr)
            </span>
          </div>
        </div>
      )}

      {hasUnit && ri.unit_impact && (
        <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
          <div className="text-sm font-semibold text-emerald-300">
            +{ri.unit_impact.additional_units_monthly.toLocaleString(undefined, { maximumFractionDigits: 1 })}{" "}
            {ri.unit_impact.unit_label}/mo
          </div>
          {ri.unit_impact.derived_dollar_impact_monthly !== null && (
            <div className="text-xs text-zinc-400 mt-0.5">
              ≈ {fmtCurrency(ri.unit_impact.derived_dollar_impact_monthly)}/mo additional gross
              {" "}({fmtCurrency(ri.unit_impact.derived_dollar_impact_annualized)}/yr)
            </div>
          )}
          <div className="text-xs text-zinc-600 mt-1">
            {String(ri.unit_impact.real_inputs_used?.formula ?? "")}
          </div>
        </div>
      )}

      {hasPortfolio && ri.portfolio_exposure_impact && (
        <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
          <div className="text-sm font-semibold text-amber-300">
            {fmtCurrency(ri.portfolio_exposure_impact.dollars_at_risk_reduction)} at-risk reduction
          </div>
          <div className="text-xs text-zinc-500 mt-0.5">{ri.portfolio_exposure_impact.note}</div>
        </div>
      )}
    </div>
  );
}

function RootCausesBlock({ theme, gap }: { theme: Theme; gap: GapEntry }) {
  const causes = gap.root_causes;

  if (!causes || causes.length === 0) {
    return (
      <div className={tc(theme, "text-xs text-zinc-600 mt-1.5", "text-xs text-zinc-400 mt-1.5")}>
        {gap.root_cause_note ?? "No specific root-cause diagnostic available for this KPI yet."}
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-1.5">
      <div className="text-xs uppercase tracking-wide text-zinc-500">Likely Causes</div>
      {causes.map((c) => (
        <div key={c.key} className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
          <div className="text-xs text-zinc-200 font-medium">{c.label}</div>
          <div className="text-xs text-zinc-400 mt-0.5">{c.finding}</div>
        </div>
      ))}
    </div>
  );
}

function GapCard({ theme, gap }: { theme: Theme; gap: GapEntry }) {
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-3")}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <div className="text-xs uppercase tracking-wide text-zinc-500">{gap.department}</div>
          <div className="text-sm font-brand font-semibold">{gap.label}</div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {gap.severity && (
            <span className="h-2 w-2 rounded-full" style={{ background: SEVERITY_DOT[gap.severity] }} title={`${gap.severity} severity`} />
          )}
          <DirectionBadge gap={gap} />
        </div>
      </div>

      <div className="grid grid-cols-3 gap-2 mt-2 text-xs">
        <div>
          <div className="text-zinc-500">You</div>
          <div className="font-semibold">{fmtValue(gap.this_store, gap.format)}</div>
        </div>
        <div>
          <div className="text-zinc-500">Peer Average</div>
          <div className="font-semibold">{fmtValue(gap.peer_average, gap.format)}</div>
        </div>
        <div>
          <div className="text-zinc-500">Gap</div>
          <div className="font-semibold">
            {gap.opportunity_gap !== null ? fmtValue(gap.opportunity_gap, gap.format) : "—"}
          </div>
        </div>
      </div>

      <RootCausesBlock theme={theme} gap={gap} />
      <RevenueImpactBlock theme={theme} gap={gap} />
    </div>
  );
}

function GapRow({ theme, gap }: { theme: Theme; gap: GapEntry }) {
  return (
    <div className={tc(theme, "flex items-center justify-between gap-3 rounded border border-zinc-800 bg-zinc-900/60 px-2.5 py-2", "flex items-center justify-between gap-3 rounded border border-zinc-200 bg-zinc-50 px-2.5 py-2")}>
      <div className="min-w-0">
        <div className="text-xs text-zinc-500">{gap.department}</div>
        <div className="text-xs text-zinc-200 font-medium truncate">{gap.label}</div>
      </div>
      <div className="flex items-center gap-3 shrink-0">
        <div className="text-right">
          <div className="text-xs text-zinc-500">You / Peer Avg</div>
          <div className="text-xs text-zinc-300">
            {fmtValue(gap.this_store, gap.format)} / {fmtValue(gap.peer_average, gap.format)}
          </div>
        </div>
        <DirectionBadge gap={gap} />
      </div>
    </div>
  );
}

export function NetworkGapAnalysisBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<NetworkGapAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getNetworkGapAnalysis()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Network Gap Analysis."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">Gap Analysis</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          The profit leakage center -- real gaps against SIMULATED peer benchmarks, each with real Root Cause
          diagnostics and real Revenue Impact where a formula exists.
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loading || !data ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            {/* Real opportunities, enriched with root cause + revenue impact */}
            <div>
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">
                Largest Real Opportunities ({data.largest_opportunity_gaps.length})
              </div>
              {data.largest_opportunity_gaps.length > 0 ? (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  {data.largest_opportunity_gaps.map((g) => (
                    <GapCard key={`${g.department}-${g.kpi}`} theme={theme} gap={g} />
                  ))}
                </div>
              ) : (
                <div className="text-xs text-zinc-500">
                  No real opportunities right now -- this dealer is at or ahead of peer average on every benchmarked
                  KPI.
                </div>
              )}
            </div>

            {/* All largest gaps (by absolute magnitude, both directions) */}
            <div>
              <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">
                Largest Gaps -- Both Directions ({data.largest_gaps.length})
              </div>
              <div className="space-y-1.5">
                {data.largest_gaps.map((g) => (
                  <GapRow key={`row-${g.department}-${g.kpi}`} theme={theme} gap={g} />
                ))}
              </div>
            </div>

            <div className={tc(theme, "text-xs text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-500 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
              {data.basis_notice}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
