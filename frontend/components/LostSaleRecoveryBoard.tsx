"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Lost Sale Recovery (session 105 follow-up) -- rendered inside Sales' "Lost Sale
// Recovery" workflow modal (core/workflow_catalog.py's sales.lost_sale_recovery). The
// eighth of Sam's ~10 "completely missing" dealership workflows; follows the same
// bespoke per-tab-section pattern session 100-105 established (Up System/BDC/Demo
// Drive/Credit App/eSignature/F&I Workflow) -- a `section` prop matching this
// workflow's 5 real tabs (Recovery Queue, Lost Reason Capture, Outreach Log,
// Reactivation, Win-Back Lists & Stats).
//
// Unifies two real signals: Lead.PipelineState == "LOST" and Deal.status ==
// "cancelled". Reactivating a lead is a deliberate bypass of the strict
// LEAD_WORKFLOW state machine (LOST has no valid outgoing transition) -- see
// core/lost_sale_recovery.py's module docstring.
import { useEffect, useState } from "react";
import {
  getLostSaleRecoveryDashboard,
  markLeadLost,
  reactivateLostLead,
  recordDealLostReason,
  logRecoveryAttempt,
  listRecoveryAttempts,
  saveRecoveryPoolAsList,
  type LostSaleRecoveryDashboard,
  type LostLead,
  type CancelledDeal,
  type RecoveryAttempt,
} from "@/lib/lostSaleRecovery";

export type LostSaleRecoverySection = "queue" | "reason_capture" | "outreach" | "reactivation" | "winback";

function REASON_LABEL(code: string): string {
  return code
    .split("_")
    .map((w) => w[0].toUpperCase() + w.slice(1))
    .join(" ");
}

type SelectedEntity = { id: string; type: "Lead" | "Deal"; label: string } | null;

function LeadRow({ lead, onSelect, selected }: { lead: LostLead; onSelect: () => void; selected: boolean }) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left text-xs px-2 py-1.5 rounded border ${
        selected ? "border-zinc-500 bg-zinc-800" : "border-zinc-800"
      } text-zinc-300`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-zinc-200">{lead.name}</span>
        <span className="text-zinc-600">{lead.id}</span>
      </div>
      <div className="text-xs text-zinc-500">
        {lead.source || "Unknown source"}
        {lead.lost_reason ? ` · ${REASON_LABEL(lead.lost_reason)}` : " · no reason recorded"}
        {lead.previous_lost_reasons.length > 0 && ` · reactivated ${lead.previous_lost_reasons.length}x before`}
      </div>
    </button>
  );
}

function DealRow({ deal, onSelect, selected }: { deal: CancelledDeal; onSelect: () => void; selected: boolean }) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left text-xs px-2 py-1.5 rounded border ${
        selected ? "border-zinc-500 bg-zinc-800" : "border-zinc-800"
      } text-zinc-300`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-zinc-200">{deal.customer?.name || deal.id}</span>
        <span className="text-zinc-600">{deal.id}</span>
      </div>
      <div className="text-xs text-zinc-500">
        {deal.vehicle?.description || "No vehicle"}
        {deal.cancel_reason ? ` · ${REASON_LABEL(deal.cancel_reason)}` : " · no reason recorded"}
      </div>
    </button>
  );
}

export function LostSaleRecoveryBoard({ section = "queue" }: { section?: LostSaleRecoverySection }) {
  const [dashboard, setDashboard] = useState<LostSaleRecoveryDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [queueTab, setQueueTab] = useState<"leads" | "deals">("leads");
  const [selected, setSelected] = useState<SelectedEntity>(null);

  const [reasonInput, setReasonInput] = useState<string>("");
  const [leadIdInput, setLeadIdInput] = useState("");

  const [attempts, setAttempts] = useState<RecoveryAttempt[]>([]);
  const [noteInput, setNoteInput] = useState("");
  const [reactivateNote, setReactivateNote] = useState("");

  const [listName, setListName] = useState("Win-Back List");
  const [listSource, setListSource] = useState<"lost_leads" | "cancelled_deals">("lost_leads");

  function refresh() {
    setLoading(true);
    getLostSaleRecoveryDashboard()
      .then((d) => {
        setDashboard(d);
        setError(null);
        if (d.reason_codes.length > 0 && !reasonInput) setReasonInput(d.reason_codes[0]);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Lost Sale Recovery data."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  useEffect(() => {
    if (section === "outreach" && selected) {
      listRecoveryAttempts(selected.id)
        .then(setAttempts)
        .catch(() => setAttempts([]));
    }
  }, [section, selected]);

  function selectLead(lead: LostLead) {
    setSelected({ id: lead.id, type: "Lead", label: lead.name });
  }

  function selectDeal(deal: CancelledDeal) {
    setSelected({ id: deal.id, type: "Deal", label: deal.customer?.name || deal.id });
  }

  async function handleMarkLost() {
    if (!leadIdInput.trim() || !reasonInput) return;
    setBusy(true);
    try {
      const lead = await markLeadLost(leadIdInput.trim(), reasonInput);
      setMessage(`Marked ${lead.id} as lost (${REASON_LABEL(reasonInput)}).`);
      setLeadIdInput("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to mark this lead lost.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRecordDealReason() {
    if (!selected || selected.type !== "Deal" || !reasonInput) return;
    setBusy(true);
    try {
      await recordDealLostReason(selected.id, reasonInput);
      setMessage(`Recorded lost-sale reason on ${selected.id}.`);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to record this deal's lost reason.");
    } finally {
      setBusy(false);
    }
  }

  async function handleLogAttempt() {
    if (!selected || !noteInput.trim()) return;
    setBusy(true);
    try {
      await logRecoveryAttempt(selected.id, selected.type, noteInput.trim());
      setNoteInput("");
      const updated = await listRecoveryAttempts(selected.id);
      setAttempts(updated);
      setMessage("Logged recovery attempt.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to log this recovery attempt.");
    } finally {
      setBusy(false);
    }
  }

  async function handleReactivate(leadId: string) {
    setBusy(true);
    try {
      const lead = await reactivateLostLead(leadId, reactivateNote.trim() || undefined);
      setMessage(`Reactivated ${lead.id} -- back in the pipeline at CONTACTED.`);
      setReactivateNote("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to reactivate this lead.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSaveAsList() {
    if (!listName.trim()) return;
    setBusy(true);
    try {
      const result = await saveRecoveryPoolAsList(listName.trim(), listSource);
      setMessage(`Saved "${listName}" -- ${result.added} of ${result.requested} added to Marketing List ${result.list_id}.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save this pool as a list.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="mb-5 text-xs text-zinc-600">Loading…</div>;
  }

  const stats = dashboard?.stats;

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}

      {section === "queue" && (
        <>
          <div className="grid grid-cols-4 gap-2 mb-3">
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{stats?.total_lost_leads ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Lost Leads</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{stats?.total_cancelled_deals ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Cancelled Deals</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-emerald-300">
                {stats?.recovery_rate_pct !== null && stats?.recovery_rate_pct !== undefined ? `${stats.recovery_rate_pct}%` : "—"}
              </div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Recovery Rate</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{stats?.leads_reactivated ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Leads Reactivated</div>
            </div>
          </div>

          <div className="flex gap-1.5 mb-2">
            <WorkButton aria-pressed={queueTab === "leads"} type="submit"
              onClick={() => setQueueTab("leads")}
              className={`text-xs px-2.5 py-1 rounded ${queueTab === "leads" ? "bg-zinc-200 text-black font-medium" : "bg-zinc-900 text-zinc-400 border border-zinc-800"}`}
            >
              Lost Leads ({dashboard?.lost_leads.length ?? 0})
            </WorkButton>
            <WorkButton aria-pressed={queueTab === "deals"} type="submit"
              onClick={() => setQueueTab("deals")}
              className={`text-xs px-2.5 py-1 rounded ${queueTab === "deals" ? "bg-zinc-200 text-black font-medium" : "bg-zinc-900 text-zinc-400 border border-zinc-800"}`}
            >
              Cancelled Deals ({dashboard?.cancelled_deals.length ?? 0})
            </WorkButton>
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            {queueTab === "leads" ? (
              (dashboard?.lost_leads.length ?? 0) === 0 ? (
                <div className="text-xs text-zinc-600">No lost leads on file.</div>
              ) : (
                <div className="space-y-1.5">
                  {dashboard!.lost_leads.map((l) => (
                    <LeadRow key={l.id} lead={l} onSelect={() => selectLead(l)} selected={selected?.id === l.id} />
                  ))}
                </div>
              )
            ) : (dashboard?.cancelled_deals.length ?? 0) === 0 ? (
              <div className="text-xs text-zinc-600">No cancelled deals on file.</div>
            ) : (
              <div className="space-y-1.5">
                {dashboard!.cancelled_deals.map((d) => (
                  <DealRow key={d.id} deal={d} onSelect={() => selectDeal(d)} selected={selected?.id === d.id} />
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {section === "reason_capture" && (
        <div className="space-y-3">
          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Mark a Lead Lost</div>
            <div className="flex flex-wrap items-center gap-2">
              <WorkField label="Lead ID (LEAD-…)"><WorkInput
                value={leadIdInput}
                onChange={(e) => setLeadIdInput(e.target.value)}
                placeholder="Lead ID (LEAD-…)"
                className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
              /></WorkField>
              <WorkField label="Reason Input"><WorkSelect
                value={reasonInput}
                onChange={(e) => setReasonInput(e.target.value)}
                className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200"
              >
                {(dashboard?.reason_codes ?? []).map((r) => (
                  <option key={r} value={r}>
                    {REASON_LABEL(r)}
                  </option>
                ))}
              </WorkSelect></WorkField>
              <WorkButton type="submit"
                onClick={handleMarkLost}
                disabled={busy || !leadIdInput.trim()}
                className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
              >
                Mark Lost
              </WorkButton>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Record a Cancelled Deal's Reason</div>
            {!selected || selected.type !== "Deal" ? (
              <div className="text-xs text-zinc-600">Select a cancelled deal from the Recovery Queue tab first.</div>
            ) : (
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-xs text-zinc-300">{selected.label} ({selected.id})</span>
                <WorkField label="Reason Input"><WorkSelect
                  value={reasonInput}
                  onChange={(e) => setReasonInput(e.target.value)}
                  className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200"
                >
                  {(dashboard?.reason_codes ?? []).map((r) => (
                    <option key={r} value={r}>
                      {REASON_LABEL(r)}
                    </option>
                  ))}
                </WorkSelect></WorkField>
                <WorkButton type="submit"
                  onClick={handleRecordDealReason}
                  disabled={busy}
                  className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
                >
                  Record Reason
                </WorkButton>
              </div>
            )}
          </div>
        </div>
      )}

      {section === "outreach" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Outreach Log</div>
          {!selected ? (
            <div className="text-xs text-zinc-600">Select a lost lead or cancelled deal from the Recovery Queue tab first.</div>
          ) : (
            <>
              <div className="text-xs text-zinc-300 mb-2">
                {selected.label} ({selected.id})
              </div>
              <div className="flex items-center gap-2 mb-3">
                <WorkField label="Log an outreach attempt (call, text, email…)"><WorkInput
                  value={noteInput}
                  onChange={(e) => setNoteInput(e.target.value)}
                  placeholder="Log an outreach attempt (call, text, email…)"
                  className="flex-1 bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
                /></WorkField>
                <WorkButton type="submit"
                  onClick={handleLogAttempt}
                  disabled={busy || !noteInput.trim()}
                  className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
                >
                  Log
                </WorkButton>
              </div>
              {attempts.length === 0 ? (
                <div className="text-xs text-zinc-600">No recovery attempts logged yet.</div>
              ) : (
                <div className="space-y-1.5">
                  {attempts.map((a) => (
                    <div key={a.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800 text-zinc-300">
                      <div>{a.body}</div>
                      <div className="text-xs text-zinc-600">
                        {a.created_by} · {new Date(a.created_at).toLocaleString()}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {section === "reactivation" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Reactivation</div>
          <p className="text-xs text-zinc-600 mb-2">
            Reactivating moves a lead directly back to CONTACTED -- LOST has no normal outgoing transition in the
            pipeline, so this is a deliberate override, fully visible in the lead's history and the audit log.
          </p>
          <WorkField label="Reactivate Note"><WorkInput
            value={reactivateNote}
            onChange={(e) => setReactivateNote(e.target.value)}
            placeholder="Optional note about why this lead is coming back (logged as a recovery attempt)"
            className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 mb-2"
          /></WorkField>
          {(dashboard?.lost_leads.length ?? 0) === 0 ? (
            <div className="text-xs text-zinc-600">No lost leads to reactivate.</div>
          ) : (
            <div className="space-y-1.5">
              {dashboard!.lost_leads.map((l) => (
                <div key={l.id} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div>
                    <span className="text-zinc-200">{l.name}</span>{" "}
                    <span className="text-zinc-600">
                      {l.id} · {l.lost_reason ? REASON_LABEL(l.lost_reason) : "no reason recorded"}
                    </span>
                  </div>
                  <WorkButton type="submit"
                    onClick={() => handleReactivate(l.id)}
                    disabled={busy}
                    className="bg-emerald-900/50 border border-emerald-800 text-emerald-200 rounded px-2.5 py-1 text-xs disabled:opacity-40"
                  >
                    Reactivate
                  </WorkButton>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {section === "winback" && (
        <div className="space-y-3">
          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Save as a Win-Back List</div>
            <p className="text-xs text-zinc-600 mb-2">
              Saves the full current pool (not just what's on screen) as a real, campaign-targetable Marketing List --
              the same List engine the CRM's Lists/Opportunities tabs already use.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <WorkField label="List Name"><WorkInput
                value={listName}
                onChange={(e) => setListName(e.target.value)}
                className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200"
              /></WorkField>
              <WorkField label="List Source"><WorkSelect
                value={listSource}
                onChange={(e) => setListSource(e.target.value as "lost_leads" | "cancelled_deals")}
                className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200"
              >
                <option value="lost_leads">Lost Leads ({stats?.total_lost_leads ?? 0})</option>
                <option value="cancelled_deals">Cancelled Deals' Customers ({stats?.total_cancelled_deals ?? 0})</option>
              </WorkSelect></WorkField>
              <WorkButton type="submit"
                onClick={handleSaveAsList}
                disabled={busy || !listName.trim()}
                className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
              >
                Save as List
              </WorkButton>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Lost Reason Breakdown</div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">Leads</div>
                {Object.entries(stats?.lost_lead_reasons ?? {}).length === 0 ? (
                  <div className="text-xs text-zinc-600">No data.</div>
                ) : (
                  Object.entries(stats!.lost_lead_reasons).map(([reason, count]) => (
                    <div key={reason} className="flex items-center justify-between text-xs text-zinc-300 mb-1">
                      <span>{REASON_LABEL(reason)}</span>
                      <span className="text-zinc-500">{count}</span>
                    </div>
                  ))
                )}
              </div>
              <div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">Deals</div>
                {Object.entries(stats?.cancelled_deal_reasons ?? {}).length === 0 ? (
                  <div className="text-xs text-zinc-600">No data.</div>
                ) : (
                  Object.entries(stats!.cancelled_deal_reasons).map(([reason, count]) => (
                    <div key={reason} className="flex items-center justify-between text-xs text-zinc-300 mb-1">
                      <span>{REASON_LABEL(reason)}</span>
                      <span className="text-zinc-500">{count}</span>
                    </div>
                  ))
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
