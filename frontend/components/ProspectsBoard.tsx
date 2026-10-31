"use client";
import { WorkInput, WorkButton, WorkSelect, WorkTextarea , WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Sales' "Prospects" Top Menu item -- the CRM-style lead center (Sam's Sales sub-menu
// spec, 2026-07-16, follow-up to the Deal Desk build): "When opening a prospect:
// Customer Profile, Activity Timeline, Communication Hub (Call/Text/Email/Video, all
// logged automatically), Task Management, Customer Notes, Next Best Action."
//
// Default view is the real source-bucketed summary (core/sales_menu.py's prospects(),
// unchanged) plus a search box; searching or clicking a lead opens the full Lead
// Record (core/lead_record.py, session 92 follow-up) -- a real merged activity
// timeline (audit pipeline-transition events + logged communications/notes + task
// events), real task management, and a rules-based Next Best Action (not a fabricated
// AI/email-tracking signal -- see core/lead_record.py's module docstring for why).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getProspectsSummary,
  getLeadRecord,
  logLeadActivity,
  addLeadNote,
  createLeadTask,
  completeLeadTask,
  convertLeadToCustomer,
  searchLeads,
  type ProspectsSummary,
  type LeadRecord,
  type CommunicationCategory,
  type NoteCategory,
  type LeadTaskType,
  type LeadSearchResult,
} from "@/lib/leadRecord";
import { NewDealModal, DealDetailModal } from "@/components/DealDeskBoard";
import { getSession } from "@/lib/auth";
import type { CustomerBrief } from "@/lib/deals";
import { getSalesEmployees, transferLead, type SalesEmployeeBrief } from "@/lib/salesOverview";
import { createAppointment, type AppointmentType } from "@/lib/appointments";
import { InlineEntityFields } from "@/components/InlineEntityFields";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const KPI_RIBBON = PRODUCT_ACCENT_COLORS;

const COMM_LABELS: Record<CommunicationCategory, string> = { call: "📞 Call", text: "💬 Text", email: "✉️ Email", video: "🎥 Video" };
const NOTE_LABELS: Record<NoteCategory, string> = { objection: "Objection", family: "Family", competitor: "Competitor", payment_goal: "Payment Goal", general: "General" };
const TASK_LABELS: Record<LeadTaskType, string> = { call: "Call", send_pricing: "Send Pricing", schedule_appraisal: "Schedule Appraisal", follow_up_after_demo: "Follow Up After Demo", custom: "Custom" };

const NBA_TONE: Record<string, string> = {
  Overdue: "border-red-900 bg-red-950/30 text-red-300",
  "Call now": "border-amber-900 bg-amber-950/30 text-amber-300",
  "Follow up today": "border-amber-900 bg-amber-950/30 text-amber-300",
  "On track": "border-green-900 bg-green-950/30 text-green-300",
  None: "border-zinc-800 bg-zinc-900/40 text-zinc-400",
};

function nbaTone(action: string): string {
  const key = Object.keys(NBA_TONE).find((k) => action.startsWith(k));
  return NBA_TONE[key || "On track"] || NBA_TONE["On track"];
}

export function ProspectsBoard({ theme }: { theme: Theme }) {
  const [summary, setSummary] = useState<ProspectsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<LeadSearchResult[]>([]);
  const [openLeadId, setOpenLeadId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    getProspectsSummary()
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleSearch(q: string) {
    setQuery(q);
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    try {
      setResults(await searchLeads(q));
    } catch {
      setResults([]);
    }
  }

  const buckets = summary?.by_source_bucket || {};

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      {/* KPI strip */}
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        {[
          { label: "Total Leads", value: summary?.total_leads ?? 0 },
          { label: "Needing Assignment", value: summary?.needing_assignment?.count ?? 0 },
          { label: "Unsold Showroom Traffic", value: summary?.unsold_showroom_traffic?.count ?? 0 },
          { label: "Lost Opportunities", value: summary?.lost_opportunities?.count ?? 0 },
        ].map((k, i) => (
          <div key={k.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5" style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }} />
            <div className="text-2xl font-semibold">{k.value}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k.label}</div>
          </div>
        ))}
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2.5", "border-b border-zinc-200 px-4 py-2.5")}>
        <WorkField label="Search leads by name/email/phone, or paste a LEAD- id"><WorkInput
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="Search leads by name/email/phone, or paste a LEAD- id…"
          className={tc(
            theme,
            "w-full rounded-md border border-zinc-700 bg-zinc-900 text-white placeholder:text-zinc-600 px-3 py-1.5 text-sm",
            "w-full rounded-md border border-zinc-300 bg-white text-black placeholder:text-zinc-400 px-3 py-1.5 text-sm"
          )}
        /></WorkField>
        {results.length > 0 && (
          <div className={tc(theme, "mt-1.5 border border-zinc-800 rounded-md divide-y divide-zinc-800 max-h-48 overflow-y-auto", "mt-1.5 border border-zinc-200 rounded-md divide-y divide-zinc-200 max-h-48 overflow-y-auto")}>
            {results.map((r) => (
              <WorkButton type="submit"
                key={r.id}
                onClick={() => {
                  setOpenLeadId(r.id);
                  setResults([]);
                  setQuery("");
                }}
                className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-zinc-800/50 transition"
              >
                {String(r.attributes.FirstName || "")} {String(r.attributes.LastName || "")} — {String(r.attributes.Source || "")} · {String(r.attributes.PipelineState || "")}
              </WorkButton>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">By Lead Source</div>
              <div className="grid grid-cols-3 gap-2">
                {Object.entries(buckets).map(([bucket, count]) => (
                  <div key={bucket} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
                    <div className="text-lg font-semibold">{count}</div>
                    <div className="text-xs text-zinc-500">{bucket}</div>
                  </div>
                ))}
              </div>
            </div>

            {summary?.equity_customers != null && (
              <div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Equity Customers (Database Mining)</div>
                <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 text-xs text-zinc-400", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 text-xs text-zinc-600")}>
                  {Array.isArray(summary.equity_customers)
                    ? `${summary.equity_customers.length} candidate(s) — reused from Marketing's database mining.`
                    : typeof summary.equity_customers === "object"
                    ? JSON.stringify(summary.equity_customers).slice(0, 200)
                    : String(summary.equity_customers)}
                </div>
              </div>
            )}

            {summary?.not_yet_tracked && (
              <div className="text-xs text-zinc-600">
                {Object.entries(summary.not_yet_tracked).map(([k, v]) => (
                  <div key={k}>• {v}</div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {openLeadId && (
        <LeadRecordModal
          theme={theme}
          leadId={openLeadId}
          onClose={() => setOpenLeadId(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

export function LeadRecordModal({
  theme,
  leadId,
  onClose,
  onChanged,
  inline = false,
}: {
  theme: Theme;
  leadId: string;
  onClose: () => void;
  onChanged: () => void;
  inline?: boolean;
}) {
  const [record, setRecord] = useState<LeadRecord | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<"timeline" | "comms" | "notes" | "tasks">("timeline");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [convertedCustomer, setConvertedCustomer] = useState<CustomerBrief | null>(null);
  const [newDealOpen, setNewDealOpen] = useState(false);
  const [createdDealId, setCreatedDealId] = useState<string | null>(null);
  const [transferOpen, setTransferOpen] = useState(false);
  const [salesEmployees, setSalesEmployees] = useState<SalesEmployeeBrief[]>([]);
  const [transferTarget, setTransferTarget] = useState("");
  const [scheduleOpen, setScheduleOpen] = useState(false);
  const [scheduleType, setScheduleType] = useState<AppointmentType>("showroom_visit");
  const [scheduleStart, setScheduleStart] = useState("");
  const [scheduleConfirm, setScheduleConfirm] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    getLeadRecord(leadId)
      .then(setRecord)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [leadId]);

  async function act<T>(fn: () => Promise<T>) {
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

  async function handleConvert() {
    setBusy(true);
    setError(null);
    try {
      const customer = await convertLeadToCustomer(leadId);
      setConvertedCustomer({
        id: customer.id,
        name: `${customer.FirstName || ""} ${customer.LastName || ""}`.trim() || String(customer.id),
        email: (customer.Email as string) || null,
        phone: (customer.Phone as string) || null,
      });
      refresh();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function openTransfer() {
    setTransferOpen(true);
    if (salesEmployees.length === 0) {
      try {
        setSalesEmployees(await getSalesEmployees());
      } catch {
        setSalesEmployees([]);
      }
    }
  }

  async function handleTransfer() {
    if (!transferTarget) return;
    await act(() => transferLead(leadId, transferTarget));
    setTransferOpen(false);
    setTransferTarget("");
  }

  async function handleSchedule() {
    if (!scheduleStart) return;
    setBusy(true);
    setError(null);
    try {
      await createAppointment({
        department: "Sales",
        appointment_type: scheduleType,
        scheduled_start: new Date(scheduleStart).toISOString(),
        lead_id: leadId,
      });
      setScheduleConfirm(`Scheduled for ${new Date(scheduleStart).toLocaleString()}`);
      setScheduleOpen(false);
      setScheduleStart("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const attrs = record?.lead?.attributes || {};
  const alreadyConverted = !!attrs.ConvertedCustomerID;

  if (createdDealId) return <DealDetailModal inline={inline} theme={theme} dealId={createdDealId} initialTab="worksheet" session={getSession()} onClose={() => { setCreatedDealId(null); refresh(); }} onChanged={onChanged} />;

  return (
    <WorkOverlay data-department-work="" className={inline ? "workspace-inline-editor" : "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"} onClick={inline || busy ? undefined : onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={inline ? "workspace-editor-surface flex flex-col" : tc(theme, "w-full max-w-3xl max-h-[92vh] flex flex-col rounded-xl border border-black/20 bg-brand-charcoal text-white shadow-2xl", "w-full max-w-3xl max-h-[92vh] flex flex-col rounded-xl border border-zinc-200 bg-white text-black shadow-2xl")}
      >
        <div className={tc(theme, "flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0", "flex items-center justify-between px-4 py-3 border-b border-zinc-200 shrink-0")}>
          <div>
            <div className="work-detail-title">
              {String(attrs.FirstName || "")} {String(attrs.LastName || "")}
            </div>
            <div className="text-xs text-zinc-500">{leadId} · {String(attrs.PipelineState || "")}</div>
          </div>
          <WorkButton type="submit" disabled={busy} aria-label="Close lead record" onClick={onClose} className="text-zinc-500 hover:text-white text-sm">{inline ? "← Back to workspace" : "✕"}</WorkButton>
        </div>

        {loading || !record ? (
          <div className="p-4 text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div className="p-4 pb-0 space-y-3 shrink-0">
              {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

              <div className={`rounded-lg border px-3 py-2 text-xs flex items-center justify-between gap-2 ${nbaTone(record.next_best_action.action)}`}>
                <div>
                  <span className="font-semibold">Next Best Action: {record.next_best_action.action}</span>
                  <span className="ml-2 opacity-80">{record.next_best_action.reason}</span>
                </div>
              </div>

              {/* Customer Profile */}
              <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 space-y-2 text-xs", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2 text-xs")}>
                <div className="flex items-center justify-between gap-2">
                  <h3>Customer profile</h3>
                  <InlineEntityFields
                    theme={theme}
                    entityId={leadId}
                    fields={[
                      { key: "Phone", label: "Phone", value: attrs.Phone },
                      { key: "Email", label: "Email", value: attrs.Email },
                      { key: "Source", label: "Source", value: attrs.Source },
                      { key: "City", label: "City", value: attrs.City },
                      { key: "State", label: "State", value: attrs.State },
                    ]}
                    onSaved={(patch) =>
                      setRecord((prev) =>
                        prev ? { ...prev, lead: { ...prev.lead, attributes: { ...prev.lead.attributes, ...patch } } } : prev
                      )
                    }
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <div><span className="text-zinc-500">Phone: </span>{String(attrs.Phone || "—")}</div>
                  <div><span className="text-zinc-500">Email: </span>{String(attrs.Email || "—")}</div>
                  <div><span className="text-zinc-500">Source: </span>{String(attrs.Source || "—")}</div>
                  <div><span className="text-zinc-500">City/State: </span>{String(attrs.City || "—")}, {String(attrs.State || "—")}</div>
                  <div><span className="text-zinc-500">Assigned: </span>{String(attrs.AssignedSalesperson || "—")} <span className="text-zinc-600">(via Transfer Lead)</span></div>
                  <div><span className="text-zinc-500">Vehicle Interest: </span>{record.related_entities.find((r) => (r as { entity_type?: string }).entity_type === "Vehicle") ? "1 vehicle linked" : "—"}</div>
                </div>
              </div>

              <div className="flex items-center gap-2 flex-wrap">
                {alreadyConverted || convertedCustomer ? (
                  <>
                    <span className="text-xs px-2 py-1 rounded bg-green-900 text-green-300">
                      ✓ Converted to customer {convertedCustomer?.id || String(attrs.ConvertedCustomerID)}
                    </span>
                    <WorkButton type="submit" variant="primary" onClick={() => setNewDealOpen(true)} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition">
                      + Create Deal
                    </WorkButton>
                  </>
                ) : (
                  <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleConvert} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
                    Convert to Customer
                  </WorkButton>
                )}
                {!transferOpen ? (
                  <WorkButton type="submit" onClick={openTransfer} className={tc(theme, "text-xs px-2.5 py-1 rounded border border-zinc-700 text-zinc-300 hover:text-white transition", "text-xs px-2.5 py-1 rounded border border-zinc-300 text-zinc-600 hover:text-black transition")}>
                    ⇄ Transfer Lead
                  </WorkButton>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <WorkField label="Transfer Target"><WorkSelect
                      value={transferTarget}
                      onChange={(e) => setTransferTarget(e.target.value)}
                      className={tc(theme, "text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1", "text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1")}
                    >
                      <option value="">Transfer to…</option>
                      {salesEmployees.map((e) => (
                        <option key={e.id} value={e.id}>{e.name || e.id}{e.title ? ` — ${e.title}` : ""}</option>
                      ))}
                    </WorkSelect></WorkField>
                    <WorkButton type="submit" variant="primary" disabled={busy || !transferTarget} onClick={handleTransfer} className="text-xs px-2 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
                      Confirm
                    </WorkButton>
                    <WorkButton type="submit" onClick={() => setTransferOpen(false)} className="text-xs px-2 py-1 rounded text-zinc-500 hover:text-white transition">
                      Cancel
                    </WorkButton>
                  </div>
                )}

                {!scheduleOpen ? (
                  <WorkButton type="submit" onClick={() => setScheduleOpen(true)} className={tc(theme, "text-xs px-2.5 py-1 rounded border border-zinc-700 text-zinc-300 hover:text-white transition", "text-xs px-2.5 py-1 rounded border border-zinc-300 text-zinc-600 hover:text-black transition")}>
                    📅 Schedule Appointment
                  </WorkButton>
                ) : (
                  <div className="flex items-center gap-1.5">
                    <WorkField label="Appointment type"><WorkSelect
                      value={scheduleType}
                      onChange={(e) => setScheduleType(e.target.value as AppointmentType)}
                      className={tc(theme, "text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1", "text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1")}
                    >
                      <option value="showroom_visit">Showroom Visit</option>
                      <option value="test_drive">Test Drive</option>
                      <option value="credit_app">Credit App</option>
                      <option value="paperwork">Paperwork</option>
                      <option value="other">Other</option>
                    </WorkSelect></WorkField>
                    <WorkField label="Appointment start"><WorkInput
                      type="datetime-local"
                      value={scheduleStart}
                      onChange={(e) => setScheduleStart(e.target.value)}
                      className={tc(theme, "text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1", "text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1")}
                    /></WorkField>
                    <WorkButton type="submit" variant="primary" disabled={busy || !scheduleStart} onClick={handleSchedule} className="text-xs px-2 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
                      Confirm
                    </WorkButton>
                    <WorkButton type="submit" onClick={() => setScheduleOpen(false)} className="text-xs px-2 py-1 rounded text-zinc-500 hover:text-white transition">
                      Cancel
                    </WorkButton>
                  </div>
                )}
                {scheduleConfirm && <span className="text-xs px-2 py-1 rounded bg-green-900 text-green-300">✓ {scheduleConfirm}</span>}
              </div>
            </div>

            <div className={tc(theme, "border-b border-zinc-800 px-4 py-2 flex items-center gap-1.5 mt-3 shrink-0", "border-b border-zinc-200 px-4 py-2 flex items-center gap-1.5 mt-3 shrink-0")}>
              {([
                { key: "timeline", label: "Activity Timeline" },
                { key: "comms", label: "Communication Hub" },
                { key: "notes", label: "Customer Notes" },
                { key: "tasks", label: `Tasks${record.overdue_task_count ? ` (${record.overdue_task_count} overdue)` : ""}` },
              ] as const).map((t) => (
                <WorkButton data-work-view aria-pressed={tab === t.key} type="submit"
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={
                    tab === t.key
                      ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                      : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition")
                  }
                >
                  {t.label}
                </WorkButton>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto p-4">
              {tab === "timeline" && <TimelineTab theme={theme} record={record} />}
              {tab === "comms" && <CommsTab theme={theme} leadId={leadId} record={record} busy={busy} act={act} />}
              {tab === "notes" && <NotesTab theme={theme} leadId={leadId} record={record} busy={busy} act={act} />}
              {tab === "tasks" && <TasksTab theme={theme} leadId={leadId} record={record} busy={busy} act={act} />}
            </div>
          </>
        )}
      </div>

      {newDealOpen && (
        <NewDealModal inline={inline}
          theme={theme}
          initialCustomer={convertedCustomer || { id: String(attrs.ConvertedCustomerID), name: `${attrs.FirstName || ""} ${attrs.LastName || ""}`.trim(), email: (attrs.Email as string) || null, phone: (attrs.Phone as string) || null }}
          onClose={() => setNewDealOpen(false)}
          onCreated={(id) => { setNewDealOpen(false); setCreatedDealId(id); onChanged(); }}
        />
      )}
    </WorkOverlay>
  );
}

const TIMELINE_ICON: Record<string, string> = {
  workflow_transition: "🔀",
  communication: "💬",
  note: "📝",
  task_created: "🗓",
  task_completed: "✅",
};

function TimelineTab({ theme, record }: { theme: Theme; record: LeadRecord }) {
  if (record.timeline.length === 0) return <div className="text-sm text-zinc-500">No activity yet.</div>;

  return (
    <div className="space-y-1.5">
      {record.timeline.map((e, i) => (
        <div key={i} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5 flex items-start gap-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5 flex items-start gap-2")}>
          <span>{TIMELINE_ICON[e.type] || "•"}</span>
          <div className="flex-1 min-w-0">
            <div className="text-xs">{e.summary}</div>
            <div className="text-xs text-zinc-500">{e.actor || "system"} · {fmt(e.timestamp)}</div>
          </div>
        </div>
      ))}
    </div>
  );
}

function CommsTab({
  theme,
  leadId,
  record,
  busy,
  act,
}: {
  theme: Theme;
  leadId: string;
  record: LeadRecord;
  busy: boolean;
  act: <T>(fn: () => Promise<T>) => Promise<void>;
}) {
  const [category, setCategory] = useState<CommunicationCategory>("call");
  const [body, setBody] = useState("");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleLog() {
    await act(() => logLeadActivity(leadId, category, body));
    setBody("");
  }

  return (
    <div className="space-y-3">
      <div className={tc(theme, "rounded-lg border border-zinc-800 p-3 space-y-2", "rounded-lg border border-zinc-200 p-3 space-y-2")}>
        <div className="flex gap-1.5">
          {(Object.keys(COMM_LABELS) as CommunicationCategory[]).map((c) => (
            <WorkButton type="submit"
              key={c}
              onClick={() => setCategory(c)}
              className={category === c ? "text-xs px-2.5 py-1.5 rounded-md bg-brand-blue text-white font-medium transition" : "text-xs px-2.5 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition"}
            >
              {COMM_LABELS[c]}
            </WorkButton>
          ))}
        </div>
        <WorkField label="What happened on this touch"><WorkTextarea value={body} onChange={(e) => setBody(e.target.value)} rows={2} placeholder="What happened on this touch…" className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
        <WorkButton type="submit" variant="primary" disabled={busy || !body.trim()} onClick={handleLog} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          Log {COMM_LABELS[category]}
        </WorkButton>
      </div>

      <div className="space-y-1.5">
        {record.communications.length === 0 ? (
          <div className="text-sm text-zinc-500">No communications logged yet.</div>
        ) : (
          record.communications.map((n) => (
            <div key={n.id} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5")}>
              <div className="text-xs text-zinc-500">{COMM_LABELS[n.category as CommunicationCategory] || n.category} · {n.created_by} · {fmt(n.created_at)}</div>
              <div className="text-xs mt-0.5">{n.body}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function NotesTab({
  theme,
  leadId,
  record,
  busy,
  act,
}: {
  theme: Theme;
  leadId: string;
  record: LeadRecord;
  busy: boolean;
  act: <T>(fn: () => Promise<T>) => Promise<void>;
}) {
  const [category, setCategory] = useState<NoteCategory>("general");
  const [body, setBody] = useState("");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleAdd() {
    await act(() => addLeadNote(leadId, category, body));
    setBody("");
  }

  return (
    <div className="space-y-3">
      <div className={tc(theme, "rounded-lg border border-zinc-800 p-3 space-y-2", "rounded-lg border border-zinc-200 p-3 space-y-2")}>
        <WorkField label="Category"><WorkSelect value={category} onChange={(e) => setCategory(e.target.value as NoteCategory)} className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`}>
          {(Object.keys(NOTE_LABELS) as NoteCategory[]).map((c) => (
            <option key={c} value={c}>{NOTE_LABELS[c]}</option>
          ))}
        </WorkSelect></WorkField>
        <WorkField label="Objection, family info, competitor mentioned, payment goal"><WorkTextarea value={body} onChange={(e) => setBody(e.target.value)} rows={2} placeholder="Objection, family info, competitor mentioned, payment goal…" className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
        <WorkButton type="submit" variant="primary" disabled={busy || !body.trim()} onClick={handleAdd} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          + Add Note
        </WorkButton>
      </div>

      <div className="space-y-1.5">
        {record.notes.length === 0 ? (
          <div className="text-sm text-zinc-500">No notes yet.</div>
        ) : (
          record.notes.map((n) => (
            <div key={n.id} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5")}>
              <div className="text-xs text-zinc-500">{NOTE_LABELS[n.category as NoteCategory] || n.category} · {n.created_by} · {fmt(n.created_at)}</div>
              <div className="text-xs mt-0.5">{n.body}</div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

function TasksTab({
  theme,
  leadId,
  record,
  busy,
  act,
}: {
  theme: Theme;
  leadId: string;
  record: LeadRecord;
  busy: boolean;
  act: <T>(fn: () => Promise<T>) => Promise<void>;
}) {
  const [taskType, setTaskType] = useState<LeadTaskType>("call");
  const [description, setDescription] = useState("");
  const [dueAt, setDueAt] = useState("");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleAdd() {
    await act(() => createLeadTask(leadId, { task_type: taskType, description, due_at: dueAt || null }));
    setDescription("");
    setDueAt("");
  }

  const now = new Date().toISOString();
  const open = record.tasks.filter((t) => !t.completed);
  const completed = record.tasks.filter((t) => t.completed);

  return (
    <div className="space-y-3">
      <div className={tc(theme, "rounded-lg border border-zinc-800 p-3 space-y-2", "rounded-lg border border-zinc-200 p-3 space-y-2")}>
        <div className="grid grid-cols-2 gap-2">
          <WorkField label="Task type"><WorkSelect value={taskType} onChange={(e) => setTaskType(e.target.value as LeadTaskType)} className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`}>
            {(Object.keys(TASK_LABELS) as LeadTaskType[]).map((t) => (
              <option key={t} value={t}>{TASK_LABELS[t]}</option>
            ))}
          </WorkSelect></WorkField>
          <WorkField label="Due date"><WorkInput type="datetime-local" value={dueAt} onChange={(e) => setDueAt(e.target.value)} className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
        </div>
        <WorkField label="Description"><WorkInput value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description (e.g. Call tomorrow about financing)…" className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
        <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleAdd} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          + Add Task
        </WorkButton>
      </div>

      <div className="space-y-1.5">
        {open.length === 0 && completed.length === 0 && <div className="text-sm text-zinc-500">No tasks yet.</div>}
        {open.map((t) => {
          const overdue = !!t.due_at && t.due_at < now;
          return (
            <div key={t.id} className={tc(theme, `rounded-lg border p-2.5 flex items-center justify-between gap-2 ${overdue ? "border-red-900 bg-red-950/20" : "border-black/20 bg-brand-charcoal"}`, `rounded-lg border p-2.5 flex items-center justify-between gap-2 ${overdue ? "border-red-300 bg-red-50" : "border-zinc-200 bg-zinc-50"}`)}>
              <div>
                <div className="text-xs font-medium">{TASK_LABELS[t.task_type]}{t.description ? `: ${t.description}` : ""}</div>
                <div className="text-xs text-zinc-500">{overdue ? "Overdue — " : "Due "}{fmt(t.due_at)} · {t.assigned_to}</div>
              </div>
              <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => act(() => completeLeadTask(t.id))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50 shrink-0">
                Complete
              </WorkButton>
            </div>
          );
        })}
        {completed.length > 0 && (
          <div className="pt-2">
            <div className="text-xs text-zinc-500 mb-1">Completed</div>
            {completed.map((t) => (
              <div key={t.id} className="text-xs text-zinc-600 py-0.5">✓ {TASK_LABELS[t.task_type]}{t.description ? `: ${t.description}` : ""} — {fmt(t.completed_at)}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
