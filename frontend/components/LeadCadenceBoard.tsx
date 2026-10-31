"use client";
import { WorkSelect, WorkButton, WorkInput } from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";

// Lead Management (session 102 follow-up) -- rendered inside Sales' "Lead
// Management" workflow modal (core/workflow_catalog.py's sales.lead_cadence). Sam:
// "it needs to be a working process, not just a list" -- rather than building new
// backend logic, every one of this workflow's 5 named tabs reuses functionality
// that was already real and already built for Prospects/Appointments/Deal Desk
// (core/lead_record.py, core/lead_tasks.py, core/appointments.py,
// core/lead_conversion.py, core/deals.py) -- this is the connective tissue thread
// through a specific tracked Lead ID rather than a fourth parallel lead-detail UI.
import { useEffect, useState } from "react";
import {
  getLeadRecord,
  addLeadNote,
  convertLeadToCustomer,
  type LeadRecord,
  type NoteCategory,
} from "@/lib/leadRecord";
import { transferLead, getSalesEmployees, type SalesEmployeeBrief } from "@/lib/salesOverview";
import { createAppointment, type AppointmentType } from "@/lib/appointments";
import { NewDealModal } from "@/components/DealDeskBoard";
import type { CustomerBrief } from "@/lib/deals";

export type LeadCadenceSection = "assignment" | "timeline" | "needs_analysis" | "appointments" | "opportunity";

const NOTE_CATEGORIES: NoteCategory[] = ["objection", "family", "competitor", "payment_goal", "general"];
const APPT_TYPES: AppointmentType[] = ["showroom_visit", "test_drive", "trade_appraisal", "paperwork"];

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function NoLead() {
  return (
    <div className="p-4 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/40">
      <p className="text-xs text-zinc-500 leading-relaxed">
        This tab works against a specific Lead. Start or track an instance of this
        workflow from the <span className="text-zinc-300">Overview</span> tab with a real
        Lead ID (LEAD-…) to see it here.
      </p>
    </div>
  );
}

export function LeadCadenceBoard({ leadId, section }: { leadId: string | null; section: LeadCadenceSection }) {
  const [record, setRecord] = useState<LeadRecord | null>(null);
  const [employees, setEmployees] = useState<SalesEmployeeBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [transferTo, setTransferTo] = useState("");
  const [noteCategory, setNoteCategory] = useState<NoteCategory>("general");
  const [noteBody, setNoteBody] = useState("");
  const [apptType, setApptType] = useState<AppointmentType>("showroom_visit");
  const [apptStart, setApptStart] = useState("");
  const [converted, setConverted] = useState<{ customerId: string; brief: CustomerBrief } | null>(null);
  const [showNewDeal, setShowNewDeal] = useState(false);

  function refresh() {
    if (!leadId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([getLeadRecord(leadId), getSalesEmployees()])
      .then(([r, emps]) => {
        setRecord(r);
        setEmployees(emps);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load this lead."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [leadId]);

  async function handleTransfer() {
    if (!leadId || !transferTo) return;
    setBusy(true);
    try {
      await transferLead(leadId, transferTo);
      setMessage("Lead transferred.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to transfer this lead.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddNote() {
    if (!leadId || !noteBody.trim()) return;
    setBusy(true);
    try {
      await addLeadNote(leadId, noteCategory, noteBody.trim());
      setNoteBody("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save this note.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSchedule() {
    if (!leadId || !apptStart) return;
    setBusy(true);
    try {
      await createAppointment({
        department: "Sales",
        appointment_type: apptType,
        scheduled_start: new Date(apptStart).toISOString(),
        lead_id: leadId,
      });
      setMessage("Appointment scheduled.");
      setApptStart("");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to schedule this appointment.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConvert() {
    if (!leadId || !record) return;
    setBusy(true);
    try {
      const result = await convertLeadToCustomer(leadId);
      const attrs = record.lead.attributes;
      const brief: CustomerBrief = {
        id: result.id,
        name: `${attrs.FirstName || ""} ${attrs.LastName || ""}`.trim() || result.id,
        email: (attrs.Email as string) || null,
        phone: (attrs.Phone as string) || null,
        credit_score: null,
      };
      setConverted({ customerId: result.id, brief });
      setMessage("Converted to Customer.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to convert this lead.");
    } finally {
      setBusy(false);
    }
  }

  if (!leadId) return <NoLead />;
  if (loading) return <div className="text-xs text-zinc-600">Loading…</div>;
  if (!record) return <div className="text-xs text-zinc-600">{error || "Lead not found."}</div>;

  const attrs = record.lead.attributes;
  const currentAssignee = employees.find((e) => e.id === attrs.AssignedSalesperson);

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}

      {section === "assignment" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Lead Assignment</div>
          <div className="text-xs text-zinc-300 mb-3">
            Currently assigned to: <span className="text-zinc-200">{currentAssignee ? currentAssignee.name : (attrs.AssignedSalesperson as string) || "unassigned"}</span>
          </div>
          <div className="flex flex-wrap gap-2 items-center">
            <WorkField label="Transfer to employee"><WorkSelect value={transferTo} onChange={(e) => setTransferTo(e.target.value)} className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200">
              <option value="">Select a rep…</option>
              {employees.map((e) => <option key={e.id} value={e.id}>{e.name}{e.title ? ` — ${e.title}` : ""}</option>)}
            </WorkSelect></WorkField>
            <WorkButton type="submit" onClick={handleTransfer} disabled={busy || !transferTo} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
              Transfer
            </WorkButton>
          </div>
        </div>
      )}

      {section === "timeline" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Communication Timeline</div>
          {record.timeline.length === 0 ? (
            <div className="text-xs text-zinc-600">Nothing logged yet.</div>
          ) : (
            <div className="space-y-1.5">
              <RecordCollection>{record.timeline.map((t, i) => (
                <div key={i} className="text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div className="text-zinc-200">{t.summary}</div>
                  <div className="text-zinc-500">{t.type} · {t.actor || "—"} · {fmt(t.timestamp)}</div>
                </div>
              ))}</RecordCollection>
            </div>
          )}
        </div>
      )}

      {section === "needs_analysis" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Needs Analysis</div>
          <div className="flex flex-wrap gap-2 mb-2">
            <WorkField label="Note Category"><WorkSelect value={noteCategory} onChange={(e) => setNoteCategory(e.target.value as NoteCategory)} className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200">
              {NOTE_CATEGORIES.map((c) => <option key={c} value={c}>{c.replace(/_/g, " ")}</option>)}
            </WorkSelect></WorkField>
            <WorkField label="What did you learn?"><WorkInput value={noteBody} onChange={(e) => setNoteBody(e.target.value)} placeholder="What did you learn?" className="flex-1 min-w-[160px] bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600" /></WorkField>
            <WorkButton type="submit" onClick={handleAddNote} disabled={busy || !noteBody.trim()} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
              Save Note
            </WorkButton>
          </div>
          <div className="space-y-1.5">
            {record.notes.length === 0 ? (
              <div className="text-xs text-zinc-600">No notes yet.</div>
            ) : (
              <RecordCollection label="Notes">{record.notes.map((n) => (
                <div key={n.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div className="text-zinc-200">{n.body}</div>
                  <div className="text-zinc-500">{n.category} · {fmt(n.created_at)}</div>
                </div>
              ))}</RecordCollection>
            )}
          </div>
        </div>
      )}

      {section === "appointments" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Appointment Scheduling</div>
          <div className="flex flex-wrap gap-2 items-center">
            <WorkField label="Appointment type"><WorkSelect value={apptType} onChange={(e) => setApptType(e.target.value as AppointmentType)} className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200">
              {APPT_TYPES.map((t) => <option key={t} value={t}>{t.replace(/_/g, " ")}</option>)}
            </WorkSelect></WorkField>
            <WorkField label="Appointment start"><WorkInput type="datetime-local" value={apptStart} onChange={(e) => setApptStart(e.target.value)} className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200" /></WorkField>
            <WorkButton type="submit" onClick={handleSchedule} disabled={busy || !apptStart} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
              Schedule
            </WorkButton>
          </div>
        </div>
      )}

      {section === "opportunity" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Opportunity Creation</div>
          {!converted ? (
            <WorkButton type="submit" onClick={handleConvert} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
              {busy ? "Converting…" : "Convert to Customer"}
            </WorkButton>
          ) : (
            <>
              <div className="text-xs text-emerald-400 mb-2">
                Converted -- {converted.brief.name} is now {converted.customerId}.
              </div>
              <WorkButton type="submit" variant="primary" onClick={() => setShowNewDeal(true)} className="text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium">
                + Create Deal
              </WorkButton>
            </>
          )}
        </div>
      )}

      {showNewDeal && converted && (
        <NewDealModal
          theme="dark"
          initialCustomer={converted.brief}
          onClose={() => setShowNewDeal(false)}
          onCreated={() => {
            setShowNewDeal(false);
            setMessage("Deal created.");
          }}
        />
      )}
    </div>
  );
}
