"use client";

// Sales "Ups" — the live up system off /up-system/* (core/up_system.py): the floor rotation,
// the working ups list, and a real "log an up" form (POST /up-system/log). Logging refreshes both.

import { useRef, useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import { getRotation, listUps, logUp, type Rotation, type Up } from "@/lib/upSystem";
import { useAsync, WiredScreen, ListCard, Row, EmptyNote } from "./kit";

export function SalesUps({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  const rotation = useAsync<Rotation>(() => getRotation(), []);
  const ups = useAsync<Up[]>(() => listUps(), []);

  const [firstName, setFirstName] = useState("");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const [error, setError] = useState<string | null>(null);
  function reload() { rotation.reload(); ups.reload(); }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!firstName.trim() || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    setError(null);
    try {
      await logUp({ up_type: "walk_in", first_name: firstName.trim(), notes: notes.trim() || undefined });
      setFirstName("");
      setNotes("");
      rotation.reload();
      ups.reload();
    } catch {
      setError("The walk-in could not be confirmed. Check the visitor list before trying again.");
    } finally {
      inFlight.current = false;
      setBusy(false);
    }
  }

  const list = ups.data ?? [];

  return (
    <WiredScreen app={app} screen={screen} loading={rotation.loading || ups.loading} error={rotation.error || ups.error} empty={!rotation.data && !ups.data} onRetry={reload}>
      <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-4">
        <h3 className="mb-2 text-sm font-semibold text-white">Log a walk-in</h3>
        <form onSubmit={submit} className="space-y-2">
          <input
            aria-label="Customer first name"
            required
            disabled={busy}
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
            placeholder="Customer first name"
            className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500"
          />
          <input
            aria-label="Notes (optional)"
            disabled={busy}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Notes (optional)"
            className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500"
          />
          {error && <p role="alert" className="text-sm text-zinc-300">{error} <button type="button" onClick={reload} className="underline">Refresh visitor list</button></p>}
          <button disabled={busy || !firstName.trim()} className={`${accent.bg} w-full rounded-full py-2 text-sm font-semibold text-white disabled:opacity-50`}>
            {busy ? "Logging…" : "Log up → next in rotation"}
          </button>
        </form>
      </div>

      {rotation.data?.next_up && (
        <div className={`${accent.soft} rounded-xl px-3 py-2 text-xs ${accent.softText}`}>
          Next up: <strong>{rotation.data.next_up.name || rotation.data.next_up.employee_id}</strong>
        </div>
      )}

      <ListCard title="Recent ups" count={list.length}>
        {list.map((u) => (
          <Row
            key={u.id}
            primary={[u.first_name, u.last_name].filter(Boolean).join(" ") || "Up"}
            secondary={[u.up_type.replace(/_/g, " "), u.assigned_to_name].filter(Boolean).join(" · ") || undefined}
            meta={u.up_status.replace(/_/g, " ")}
          />
        ))}
        {list.length === 0 && <EmptyNote>No ups recorded.</EmptyNote>}
      </ListCard>
    </WiredScreen>
  );
}
