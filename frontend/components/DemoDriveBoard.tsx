"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Demo Drive (session 102 follow-up) -- rendered inside Sales' "Demo Drive" workflow
// modal (core/workflow_catalog.py's sales.demo_drive). A real keys-out board: log a
// test drive with a verified license (the enforced compliance gate -- the backend
// refuses to start a drive without it), watch which vehicles are currently off the
// lot, and close each one out with an odometer reading and a buying-interest signal.
// Fourth of Sam's ~10 "completely missing" dealership workflows; follows the same
// bespoke-action-component pattern as UpSystemBoard/BdcBoard (session 100).
//
// Session 102 direct follow-up (Sam: "the tabs... need to work... a working process,
// not just a list") -- split into a `section` prop matching Demo Drive's 5 named tabs
// instead of rendering the whole board identically on every one of them. Keys-Out
// Board is now a read-only monitoring view; Return & Odometer is where the actual
// return/cancel actions live; Interest & Follow-Up is a new real history of returned
// drives (core/demo_drive.py's list_demo_drives, status="returned").
import { useEffect, useState } from "react";
import {
  getDemoDriveDashboard,
  listDemoDrives,
  startDemoDrive,
  returnDemoDrive,
  cancelDemoDrive,
  type DemoDriveDashboard,
  type DemoDrive,
  type InterestLevel,
} from "@/lib/demoDrive";

export type DemoDriveSection = "board" | "log" | "license" | "return" | "interest";

const INTEREST: InterestLevel[] = ["hot", "warm", "cold"];

const INTEREST_TONE: Record<string, string> = {
  hot: "text-red-300",
  warm: "text-amber-300",
  cold: "text-sky-300",
};

function fmt(ts: string | null): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function ReturnRow({ demo, onDone, onError }: { demo: DemoDrive; onDone: () => void; onError: (m: string) => void }) {
  const [open, setOpen] = useState(false);
  const [odo, setOdo] = useState("");
  const [interest, setInterest] = useState<InterestLevel>("warm");
  const [feedback, setFeedback] = useState("");
  const [busy, setBusy] = useState(false);

  async function submitReturn() {
    setBusy(true);
    try {
      await returnDemoDrive(demo.id, {
        odometer_in: odo.trim() ? Number(odo) : null,
        interest_level: interest,
        feedback: feedback.trim() || undefined,
      });
      onDone();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Unable to return.");
    } finally {
      setBusy(false);
    }
  }

  async function doCancel() {
    setBusy(true);
    try {
      await cancelDemoDrive(demo.id);
      onDone();
    } catch (e) {
      onError(e instanceof Error ? e.message : "Unable to cancel.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/40 p-2">
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-medium text-zinc-200 truncate">
            {demo.driver_label} · {demo.vehicle_label}
          </div>
          <div className="text-xs text-zinc-500 truncate">
            with {demo.salesperson_name || demo.salesperson_id}
            {demo.odometer_out !== null ? ` · out @ ${demo.odometer_out} mi` : ""}
            {demo.license_verified ? " · ✓ license" : " · ⚠ no license"}
          </div>
        </div>
        <div className="flex gap-1.5 shrink-0">
          <WorkButton type="submit"
            onClick={() => setOpen((o) => !o)}
            className="bg-zinc-200 text-black font-medium rounded px-2 py-0.5 text-xs"
          >
            Return
          </WorkButton>
          <WorkButton type="submit"
            onClick={doCancel}
            disabled={busy}
            className="bg-zinc-800 border border-zinc-700 text-zinc-300 rounded px-2 py-0.5 text-xs disabled:opacity-40"
          >
            Cancel
          </WorkButton>
        </div>
      </div>

      {open && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <WorkField label="Odometer in"><WorkInput
            value={odo}
            onChange={(e) => setOdo(e.target.value)}
            inputMode="numeric"
            placeholder="Odometer in"
            className="w-28 bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
          /></WorkField>
          <WorkField label="Interest"><WorkSelect
            value={interest}
            onChange={(e) => setInterest(e.target.value as InterestLevel)}
            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200"
          >
            {INTEREST.map((i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </WorkSelect></WorkField>
          <WorkField label="Feedback (optional)"><WorkInput
            value={feedback}
            onChange={(e) => setFeedback(e.target.value)}
            placeholder="Feedback (optional)"
            className="flex-1 min-w-[140px] bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
          /></WorkField>
          <WorkButton type="submit"
            onClick={submitReturn}
            disabled={busy}
            className="bg-emerald-900/50 border border-emerald-800 text-emerald-200 rounded px-2 py-1 text-xs disabled:opacity-40"
          >
            {busy ? "…" : "Confirm Return"}
          </WorkButton>
        </div>
      )}
    </div>
  );
}

export function DemoDriveBoard({ section = "board" }: { section?: DemoDriveSection }) {
  const [data, setData] = useState<DemoDriveDashboard | null>(null);
  const [returned, setReturned] = useState<DemoDrive[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // Log-a-drive form
  const [leadId, setLeadId] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [salespersonId, setSalespersonId] = useState("");
  const [license, setLicense] = useState("");
  const [verified, setVerified] = useState(false);
  const [odoOut, setOdoOut] = useState("");
  const [notes, setNotes] = useState("");

  function refresh() {
    setLoading(true);
    Promise.all([getDemoDriveDashboard(), listDemoDrives("returned")])
      .then(([d, r]) => {
        setData(d);
        setReturned(r);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the demo drive board."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function logDrive() {
    if (!leadId.trim() || !vehicleId.trim() || !salespersonId.trim()) return;
    setBusy(true);
    try {
      await startDemoDrive({
        linked_entity_id: leadId.trim(),
        vehicle_id: vehicleId.trim(),
        salesperson_id: salespersonId.trim(),
        license_number: license.trim(),
        license_verified: verified,
        odometer_out: odoOut.trim() ? Number(odoOut) : null,
        notes: notes.trim() || undefined,
      });
      setLeadId("");
      setVehicleId("");
      setSalespersonId("");
      setLicense("");
      setVerified(false);
      setOdoOut("");
      setNotes("");
      setError(null);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to log the drive.");
    } finally {
      setBusy(false);
    }
  }

  const stats = data?.stats;

  if (loading) {
    return <div className="mb-5 text-xs text-zinc-600">Loading…</div>;
  }

  const logForm = (
    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
      <div className="text-xs font-medium text-zinc-200 mb-1.5">Log a Drive</div>
      <div className="grid grid-cols-3 gap-2 mb-2">
        <WorkField label="Lead / Customer ID"><WorkInput value={leadId} onChange={(e) => setLeadId(e.target.value)} placeholder="Lead / Customer ID"
          className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600" /></WorkField>
        <WorkField label="Vehicle ID (VEH-…)"><WorkInput value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} placeholder="Vehicle ID (VEH-…)"
          className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600" /></WorkField>
        <WorkField label="Salesperson ID (EMP-…)"><WorkInput value={salespersonId} onChange={(e) => setSalespersonId(e.target.value)} placeholder="Salesperson ID (EMP-…)"
          className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600" /></WorkField>
        <WorkField label="License #"><WorkInput value={license} onChange={(e) => setLicense(e.target.value)} placeholder="License #"
          className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600" /></WorkField>
        <WorkField label="Odometer out"><WorkInput value={odoOut} onChange={(e) => setOdoOut(e.target.value)} inputMode="numeric" placeholder="Odometer out"
          className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600" /></WorkField>
        <WorkField label="Notes"><WorkInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes"
          className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600" /></WorkField>
      </div>
      <div className="flex items-center justify-between gap-2">
        <label className="flex items-center gap-1.5 text-xs text-zinc-300">
          <WorkInput type="checkbox" checked={verified} onChange={(e) => setVerified(e.target.checked)} />
          Driver&rsquo;s license verified (required)
        </label>
        <WorkButton type="submit"
          onClick={logDrive}
          disabled={busy || !leadId.trim() || !vehicleId.trim() || !salespersonId.trim() || !verified}
          className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
        >
          {busy ? "…" : "Start Drive"}
        </WorkButton>
      </div>
    </div>
  );

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}

      {section === "board" && (
        <>
          <div className="grid grid-cols-4 gap-2 mb-3">
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{stats ? stats.active : "—"}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Keys Out</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">
                {stats && stats.avg_duration_minutes !== null ? `${stats.avg_duration_minutes}m` : "—"}
              </div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Avg Drive</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">
                {stats && stats.avg_miles_driven !== null ? `${stats.avg_miles_driven}` : "—"}
              </div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Avg Miles</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">
                {stats && stats.license_verified_pct !== null ? `${stats.license_verified_pct}%` : "—"}
              </div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">License ✓</div>
            </div>
          </div>
          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Currently Out ({data?.active.length ?? 0})</div>
            {!data || data.active.length === 0 ? (
              <div className="text-xs text-zinc-600">No vehicles out on a demo drive right now.</div>
            ) : (
              <div className="space-y-1.5">
                {data.active.map((d) => (
                  <div key={d.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800">
                    <div className="text-zinc-200">{d.driver_label} · {d.vehicle_label}</div>
                    <div className="text-zinc-500">
                      with {d.salesperson_name || d.salesperson_id} · out {fmt(d.start_at)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {section === "log" && logForm}

      {section === "license" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">License Verification</div>
          <p className="text-xs text-zinc-500 leading-relaxed mb-3">
            A drive can&rsquo;t start without the license-verified box checked -- the backend
            enforces this, not just the form. This is a captured flag confirming a real
            license was seen and checked, not a DMV/AAMVA database validation (no such
            API is connected here).
          </p>
          <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800 inline-block">
            <div className="text-lg font-semibold text-zinc-100">
              {stats && stats.license_verified_pct !== null ? `${stats.license_verified_pct}%` : "—"}
            </div>
            <div className="text-xs text-zinc-500 uppercase tracking-wide">Verified Across All Logged Drives</div>
          </div>
        </div>
      )}

      {section === "return" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Return &amp; Odometer ({data?.active.length ?? 0} out)</div>
          {!data || data.active.length === 0 ? (
            <div className="text-xs text-zinc-600">No vehicles out on a demo drive right now.</div>
          ) : (
            <div className="space-y-1.5">
              {data.active.map((d) => (
                <ReturnRow key={d.id} demo={d} onDone={refresh} onError={setError} />
              ))}
            </div>
          )}
        </div>
      )}

      {section === "interest" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Interest &amp; Follow-Up ({returned.length})</div>
          {returned.length === 0 ? (
            <div className="text-xs text-zinc-600">No completed drives yet.</div>
          ) : (
            <div className="space-y-1.5">
              {returned.map((d) => (
                <div key={d.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-zinc-200 truncate">{d.driver_label} · {d.vehicle_label}</div>
                    {d.interest_level && (
                      <span className={`shrink-0 uppercase text-xs ${INTEREST_TONE[d.interest_level]}`}>{d.interest_level}</span>
                    )}
                  </div>
                  <div className="text-zinc-500">
                    {d.miles_driven !== null ? `${d.miles_driven} mi · ` : ""}
                    {d.duration_minutes !== null ? `${d.duration_minutes}m · ` : ""}
                    returned {fmt(d.end_at)}
                  </div>
                  {d.feedback && <div className="text-zinc-400 mt-0.5">&ldquo;{d.feedback}&rdquo;</div>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
