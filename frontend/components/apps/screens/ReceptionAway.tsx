"use client";

// Receptionist "Away from desk" — the customer-facing kiosk mode (2026-07-24, Sam: "an away from
// desk feature they can have facing the customer where the customer can enter their name and info
// and request someone / which notifies on the floor sales people"). The receptionist turns the
// tablet to face the lobby; a walk-in signs themselves in, which logs a real walk-in up into the
// sales rotation (lib/upSystem.logUp). Notification delivery is not confirmed by this API. Big, touch-friendly,
// tablet-first; auto-resets after a thank-you so it's ready for the next visitor.

import { useEffect, useRef, useState } from "react";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { logUp, type Up } from "@/lib/upSystem";
import { useAppTheme } from "@/lib/apps/appTheme";

export function ReceptionAway({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const theme = useAppTheme();
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<Up | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [err, setErr] = useState<string | null>(null);

  function reset() {
    setDone(null);
    setName("");
    setPhone("");
    setReason("");
    setErr(null);
  }

  // Auto-clear the thank-you after a bit so the kiosk is fresh for the next visitor.
  useEffect(() => {
    if (!done) return;
    const t = setTimeout(reset, 8000);
    return () => clearTimeout(t);
  }, [done]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || inFlight.current || done) return;
    inFlight.current = true;
    setBusy(true);
    setErr(null);
    try {
      const up = await logUp({
        up_type: "walk_in",
        first_name: name.trim(),
        phone: phone.trim() || null,
        notes: reason.trim() || undefined,
      });
      setDone(up);
    } catch {
      setErr("We couldn't confirm your sign-in. Please ask the front desk to check before trying again.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  if (done) {
    return (
      <div className="flex min-h-[62vh] flex-col items-center justify-center text-center">
        <div className="text-6xl">👋</div>
        <h2 className="mt-4 text-3xl font-bold text-white">Thanks, {done.first_name}!</h2>
        <p className="mt-2 text-lg text-zinc-300">
          {done.assigned_to_name ? `Your visit is recorded and assigned to ${done.assigned_to_name}.` : "Your visit is recorded."}
        </p>
        <button
          onClick={reset}
          className="mt-8 rounded-full bg-[var(--app-accent)] px-8 py-3 text-lg font-semibold text-[var(--app-accent-text)]"
        >
          Next visitor
        </button>
      </div>
    );
  }

  const input = "w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3.5 text-lg text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none";

  return (
    <div className="mx-auto max-w-lg py-4">
      <div className="text-center">
        <h2 className="text-3xl font-bold text-white">Welcome to {theme.dealershipName}</h2>
        <p className="mt-2 text-lg text-zinc-400">Sign in to join the floor team's visitor list.</p>
      </div>

      <form onSubmit={submit} className="mt-6 space-y-3">
        <input className={input} aria-label="Your name" required disabled={busy} placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
        <input className={input} aria-label="Phone number (optional)" disabled={busy} placeholder="Phone number (optional)" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
        <input className={input} aria-label="Reason for visit (optional)" disabled={busy} placeholder="What can we help you with? (optional)" value={reason} onChange={(e) => setReason(e.target.value)} />
        {err && <div role="alert" className="rounded-xl bg-red-500/10 px-4 py-3 text-sm text-red-400">{err}</div>}
        <button
          disabled={busy || !name.trim()}
          className="w-full rounded-full bg-[var(--app-accent)] py-4 text-lg font-semibold text-[var(--app-accent-text)] disabled:opacity-50"
        >
          {busy ? "One moment…" : "Sign in"}
        </button>
      </form>
      <p className="mt-3 text-center text-xs text-zinc-500">Need immediate help? Please speak with the front desk.</p>
    </div>
  );
}
