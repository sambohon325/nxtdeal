// Administration's "AI Management" item (Administration Control Center rebuild,
// continued). Backend: core/ai_management.py / _api.py. A real catalog of every
// OpenAI-backed feature in this codebase, each with a real per-feature kill switch
// (backed by core/system_config.py's FEATURE_FLAGS, actually checked by each
// feature's own consumer function) and honest, in-memory call-attempt counters.
// ADMIN/OPERATIONS-only throughout, same convention as every other bespoke
// Administration board.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type AiFeatureStats = {
  attempted: number;
  succeeded: number;
  fell_back: number;
  blocked: number;
  last_outcome: string | null;
  last_at: string | null;
  last_detail?: string | null;
};

export type AiFeatureCatalogEntry = {
  key: string;
  flag: string;
  name: string;
  module: string;
  functions: string[];
  description: string;
  has_tool_calling_access: boolean;
  fallback_exists: boolean;
  wired_route: boolean;
  route_note: string;
};

export type AiFeature = AiFeatureCatalogEntry & {
  enabled: boolean;
  stats: AiFeatureStats;
};

export type AiManagementOverview = {
  features: AiFeature[];
  summary: {
    total_features: number;
    enabled_count: number;
    disabled_count: number;
    features_with_recorded_activity: number;
    features_missing_a_real_route: number;
  };
  sandbox_network_note: string;
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

export function getAiManagementOverview(): Promise<AiManagementOverview> {
  return get("/ai-management/overview");
}

export function getAiFeatureCatalog(): Promise<{ features: AiFeatureCatalogEntry[] }> {
  return get("/ai-management/catalog");
}

export function getAiCallStats(featureKey?: string): Promise<{ stats: Record<string, AiFeatureStats> }> {
  const qs = featureKey ? `?feature_key=${encodeURIComponent(featureKey)}` : "";
  return get(`/ai-management/stats${qs}`);
}

export function setAiFeatureEnabled(
  featureKey: string,
  enabled: boolean
): Promise<{ feature_key: string; name: string; flag: string; enabled: boolean }> {
  return post(`/ai-management/features/${encodeURIComponent(featureKey)}`, { enabled });
}
