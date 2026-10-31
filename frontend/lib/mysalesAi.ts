// MySales personal AI config client (Freemium Phase 5+, 2026-08-03). Backend: core/mysales_ai.py.
// Per-rep (self-scoped) AI setup for MySales: personal on/off, bring-your-own-key (the raw key is
// never stored — only a masked hint), and tiered routing (route routine tasks to a cheap tier,
// premium tasks to a high-end model, prefer on-device when the native app supports it). Uses the
// standard bearer session (MySales mirrors it), so these are the caller's own settings.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export const BYOK_PROVIDERS = ["openai", "anthropic", "gemini", "azure_openai", "other"] as const;

export type MySalesByok = { provider: string | null; key_masked: string | null; configured: boolean };
export type MySalesRouting = { on_device_when_available: boolean; routine_tier: string; premium_tier: string };
export type MySalesAiConfig = {
  rep_id: string;
  ai_enabled: boolean;
  byok: MySalesByok;
  routing: MySalesRouting;
  updated_at: string | null;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}
function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}
function post<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function getMySalesAiConfig(): Promise<MySalesAiConfig> {
  return get<MySalesAiConfig>("/mysales/ai-config");
}
export function setMySalesAiEnabled(enabled: boolean): Promise<MySalesAiConfig> {
  return post<MySalesAiConfig>("/mysales/ai-config/enabled", { enabled });
}
export function setMySalesByok(provider: string, apiKey: string): Promise<MySalesAiConfig> {
  return post<MySalesAiConfig>("/mysales/ai-config/byok", { provider, api_key: apiKey });
}
export function clearMySalesByok(): Promise<MySalesAiConfig> {
  return post<MySalesAiConfig>("/mysales/ai-config/byok/clear");
}
export function setMySalesRouting(routing: {
  on_device_when_available?: boolean;
  routine_tier?: string;
  premium_tier?: string;
}): Promise<MySalesAiConfig> {
  return post<MySalesAiConfig>("/mysales/ai-config/routing", routing);
}
