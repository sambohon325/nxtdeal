"use client";

// Service Operations "Inspections" — the Digital Vehicle Inspection, live off
// core/vehicle_inspection.py. App Suite roadmap Phase 1: the Inspections shell now drives a
// real DVI on a repair order — pick an RO from the live board, start the inspection, mark
// each point green/yellow/red, complete it, and push flagged items to the advisor as real
// Concerns (feeding the RO Concerns→Estimate→Approval pipeline). All existing lib clients.

import { useRef, useState } from "react";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { getRoBoard, type RoBoard, type RoBrief, type RoStage } from "@/lib/repairOrders";
import {
  getInspection,
  startInspection,
  updateInspectionItem,
  completeInspection,
  createConcernsFromInspection,
  type Inspection,
  type InspectionStatus,
} from "@/lib/vehicleInspection";
import { useAsync, WiredScreen, StatGrid, ListCard, Row, EmptyNote, Badge } from "./kit";

const STAGE_ORDER: RoStage[] = [
  "Check-In", "RO Written", "Inspection", "Estimate", "Customer Approval",
  "Parts", "Repair", "Quality Control", "Delivery", "Follow-Up",
];

const STATUS_STYLE: Record<InspectionStatus, string> = {
  green: "bg-emerald-500/80 text-black",
  yellow: "bg-amber-400/90 text-black",
  red: "bg-red-500/90 text-white",
  not_inspected: "bg-white/10 text-zinc-300",
};

export function InspectionsScreen({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data, reload } = useAsync<RoBoard>(() => getRoBoard(), []);

  const [ro, setRo] = useState<RoBrief | null>(null);
  const [inspection, setInspection] = useState<Inspection | null>(null);
  const readVersion = useRef(0);
  const [reading, setReading] = useState(false);
  const [readError, setReadError] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  const board = data ?? ({} as RoBoard);
  // Prioritize ROs in the Inspection stage, then everything else open.
  const inspectionRos = board["Inspection"] ?? [];
  const otherRos = STAGE_ORDER.filter((s) => s !== "Inspection").flatMap((s) => board[s] ?? []);

  async function openRo(brief: RoBrief) {
    const version = ++readVersion.current;
    setReading(true);
    setReadError(false);
    setRo(brief);
    setInspection(null);
    setNote(null);
    try {
      const result = await getInspection(brief.id);
      if (version === readVersion.current) setInspection(result);
    } catch {
      if (version === readVersion.current) setReadError(true);
    } finally {
      if (version === readVersion.current) setReading(false);
    }
  }

  async function start() {
    if (!ro || !inspection || inspection.status !== "not_started" || reading || readError) return;
    setBusy(true);
    try {
      setInspection(await startInspection(ro.id));
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Couldn't start inspection.");
    } finally {
      setBusy(false);
    }
  }

  async function setStatus(itemKey: string, status: InspectionStatus) {
    if (!ro) return;
    setBusy(true);
    try {
      setInspection(await updateInspectionItem(ro.id, itemKey, status, ""));
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Couldn't update item.");
    } finally {
      setBusy(false);
    }
  }

  async function complete() {
    if (!ro) return;
    setBusy(true);
    try {
      setInspection(await completeInspection(ro.id));
      setNote("Inspection completed.");
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Couldn't complete inspection.");
    } finally {
      setBusy(false);
    }
  }

  async function sendFlagged() {
    if (!ro || !inspection) return;
    const flagged = Object.entries(inspection.items)
      .filter(([, it]) => (it.status === "red" || it.status === "yellow") && !it.concern_created)
      .map(([key]) => key);
    if (flagged.length === 0) {
      setNote("No new flagged items to send.");
      return;
    }
    setBusy(true);
    try {
      await createConcernsFromInspection(ro.id, flagged);
      setInspection(await getInspection(ro.id));
      setNote(`Sent ${flagged.length} flagged item(s) to the advisor as concerns.`);
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Couldn't create concerns.");
    } finally {
      setBusy(false);
    }
  }

  // group inspection items by category for display
  const grouped: Record<string, [string, Inspection["items"][string]][]> = {};
  if (inspection) {
    for (const [key, it] of Object.entries(inspection.items)) {
      (grouped[it.category] ||= []).push([key, it]);
    }
  }

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>
      {note && <div className="rounded-xl bg-white/[0.06] px-3 py-2 text-[11px] text-zinc-200">{note}</div>}

      {!ro ? (
        <>
          <StatGrid
            app={app}
            stats={[
              { label: "In Inspection", value: inspectionRos.length },
              { label: "Other open", value: otherRos.length },
            ]}
          />
          <ListCard title="Ready to inspect" count={inspectionRos.length}>
            {inspectionRos.length === 0 && <EmptyNote>No ROs currently in the Inspection stage.</EmptyNote>}
            {inspectionRos.map((r) => (
              <Row key={r.id} onClick={() => openRo(r)} primary={`${r.service_number || r.id} · ${r.description || "Service"}`} secondary={r.vin || undefined} meta={r.technician || undefined} />
            ))}
          </ListCard>
          {otherRos.length > 0 && (
            <ListCard title="Other open ROs" count={otherRos.length}>
              {otherRos.map((r) => (
                <Row key={r.id} onClick={() => openRo(r)} primary={`${r.service_number || r.id} · ${r.description || "Service"}`} secondary={r.ro_stage} meta={r.technician || undefined} />
              ))}
            </ListCard>
          )}
        </>
      ) : (
        <>
          <button onClick={() => { readVersion.current++; setReading(false); setReadError(false); setRo(null); setInspection(null); }} className="text-[11px] text-zinc-400">
            ← Back to ROs
          </button>

          <ListCard title={`${ro.service_number || ro.id} · ${ro.description || "Service"}`}>
            <Row primary={ro.vin || "No VIN"} secondary={ro.ro_stage} meta={inspection ? <Badge app={app}>{inspection.status}</Badge> : reading ? "Loading inspection" : "Unavailable"} />
          </ListCard>

          {reading ? <p role="status" className="text-sm text-zinc-300">Loading inspection…</p> : readError || !inspection ? (
            <div role="alert" className="space-y-2 text-sm text-zinc-300">
              <p>We couldn&apos;t load this inspection. Its current status is unknown.</p>
              <button type="button" onClick={() => openRo(ro)} className="min-h-11 rounded-lg border border-white/20 px-4 py-2">Try again</button>
            </div>
          ) : inspection.status === "not_started" ? (
            <button onClick={start} disabled={busy} className="w-full rounded-full bg-[var(--app-accent)] py-2.5 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-40">
              Start inspection
            </button>
          ) : (
            <>
              <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
                <div className="rounded-lg bg-emerald-500/15 py-1.5 text-emerald-300">{inspection.summary.green ?? 0} green</div>
                <div className="rounded-lg bg-amber-400/15 py-1.5 text-amber-300">{inspection.summary.yellow ?? 0} yellow</div>
                <div className="rounded-lg bg-red-500/15 py-1.5 text-red-300">{inspection.summary.red ?? 0} red</div>
              </div>

              {Object.entries(grouped).map(([category, items]) => (
                <ListCard key={category} title={category} count={items.length}>
                  {items.map(([key, it]) => (
                    <div key={key} className="flex items-center justify-between gap-2 rounded-lg border border-white/5 px-2 py-1.5">
                      <span className="min-w-0 truncate text-[12px] text-zinc-200">{it.item}</span>
                      <div className="flex shrink-0 gap-1">
                        {(["green", "yellow", "red"] as InspectionStatus[]).map((s) => (
                          <button
                            key={s}
                            onClick={() => setStatus(key, s)}
                            disabled={busy}
                            className={`h-6 w-6 rounded-full text-[9px] font-bold ${it.status === s ? STATUS_STYLE[s] : "bg-white/5 text-zinc-500"}`}
                            title={s}
                            aria-label={`${it.item}: ${s}`}
                            aria-pressed={it.status === s}
                          >
                            {s[0].toUpperCase()}
                          </button>
                        ))}
                      </div>
                    </div>
                  ))}
                </ListCard>
              ))}

              <div className="flex gap-2">
                <button onClick={sendFlagged} disabled={busy} className="flex-1 rounded-lg border border-white/20 px-4 py-2 text-sm text-white disabled:opacity-40">
                  Send flagged to advisor
                </button>
                {inspection.status !== "completed" && (
                  <button onClick={complete} disabled={busy} className="flex-1 rounded-full bg-[var(--app-accent)] py-2.5 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-40">
                    Complete
                  </button>
                )}
              </div>
            </>
          )}
        </>
      )}
    </WiredScreen>
  );
}
