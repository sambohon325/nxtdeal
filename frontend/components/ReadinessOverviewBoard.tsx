"use client";
import { WorkInput, WorkButton } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Readiness' rebuilt "Overview" Top Menu item -- the real Enterprise Readiness
// Dashboard Sam described, and, confirmed the same real feature before
// building anything, ALSO the answer to his separately-named "Readiness
// Heatmap" capstone ("show every department % with drill-down capability").
// Three real pieces, composed by core/readiness_overview.py:
//   1. A department readiness heatmap -- real, color-coded, covering the 5
//      departments core/prediction.py actually has an entry for (sales/
//      service/finance/marketing/parts), with an honest note on the 3 it
//      doesn't (Operations/Inventory/Administration).
//   2. Today's Risks -- core/enterprise_risk_center.py's real risk feed
//      reused verbatim, shown as a ranked top-5 strip.
//   3. An Executive Summary -- a real, rules-based templated narrative (never
//      a fabricated LLM fact), with an optional isolated-OpenAI phrasing
//      polish that can never invent a number.
// Clicking a heatmap cell drills down into BusinessHealthBoard's own
// per-department detail (reused via its focusDepartment prop) rather than a
// second, duplicate detail view.
import { useEffect, useState } from "react";
import {
  getReadinessOverview,
  regenerateExecutiveSummary,
  type ReadinessOverview,
  type HeatmapCell,
  type TopRisk,
  type StatusColor,
} from "@/lib/readinessOverview";
import { BusinessHealthBoard } from "@/components/BusinessHealthBoard";
import { askBusinessAnalyst, type BusinessAnalystAnswer } from "@/lib/aiBusinessAnalyst";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

// business_health.py's own 5 department keys -- sales/service/finance/marketing
// match the heatmap's keys 1:1; "inventory" has no heatmap equivalent (business
// health tracks Inventory, prediction.py tracks Parts -- genuinely different
// scopes, not silently conflated). "parts" (the heatmap's own 5th key) has no
// Business Health section at all -- honestly non-clickable rather than
// papered over with a mismatched drill-down.
const BUSINESS_HEALTH_DEPARTMENTS = new Set(["sales", "service", "finance", "marketing"]);

const STATUS_COLOR_STYLE: Record<StatusColor, { bg: string; border: string; text: string; dot: string }> = {
  green: { bg: "bg-emerald-950/30", border: "border-emerald-800/50", text: "text-emerald-300", dot: "#2FBF71" },
  yellow: { bg: "bg-amber-950/30", border: "border-amber-800/50", text: "text-amber-300", dot: "#F4C300" },
  red: { bg: "bg-red-950/30", border: "border-red-800/50", text: "text-red-300", dot: "#EE3C25" },
  gray: { bg: "bg-zinc-800/40", border: "border-zinc-700/50", text: "text-zinc-400", dot: "#6B7280" },
};

const SEVERITY_DOT: Record<string, string> = {
  critical: "#EE3C25",
  high: "#F4802E",
  medium: "#F4C300",
  low: "#8AA0B0",
};

function fmtPct(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined) return "—";
  return `${value.toFixed(digits)}%`;
}

function BasisBadge({ basis }: { basis?: string }) {
  if (!basis) return null;
  const map: Record<string, string> = {
    ledger: "bg-emerald-950/40 text-emerald-300",
    blended: "bg-amber-950/40 text-amber-300",
    industry_estimate: "bg-zinc-800 text-zinc-400",
  };
  const cls = map[basis] ?? "bg-zinc-800 text-zinc-400";
  return <span className={`ml-1.5 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${cls}`}>{basis.replace("_", " ")}</span>;
}

function HeatmapCellCard({
  theme,
  cell,
  onClick,
  clickable,
}: {
  theme: Theme;
  cell: HeatmapCell;
  onClick?: () => void;
  clickable: boolean;
}) {
  const style = STATUS_COLOR_STYLE[cell.status_color];
  return (
    <button
      onClick={clickable ? onClick : undefined}
      disabled={!clickable}
      className={`relative overflow-hidden rounded-lg border ${style.border} ${style.bg} p-3 text-left transition ${
        clickable ? "hover:brightness-125 cursor-pointer" : "cursor-default opacity-90"
      }`}
    >
      <span className="absolute right-2 top-2 h-2.5 w-2.5 rounded-full" style={{ background: style.dot }} />
      <div className="text-xs uppercase tracking-wide text-zinc-400">{cell.department}</div>
      <div className={`text-2xl font-semibold mt-1 ${style.text}`}>{fmtPct(cell.confidence_pct)}</div>
      <div className="text-xs text-zinc-500 mt-1 flex items-center flex-wrap">
        {cell.ready ? "Ready" : `Below ${cell.threshold}% threshold`}
        <BasisBadge basis={cell.basis} />
      </div>
      {clickable && <div className="text-xs text-zinc-600 mt-1.5">Click to drill down →</div>}
    </button>
  );
}

function RiskChip({ theme, risk }: { theme: Theme; risk: TopRisk }) {
  return (
    <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-3 py-2", "rounded border border-zinc-200 bg-zinc-50 px-3 py-2")}>
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold">{risk.count}</span>
        <span className="h-2 w-2 rounded-full" style={{ background: SEVERITY_DOT[risk.severity] ?? "#8AA0B0" }} />
      </div>
      <div className="text-xs text-zinc-300 mt-0.5">{risk.title}</div>
      <div className="text-xs text-zinc-500 mt-1">{risk.resolve?.department} → {risk.resolve?.item_key}</div>
    </div>
  );
}

type AskedQA = BusinessAnalystAnswer & { id: number };

function AiBusinessAnalystPanel({ theme }: { theme: Theme }) {
  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<AskedQA[]>([]);

  const SAMPLE_QUESTIONS = [
    "Why is inventory readiness declining?",
    "What are the top risks right now?",
    "How is our loan portfolio and collections looking?",
    "What should we do about sales performance?",
  ];

  function handleAsk(q?: string) {
    const text = (q ?? question).trim();
    if (!text || asking) return;
    setAsking(true);
    setError(null);
    askBusinessAnalyst(text)
      .then((res) => {
        setHistory((prev) => [{ ...res, id: Date.now() }, ...prev]);
        setQuestion("");
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to reach the AI Business Analyst."))
      .finally(() => setAsking(false));
  }

  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
      <div className="text-sm font-brand font-semibold mb-1">AI Business Analyst</div>
      <div className="text-xs text-zinc-500 mb-3">
        Ask a plain-English question -- every answer is grounded in the real data above (Business Health,
        Today&apos;s Risks, Recommendations, Forecasts). The optional AI phrasing may never invent a number not
        already present in that real data.
      </div>

      <div className="flex gap-2">
        <WorkField label="Question"><WorkInput
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleAsk();
          }}
          placeholder="e.g. Why is inventory readiness declining?"
          className={tc(
            theme,
            "flex-1 rounded border border-zinc-700 bg-zinc-900 px-2.5 py-1.5 text-xs text-white placeholder:text-zinc-600",
            "flex-1 rounded border border-zinc-300 bg-white px-2.5 py-1.5 text-xs text-black placeholder:text-zinc-400"
          )}
        /></WorkField>
        <WorkButton type="submit"
          onClick={() => handleAsk()}
          disabled={asking || !question.trim()}
          className="px-3 py-1.5 rounded text-xs bg-zinc-200 text-black font-medium hover:bg-white disabled:opacity-50"
        >
          {asking ? "Asking…" : "Ask"}
        </WorkButton>
      </div>

      <div className="flex flex-wrap gap-1.5 mt-2">
        {SAMPLE_QUESTIONS.map((q) => (
          <WorkButton type="submit"
            key={q}
            onClick={() => handleAsk(q)}
            disabled={asking}
            className="px-2 py-1 rounded text-xs bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
          >
            {q}
          </WorkButton>
        ))}
      </div>

      {error && <div className="text-xs text-red-400 mt-2">{error}</div>}

      {history.length > 0 && (
        <div className="mt-3 space-y-2">
          {history.map((qa) => (
            <div key={qa.id} className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 p-2.5", "rounded border border-zinc-200 bg-zinc-50 p-2.5")}>
              <div className="flex items-center justify-between flex-wrap gap-1">
                <div className="text-xs font-semibold text-zinc-200">{qa.question}</div>
                <span
                  className={`px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${
                    qa.ai_generated ? "bg-sky-950/40 text-sky-300" : "bg-emerald-950/40 text-emerald-300"
                  }`}
                >
                  {qa.ai_generated ? "AI-phrased" : "real template"}
                </span>
              </div>
              <div className="text-xs text-zinc-300 mt-1.5 leading-relaxed">{qa.answer}</div>
              {qa.note && <div className="text-xs text-zinc-600 mt-1.5 italic">{qa.note}</div>}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function ReadinessOverviewBoard({ theme, hideAssistant = false }: { theme: Theme; hideAssistant?: boolean }) {
  const [data, setData] = useState<ReadinessOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [focusDepartment, setFocusDepartment] = useState<string | null>(null);
  const [regenerating, setRegenerating] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    getReadinessOverview(!hideAssistant)
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the Readiness Overview."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), [hideAssistant]);

  function handleRegenerate(polish: boolean) {
    setRegenerating(true);
    regenerateExecutiveSummary(polish)
      .then((summary) => setData((prev) => (prev ? { ...prev, executive_summary: summary } : prev)))
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to regenerate the summary."))
      .finally(() => setRegenerating(false));
  }

  if (focusDepartment) {
    return (
      <BusinessHealthBoard
        theme={theme}
        focusDepartment={focusDepartment}
        onClearFocus={() => setFocusDepartment(null)}
      />
    );
  }

  const heatmap = data?.heatmap;
  const risks = data?.todays_risks;
  const summary = data?.executive_summary;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">Enterprise Readiness Dashboard</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          Is the dealership ready to achieve its goals, where are the risks, and what should we do about it -- a real
          readiness heatmap, today&apos;s risks, and an executive summary, all composed from already-real data.
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            {/* Executive Summary */}
            <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="text-sm font-brand font-semibold flex items-center">
                  Executive Summary
                  <span
                    className={`ml-2 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide ${
                      summary?.ai_generated ? "bg-sky-950/40 text-sky-300" : "bg-emerald-950/40 text-emerald-300"
                    }`}
                  >
                    {summary?.ai_generated ? "AI-polished" : "real template"}
                  </span>
                </div>
                <div className="flex gap-2">
                  <WorkButton type="submit"
                    onClick={() => handleRegenerate(false)}
                    disabled={regenerating}
                    className="px-2.5 py-1 rounded text-xs bg-zinc-800 text-zinc-200 hover:bg-zinc-700 disabled:opacity-50"
                  >
                    Regenerate (template)
                  </WorkButton>
                  {!hideAssistant && <WorkButton type="submit"
                    onClick={() => handleRegenerate(true)}
                    disabled={regenerating}
                    className="px-2.5 py-1 rounded text-xs bg-zinc-200 text-black font-medium hover:bg-white disabled:opacity-50"
                  >
                    ✨ Regenerate + AI polish
                  </WorkButton>}
                </div>
              </div>
              <p className="text-sm text-zinc-200 mt-3 leading-relaxed">{summary?.summary}</p>
              {!hideAssistant && summary?.ai_polish_note && (
                <div className="text-xs text-zinc-600 mt-2 italic">{summary.ai_polish_note}</div>
              )}
              <div className="text-xs text-zinc-600 mt-2">
                Every fact in this summary comes from the computed data below.
                {!hideAssistant && " Optional AI polish changes phrasing only, never numbers or findings."}
              </div>
            </div>

            {/* Readiness Heatmap */}
            <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
              <div className="text-sm font-brand font-semibold mb-1">Department Readiness Heatmap</div>
              <div className="text-xs text-zinc-500 mb-3">
                {heatmap?.avg_confidence_pct !== null && heatmap?.avg_confidence_pct !== undefined
                  ? `${fmtPct(heatmap.avg_confidence_pct)} average confidence across the ${heatmap.covered_count} covered department(s).`
                  : "No covered department has a confidence score yet."}
              </div>
              <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                {heatmap?.covered.map((cell) => (
                  <HeatmapCellCard
                    key={cell.department}
                    theme={theme}
                    cell={cell}
                    clickable={BUSINESS_HEALTH_DEPARTMENTS.has(cell.department)}
                    onClick={() => setFocusDepartment(cell.department)}
                  />
                ))}
              </div>
              {heatmap?.uncovered && heatmap.uncovered.length > 0 && (
                <div className="text-xs text-zinc-600 mt-3 flex items-center flex-wrap">
                  <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500 uppercase tracking-wide mr-2">gap</span>
                  {heatmap.uncovered_note}
                </div>
              )}
            </div>

            {/* Today's Risks */}
            <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
              <div className="flex items-center justify-between mb-3">
                <div className="text-sm font-brand font-semibold">Today&apos;s Risks</div>
                {risks?.kpi && (
                  <div className="text-xs text-zinc-500">
                    {risks.kpi.total_exception_types_active} of {risks.kpi.total_exception_types} exception types active ·{" "}
                    {risks.kpi.total_affected_entities} affected entities
                  </div>
                )}
              </div>
              {risks && risks.top_risks.length > 0 ? (
                <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-2">
                  {risks.top_risks.map((r) => (
                    <RiskChip key={r.key} theme={theme} risk={r} />
                  ))}
                </div>
              ) : (
                <div className="text-xs text-emerald-300">No active risks right now -- clear across Critical, Financial, and Operational categories.</div>
              )}
              <div className="text-xs text-zinc-600 mt-3">
                Reused directly from the Enterprise Risk Center (Readiness → Exceptions) -- no recomputation.
              </div>
            </div>

            {/* AI Business Analyst */}
            {!hideAssistant && <AiBusinessAnalystPanel theme={theme} />}

            {data?.not_yet_tracked && Object.keys(data.not_yet_tracked).length > 0 && (
              <div className={tc(theme, "text-xs text-zinc-500 bg-zinc-900/40 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-500 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
                {Object.entries(data.not_yet_tracked).map(([key, note]) => (
                  <div key={key} className="mb-1 last:mb-0">
                    <span className="uppercase tracking-wide text-zinc-600 mr-1">{key.replace(/_/g, " ")}:</span>
                    {note}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
