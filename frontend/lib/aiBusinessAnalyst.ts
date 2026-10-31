// Readiness' "AI Business Analyst" capstone -- an executive asks a natural-language
// question and gets a real, factual answer composed from Business Health/Enterprise
// Risk Center/Recommendations/Forecasts data. Backend: core/ai_business_analyst.py /
// _api.py -- an isolated OpenAI call that may only phrase an answer from a real,
// pre-computed FACTS block (never invent a number); its fallback (used whenever
// OpenAI is unreachable, which is every call in this sandbox) is a real
// topic-matching formatter over that same FACTS block, not a generic "AI
// unavailable" message. Open to every real role.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type BusinessAnalystAnswer = {
  question: string;
  answer: string;
  ai_generated: boolean;
  note?: string;
  fallback_answer?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function askBusinessAnalyst(question: string): Promise<BusinessAnalystAnswer> {
  return fetch(`${API_BASE}/ai-business-analyst/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ question }),
  }).then(handle<BusinessAnalystAnswer>);
}
