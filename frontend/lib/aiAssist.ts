// Inline AI Text-Assist client (2026-07-23) -- talks to backend/api/routers/
// ai_assist.py's single POST /ai-assist route (core/ai_assist.py's assist_text:
// one generic generate/rewrite/shorten/expand/retone/grammar transform reused by
// every text field across NXTDeal). Mirrors lib/accessories.ts's client shape
// exactly (API_BASE + authHeaders + a shared handle<T> helper, one thin call).
//
// The backend never returns a blank: when the OpenAI feature is killed or a call
// fails it falls back to a real rule-based transform and sets ai_generated:false
// with a human `note`. This client surfaces that note verbatim so the UI can show
// "offline draft" honestly rather than pretending it was AI-written.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// Must stay in step with core/ai_assist.py's ACTIONS tuple.
export type AiAssistAction =
  | "generate"
  | "rewrite"
  | "shorten"
  | "expand"
  | "retone"
  | "grammar";

// Must stay in step with core/system_config.py's BRAND_TONES (the same fixed
// vocabulary the AI Management brand-settings picker offers). A caller that omits
// `tone` lets the backend fall back to this dealer's saved brand tone.
export const AI_ASSIST_TONES = ["Professional", "High Energy", "Direct", "Friendly"] as const;
export type AiAssistTone = (typeof AI_ASSIST_TONES)[number];

export type AiAssistResult = {
  result: string;
  action: AiAssistAction;
  ai_generated: boolean;
  // Present only on the deterministic-fallback path (feature killed / call
  // failed) -- an honest one-line explanation, never a blank.
  note?: string;
  // Present only on a bad request (unknown action / empty text for a transform).
  error?: string;
};

export type AiAssistOptions = {
  tone?: AiAssistTone | null;
  // For `generate`, describes what to write. For the transform actions, extra
  // guidance appended to the instruction (e.g. the field label or campaign goal).
  context?: string | null;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error(
      (data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend."
    );
  }
  return data as T;
}

// One assist call. `text` is the input to transform (ignored for `generate`,
// which writes from `context`). Returns the full result including the honest
// ai_generated flag + optional fallback note.
export function assist(
  text: string,
  action: AiAssistAction,
  options: AiAssistOptions = {}
): Promise<AiAssistResult> {
  return fetch(`${API_BASE}/ai-assist`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      text: text ?? "",
      action,
      tone: options.tone ?? null,
      context: options.context ?? null,
    }),
  }).then(handle<AiAssistResult>);
}
