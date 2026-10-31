"use client";
import { WorkButton } from "./WorkspaceUi";

// Network's rebuilt "Overview" item -- the first slice of Sam's "NXTDeal
// Intelligence Network" reframe ("a 24/7 AI 20 Group"). Rendered ABOVE the
// existing generic KPI module board (components/MenuDashPanel.tsx's
// itemKey === "overview" branch, unchanged -- same "ABOVE, not instead of"
// precedent SalesOverviewBoard/OperationsOverviewBoard/ServiceOverviewBoard
// already established), not a full replacement.
//
// Three real pieces, composed by core/network_opportunity_value.py:
//   1. An Executive Summary -- a real, rules-based templated narrative
//      (never a fabricated LLM fact) with an optional isolated-OpenAI
//      phrasing polish that can never invent a number, matching Sam's own
//      example format ("Your dealership ranks in the top 12%... Estimated
//      annual opportunity: $486,000").
//   2. Largest Opportunities -- the real, dollar-ranked gap list. Every
//      figure is either DIRECT (already currency-shaped) or DERIVED (a
//      count gap x this dealer's own real per-unit dollar value) -- both
//      shown with their real inputs. A percent/ratio gap with no real
//      dollar multiplier is never guessed at; it's excluded from this list
//      entirely (it has no dollar figure to rank by).
//   3. Total Identified Opportunity -- a real, annualized (monthly x 12)
//      grand total across every non-excluded department, matching Sam's
//      "$1.8 Million" framing.
import { useEffect, useState } from "react";
import {
  getNetworkOverview,
  regenerateNetworkSummary,
  type NetworkOverview,
  type DollarGap,
  type DepartmentDollarOpportunity,
} from "@/lib/networkOpportunity";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function fmtCurrency(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  const sign = value < 0 ? "-" : "";
  return `${sign}$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function fmtPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

function ConversionBadge({ method }: { method: DollarGap["conversion_method"] }) {
  const map: Record<DollarGap["conversion_method"], string> = {
    direct_currency: "bg-emerald-950/40 text-emerald-300",
    derived_per_unit_real_value: "bg-sky-950/40 text-sky-300",
    not_convertible_to_dollars: "bg-zinc-800 text-zinc-400",
  };
  const label: Record<DollarGap["conversion_method"], string> = {
    direct_currency: "real $",
    derived_per_unit_real_value: "derived $",
    not_convertible_to_dollars: "not convertible",
  };
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${map[method]}`}>
      {label[method]}
    </span>
  );
}

function OpportunityCard({ theme, gap }: { theme: Theme; gap: DollarGap }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-3", "rounded border border-zinc-200 bg-zinc-50 p-3")}>
      <div className="flex items-center justify-between gap-2 flex-wrap">
        <div className="text-xs uppercase tracking-wide text-zinc-500">{gap.department_title}</div>
        <ConversionBadge method={gap.conversion_method} />
      </div>
      <div className="text-sm font-semibold mt-0.5">{gap.label}</div>
      <div className="text-xl font-brand font-semibold mt-1 text-emerald-300">
        {fmtCurrency(gap.annualized_dollar_impact)}
        <span className="text-xs text-zinc-500 font-normal ml-1">/yr</span>
      </div>
      <div className="text-xs text-zinc-500 mt-0.5">
        {fmtCurrency(gap.dollar_impact_monthly)}/mo · behind peer average by {fmtPct(gap.peer_gap_pct)}
      </div>
      <WorkButton type="submit"
        onClick={() => setExpanded((e) => !e)}
        className="text-xs text-zinc-500 hover:text-zinc-300 mt-1.5 underline"
      >
        {expanded ? "Hide the math" : "Show the math"}
      </WorkButton>
      {expanded && gap.real_inputs_used && (
        <div className="text-xs text-zinc-500 mt-1.5 space-y-0.5 font-mono">
          {Object.entries(gap.real_inputs_used).map(([k, v]) => (
            <div key={k}>
              {k}: {typeof v === "number" ? v.toLocaleString() : String(v)}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function DepartmentBar({ theme, dept, maxVal }: { theme: Theme; dept: DepartmentDollarOpportunity; maxVal: number }) {
  const pct = maxVal > 0 ? Math.max(2, (dept.annualized_opportunity / maxVal) * 100) : 0;
  return (
    <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2.5", "rounded border border-zinc-200 bg-zinc-50 p-2.5")}>
      <div className="flex items-center justify-between text-xs">
        <span className="text-zinc-300">
          {dept.department_title}
          {dept.excluded_from_grand_total && (
            <span className="ml-1.5 px-1 py-0.5 rounded bg-zinc-800 text-zinc-500 text-xs uppercase">rollup, excluded</span>
          )}
        </span>
        <span className="font-semibold">{fmtCurrency(dept.annualized_opportunity)}/yr</span>
      </div>
      <div className="h-1.5 rounded bg-zinc-800 mt-1.5 overflow-hidden">
        <div className="h-full bg-emerald-500/70" style={{ width: `${pct}%` }} />
      </div>
      <div className="text-xs text-zinc-600 mt-1">
        {dept.convertible_gap_count} convertible · {dept.not_convertible_gap_count} not convertible
      </div>
    </div>
  );
}

export function NetworkOverviewBoard({ theme, hideAssistant = false }: { theme: Theme; hideAssistant?: boolean }) {
  const [data, setData] = useState<NetworkOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    getNetworkOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the Network Overview."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), []);

  function handleRegenerate(polish: boolean) {
    setRegenerating(true);
    regenerateNetworkSummary(polish)
      .then((summary) => setData((prev) => (prev ? { ...prev, executive_summary: summary } : prev)))
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to regenerate the summary."))
      .finally(() => setRegenerating(false));
  }

  if (loading) {
    return <div className="p-4 text-sm text-zinc-500">Loading network intelligence…</div>;
  }

  if (error && !data) {
    return <div className="p-4 text-xs text-red-400">{error}</div>;
  }

  if (!data) return null;

  const summary = data.executive_summary;
  const largest = data.largest_opportunities ?? [];
  const departments = data.dollar_opportunity?.by_department ?? [];
  const maxVal = Math.max(1, ...departments.map((d) => d.annualized_opportunity));

  return (
    <div className={tc(theme, "bg-brand-ink text-white p-4 space-y-4", "bg-white text-black p-4 space-y-4")}>
      {error && <div className="text-xs text-red-400">{error}</div>}

      {/* Executive Summary */}
      <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div className="text-sm font-brand font-semibold flex items-center">
            Executive Summary
            <span
              className={`ml-2 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${
                summary?.ai_generated ? "bg-sky-950/40 text-sky-300" : "bg-emerald-950/40 text-emerald-300"
              }`}
            >
              {summary?.ai_generated ? "AI-polished" : "real template"}
            </span>
          </div>
          <div className="flex gap-2">
            <WorkButton type="submit"
              onClick={() => handleRegenerate(false)}
              disabled={regenerating}
              className="px-2.5 py-1 rounded text-xs bg-zinc-800 text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
            >
              Regenerate (template)
            </WorkButton>
            {!hideAssistant && <WorkButton type="submit"
              onClick={() => handleRegenerate(true)}
              disabled={regenerating}
              className="px-2.5 py-1 rounded text-xs bg-zinc-200 text-black font-medium hover:bg-white disabled:opacity-50"
            >
              ✨ Regenerate + AI polish
            </WorkButton>}
          </div>
        </div>
        <p className="text-sm text-zinc-200 mt-3 leading-relaxed">{summary?.summary}</p>
        {!hideAssistant && summary?.ai_polish_note && (
          <div className="text-xs text-zinc-600 mt-2 italic">{summary.ai_polish_note}</div>
        )}
        <div className="text-xs text-zinc-600 mt-2">
          This summary uses the percentile, gap and dollar data below, including the labeled simulated peer comparisons.
          {!hideAssistant && " Optional AI polish changes phrasing only, never numbers or findings."}
        </div>
      </div>

      {/* Total Identified Opportunity */}
      <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <div className="text-xs uppercase tracking-wide text-zinc-500">Total Identified Opportunity</div>
            <div className="text-3xl font-brand font-semibold mt-1 text-emerald-300">
              {fmtCurrency(data.dollar_opportunity?.annualized)}
              <span className="text-xs text-zinc-500 font-normal ml-1">/yr</span>
            </div>
            <div className="text-xs text-zinc-500 mt-1">
              {fmtCurrency(data.dollar_opportunity?.monthly)}/mo, held steady for a year -- a real, formula-derived
              projection, not a guaranteed outcome.
            </div>
          </div>
          <div className="text-right">
            <div className="text-xs uppercase tracking-wide text-zinc-500">Network Percentile Rank</div>
            <div className="text-2xl font-brand font-semibold mt-1">{fmtPct(data.network_percentile_rank?.avg_pct, 1)}</div>
          </div>
        </div>
        {data.dollar_opportunity?.excluded_departments && data.dollar_opportunity.excluded_departments.length > 0 && (
          <div className="text-xs text-zinc-600 mt-2">
            Excludes: {data.dollar_opportunity.excluded_departments.join(", ")} (a cross-department rollup -- see
            note on its card below).
          </div>
        )}
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 mt-3">
          {departments.map((d) => (
            <DepartmentBar key={d.department} theme={theme} dept={d} maxVal={maxVal} />
          ))}
        </div>
      </div>

      {/* Largest Opportunities */}
      <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
        <div className="text-sm font-brand font-semibold mb-1">Largest Opportunities</div>
        <div className="text-xs text-zinc-500 mb-3">
          Every real dollar-convertible gap this dealer is behind the (simulated) peer average on, ranked by
          annualized dollar impact.
        </div>
        {largest.length > 0 ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-2">
            {largest.map((g) => (
              <OpportunityCard key={`${g.department}-${g.kpi}`} theme={theme} gap={g} />
            ))}
          </div>
        ) : (
          <div className="text-xs text-emerald-300">
            No dollar-convertible gap right now -- this dealer is currently at or above the (simulated) peer average
            on every currency/countable KPI.
          </div>
        )}
      </div>

      <div className={tc(theme, "text-xs text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-500 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
        {data.dollar_opportunity?.basis_notice}
      </div>
    </div>
  );
}
