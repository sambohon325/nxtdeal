"use client";
import { WorkButton, WorkSelect } from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";
import {PublishedWebsiteOffers} from "./PublishedWebsiteOffers";

// BDC / Internet Leads (session 100 follow-up) -- rendered inside Sales' "BDC
// (Internet Leads)" workflow modal (core/workflow_catalog.py's sales.bdc). Real
// speed-to-lead: an urgency-ranked untouched queue plus a real response-time
// scorecard measured off actual timestamps, not a fabricated estimate (see
// core/bdc.py's precise_timestamp caveat -- historical leads without a full
// timestamp are honestly excluded from urgency ranking rather than guessed at).
// "Log Contact" opens Prospects' real LeadRecordModal so first-contact logging goes
// through the exact same Communication Hub every other lead record uses.
//
// Session 102 follow-up (Sam: "it needs to be a working process, not just a list")
// -- split into a `section` prop matching BDC's 5 named tabs instead of rendering
// the whole board identically everywhere. Qualification and Handoff to Floor are new
// real stages built on core/bdc.py's get_qualification_queue()/get_handoff_candidates()
// -- the actual BDC-to-floor transfer reuses core/lead_assignment.py's real
// transfer_lead() (session 94's transferLead), not a parallel handoff mechanism.
import { useEffect, useState } from "react";
import {
  getBdcDashboard,
  getQualificationQueue,
  getHandoffCandidates,
  type BdcDashboard,
  type BdcLeadBrief,
} from "@/lib/bdc";
import { transferLead, getSalesEmployees, type SalesEmployeeBrief } from "@/lib/salesOverview";
import { LeadRecordModal } from "@/components/ProspectsBoard";

export type BdcSection = "queue" | "scorecard" | "first_contact" | "qualification" | "handoff";

const URGENCY_TONE: Record<string, string> = {
  critical: "border-red-900 bg-red-950/30 text-red-300",
  warning: "border-amber-900 bg-amber-950/30 text-amber-300",
  ok: "border-zinc-800 bg-zinc-900/40 text-zinc-400",
  unknown: "border-zinc-800 bg-zinc-900/20 text-zinc-600",
};

function LeadCard({ l, onOpen }: { l: BdcLeadBrief; onOpen: () => void }) {
  return (
    <button
      onClick={onOpen}
      className={`w-full text-left rounded-lg border p-2 flex items-center justify-between gap-2 ${URGENCY_TONE[l.urgency]}`}
    >
      <div className="min-w-0">
        <div className="text-xs font-medium truncate">
          {l.first_name} {l.last_name} · {l.source}
        </div>
        <div className="text-xs opacity-80">
          {l.precise_timestamp && l.minutes_since_created !== null
            ? `${l.minutes_since_created}m since submitted`
            : `${l.created_date || "—"} (no precise timestamp)`}
        </div>
      </div>
      <span className="text-xs uppercase shrink-0">{l.urgency}</span>
    </button>
  );
}

export function BdcBoard({ section = "queue" }: { section?: BdcSection }) {
  const [data, setData] = useState<BdcDashboard | null>(null);
  const [qualification, setQualification] = useState<BdcLeadBrief[]>([]);
  const [handoff, setHandoff] = useState<BdcLeadBrief[]>([]);
  const [employees, setEmployees] = useState<SalesEmployeeBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [openLeadId, setOpenLeadId] = useState<string | null>(null);
  const [transferFor, setTransferFor] = useState<string | null>(null);
  const [transferTo, setTransferTo] = useState("");
  const [transferred, setTransferred] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    Promise.all([getBdcDashboard(), getQualificationQueue(), getHandoffCandidates(), getSalesEmployees()])
      .then(([d, q, h, emps]) => {
        setData(d);
        setQualification(q.leads);
        setHandoff(h.leads);
        setEmployees(emps);
        setError(null);
      })
      .catch(() => setError("Unable to load the BDC queue."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleTransfer(leadId: string) {
    if (!transferTo) return;
    try {
      await transferLead(leadId, transferTo);
      setTransferFor(null);
      setTransferred(leadId);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to transfer this lead.");
    }
  }

  if (loading) {
    return <div className="mb-5 text-xs text-zinc-600">Loading…</div>;
  }

  if (!data) {
    return <div className="mb-5 text-sm"><p role="alert">Unable to load the BDC queue.</p><WorkButton type="submit" onClick={refresh}>Retry BDC queue</WorkButton></div>;
  }

  const mostUrgent = data.untouched_queue.leads[0];

  return (
    <div className="mb-5">
      <PublishedWebsiteOffers/>
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}

      {section === "queue" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Untouched Queue ({data.untouched_queue.count})</div>
          {data.untouched_queue.leads.length === 0 ? (
            <div className="text-xs text-zinc-600">Nothing untouched right now.</div>
          ) : (
            <div className="space-y-1.5">
              <RecordCollection>{data.untouched_queue.leads.map((l) => (
                <LeadCard key={l.id} l={l} onOpen={() => setOpenLeadId(l.id)} />
              ))}</RecordCollection>
            </div>
          )}
          {Object.keys(data.not_yet_tracked).length > 0 && (
            <div className="text-xs text-zinc-600 mt-2 space-y-0.5">
              {Object.entries(data.not_yet_tracked).map(([k, v]) => (
                <div key={k}>• {k === "chat_transcripts" ? "Website chat requests need a reviewed handoff before they enter this queue." : k === "outbound_dialer_integration" ? "A dialer is not connected. Record call outcomes in the customer history." : v}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {section === "scorecard" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Response-Time Scorecard</div>
          <div className="grid grid-cols-3 gap-2">
            <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">
                {data.response_time.average_minutes !== null ? `${data.response_time.average_minutes}m` : "—"}
              </div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Avg Response (n={data.response_time.sample_size})</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">
                {data.response_time.under_target_pct !== null ? `${data.response_time.under_target_pct}%` : "—"}
              </div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Under {data.sla_thresholds.urgent_minutes}m</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{data.untouched_queue.count}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Currently Untouched</div>
            </div>
          </div>
          <div className="text-xs text-zinc-600 mt-2">
            SLA: contact within {data.sla_thresholds.urgent_minutes}m is on target, {data.sla_thresholds.warning_minutes}m+ is critical.
          </div>
        </div>
      )}

      {section === "first_contact" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Work the Next One</div>
          {!mostUrgent ? (
            <div className="text-xs text-zinc-600">Nothing waiting on first contact right now.</div>
          ) : (
            <>
              <div className={`rounded-lg border p-3 mb-2 ${URGENCY_TONE[mostUrgent.urgency]}`}>
                <div className="text-sm font-medium mb-1">{mostUrgent.first_name} {mostUrgent.last_name}</div>
                <div className="text-xs opacity-80 mb-2">
                  {mostUrgent.source} ·{" "}
                  {mostUrgent.precise_timestamp && mostUrgent.minutes_since_created !== null
                    ? `${mostUrgent.minutes_since_created}m since submitted`
                    : `${mostUrgent.created_date || "—"} (no precise timestamp)`}
                </div>
                <WorkButton type="submit"
                  onClick={() => setOpenLeadId(mostUrgent.id)}
                  className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium"
                >
                  Log First Contact
                </WorkButton>
              </div>
              <div className="text-xs text-zinc-500 mb-1">Up next after this one:</div>
              <div className="space-y-1.5">
                {data.untouched_queue.leads.slice(1, 6).map((l) => (
                  <LeadCard key={l.id} l={l} onOpen={() => setOpenLeadId(l.id)} />
                ))}
              </div>
            </>
          )}
        </div>
      )}

      {section === "qualification" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Qualification ({qualification.length})</div>
          <p className="text-xs text-zinc-600 mb-2">
            Contacted at least once but no appointment yet -- confirm interest, budget, and timeline before handing off.
          </p>
          {qualification.length === 0 ? (
            <div className="text-xs text-zinc-600">Nothing waiting on qualification right now.</div>
          ) : (
            <div className="space-y-1.5">
              <RecordCollection>{qualification.map((l) => (
                <LeadCard key={l.id} l={l} onOpen={() => setOpenLeadId(l.id)} />
              ))}</RecordCollection>
            </div>
          )}
        </div>
      )}

      {section === "handoff" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Handoff to Floor ({handoff.length})</div>
          <p className="text-xs text-zinc-600 mb-2">
            Appointment set or already visited -- ready to move off BDC to a floor salesperson.
          </p>
          {handoff.length === 0 ? (
            <div className="text-xs text-zinc-600">Nothing ready to hand off right now.</div>
          ) : (
            <div className="space-y-1.5">
              <RecordCollection>{handoff.map((l) => (
                <div key={l.id} className="rounded-lg border border-zinc-800 p-2">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-xs font-medium text-zinc-200 truncate">{l.first_name} {l.last_name} · {l.source}</div>
                      <div className="text-xs text-zinc-500">{l.pipeline_state}</div>
                    </div>
                    <WorkButton type="submit"
                      onClick={() => setTransferFor(transferFor === l.id ? null : l.id)}
                      className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-300 shrink-0"
                    >
                      Transfer to Floor
                    </WorkButton>
                  </div>
                  {transferFor === l.id && (
                    <div className="flex items-center gap-1.5 mt-1.5 pt-1.5 border-t border-zinc-800">
                      <WorkField label="Transfer to employee"><WorkSelect
                        value={transferTo}
                        onChange={(e) => setTransferTo(e.target.value)}
                        className="text-xs rounded border border-zinc-700 bg-black px-1.5 py-1 text-white flex-1"
                      >
                        <option value="">Select a floor rep…</option>
                        {employees.map((e) => (
                          <option key={e.id} value={e.id}>{e.name}{e.title ? ` — ${e.title}` : ""}</option>
                        ))}
                      </WorkSelect></WorkField>
                      <WorkButton type="submit" variant="primary"
                        onClick={() => handleTransfer(l.id)}
                        disabled={!transferTo}
                        className="text-xs px-2 py-1 rounded bg-brand-blue text-white font-medium disabled:opacity-50"
                      >
                        Confirm
                      </WorkButton>
                    </div>
                  )}
                  {transferred === l.id && (
                    <div className="text-xs text-emerald-400 mt-1">Transferred to the floor.</div>
                  )}
                </div>
              ))}</RecordCollection>
            </div>
          )}
        </div>
      )}

      {openLeadId && (
        <LeadRecordModal theme="dark" leadId={openLeadId} onClose={() => setOpenLeadId(null)} onChanged={refresh} />
      )}
    </div>
  );
}
