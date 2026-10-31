"use client";

// Receptionist "Appointments" — today's Sales + Service appointments live off
// GET /appointments (core/appointments.py), filtered to the device's local day,
// with one-tap arrival marking
// (POST /appointments/{id}/status → "arrived").

import { useRef, useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import { listAppointments, updateAppointmentStatus, type Appointment } from "@/lib/appointments";
import { useAsync, WiredScreen, ListCard, Row, EmptyNote } from "./kit";

function fmtTime(iso: string): string {
  const value = new Date(iso);
  if (!Number.isFinite(value.getTime())) return "Time unavailable";
  return value.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short",
  });
}

export function ReceptionAppointments({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  const [busyId, setBusyId] = useState<string | null>(null);
  const inFlight = useRef(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const { loading, error, data, reload } = useAsync<Appointment[]>(() => listAppointments(), []);

  const today = new Date();
  const appts = (data ?? []).filter(a => {
    const start = new Date(a.scheduled_start);
    return Number.isFinite(start.getTime()) && start.getFullYear() === today.getFullYear()
      && start.getMonth() === today.getMonth() && start.getDate() === today.getDate();
  }).sort((a, b) => {
    const first = Date.parse(a.scheduled_start);
    const second = Date.parse(b.scheduled_start);
    if (!Number.isFinite(first)) return Number.isFinite(second) ? 1 : 0;
    if (!Number.isFinite(second)) return -1;
    return first - second;
  });

  async function markArrived(id: string) {
    if (inFlight.current) return;
    const appointment = appts.find(a => a.id === id);
    if (!appointment || !["scheduled", "confirmed"].includes(appointment.status)) return;
    inFlight.current = true;
    setBusyId(id);
    setActionError(null);
    try {
      await updateAppointmentStatus(id, "arrived");
      reload();
    } catch {
      setActionError("Arrival could not be confirmed. Refresh appointments before trying again.");
    } finally {
      inFlight.current = false;
      setBusyId(null);
    }
  }

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>
      {actionError && <p role="alert" className="text-sm text-zinc-300">{actionError}</p>}
      <ListCard title="Today's appointments" count={appts.length}>
        <p className="text-xs text-zinc-400">Today and appointment times use this device's timezone. Refresh to update the list.</p>
        <button type="button" onClick={reload} disabled={busyId !== null} className="text-xs text-zinc-300 underline disabled:opacity-50">Refresh appointments</button>
        {data?.some(a => !Number.isFinite(Date.parse(a.scheduled_start))) && <p role="status" className="text-xs text-zinc-400">Some appointments have invalid times and cannot be placed on today's list.</p>}
        {appts.map((a) => (
          <Row
            key={a.id}
            primary={`${a.appointment_type.replace(/_/g, " ")} · ${a.department}`}
            secondary={[fmtTime(a.scheduled_start), a.status, a.notes].filter(Boolean).join(" · ") || undefined}
            meta={
              !["scheduled", "confirmed"].includes(a.status) ? (
                <span className={accent.text}>{a.status.replace(/_/g, " ")}</span>
              ) : (
                <button
                  onClick={() => markArrived(a.id)}
                  disabled={busyId !== null}
                  aria-label={`Mark ${a.appointment_type.replace(/_/g, " ")} at ${fmtTime(a.scheduled_start)} arrived`}
                  className={`${accent.bg} rounded-full px-2.5 py-1 text-[10px] font-semibold text-white disabled:opacity-50`}
                >
                  {busyId === a.id ? "…" : "Arrived"}
                </button>
              )
            }
          />
        ))}
        {appts.length === 0 && <EmptyNote>No appointments scheduled for today.</EmptyNote>}
      </ListCard>
    </WiredScreen>
  );
}
