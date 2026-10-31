// AI Spend Governor client (Freemium roadmap, Phase 5). Backend: core/ai_spend.py / api routes
// /ai-spend/*. ADMIN-only. The dealer brings their own AI key (model-agnostic), sets a per-user
// monthly AI-action limit so one user can't burn the whole key's budget, and sees an aggregate
// consumption view. Metering is by AI ACTIONS (no token/cost metering exists yet) — surfaced
// honestly in the UI.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type CustomEndpoint = { base_url: string; model: string; auth_header: string; notes: string } | null;

export type AiSpendPolicy = {
  id: string;
  provider: string;
  byo_key_configured: boolean;
  per_user_monthly_limit: number | null;
  user_overrides: Record<string, number | null>;
  ai_enabled: boolean;
  ai_off_users: string[];
  custom_endpoint: CustomEndpoint;
  managed_rate_per_action: number;
  managed_ai_available: boolean;
  updated_by: string | null;
  updated_at: string | null;
};

export type MyAiStatus = {
  ai_enabled: boolean;
  dealer_ai_enabled: boolean;
  user_ai_off: boolean;
};

export type AiSpendUser = {
  user_id: string;
  used: number;
  limit: number | null;
  remaining: number | null;
  over_limit: boolean;
  by_feature: Record<string, number>;
};

export type ManagedBilling = {
  provider: string;
  billable_actions: number;
  rate_per_action: number;
  estimated_charge: number;
  note: string;
} | null;

export type AiSpendOverview = {
  period: string;
  provider: string;
  byo_key_configured: boolean;
  per_user_monthly_limit: number | null;
  ai_enabled: boolean;
  ai_off_user_count: number;
  total_ai_actions: number;
  attributed_actions: number;
  unattributed_actions: number;
  distinct_users: number;
  users: AiSpendUser[];
  metering_basis: string;
  managed_billing: ManagedBilling;
};

// "dealeros" = our hosted, usage-billed AI (paid add-on). "custom" = homegrown/any-API endpoint.
export const AI_PROVIDERS = ["dealeros", "openai", "gemini", "anthropic", "azure_openai", "local", "custom", "other"] as const;
export const MANAGED_PROVIDER = "dealeros";

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

export function getAiSpendPolicy(): Promise<AiSpendPolicy> {
  return get<AiSpendPolicy>("/ai-spend/policy");
}
export function getAiSpendOverview(period?: string): Promise<AiSpendOverview> {
  return get<AiSpendOverview>(`/ai-spend/overview${period ? `?period=${encodeURIComponent(period)}` : ""}`);
}
export function setAiSpendProvider(provider: string, byoKeyConfigured?: boolean): Promise<AiSpendPolicy> {
  return post<AiSpendPolicy>("/ai-spend/provider", { provider, byo_key_configured: byoKeyConfigured });
}
export function setAiSpendDefaultLimit(limit: number | null): Promise<AiSpendPolicy> {
  return post<AiSpendPolicy>("/ai-spend/limit", { limit });
}
export function setAiSpendUserLimit(userId: string, limit: number | null): Promise<AiSpendPolicy> {
  return post<AiSpendPolicy>("/ai-spend/user-limit", { user_id: userId, limit });
}

// Dealer-level master AI switch (admin).
export function setDealerAiEnabled(enabled: boolean): Promise<AiSpendPolicy> {
  return post<AiSpendPolicy>("/ai-spend/ai-enabled", { enabled });
}
// Homegrown / any-API endpoint (admin). Pass null to clear.
export function setCustomEndpoint(cfg: { base_url?: string; model?: string; auth_header?: string; notes?: string } | null): Promise<AiSpendPolicy> {
  return post<AiSpendPolicy>("/ai-spend/custom-endpoint", cfg === null ? { clear: true } : cfg);
}
// Usage-based price per AI action for the managed provider (admin).
export function setManagedRate(rate: number): Promise<AiSpendPolicy> {
  return post<AiSpendPolicy>("/ai-spend/managed-rate", { rate });
}

// --- Per-user (self) AI on/off ---
export function getMyAiStatus(): Promise<MyAiStatus> {
  return get<MyAiStatus>("/ai-spend/my-status");
}
export function setMyAi(enabled: boolean): Promise<MyAiStatus> {
  return post<MyAiStatus>("/ai-spend/my-ai", { enabled });
}
