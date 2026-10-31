"use client";

// Network's "Trends" item -- real day-over-day KPI deltas per department (now
// including the real "bhph" portfolio department, previously uncovered) plus a
// real 90-day-or-however-many-days-were-actually-recorded snapshot history view.
import { useEffect, useState } from "react";
import {
  getNetworkTrends,
  type NetworkTrends,
  type TrendKpi,
} from "@/lib/networkTrends";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const DEPARTMENT_LABEL: Record<string, string> = {
  sales: "Sales",
  service: "Service",
  parts: "Parts",
  fi: "F&I",
  executive: "Executive",
  bhph: "BHPH / Loan Portfolio",
};

function DeltaBadge({ kpi }: { kpi: TrendKpi }) {
  if (!kpi.has_history || kpi.delta_pct === null) {
    return <span className="text-xs text-zinc-600">no history yet</span>;
  }
  const positive = kpi.delta_pct >= 0;
  return (
    <span className={positive ? "text-xs text-emerald-400" : "text-xs text-red-400"}>
      {positive ? "▲" : "▼"} {Math.abs(kpi.delta_pct).toLocaleString(undefined, { maximumFractionDigits: 1 })}%
    </span>
  );
}

function DepartmentCard({
  theme,
  department,
  kpis,
  daysWithData,
  daysRequested,
}: {
  theme: Theme;
  department: string;
  kpis: TrendKpi[];
  daysWithData: number;
  daysRequested: number;
}) {
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-3")}>
      <div className="flex items-center justify-between">
        <div className="text-sm font-brand font-semibold">{DEPARTMENT_LABEL[department] ?? department}</div>
        <div className="text-xs text-zinc-500">
          {daysWithData}/{daysRequested} real day(s) recorded
        </div>
      </div>
      <div className="mt-2 space-y-1.5">
        {kpis.map((k) => (
          <div key={k.key} className={tc(theme, "flex items-center justify-between rounded border border-zinc-800 bg-zinc-900/60 px-2 py-1.5", "flex items-center justify-between rounded border border-zinc-200 bg-zinc-50 px-2 py-1.5")}>
            <div className="text-xs text-zinc-300">{k.label}</div>
            <div className="flex items-center gap-2">
              <div className="text-xs font-medium">
                {k.value.toLocaleString(undefined, { maximumFractionDigits: 2 })}
              </div>
              <DeltaBadge kpi={k} />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function NetworkTrendsBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<NetworkTrends | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getNetworkTrends()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Network Trends."))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">Trends</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          Real day-over-day KPI deltas across all 6 tracked departments (including BHPH), plus a real
          90-day snapshot history view -- coverage grows one real recorded day at a time.
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loading || !data ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {Object.entries(data.department_trends).map(([dept, kpis]) => (
                <DepartmentCard
                  key={dept}
                  theme={theme}
                  department={dept}
                  kpis={kpis}
                  daysWithData={data.department_history[dept]?.days_with_data ?? 0}
                  daysRequested={data.department_history[dept]?.days_requested ?? data.history_days_requested}
                />
              ))}
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
