// Client for the AI Demo Platform (/public/demo/*, core/demo_mode.py). All public — the demo
// mints its own persona session. Only functional against a DEALEROS_DEMO tenant.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { getDemoSession, type DemoPersona, type DemoScenario, type DemoMode } from "@/lib/demoSession";

export type PersonasResponse = {
  enabled: boolean;
  personas: DemoPersona[];
  scenarios: DemoScenario[];
  modes: DemoMode[];
};

export type StartDemoResponse = {
  token: string;
  session_id: string;
  persona: DemoPersona;
  role: string;
  allowed_dashboards: string[];
  mode: DemoMode;
  scenarios: DemoScenario[];
  watermark: { label: string; session_id: string; started_at: string };
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && data.error)) {
    throw new Error((data && data.error) || "Demo backend unavailable.");
  }
  return data as T;
}

export function fetchDemoPersonas(): Promise<PersonasResponse> {
  return fetch(`${API_BASE}/public/demo/personas`).then(handle<PersonasResponse>);
}

export function startDemo(persona: string, mode: DemoMode, contact?: Record<string, string>, accessCode?: string): Promise<StartDemoResponse> {
  return fetch(`${API_BASE}/public/demo/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ persona, mode, contact: contact ?? null, access_code: accessCode ?? null }),
  }).then(handle<StartDemoResponse>);
}

// Ask the AI Demo Host a real question — routes through NXTDeal's own AI (/ai/chat),
// authenticated by the persona's demo token, so answers are grounded in the seeded data and
// come back with a suggested dashboard the host can auto-navigate to.
export type GuideAnswer = { response: string; suggested_dashboard?: string | null };

export function askDemoGuide(question: string): Promise<GuideAnswer> {
  return fetch(`${API_BASE}/ai/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question }),
  })
    .then((r) => r.json())
    .then((d) => {
      if (!d || d.error) throw new Error(d?.error || "No answer.");
      return { response: d.response ?? "", suggested_dashboard: d.suggested_dashboard ?? null };
    });
}

export type DemoSummary = {
  session_id: string;
  persona_label: string;
  interests: string[];
  intent: "low" | "medium" | "high";
  score: number;
  pages_viewed: number;
  questions_asked: number;
  recommendation: string;
  ctas: { kind: string; label: string; href: string }[];
};

export function fetchDemoSummary(sessionId: string): Promise<DemoSummary> {
  return fetch(`${API_BASE}/public/demo/summary/${encodeURIComponent(sessionId)}`, { headers: authHeaders() }).then(handle<DemoSummary>);
}

// Fire-and-forget analytics — never blocks or throws into the UI.
export function trackDemoEvent(kind: string, detail?: Record<string, unknown>) {
  const session = getDemoSession();
  if (!session) return;
  fetch(`${API_BASE}/public/demo/track`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ session_id: session.sessionId, kind, detail: detail ?? null }),
  }).catch(() => {});
}
