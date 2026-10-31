"use client";

import { useEffect, useRef, useState } from "react";
import { startKioskPrivacyTimer } from "@/lib/kioskPrivacy";
import type { AppDef, AppScreen } from "@/lib/apps/registry";
import { publicGetCheckinView, publicSubmitCheckin, type DropOffOrWait, type PublicCheckinView } from "@/lib/appointmentScheduling";
import { useAsync } from "./kit";

const field = "w-full rounded-lg border border-white/10 bg-white/5 px-3 py-3 text-sm text-white";
const button = "rounded-lg border border-white/20 px-4 py-3 text-sm text-white disabled:opacity-40";

export function KioskCheckin({ screen }: { app: AppDef; screen: AppScreen }) {
  const statusOnly = screen.key === "queue";
  const [entry, setEntry] = useState("");
  const [token, setToken] = useState("");
  const [privacyWarning, setPrivacyWarning] = useState(false);
  const privacyTimer = useRef<ReturnType<typeof startKioskPrivacyTimer> | null>(null);
  useEffect(() => {
    if (!token) return;
    const timer = startKioskPrivacyTimer(setPrivacyWarning, () => {
      setToken(""); setEntry(""); setPrivacyWarning(false);
    });
    privacyTimer.current = timer;
    return () => { timer.stop(); privacyTimer.current = null; };
  }, [token]);
  function reset() { setToken(""); setEntry(""); }
  return <section className="space-y-4">
    <h2 className="text-xl font-semibold text-white">{screen.heading}</h2>
    {token && <p className="text-xs text-zinc-400">For your privacy, this screen clears after two minutes without activity. Clearing the screen does not cancel a submitted check-in.</p>}
    {token && privacyWarning && <div role="alert" className="space-y-2 rounded-lg border border-amber-300/30 p-3">
      <p>Your details will clear in 30 seconds without activity.</p>
      <button type="button" className={button} onClick={() => privacyTimer.current?.restart()}>Keep my details on screen</button>
    </div>}
    {!token ? <form className="space-y-3" onSubmit={e => { e.preventDefault(); if (entry.trim()) setToken(entry.trim()); }}>
      <p className="text-sm text-zinc-300">Enter the private check-in code from your appointment link. Ask your advisor for a code if you do not have one.</p>
      <label className="block text-sm text-zinc-300">Appointment check-in code
        <input className={`${field} mt-2`} value={entry} onChange={e => setEntry(e.target.value)} autoComplete="off" autoCapitalize="none" spellCheck={false} required />
      </label>
      <button className={button} disabled={!entry.trim()}>Find my appointment</button>
      <p className="text-xs text-zinc-400">For walk-ins or help finding your appointment, please see the service desk.</p>
    </form> : <Appointment key={token} token={token} onFinish={reset} statusOnly={statusOnly} />}
  </section>;
}

function Appointment({ token, onFinish, statusOnly = false }: { token: string; onFinish: () => void; statusOnly?: boolean }) {
  const request = useAsync(() => publicGetCheckinView(token), [token]);
  const [submitted, setSubmitted] = useState<PublicCheckinView | null>(null);
  const [mode, setMode] = useState<DropOffOrWait>("wait");
  const [contact, setContact] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  const view = submitted ?? request.data;
  const closed = !!view && ["completed", "cancelled", "no_show"].includes(view.status);

  async function submit() {
    if (statusOnly || inFlight.current || !view || view.revoked || view.checkin || closed) return;
    inFlight.current = true;
    setBusy(true); setError(null);
    try { setSubmitted(await publicSubmitCheckin(token, mode, contact.trim(), notes.trim())); }
    catch { setError("Your check-in could not be confirmed. Please try again or ask the service desk."); }
    finally { inFlight.current = false; setBusy(false); }
  }

  return <div className="space-y-4 rounded-xl border border-white/10 bg-white/[0.03] p-4">
    {request.loading ? <p role="status">Looking up your appointment…</p> : request.error || !view ? <div role="alert">
      <p>We could not open this appointment. Check your code or ask the service desk.</p>
      <button className={`${button} mt-3`} onClick={request.reload}>Try again</button>
    </div> : view.revoked ? <p role="alert">This appointment link has been revoked. Please see the service desk.</p> : <>
      <h3 className="text-lg font-medium">{view.person_name ?? "Your appointment"}</h3>
      <p className="text-sm text-zinc-300">{view.department} · {new Date(view.scheduled_start).toLocaleString()}</p>
      {view.vehicle && <p className="text-sm text-zinc-300">{view.vehicle}</p>}
      {statusOnly ? <div className="space-y-3">
        <p role="status">Appointment status: {view.status.replaceAll("_", " ")}</p>
        <p className="text-sm text-zinc-300">{view.checkin ? "Your pre-visit details are saved." : "No pre-visit check-in details have been recorded."} Please see the service desk to confirm your arrival and advisor.</p>
        <p className="text-sm text-zinc-400">Queue position and wait estimates are not available here.</p>
        <button type="button" className={button} onClick={request.reload}>Refresh appointment status</button>
      </div> : closed ? <p role="status">This appointment is {view.status.replaceAll("_", " ")}. Please see the service desk.</p> : view.checkin ? <p role="status" className="text-[var(--app-accent)]">Your pre-visit details are saved. Please let the service desk know you have arrived.</p> : <form onSubmit={e => { e.preventDefault(); void submit(); }} className="space-y-3" aria-busy={busy}>
        <label className="block text-sm">Your visit
          <select className={`${field} mt-1`} value={mode} onChange={e => setMode(e.target.value as DropOffOrWait)} disabled={busy}>
            <option value="wait">I will wait</option><option value="drop_off">I will drop off my vehicle</option>
          </select>
        </label>
        <label className="block text-sm">Preferred contact method (optional)
          <input className={`${field} mt-1`} maxLength={200} value={contact} onChange={e => setContact(e.target.value)} disabled={busy} autoComplete="off" />
        </label>
        <label className="block text-sm">Visit notes (optional)
          <textarea className={`${field} mt-1`} maxLength={2000} value={notes} onChange={e => setNotes(e.target.value)} disabled={busy} />
        </label>
        {error && <p role="alert" className="text-amber-200">{error}</p>}
        <button className={button} disabled={busy}>{busy ? "Saving…" : "Save check-in details"}</button>
      </form>}
    </>}
    <button type="button" onClick={onFinish} disabled={busy} className={button}>Finish and clear my details</button>
  </div>;
}
