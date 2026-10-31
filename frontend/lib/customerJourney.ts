// Customer Journey Engine -- core/customer_journey.py's graph-native lifecycle
// stage tracking (Awareness -> Lead -> Appointment -> Sale -> Service ->
// Loyalty -> Repeat), stored directly as attributes on the Customer entity,
// plus slice 2's isolated-OpenAI-backed next-best-action recommendation with an
// honest non-AI fallback. Backed by 6 dedicated /customer-journey/* routes
// (api/routers/customer_journey.py), not the generic /menu/data dispatch --
// same "bespoke board bypasses /menu/data for its own extra views" precedent
// lib/communicationsHub.ts and every other rebuild in this codebase established.
// Mirrors lib/communicationsHub.ts's client pattern exactly (API_BASE + authHeaders
// + a shared handle<T> helper, one thin function per route).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// Ordered lifecycle stages -- must stay in step with core/customer_journey.py's
// STAGES list (order is load-bearing: advance steps to the next stage in order).
export const JOURNEY_STAGES = [
  "AWARENESS",
  "LEAD",
  "APPOINTMENT",
  "SALE",
  "SERVICE",
  "LOYALTY",
  "REPEAT",
] as const;
export type JourneyStage = (typeof JOURNEY_STAGES)[number];

export type JourneyHistoryEntry = {
  stage: string;
  timestamp: string;
  note: string;
};

export type CustomerJourney = {
  customer_id: string;
  name: string | null;
  journey_stage: string | null;
  journey_history: JourneyHistoryEntry[];
};

export type JourneyOverview = {
  stages: string[];
  counts_by_stage: Record<string, number>;
  total_customers_in_journey: number;
};

export type JourneyRecommendation = {
  recommended_action: string;
  reason: string;
  suggested_timing: string;
  suggested_campaign: string;
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

export function getJourneyOverview(): Promise<JourneyOverview> {
  return fetch(`${API_BASE}/customer-journey/overview`, {
    headers: { ...authHeaders() },
  }).then(handle<JourneyOverview>);
}

export function getCustomerJourney(customerId: string): Promise<CustomerJourney> {
  return fetch(`${API_BASE}/customer-journey/customer/${encodeURIComponent(customerId)}`, {
    headers: { ...authHeaders() },
  }).then(handle<CustomerJourney>);
}

export function advanceJourney(customerId: string, note?: string): Promise<CustomerJourney> {
  return fetch(`${API_BASE}/customer-journey/customer/${encodeURIComponent(customerId)}/advance`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ note: note ?? "" }),
  }).then(handle<CustomerJourney>);
}

export function setJourneyStage(customerId: string, stage: string, note?: string): Promise<CustomerJourney> {
  return fetch(`${API_BASE}/customer-journey/customer/${encodeURIComponent(customerId)}/stage`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ stage, note: note ?? "" }),
  }).then(handle<CustomerJourney>);
}

export function listCustomersInStage(stage: string): Promise<CustomerJourney[]> {
  return fetch(`${API_BASE}/customer-journey/stage/${encodeURIComponent(stage)}`, {
    headers: { ...authHeaders() },
  }).then(handle<CustomerJourney[]>);
}

export function generateJourneyRecommendation(customerId: string): Promise<JourneyRecommendation> {
  return fetch(`${API_BASE}/customer-journey/customer/${encodeURIComponent(customerId)}/recommendation`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  }).then(handle<JourneyRecommendation>);
}
