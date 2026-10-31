"use client";

// Network's "Opportunities" item -- action-oriented intelligence, enriched
// (Intelligence Network reframe, slice 1) with the same real dollar-
// denominated department totals + grand total + largest-opportunities list
// core/network_opportunity_value.py backs Overview with. The pre-existing
// 5-bucket recommendation grouping (revenue/cost-reduction/operational/
// staffing/process) is unchanged, shown below the dollar summary.
import { useEffect, useState } from "react";
import {
  getNetworkOpportunities,
  type NetworkOpportunities,
  type RecommendationEntry,
  type DollarGap,
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

const SEVERITY_DOT: Record<string, string> = {
  high: "#EE3C25",
  medium: "#F4C300",
  low: "#8AA0B0",
};

const BUCKETS: { key: keyof NetworkOpportunities; label: string }[] = [
  { key: "revenue_opportunities", label: "Revenue Opportunities" },
  { key: "cost_reduction_opportunities", label: "Cost Reduction" },
  { key: "operational_improvements", label: "Operational Improvements" },
  { key: "staffing_recommendations", label: "Staffing" },
  { key: "process_improvements", label: "Process Improvements" },
];

function RecommendationRow({ theme, rec }: { theme: Theme; rec: RecommendationEntry }) {
  return (
    <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2.5", "rounded border border-zinc-200 bg-zinc-50 p-2.5")}>
      <div className="flex items-center gap-2">
        <span className="h-2 w-2 rounded-full shrink-0" style={{ background: SEVERITY_DOT[rec.severity] ?? "#8AA0B0" }} />
        <span className="text-xs uppercase tracking-wide text-zinc-500">{rec.department}</span>
      </div>
      <div className="text-xs text-zinc-200 mt-1">{rec.finding}</div>
      <div className="text-xs text-zinc-400 mt-1">{rec.recommendation}</div>
    </div>
  );
}

function TopOpportunityChip({ gap }: { gap: DollarGap }) {
  return (
    <div className="rounded border border-zinc-800 bg-zinc-900/60 px-2.5 py-2">
      <div className="text-xs text-zinc-500">{gap.department_title}</div>
      <div className="text-xs text-zinc-200 font-medium">{gap.label}</div>
      <div className="text-sm font-semibold text-emerald-300">{fmtCurrency(gap.annualized_dollar_impact)}/yr</div>
    </div>
  );
}

export function NetworkOpportunitiesBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<NetworkOpportunities | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getNetworkOpportunities()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Network Opportunities."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">Network Opportunities</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          Action-oriented intelligence -- real, severity-ranked recommendations plus the real, dollar-denominated
          opportunity total behind them.
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loading || !data ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            {/* Dollar total */}
            <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500">Total Identified Opportunity</div>
                  <div className="text-3xl font-brand font-semibold mt-1 text-emerald-300">
                    {fmtCurrency(data.dollar_opportunities?.grand_total_annualized)}
                    <span className="text-xs text-zinc-500 font-normal ml-1">/yr</span>
                  </div>
                  <div className="text-xs text-zinc-500 mt-1">
                    {fmtCurrency(data.dollar_opportunities?.grand_total_monthly)}/mo, annualized -- a real,
                    formula-derived projection, not a guaranteed outcome.
                  </div>
                </div>
              </div>
              {data.dollar_opportunities?.by_department && (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2 mt-3">
                  {data.dollar_opportunities.by_department.map((d) => (
                    <div key={d.department} className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2", "rounded border border-zinc-200 bg-zinc-50 p-2")}>
                      <div className="text-xs text-zinc-500">
                        {d.department_title}
                        {d.excluded_from_grand_total && <span className="ml-1 text-zinc-600">(rollup)</span>}
                      </div>
                      <div className="text-sm font-semibold">{fmtCurrency(d.annualized_opportunity)}/yr</div>
                    </div>
                  ))}
                </div>
              )}
              {data.dollar_opportunities?.largest_opportunities && data.dollar_opportunities.largest_opportunities.length > 0 && (
                <div className="mt-3">
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1.5">Top Opportunities</div>
                  <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                    {data.dollar_opportunities.largest_opportunities.slice(0, 5).map((g) => (
                      <TopOpportunityChip key={`${g.department}-${g.kpi}`} gap={g} />
                    ))}
                  </div>
                </div>
              )}
              <div className="text-xs text-zinc-600 mt-3">{data.dollar_opportunities?.basis_notice}</div>
            </div>

            {/* Recommendation buckets */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {BUCKETS.map(({ key, label }) => {
                const recs = (data[key] as RecommendationEntry[]) ?? [];
                return (
                  <div key={key as string} className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-3")}>
                    <div className="text-sm font-brand font-semibold mb-2">{label}</div>
                    {recs.length > 0 ? (
                      <div className="space-y-2">
                        {recs.map((r, i) => (
                          <RecommendationRow key={i} theme={theme} rec={r} />
                        ))}
                      </div>
                    ) : (
                      <div className="text-xs text-zinc-500">Nothing here right now.</div>
                    )}
                  </div>
                );
              })}
            </div>

            <div className={tc(theme, "text-xs text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-500 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
              {data.note}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
