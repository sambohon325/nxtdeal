"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// NXTDeal' internal "Success Center" board -- an ADMIN/OPERATIONS-only control
// surface over core/success_center.py's client-success / account-management
// platform. This is NOT a dealership department: it manages NXTDeal' own
// portfolio of DEALER accounts that use NXTDeal. Two sections: a dealer-portfolio
// list to pick an account, and a per-dealer overview (open recommendations by
// priority, success objectives, initiatives-by-status, latest/upcoming QBR) with
// controls to log a QBR / add an objective / initiative / recommendation, resolve
// a recommendation, and generate QBR-insights talking points from the isolated AI
// (with the same honest disabled/fallback handling as the Customer Journey board).
// Read/act through lib/successCenter.ts -- same shape and styling vocabulary as
// OperationsCustomerJourneyBoard.tsx (RIBBON palette, theme-aware classes).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  listDealers,
  getDealerOverview,
  createQbr,
  addObjective,
  addInitiative,
  addRecommendation,
  resolveRecommendation,
  generateQbrInsights,
  REC_PRIORITIES,
  INITIATIVE_STATUSES,
  type Dealer,
  type DealerOverview,
  type Recommendation,
  type QbrInsights,
} from "@/lib/successCenter";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

// A readable Title-Case label + a ribbon-derived accent per open-recommendation
// priority bucket (core/success_center.py's PRIORITIES).
const PRIORITY_LABEL: Record<string, string> = {
  high: "High",
  medium: "Medium",
  low: "Low",
};

const PRIORITY_COLOR: Record<string, string> = {
  high: RIBBON[3],
  medium: RIBBON[2],
  low: RIBBON[1],
};

// A readable label per initiative status (core/success_center.py's
// INITIATIVE_STATUSES).
const STATUS_LABEL: Record<string, string> = {
  planned: "Planned",
  in_progress: "In Progress",
  completed: "Completed",
  on_hold: "On Hold",
};

const STATUS_COLOR: Record<string, string> = {
  planned: RIBBON[0],
  in_progress: RIBBON[1],
  completed: RIBBON[2],
  on_hold: RIBBON[3],
};

function priorityLabel(priority: string | null | undefined): string {
  if (!priority) return "—";
  return PRIORITY_LABEL[priority] ?? priority;
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function InsightsCard({ theme, insights }: { theme: Theme; insights: QbrInsights }) {
  const points = Array.isArray(insights.talking_points) ? insights.talking_points : [];
  return (
    <div className={tc(theme, "rounded-md border border-zinc-700 bg-black/20 p-3", "rounded-md border border-zinc-300 bg-white p-3")}>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">
        🤖 QBR Insights {insights.ai_generated ? "" : insights.disabled ? "(disabled — fallback)" : "(fallback)"}
      </div>
      {insights.summary && <div className="text-sm font-medium text-zinc-200">{insights.summary}</div>}
      {points.length > 0 ? (
        <ul className="mt-2 space-y-1">
          {points.map((point, i) => (
            <li key={i} className="flex items-start gap-2 text-xs text-zinc-400">
              <span className="mt-1 h-1.5 w-1.5 rounded-full flex-shrink-0" style={{ background: RIBBON[1] }} />
              <span className="break-words">{point}</span>
            </li>
          ))}
        </ul>
      ) : (
        <div className="text-xs text-zinc-500 mt-2">No talking points generated.</div>
      )}
      {insights.suggested_focus && (
        <div className="text-xs text-zinc-500 mt-2">
          <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Suggested Focus</span>
          {insights.suggested_focus}
        </div>
      )}
      {insights.fallback_reason && (
        <div className="text-xs text-zinc-600 mt-2 italic">Fallback reason: {insights.fallback_reason}</div>
      )}
    </div>
  );
}

export function SuccessCenterBoard({ theme }: { theme: Theme }) {
  const [dealers, setDealers] = useState<Dealer[]>([]);
  const [dealersLoading, setDealersLoading] = useState(true);
  const [dealersError, setDealersError] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [overview, setOverview] = useState<DealerOverview | null>(null);
  const [overviewLoading, setOverviewLoading] = useState(false);
  const [overviewError, setOverviewError] = useState<string | null>(null);

  // Open recommendations list is loaded lazily via the overview's own totals; the
  // resolve control needs the actual records, so we surface them here too.
  const [openRecs, setOpenRecs] = useState<Recommendation[]>([]);

  const [actionBusy, setActionBusy] = useState(false);

  // Add-form field state.
  const [qbrPeriod, setQbrPeriod] = useState("");
  const [qbrNotes, setQbrNotes] = useState("");
  const [objectiveTitle, setObjectiveTitle] = useState("");
  const [objectiveTarget, setObjectiveTarget] = useState("");
  const [initiativeTitle, setInitiativeTitle] = useState("");
  const [initiativeStatus, setInitiativeStatus] = useState<string>(INITIATIVE_STATUSES[0]);
  const [recText, setRecText] = useState("");
  const [recPriority, setRecPriority] = useState<string>("medium");

  const [insights, setInsights] = useState<QbrInsights | null>(null);
  const [insightsBusy, setInsightsBusy] = useState(false);

  function refreshDealers() {
    setDealersLoading(true);
    setDealersError(null);
    listDealers()
      .then(setDealers)
      .catch((e) => setDealersError(e instanceof Error ? e.message : "Unable to load the dealer portfolio."))
      .finally(() => setDealersLoading(false));
  }

  useEffect(refreshDealers, []);

  function loadOverview(dealerId: string) {
    setOverviewLoading(true);
    setOverviewError(null);
    getDealerOverview(dealerId)
      .then(setOverview)
      .catch((e) => {
        setOverview(null);
        setOverviewError(e instanceof Error ? e.message : "Unable to load this dealer's overview.");
      })
      .finally(() => setOverviewLoading(false));
  }

  function selectDealer(dealerId: string) {
    setSelectedId(dealerId);
    setOverview(null);
    setOpenRecs([]);
    setInsights(null);
    setOverviewError(null);
    loadOverview(dealerId);
  }

  function refreshSelected() {
    if (selectedId) loadOverview(selectedId);
  }

  async function handleAddQbr() {
    if (!selectedId || !qbrPeriod.trim()) return;
    setActionBusy(true);
    setOverviewError(null);
    try {
      await createQbr(selectedId, qbrPeriod.trim(), qbrNotes.trim() || undefined);
      setQbrPeriod("");
      setQbrNotes("");
      refreshSelected();
    } catch (e) {
      setOverviewError(e instanceof Error ? e.message : "Unable to log this QBR.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleAddObjective() {
    if (!selectedId || !objectiveTitle.trim()) return;
    setActionBusy(true);
    setOverviewError(null);
    try {
      await addObjective(selectedId, objectiveTitle.trim(), objectiveTarget.trim() || undefined);
      setObjectiveTitle("");
      setObjectiveTarget("");
      refreshSelected();
    } catch (e) {
      setOverviewError(e instanceof Error ? e.message : "Unable to add this objective.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleAddInitiative() {
    if (!selectedId || !initiativeTitle.trim()) return;
    setActionBusy(true);
    setOverviewError(null);
    try {
      await addInitiative(selectedId, initiativeTitle.trim(), initiativeStatus);
      setInitiativeTitle("");
      setInitiativeStatus(INITIATIVE_STATUSES[0]);
      refreshSelected();
    } catch (e) {
      setOverviewError(e instanceof Error ? e.message : "Unable to add this initiative.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleAddRecommendation() {
    if (!selectedId || !recText.trim()) return;
    setActionBusy(true);
    setOverviewError(null);
    try {
      const created = await addRecommendation(selectedId, recText.trim(), recPriority);
      setOpenRecs((prev) => [created, ...prev]);
      setRecText("");
      setRecPriority("medium");
      refreshSelected();
    } catch (e) {
      setOverviewError(e instanceof Error ? e.message : "Unable to add this recommendation.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleResolve(recId: string) {
    if (!selectedId) return;
    setActionBusy(true);
    setOverviewError(null);
    try {
      await resolveRecommendation(selectedId, recId);
      setOpenRecs((prev) => prev.filter((r) => r.id !== recId));
      refreshSelected();
    } catch (e) {
      setOverviewError(e instanceof Error ? e.message : "Unable to resolve this recommendation.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleInsights() {
    if (!selectedId) return;
    setInsightsBusy(true);
    try {
      const result = await generateQbrInsights(selectedId);
      setInsights(result);
    } catch (e) {
      setOverviewError(e instanceof Error ? e.message : "Unable to generate QBR insights.");
    } finally {
      setInsightsBusy(false);
    }
  }

  const byPriority = overview?.open_recommendations_by_priority ?? {};
  const byStatus = overview?.initiatives_by_status ?? {};

  const inputDark = "flex-1 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white";
  const inputLight = "flex-1 text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black";
  const selectDark = "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white";
  const selectLight = "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black";

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      {/* Dealer portfolio */}
      <div className={tc(theme, "p-4 border-b border-zinc-800", "p-4 border-b border-zinc-200")}>
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">🏢 Dealer Portfolio</div>
          <WorkButton type="submit" onClick={refreshDealers} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
            ↻ Refresh
          </WorkButton>
        </div>
        {dealersLoading && <div className="text-sm text-zinc-500 mt-2">Loading…</div>}
        {dealersError && <div className="text-sm text-red-400 mt-2">{dealersError}</div>}
        {!dealersLoading && !dealersError && dealers.length === 0 && (
          <div className="text-sm text-zinc-500 mt-2">No dealer accounts yet.</div>
        )}
        {!dealersLoading && !dealersError && dealers.length > 0 && (
          <div className="grid grid-cols-2 gap-2 mt-3 md:grid-cols-3">
            {dealers.map((dealer) => {
              const active = dealer.dealer_id === selectedId;
              return (
                <button
                  key={dealer.dealer_id}
                  onClick={() => selectDealer(dealer.dealer_id)}
                  className={tc(
                    theme,
                    "text-left rounded-md border bg-brand-charcoal px-3 py-2",
                    "text-left rounded-md border bg-zinc-50 px-3 py-2"
                  )}
                  style={{
                    borderColor: active ? RIBBON[0] : "transparent",
                    boxShadow: active ? `0 0 0 2px ${RIBBON[0]}33` : undefined,
                  }}
                >
                  <div className="text-sm font-medium text-zinc-200 truncate">{dealer.name ?? dealer.dealer_id}</div>
                  <div className="text-xs text-zinc-500 truncate">{dealer.dealer_id}</div>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {!selectedId && (
        <div className="p-4 text-sm text-zinc-500">Select a dealer account to view its success overview.</div>
      )}

      {selectedId && (
        <div className={tc(theme, "p-4 space-y-4", "p-4 space-y-4")}>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">📊 Account Overview</div>
            <WorkButton type="submit" onClick={refreshSelected} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
              ↻ Refresh
            </WorkButton>
          </div>

          {overviewLoading && <div className="text-sm text-zinc-500">Loading…</div>}
          {overviewError && <div className="text-sm text-red-400">{overviewError}</div>}

          {overview && (
            <>
              {/* KPIs */}
              <div className="grid grid-cols-4 gap-3">
                <Kpi theme={theme} label="Open Recs" value={String(overview.open_recommendations_total ?? 0)} color={RIBBON[3]} />
                <Kpi theme={theme} label="Objectives" value={String(overview.objectives_count ?? 0)} color={RIBBON[0]} />
                <Kpi theme={theme} label="Initiatives" value={String(overview.initiatives_count ?? 0)} color={RIBBON[1]} />
                <Kpi theme={theme} label="QBRs Logged" value={String(overview.qbr_count ?? 0)} color={RIBBON[2]} />
              </div>

              {/* Open recommendations by priority */}
              <div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Open Recommendations by Priority</div>
                <div className="grid grid-cols-3 gap-2">
                  {REC_PRIORITIES.map((priority) => (
                    <div
                      key={priority}
                      className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2", "rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2")}
                    >
                      <div className="text-lg font-semibold" style={{ color: PRIORITY_COLOR[priority] ?? RIBBON[0] }}>
                        {byPriority[priority] ?? 0}
                      </div>
                      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{PRIORITY_LABEL[priority] ?? priority}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Initiatives by status */}
              <div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Initiatives by Status</div>
                <div className="grid grid-cols-4 gap-2">
                  {INITIATIVE_STATUSES.map((status) => (
                    <div
                      key={status}
                      className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2", "rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2")}
                    >
                      <div className="text-lg font-semibold" style={{ color: STATUS_COLOR[status] ?? RIBBON[0] }}>
                        {byStatus[status] ?? 0}
                      </div>
                      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{STATUS_LABEL[status] ?? status}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* QBR summary */}
              <div className="grid grid-cols-2 gap-2">
                <div className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal p-3", "rounded-md border border-zinc-200 bg-zinc-50 p-3")}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Latest QBR</div>
                  {overview.latest_qbr ? (
                    <>
                      <div className="text-sm font-medium text-zinc-200">{overview.latest_qbr.period}</div>
                      <div className="text-xs text-zinc-500">{fmt(overview.latest_qbr.created_at)}</div>
                      {overview.latest_qbr.notes && (
                        <div className="text-xs text-zinc-400 mt-1 break-words">{overview.latest_qbr.notes}</div>
                      )}
                    </>
                  ) : (
                    <div className="text-xs text-zinc-500">No QBR logged yet.</div>
                  )}
                </div>
                <div className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal p-3", "rounded-md border border-zinc-200 bg-zinc-50 p-3")}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Upcoming QBR</div>
                  {overview.upcoming_qbr ? (
                    <>
                      <div className="text-sm font-medium text-zinc-200">{overview.upcoming_qbr.period}</div>
                      <div className="text-xs text-zinc-500">{fmt(overview.upcoming_qbr.created_at)}</div>
                    </>
                  ) : (
                    <div className="text-xs text-zinc-500">None scheduled.</div>
                  )}
                </div>
              </div>

              {/* Objectives list */}
              <div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Success Objectives</div>
                {overview.objectives.length === 0 ? (
                  <div className="text-xs text-zinc-500">No objectives recorded yet.</div>
                ) : (
                  <div className="space-y-1.5">
                    {overview.objectives.map((objective) => (
                      <div
                        key={objective.id}
                        className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2", "rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2")}
                      >
                        <div className="text-sm text-zinc-200 break-words">{objective.title}</div>
                        {objective.target && (
                          <div className="text-xs text-zinc-500">
                            <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Target</span>
                            {objective.target}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Open recommendations added this session -- resolvable */}
              {openRecs.length > 0 && (
                <div>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Open Recommendations (this session)</div>
                  <div className="space-y-1.5">
                    {openRecs.map((rec) => (
                      <div
                        key={rec.id}
                        className={tc(theme, "flex items-start justify-between gap-2 rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2", "flex items-start justify-between gap-2 rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2")}
                      >
                        <div className="min-w-0">
                          <div className="text-sm text-zinc-200 break-words">{rec.text}</div>
                          <div className="text-xs" style={{ color: PRIORITY_COLOR[rec.priority] ?? "#9CA3AF" }}>
                            {priorityLabel(rec.priority)}
                          </div>
                        </div>
                        <WorkButton type="submit"
                          onClick={() => handleResolve(rec.id)}
                          disabled={actionBusy}
                          className="text-xs px-3 py-1.5 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50 whitespace-nowrap"
                        >
                          ✓ Resolve
                        </WorkButton>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* QBR insights AI */}
              <div className="space-y-2">
                <WorkButton type="submit"
                  onClick={handleInsights}
                  disabled={insightsBusy}
                  className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50"
                >
                  {insightsBusy ? "Generating…" : "✨ Generate QBR Insights"}
                </WorkButton>
                {insights && <InsightsCard theme={theme} insights={insights} />}
              </div>

              {/* Add controls */}
              <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-3")}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Add to Account</div>

                {/* Log QBR */}
                <div className="flex flex-wrap items-center gap-2">
                  <WorkField label="QBR period"><WorkInput
                    value={qbrPeriod}
                    onChange={(e) => setQbrPeriod(e.target.value)}
                    placeholder="QBR period (e.g. Q3 2026)"
                    className={tc(theme, inputDark, inputLight)}
                  /></WorkField>
                  <WorkField label="Notes (optional)"><WorkInput
                    value={qbrNotes}
                    onChange={(e) => setQbrNotes(e.target.value)}
                    placeholder="Notes (optional)"
                    className={tc(theme, inputDark, inputLight)}
                  /></WorkField>
                  <WorkButton type="submit"
                    onClick={handleAddQbr}
                    disabled={actionBusy || !qbrPeriod.trim()}
                    className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
                  >
                    Log QBR
                  </WorkButton>
                </div>

                {/* Add objective */}
                <div className="flex flex-wrap items-center gap-2">
                  <WorkField label="Objective title"><WorkInput
                    value={objectiveTitle}
                    onChange={(e) => setObjectiveTitle(e.target.value)}
                    placeholder="Objective title"
                    className={tc(theme, inputDark, inputLight)}
                  /></WorkField>
                  <WorkField label="Target (optional)"><WorkInput
                    value={objectiveTarget}
                    onChange={(e) => setObjectiveTarget(e.target.value)}
                    placeholder="Target (optional)"
                    className={tc(theme, inputDark, inputLight)}
                  /></WorkField>
                  <WorkButton type="submit"
                    onClick={handleAddObjective}
                    disabled={actionBusy || !objectiveTitle.trim()}
                    className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
                  >
                    Add Objective
                  </WorkButton>
                </div>

                {/* Add initiative */}
                <div className="flex flex-wrap items-center gap-2">
                  <WorkField label="Initiative title"><WorkInput
                    value={initiativeTitle}
                    onChange={(e) => setInitiativeTitle(e.target.value)}
                    placeholder="Initiative title"
                    className={tc(theme, inputDark, inputLight)}
                  /></WorkField>
                  <WorkField label="Initiative Status"><WorkSelect
                    value={initiativeStatus}
                    onChange={(e) => setInitiativeStatus(e.target.value)}
                    className={tc(theme, selectDark, selectLight)}
                  >
                    {INITIATIVE_STATUSES.map((status) => (
                      <option key={status} value={status}>
                        {STATUS_LABEL[status] ?? status}
                      </option>
                    ))}
                  </WorkSelect></WorkField>
                  <WorkButton type="submit"
                    onClick={handleAddInitiative}
                    disabled={actionBusy || !initiativeTitle.trim()}
                    className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
                  >
                    Add Initiative
                  </WorkButton>
                </div>

                {/* Add recommendation */}
                <div className="flex flex-wrap items-center gap-2">
                  <WorkField label="Recommendation text"><WorkInput
                    value={recText}
                    onChange={(e) => setRecText(e.target.value)}
                    placeholder="Recommendation text"
                    className={tc(theme, inputDark, inputLight)}
                  /></WorkField>
                  <WorkField label="Priority"><WorkSelect
                    value={recPriority}
                    onChange={(e) => setRecPriority(e.target.value)}
                    className={tc(theme, selectDark, selectLight)}
                  >
                    {REC_PRIORITIES.map((priority) => (
                      <option key={priority} value={priority}>
                        {PRIORITY_LABEL[priority] ?? priority}
                      </option>
                    ))}
                  </WorkSelect></WorkField>
                  <WorkButton type="submit"
                    onClick={handleAddRecommendation}
                    disabled={actionBusy || !recText.trim()}
                    className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
                  >
                    Add Recommendation
                  </WorkButton>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
