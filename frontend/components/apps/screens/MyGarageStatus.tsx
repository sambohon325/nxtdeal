"use client";

// My Garage "Status" — live status of the verified customer's active repair orders: where
// each vehicle is in the 10-stage service lifecycle, the assigned technician, and a recent
// activity timeline. Behind CustomerVerifyGate, reads the token-scoped /public/garage/status
// endpoint (core/garage.py → repair_orders.get_ro_workspace). Read-only, real data only —
// no fabricated progress.

import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import { getMyStatus, type GarageStatusView, type GarageStatusItem } from "@/lib/garage";
import { CustomerVerifyGate } from "@/components/apps/CustomerVerifyGate";
import { useAsync, EmptyNote, CustomerLoadError } from "./kit";

function Progress({ item }: { item: GarageStatusItem }) {
  const steps = item.workflow_checklist;
  const doneOrCurrent = steps.filter((s) => s.status !== "pending").length;
  const pct = steps.length ? Math.round((doneOrCurrent / steps.length) * 100) : 0;
  return (
    <div className="mt-3">
      <div className="mb-1 flex items-center justify-between text-[10px] text-zinc-500">
        <span>{item.stage || "In progress"}</span>
        <span>{pct}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-emerald-500/80" style={{ width: `${pct}%` }} />
      </div>
      <div className="mt-2 flex flex-wrap gap-1">
        {steps.map((s) => (
          <span
            key={s.stage}
            className={
              "rounded-full px-2 py-0.5 text-[9px] font-medium " +
              (s.status === "complete"
                ? "bg-emerald-500/15 text-emerald-300"
                : s.status === "current"
                  ? "bg-white/15 text-white"
                  : "bg-white/[0.04] text-zinc-500")
            }
          >
            {s.stage}
          </span>
        ))}
      </div>
    </div>
  );
}

function Card({ item }: { item: GarageStatusItem }) {
  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-white">{item.vehicle}</div>
          <div className="truncate text-[11px] text-zinc-500">
            {item.description || "Repair order"} · #{item.service_number}
          </div>
        </div>
        {item.technician && (
          <div className="shrink-0 text-right text-[11px] text-zinc-400">Tech: {item.technician}</div>
        )}
      </div>

      <Progress item={item} />

      {item.timeline.length > 0 && (
        <div className="mt-3 border-t border-white/5 pt-2">
          <div className="mb-1 text-[10px] uppercase tracking-wide text-zinc-500">Recent activity</div>
          <ul className="space-y-1">
            {item.timeline.slice().reverse().map((e, i) => (
              <li key={i} className="flex items-start justify-between gap-2 text-[11px]">
                <span className="text-zinc-300">{String(e.label ?? e.type ?? "Update")}</span>
                <span className="shrink-0 text-zinc-500">{String(e.at ?? "")}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Inner({ app }: { app: AppDef }) {
  const accent = accentOf(app);
  const { loading, error, data, reload } = useAsync<GarageStatusView>(() => getMyStatus(), []);

  if (loading) {
    return <div className="flex justify-center py-12"><div className={`h-6 w-6 animate-spin rounded-full border-2 border-white/15 ${accent.text} border-t-current`} /></div>;
  }
  if (error) {
    return <CustomerLoadError subject="your service status" onRetry={reload} />;
  }
  if (!data) return null;

  if (data.count === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4">
        <EmptyNote>No vehicles are in for service right now. Live progress will appear here when one is.</EmptyNote>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {data.active_ros.map((ro) => (
        <Card key={ro.ro_id} item={ro} />
      ))}
    </div>
  );
}

export function MyGarageStatus({ app, screen }: { app: AppDef; screen: AppScreen }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-white">{screen.heading}</h2>
        <p className="mt-0.5 text-sm text-zinc-400">{screen.intro}</p>
      </div>
      <CustomerVerifyGate what="your vehicle&apos;s live service status">
        <Inner app={app} />
      </CustomerVerifyGate>
    </div>
  );
}
