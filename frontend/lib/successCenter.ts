// Success Center -- NXTDeal-INTERNAL client-success / account-management platform
// (core/success_center.py). NOT a dealership department: this is the client the
// NXTDeal success team runs to manage its portfolio of DEALER accounts that use
// NXTDeal -- Quarterly Business Reviews (QBRs), success objectives, active
// initiatives, and open recommendations, one record set per dealer account, plus
// an isolated-OpenAI-backed QBR-insights generator with an honest non-AI fallback.
// Backed by 8 dedicated /success-center/* routes (api/routers/success_center.py),
// restricted server-side to ADMIN + OPERATIONS.
//
// Mirrors lib/customerJourney.ts's client pattern exactly (API_BASE + authHeaders
// + a shared handle<T> helper, one thin function per route).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// Ordered priority buckets -- must stay in step with core/success_center.py's
// PRIORITIES list.
export const REC_PRIORITIES = ["high", "medium", "low"] as const;
export type RecPriority = (typeof REC_PRIORITIES)[number];

// Ordered initiative statuses -- must stay in step with core/success_center.py's
// INITIATIVE_STATUSES list.
export const INITIATIVE_STATUSES = ["planned", "in_progress", "completed", "on_hold"] as const;
export type InitiativeStatus = (typeof INITIATIVE_STATUSES)[number];

// A managed dealer account brief (core/success_center.py's _dealer_brief).
export type Dealer = {
  dealer_id: string;
  name: string | null;
  notes: string;
  created_at: string | null;
};

// A success objective record (_brief of a SuccessObjective entity).
export type Objective = {
  id: string;
  dealer_id: string;
  title: string;
  target: string;
  created_at: string;
};

// An active initiative record (_brief of a SuccessInitiative entity).
export type Initiative = {
  id: string;
  dealer_id: string;
  title: string;
  status: string;
  created_at: string;
};

// A QBR record (_brief of a SuccessQBR entity).
export type QBR = {
  id: string;
  dealer_id: string;
  period: string;
  notes: string;
  created_at: string;
};

// A recommendation record (_brief of a SuccessRecommendation entity). resolved_at
// / resolved_by are null while the recommendation is still open.
export type Recommendation = {
  id: string;
  dealer_id: string;
  text: string;
  priority: string;
  status: string;
  created_at: string;
  resolved_at: string | null;
  resolved_by: string | null;
};

// The live-computed account-health overview for one dealer (get_success_overview).
// open_recommendations_by_priority and initiatives_by_status are seeded to 0 for
// every bucket even when empty, so callers can index them defensively.
export type DealerOverview = {
  dealer_id: string;
  name: string | null;
  open_recommendations_by_priority: Record<string, number>;
  open_recommendations_total: number;
  objectives: Objective[];
  objectives_count: number;
  initiatives_by_status: Record<string, number>;
  initiatives_count: number;
  latest_qbr: QBR | null;
  upcoming_qbr: QBR | null;
  qbr_count: number;
};

// QBR-insights AI result (generate_qbr_insights). On success ai_generated is true;
// on the kill-switched/failure fallback ai_generated is false and one of
// disabled/fallback_reason explains why. Same disabled/fallback shape as
// lib/customerJourney.ts's JourneyRecommendation.
export type QbrInsights = {
  summary: string;
  talking_points: string[];
  suggested_focus: string;
  ai_generated: boolean;
  disabled?: boolean;
  fallback_reason?: string;
  error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function listDealers(): Promise<Dealer[]> {
  return fetch(`${API_BASE}/success-center/dealers`, {
    headers: { ...authHeaders() },
  }).then(handle<Dealer[]>);
}

export function getDealerOverview(dealerId: string): Promise<DealerOverview> {
  return fetch(`${API_BASE}/success-center/dealer/${encodeURIComponent(dealerId)}`, {
    headers: { ...authHeaders() },
  }).then(handle<DealerOverview>);
}

export function createQbr(dealerId: string, period: string, notes?: string): Promise<QBR> {
  return fetch(`${API_BASE}/success-center/dealer/${encodeURIComponent(dealerId)}/qbr`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ period, notes: notes ?? "" }),
  }).then(handle<QBR>);
}

export function addObjective(dealerId: string, title: string, target?: string): Promise<Objective> {
  return fetch(`${API_BASE}/success-center/dealer/${encodeURIComponent(dealerId)}/objective`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ title, target: target ?? "" }),
  }).then(handle<Objective>);
}

export function addInitiative(dealerId: string, title: string, status?: string): Promise<Initiative> {
  return fetch(`${API_BASE}/success-center/dealer/${encodeURIComponent(dealerId)}/initiative`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ title, status: status ?? "planned" }),
  }).then(handle<Initiative>);
}

export function addRecommendation(dealerId: string, text: string, priority?: string): Promise<Recommendation> {
  return fetch(`${API_BASE}/success-center/dealer/${encodeURIComponent(dealerId)}/recommendation`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ text, priority: priority ?? "medium" }),
  }).then(handle<Recommendation>);
}

export function resolveRecommendation(dealerId: string, recId: string): Promise<Recommendation> {
  return fetch(
    `${API_BASE}/success-center/dealer/${encodeURIComponent(dealerId)}/recommendation/${encodeURIComponent(recId)}/resolve`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
    }
  ).then(handle<Recommendation>);
}

export function generateQbrInsights(dealerId: string): Promise<QbrInsights> {
  return fetch(`${API_BASE}/success-center/dealer/${encodeURIComponent(dealerId)}/qbr-insights`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  }).then(handle<QbrInsights>);
}
