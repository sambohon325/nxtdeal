"use client";
import { WorkButton, WorkInput } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Operations' "Scheduling" item (session 106 follow-up #5) -- Recon
// Scheduling, Delivery Scheduling with automatic risk detection, Transport
// Scheduling. Backend: core/operations_scheduling.py / _api.py.

import { useEffect, useState } from "react";
import {
  getReconSchedule,
  scheduleRecon,
  getDeliveryRiskBoard,
  scheduleDelivery,
  getTransportSchedule,
  updateTransportStatus,
  type ReconSchedule,
  type DeliveryRiskBoard,
  type DeliveryRiskDeal,
  type TransportSchedule,
  type TransportTransaction,
} from "@/lib/operationsScheduling";
import { EntityHoverLink } from "@/components/EntityHoverLink";

type Theme = "dark" | "light";
type Tab = "recon" | "delivery" | "transport";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function ReconTab({ theme }: { theme: Theme }) {
  const [data, setData] = useState<ReconSchedule | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [dates, setDates] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getReconSchedule().then(setData).catch((e) => setError((e as Error).message)).finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const inputClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white", "bg-white border-zinc-300 text-black");

  async function handleSchedule(vehicleId: string) {
    const date = dates[vehicleId];
    if (!date) {
      setError("Pick a target date first.");
      return;
    }
    setBusyId(vehicleId);
    setError(null);
    try {
      await scheduleRecon(vehicleId, date);
      setMessage(`Recon scheduled for ${date}.`);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="text-sm text-zinc-500" role="status">Loading…</div>;
  if (!data) return <div role="alert"><p>{error || "Unable to load records."}</p><WorkButton type="submit" onClick={refresh}>Try again</WorkButton></div>;

  return (
    <div className="space-y-3">
      {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
      {message && <div className="text-xs px-3 py-2 rounded-lg bg-green-500/15 border border-green-500/40 text-green-300">{message}</div>}
      <div className="text-xs text-zinc-600 italic">{data.note}</div>
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(data.by_lot).map(([lot, count]) => (
          <span key={lot} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300">{lot}: {count}</span>
        ))}
      </div>
      <div className="space-y-1.5">
        {data.vehicles.map((v) => (
          <div key={v.vehicle_id} className={tc(theme, "rounded-lg border border-zinc-800 bg-black/20 p-2.5 flex items-center justify-between gap-2", "rounded-lg border border-zinc-200 bg-white p-2.5 flex items-center justify-between gap-2")}>
            <div className="min-w-0">
              <div className="text-xs font-medium truncate">{v.year} {v.make} {v.model}</div>
              <div className="text-xs text-zinc-500 truncate">{v.stock_number} · {v.lot}</div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <WorkInput
                type="date"
                aria-label={`Recon target date for ${v.vehicle_id}`} value={dates[v.vehicle_id] || ""}
                onChange={(e) => setDates((prev) => ({ ...prev, [v.vehicle_id]: e.target.value }))}
                className={`rounded-md border px-2 py-1 text-xs ${inputClass}`}
              />
              <WorkButton type="submit" variant="primary" disabled={busyId === v.vehicle_id} onClick={() => handleSchedule(v.vehicle_id)} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Schedule</WorkButton>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function DeliveryDealRow({ theme, deal, onScheduled }: { theme: Theme; deal: DeliveryRiskDeal; onScheduled: () => void }) {
  const [start, setStart] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white", "bg-white border-zinc-300 text-black");

  async function handleSchedule() {
    if (!start) {
      setError("Pick a date/time first.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await scheduleDelivery(deal.deal_id, new Date(start).toISOString());
      onScheduled();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-black/20 p-2.5", "rounded-lg border border-zinc-200 bg-white p-2.5")}>
      <div className="flex items-center justify-between gap-2">
        <div className="text-xs"><EntityHoverLink id={deal.deal_id} /> — {deal.vehicle_id && <EntityHoverLink id={deal.vehicle_id} />} <span className="text-zinc-500">({deal.status})</span></div>
        {deal.scheduled_start && <span className="text-xs text-zinc-500">scheduled: {new Date(deal.scheduled_start).toLocaleString()}</span>}
      </div>
      {error && <div className="text-xs text-red-400 mt-1">{error}</div>}
      <div className="flex items-center gap-1.5 mt-1.5">
        <WorkField label="Start date and time"><WorkInput type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className={`rounded-md border px-2 py-1 text-xs ${inputClass}`} /></WorkField>
        <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleSchedule} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          {deal.appointment_id ? "Reschedule" : "Schedule Delivery"}
        </WorkButton>
      </div>
    </div>
  );
}

function DeliveryTab({ theme }: { theme: Theme }) {
  const [data, setData] = useState<DeliveryRiskBoard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getDeliveryRiskBoard().then(setData).catch((e) => setError((e as Error).message)).finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  if (loading) return <div className="text-sm text-zinc-500" role="status">Loading…</div>;
  if (!data) return <div role="alert"><p>{error || "Unable to load records."}</p><WorkButton type="submit" onClick={refresh}>Try again</WorkButton></div>;

  return (
    <div className="space-y-4">
      {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
      <div className="text-xs text-zinc-600 italic">{data.note}</div>

      <div>
        <div className="text-xs font-brand uppercase tracking-wide text-red-400 mb-1.5">Overdue ({data.overdue.count})</div>
        <div className="space-y-1.5">
          {data.overdue.deals.length === 0 ? <div className="text-xs text-zinc-600">None overdue.</div> : data.overdue.deals.map((d) => <DeliveryDealRow key={d.deal_id} theme={theme} deal={d} onScheduled={refresh} />)}
        </div>
      </div>

      <div>
        <div className="text-xs font-brand uppercase tracking-wide text-amber-400 mb-1.5">No Delivery Scheduled ({data.no_delivery_scheduled.count})</div>
        <div className="space-y-1.5">
          {data.no_delivery_scheduled.deals.length === 0 ? <div className="text-xs text-zinc-600">All caught up.</div> : data.no_delivery_scheduled.deals.map((d) => <DeliveryDealRow key={d.deal_id} theme={theme} deal={d} onScheduled={refresh} />)}
        </div>
      </div>

      <div>
        <div className="text-xs font-brand uppercase tracking-wide text-green-400 mb-1.5">On Track ({data.on_track.count})</div>
        <div className="space-y-1.5">
          {data.on_track.deals.length === 0 ? <div className="text-xs text-zinc-600">None yet.</div> : data.on_track.deals.map((d) => <DeliveryDealRow key={d.deal_id} theme={theme} deal={d} onScheduled={refresh} />)}
        </div>
      </div>
    </div>
  );
}

const TRANSPORT_LABELS: Record<TransportTransaction["transport_status"], string> = {
  at_auction_yard: "At Auction Yard",
  in_transit: "In Transit",
  delivered: "Delivered",
};

const NEXT_STATUS: Record<TransportTransaction["transport_status"], TransportTransaction["transport_status"] | null> = {
  at_auction_yard: "in_transit",
  in_transit: "delivered",
  delivered: null,
};

function TransportTab({ theme }: { theme: Theme }) {
  const [data, setData] = useState<TransportSchedule | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getTransportSchedule().then(setData).catch((e) => setError((e as Error).message)).finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function advance(t: TransportTransaction) {
    const next = NEXT_STATUS[t.transport_status];
    if (!next) return;
    setBusyId(t.id);
    setError(null);
    try {
      await updateTransportStatus(t.id, next);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="text-sm text-zinc-500" role="status">Loading…</div>;
  if (!data) return <div role="alert"><p>{error || "Unable to load records."}</p><WorkButton type="submit" onClick={refresh}>Try again</WorkButton></div>;

  return (
    <div className="space-y-3">
      {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
      <div className="flex flex-wrap gap-1.5">
        {Object.entries(data.by_transport_status).map(([status, count]) => (
          <span key={status} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300">{TRANSPORT_LABELS[status as TransportTransaction["transport_status"]] || status}: {count}</span>
        ))}
      </div>
      <div className="space-y-1.5">
        {data.transactions.map((t) => (
          <div key={t.id} className={tc(theme, "rounded-lg border border-zinc-800 bg-black/20 p-2.5 flex items-center justify-between gap-2", "rounded-lg border border-zinc-200 bg-white p-2.5 flex items-center justify-between gap-2")}>
            <div className="min-w-0">
              <div className="text-xs font-medium truncate"><EntityHoverLink id={t.vehicle_id} /> · {t.auction_house}</div>
              <div className="text-xs text-zinc-500 truncate">{t.carrier || "no carrier on file"} {t.expected_arrival ? `· ETA ${t.expected_arrival}` : ""}</div>
            </div>
            <div className="flex items-center gap-1.5 shrink-0">
              <span className={`text-xs px-1.5 py-0.5 rounded ${t.transport_status === "delivered" ? "bg-green-950/40 text-green-300" : t.transport_status === "in_transit" ? "bg-blue-950/40 text-blue-300" : "bg-zinc-800 text-zinc-400"}`}>{TRANSPORT_LABELS[t.transport_status]}</span>
              {NEXT_STATUS[t.transport_status] && (
                <WorkButton type="submit" variant="primary" disabled={busyId === t.id} onClick={() => advance(t)} className="text-xs px-2 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
                  Mark {TRANSPORT_LABELS[NEXT_STATUS[t.transport_status]!]}
                </WorkButton>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function OperationsSchedulingBoard({ theme, initialTab = "recon" }: { theme: Theme; initialTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "flex items-center gap-1.5 p-3 border-b border-zinc-800", "flex items-center gap-1.5 p-3 border-b border-zinc-200")}>
        {(["recon", "delivery", "transport"] as Tab[]).map((t) => (
          <WorkButton data-work-view aria-pressed={tab === t} type="submit"
            key={t}
            onClick={() => setTab(t)}
            className={`text-xs px-3 py-1.5 rounded font-medium capitalize ${tab === t ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-300"}`}
          >
            {t === "recon" ? "Recon Scheduling" : t === "delivery" ? "Delivery Scheduling" : "Transport Scheduling"}
          </WorkButton>
        ))}
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {tab === "recon" && <ReconTab theme={theme} />}
        {tab === "delivery" && <DeliveryTab theme={theme} />}
        {tab === "transport" && <TransportTab theme={theme} />}
      </div>
    </div>
  );
}
