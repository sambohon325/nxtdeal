// AI Consulting Engine -- core/consulting_engine.py's four-part strategic
// consultation (Analysis -> Root Cause -> Opportunity -> Action Plan) that
// COMPOSES NXTDeal's own already-real analysis (ai_business_analyst's
// whole-business facts or network_advisors' per-department facts, plus the real
// readiness recommendation feed and the dollar-denominated opportunity sizing)
// into a single consulting answer, with an isolated-OpenAI phrasing pass over an
// always-real, fact-grounded fallback (ai_generated=false). Backed by 2
// dedicated /consulting-engine/* routes (api/routers/consulting_engine.py), not
// the generic /menu/data dispatch -- same "bespoke board bypasses /menu/data for
// its own extra views" precedent lib/customerJourney.ts and every other rebuild
// in this codebase established.
// Mirrors lib/customerJourney.ts's client pattern exactly (API_BASE + authHeaders
// + a shared handle<T> helper, one thin function per route).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// The four-part consultation returned by POST /consulting-engine/ask. Every
// field maps 1:1 to core/consulting_engine.py's run_consultation result dict;
// `note` is present only on the fallback/disabled paths.
export type Consultation = {
  question: string;
  department: string | null;
  analysis: string;
  root_cause: string;
  opportunity: string;
  action_plan: string[];
  confidence_note: string;
  sources: string[];
  ai_generated: boolean;
  note?: string;
};

// One row in overview.recent_consultations -- the lightweight graph-native
// Consultation breadcrumb (id prefix CONSULT) list_recent_consultations() emits.
// Every attribute is read via Entity.attributes.get(...), so each may be absent.
export type RecentConsultation = {
  id: string;
  question: string | null;
  department: string | null;
  ai_generated: boolean | null;
  created_at: string | null;
};

export type ConsultingDataSources = {
  readiness_recommendations_present: boolean;
  triggered_recommendation_count: number | null;
  network_opportunity_present: boolean;
  total_annualized_opportunity: number | null;
};

export type ConsultingOverview = {
  starter_questions: string[];
  departments_available: string[];
  data_sources: ConsultingDataSources;
  recent_consultations: RecentConsultation[];
  note: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function getConsultingOverview(): Promise<ConsultingOverview> {
  return fetch(`${API_BASE}/consulting-engine/overview`, {
    headers: { ...authHeaders() },
  }).then(handle<ConsultingOverview>);
}

export function askConsultation(question: string, department?: string | null): Promise<Consultation> {
  return fetch(`${API_BASE}/consulting-engine/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question, department: department ?? null }),
  }).then(handle<Consultation>);
}
