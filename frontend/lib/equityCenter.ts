// Equity Center -- core/equity_center.py's graph-native equity / trade-up
// opportunity engine (equity mining, lease-maturity trade-up, and recorded
// upgrade offers), plus an isolated-OpenAI-backed AI upgrade-offer draft with an
// honest non-AI fallback. Backed by 5 dedicated /equity-center/* routes
// (api/routers/equity_center.py), not the generic /menu/data dispatch -- the
// same "bespoke board bypasses /menu/data for its own extra views" precedent
// lib/customerJourney.ts and every other rebuild in this codebase established.
// Mirrors lib/customerJourney.ts's client pattern exactly (API_BASE + authHeaders
// + a shared handle<T> helper, one thin function per route).
//
// EVERY dollar figure this module returns is an ESTIMATE (is_estimated=True on
// the backend, with a real basis/disclaimer) -- there is no lender payoff API
// and no valuation vendor connected. The disclaimer strings are surfaced in the
// UI, never presented as a real payoff or a binding appraisal.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// Equity status buckets -- must stay in step with core/equity_center.py's
// POSITIVE / NEGATIVE / NEAR_EVEN / UNKNOWN constants.
export const EQUITY_STATUSES = ["positive", "negative", "near_even", "unknown"] as const;
export type EquityStatus = (typeof EQUITY_STATUSES)[number];

// GET /equity-center/overview -- live-computed counts across every customer plus
// the total estimated dollar opportunity (sum of every positive estimated equity).
export type EquityOverview = {
  positive_equity: number;
  negative_equity: number;
  near_even: number;
  lease_maturing_soon: number;
  upgrade_ready: number;
  customers_with_estimates: number;
  total_customers: number;
  total_estimated_opportunity: number;
  lease_maturity_horizon_days: number;
  is_estimated: boolean;
  basis: string;
  disclaimer: string;
};

// GET /equity-center/customer/{customer_id} -- one customer's estimated equity
// position. equity_amount / status are null / "unknown" when the desk hasn't
// entered both an estimated payoff and an estimated value (nothing fabricated).
export type EquityPosition = {
  customer_id: string;
  name: string | null;
  estimated_payoff: number | null;
  estimated_value: number | null;
  equity_amount: number | null;
  status: string;
  lease_maturity_date: string | null;
  days_to_lease_maturity: number | null;
  lease_maturing_soon: boolean;
  has_estimate_inputs: boolean;
  is_estimated: boolean;
  basis: string;
  disclaimer: string;
  near_even_threshold: number;
  lease_maturity_horizon_days: number;
};

// GET /equity-center/opportunities -- one row per real upgrade candidate
// (positive estimated equity AND/OR a loan/lease maturing within horizon).
export type EquityOpportunity = {
  customer_id: string;
  name: string | null;
  status: string;
  equity_amount: number | null;
  lease_maturity_date: string | null;
  days_to_lease_maturity: number | null;
  lease_maturing_soon: boolean;
  upgrade_ready: boolean;
  reason: string;
  is_estimated: boolean;
  basis: string;
  disclaimer: string;
};

// POST /equity-center/customer/{customer_id}/offer -- the recorded, timestamped
// upgrade offer appended to the customer's graph-native equity_upgrade_offers
// list. Snapshots the estimated position at offer time.
export type RecordedOffer = {
  id: string;
  customer_id: string;
  name: string | null;
  created_at: string;
  note: string;
  equity_amount: number | null;
  status: string;
  estimated_payoff: number | null;
  estimated_value: number | null;
  lease_maturity_date: string | null;
  is_estimated: boolean;
  basis: string;
  disclaimer: string;
};

// POST /equity-center/customer/{customer_id}/upgrade-offer -- the AI upgrade-offer
// draft. ai_generated=true on a real OpenAI success; on a disabled kill switch or
// any failure it returns an honest non-AI fallback (ai_generated=false, plus
// disabled or fallback_reason). Mirrors lib/customerJourney.ts's
// JourneyRecommendation optional-flag shape.
export type UpgradeOffer = {
  headline: string;
  message: string;
  suggested_next_step: string;
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

export function getEquityOverview(): Promise<EquityOverview> {
  return fetch(`${API_BASE}/equity-center/overview`, {
    headers: { ...authHeaders() },
  }).then(handle<EquityOverview>);
}

export function getOpportunities(horizonDays?: number): Promise<EquityOpportunity[]> {
  const query = typeof horizonDays === "number" ? `?horizon_days=${encodeURIComponent(String(horizonDays))}` : "";
  return fetch(`${API_BASE}/equity-center/opportunities${query}`, {
    headers: { ...authHeaders() },
  }).then(handle<EquityOpportunity[]>);
}

export function getCustomerEquity(customerId: string): Promise<EquityPosition> {
  return fetch(`${API_BASE}/equity-center/customer/${encodeURIComponent(customerId)}`, {
    headers: { ...authHeaders() },
  }).then(handle<EquityPosition>);
}

export function createOffer(customerId: string, note?: string): Promise<RecordedOffer> {
  return fetch(`${API_BASE}/equity-center/customer/${encodeURIComponent(customerId)}/offer`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ note: note ?? "" }),
  }).then(handle<RecordedOffer>);
}

export function generateUpgradeOffer(customerId: string): Promise<UpgradeOffer> {
  return fetch(`${API_BASE}/equity-center/customer/${encodeURIComponent(customerId)}/upgrade-offer`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  }).then(handle<UpgradeOffer>);
}
