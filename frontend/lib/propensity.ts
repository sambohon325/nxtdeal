// Buy-Propensity client (Phase 1, 2026-07-25): the 0-100 buy-propensity score, ranking
// leaderboard, AI outreach drafts, and third-party enrichment. Talks to
// backend/api/routers/buy_propensity.py (/propensity/*, /enrichment/*).
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type PropensityFactor = { label: string; points: number; detail: string };

export type PropensityScore = {
  entity_id: string;
  entity_type: string;
  name: string;
  score: number;
  tier: "hot" | "warm" | "cool";
  factors: PropensityFactor[];
  recommended_action: string;
  basis: string;
};

export type RankRow = {
  entity_id: string;
  entity_type: string;
  name: string;
  score: number;
  tier: "hot" | "warm" | "cool";
  top_factor: string | null;
};

export type RankResult = {
  segment: string;
  count: number;
  by_tier: Record<string, number>;
  ranked: RankRow[];
};

export type OutreachDraft = {
  entity_id: string;
  channel: string;
  subject: string | null;
  body: string;
  based_on: string[];
  score: number;
  tier: string;
};

export type EnrichmentResult = {
  customer_id: string;
  provider: string | null;
  mode: "live" | "simulated";
  appended_count: number;
  appended: Record<string, unknown>;
  note?: string;
};

export async function rankPropensity(segment: "customers" | "leads" | "all" = "customers", limit = 50): Promise<RankResult> {
  const res = await fetch(`${API_BASE}/propensity/rank?segment=${segment}&limit=${limit}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getPropensity(entityId: string): Promise<PropensityScore> {
  const res = await fetch(`${API_BASE}/propensity/${encodeURIComponent(entityId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function draftOutreach(entityId: string, channel: "email" | "sms" = "email"): Promise<OutreachDraft> {
  const res = await fetch(`${API_BASE}/propensity/${encodeURIComponent(entityId)}/outreach`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ channel }),
  });
  return handle(res);
}

export async function enrichCustomer(customerId: string): Promise<EnrichmentResult> {
  const res = await fetch(`${API_BASE}/enrichment/${encodeURIComponent(customerId)}`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}
