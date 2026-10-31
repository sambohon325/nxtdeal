"use client";
import { WorkButton, WorkSelect, WorkInput, WorkTextarea , WorkStat, WorkOverlay} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";

// Service's "Appointments" item -- the dedicated Service scheduling center
// (session 105 follow-up, closing the last flagged gap from the Sales Deal Desk /
// missing-workflows arc). Backend has been real since session 96
// (core/appointments.py, department-agnostic -- Sales and Service share the same
// entity, distinguished by a `department` attribute); this is the first frontend
// built for the Service side of it. Mirrors AppointmentsBoard.tsx's (Sales) layout
// and interaction pattern, swapped to Service's own appointment types (service/
// waiter/drop_off/recall/other) and technician/advisor roster
// (GET /service/employees, core/appointments_api.py's list_service_employees_api).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  listAppointments,
  createAppointment,
  updateAppointmentStatus,
  getServiceEmployees,
  type Appointment,
  type AppointmentType,
  type AppointmentStatus,
  type ServiceEmployeeBrief,
} from "@/lib/appointments";
import { EntityHoverLink } from "@/components/EntityHoverLink";
import {
  getCapacityPlanning,
  suggestAssignee,
  sendAppointmentReminder,
  generateCheckinLink,
  type CapacityPlan,
  type AssigneeSuggestion,
  type ReminderChannel,
} from "@/lib/appointmentScheduling";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const SERVICE_TYPES: AppointmentType[] = ["service", "waiter", "drop_off", "recall", "other"];

const TYPE_LABELS: Record<string, string> = {
  service: "Service", waiter: "Waiter", drop_off: "Drop-Off", recall: "Recall", other: "Other",
};

const STATUS_TONE: Record<AppointmentStatus, string> = {
  scheduled: "border-zinc-800 bg-zinc-900/40 text-zinc-300",
  confirmed: "border-blue-900 bg-blue-950/30 text-blue-300",
  arrived: "border-amber-900 bg-amber-950/30 text-amber-300",
  completed: "border-green-900 bg-green-950/30 text-green-300",
  no_show: "border-red-900 bg-red-950/30 text-red-300",
  cancelled: "border-zinc-800 bg-zinc-900/20 text-zinc-600",
};

const NEXT_ACTIONS: Record<AppointmentStatus, { label: string; to: AppointmentStatus }[]> = {
  scheduled: [{ label: "Confirm", to: "confirmed" }, { label: "Cancel", to: "cancelled" }],
  confirmed: [{ label: "Arrived", to: "arrived" }, { label: "No-Show", to: "no_show" }, { label: "Cancel", to: "cancelled" }],
  arrived: [{ label: "Complete", to: "completed" }, { label: "Cancel", to: "cancelled" }],
  completed: [],
  no_show: [],
  cancelled: [],
};

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { weekday: "short", month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: number; color: string }) { return <WorkStat label={label} value={value}/>; }

function AppointmentRow({ theme, appt, busy, onAdvance }: { theme: Theme; appt: Appointment; busy: boolean; onAdvance: (id: string, status: AppointmentStatus) => void }) {
  const [remindOpen, setRemindOpen] = useState(false);
  const [remindChannel, setRemindChannel] = useState<ReminderChannel>("sms");
  const [remindBusy, setRemindBusy] = useState(false);
  const [remindSent, setRemindSent] = useState(false);
  const [checkinLink, setCheckinLink] = useState<string | null>(null);
  const [checkinBusy, setCheckinBusy] = useState(false);
  const [checkinCopied, setCheckinCopied] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const isTerminal = appt.status === "completed" || appt.status === "cancelled" || appt.status === "no_show";

  async function handleSendReminder() {
    setRemindBusy(true);
    setActionError(null);
    try {
      await sendAppointmentReminder(appt.id, remindChannel);
      setRemindSent(true);
      setRemindOpen(false);
    } catch {
      setActionError("The simulated reminder could not be recorded. Please try again.");
    } finally {
      setRemindBusy(false);
    }
  }

  async function handleGenerateCheckin() {
    setCheckinBusy(true);
    setActionError(null);
    setCheckinCopied(false);
    try {
      const link = await generateCheckinLink(appt.id);
      if (link.path) {
        setCheckinLink(typeof window !== "undefined" ? `${window.location.origin}${link.path}` : link.path);
      }
    } catch {
      setActionError("The check-in link could not be created. Please try again.");
    } finally {
      setCheckinBusy(false);
    }
  }

  async function handleCopyCheckin() {
    if (!checkinLink) return;
    setCheckinCopied(false);
    setActionError(null);
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(checkinLink);
      setCheckinCopied(true);
    } catch {
      setActionError("The link could not be copied. Select the link and copy it manually.");
    }
  }

  return (
    <div className={tc(theme, `rounded-lg border p-2.5 ${STATUS_TONE[appt.status]}`, `rounded-lg border p-2.5 ${STATUS_TONE[appt.status]}`)}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <div className="text-xs font-medium">
            {TYPE_LABELS[appt.appointment_type] || appt.appointment_type}
            {(appt.customer_id || appt.lead_id) && (
              <span className="ml-1.5 opacity-80">
                — <EntityHoverLink id={(appt.customer_id || appt.lead_id) as string} />
              </span>
            )}
          </div>
          <div className="text-xs opacity-70 mt-0.5">{fmt(appt.scheduled_start)} · {appt.assigned_to || "unassigned"} · {appt.status}</div>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {!isTerminal && (
            <>
              {remindSent ? (
                <span className="text-xs text-green-400">Simulation recorded — not delivered</span>
              ) : (
                <WorkButton type="submit" disabled={remindBusy} onClick={() => setRemindOpen((o) => !o)} className="text-xs px-2 py-1 rounded bg-zinc-200/10 hover:bg-zinc-200/20 transition disabled:opacity-50">
                  📱 Remind
                </WorkButton>
              )}
              <WorkButton type="submit" disabled={checkinBusy} onClick={handleGenerateCheckin} className="text-xs px-2 py-1 rounded bg-zinc-200/10 hover:bg-zinc-200/20 transition disabled:opacity-50">
                🔗 Check-In Link
              </WorkButton>
            </>
          )}
          {NEXT_ACTIONS[appt.status].map((a) => (
            <WorkButton type="submit" variant="primary" key={a.to} disabled={busy} onClick={() => onAdvance(appt.id, a.to)} className="text-xs px-2 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
              {a.label}
            </WorkButton>
          ))}
        </div>
      </div>

      {actionError && <p role="alert" className="mt-2 text-xs text-amber-500">{actionError}</p>}
      {remindOpen && (
        <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-white/10">
          <WorkField label="Reminder channel"><WorkSelect value={remindChannel} onChange={(e) => setRemindChannel(e.target.value as ReminderChannel)} className="rounded border border-zinc-700 bg-zinc-900 text-white text-xs px-1.5 py-0.5">
            <option value="sms">SMS</option>
            <option value="email">Email</option>
            <option value="call">Call</option>
          </WorkSelect></WorkField>
          <WorkButton type="submit" variant="primary" disabled={remindBusy} onClick={handleSendReminder} className="text-xs px-2 py-0.5 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
            Send (simulated)
          </WorkButton>
        </div>
      )}

      {checkinLink && (
        <div className="flex items-center gap-1.5 mt-2 pt-2 border-t border-white/10">
          <WorkInput aria-label="Appointment check-in link" readOnly value={checkinLink} className="flex-1 rounded border border-zinc-700 bg-zinc-900 text-white text-xs px-1.5 py-0.5" />
          <WorkButton type="submit"
            onClick={handleCopyCheckin}
            className="text-xs px-2 py-0.5 rounded bg-zinc-200/10 hover:bg-zinc-200/20 transition"
          >
            {checkinCopied ? "Copied!" : "Copy"}
          </WorkButton>
        </div>
      )}
    </div>
  );
}

function ScheduleModal({
  theme,
  onClose,
  onCreated,
}: {
  theme: Theme;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [appointmentType, setAppointmentType] = useState<AppointmentType>("service");
  const [customerId, setCustomerId] = useState("");
  const [vehicleId, setVehicleId] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [start, setStart] = useState("");
  const [notes, setNotes] = useState("");
  const [employees, setEmployees] = useState<ServiceEmployeeBrief[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getServiceEmployees().then(setEmployees).catch(() => setEmployees([]));
  }, []);

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleCreate() {
    if (!start) {
      setError("A date/time is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createAppointment({
        department: "Service",
        appointment_type: appointmentType,
        scheduled_start: new Date(start).toISOString(),
        assigned_to: assignedTo || null,
        customer_id: customerId || null,
        vehicle_id: vehicleId || null,
        notes,
      });
      onCreated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={tc(theme, "w-full max-w-md rounded-xl border border-black/20 bg-brand-charcoal text-white p-4 space-y-3", "w-full max-w-md rounded-xl border border-zinc-200 bg-white text-black p-4 space-y-3")}
      >
        <div className="text-sm font-brand uppercase tracking-wide">Schedule Appointment</div>
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        <WorkField label="Appointment Type"><WorkSelect value={appointmentType} onChange={(e) => setAppointmentType(e.target.value as AppointmentType)} className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`}>
          {SERVICE_TYPES.map((t) => (
            <option key={t} value={t}>{TYPE_LABELS[t]}</option>
          ))}
        </WorkSelect></WorkField>

        <WorkField label="Start date and time"><WorkInput type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>

        <WorkField label="Customer id (CUST-…), optional"><WorkInput value={customerId} onChange={(e) => setCustomerId(e.target.value)} placeholder="Customer id (CUST-…), optional" className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
        <WorkField label="Vehicle id (VEH-…), optional"><WorkInput value={vehicleId} onChange={(e) => setVehicleId(e.target.value)} placeholder="Vehicle id (VEH-…), optional" className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>

        <WorkField label="Assigned employee"><WorkSelect value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)} className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`}>
          <option value="">Assign to…</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>{e.name || e.id}{e.title ? ` — ${e.title}` : ""}</option>
          ))}
        </WorkSelect></WorkField>

        <WorkField label="Notes"><WorkTextarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Notes…" className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>

        <div className="flex items-center gap-2 justify-end">
          <WorkButton type="submit" onClick={onClose} className="text-xs px-3 py-1.5 rounded text-zinc-500 hover:text-white transition">Cancel</WorkButton>
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleCreate} className="text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            Schedule
          </WorkButton>
        </div>
      </div>
    </WorkOverlay>
  );
}

export function ServiceAppointmentsBoard({ theme }: { theme: Theme }) {
  const [today, setToday] = useState<Appointment[]>([]);
  const [week, setWeek] = useState<Appointment[]>([]);
  const [waiters, setWaiters] = useState<Appointment[]>([]);
  const [dropOffs, setDropOffs] = useState<Appointment[]>([]);
  const [recalls, setRecalls] = useState<Appointment[]>([]);
  const [noShows, setNoShows] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [capacity, setCapacity] = useState<CapacityPlan | null>(null);
  const [suggestion, setSuggestion] = useState<AssigneeSuggestion | null>(null);

  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    refreshCapacity();
    Promise.all([
      listAppointments({ department: "Service", scope: "today" }),
      listAppointments({ department: "Service", scope: "this_week" }),
      listAppointments({ department: "Service", appointmentType: "waiter" }),
      listAppointments({ department: "Service", appointmentType: "drop_off" }),
      listAppointments({ department: "Service", appointmentType: "recall" }),
      listAppointments({ department: "Service", status: "no_show" }),
    ])
      .then(([t, w, wa, d, rc, ns]) => {
        setToday(t);
        setWeek(w);
        setWaiters(wa);
        setDropOffs(d);
        setRecalls(rc);
        setNoShows(ns);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Could not load appointments."))
      .finally(() => setLoading(false));
  }

  function refreshCapacity() {
    getCapacityPlanning("Service").then(setCapacity).catch(() => setCapacity(null));
    suggestAssignee("Service").then(setSuggestion).catch(() => setSuggestion(null));
  }

  useEffect(refresh, []);

  async function handleAdvance(id: string, status: AppointmentStatus) {
    setBusy(true);
    setError(null);
    try {
      await updateAppointmentStatus(id, status);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update appointment.");
    } finally {
      setBusy(false);
    }
  }

  const calendars: Record<string, Appointment[]> = {};
  for (const a of week) {
    const key = a.assigned_to || "unassigned";
    calendars[key] = calendars[key] || [];
    calendars[key].push(a);
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Today's Appointments" value={today.length} color={RIBBON[0]} />
        <Kpi theme={theme} label="This Week" value={week.length} color={RIBBON[1]} />
        <Kpi theme={theme} label="Waiters" value={waiters.length} color={RIBBON[2]} />
        <Kpi theme={theme} label="No-Shows" value={noShows.length} color={RIBBON[3]} />
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2.5", "border-b border-zinc-200 px-4 py-2.5")}>
        <WorkButton type="submit" variant="primary" onClick={() => setScheduleOpen(true)} className="text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition">
          + Schedule Appointment
        </WorkButton>
      </div>

      {error && <div role="alert" className="p-4 text-sm text-red-500">{error} <WorkButton type="submit" onClick={refresh} className="underline">Try again</WorkButton></div>}
      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            {capacity && (
              <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
                <div className="flex items-center justify-between mb-1.5">
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Capacity Planning — Today ({capacity.total_booked}/{capacity.total_capacity} booked, {capacity.pct_booked}%)</div>
                  {suggestion && (
                    <div className="text-xs text-zinc-500">
                      Suggested next: <span className="text-white font-medium">{suggestion.name || suggestion.recommended_employee_id}</span> ({suggestion.available_slots} slots open)
                    </div>
                  )}
                </div>
                <div className="grid grid-cols-3 gap-1.5">
                  <RecordCollection>{capacity.employees.map((e) => (
                    <div key={e.employee_id} className={`text-xs px-2 py-1 rounded ${e.at_capacity ? "bg-red-950/40 text-red-300" : "bg-zinc-200/10 text-zinc-400"}`}>
                      {e.name || e.employee_id}: {e.booked_count}/{e.capacity}
                    </div>
                  ))}</RecordCollection>
                </div>
                <div className="text-xs text-zinc-600 italic mt-1.5">{capacity.note}</div>
              </div>
            )}

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Today's Schedule ({today.length})</div>
              {today.length === 0 ? (
                <div className="text-xs text-zinc-600">Nothing scheduled today.</div>
              ) : (
                <div className="space-y-1.5">
                  {today.map((a) => (
                    <AppointmentRow key={a.id} theme={theme} appt={a} busy={busy} onAdvance={handleAdvance} />
                  ))}
                </div>
              )}
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Technician / Advisor Calendars (This Week)</div>
              {Object.keys(calendars).length === 0 ? (
                <div className="text-xs text-zinc-600">No appointments this week.</div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  {Object.entries(calendars).map(([who, appts]) => (
                    <div key={who} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5")}>
                      <div className="text-xs font-medium mb-1">{who} ({appts.length})</div>
                      <div className="space-y-1">
                        <RecordCollection>{appts.map((a) => (
                          <div key={a.id} className="text-xs text-zinc-500">{fmt(a.scheduled_start)} · {TYPE_LABELS[a.appointment_type] || a.appointment_type}</div>
                        ))}</RecordCollection>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Waiter vs. Drop-Off ({waiters.length} / {dropOffs.length})</div>
              {waiters.length === 0 && dropOffs.length === 0 ? (
                <div className="text-xs text-zinc-600">No waiter or drop-off appointments booked.</div>
              ) : (
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <div className="text-xs text-zinc-500 mb-1">Waiters</div>
                    <div className="space-y-1.5">
                      <RecordCollection>{waiters.map((a) => (
                        <AppointmentRow key={a.id} theme={theme} appt={a} busy={busy} onAdvance={handleAdvance} />
                      ))}</RecordCollection>
                    </div>
                  </div>
                  <div>
                    <div className="text-xs text-zinc-500 mb-1">Drop-Offs</div>
                    <div className="space-y-1.5">
                      <RecordCollection>{dropOffs.map((a) => (
                        <AppointmentRow key={a.id} theme={theme} appt={a} busy={busy} onAdvance={handleAdvance} />
                      ))}</RecordCollection>
                    </div>
                  </div>
                </div>
              )}
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Recall Appointments ({recalls.length})</div>
              {recalls.length === 0 ? (
                <div className="text-xs text-zinc-600">No recall appointments booked.</div>
              ) : (
                <div className="space-y-1.5">
                  <RecordCollection>{recalls.map((a) => (
                    <AppointmentRow key={a.id} theme={theme} appt={a} busy={busy} onAdvance={handleAdvance} />
                  ))}</RecordCollection>
                </div>
              )}
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">No-Show Tracking ({noShows.length})</div>
              {noShows.length === 0 ? (
                <div className="text-xs text-zinc-600">No no-shows on record.</div>
              ) : (
                <div className="space-y-1.5">
                  <RecordCollection>{noShows.map((a) => (
                    <AppointmentRow key={a.id} theme={theme} appt={a} busy={busy} onAdvance={handleAdvance} />
                  ))}</RecordCollection>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {scheduleOpen && (
        <ScheduleModal
          theme={theme}
          onClose={() => setScheduleOpen(false)}
          onCreated={() => {
            setScheduleOpen(false);
            refresh();
          }}
        />
      )}
    </div>
  );
}
