"use client";
import { WorkButton , WorkStat} from "./WorkspaceUi";

// Readiness' reimagined "Recommendations" Top Menu item, item #8 of Sam's
// 10-item Enterprise Readiness & Intelligence structure -- Sam's own framing:
// "This is where AI becomes truly valuable." Composes a real, transparent
// 12-rule engine (core/readiness_recommendations.py) across Sales/Service/
// Finance/Inventory/Marketing -- every recommendation traces to a real
// condition crossing a real, documented threshold (same standing convention
// core/network_audit.py established session 38 -- a rules engine over real
// data, never a fabricated LLM narrative). A real Executive Recommendations
// feed curates every triggered High/Critical rule across every department,
// same "no blended score" discipline core/business_health.py and core/
// enterprise_risk_center.py already established for this same Readiness
// reframe -- the ranked feed is the honest analog to a single AI score.
import { useEffect, useState } from "react";
import {
  getRecommendationsOverview,
  type RecommendationsOverview,
  type RecommendationItem,
  type Category,
  type Severity,
} from "@/lib/readinessRecommendations";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = ["#EE3C25", "#F4C300", "#3E6CB3"];

const CATEGORY_META: Record<Category, { title: string; color: string }> = {
  sales: { title: "Sales Recommendations", color: "#3E6CB3" },
  service: { title: "Service Recommendations", color: "#46C0C8" },
  finance: { title: "Finance Recommendations", color: "#F44321" },
  inventory: { title: "Inventory Recommendations", color: "#F4C300" },
  marketing: { title: "Marketing Recommendations", color: "#8A5CF6" },
};

const CATEGORY_ORDER: Category[] = ["sales", "service", "finance", "inventory", "marketing"];

const SEVERITY_STYLE: Record<Severity, { label: string; cls: string; dot: string }> = {
  critical: { label: "Critical", cls: "bg-red-950/50 text-red-300 border border-red-900/60", dot: "#EE3C25" },
  high: { label: "High", cls: "bg-orange-950/40 text-orange-300 border border-orange-900/50", dot: "#F4802E" },
  medium: { label: "Medium", cls: "bg-amber-950/40 text-amber-300 border border-amber-900/50", dot: "#F4C300" },
  low: { label: "Low", cls: "bg-zinc-800/60 text-zinc-300 border border-zinc-700/60", dot: "#8AA0B0" },
};

function SeverityBadge({ severity }: { severity?: Severity | null }) {
  if (!severity) {
    return <span className="ml-1.5 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide bg-emerald-950/40 text-emerald-300 border border-emerald-900/50">Clear</span>;
  }
  const entry = SEVERITY_STYLE[severity];
  return <span className={`ml-1.5 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${entry.cls}`}>{entry.label}</span>;
}

function BasisBadge({ basis }: { basis?: string }) {
  if (!basis) return null;
  const cls = basis === "real" ? "bg-emerald-950/40 text-emerald-300" : "bg-amber-950/40 text-amber-300";
  return <span className={`ml-1.5 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${cls}`}>{basis}</span>;
}

function fmtNum(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

function KpiTile({ theme, label, value, color }: { theme: Theme; label: string; value: string | number; color?: string }) { return <WorkStat label={label} value={value}/>; }

function RecommendationCard({ theme, item }: { theme: Theme; item: RecommendationItem }) {
  const [expanded, setExpanded] = useState(false);

  const hasDetail =
    (item.actions && item.actions.length > 0) ||
    (item.all_flagged && item.all_flagged.length > 0) ||
    (item.over_performers && item.over_performers.length > 0) ||
    (item.under_performers && item.under_performers.length > 0);

  return (
    <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/50 p-3", "rounded border border-zinc-200 bg-white p-3")}>
      <div className="flex items-start justify-between flex-wrap gap-1">
        <div className="flex items-center flex-wrap">
          <span className="text-sm font-medium">{item.title}</span>
          <SeverityBadge severity={item.severity} />
          <BasisBadge basis={item.basis} />
        </div>
      </div>

      {item.access_error ? (
        <div className={tc(theme, "text-xs text-zinc-600 italic mt-1", "text-xs text-zinc-400 italic mt-1")}>{item.access_error}</div>
      ) : (
        <>
          <div className={tc(theme, "text-xs text-zinc-300 mt-1.5", "text-xs text-zinc-700 mt-1.5")}>{item.finding}</div>

          {item.recommendation && (
            <div className={tc(theme, "text-xs text-sky-300 mt-1.5 font-medium", "text-xs text-sky-700 mt-1.5 font-medium")}>
              → {item.recommendation}
            </div>
          )}

          {item.resolve && item.triggered && (
            <div className="text-xs text-zinc-500 mt-1.5">
              Act in <span className="font-medium">{item.resolve.department}</span> ·{" "}
              <span className="italic">{item.resolve.hint}</span>
            </div>
          )}

          {hasDetail && (
            <div className="mt-2">
              <WorkButton
                type="button"
                onClick={() => setExpanded((e) => !e)}
                className={tc(theme, "text-xs text-zinc-400 hover:text-zinc-200 underline", "text-xs text-zinc-500 hover:text-zinc-700 underline")}
              >
                {expanded ? "Hide detail" : "Show detail"}
              </WorkButton>

              {expanded && (
                <div className="mt-1.5 space-y-2">
                  {item.actions && item.actions.length > 0 && (
                    <ul className="space-y-1.5">
                      {item.actions.map((a, idx) => (
                        <li key={idx} className={tc(theme, "text-xs text-zinc-400", "text-xs text-zinc-600")}>
                          <div>{a.action}</div>
                          {a.items.length > 0 && (
                            <ul className="mt-0.5 ml-2 space-y-0.5 max-h-32 overflow-y-auto pr-1">
                              {a.items.map((it, i2) => (
                                <li key={i2} className="text-zinc-500">
                                  <span className="text-zinc-600">{it.id}</span> — {it.label}
                                </li>
                              ))}
                            </ul>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}

                  {item.all_flagged && item.all_flagged.length > 0 && (
                    <ul className="space-y-0.5 max-h-40 overflow-y-auto pr-1">
                      {item.all_flagged.map((f, idx) => (
                        <li key={idx} className={tc(theme, "text-xs text-zinc-400", "text-xs text-zinc-600")}>
                          {f.service_type}: {f.delta_pct}% ({f.recent_count} ROs / ${f.recent_revenue.toLocaleString()} vs {f.prior_count} ROs / ${f.prior_revenue.toLocaleString()})
                        </li>
                      ))}
                    </ul>
                  )}

                  {(item.over_performers || item.under_performers) && (
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                      {item.over_performers && item.over_performers.length > 0 && (
                        <div>
                          <div className="text-xs uppercase tracking-wide text-emerald-500">Over-performing</div>
                          <ul className="space-y-0.5">
                            {item.over_performers.map((c, idx) => (
                              <li key={idx} className="text-xs text-emerald-300">
                                {c.source}: {c.conversion_rate}% ({c.vs_average_pct > 0 ? "+" : ""}{c.vs_average_pct}%, n={c.lead_count})
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                      {item.under_performers && item.under_performers.length > 0 && (
                        <div>
                          <div className="text-xs uppercase tracking-wide text-red-500">Under-performing</div>
                          <ul className="space-y-0.5">
                            {item.under_performers.map((c, idx) => (
                              <li key={idx} className="text-xs text-red-300">
                                {c.source}: {c.conversion_rate}% ({c.vs_average_pct}%, n={c.lead_count})
                              </li>
                            ))}
                          </ul>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}

function CategorySection({
  theme,
  title,
  color,
  items,
}: {
  theme: Theme;
  title: string;
  color: string;
  items: RecommendationItem[];
}) {
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: color }} />
      <div className="pl-2">
        <div className="text-sm font-brand font-semibold mb-3">{title}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {items.map((item) => (
            <RecommendationCard key={item.key} theme={theme} item={item} />
          ))}
        </div>
      </div>
    </div>
  );
}

export function ReadinessRecommendationsBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<RecommendationsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getRecommendationsOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Recommendations."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), []);

  const kpi = data?.kpi;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800 flex items-center justify-between", "px-4 py-3 border-b border-zinc-200 flex items-center justify-between")}>
        <div>
          <div className="text-sm font-brand font-semibold">Recommendations</div>
          <div className="text-xs text-zinc-500 mt-0.5">
            A real, transparent rules engine -- every recommendation traces to a real condition
            crossing a real threshold over real data. Not an LLM narrative.
          </div>
        </div>
        <WorkButton
          type="button"
          onClick={refresh}
          className={tc(theme, "text-xs px-2 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200", "text-xs px-2 py-1 rounded bg-zinc-200 hover:bg-zinc-300 text-black")}
        >
          Refresh
        </WorkButton>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-3">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div className="grid grid-cols-2 md:grid-cols-6 gap-2">
              <KpiTile theme={theme} label="Rules Triggered" value={`${fmtNum(kpi?.triggered_count)} / ${fmtNum(kpi?.total_rules)}`} />
              <KpiTile theme={theme} label="Critical" value={fmtNum(kpi?.by_severity?.critical)} color={SEVERITY_STYLE.critical.dot} />
              <KpiTile theme={theme} label="High" value={fmtNum(kpi?.by_severity?.high)} color={SEVERITY_STYLE.high.dot} />
              <KpiTile theme={theme} label="Medium" value={fmtNum(kpi?.by_severity?.medium)} color={SEVERITY_STYLE.medium.dot} />
              <KpiTile theme={theme} label="Low" value={fmtNum(kpi?.by_severity?.low)} color={SEVERITY_STYLE.low.dot} />
              <KpiTile theme={theme} label="Executive Feed" value={fmtNum(data?.executive_recommendations?.length)} />
            </div>

            {data?.overall_recommendation_score_note && (
              <div className={tc(theme, "text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
                {data.overall_recommendation_score_note}
              </div>
            )}

            {data && data.executive_recommendations.length > 0 && (
              <CategorySection
                theme={theme}
                title="Executive Recommendations"
                color={RIBBON[0]}
                items={data.executive_recommendations}
              />
            )}

            {data && (
              <div className="space-y-3">
                {CATEGORY_ORDER.map((cat) => (
                  <CategorySection
                    key={cat}
                    theme={theme}
                    title={CATEGORY_META[cat].title}
                    color={CATEGORY_META[cat].color}
                    items={data.categories[cat] || []}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
