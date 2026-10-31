"use client";
import {RecordTable} from "./RecordTable";
import { WorkButton, WorkInput , WorkStat, WorkOverlay} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";

// Inventory department's "Lot Management" item -- physical inventory
// control (Inventory rebuild, fifth slice). Real Lot Map (row/space
// positions), Key Management (checkout/checkin/missing), Damage Reports,
// and Showroom Assignments -- all REAL features, not simulated, since
// these are internal tracking capabilities this codebase simply hadn't
// built yet rather than external data this system can't obtain.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getLotMap,
  getKeyBoard,
  getShowroomBoard,
  listDamageReports,
  updateDamageStatus,
  getLotControlView,
  setLotPosition,
  checkoutKey,
  checkinKey,
  reportKeyMissing,
  reportDamage,
  assignShowroom,
  removeShowroomAssignment,
  logScan,
  type LotMap,
  type KeyBoard,
  type ShowroomBoard,
  type DamageReport,
  type LotControlView,
  type DamageSeverity,
} from "@/lib/lotControl";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const SEVERITY_TONE: Record<DamageSeverity, string> = {
  minor: "bg-blue-950/40 text-blue-300",
  moderate: "bg-amber-950/40 text-amber-300",
  severe: "bg-red-950/40 text-red-300",
};

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function VehicleDetailModal({ theme, vehicleId, onClose, onChanged }: { theme: Theme; vehicleId: string; onClose: () => void; onChanged: () => void }) {
  const [data, setData] = useState<LotControlView | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [row, setRow] = useState("");
  const [space, setSpace] = useState("");
  const [section, setSection] = useState("");
  const [holder, setHolder] = useState("");
  const [severity, setSeverity] = useState<DamageSeverity>("minor");
  const [description, setDescription] = useState("");
  const [estCost, setEstCost] = useState("");

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function refresh() {
    setLoading(true);
    setError(null);
    getLotControlView(vehicleId)
      .then((v) => {
        setData(v);
        setRow(v.lot_position?.row || "");
        setSpace(v.lot_position?.space || "");
        setSection(v.lot_position?.section || "");
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [vehicleId]);

  async function withBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      refresh();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading || !data) {
    return (
      <WorkOverlay className="work-inventory-detail">
        <div onClick={(e) => e.stopPropagation()} className={tc(theme, "rounded-xl border border-black/20 bg-brand-ink text-white p-5", "rounded-xl border border-zinc-200 bg-white text-black p-5")}>
          {loading ? <div className="text-sm text-zinc-500" role="status">Loading…</div> : <div role="alert"><p>{error || "Unable to load this record."}</p><WorkButton type="submit" onClick={refresh}>Try again</WorkButton></div>}
          <WorkButton type="submit" onClick={onClose}>Back to lot management</WorkButton>
        </div>
      </WorkOverlay>
    );
  }

  const { vehicle, lot_position, key_status, damage_reports, showroom_assignment, scan_log } = data;

  return (
    <WorkOverlay className="work-inventory-detail">
      <div onClick={(e) => e.stopPropagation()} className={tc(theme, "w-full rounded-xl border border-black/20 bg-brand-ink text-white p-5 space-y-3", "w-full rounded-xl border border-zinc-200 bg-white text-black p-5 space-y-3")}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-brand uppercase tracking-wide">
              {vehicle.year} {vehicle.make} {vehicle.model}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">{vehicle.vehicle_id} · Lot {vehicle.lot || "—"} · Stock #{vehicle.stock_number || "—"}</div>
          </div>
          <WorkButton type="submit" onClick={onClose} className="text-xs text-zinc-500 hover:text-white transition">Back to lot management</WorkButton>
        </div>

        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Lot Position</div>
          <div className="text-xs mb-2 text-zinc-400">
            {lot_position ? `Row ${lot_position.row || "—"}, Space ${lot_position.space || "—"}${lot_position.section ? `, ${lot_position.section}` : ""}` : "Not yet positioned"}
          </div>
          <div className="grid grid-cols-3 gap-1.5 mb-2">
            <WorkField label="Row"><WorkInput value={row} onChange={(e) => setRow(e.target.value)} placeholder="Row" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
            <WorkField label="Space"><WorkInput value={space} onChange={(e) => setSpace(e.target.value)} placeholder="Space" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
            <WorkField label="Section"><WorkInput value={section} onChange={(e) => setSection(e.target.value)} placeholder="Section" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          </div>
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withBusy(() => setLotPosition(vehicleId, row, space, section))} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Update Position</WorkButton>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Key Management</div>
          <div className="text-xs mb-2 text-zinc-400">
            Status: <span className="capitalize">{key_status.status.replace("_", " ")}</span>{key_status.holder ? ` · Held by ${key_status.holder}` : ""}
          </div>
          {key_status.status === "on_lot" ? (
            <div className="flex items-center gap-1.5 mb-2">
              <WorkField label="Checking out to"><WorkInput value={holder} onChange={(e) => setHolder(e.target.value)} placeholder="Checking out to…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
              <WorkButton type="submit" variant="primary" disabled={busy || !holder.trim()} onClick={() => withBusy(() => checkoutKey(vehicleId, holder))} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50 whitespace-nowrap">Check Out</WorkButton>
            </div>
          ) : (
            <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withBusy(() => checkinKey(vehicleId))} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50 mr-1.5">{key_status.status === "missing" ? "Mark Found & Check In" : "Check In"}</WorkButton>
          )}
          <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => withBusy(() => reportKeyMissing(vehicleId, "Reported via Lot Management"))} className="text-xs px-2.5 py-1.5 rounded bg-red-600 text-white font-medium hover:opacity-90 transition disabled:opacity-50">Report Missing</WorkButton>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Damage Reports</div>
          <div className="space-y-1 mb-2">
            {damage_reports.map((d) => (
              <div key={d.id} className="flex items-center justify-between text-xs">
                <span className={`px-1.5 py-0.5 rounded text-xs capitalize ${SEVERITY_TONE[d.severity]}`}>{d.severity}</span>
                <span className="flex-1 mx-2 truncate">{d.description}</span>
                <span className="text-zinc-500 capitalize">{d.status}</span>
              </div>
            ))}
            {damage_reports.length === 0 && <div className="text-xs text-zinc-500">No damage reports on file.</div>}
          </div>
          <div className="flex items-center gap-1.5 mb-1.5">
            {(["minor", "moderate", "severe"] as const).map((s) => (
              <WorkButton type="submit"  key={s} onClick={() => setSeverity(s)} className={`text-xs px-2.5 py-1 rounded-full capitalize transition ${severity === s ? "bg-brand-blue text-white" : "bg-zinc-200/10 text-zinc-400"}`}>{s}</WorkButton>
            ))}
          </div>
          <WorkField label="Damage description"><WorkInput value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Damage description…" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-1.5 ${textClass}`} /></WorkField>
          <WorkField label="Estimated cost ($, optional)"><WorkInput value={estCost} onChange={(e) => setEstCost(e.target.value)} type="number" placeholder="Estimated cost ($, optional)" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`} /></WorkField>
          <WorkButton type="submit" variant="primary" disabled={busy || !description.trim()} onClick={() => withBusy(() => reportDamage(vehicleId, severity, description, estCost ? parseFloat(estCost) : undefined))} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Report Damage</WorkButton>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Showroom Assignment</div>
          <div className="text-xs mb-2 text-zinc-400">{showroom_assignment?.assigned ? "Currently assigned to showroom" : "Not on showroom"}</div>
          {showroom_assignment?.assigned ? (
            <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => withBusy(() => removeShowroomAssignment(vehicleId))} className="text-xs px-2.5 py-1.5 rounded bg-red-600 text-white font-medium hover:opacity-90 transition disabled:opacity-50">Remove from Showroom</WorkButton>
          ) : (
            <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withBusy(() => assignShowroom(vehicleId, "Assigned via Lot Management"))} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Assign to Showroom</WorkButton>
          )}
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Check-In / Scan Log</div>
          <div className="space-y-1 mb-2">
            <RecordCollection>{scan_log.slice().reverse().map((s, i) => (
              <div key={i} className="text-xs text-zinc-400">{fmt(s.at)} · {s.location_note || "no location note"}</div>
            ))}</RecordCollection>
            {scan_log.length === 0 && <div className="text-xs text-zinc-500">No scans logged yet.</div>}
          </div>
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => withBusy(() => logScan(vehicleId, "Logged via Lot Management"))} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Log a Scan</WorkButton>
        </div>
      </div>
    </WorkOverlay>
  );
}

export function LotControlBoard({ theme, initialTab = "map" }: { theme: Theme; initialTab?: "map" | "keys" | "damage" | "showroom" }) {
  const [tab, setTab] = useState<"map" | "keys" | "damage" | "showroom">(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);
  const [lotMap, setLotMap] = useState<LotMap | null>(null);
  const [keyBoard, setKeyBoard] = useState<KeyBoard | null>(null);
  const [showroomBoard, setShowroomBoard] = useState<ShowroomBoard | null>(null);
  const [damageReports, setDamageReports] = useState<DamageReport[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    Promise.all([getLotMap(), getKeyBoard(), getShowroomBoard(), listDamageReports(undefined, "open")])
      .then(([lm, kb, sb, dr]) => {
        setLotMap(lm);
        setKeyBoard(kb);
        setShowroomBoard(sb);
        setDamageReports(dr.reports);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleResolve(reportId: string) {
    try {
      await updateDamageStatus(reportId, "resolved", "Resolved via Lot Management");
      refresh();
    } catch {
      // surfaced implicitly by refresh not updating; keep it simple here
    }
  }

  return (
    <div className={tc(theme, "work-inventory-board", "work-inventory-board")}>
      <div hidden={!!selected}>
      <div className={tc(theme, "work-inventory-stats", "work-inventory-stats")}>
        <Kpi theme={theme} label="Unsold Vehicles" value={String(lotMap?.total_unsold || 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Keys Checked Out" value={String(keyBoard?.checked_out.length || 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Open Damage Reports" value={String(damageReports.length)} color={RIBBON[2]} />
        <Kpi theme={theme} label="On Showroom" value={String(showroomBoard?.count || 0)} color={RIBBON[3]} />
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {([
          ["map", "Lot Map"],
          ["keys", "Key Management"],
          ["damage", "Damage Reports"],
          ["showroom", "Showroom"],
        ] as const).map(([key, label]) => (
          <WorkButton data-work-view aria-pressed={tab === key} type="submit"
            key={key}
            onClick={() => setTab(key)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${tab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {label}
          </WorkButton>
        ))}
      </div>

      <div className="flex-1 p-4">
        {loading ? (
          <div className="text-sm text-zinc-500" role="status">Loading…</div>
        ) : tab === "map" ? (
          <div className="work-stack">{Object.entries(lotMap?.by_lot||{}).map(([lot,vehicles])=><section key={lot}><h3>{lot} ({vehicles.length})</h3><RecordTable label={`${lot} vehicles`}><thead><tr><th>Vehicle</th><th>Position</th><th>Next step</th></tr></thead><tbody>{vehicles.map(v=><tr key={v.vehicle_id}><td><strong>{v.year} {v.make} {v.model}</strong><span className="work-record-meta">{v.vehicle_id}</span></td><td>{v.lot_position?`Row ${v.lot_position.row||"Not set"}, Space ${v.lot_position.space||"Not set"}`:"Unpositioned"}</td><td><WorkButton onClick={()=>setSelected(v.vehicle_id)}>Open vehicle</WorkButton></td></tr>)}</tbody></RecordTable></section>)}</div>
        ) : tab === "keys" ? (
          <div className="work-stack"><section><h3>Checked-out keys</h3><RecordTable label="Checked-out keys"><thead><tr><th>Vehicle</th><th>Held by</th><th>Next step</th></tr></thead><tbody>{keyBoard?.checked_out.map(v=><tr key={v.vehicle_id}><td>{v.year} {v.make} {v.model}</td><td>{v.key_status.holder}</td><td><WorkButton onClick={()=>setSelected(v.vehicle_id)}>Review keys</WorkButton></td></tr>)}</tbody></RecordTable>{!keyBoard?.checked_out.length&&<p>No keys currently checked out.</p>}</section><section><h3>Missing keys</h3><RecordTable label="Missing keys"><thead><tr><th>Vehicle</th><th>Next step</th></tr></thead><tbody>{keyBoard?.missing.map(v=><tr key={v.vehicle_id}><td>{v.year} {v.make} {v.model}</td><td><WorkButton onClick={()=>setSelected(v.vehicle_id)}>Review keys</WorkButton></td></tr>)}</tbody></RecordTable>{!keyBoard?.missing.length&&<p>No missing keys.</p>}</section></div>
        ) : tab === "damage" ? (
          <RecordTable label="Damage reports"><thead><tr><th>Vehicle</th><th>Damage</th><th>Estimated cost</th><th>Reported</th><th>Actions</th></tr></thead><tbody>{damageReports.map(d=><tr key={d.id}><td><WorkButton onClick={()=>setSelected(d.vehicle_id)}>{d.vehicle_id}</WorkButton></td><td>{d.description}<span className="work-record-meta">{d.severity}</span></td><td>{d.estimated_cost?`$${d.estimated_cost.toLocaleString()}`:"Not estimated"}</td><td>{fmt(d.reported_at)}</td><td><WorkButton onClick={()=>handleResolve(d.id)}>Mark resolved</WorkButton></td></tr>)}</tbody></RecordTable>
        ) : (
          <RecordTable label="Showroom vehicles"><thead><tr><th>Vehicle</th><th>Notes</th><th>Next step</th></tr></thead><tbody>{showroomBoard?.vehicles.map(v=><tr key={v.vehicle_id}><td>{v.year} {v.make} {v.model}</td><td>{v.showroom_assignment?.notes||"No notes"}</td><td><WorkButton onClick={()=>setSelected(v.vehicle_id)}>Open vehicle</WorkButton></td></tr>)}</tbody></RecordTable>
        )}
      </div>

      </div>
      {selected && (
        <VehicleDetailModal theme={theme} vehicleId={selected} onClose={() => setSelected(null)} onChanged={refresh} />
      )}
    </div>
  );
}
