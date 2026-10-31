"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Finance's "Collections" item -- the third slice of Sam's "Retail Automotive
// Lending Platform" expansion (2026-07-17), right after Portfolio and Payments.
// A real bucketed (3/7/15/30/60-day) delinquency work queue, a real Collection
// Agent Workspace per loan (risk score, priority recommendation, collection-stage
// path, contact logging), all built on top of core/loan_servicing.py's own
// delinquency computation -- real once real Payments exist for a loan, simulated
// otherwise, carried through honestly via each response's own `basis` field.
// "AI Collection Prioritization" is a real, transparent rules engine, not a
// machine-learning model or LLM call.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { CommsQuickActions } from "@/components/CommsQuickActions";
import {
  getCollectionsDashboard,
  getCollectionQueue,
  getAgentWorkspace,
  advanceCollectionStage,
  logContact,
  COLLECTION_STAGES,
  STAGE_LABELS,
  BUCKET_LABELS,
  QUEUE_BUCKETS,
  CONTACT_CHANNELS,
  type CollectionsDashboard,
  type QueueRow,
  type QueueBucket,
  type CollectionStage,
  type ContactChannel,
  type AgentWorkspace,
} from "@/lib/collections";
import { LoanDetailModal } from "@/components/PortfolioBoard";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function priorityBadge(priority: string | null): string {
  if (priority === "recovery_risk") return "bg-red-950/40 text-red-300";
  if (priority === "high_probability_to_pay") return "bg-green-950/40 text-green-300";
  return "bg-zinc-800 text-zinc-400";
}

export function CollectionsBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<CollectionsDashboard | null>(null);
  const [queue, setQueue] = useState<QueueRow[]>([]);
  const [bucketFilter, setBucketFilter] = useState<QueueBucket | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [fullLoanId, setFullLoanId] = useState<string | null>(null);
  const [lookupId, setLookupId] = useState("");

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function refresh() {
    setLoading(true);
    Promise.all([getCollectionsDashboard(), getCollectionQueue(bucketFilter || undefined)])
      .then(([d, q]) => {
        setDashboard(d);
        setQueue(q.loans);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [bucketFilter]);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total In Queue" value={String(dashboard?.total_in_queue ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Recovery Risk" value={String(dashboard?.recovery_risk_count ?? 0)} color={RIBBON[3]} />
        <Kpi theme={theme} label="High Probability To Pay" value={String(dashboard?.contact_today_count ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="60+ Day Bucket" value={String(dashboard?.bucket_counts?.["60_day"] ?? 0)} color={RIBBON[2]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800">
        <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
          Risk score + priority recommendation are a real, transparent rules engine (days past due + broken promises + payment consistency) -- not machine learning or an LLM call. Delinquency data is real once real Payments exist for a loan, simulated otherwise -- each row's basis is carried through honestly.
        </span>
      </div>

      <div className="px-4 py-3 border-b border-zinc-800 flex items-center gap-2 flex-wrap">
        <span className="text-xs text-zinc-500 uppercase tracking-wide font-brand">Bucket:</span>
        <WorkButton type="submit"
          onClick={() => setBucketFilter(null)}
          className={`text-xs px-2 py-1 rounded ${bucketFilter === null ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-400"}`}
        >
          All
        </WorkButton>
        {QUEUE_BUCKETS.map((b) => (
          <WorkButton type="submit"
            key={b}
            onClick={() => setBucketFilter(bucketFilter === b ? null : b)}
            className={`text-xs px-2 py-1 rounded ${bucketFilter === b ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-400"}`}
          >
            {BUCKET_LABELS[b]} ({dashboard?.bucket_counts?.[b] ?? 0})
          </WorkButton>
        ))}
        <div className="flex-1" />
        <WorkField label="Record ID"><WorkInput
          value={lookupId}
          onChange={(e) => setLookupId(e.target.value)}
          placeholder="Loan id (e.g. FIN-00001)…"
          className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}
        /></WorkField>
        <WorkButton type="submit" variant="primary"
          disabled={!lookupId}
          onClick={() => setSelected(lookupId.trim().toUpperCase())}
          className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
        >
          Open Workspace
        </WorkButton>
      </div>

      <div className="flex-1 p-4 overflow-y-auto">
        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
            Work Queue {bucketFilter ? `— ${BUCKET_LABELS[bucketFilter]}` : ""} (worst first)
          </div>
          {loading ? (
            <div className="text-xs text-zinc-500">Loading…</div>
          ) : queue.length === 0 ? (
            <div className="text-xs text-zinc-500">No loans in this bucket.</div>
          ) : (
            <div className="space-y-1 max-h-[28rem] overflow-y-auto">
              {queue.map((row) => (
                <WorkButton type="submit"
                  key={row.loan_id}
                  onClick={() => setSelected(row.loan_id)}
                  className="w-full text-left flex items-center justify-between text-xs hover:text-brand-blue transition py-1 border-b border-zinc-800/50"
                >
                  <span className="flex items-center gap-2">
                    <span className="font-medium">{row.loan_id}</span>
                    <span className="text-zinc-500">{row.customer_name || "—"}</span>
                    <span className="text-zinc-600">{row.days_past_due}d past due · {money(row.amount_past_due)}</span>
                  </span>
                  <span className="flex items-center gap-2">
                    <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">{STAGE_LABELS[row.collection_stage]}</span>
                    <span className={`text-xs px-1.5 py-0.5 rounded ${priorityBadge(row.priority)}`}>{row.priority_label || "—"}</span>
                  </span>
                </WorkButton>
              ))}
            </div>
          )}
        </div>
      </div>

      {selected && (
        <AgentWorkspaceModal
          theme={theme}
          loanId={selected}
          onClose={() => setSelected(null)}
          onChanged={refresh}
          onViewFullLoan={(id) => setFullLoanId(id)}
        />
      )}

      {fullLoanId && (
        <LoanDetailModal theme={theme} loanId={fullLoanId} onClose={() => setFullLoanId(null)} onChanged={refresh} />
      )}
    </div>
  );
}

function AgentWorkspaceModal({
  theme,
  loanId,
  onClose,
  onChanged,
  onViewFullLoan,
}: {
  theme: Theme;
  loanId: string;
  onClose: () => void;
  onChanged: () => void;
  onViewFullLoan: (id: string) => void;
}) {
  const [workspace, setWorkspace] = useState<AgentWorkspace | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [stageBusy, setStageBusy] = useState(false);
  const [stageReason, setStageReason] = useState("");
  const [contactChannel, setContactChannel] = useState<ContactChannel>("call");
  const [contactNotes, setContactNotes] = useState("");
  const [contactBusy, setContactBusy] = useState(false);

  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function load() {
    setLoading(true);
    setError(null);
    getAgentWorkspace(loanId)
      .then(setWorkspace)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [loanId]);

  async function handleAdvanceStage(stage: CollectionStage) {
    setStageBusy(true);
    try {
      await advanceCollectionStage(loanId, stage, stageReason);
      setStageReason("");
      load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStageBusy(false);
    }
  }

  async function handleLogContact() {
    if (!contactNotes.trim()) return;
    setContactBusy(true);
    try {
      await logContact(loanId, contactChannel, contactNotes);
      setContactNotes("");
      load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setContactBusy(false);
    }
  }

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className={tc(theme, "w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-800 bg-brand-ink text-white p-5", "w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-200 bg-white text-black p-5")}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-sm font-semibold">Collection Agent Workspace — {loanId}</div>
            {workspace && <div className="text-xs text-zinc-500">{workspace.finance_number}</div>}
          </div>
          <div className="flex items-center gap-2">
            <WorkButton type="submit" onClick={() => onViewFullLoan(loanId)} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">
              View Full Loan →
            </WorkButton>
            <WorkButton type="submit" onClick={onClose} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">
              Close
            </WorkButton>
          </div>
        </div>

        {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
        {loading ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : !workspace ? (
          <div className="text-xs text-zinc-500">Unable to load workspace.</div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Risk Score</div>
                <div className="text-2xl font-semibold">{workspace.risk_score.score} <span className="text-xs text-zinc-500">/ 100</span></div>
                <div className="text-xs text-zinc-500 mt-1">{workspace.risk_score.tier} tier · basis: {workspace.risk_score.basis}</div>
              </div>
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Priority Recommendation</div>
                <div className={`inline-block text-xs px-2 py-1 rounded ${priorityBadge(workspace.priority_recommendation.recommendation)}`}>
                  {workspace.priority_recommendation.label}
                </div>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Customer</div>
                <div className="text-xs">{(workspace.customer?.name as string) || "—"}</div>
                <div className="text-xs text-zinc-500">{(workspace.customer?.phone as string) || ""} {(workspace.customer?.email as string) || ""}</div>
                {(workspace.customer?.phone as string) && (
                  <div className="mt-1.5">
                    <CommsQuickActions
                      customerId={(workspace.customer?.id as string) || undefined}
                      phone={workspace.customer?.phone as string}
                      name={workspace.customer?.name as string}
                      size="xs"
                    />
                  </div>
                )}
              </div>
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Vehicle</div>
                <div className="text-xs">{workspace.vehicle ? [workspace.vehicle.year, workspace.vehicle.make, workspace.vehicle.model].filter(Boolean).join(" ") || "Vehicle details unavailable" : "No vehicle linked"}</div>
              </div>
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Employment</div>
              {workspace.employment?.on_file ? (
                <div className="text-xs">
                  {workspace.employment.employer_name} · {money(workspace.employment.monthly_income)}/mo · {workspace.employment.employment_status}
                </div>
              ) : (
                <div className="text-xs text-zinc-500">{workspace.employment?.note}</div>
              )}
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Collection Path</div>
              <div className="flex items-center gap-1 mb-2 flex-wrap">
                {COLLECTION_STAGES.map((s, i) => (
                  <span key={s} className="flex items-center gap-1">
                    <span className={`text-xs px-2 py-1 rounded ${workspace.collection_stage === s ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-400"}`}>
                      {STAGE_LABELS[s]}
                    </span>
                    {i < COLLECTION_STAGES.length - 1 && <span className="text-zinc-600">→</span>}
                  </span>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <WorkField label="Reason (optional)"><WorkInput
                  value={stageReason}
                  onChange={(e) => setStageReason(e.target.value)}
                  placeholder="Reason (optional)…"
                  className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`}
                /></WorkField>
                <WorkField label="Advance to"><WorkSelect
                  disabled={stageBusy}
                  onChange={(e) => e.target.value && handleAdvanceStage(e.target.value as CollectionStage)}
                  value=""
                  className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}
                >
                  <option value="">Advance to…</option>
                  {COLLECTION_STAGES.map((s) => (
                    <option key={s} value={s}>{STAGE_LABELS[s]}</option>
                  ))}
                </WorkSelect></WorkField>
              </div>
              {workspace.collection_stage_history.length > 0 && (
                <div className="mt-2 space-y-0.5 max-h-24 overflow-y-auto">
                  {workspace.collection_stage_history.slice().reverse().map((h, i) => (
                    <div key={i} className="text-xs text-zinc-500">
                      {STAGE_LABELS[h.stage]} · {h.by} · {h.reason || "no reason given"} · {h.at.slice(0, 16).replace("T", " ")}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Log Contact</div>
              <div className="flex items-center gap-2 mb-2">
                {CONTACT_CHANNELS.map((c) => (
                  <WorkButton type="submit"
                    key={c}
                    onClick={() => setContactChannel(c)}
                    className={`text-xs px-2 py-1 rounded capitalize ${contactChannel === c ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-400"}`}
                  >
                    {c}
                  </WorkButton>
                ))}
              </div>
              <div className="flex items-center gap-2">
                <WorkField label="Notes"><WorkInput
                  value={contactNotes}
                  onChange={(e) => setContactNotes(e.target.value)}
                  placeholder="Notes…"
                  className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`}
                /></WorkField>
                <WorkButton type="submit" variant="primary"
                  disabled={contactBusy || !contactNotes.trim()}
                  onClick={handleLogContact}
                  className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                >
                  Log
                </WorkButton>
              </div>
              <div className="mt-2 space-y-1 max-h-40 overflow-y-auto">
                {workspace.contact_history.length === 0 ? (
                  <div className="text-xs text-zinc-500">No contact logged yet.</div>
                ) : (
                  workspace.contact_history.slice().reverse().map((n) => (
                    <div key={n.id} className="text-xs text-zinc-400">
                      <span className="capitalize text-zinc-500">{n.category}</span> · {n.body} · {n.created_by} · {n.created_at.slice(0, 16).replace("T", " ")}
                    </div>
                  ))
                )}
              </div>
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">References</div>
              <div className="text-xs text-zinc-500">{workspace.references.note}</div>
            </div>
          </div>
        )}
      </div>
    </WorkOverlay>
  );
}
