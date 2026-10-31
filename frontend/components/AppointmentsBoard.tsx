"use client";
import { WorkButton, WorkSelect, WorkInput, WorkTextarea , WorkStat, WorkOverlay} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import {CollectionPagination} from "./CollectionPagination";
import { WorkField } from "./WorkField";

// Sales' "Appointments" item -- the real sales calendar (session 96 follow-up,
// backend: core/appointments.py). Today's/This Week's schedule, salesperson
// calendars, test drives, and no-show tracking, all real as of this session --
// closing the single most-repeated "not_yet_tracked" gap in this codebase.
import {fetchCrmRecords,defaultFilters,type CrmRow} from "@/lib/salesCrm";
import visitStyles from "./sales/SalesVisits.module.css";
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  listAppointments,
  createAppointment,
  updateAppointmentStatus,
  type Appointment,
  type AppointmentType,
  type AppointmentStatus,
} from "@/lib/appointments";
import { getSalesEmployees, type SalesEmployeeBrief } from "@/lib/salesOverview";
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

const SALES_TYPES: AppointmentType[] = ["showroom_visit", "test_drive", "delivery", "credit_app", "paperwork", "trade_appraisal", "other"];

const TYPE_LABELS: Record<string, string> = {
  showroom_visit: "Showroom Visit", test_drive: "Test Drive", delivery: "Delivery",
  credit_app: "Credit App", paperwork: "Paperwork", trade_appraisal: "Trade Appraisal", other: "Other",
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
  inline = false,
}: {
  theme: Theme;
  onClose: () => void;
  onCreated: () => void;
  inline?: boolean;
}) {
  const [appointmentType, setAppointmentType] = useState<AppointmentType>("showroom_visit");
  const [customerId, setCustomerId] = useState("");
  const [leadId, setLeadId] = useState("");
  const [assignedTo, setAssignedTo] = useState("");
  const [start, setStart] = useState("");
  const [notes, setNotes] = useState("");
  const [employees, setEmployees] = useState<SalesEmployeeBrief[]>([]);
  const [search,setSearch]=useState("");const [kind,setKind]=useState<"Lead"|"Customer">("Lead");
  const [matches,setMatches]=useState<CrmRow[]>([]);const [searchError,setSearchError]=useState(false);const [searching,setSearching]=useState(false);const [selectedName,setSelectedName]=useState("");
  useEffect(()=>{setMatches([]);setSearchError(false);if(search.trim().length<2){setSearching(false);return;}let current=true;setSearching(true);
   const timer=setTimeout(()=>fetchCrmRecords({...defaultFilters,kind,q:search.trim()},0).then(data=>{if(current)setMatches(data.records.slice(0,5));}).catch(()=>{if(current)setSearchError(true);}).finally(()=>{if(current)setSearching(false);}),250);
   return()=>{current=false;clearTimeout(timer);};
  },[search,kind]);

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSalesEmployees().then(setEmployees).catch(() => setEmployees([]));
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
        department: "Sales",
        appointment_type: appointmentType,
        scheduled_start: new Date(start).toISOString(),
        assigned_to: assignedTo || null,
        customer_id: customerId || null,
        lead_id: leadId || null,
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
    <WorkOverlay data-department-work="" className={inline ? "workspace-inline-editor" : "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"} onClick={inline ? undefined : onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={inline ? "workspace-editor-surface p-5 space-y-4" : tc(theme, "w-full max-w-md rounded-xl border border-black/20 bg-brand-charcoal text-white p-4 space-y-3", "w-full max-w-md rounded-xl border border-zinc-200 bg-white text-black p-4 space-y-3")}
      >
        <div className="text-sm font-brand uppercase tracking-wide">Schedule Appointment</div>
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        <WorkSelect aria-label="Visit purpose" value={appointmentType} onChange={(e) => setAppointmentType(e.target.value as AppointmentType)} className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`}>
          {SALES_TYPES.map((t) => (
            <option key={t} value={t}>{TYPE_LABELS[t]}</option>
          ))}
        </WorkSelect>

        <label className="text-sm">Visit date and time<WorkInput aria-label="Visit date and time" type="datetime-local" value={start} onChange={(e) => setStart(e.target.value)} className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></label>


        <div><label>Who is visiting?<WorkSelect aria-label="Search customer type" value={kind} onChange={e=>{setKind(e.target.value as "Lead"|"Customer");setSearch("");setSelectedName("");setLeadId("");setCustomerId("");}}><option value="Lead">Lead / opportunity</option><option value="Customer">Existing customer</option></WorkSelect></label>
        {selectedName?<p>Selected: {selectedName} <WorkButton type="submit" onClick={()=>{setSelectedName("");setLeadId("");setCustomerId("");}}>Change customer</WorkButton></p>:<><WorkInput aria-label="Find visiting customer" placeholder="Search name, phone or email…" value={search} onChange={e=>setSearch(e.target.value)} className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`}/>{searching?<p role="status">Searching…</p>:searchError?<p role="alert">Customer search unavailable. Try again or use a known record ID below.</p>:matches.map(record=><WorkButton type="submit" key={record.id} className="block w-full text-left p-2" onClick={()=>{setSelectedName(record.name);setLeadId(kind==="Lead"?record.id:"");setCustomerId(kind==="Customer"?record.id:"");setSearch("");}}>{record.name} · {record.email||record.phone||record.id}</WorkButton>)}{search.length>=2&&!searching&&!searchError&&!matches.length&&<p>No matches. Try a different name.</p>}<small>Enter at least two characters. Refine your search if the customer is not in the first five matches.</small></>}
        <details><summary>Use record IDs instead (optional)</summary><WorkInput aria-label="Customer record ID" value={customerId} onChange={e=>{setCustomerId(e.target.value);setSelectedName("");}} placeholder="Customer ID"/><WorkInput aria-label="Lead record ID" value={leadId} onChange={e=>{setLeadId(e.target.value);setSelectedName("");}} placeholder="Lead ID"/></details></div>

        <WorkSelect aria-label="Assigned salesperson" value={assignedTo} onChange={(e) => setAssignedTo(e.target.value)} className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`}>
          <option value="">Assign to…</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>{e.name || e.id}{e.title ? ` — ${e.title}` : ""}</option>
          ))}
        </WorkSelect>

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

export function AppointmentsBoard({ theme, workflow = false, onOpenCustomer }: { theme: Theme; workflow?: boolean; onOpenCustomer?: (id:string, kind:"Lead"|"Customer")=>void }) {
  const [today, setToday] = useState<Appointment[]>([]);
  const [week, setWeek] = useState<Appointment[]>([]);
  const [testDrives, setTestDrives] = useState<Appointment[]>([]);
  const [noShows, setNoShows] = useState<Appointment[]>([]);
  const [loading, setLoading] = useState(true);
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [capacity, setCapacity] = useState<CapacityPlan | null>(null);
  const [suggestion, setSuggestion] = useState<AssigneeSuggestion | null>(null);
  const [view,setView]=useState<"today"|"week"|"drives"|"missed">("today");
  const [owner,setOwner]=useState("");const [page,setPage]=useState(0);
  const [loadError,setLoadError]=useState(false);const [actionError,setActionError]=useState("");


  function refresh() {
    setLoading(true);setLoadError(false);
    Promise.all([
      listAppointments({ department: "Sales", scope: "today" }),
      listAppointments({ department: "Sales", scope: "this_week" }),
      listAppointments({ department: "Sales", appointmentType: "test_drive" }),
      listAppointments({ department: "Sales", status: "no_show" }),
    ])
      .then(([t, w, td, ns]) => {
        setToday(t);
        setWeek(w);
        setTestDrives(td);
        setNoShows(ns);
      })
      .catch(() => {setLoadError(true);})
      .finally(() => setLoading(false));
  }

  function refreshCapacity() {
    getCapacityPlanning("Sales").then(setCapacity).catch(() => {});
    suggestAssignee("Sales").then(setSuggestion).catch(() => {});
  }

  useEffect(refresh, []);
  useEffect(refreshCapacity, []);

  async function handleAdvance(id: string, status: AppointmentStatus) {
    setBusy(true);setActionError("");
    try {
      await updateAppointmentStatus(id, status);
      refresh();
    } catch {
      setActionError("The visit status could not be saved. Please try again.");
    } finally {
      setBusy(false);
    }
  }


  const source=view==="today"?today:view==="week"?week:view==="drives"?testDrives:noShows;
  const roster=[...new Set(source.map(a=>a.assigned_to||"unassigned"))].sort();
  const visits=source.filter(a=>!owner||(a.assigned_to||"unassigned")===owner).slice().sort((a,b)=>a.scheduled_start.localeCompare(b.scheduled_start));
  const pages=Math.max(1,Math.ceil(visits.length/25));const current=Math.min(page,pages-1);
  if(workflow && scheduleOpen)return <section aria-label="Schedule a sales visit"><WorkButton type="submit" onClick={()=>setScheduleOpen(false)}>← Back to appointments</WorkButton><ScheduleModal inline theme={theme} onClose={()=>setScheduleOpen(false)} onCreated={()=>{setScheduleOpen(false);refresh();refreshCapacity();}}/></section>;
  if(workflow)return <section className={visitStyles.visits} aria-label="Sales visit workflow">
   <header><div><h3>Appointments & showroom</h3><p>Open the customer record, prepare for their visit, then record what happened.</p></div><WorkButton type="submit" onClick={()=>setScheduleOpen(true)}>＋ Schedule a visit</WorkButton></header>
   <nav aria-label="Visit views">{([["today","Today"],["week","This week"],["drives","Test drives"],["missed","Missed visits"]] as const).map(([key,label])=><WorkButton data-work-view type="submit" key={key} aria-pressed={view===key} onClick={()=>{setView(key);setOwner("");setPage(0);}}>{label}</WorkButton>)}</nav>
   <div className={visitStyles.filters}><label>Salesperson <WorkSelect value={owner} onChange={e=>{setOwner(e.target.value);setPage(0);}}><option value="">All salespeople</option>{roster.map(id=><option key={id} value={id}>{capacity?.employees.find(e=>e.employee_id===id)?.name||id}</option>)}</WorkSelect></label><span>{loading?"Refreshing visits…":loadError?"Schedule unavailable":`${visits.length} ${visits.length===1?"visit":"visits"}`}</span><WorkButton type="submit" onClick={refresh} disabled={loading}>Refresh visits</WorkButton></div>
   {actionError&&<p role="alert">{actionError}</p>}
   {loadError?<div role="alert"><p>Your schedule could not be loaded. Existing appointments have not been changed.</p><WorkButton type="submit" onClick={refresh}>Retry schedule</WorkButton></div>:loading?<p role="status">Loading appointments…</p>:<>
    {!visits.length&&<div className={visitStyles.empty}><h4>No visits in this view.</h4><p>Choose another view or salesperson, or schedule a visit for a customer.</p></div>}
    {visits.slice(current*25,current*25+25).map(appt=><article key={appt.id} className={visitStyles.visit}>
      <AppointmentRow theme={theme} appt={appt} busy={busy} onAdvance={handleAdvance}/>
      <div className={visitStyles.next}><p><strong>Next step: </strong>{appt.status==="scheduled"?"Review the customer's needs and confirm the visit.":appt.status==="confirmed"?"Prepare the vehicle and mark Arrived when the customer checks in.":appt.status==="arrived"?"Work with the customer, then record the visit outcome.":appt.status==="no_show"?"Open the customer record to log follow-up and agree on another visit.":appt.status==="completed"?"Record the outcome and add the customer's next follow-up.":"Review the customer record before arranging a replacement visit."}</p>{(appt.lead_id||appt.customer_id)&&<WorkButton type="submit" onClick={()=>onOpenCustomer?.((appt.lead_id||appt.customer_id)!,appt.lead_id?"Lead":"Customer")}>Open customer record →</WorkButton>}</div>
      {appt.notes&&<details><summary>Visit notes</summary><p>{appt.notes}</p></details>}
    </article>)}
    <CollectionPagination label="Visits" total={visits.length} page={current} pageSize={25} onPageChange={setPage}/>
   </>}
   <details className={visitStyles.capacity}><summary>Team capacity & assignment planning</summary>{capacity?<><p>Today: {capacity.total_booked} of {capacity.total_capacity} slots booked.</p>{suggestion&&<p>Suggested next assignee: {suggestion.name||suggestion.recommended_employee_id}</p>}<ul>{capacity.employees.map(e=><li key={e.employee_id}>{e.name||e.employee_id}: {e.booked_count}/{e.capacity}</li>)}</ul><p>{capacity.note}</p></>:<p>Capacity is unavailable. <WorkButton type="submit" onClick={refreshCapacity}>Retry capacity</WorkButton></p>}</details>
  </section>;
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
        <Kpi theme={theme} label="Test Drives" value={testDrives.length} color={RIBBON[2]} />
        <Kpi theme={theme} label="No-Shows" value={noShows.length} color={RIBBON[3]} />
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2.5", "border-b border-zinc-200 px-4 py-2.5")}>
        <WorkButton type="submit" variant="primary" onClick={() => setScheduleOpen(true)} className="text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition">
          + Schedule Appointment
        </WorkButton>
      </div>

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
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Salesperson Calendars (This Week)</div>
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
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Test Drives ({testDrives.length})</div>
              {testDrives.length === 0 ? (
                <div className="text-xs text-zinc-600">No test drives booked.</div>
              ) : (
                <div className="space-y-1.5">
                  <RecordCollection>{testDrives.map((a) => (
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
