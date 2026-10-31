"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Operations' "Customer Journey" board -- a staff-facing visualizer + control
// surface over core/customer_journey.py's graph-native lifecycle stage tracking
// (Awareness -> Lead -> Appointment -> Sale -> Service -> Loyalty -> Repeat).
// Three sections: a Journey Designer pipeline (7 stage nodes scaled by live
// volume), stage-overview KPIs, and a per-customer lookup that can advance /
// set a customer's stage and pull slice 2's AI next-best-action recommendation.
// Read/act through lib/customerJourney.ts -- same shape and styling vocabulary
// as OperationsCommunicationsBoard.tsx (RIBBON palette, theme-aware classes).
import { CustomerLoyaltyPanel } from "@/components/CustomerLoyaltyPanel";
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState } from "react";
import {
  getJourneyOverview,
  getCustomerJourney,
  advanceJourney,
  setJourneyStage,
  generateJourneyRecommendation,
  JOURNEY_STAGES,
  type JourneyOverview,
  type CustomerJourney,
  type JourneyRecommendation,
} from "@/lib/customerJourney";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

// A readable Title-Case label + a ribbon-derived accent color per stage. Colors
// cycle the RIBBON palette so the pipeline reads as one branded system.
const STAGE_LABEL: Record<string, string> = {
  AWARENESS: "Awareness",
  LEAD: "Lead",
  APPOINTMENT: "Appointment",
  SALE: "Sale",
  SERVICE: "Service",
  LOYALTY: "Loyalty",
  REPEAT: "Repeat",
};

const STAGE_COLOR: Record<string, string> = {
  AWARENESS: RIBBON[0],
  LEAD: RIBBON[1],
  APPOINTMENT: RIBBON[2],
  SALE: RIBBON[3],
  SERVICE: RIBBON[0],
  LOYALTY: RIBBON[1],
  REPEAT: RIBBON[2],
};

function stageLabel(stage: string | null | undefined): string {
  if (!stage) return "—";
  return STAGE_LABEL[stage] ?? stage;
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

// One node in the horizontal lifecycle pipeline. Scales its emphasis (ring +
// count size) by this stage's share of the busiest stage, so heavier stages
// visually pop -- the "designer/visualizer" idea from the slice brief.
function StageNode({
  theme,
  stage,
  count,
  maxCount,
  active,
}: {
  theme: Theme;
  stage: string;
  count: number;
  maxCount: number;
  active: boolean;
}) {
  const color = STAGE_COLOR[stage] ?? RIBBON[0];
  const share = maxCount > 0 ? count / maxCount : 0;
  // 1.0 -> ~1.18 scale for the busiest stage; keeps small stages readable.
  const scale = 1 + share * 0.18;
  return (
    <div className="flex flex-col items-center gap-1" style={{ transform: `scale(${scale})` }}>
      <div
        className={tc(
          theme,
          "flex flex-col items-center justify-center rounded-full border bg-brand-charcoal",
          "flex flex-col items-center justify-center rounded-full border bg-zinc-50"
        )}
        style={{
          width: 64,
          height: 64,
          borderColor: color,
          borderWidth: active ? 3 : 1,
          boxShadow: active ? `0 0 0 3px ${color}33` : undefined,
        }}
      >
        <span className="text-lg font-semibold leading-none" style={{ color }}>
          {count}
        </span>
      </div>
      <span className="text-xs font-brand uppercase tracking-wide text-zinc-500 text-center">{STAGE_LABEL[stage] ?? stage}</span>
    </div>
  );
}

function JourneyPipeline({ theme, overview }: { theme: Theme; overview: JourneyOverview | null }) {
  const counts = overview?.counts_by_stage ?? {};
  const maxCount = useMemo(() => {
    const values = JOURNEY_STAGES.map((s) => counts[s] ?? 0);
    return values.reduce((a, b) => Math.max(a, b), 0);
  }, [counts]);

  return (
    <div className="flex items-center gap-1 overflow-x-auto py-4">
      {JOURNEY_STAGES.map((stage, i) => (
        <div key={stage} className="flex items-center gap-1">
          <StageNode
            theme={theme}
            stage={stage}
            count={counts[stage] ?? 0}
            maxCount={maxCount}
            active={(counts[stage] ?? 0) > 0}
          />
          {i < JOURNEY_STAGES.length - 1 && (
            <span className="text-zinc-600 text-lg select-none">→</span>
          )}
        </div>
      ))}
    </div>
  );
}

function RecommendationCard({ theme, rec }: { theme: Theme; rec: JourneyRecommendation }) {
  return (
    <div className={tc(theme, "rounded-md border border-zinc-700 bg-black/20 p-3", "rounded-md border border-zinc-300 bg-white p-3")}>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">
        🤖 AI Recommendation {rec.ai_generated ? "" : rec.disabled ? "(disabled — fallback)" : "(fallback)"}
      </div>
      <div className="text-sm font-medium text-zinc-200">{rec.recommended_action || "—"}</div>
      {rec.reason && <div className="text-xs text-zinc-400 mt-1">{rec.reason}</div>}
      <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2">
        {rec.suggested_timing && (
          <div className="text-xs text-zinc-500">
            <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Timing</span>
            {rec.suggested_timing}
          </div>
        )}
        {rec.suggested_campaign && (
          <div className="text-xs text-zinc-500">
            <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Campaign</span>
            {rec.suggested_campaign}
          </div>
        )}
      </div>
      {rec.fallback_reason && (
        <div className="text-xs text-zinc-600 mt-2 italic">Fallback reason: {rec.fallback_reason}</div>
      )}
    </div>
  );
}

export function OperationsCustomerJourneyBoard({ theme }: { theme: Theme }) {
  const [overview, setOverview] = useState<JourneyOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Per-customer lookup state -- distinct from the overview above.
  const [lookupId, setLookupId] = useState("");
  const [journey, setJourney] = useState<CustomerJourney | null>(null);
  const [journeyLoading, setJourneyLoading] = useState(false);
  const [journeyError, setJourneyError] = useState<string | null>(null);

  const [actionBusy, setActionBusy] = useState(false);
  const [setStageValue, setSetStageValue] = useState<string>(JOURNEY_STAGES[0]);

  const [rec, setRec] = useState<JourneyRecommendation | null>(null);
  const [recBusy, setRecBusy] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    getJourneyOverview()
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the Customer Journey overview."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  function loadJourney(customerId: string) {
    const id = customerId.trim();
    if (!id) {
      setJourneyError("Enter a customer id to look up.");
      return;
    }
    setJourneyLoading(true);
    setJourneyError(null);
    setRec(null);
    getCustomerJourney(id)
      .then((j) => {
        setJourney(j);
        if (j.journey_stage) setSetStageValue(j.journey_stage);
      })
      .catch((e) => {
        setJourney(null);
        setJourneyError(e instanceof Error ? e.message : "Unable to load this customer's journey.");
      })
      .finally(() => setJourneyLoading(false));
  }

  async function handleAdvance() {
    if (!journey) return;
    setActionBusy(true);
    setJourneyError(null);
    try {
      const updated = await advanceJourney(journey.customer_id);
      setJourney(updated);
      if (updated.journey_stage) setSetStageValue(updated.journey_stage);
      refresh();
    } catch (e) {
      setJourneyError(e instanceof Error ? e.message : "Unable to advance this customer.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleSetStage() {
    if (!journey) return;
    setActionBusy(true);
    setJourneyError(null);
    try {
      const updated = await setJourneyStage(journey.customer_id, setStageValue);
      setJourney(updated);
      refresh();
    } catch (e) {
      setJourneyError(e instanceof Error ? e.message : "Unable to set this customer's stage.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleRecommendation() {
    if (!journey) return;
    setRecBusy(true);
    try {
      const result = await generateJourneyRecommendation(journey.customer_id);
      setRec(result);
    } catch (e) {
      setJourneyError(e instanceof Error ? e.message : "Unable to generate a recommendation.");
    } finally {
      setRecBusy(false);
    }
  }

  const counts = overview?.counts_by_stage ?? {};

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      {/* Journey Designer -- the visual pipeline */}
      <div className={tc(theme, "p-4 border-b border-zinc-800", "p-4 border-b border-zinc-200")}>
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">🧭 Journey Designer</div>
          <WorkButton type="submit" onClick={refresh} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
            ↻ Refresh
          </WorkButton>
        </div>
        {loading && <div className="text-sm text-zinc-500 mt-2">Loading…</div>}
        {error && <div className="text-sm text-red-400 mt-2">{error}</div>}
        {!loading && !error && <JourneyPipeline theme={theme} overview={overview} />}
      </div>

      {/* Stage overview KPIs */}
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Customers Tracked" value={String(overview?.total_customers_in_journey ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Lifecycle Stages" value={String(JOURNEY_STAGES.length)} color={RIBBON[1]} />
        <Kpi theme={theme} label="In Sale Stage" value={String(counts["SALE"] ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="In Repeat Stage" value={String(counts["REPEAT"] ?? 0)} color={RIBBON[3]} />
      </div>

      <div className={tc(theme, "grid grid-cols-4 gap-2 px-4 py-3 border-b border-zinc-800", "grid grid-cols-4 gap-2 px-4 py-3 border-b border-zinc-200")}>
        {JOURNEY_STAGES.map((stage) => (
          <div
            key={stage}
            className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2", "rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2")}
          >
            <div className="text-lg font-semibold" style={{ color: STAGE_COLOR[stage] ?? RIBBON[0] }}>
              {counts[stage] ?? 0}
            </div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{STAGE_LABEL[stage] ?? stage}</div>
          </div>
        ))}
      </div>

      {/* Per-customer journey */}
      <div className={tc(theme, "p-4 space-y-3", "p-4 space-y-3")}>
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">👤 Per-Customer Journey</div>

        <div className="flex items-center gap-2">
          <WorkField label="Record ID"><WorkInput
            value={lookupId}
            onChange={(e) => setLookupId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") loadJourney(lookupId);
            }}
            placeholder="Customer id (e.g. CUST-00123)"
            className={tc(
              theme,
              "flex-1 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white",
              "flex-1 text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black"
            )}
          /></WorkField>
          <WorkButton type="submit"
            onClick={() => loadJourney(lookupId)}
            disabled={journeyLoading}
            className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
          >
            {journeyLoading ? "Loading…" : "Look Up"}
          </WorkButton>
        </div>

        {journeyError && <div className="text-sm text-red-400">{journeyError}</div>}

        {journey && <CustomerLoyaltyPanel customerId={journey.customer_id} />}
        {journey && (
          <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-3")}>
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-200 truncate">{journey.name ?? journey.customer_id}</div>
                <div className="text-xs text-zinc-500">{journey.customer_id}</div>
              </div>
              <div className="text-right">
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Current Stage</div>
                <div className="text-sm font-semibold" style={{ color: STAGE_COLOR[journey.journey_stage ?? ""] ?? "#9CA3AF" }}>
                  {stageLabel(journey.journey_stage)}
                </div>
              </div>
            </div>

            {/* Actions */}
            <div className="flex flex-wrap items-center gap-2">
              <WorkButton type="submit"
                onClick={handleAdvance}
                disabled={actionBusy}
                className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50"
              >
                {actionBusy ? "…" : "➜ Advance Stage"}
              </WorkButton>
              <div className="flex items-center gap-1.5">
                <WorkField label="Journey stage"><WorkSelect
                  value={setStageValue}
                  onChange={(e) => setSetStageValue(e.target.value)}
                  className={tc(
                    theme,
                    "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white",
                    "text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black"
                  )}
                >
                  {JOURNEY_STAGES.map((s) => (
                    <option key={s} value={s}>
                      {STAGE_LABEL[s] ?? s}
                    </option>
                  ))}
                </WorkSelect></WorkField>
                <WorkButton type="submit"
                  onClick={handleSetStage}
                  disabled={actionBusy}
                  className="text-xs px-3 py-1.5 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50"
                >
                  Set Stage
                </WorkButton>
              </div>
              <WorkButton type="submit"
                onClick={handleRecommendation}
                disabled={recBusy}
                className="text-xs px-3 py-1.5 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50 ml-auto"
              >
                {recBusy ? "Generating…" : "✨ Get AI Recommendation"}
              </WorkButton>
            </div>

            {rec && <RecommendationCard theme={theme} rec={rec} />}

            {/* Journey history timeline */}
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Journey History</div>
              {journey.journey_history.length === 0 ? (
                <div className="text-xs text-zinc-500">No stage history recorded yet.</div>
              ) : (
                <div className="space-y-1.5">
                  {journey.journey_history.map((entry, i) => (
                    <div key={i} className="flex items-start gap-2">
                      <span
                        className="mt-1 h-2 w-2 rounded-full flex-shrink-0"
                        style={{ background: STAGE_COLOR[entry.stage] ?? "#9CA3AF" }}
                      />
                      <div className="min-w-0">
                        <div className="text-xs text-zinc-300">
                          <span className="font-medium">{STAGE_LABEL[entry.stage] ?? entry.stage}</span>
                          <span className="text-zinc-600 ml-2">{fmt(entry.timestamp)}</span>
                        </div>
                        {entry.note && <div className="text-xs text-zinc-500 break-words">{entry.note}</div>}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
