// Generalized AI model-selector client for all companion apps (2026-10-24).
// Backend: core/ai_config.py + api/app.py routes /ai-config/app.
//
// Each authenticated user can configure how AI runs in a given app:
//   - off          -> turn AI off for themselves
//   - byok         -> bring their own provider key (raw key never stored on the server)
//   - on_device    -> prefer the native on-device model (routine tasks only)
//   - dealer       -> use the dealership's managed AI provider
//
// Staff apps (salesapp, reception, serviceops) use this with their staff session.
// Customer apps (showroom, mygarage, kiosk) are dealer-managed only -- no per-user config.
// MySales personal delegates to its own Hub-based assistant connection flow.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export const BYOK_PROVIDERS = ["openai", "anthropic", "gemini", "azure_openai", "local", "custom", "other"] as const;

export type AiConfigByok = { provider: string | null; key_masked: string | null; configured: boolean };
export type AiConfigRouting = { on_device_when_available: boolean; routine_tier: string; premium_tier: string };
export type AiConfigResponse = {
  user_id: string;
  app_slug: string;
  ai_enabled: boolean;
  byok: AiConfigByok;
  routing: AiConfigRouting;
  updated_at: string | null;
};

export type RoutingDecision = {
  source: "off" | "byok" | "on_device" | "dealer";
  provider?: string;
  model: string;
  task_kind: string;
  app_slug: string;
  reason: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error(
      typeof data?.detail === "string"
        ? data.detail
        : (data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.",
    );
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

// Query params for the app slug (defaults to "mysales" on the backend).
function appQuery(app: string): string {
  return `?app=${encodeURIComponent(app)}`;
}

export function getAiConfig(app: string): Promise<AiConfigResponse> {
  return get<AiConfigResponse>(`/ai-config/app${appQuery(app)}`);
}

export function setAiEnabled(app: string, enabled: boolean): Promise<AiConfigResponse> {
  return post<AiConfigResponse>(`/ai-config/app/enabled`, { app, enabled });
}

export function setAiByok(app: string, provider: string, apiKey: string): Promise<AiConfigResponse> {
  return post<AiConfigResponse>(`/ai-config/app/byok`, { app, provider, api_key: apiKey });
}

export function clearAiByok(app: string): Promise<AiConfigResponse> {
  return post<AiConfigResponse>(`/ai-config/app/byok/clear`, { app });
}

export function setAiRouting(app: string, routing: {
  on_device_when_available?: boolean;
  routine_tier?: string;
  premium_tier?: string;
}): Promise<AiConfigResponse> {
  return post<AiConfigResponse>(`/ai-config/app/routing`, { app, ...routing });
}

export function resolveAiModel(app: string, task: "routine" | "premium" = "routine"): Promise<RoutingDecision> {
  return get<RoutingDecision>(`/ai-config/app/resolve${appQuery(app)}&task=${encodeURIComponent(task)}`);
}
