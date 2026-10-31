// Finance's "Lender Intelligence" item (2026-07-19) -- closes the "Lender
// Intelligence" item from Sam's own six-pillar spec. Backend: core/
// lender_intelligence.py / _api.py. Real per-lender scorecards (approval rate,
// average offered APR, average decision turnaround) computed off Deal Desk's own
// new, real, append-only lender_submission_history log -- and a real, transparent,
// rules-based lender recommendation, never a fabricated AI score.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type LenderScorecard = {
  lender_id: string;
  lender_name: string;
  total_submissions: number;
  decided_submissions: number;
  pending_submissions: number;
  approved_count: number;
  declined_count: number;
  countered_count: number;
  approval_rate_pct: number | null;
  avg_offered_apr: number | null;
  avg_turnaround_days: number | null;
  turnaround_sample_size: number;
  has_sufficient_data: boolean;
};

export type SubmissionLogEntry = {
  lender_id: string;
  lender_name: string;
  deal_id: string;
  customer_credit_tier: string;
  submitted_at: string;
  decided_at: string | null;
  decision: "approved" | "declined" | "countered" | null;
  terms: { apr?: number; term_months?: number; amount_financed?: number; monthly_payment?: number } | null;
  notes: string | null;
  customer_name: string | null;
  vehicle_description: string | null;
  turnaround_days: number | null;
};

export type RecommendationEntry = LenderScorecard & {
  basis: string;
};

export type LenderRecommendation = {
  deal_id: string | null;
  credit_tier: string | null;
  tier_note: string | null;
  min_sample_size: number;
  ranked: RecommendationEntry[];
  insufficient_data: RecommendationEntry[];
  error?: string;
};

export type LenderIntelligenceOverview = {
  total_submissions: number;
  decided_submissions: number;
  pending_submissions: number;
  overall_approval_rate_pct: number | null;
  lenders_with_sufficient_data: number;
  total_lenders: number;
  scorecards: LenderScorecard[];
  recommendation: LenderRecommendation;
  not_yet_tracked: Record<string, string>;
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

export function getLenderIntelligenceOverview(): Promise<LenderIntelligenceOverview> {
  return get(`/lender-intelligence/overview`);
}

export function getLenderScorecards(): Promise<{ scorecards: LenderScorecard[] }> {
  return get(`/lender-intelligence/scorecards`);
}

export function getSubmissionLog(lenderId?: string, limit = 200): Promise<{ submissions: SubmissionLogEntry[] }> {
  const params = new URLSearchParams();
  if (lenderId) params.set("lender_id", lenderId);
  params.set("limit", String(limit));
  return get(`/lender-intelligence/submissions?${params.toString()}`);
}

export function getLenderRecommendation(dealId?: string): Promise<LenderRecommendation> {
  const params = new URLSearchParams();
  if (dealId) params.set("deal_id", dealId);
  const qs = params.toString();
  return get(`/lender-intelligence/recommendation${qs ? `?${qs}` : ""}`);
}
