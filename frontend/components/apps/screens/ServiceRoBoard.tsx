"use client";

// Service Operations "RO Board" — the live repair-order board off GET /repair-orders/board
// (core/repair_orders.py). Groups open ROs by their 10-stage lifecycle; each stage that has work
// renders as a card. Orders open the shared workspace without clearing board filters.

import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { useState } from "react";
import { getRoBoard, getRoCatalog, type RoBoard, type RoStage } from "@/lib/repairOrders";
import { RoWorkspaceModal } from "@/components/RepairOrderWorkspaceBoard";
import { useAsync, WiredScreen, StatGrid, ListCard, Row, EmptyNote } from "./kit";

const STAGE_ORDER: RoStage[] = [
  "Check-In", "RO Written", "Inspection", "Estimate", "Customer Approval",
  "Parts", "Repair", "Quality Control", "Delivery", "Follow-Up",
];

export function ServiceRoBoard({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data, reload } = useAsync<RoBoard>(() => getRoBoard(), []);
  const [query, setQuery] = useState("");
  const [stageFilter, setStageFilter] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);

  const board = data ?? ({} as RoBoard);
  const total = STAGE_ORDER.reduce((n, s) => n + (board[s]?.length ?? 0), 0);
  const waiting = (board["Customer Approval"]?.length ?? 0) + (board["Parts"]?.length ?? 0);
  const ready = board["Delivery"]?.length ?? 0;

  return (
    <><WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>
      <StatGrid
        app={app}
        stats={[
          { label: "Open ROs", value: total },
          { label: "In repair", value: board["Repair"]?.length ?? 0 },
          { label: "Waiting", value: waiting, hint: "approval + parts" },
          { label: "Ready", value: ready },
        ]}
      />

      {total === 0 && <EmptyNote>No open repair orders right now.</EmptyNote>}

      <div className="grid gap-3 rounded-xl border border-white/15 bg-white/5 p-4 sm:grid-cols-2">
        <label className="text-sm text-slate-200">Find a repair order<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Order number, VIN, work or technician" className="mt-2 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none" /></label>
        <label className="text-sm text-slate-200">Stage<select value={stageFilter} onChange={event => setStageFilter(event.target.value)} className="mt-2 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none"><option value="all">All stages ({total})</option>{STAGE_ORDER.map(stage => <option key={stage} value={stage}>{stage} ({board[stage]?.length ?? 0})</option>)}</select></label>
      </div>
      {(query || stageFilter !== "all") && !STAGE_ORDER.some(stage => (stageFilter === "all" || stageFilter === stage) && (board[stage] ?? []).some(ro => [ro.service_number, ro.id, ro.vin, ro.description, ro.technician].join(" ").toLowerCase().includes(query.trim().toLowerCase()))) && <div role="status" className="rounded-xl border border-white/15 p-4"><p>No repair orders match these filters.</p><button onClick={() => { setQuery(""); setStageFilter("all"); }} className="mt-2 text-[var(--app-accent)] underline">Clear filters</button></div>}
      <p className="text-sm text-slate-300">Select an order to review concerns, estimates, parts and quality checks. Your filters stay in place when you return.</p>

      {STAGE_ORDER.map((stage) => {
        if (stageFilter !== "all" && stageFilter !== stage) return null;
        const ros = (board[stage] ?? []).filter(ro => [ro.service_number, ro.id, ro.vin, ro.description, ro.technician].join(" ").toLowerCase().includes(query.trim().toLowerCase()));
        if (ros.length === 0) return null;
        return (
          <ListCard key={stage} title={stage} count={ros.length}>
            {ros.map((ro) => (
              <Row
                key={ro.id}
                onClick={() => setSelected(ro.id)}
                primary={`${ro.service_number || ro.id} · ${ro.description || "Service"}`}
                secondary={[ro.vin, ro.pay_type].filter(Boolean).join(" · ") || undefined}
                meta={<>{ro.technician}<span className="block text-[var(--app-accent)]">Open order →</span></>}
              />
            ))}
          </ListCard>
        );
      })}
    </WiredScreen>{selected && <ServiceOrderDetails key={selected} roId={selected} onClose={() => { setSelected(null); reload(); }} />}</>
  );
}

export function ServiceOrderDetails({ roId, onClose }: { roId: string; onClose: () => void }) {
  const { data, loading, error, reload } = useAsync(() => getRoCatalog(), []);
  if (data && !error) return <RoWorkspaceModal theme="dark" roId={roId} catalog={data} onClose={onClose} onChanged={() => {}} />;
  return <div role="dialog" aria-label="Open repair order" className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 p-4"><div className="rounded-xl bg-slate-900 p-6 text-white">
    <button onClick={onClose} className="mb-4 underline">Back to repair orders</button>
    {loading ? <p role="status">Opening repair order…</p> : <div role="alert"><p>{error || "Unable to open this order."}</p><button onClick={reload} className="mt-4 underline">Try again</button></div>}
  </div></div>;
}
