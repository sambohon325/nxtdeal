"use client";
import { WorkButton, WorkSelect, WorkInput, WorkTextarea, WorkSection } from "./WorkspaceUi";
import {RecordTable} from "./RecordTable";
import { WorkField } from "./WorkField";

// Marketing's "Events" Top Menu item (session 84). Sam: "build out the event dash. we
// want to style it after nxtdeal bumper, automotivemastermind.com, and auto alert.
// this part we absolutely have to nail, and has to tightly integrate into the CRM."
//
// A Timeline/Events toggle at the top: Timeline is the AutoAlert/automotiveMastermind
// half -- a live, urgency-ranked feed of individually actionable trigger signals, each
// one-click promotable straight into a real new CRM Lead (with an optional immediate
// salesperson assignment). Events is the NXTDeal Bumper half -- real scheduled
// dealership events with a CRM-list-backed invite audience and RSVP tracking, with the
// same one-click promote-to-Lead action available per attendee post-event. Mounted by
// components/MenuDashPanel.tsx the same way MarketingCRMBoard.tsx/EmailSmsBuilder.tsx/
// SocialReputationBoard.tsx/AdvertisingBoard.tsx are.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState, type DragEvent } from "react";
import {
  listAlertTypes,
  getAlertFeed,
  dismissAlert,
  promoteAlert,
  listEventTypes,
  createEvent,
  listEvents,
  getEventDetail,
  updateEvent,
  publishEvent,
  startEvent,
  completeEvent,
  cancelEvent,
  createRsvp,
  updateRsvpStatus,
  promoteRsvpToLead,
  listEventTaskStatuses,
  createEventTask,
  listEventTasks,
  updateEventTaskStatus,
  deleteEventTask,
  getEventWarRoom,
  generateEventCampaignDraft,
  createEventCampaign,
  listCampaignsForEvent,
  type TriggerAlert,
  type Urgency,
  type EventType,
  type DealershipEvent,
  type EventDetail,
  type EventRsvp,
  type EventTask,
  type EventTaskStatus,
  type EventWarRoom,
  type EventCampaignDraft,
  type EventCampaign,
} from "@/lib/events";
import { listSalesEmployees, listAllLists, type SalesEmployee, type MarketingList } from "@/lib/marketingLists";
import { VISUALIZATION_DRAG_TYPE, type VisualizationDropPayload } from "@/lib/useVisualizationWorkspace";

type Theme = "dark" | "light";
type Section = "timeline" | "events";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

// Same brand-ribbon order as components/DepartmentWorkflowButtons.tsx's RIBBON_COLORS.
const KPI_RIBBON = PRODUCT_ACCENT_COLORS;

const URGENCY_COLORS: Record<Urgency, string> = {
  high: "bg-red-950 text-red-300 border-red-900",
  medium: "bg-amber-950 text-amber-300 border-amber-900",
  low: "bg-zinc-900 text-zinc-400 border-zinc-800",
};

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-zinc-800 text-zinc-400",
  scheduled: "bg-blue-900 text-blue-300",
  live: "bg-green-900 text-green-300",
  completed: "bg-zinc-800 text-zinc-500",
  cancelled: "bg-zinc-800 text-zinc-500",
};

function DragHandle({
  theme,
  itemKey,
  fieldPath,
  sourceLabel,
  rows,
  numericColumns,
  labelColumn,
}: {
  theme: Theme;
  itemKey: string;
  fieldPath: string[];
  sourceLabel: string;
  rows: Record<string, unknown>[];
  numericColumns: string[];
  labelColumn: string;
}) {
  if (rows.length === 0 || numericColumns.length === 0) return null;

  function handleDragStart(event: DragEvent<HTMLButtonElement>) {
    const payload: VisualizationDropPayload = {
      department: "Marketing",
      itemKey,
      fieldPath,
      sourceLabel,
      rows,
      numericColumns,
      labelColumn,
    };
    event.dataTransfer.setData(VISUALIZATION_DRAG_TYPE, JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "copy";
  }

  return (
    <WorkButton type="submit"
      draggable
      onDragStart={handleDragStart}
      title="Drag into the Workspace to build a chart, then pin it"
      className={tc(
        theme,
        "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-700 text-zinc-500 hover:text-white hover:border-zinc-500 transition cursor-grab active:cursor-grabbing",
        "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-400 text-zinc-600 hover:text-black hover:border-zinc-600 transition cursor-grab active:cursor-grabbing"
      )}
    >
      ⠿ Drag to Workspace
    </WorkButton>
  );
}

type WorkflowState={onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void};
export function EventsBoard({ theme, workflowStep,onDraftOpenChange,onSavingChange }: WorkflowState & { theme: Theme; workflowStep?: EventDetailTab | "configuration" }) {
  const [section, setSection] = useState<Section>(workflowStep ? "events" : "timeline");

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      {!workflowStep&&<div className={tc(theme, "border-b border-zinc-800 px-4 py-2.5 flex items-center gap-2", "border-b border-zinc-200 px-4 py-2.5 flex items-center gap-2")}>
        <span className={tc(theme, "text-xs uppercase tracking-wide text-zinc-500 mr-1", "text-xs uppercase tracking-wide text-zinc-500 mr-1")}>Toggle</span>
        {(["timeline", "events"] as Section[]).map((s) => (
          <WorkButton type="submit"
            key={s}
            onClick={() => setSection(s)}
            className={
              section === s
                ? "text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium transition"
                : tc(
                    theme,
                    "text-xs px-3 py-1.5 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition border border-zinc-800",
                    "text-xs px-3 py-1.5 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-100 transition border border-zinc-300"
                  )
            }
          >
            {s === "timeline" ? "⚡ Timeline" : "🎪 Events"}
          </WorkButton>
        ))}
      </div>}

      {section === "timeline" ? <TimelineTab theme={theme} /> : <EventsTab onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} theme={theme} workflowStep={workflowStep} />}
    </div>
  );
}

// --- Timeline tab (AutoAlert / automotiveMastermind style) ---

function TimelineTab({ theme }: { theme: Theme }) {
  const [alertTypes, setAlertTypes] = useState<Record<string, string>>({});
  const [alerts, setAlerts] = useState<TriggerAlert[]>([]);
  const [salesEmployees, setSalesEmployees] = useState<SalesEmployee[]>([]);
  const [loading, setLoading] = useState(true);
  const [typeFilter, setTypeFilter] = useState<string>("");

  function refresh() {
    setLoading(true);
    getAlertFeed({ status: "new" })
      .then(setAlerts)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    listAlertTypes().then(setAlertTypes);
    listSalesEmployees().then(setSalesEmployees);
    refresh();
  }, []);

  const visible = typeFilter ? alerts.filter((a) => a.alert_type === typeFilter) : alerts;

  const byUrgency = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const a of alerts) counts[a.urgency] = (counts[a.urgency] || 0) + 1;
    return counts;
  }, [alerts]);

  const byType = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const a of alerts) counts[a.alert_type] = (counts[a.alert_type] || 0) + 1;
    return counts;
  }, [alerts]);

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      {/* KPI strip */}
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        {[
          { label: "Open Alerts", value: alerts.length },
          { label: "High Urgency", value: byUrgency.high || 0 },
          { label: "Medium", value: byUrgency.medium || 0 },
          { label: "Low", value: byUrgency.low || 0 },
        ].map((k, i) => (
          <div key={k.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
              style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
            />
            <div className="text-2xl font-semibold">{k.value}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k.label}</div>
          </div>
        ))}
        <div className="col-span-4 flex justify-end">
          <DragHandle
            theme={theme}
            itemKey="events"
            fieldPath={["timeline", "by_type"]}
            sourceLabel="Trigger Alerts by Type"
            rows={Object.entries(byType).map(([alert_type, count]) => ({ alert_type, count }))}
            numericColumns={["count"]}
            labelColumn="alert_type"
          />
        </div>
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2 flex items-center gap-1.5 flex-wrap", "border-b border-zinc-200 px-4 py-2 flex items-center gap-1.5 flex-wrap")}>
        <WorkButton type="submit"
          onClick={() => setTypeFilter("")}
          className={
            typeFilter === ""
              ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
              : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition")
          }
        >
          All
        </WorkButton>
        {Object.entries(alertTypes).map(([key, label]) => (
          <WorkButton type="submit"
            key={key}
            onClick={() => setTypeFilter(key)}
            className={
              typeFilter === key
                ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition")
            }
          >
            {label}
          </WorkButton>
        ))}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-2">
        {loading ? (
          <div className="text-sm text-zinc-500">Scanning the graph for real trigger signals…</div>
        ) : visible.length === 0 ? (
          <div className="text-sm text-zinc-500">No open alerts right now -- the Timeline re-scans the live graph on every load.</div>
        ) : (
          visible.map((a) => (
            <AlertCard key={a.id} theme={theme} alert={a} salesEmployees={salesEmployees} onChanged={refresh} />
          ))
        )}
      </div>
    </div>
  );
}

function AlertCard({
  theme,
  alert,
  salesEmployees,
  onChanged,
}: {
  theme: Theme;
  alert: TriggerAlert;
  salesEmployees: SalesEmployee[];
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [showAssign, setShowAssign] = useState(false);
  const [assignTo, setAssignTo] = useState("");

  async function handlePromote() {
    setBusy(true);
    try {
      await promoteAlert(alert.id, assignTo || undefined);
      onChanged();
    } catch (e) {
      alert_((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  // avoid shadowing the DOM `alert()` global with our `alert` prop
  function alert_(msg: string) {
    window.alert(msg);
  }

  async function handleDismiss() {
    setBusy(true);
    try {
      await dismissAlert(alert.id);
      onChanged();
    } catch (e) {
      alert_((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={`rounded-lg border p-3 ${URGENCY_COLORS[alert.urgency]}`}>
      <div className="flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="text-xs px-1.5 py-0.5 rounded uppercase bg-black/30">{alert.urgency}</span>
          <span className="text-xs font-medium">{alert.alert_type_label}</span>
          {alert.basis === "heuristic" && (
            <span className="text-xs px-1.5 py-0.5 rounded bg-black/30" title={alert.notes || "Heuristic estimate"}>
              HEURISTIC
            </span>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => setShowAssign(!showAssign)} className="text-xs px-2 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
            Promote →
          </WorkButton>
          <WorkButton type="submit" disabled={busy} onClick={handleDismiss} className={tc(theme, "text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-white transition disabled:opacity-50", "text-xs px-2 py-1 rounded border border-zinc-400 text-zinc-600 hover:text-black transition disabled:opacity-50")}>
            Dismiss
          </WorkButton>
        </div>
      </div>
      <div className="text-sm mt-1.5 font-medium">{alert.target_name}</div>
      <div className="text-xs mt-0.5 opacity-90">{alert.headline}</div>

      {showAssign && (
        <div className="mt-2 flex items-center gap-1.5">
          <WorkField label="Assign to employee"><WorkSelect value={assignTo} onChange={(e) => setAssignTo(e.target.value)} className={tc(theme, "text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1", "text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1")}>
            <option value="">No assignment -- just create the Lead</option>
            {salesEmployees.map((e) => (
              <option key={e.id} value={e.id}>{e.name}{e.title ? ` -- ${e.title}` : ""}</option>
            ))}
          </WorkSelect></WorkField>
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={handlePromote} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
            Confirm →
          </WorkButton>
        </div>
      )}
    </div>
  );
}

// --- Events tab (NXTDeal Bumper style) ---

function EventsTab({ theme, workflowStep,onDraftOpenChange,onSavingChange }: WorkflowState & { theme: Theme; workflowStep?: EventDetailTab | "configuration" }) {
  const [eventTypes, setEventTypes] = useState<EventType[]>([]);
  const [events, setEvents] = useState<DealershipEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"list" | "new">("list");
  const [childDirty,setChildDirty]=useState(false);
  useEffect(()=>{onDraftOpenChange?.(childDirty);return()=>onDraftOpenChange?.(false)},[childDirty,onDraftOpenChange]);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    listEvents()
      .then(setEvents)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    listEventTypes().then(setEventTypes);
    refresh();
  }, []);

  const byStatus = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of events) counts[e.status] = (counts[e.status] || 0) + 1;
    return counts;
  }, [events]);

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-hidden">
      {!selectedId&&<><div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        {[
          { label: "Total Events", value: events.length },
          { label: "Scheduled", value: byStatus.scheduled || 0 },
          { label: "Live", value: byStatus.live || 0 },
          { label: "Completed", value: byStatus.completed || 0 },
        ].map((k, i) => (
          <div key={k.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
              style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
            />
            <div className="text-2xl font-semibold">{k.value}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k.label}</div>
          </div>
        ))}
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2 flex items-center gap-2", "border-b border-zinc-200 px-4 py-2 flex items-center gap-2")}>
        {(["list", "new"] as const).map((v) => (
          <WorkButton disabled={childDirty} data-work-view aria-pressed={view === v} type="submit"
            key={v}
            onClick={() => { setView(v); setSelectedId(null); }}
            className={
              view === v
                ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition")
            }
          >
            {v === "list" ? "Events" : "+ New Event"}
          </WorkButton>
        ))}
      </div></>}

      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : selectedId ? (
          <EventDetailView workflowMode={!!workflowStep} theme={theme} initialTab={workflowStep && workflowStep !== "configuration" ? workflowStep : "rsvps"} eventId={selectedId} onBack={() => setSelectedId(null)} onChanged={refresh} />
        ) : view === "new" ? (
          <NewEventForm onDraftOpenChange={setChildDirty} onSavingChange={onSavingChange} onCancel={()=>setView("list")} theme={theme} eventTypes={eventTypes} onCreated={(id) => { refresh(); setSelectedId(id); setView("list"); }} />
        ) : (
          <EventList theme={theme} events={events} onSelect={setSelectedId} />
        )}
      </div>
    </div>
  );
}

function EventList({ theme: _theme, events, onSelect }: { theme: Theme; events: DealershipEvent[]; onSelect: (id: string) => void }) {
 return <><RecordTable label="Events"><thead><tr><th>Event</th><th>When</th><th>Location</th><th>Status</th><th>Action</th></tr></thead><tbody>{events.map(e=><tr key={e.id}><td>{e.name}<span className="work-record-meta">{e.event_type.replaceAll("_"," ")}</span></td><td>{e.start_time?new Date(e.start_time).toLocaleString():"Not scheduled"}</td><td>{e.location||"Not specified"}</td><td>{e.status}</td><td><WorkButton onClick={()=>onSelect(e.id)}>Open event</WorkButton></td></tr>)}</tbody></RecordTable>{!events.length&&<p>No events yet. Use New Event to create one.</p>}</>;
}

function NewEventForm({ theme, eventTypes, onCreated,onCancel,onDraftOpenChange,onSavingChange }: WorkflowState & { theme: Theme; eventTypes: EventType[]; onCreated: (id: string) => void;onCancel:()=>void }) {
  const [name, setName] = useState("");
  const [eventType, setEventType] = useState("test_drive");
  const [description, setDescription] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [location, setLocation] = useState("");
  const [capacity, setCapacity] = useState("");
  const [lists, setLists] = useState<MarketingList[]>([]);
  const [linkedListId, setLinkedListId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error,setError]=useState("");
  const dirty=[name,description,startTime,endTime,location,capacity,linkedListId].some(v=>v.trim())||eventType!=="test_drive";
  useEffect(()=>{onDraftOpenChange?.(dirty);return()=>onDraftOpenChange?.(false)},[dirty,onDraftOpenChange]);
  useEffect(()=>{onSavingChange?.(saving);return()=>onSavingChange?.(false)},[saving,onSavingChange]);

  useEffect(() => {
    listAllLists().then(setLists);
  }, []);

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleSubmit() {
    setSaving(true);setError("");
    try {
      const created = await createEvent({
        name,
        event_type: eventType,
        start_time: startTime || null,
        end_time: endTime || null,
        location,
        capacity: capacity ? Number(capacity) : null,
        description,
        linked_list_id: linkedListId || null,
      });
      onCreated(created.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-xl space-y-3">
      {error&&<p role="alert">{error}</p>}
      <WorkButton disabled={saving} onClick={onCancel}>Discard event draft</WorkButton>
      <div>
        <label className="text-xs text-zinc-500">Event Name</label>
        <WorkInput aria-label="Event Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Spring Test Drive Weekend" className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>
      <div>
        <label className="text-xs text-zinc-500">Event Type</label>
        <WorkSelect aria-label="Event Type" value={eventType} onChange={(e) => setEventType(e.target.value)} className={`w-full mt-1 rounded-md border px-2 py-1.5 text-sm ${textClass}`}>
          {eventTypes.map((t) => (
            <option key={t.key} value={t.key}>{t.name}</option>
          ))}
        </WorkSelect>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-zinc-500">Start</label>
          <WorkInput aria-label="Start" type="datetime-local" value={startTime} onChange={(e) => setStartTime(e.target.value)} className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
        </div>
        <div>
          <label className="text-xs text-zinc-500">End</label>
          <WorkInput aria-label="End" type="datetime-local" value={endTime} onChange={(e) => setEndTime(e.target.value)} className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
        </div>
      </div>
      <div>
        <label className="text-xs text-zinc-500">Location</label>
        <WorkInput aria-label="Location" value={location} onChange={(e) => setLocation(e.target.value)} className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>
      <div>
        <label className="text-xs text-zinc-500">Capacity (optional)</label>
        <WorkInput aria-label="Capacity (optional)" type="number" value={capacity} onChange={(e) => setCapacity(e.target.value)} className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>
      <div>
        <label className="text-xs text-zinc-500">Description</label>
        <WorkTextarea aria-label="Description" value={description} onChange={(e) => setDescription(e.target.value)} rows={3} className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>
      <div>
        <label className="text-xs text-zinc-500">🔗 Invite Audience -- CRM List (optional)</label>
        <WorkSelect aria-label="🔗 Invite Audience -- CRM List (optional)" value={linkedListId} onChange={(e) => setLinkedListId(e.target.value)} className={`w-full mt-1 rounded-md border px-2 py-1.5 text-sm ${textClass}`}>
          <option value="">No list -- walk-ins / self-registration only</option>
          {lists.map((l) => (
            <option key={l.id} value={l.id}>{l.name} ({(l.member_ids ?? []).length})</option>
          ))}
        </WorkSelect>
        <div className="text-xs text-zinc-500 mt-1">Publishing the event snapshots this list's members into real invited RSVPs.</div>
      </div>

      <WorkButton type="submit" variant="primary" onClick={handleSubmit} disabled={saving || !name.trim()} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
        {saving ? "Saving…" : "Save Draft"}
      </WorkButton>
    </div>
  );
}

type EventDetailTab = "rsvps" | "war_room" | "tasks" | "campaigns";

function EventDetailView({ theme, eventId, onBack, onChanged, initialTab = "rsvps", workflowMode=false }: { workflowMode?:boolean; theme: Theme; eventId: string; onBack: () => void; onChanged: () => void; initialTab?: EventDetailTab }) {
  const [detail, setDetail] = useState<EventDetail | null>(null);
  const [busy, setBusy] = useState(false);
  const [salesEmployees, setSalesEmployees] = useState<SalesEmployee[]>([]);
  const [showWalkIn, setShowWalkIn] = useState(false);
  const [walkInName, setWalkInName] = useState("");
  const [walkInPhone, setWalkInPhone] = useState("");
  const [walkInEmail, setWalkInEmail] = useState("");
  const [detailTab, setDetailTab] = useState<EventDetailTab>(initialTab);
  useEffect(()=>setDetailTab(initialTab),[initialTab]);

  function refresh() {
    getEventDetail(eventId).then(setDetail);
  }

  useEffect(() => {
    refresh();
    listSalesEmployees().then(setSalesEmployees);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [eventId]);

  async function act(fn: (id: string) => Promise<unknown>) {
    setBusy(true);
    try {
      await fn(eventId);
      refresh();
      onChanged();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleAddWalkIn() {
    setBusy(true);
    try {
      await createRsvp(eventId, { name: walkInName, phone: walkInPhone, email: walkInEmail, source: "walk_in" });
      setWalkInName("");
      setWalkInPhone("");
      setWalkInEmail("");
      setShowWalkIn(false);
      refresh();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleStatusChange(rsvpId: string, status: EventRsvp["status"]) {
    setBusy(true);
    try {
      await updateRsvpStatus(rsvpId, status);
      refresh();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handlePromoteRsvp(rsvpId: string, employeeId?: string) {
    setBusy(true);
    try {
      await promoteRsvpToLead(rsvpId, employeeId);
      refresh();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (!detail) return <div className="text-sm text-zinc-500">Loading…</div>;

  const { event, rsvp_summary, rsvps } = detail;
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  return (
    <div className="max-w-3xl space-y-3">
      <WorkButton type="submit" onClick={onBack} className="text-xs text-zinc-500 hover:text-white transition">← Back to events</WorkButton>

      <div className="flex items-center justify-between">
        <span className="text-lg font-medium">{event.name}</span>
        <span className={`text-xs px-2 py-1 rounded uppercase ${STATUS_COLORS[event.status] || "bg-zinc-800 text-zinc-400"}`}>{event.status}</span>
      </div>
      <div className="text-xs text-zinc-500">
        {event.event_type} {event.start_time ? `· ${new Date(event.start_time).toLocaleString()}` : ""} {event.location ? `· ${event.location}` : ""}
        {event.capacity ? ` · capacity ${event.capacity}` : ""}
      </div>
      {event.description && <div className="text-sm">{event.description}</div>}

      <div className="flex items-center gap-2">
        {event.status === "draft" && (
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => act(publishEvent)} className="text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            📣 Publish (invite the linked List)
          </WorkButton>
        )}
        {event.status === "scheduled" && (
          <WorkButton type="submit" disabled={busy} onClick={() => act(startEvent)} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition disabled:opacity-50">
            ▶ Start
          </WorkButton>
        )}
        {(event.status === "scheduled" || event.status === "live") && (
          <WorkButton type="submit" disabled={busy} onClick={() => act(completeEvent)} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition disabled:opacity-50">
            ✓ Complete
          </WorkButton>
        )}
        {(event.status === "draft" || event.status === "scheduled") && (
          <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => act(cancelEvent)} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-red-400 hover:text-red-300 transition disabled:opacity-50">
            ✕ Cancel
          </WorkButton>
        )}
      </div>

      {!workflowMode&&<div className="flex items-center gap-1 border-b border-zinc-800 pb-0.5">
        {([
          ["rsvps", `RSVPs (${rsvps.length})`],
          ["war_room", "🎯 War Room"],
          ["tasks", "✅ Tasks"],
          ["campaigns", "📣 Campaigns"],
        ] as [EventDetailTab, string][]).map(([key, label]) => (
          <WorkButton type="submit"
            key={key}
            onClick={() => setDetailTab(key)}
            className={`text-xs px-2.5 py-1.5 rounded-t-md transition ${
              detailTab === key
                ? "bg-brand-blue text-white font-medium"
                : "text-zinc-500 hover:text-white"
            }`}
          >
            {label}
          </WorkButton>
        ))}
      </div>}

      {detailTab === "rsvps" && (
        <>
          <div className="grid grid-cols-5 gap-2">
            {Object.entries(rsvp_summary).map(([status, count]) => (
              <div key={status} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2 text-center", "rounded-lg border border-zinc-200 bg-zinc-50 p-2 text-center")}>
                <div className="text-lg font-semibold">{count}</div>
                <div className="text-xs text-zinc-500 capitalize">{status.replace("_", " ")}</div>
              </div>
            ))}
          </div>

          <div className="flex items-center justify-between">
            <div className="text-xs font-medium">RSVPs ({rsvps.length})</div>
            <WorkButton type="submit" onClick={() => setShowWalkIn(!showWalkIn)} className="text-xs px-2.5 py-1 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition">
              + Log Walk-In
            </WorkButton>
          </div>

          {showWalkIn && (
            <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 space-y-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2")}>
              <WorkField label="Name"><WorkInput value={walkInName} onChange={(e) => setWalkInName(e.target.value)} placeholder="Name" className={`w-full rounded-md border px-2.5 py-1.5 text-xs ${textClass}`} /></WorkField>
              <WorkField label="Phone"><WorkInput value={walkInPhone} onChange={(e) => setWalkInPhone(e.target.value)} placeholder="Phone" className={`w-full rounded-md border px-2.5 py-1.5 text-xs ${textClass}`} /></WorkField>
              <WorkField label="Email"><WorkInput value={walkInEmail} onChange={(e) => setWalkInEmail(e.target.value)} placeholder="Email" className={`w-full rounded-md border px-2.5 py-1.5 text-xs ${textClass}`} /></WorkField>
              <WorkButton type="submit" variant="primary" disabled={busy || !walkInName.trim()} onClick={handleAddWalkIn} className="text-xs px-3 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
                Add RSVP
              </WorkButton>
            </div>
          )}

          <div className="space-y-1.5">
            {rsvps.map((r) => (
              <RsvpRow key={r.id} theme={theme} rsvp={r} salesEmployees={salesEmployees} onStatusChange={handleStatusChange} onPromote={handlePromoteRsvp} />
            ))}
          </div>
        </>
      )}

      {detailTab === "war_room" && <WarRoomPanel theme={theme} eventId={eventId} />}
      {detailTab === "tasks" && <EventTasksPanel theme={theme} eventId={eventId} salesEmployees={salesEmployees} />}
      {detailTab === "campaigns" && <EventCampaignsPanel theme={theme} eventId={eventId} />}
    </div>
  );
}

// --- War Room (real-time roll-up: RSVP/attendance + task completion + generated campaigns) ---

function WarRoomPanel({ theme, eventId }: { theme: Theme; eventId: string }) {
  const [room, setRoom] = useState<EventWarRoom | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getEventWarRoom(eventId).then((r) => { setRoom(r); setLoading(false); });
  }, [eventId]);

  if (loading) return <div className="text-sm text-zinc-500">Loading…</div>;
  if (!room) return <div className="text-sm text-zinc-500">War Room unavailable.</div>;

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  return (
    <div className="space-y-3">
      {room.is_live && (
        <div className="text-xs px-2.5 py-1 rounded-md bg-red-950 text-red-300 border border-red-900 inline-block font-medium">
          ● LIVE now
        </div>
      )}

      <div className="grid grid-cols-4 gap-2">
        <div className={cardClass}>
          <div className="text-lg font-semibold">{room.attendance.total_roster}</div>
          <div className="text-xs text-zinc-500">Roster</div>
        </div>
        <div className={cardClass}>
          <div className="text-lg font-semibold">{room.attendance.checked_in_count}</div>
          <div className="text-xs text-zinc-500">Checked In</div>
        </div>
        <div className={cardClass}>
          <div className="text-lg font-semibold">{room.attendance.check_in_rate_pct !== null ? `${room.attendance.check_in_rate_pct}%` : "—"}</div>
          <div className="text-xs text-zinc-500">Check-In Rate</div>
        </div>
        <div className={cardClass}>
          <div className="text-lg font-semibold">{room.attendance.no_show_count}</div>
          <div className="text-xs text-zinc-500">No-Shows</div>
        </div>
      </div>
      <div className="text-xs text-zinc-600">{room.attendance.basis}</div>
      {room.outcomes&&<WorkSection title="Recorded outcomes & follow-up" description={room.outcomes.basis}>
        <p>{room.outcomes.responses} campaign responses · {room.outcomes.completed_outcomes} completed outcomes · {room.outcomes.follow_up_due} responses needing follow-up</p>
        {Object.entries(room.outcomes.values_by_currency).map(([currency,value])=><p key={currency}>{currency}: {value.toLocaleString(undefined,{minimumFractionDigits:2,maximumFractionDigits:2})} in linked recorded value</p>)}
        {!Object.keys(room.outcomes.values_by_currency).length&&<p>No completed outcome values are linked to this event's campaigns yet.</p>}
        {room.outcomes.missing_values>0&&<p>{room.outcomes.missing_values} completed outcomes have no recorded value.</p>}
        <p>Use RSVP Management to follow up with attendees. Link appointments and outcomes in Campaigns & Advertising → Attribution & Analytics.</p>
      </WorkSection>}


      <div className={cardClass}>
        <div className="text-xs font-medium mb-2">Planning Progress</div>
        <div className="flex items-center gap-3">
          <div className="flex-1 h-2 rounded-full bg-zinc-800 overflow-hidden">
            <div className="h-full bg-brand-blue" style={{ width: `${room.project_management.completion_pct ?? 0}%` }} />
          </div>
          <div className="text-xs font-medium">{room.project_management.completion_pct !== null ? `${room.project_management.completion_pct}%` : "no tasks"}</div>
        </div>
        {room.project_management.overdue_count > 0 && (
          <div className="text-xs text-red-400 mt-2">⚠ {room.project_management.overdue_count} task(s) overdue</div>
        )}
      </div>

      <div className={cardClass}>
        <div className="text-xs font-medium mb-2">Campaigns Generated ({room.campaigns_generated})</div>
        {room.recent_campaigns.length === 0 ? (
          <div className="text-xs text-zinc-500">None yet -- use the Campaigns tab to generate one.</div>
        ) : (
          <div className="space-y-1">
            {room.recent_campaigns.map((c) => (
              <div key={c.id} className="text-xs flex items-center justify-between">
                <span>{c.name}</span>
                <span className="text-zinc-500 uppercase">{c.status} · {c.channel}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// --- Project Management (real planning checklist) ---

function EventTasksPanel({ theme, eventId, salesEmployees }: { theme: Theme; eventId: string; salesEmployees: SalesEmployee[] }) {
  const [tasks, setTasks] = useState<EventTask[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [title, setTitle] = useState("");
  const [assignee, setAssignee] = useState("");
  const [dueDate, setDueDate] = useState("");

  function refresh() {
    setLoading(true);
    listEventTasks(eventId).then((t) => { setTasks(t); setLoading(false); });
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [eventId]);

  async function handleCreate() {
    if (!title.trim()) return;
    setBusy(true);
    try {
      await createEventTask(eventId, { title, assignee_employee_id: assignee || null, due_date: dueDate || null });
      setTitle(""); setAssignee(""); setDueDate("");
      refresh();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleStatus(taskId: string, status: EventTaskStatus) {
    setBusy(true);
    try {
      await updateEventTaskStatus(taskId, status);
      refresh();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleDelete(taskId: string) {
    setBusy(true);
    try {
      await deleteEventTask(taskId);
      refresh();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5");

  const STATUS_LABEL: Record<EventTaskStatus, string> = { open: "Open", in_progress: "In Progress", done: "Done", blocked: "Blocked" };
  const STATUS_STYLE: Record<EventTaskStatus, string> = {
    open: "bg-zinc-800 text-zinc-400",
    in_progress: "bg-amber-950 text-amber-300",
    done: "bg-emerald-950 text-emerald-300",
    blocked: "bg-red-950 text-red-300",
  };

  return (
    <div className="space-y-3">
      <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 space-y-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2")}>

        <WorkField label="+ New Task"><WorkInput value={title} onChange={(e) => setTitle(e.target.value)} placeholder="e.g. Confirm catering delivery" className={`w-full rounded-md border px-2.5 py-1.5 text-xs ${textClass}`} /></WorkField>
        <div className="flex gap-2">
          <WorkField label="Assigned employee"><WorkSelect value={assignee} onChange={(e) => setAssignee(e.target.value)} className={`flex-1 rounded-md border px-2.5 py-1.5 text-xs ${textClass}`}>
            <option value="">Unassigned</option>
            {salesEmployees.map((emp) => <option key={emp.id} value={emp.id}>{emp.name}</option>)}
          </WorkSelect></WorkField>
          <WorkField label="Due Date"><WorkInput type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} className={`rounded-md border px-2.5 py-1.5 text-xs ${textClass}`} /></WorkField>
        </div>
        <WorkButton type="submit" variant="primary" disabled={busy || !title.trim()} onClick={handleCreate} className="text-xs px-3 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
          Add Task
        </WorkButton>
      </div>

      {loading ? (
        <div className="text-sm text-zinc-500">Loading…</div>
      ) : tasks.length === 0 ? (
        <div className="text-xs text-zinc-500">No planning tasks yet.</div>
      ) : (
        <div className="space-y-1.5">
          {tasks.map((t) => (
            <div key={t.id} className={`${cardClass} flex items-center justify-between gap-2 flex-wrap`}>
              <div>
                <div className="text-xs font-medium">{t.title}</div>
                <div className="text-xs text-zinc-500">
                  {t.assignee_employee_id ? `→ ${t.assignee_employee_id}` : "Unassigned"}
                  {t.due_date ? ` · due ${t.due_date}` : ""}
                </div>
              </div>
              <div className="flex items-center gap-1.5">
                <span className={`text-xs px-2 py-0.5 rounded uppercase ${STATUS_STYLE[t.status]}`}>{STATUS_LABEL[t.status]}</span>
                <WorkField label="Status"><WorkSelect
                  value={t.status}
                  onChange={(e) => handleStatus(t.id, e.target.value as EventTaskStatus)}
                  className={`rounded-md border px-1.5 py-1 text-xs ${textClass}`}
                >
                  {(Object.keys(STATUS_LABEL) as EventTaskStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
                </WorkSelect></WorkField>
                <WorkButton type="submit" variant="danger" onClick={() => handleDelete(t.id)} className="text-xs text-zinc-500 hover:text-red-400 transition">✕</WorkButton>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

// --- Campaign Generator (AI-drafted promo copy -> real linked Campaign) ---

function EventCampaignsPanel({ theme, eventId }: { theme: Theme; eventId: string }) {
  const [campaigns, setCampaigns] = useState<EventCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [channel, setChannel] = useState<"email" | "sms">("email");
  const [tone, setTone] = useState("friendly and professional");
  const [draft, setDraft] = useState<EventCampaignDraft | null>(null);

  function refresh() {
    setLoading(true);
    listCampaignsForEvent(eventId).then((c) => { setCampaigns(c); setLoading(false); });
  }

  useEffect(() => { refresh(); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [eventId]);

  async function handleGenerateDraft() {
    setBusy(true);
    try {
      const d = await generateEventCampaignDraft(eventId, channel, tone);
      setDraft(d);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function handleCreateCampaign() {
    setBusy(true);
    try {
      await createEventCampaign(eventId, channel, tone);
      setDraft(null);
      refresh();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  return (
    <div className="space-y-3">
      <div className={`${cardClass} space-y-2`}>
        <div className="text-xs font-medium">✨ AI Campaign Generator</div>
        <div className="text-xs text-zinc-500">
          Drafts real promo copy for this event, then creates a real Campaign targeting its actual invite/RSVP roster (never a blanket broadcast).
        </div>
        <div className="flex gap-2">
          <WorkField label="Channel"><WorkSelect value={channel} onChange={(e) => setChannel(e.target.value as "email" | "sms")} className={`rounded-md border px-2.5 py-1.5 text-xs ${textClass}`}>
            <option value="email">Email</option>
            <option value="sms">SMS</option>
          </WorkSelect></WorkField>
          <WorkField label="Tone"><WorkInput value={tone} onChange={(e) => setTone(e.target.value)} placeholder="Tone" className={`flex-1 rounded-md border px-2.5 py-1.5 text-xs ${textClass}`} /></WorkField>
        </div>
        <div className="flex gap-2">
          <WorkButton type="submit" disabled={busy} onClick={handleGenerateDraft} className="text-xs px-3 py-1 rounded border border-zinc-700 text-zinc-300 hover:text-white transition disabled:opacity-50">
            Generate Draft
          </WorkButton>
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleCreateCampaign} className="text-xs px-3 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
            ✓ Generate + Create Campaign
          </WorkButton>
        </div>

        {draft && (
          <div className={tc(theme, "rounded-md border border-zinc-700 bg-black/30 p-2.5 space-y-1", "rounded-md border border-zinc-300 bg-white p-2.5 space-y-1")}>
            <div className="text-xs text-zinc-500">Preview -- goal: {draft.goal}</div>
            {Object.entries(draft.copy).map(([k, v]) => (
              <div key={k} className="text-xs"><span className="text-zinc-500">{k}:</span> {v}</div>
            ))}
          </div>
        )}
      </div>

      <div className="text-xs font-medium">Generated Campaigns ({campaigns.length})</div>
      {loading ? (
        <div className="text-sm text-zinc-500">Loading…</div>
      ) : campaigns.length === 0 ? (
        <div className="text-xs text-zinc-500">None yet.</div>
      ) : (
        <div className="space-y-1.5">
          {campaigns.map((c) => (
            <div key={c.id} className={`${cardClass} flex items-center justify-between`}>
              <div className="text-xs">{c.name}</div>
              <div className="text-xs text-zinc-500 uppercase">{c.status} · {c.channel} · {c.audience_count} recipients</div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function RsvpRow({
  theme,
  rsvp,
  salesEmployees,
  onStatusChange,
  onPromote,
}: {
  theme: Theme;
  rsvp: EventRsvp;
  salesEmployees: SalesEmployee[];
  onStatusChange: (id: string, status: EventRsvp["status"]) => void;
  onPromote: (id: string, employeeId?: string) => void;
}) {
  const [assignTo, setAssignTo] = useState("");

  return (
    <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5 flex items-center justify-between gap-2 flex-wrap", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5 flex items-center justify-between gap-2 flex-wrap")}>
      <div>
        <div className="text-sm">{rsvp.name}</div>
        <div className="text-xs text-zinc-500">{rsvp.phone || rsvp.email || "—"} · {rsvp.source}</div>
      </div>
      <div className="flex items-center gap-1.5">
        <WorkField label="Status"><WorkSelect
          value={rsvp.status}
          onChange={(e) => onStatusChange(rsvp.id, e.target.value as EventRsvp["status"])}
          className={tc(theme, "text-xs rounded border border-zinc-700 bg-zinc-900 text-white px-1.5 py-1", "text-xs rounded border border-zinc-300 bg-white text-black px-1.5 py-1")}
        >
          {["invited", "confirmed", "attended", "no_show", "cancelled"].map((s) => (
            <option key={s} value={s}>{s.replace("_", " ")}</option>
          ))}
        </WorkSelect></WorkField>
        {rsvp.promoted_to_lead_id ? (
          <span className="text-xs px-1.5 py-0.5 rounded bg-green-900 text-green-300">→ {rsvp.promoted_to_lead_id}</span>
        ) : (
          <>
            <WorkField label="Assign to employee"><WorkSelect value={assignTo} onChange={(e) => setAssignTo(e.target.value)} className={tc(theme, "text-xs rounded border border-zinc-700 bg-zinc-900 text-white px-1.5 py-1", "text-xs rounded border border-zinc-300 bg-white text-black px-1.5 py-1")}>
              <option value="">Unassigned</option>
              {salesEmployees.map((e) => (
                <option key={e.id} value={e.id}>{e.name}</option>
              ))}
            </WorkSelect></WorkField>
            <WorkButton type="submit" variant="primary" onClick={() => onPromote(rsvp.id, assignTo || undefined)} className="text-xs px-2 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition">
              Promote →
            </WorkButton>
          </>
        )}
      </div>
    </div>
  );
}
