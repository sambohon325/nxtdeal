"use client";

// Receptionist "Check-In" — the front desk logs a walk-in (name, phone, reason) which drops a
// real walk-in up into the sales floor rotation (lib/upSystem.logUp). Delivery is not confirmed.
// Shows who's up next so the receptionist can point the visitor the right way. This is the
// staff-driven twin of the customer-facing "Away from desk" kiosk screen.

import { useRef, useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import { logUp, getRotation, type Up, type Rotation } from "@/lib/upSystem";
import { useAsync, WiredScreen } from "./kit";

export function ReceptionCheckin({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  const rotation = useAsync<Rotation>(() => getRotation(), []);
  const [first, setFirst] = useState("");
  const [phone, setPhone] = useState("");
  const [reason, setReason] = useState("");
  const [logged, setLogged] = useState<Up | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const inFlight = useRef(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!first.trim() || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setErr(null);
    setLogged(null);
    try {
      const up = await logUp({
        up_type: "walk_in",
        first_name: first.trim(),
        phone: phone.trim() || null,
        notes: reason.trim() || undefined,
      });
      setLogged(up);
      setFirst("");
      setPhone("");
      setReason("");
      rotation.reload();
    } catch {
      setErr("The visitor's check-in could not be confirmed. Check the visitor list before trying again.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const input = "w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-[var(--app-accent)]";

  return (
    <WiredScreen app={app} screen={screen} loading={rotation.loading} error={rotation.error} empty={false} onRetry={rotation.reload}>
      {rotation.data?.next_up && (
        <div className={`${accent.soft} rounded-xl px-3 py-2 text-xs ${accent.softText}`}>
          Next up on the floor: <strong>{rotation.data.next_up.name || rotation.data.next_up.employee_id}</strong>
        </div>
      )}

      {logged && (
        <div role="status" className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-300">
          ✓ {logged.first_name} checked in
          {logged.assigned_to_name ? ` — assigned to ${logged.assigned_to_name}.` : " and added to the floor rotation."}
        </div>
      )}

      <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
        <h3 className="mb-3 text-sm font-semibold text-white">Check in a visitor</h3>
        <form onSubmit={submit} className="space-y-2.5">
          <label className="block text-sm text-slate-200">Visitor name <span className="text-slate-400">(required)</span><input className={input + " mt-1.5"} aria-label="Visitor name" required disabled={busy} placeholder="Visitor name" value={first} onChange={(e) => setFirst(e.target.value)} /></label>
          <label className="block text-sm text-slate-200">Phone <span className="text-slate-400">(optional)</span><input className={input + " mt-1.5"} aria-label="Phone (optional)" disabled={busy} placeholder="Phone (optional)" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" /></label>
          <label className="block text-sm text-slate-200">Reason for visit <span className="text-slate-400">(optional)</span><input className={input + " mt-1.5"} aria-label="Reason for visit (optional)" disabled={busy} placeholder="Reason / who they're here to see (optional)" value={reason} onChange={(e) => setReason(e.target.value)} /></label>
          {err && <div role="alert" className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{err}</div>}
          <button
            disabled={busy || !first.trim()}
            className="w-full rounded-full bg-[var(--app-accent)] py-2.5 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-50"
          >
            {busy ? "Checking in…" : "Check in visitor"}
          </button>
        </form>
      </div>
    </WiredScreen>
  );
}
