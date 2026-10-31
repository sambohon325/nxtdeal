"use client";
import { WorkButton, WorkTextarea, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// The "AI Consulting Engine" board -- the strategic centerpiece of the NXTDeal
// deck (NXTDeal deck: "software + human consultants" -> "software + an AI
// consulting organization"). A user asks a plain business question ("Why are
// service sales down?", "Where are we losing the most gross profit?") and gets
// back a structured CONSULTING answer in four parts: Analysis, Root Cause,
// Opportunity, and a concrete Action Plan. It composes core/consulting_engine.py's
// pure-composition-over-already-real-modules answer, with AI phrasing as optional
// polish over an always-real, fact-grounded fallback (never load-bearing).
// Read/act through lib/consultingEngine.ts -- same shape and styling vocabulary
// (RIBBON palette, theme-aware classes) as OperationsCustomerJourneyBoard.tsx.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getConsultingOverview,
  askConsultation,
  type ConsultingOverview,
  type Consultation,
} from "@/lib/consultingEngine";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

// The sentinel value the department <select> uses for a whole-store (no
// department) consultation. Distinct from any real ADVISOR_DEPARTMENTS key so it
// never collides; mapped back to null before the POST.
const ALL_DEPARTMENTS = "";

// Readable Title-Case labels for the known ADVISOR_DEPARTMENTS keys
// (["sales", "service", "parts", "fi", "bhph"]); unknown keys fall back to the
// raw value so the board never blanks out if the backend list grows.
const DEPARTMENT_LABEL: Record<string, string> = {
  sales: "Sales",
  service: "Service",
  parts: "Parts",
  fi: "F&I",
  bhph: "BHPH",
};

function departmentLabel(dept: string | null | undefined): string {
  if (!dept) return "Whole business";
  return DEPARTMENT_LABEL[dept] ?? dept;
}

function money(value: number | null | undefined): string {
  const n = typeof value === "number" ? value : 0;
  return n.toLocaleString([], { style: "currency", currency: "USD", minimumFractionDigits: 0, maximumFractionDigits: 0 });
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

// One of the four labeled consulting cards. `accent` is a RIBBON color used for
// the left clip and the section label so the four cards read as one system.
function SectionCard({
  theme,
  label,
  accent,
  children,
}: {
  theme: Theme;
  label: string;
  accent: string;
  children: React.ReactNode;
}) {
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
      <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5" style={{ background: accent, clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }} />
      <div className="text-xs font-brand uppercase tracking-wide mb-1.5" style={{ color: accent }}>
        {label}
      </div>
      {children}
    </div>
  );
}

// A single data-readiness pill in the strip below the ask box.
function ReadinessPill({ theme, label, value, ok }: { theme: Theme; label: string; value: string; ok: boolean }) {
  return (
    <div className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2", "rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2")}>
      <div className="flex items-center gap-1.5">
        <span className="h-2 w-2 rounded-full flex-shrink-0" style={{ background: ok ? RIBBON[1] : "#9CA3AF" }} />
        <div className="text-sm font-semibold">{value}</div>
      </div>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mt-0.5">{label}</div>
    </div>
  );
}

function ConsultationAnswer({ theme, result }: { theme: Theme; result: Consultation }) {
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="text-xs font-brand uppercase tracking-wide px-2 py-0.5 rounded-full"
          style={{
            background: result.ai_generated ? `${RIBBON[1]}22` : "#9CA3AF22",
            color: result.ai_generated ? RIBBON[1] : "#9CA3AF",
          }}
        >
          {result.ai_generated ? "🤖 AI-phrased" : "📊 Fact-based (fallback)"}
        </span>
        <span className="text-xs font-brand uppercase tracking-wide text-zinc-500">
          {departmentLabel(result.department)}
        </span>
      </div>

      {result.note && (
        <div className={tc(theme, "text-xs text-zinc-400 italic", "text-xs text-zinc-500 italic")}>{result.note}</div>
      )}

      <SectionCard theme={theme} label="Analysis" accent={RIBBON[0]}>
        <div className="text-sm text-zinc-200 whitespace-pre-line">{result.analysis || "—"}</div>
      </SectionCard>

      <SectionCard theme={theme} label="Root Cause" accent={RIBBON[3]}>
        <div className="text-sm text-zinc-200 whitespace-pre-line">{result.root_cause || "—"}</div>
      </SectionCard>

      <SectionCard theme={theme} label="Opportunity" accent={RIBBON[2]}>
        <div className="text-sm text-zinc-200 whitespace-pre-line">{result.opportunity || "—"}</div>
      </SectionCard>

      <SectionCard theme={theme} label="Action Plan" accent={RIBBON[1]}>
        {(result.action_plan ?? []).length === 0 ? (
          <div className="text-sm text-zinc-500">No action steps returned.</div>
        ) : (
          <ol className="space-y-1.5">
            {(result.action_plan ?? []).map((step, i) => (
              <li key={i} className="flex items-start gap-2">
                <span
                  className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full text-xs font-semibold"
                  style={{ background: `${RIBBON[1]}22`, color: RIBBON[1] }}
                >
                  {i + 1}
                </span>
                <span className="text-sm text-zinc-200 break-words">{step}</span>
              </li>
            ))}
          </ol>
        )}
      </SectionCard>

      {result.confidence_note && (
        <div className={tc(theme, "rounded-md border border-zinc-800 bg-black/20 p-2.5", "rounded-md border border-zinc-200 bg-white p-2.5")}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-0.5">Confidence</div>
          <div className="text-xs text-zinc-400">{result.confidence_note}</div>
        </div>
      )}

      {(result.sources ?? []).length > 0 && (
        <div className="text-xs text-zinc-500">
          <span className="font-brand uppercase tracking-wide text-zinc-600 mr-1">Sources</span>
          {(result.sources ?? []).join(" · ")}
        </div>
      )}
    </div>
  );
}

export function ConsultingEngineBoard({ theme }: { theme: Theme }) {
  const [overview, setOverview] = useState<ConsultingOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Ask-box state -- distinct from the overview above.
  const [question, setQuestion] = useState("");
  const [department, setDepartment] = useState<string>(ALL_DEPARTMENTS);
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [result, setResult] = useState<Consultation | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getConsultingOverview()
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the AI Consulting Engine overview."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  function runAsk(rawQuestion: string, dept: string) {
    const q = rawQuestion.trim();
    if (!q) {
      setAskError("Ask a business question first.");
      return;
    }
    setAsking(true);
    setAskError(null);
    askConsultation(q, dept === ALL_DEPARTMENTS ? null : dept)
      .then((r) => {
        setResult(r);
        refresh();
      })
      .catch((e) => {
        setResult(null);
        setAskError(e instanceof Error ? e.message : "Unable to run this consultation.");
      })
      .finally(() => setAsking(false));
  }

  function handleStarter(q: string) {
    setQuestion(q);
    runAsk(q, department);
  }

  const dataSources = overview?.data_sources ?? null;
  const starters = overview?.starter_questions ?? [];
  const departments = overview?.departments_available ?? [];
  const recent = overview?.recent_consultations ?? [];

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      {/* Ask box -- the prominent centerpiece */}
      <div className={tc(theme, "p-4 border-b border-zinc-800", "p-4 border-b border-zinc-200")}>
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">🧠 AI Consulting Engine</div>
          <WorkButton type="submit" onClick={refresh} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
            ↻ Refresh
          </WorkButton>
        </div>

        <div className="mt-3 space-y-2">
          <WorkField label="Ask a business question —"><WorkTextarea
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) runAsk(question, department);
            }}
            rows={3}
            placeholder="Ask a business question — e.g. Where are we losing the most gross profit?"
            className={tc(
              theme,
              "w-full text-sm rounded border border-zinc-700 bg-black/30 px-3 py-2 text-white",
              "w-full text-sm rounded border border-zinc-300 bg-white px-3 py-2 text-black"
            )}
          /></WorkField>
          <div className="flex flex-wrap items-center gap-2">
            <WorkField label="Department"><WorkSelect
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className={tc(
                theme,
                "text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white",
                "text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black"
              )}
            >
              <option value={ALL_DEPARTMENTS}>All / whole business</option>
              {departments.map((d) => (
                <option key={d} value={d}>
                  {departmentLabel(d)}
                </option>
              ))}
            </WorkSelect></WorkField>
            <WorkButton type="submit"
              onClick={() => runAsk(question, department)}
              disabled={asking}
              className="text-xs px-4 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap ml-auto"
            >
              {asking ? "Consulting…" : "✨ Ask"}
            </WorkButton>
          </div>
        </div>

        {/* Suggested starter questions */}
        {starters.length > 0 && (
          <div className="mt-3">
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Suggested Questions</div>
            <div className="flex flex-wrap gap-1.5">
              {starters.map((q) => (
                <WorkButton type="submit"
                  key={q}
                  onClick={() => handleStarter(q)}
                  disabled={asking}
                  className={tc(
                    theme,
                    "text-xs px-2.5 py-1 rounded-full border border-zinc-700 bg-black/20 text-zinc-300 hover:text-white disabled:opacity-50",
                    "text-xs px-2.5 py-1 rounded-full border border-zinc-300 bg-zinc-50 text-zinc-600 hover:text-black disabled:opacity-50"
                  )}
                >
                  {q}
                </WorkButton>
              ))}
            </div>
          </div>
        )}

        {askError && <div className="text-sm text-red-400 mt-3">{askError}</div>}
      </div>

      {/* Data-readiness strip */}
      <div className={tc(theme, "grid grid-cols-3 gap-2 px-4 py-3 border-b border-zinc-800", "grid grid-cols-3 gap-2 px-4 py-3 border-b border-zinc-200")}>
        {loading && <div className="col-span-3 text-sm text-zinc-500">Loading…</div>}
        {error && <div className="col-span-3 text-sm text-red-400">{error}</div>}
        {!loading && !error && dataSources && (
          <>
            <ReadinessPill
              theme={theme}
              label="Recommendations Feed"
              value={dataSources.readiness_recommendations_present ? `${dataSources.triggered_recommendation_count ?? 0} triggered` : "Not present"}
              ok={dataSources.readiness_recommendations_present}
            />
            <ReadinessPill
              theme={theme}
              label="Opportunity Sizing"
              value={dataSources.network_opportunity_present ? "Present" : "Not present"}
              ok={dataSources.network_opportunity_present}
            />
            <ReadinessPill
              theme={theme}
              label="Total Annualized Opportunity"
              value={money(dataSources.total_annualized_opportunity)}
              ok={(dataSources.total_annualized_opportunity ?? 0) > 0}
            />
          </>
        )}
      </div>

      {/* The four-part consulting answer */}
      <div className="p-4 space-y-3">
        {asking && !result && <div className="text-sm text-zinc-500">Composing your consultation…</div>}
        {result ? (
          <ConsultationAnswer theme={theme} result={result} />
        ) : (
          !asking && (
            <div className="text-sm text-zinc-500">
              Ask a whole-store question above, or scope it to a department, to get a four-part consulting
              answer — Analysis, Root Cause, Opportunity, and a concrete Action Plan.
            </div>
          )
        )}
      </div>

      {/* Recent consultations */}
      {recent.length > 0 && (
        <div className={tc(theme, "p-4 border-t border-zinc-800", "p-4 border-t border-zinc-200")}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Recent Consultations</div>
          <div className="space-y-1.5">
            {recent.map((c) => (
              <div key={c.id} className="flex items-start gap-2">
                <span
                  className="mt-1 h-2 w-2 rounded-full flex-shrink-0"
                  style={{ background: c.ai_generated ? RIBBON[1] : "#9CA3AF" }}
                />
                <div className="min-w-0">
                  <div className="text-xs text-zinc-300 break-words">{c.question ?? "—"}</div>
                  <div className="text-xs text-zinc-500">
                    {departmentLabel(c.department)}
                    <span className="text-zinc-600 ml-2">{fmt(c.created_at)}</span>
                    <span className="text-zinc-600 ml-2">{c.ai_generated ? "AI-phrased" : "fact-based"}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
