// Loyalty / VIP Rewards Engine -- core/loyalty.py's graph-native points/tier/
// visit/referral/reward tracking, stored directly as attributes on the existing
// Customer entity (exactly like core/customer_journey.py stores journey state).
// Backed by 7 dedicated /loyalty/* routes (api/routers/loyalty.py), not the
// generic /menu/data dispatch -- same "bespoke board bypasses /menu/data for its
// own extra views" precedent lib/customerJourney.ts and every other rebuild in
// this codebase established. This module is deliberately AI-free -- loyalty
// accounting is deterministic arithmetic, so there is no recommendation route here.
// Mirrors lib/customerJourney.ts's client pattern exactly (API_BASE + authHeaders
// + a shared handle<T> helper, one thin function per route).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// Ordered tier names -- must stay in step with core/loyalty.py's TIERS list
// (Bronze -> Silver -> Gold -> Platinum, ascending by lifetime-points threshold).
export const LOYALTY_TIERS = ["Bronze", "Silver", "Gold", "Platinum"] as const;
export type LoyaltyTier = (typeof LOYALTY_TIERS)[number];

// One immutable line in a member's loyalty ledger -- serialized core/loyalty.py
// LedgerEntry. `points` is signed: positive for earning, negative for a
// redemption, zero for a visit/referral that only advances a counter.
export type LedgerEntry = {
  entry_id: string;
  entry_type: string;
  points: number;
  reason: string;
  department: string;
  timestamp: string;
  balance_after: number;
};

// One reward a member has redeemed -- serialized core/loyalty.py RedemptionRecord.
export type RedemptionRecord = {
  redemption_id: string;
  reward_id: string;
  reward_name: string;
  point_cost: number;
  department: string;
  timestamp: string;
};

// A redeemable reward in the loyalty catalog -- serialized core/loyalty.py
// RewardCatalogItem (note the backend field is reward_id, not id).
export type RewardCatalogItem = {
  reward_id: string;
  name: string;
  description: string;
  point_cost: number;
  department: string;
};

// A member's full loyalty record -- core/loyalty.py's _member_brief shape.
export type Member = {
  customer_id: string;
  name: string | null;
  enrolled: boolean;
  enrolled_at: string | null;
  points_balance: number;
  lifetime_points: number;
  tier: string | null;
  visits: number;
  referrals: number;
  ledger: LedgerEntry[];
  redemptions: RedemptionRecord[];
};

// Program rollup -- core/loyalty.py's get_loyalty_overview shape. tier_distribution
// is seeded to 0 for every real tier even when empty.
export type LoyaltyOverview = {
  tiers: string[];
  member_count: number;
  total_outstanding_points: number;
  tier_distribution: Record<string, number>;
  total_redemptions: number;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function getLoyaltyOverview(): Promise<LoyaltyOverview> {
  return fetch(`${API_BASE}/loyalty/overview`, {
    headers: { ...authHeaders() },
  }).then(handle<LoyaltyOverview>);
}

export function getRewards(): Promise<RewardCatalogItem[]> {
  return fetch(`${API_BASE}/loyalty/rewards`, {
    headers: { ...authHeaders() },
  }).then(handle<RewardCatalogItem[]>);
}

export function getMember(customerId: string): Promise<Member> {
  return fetch(`${API_BASE}/loyalty/member/${encodeURIComponent(customerId)}`, {
    headers: { ...authHeaders() },
  }).then(handle<Member>);
}

export function awardPoints(
  customerId: string,
  points: number,
  reason?: string,
  department?: string
): Promise<Member> {
  return fetch(`${API_BASE}/loyalty/member/${encodeURIComponent(customerId)}/points`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ points, reason: reason ?? "", department: department ?? "" }),
  }).then(handle<Member>);
}

export function recordVisit(customerId: string, department?: string): Promise<Member> {
  return fetch(`${API_BASE}/loyalty/member/${encodeURIComponent(customerId)}/visit`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ department: department ?? "" }),
  }).then(handle<Member>);
}

export function recordReferral(customerId: string, referredName: string): Promise<Member> {
  return fetch(`${API_BASE}/loyalty/member/${encodeURIComponent(customerId)}/referral`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ referred_name: referredName }),
  }).then(handle<Member>);
}

export function redeemReward(customerId: string, rewardId: string): Promise<Member> {
  return fetch(`${API_BASE}/loyalty/member/${encodeURIComponent(customerId)}/redeem`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ reward_id: rewardId }),
  }).then(handle<Member>);
}
