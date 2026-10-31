"use client";

// Operations' "Overview" item -- rendered ABOVE the existing generic Overview KPI
// board (same "ABOVE, not instead of" precedent SalesOverviewBoard established,
// session 94), not a replacement for it. Backend: core/operations_overview.py.
// Sam's spec: "Operations Action Center" (clickable Daily Priorities, not bare
// counts), a color-coded "Department Health Dashboard," and "Workload
// Distribution." See the backend module docstring for the honest scoping notes
// on "Units Over 90 Days" (no acquisition-date field exists) and "Recon Team/
// Title Team/Lot Team" (illustrative, not a real roster in this codebase).
import { useEffect, useState, type ReactNode } from "react";
import { getOperationsOverview, type OperationsOverview, type DealBrief, type VehicleBrief } from "@/lib/operationsOverview";
import { EntityHoverLink } from "@/components/EntityHoverLink";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const LOAD_TONE: Record<string, string> = {
  low: "bg-green-950/40 text-green-300 border-green-900",
  moderate: "bg-amber-950/40 text-amber-300 border-amber-900",
  high: "bg-red-950/40 text-red-300 border-red-900",
  unstaffed: "bg-zinc-800 text-zinc-400 border-zinc-700",
};

function PriorityCard({
  theme,
  title,
  count,
  children,
}: {
  theme: Theme;
  title: string;
  count: number | null;
  children: ReactNode;
}) {
  return (
    <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-xs font-brand uppercase tracking-wide text-zinc-500">{title}</span>
        <span className="text-sm font-semibold">{count ?? "—"}</span>
      </div>
      <div className="space-y-1 max-h-32 overflow-y-auto">{children}</div>
    </div>
  );
}

function DealRow({ d }: { d: DealBrief }) {
  return (
    <div className="text-xs flex items-center gap-1">
      <EntityHoverLink id={d.deal_id} /> — {d.vehicle_id && <EntityHoverLink id={d.vehicle_id} />} <span className="text-zinc-500">({d.status})</span>
    </div>
  );
}

function VehicleRow({ v }: { v: VehicleBrief }) {
  return (
    <div className="text-xs">
      <EntityHoverLink id={v.vehicle_id} /> <span className="text-zinc-500">{v.stock_number}</span>
    </div>
  );
}

export function OperationsOverviewBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<OperationsOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getOperationsOverview()
      .then(setData)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return <div className="p-4 text-sm text-zinc-500">Loading Operations Overview…</div>;
  }

  if (error || !data) {
    return <div className="p-4 text-sm text-red-400">{error || "Unable to load Operations Overview."}</div>;
  }

  const { action_center, department_health, workload_distribution } = data;

  return (
    <div className={tc(theme, "bg-brand-ink text-white", "bg-white text-black")}>
      <div className="p-4 space-y-5 border-b border-zinc-800/60">
        {/* Action Center / Daily Priorities */}
        <div>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Daily Priorities</div>
          <div className="grid grid-cols-3 gap-3">
            <PriorityCard theme={theme} title="Deliveries At Risk" count={action_center.deliveries_at_risk.count}>
              {action_center.deliveries_at_risk.deals.length === 0 ? (
                <div className="text-xs text-zinc-600">None at risk.</div>
              ) : (
                action_center.deliveries_at_risk.deals.map((d) => <DealRow key={d.deal_id} d={d} />)
              )}
            </PriorityCard>
            <PriorityCard theme={theme} title="Vehicles Missing Titles" count={action_center.vehicles_missing_titles.count}>
              {action_center.vehicles_missing_titles.vehicles.length === 0 ? (
                <div className="text-xs text-zinc-600">None missing.</div>
              ) : (
                action_center.vehicles_missing_titles.vehicles.map((v) => <VehicleRow key={v.vehicle_id} v={v} />)
              )}
            </PriorityCard>
            <PriorityCard theme={theme} title="Awaiting Inspection" count={action_center.vehicles_awaiting_inspection.count}>
              {action_center.vehicles_awaiting_inspection.vehicles.length === 0 ? (
                <div className="text-xs text-zinc-600">None awaiting inspection.</div>
              ) : (
                action_center.vehicles_awaiting_inspection.vehicles.map((v) => <VehicleRow key={v.vehicle_id} v={v} />)
              )}
            </PriorityCard>
            <PriorityCard theme={theme} title="Compliance Violations" count={action_center.compliance_violations.count}>
              {action_center.compliance_violations.error ? (
                <div className="text-xs text-zinc-600 italic">{action_center.compliance_violations.error}</div>
              ) : (
                <div className="text-xs text-zinc-500">{action_center.compliance_violations.count === 0 ? "No open violations." : "See Compliance & Deal Jacket workflow."}</div>
              )}
            </PriorityCard>
            <PriorityCard theme={theme} title="Wholesale Decision Needed" count={action_center.wholesale_candidates_needing_decision.count}>
              <div className="text-xs text-zinc-600 italic mb-1">{action_center.wholesale_candidates_needing_decision.substituted_for}</div>
              {(action_center.wholesale_candidates_needing_decision.vehicles as { vehicle_id: string; stock_number?: string }[]).slice(0, 5).map((v) => (
                <div key={v.vehicle_id} className="text-xs"><EntityHoverLink id={v.vehicle_id} /> <span className="text-zinc-500">{v.stock_number}</span></div>
              ))}
            </PriorityCard>
          </div>
        </div>

        {/* Department Health */}
        <div>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Department Health</div>
          <div className="grid grid-cols-5 gap-2">
            {department_health.checks.map((c) => (
              <div key={c.area} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5")}>
                <div className="text-xs font-medium mb-1">{c.status === "healthy" ? "✅" : "⚠"} {c.area}</div>
                <div className="text-xs text-zinc-500 leading-snug">{c.detail}</div>
              </div>
            ))}
          </div>
        </div>

        {/* Workload Distribution */}
        <div>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Workload Distribution</div>
          <div className="grid grid-cols-3 gap-3">
            {workload_distribution.areas.map((a, i) => (
              <div key={a.area} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
                <div className="flex items-center justify-between mb-1">
                  <span className="text-xs font-medium">{a.area}</span>
                  <span className={`text-xs px-1.5 py-0.5 rounded border ${LOAD_TONE[a.load]}`}>{a.load}</span>
                </div>
                <div className="text-xs text-zinc-500">{a.headcount} staff · {a.open_task_count} open tasks</div>
                {a.note && <div className="text-xs text-zinc-600 italic mt-1">{a.note}</div>}
              </div>
            ))}
          </div>
          <div className="text-xs text-zinc-600 italic mt-2">{workload_distribution.methodology_note}</div>
        </div>
      </div>
    </div>
  );
}
