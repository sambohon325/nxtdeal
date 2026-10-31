"use client";
import { WorkButton , WorkStat} from "./WorkspaceUi";

// Readiness' reimagined "Exceptions" Top Menu item, which is ALSO Sam's
// separately-named "Enterprise Risk Center" capstone feature -- built once,
// not twice (see core/enterprise_risk_center.py's own docstring). Composes 9
// already-real signals plus one genuinely new per-deal check
// (negative_gross_deals) into Sam's 3 categories, each exception carrying a
// real, computed Low/Medium/High/Critical severity and a plain-language
// reference to where it should actually be resolved (this board never
// duplicates that resolution action -- it points at it). No blended overall
// risk score is shown (see the backend's own overall_risk_score_note) -- the
// KPI strip's by-severity roll-up is the honest analog.
import { useEffect, useState } from "react";
import {
  getRiskCenterOverview,
  type RiskCenterOverview,
  type ExceptionEntry,
  type Severity,
} from "@/lib/enterpriseRiskCenter";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = ["#EE3C25", "#F4C300", "#3E6CB3"];

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

function fmtMoney(value: unknown): string {
  if (value === null || value === undefined || typeof value !== "number") return "—";
  return `$${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function KpiTile({ theme, label, value, color }: { theme: Theme; label: string; value: string | number; color?: string }) { return <WorkStat label={label} value={value}/>; }

function ExceptionCard({ theme, entry }: { theme: Theme; entry: ExceptionEntry }) {
  const [expanded, setExpanded] = useState(false);

  return (
    <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/50 p-3", "rounded border border-zinc-200 bg-white p-3")}>
      <div className="flex items-start justify-between flex-wrap gap-1">
        <div className="flex items-center flex-wrap">
          <span className="text-sm font-medium">{entry.title}</span>
          <SeverityBadge severity={entry.severity} />
          <BasisBadge basis={entry.basis} />
        </div>
        <div className="text-lg font-semibold">{entry.count === null ? "—" : fmtNum(entry.count)}</div>
      </div>

      {entry.access_error ? (
        <div className={tc(theme, "text-xs text-zinc-600 italic mt-1", "text-xs text-zinc-400 italic mt-1")}>{entry.access_error}</div>
      ) : (
        <>
          {entry.total_loss !== undefined && (
            <div className="text-xs text-red-300 mt-1">Total impact: {fmtMoney(entry.total_loss)}</div>
          )}
          {entry.note && <div className="text-xs text-zinc-500 mt-1">{entry.note}</div>}

          {entry.resolve && (
            <div className="text-xs text-sky-400 mt-2">
              → Resolve in <span className="font-medium">{entry.resolve.department}</span> ·{" "}
              <span className="italic">{entry.resolve.hint}</span>
            </div>
          )}

          {entry.items && entry.items.length > 0 && (
            <div className="mt-2">
              <WorkButton
                type="button"
                onClick={() => setExpanded((e) => !e)}
                className={tc(theme, "text-xs text-zinc-400 hover:text-zinc-200 underline", "text-xs text-zinc-500 hover:text-zinc-700 underline")}
              >
                {expanded ? "Hide" : `Show ${entry.items.length} item${entry.items.length === 1 ? "" : "s"}`}
              </WorkButton>
              {expanded && (
                <ul className="mt-1 space-y-0.5 max-h-48 overflow-y-auto pr-1">
                  {entry.items.map((item, idx) => (
                    <li key={`${item.id}-${idx}`} className={tc(theme, "text-xs text-zinc-400", "text-xs text-zinc-600")}>
                      <span className="text-zinc-500">{item.id}</span> — {item.label}
                      {typeof item.gross === "number" && <span className="text-red-400"> ({fmtMoney(item.gross)})</span>}
                    </li>
                  ))}
                </ul>
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
  entries,
}: {
  theme: Theme;
  title: string;
  color: string;
  entries: ExceptionEntry[];
}) {
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: color }} />
      <div className="pl-2">
        <div className="text-sm font-brand font-semibold mb-3">{title}</div>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {entries.map((entry) => (
            <ExceptionCard key={entry.key} theme={theme} entry={entry} />
          ))}
        </div>
      </div>
    </div>
  );
}

export function EnterpriseRiskCenterBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<RiskCenterOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getRiskCenterOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the Enterprise Risk Center."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), []);

  const kpi = data?.kpi;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800 flex items-center justify-between", "px-4 py-3 border-b border-zinc-200 flex items-center justify-between")}>
        <div>
          <div className="text-sm font-brand font-semibold">Enterprise Risk Center</div>
          <div className="text-xs text-zinc-500 mt-0.5">
            Critical, Financial, and Operational exceptions -- every item carries a real, computed
            Low/Medium/High/Critical severity and a reference to where it's resolved. Not just a list.
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
              <KpiTile theme={theme} label="Active Exception Types" value={`${fmtNum(kpi?.total_exception_types_active)} / ${fmtNum(kpi?.total_exception_types)}`} />
              <KpiTile theme={theme} label="Affected Entities" value={fmtNum(kpi?.total_affected_entities)} />
              <KpiTile theme={theme} label="Critical" value={fmtNum(kpi?.by_severity?.critical)} color={SEVERITY_STYLE.critical.dot} />
              <KpiTile theme={theme} label="High" value={fmtNum(kpi?.by_severity?.high)} color={SEVERITY_STYLE.high.dot} />
              <KpiTile theme={theme} label="Medium" value={fmtNum(kpi?.by_severity?.medium)} color={SEVERITY_STYLE.medium.dot} />
              <KpiTile theme={theme} label="Low" value={fmtNum(kpi?.by_severity?.low)} color={SEVERITY_STYLE.low.dot} />
            </div>

            {data?.overall_risk_score_note && (
              <div className={tc(theme, "text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
                {data.overall_risk_score_note}
              </div>
            )}

            {data && (
              <div className="space-y-3">
                <CategorySection theme={theme} title="Critical Issues" color={RIBBON[0]} entries={data.categories.critical_issues} />
                <CategorySection theme={theme} title="Financial Exceptions" color={RIBBON[1]} entries={data.categories.financial_exceptions} />
                <CategorySection theme={theme} title="Operational Exceptions" color={RIBBON[2]} entries={data.categories.operational_exceptions} />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
