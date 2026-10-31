// Client for the MySales rep referral/reward program (/referrals/*, core/rep_referrals.py).
// Same shape every lib/*.ts client follows: API_BASE + authHeaders() + a local handle<T>.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ReferralKind = "dealership_demo" | "dealership_conversion" | "rep_recruit";

export type Referral = {
  id: string;
  kind: ReferralKind;
  label: string;
  subject: string | null;
  contact_name: string | null;
  contact_email: string | null;
  notes: string | null;
  status: string;
  reward: number;
  earned: boolean;
  declined: boolean;
  created_at: string;
  updated_at: string;
};

export type RewardTier = { label: string; reward: number };

export type ReferralSummary = {
  code: string;
  tiers: Record<string, RewardTier>;
  totals: { earned: number; pending: number; recruits: number; dealership_referrals: number };
  referrals: Referral[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function fetchMyReferrals(): Promise<ReferralSummary> {
  return fetch(`${API_BASE}/referrals/me`, { headers: authHeaders() }).then(handle<ReferralSummary>);
}

export function submitDealershipReferral(input: {
  kind: "dealership_demo" | "dealership_conversion";
  dealership_name: string;
  contact_name?: string;
  contact_email?: string;
  notes?: string;
}): Promise<Referral> {
  return fetch(`${API_BASE}/referrals/dealership`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  }).then(handle<Referral>);
}

export function applyReferralCode(code: string): Promise<Referral> {
  return fetch(`${API_BASE}/referrals/apply-code`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ code }),
  }).then(handle<Referral>);
}
