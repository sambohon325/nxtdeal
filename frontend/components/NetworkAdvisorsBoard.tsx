"use client";
import { WorkButton, WorkInput } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Network's "AI Advisors" item -- 5 real, department-specific Q&A advisors
// (Sales/Service/Parts/F&I/BHPH). Every answer is grounded strictly in this
// dealer's own real benchmark comparison, gap analysis, and curated playbook
// data (all already-real Intelligence Network modules) -- AI phrasing is
// optional polish over an always-real, topic-matched fallback answer, never
// load-bearing. Same visual template as ReadinessOverviewBoard.tsx's
// AiBusinessAnalystPanel, extended with a department picker since this
// capstone covers 5 distinct advisors rather than one dealership-wide one.
import { useEffect, useState } from "react";
import {
  getNetworkAdvisorsCatalog,
  askNetworkAdvisor,
  type AdvisorCatalogEntry,
  type AdvisorAnswer,
  type AdvisorDepartment,
} from "@/lib/networkAdvisors";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

type AskedQA = AdvisorAnswer & { id: number };

const SAMPLE_QUESTIONS: Record<AdvisorDepartment, string[]> = {
  sales: [
    "How are we doing compared to peers?",
    "What's our biggest opportunity gap?",
    "Why are we behind on that gap?",
    "What should we do about it?",
  ],
  service: [
    "How is our percentile rank?",
    "What gaps are trailing peer average?",
    "What's causing our technician utilization?",
    "Any active playbooks for this department?",
  ],
  parts: [
    "How are we doing on obsolete inventory?",
    "What's the biggest opportunity here?",
    "Why is this gap open?",
    "What should we fix first?",
  ],
  fi: [
    "How does our F&I reserve income compare?",
    "What's trailing peer average?",
    "Why is menu penetration behind?",
    "What playbook should we run?",
  ],
  bhph: [
    "How is our loan portfolio doing?",
    "What's our delinquency/repo/charge-off gap?",
    "Why are we behind on this?",
    "What should we do about collections?",
  ],
};

const DEPARTMENT_ORDER: AdvisorDepartment[] = ["sales", "service", "parts", "fi", "bhph"];

function AdvisorTabs({
  theme,
  advisors,
  active,
  onSelect,
}: {
  theme: Theme;
  advisors: AdvisorCatalogEntry[];
  active: AdvisorDepartment;
  onSelect: (d: AdvisorDepartment) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {advisors.map((a) => (
        <WorkButton type="submit"
          key={a.department}
          onClick={() => onSelect(a.department)}
          className={`px-2.5 py-1 rounded-full text-xs font-medium transition ${
            active === a.department
              ? "bg-zinc-200 text-black"
              : tc(theme, "bg-zinc-800 text-zinc-300 hover:bg-zinc-700", "bg-zinc-100 text-zinc-600 hover:bg-zinc-200")
          }`}
        >
          {a.title}
        </WorkButton>
      ))}
    </div>
  );
}

export function NetworkAdvisorsBoard({ theme }: { theme: Theme }) {
  const [advisors, setAdvisors] = useState<AdvisorCatalogEntry[]>([]);
  const [active, setActive] = useState<AdvisorDepartment>("sales");
  const [loadingCatalog, setLoadingCatalog] = useState(true);
  const [catalogError, setCatalogError] = useState<string | null>(null);

  const [question, setQuestion] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [history, setHistory] = useState<AskedQA[]>([]);

  useEffect(() => {
    getNetworkAdvisorsCatalog()
      .then((res) => setAdvisors(res.advisors))
      .catch((e) => setCatalogError(e instanceof Error ? e.message : "Unable to load the advisor catalog."))
      .finally(() => setLoadingCatalog(false));
  }, []);

  function handleAsk(q?: string) {
    const text = (q ?? question).trim();
    if (!text || asking) return;
    setAsking(true);
    setAskError(null);
    askNetworkAdvisor(active, text)
      .then((res) => {
        setHistory((prev) => [{ ...res, id: Date.now() }, ...prev]);
        setQuestion("");
      })
      .catch((e) => setAskError(e instanceof Error ? e.message : "Unable to reach the AI Advisor."))
      .finally(() => setAsking(false));
  }

  const visibleHistory = history.filter((qa) => qa.department === active);
  const orderedAdvisors = advisors.length
    ? advisors
    : DEPARTMENT_ORDER.map((d) => ({ department: d, title: d } as AdvisorCatalogEntry));

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">AI Advisors</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          5 real, department-specific advisors -- every answer is grounded strictly in this dealer&apos;s own real
          benchmark comparison, gap analysis, and curated playbook data. The optional AI phrasing may never invent a
          number not already present in that real data.
        </div>
      </div>

      {catalogError && <div className="mx-4 mt-2 text-xs text-red-400">{catalogError}</div>}

      <div className="flex-1 p-4 space-y-4">
        {loadingCatalog ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <AdvisorTabs theme={theme} advisors={orderedAdvisors} active={active} onSelect={setActive} />

            <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
              <div className="text-sm font-brand font-semibold mb-1">
                {orderedAdvisors.find((a) => a.department === active)?.title ?? active} Advisor
              </div>
              <div className="text-xs text-zinc-500 mb-3">
                Ask a plain-English question about this department.
              </div>

              <div className="flex gap-2">
                <WorkField label="Question"><WorkInput
                  value={question}
                  onChange={(e) => setQuestion(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleAsk();
                  }}
                  placeholder="e.g. Why are we behind on this gap?"
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
                {(SAMPLE_QUESTIONS[active] ?? []).map((q) => (
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

              {askError && <div className="text-xs text-red-400 mt-2">{askError}</div>}

              {visibleHistory.length > 0 ? (
                <div className="mt-3 space-y-2">
                  {visibleHistory.map((qa) => (
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
              ) : (
                <div className="text-xs text-zinc-600 mt-3">
                  No questions asked yet for this department -- try one of the suggestions above.
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}
