// Finance's "Collections" item -- the third slice of Sam's Retail Automotive Lending
// Platform expansion (2026-07-17), right after Portfolio and Payments. Backend:
// core/collections.py / _api.py. Built entirely on top of core/loan_servicing.py's
// own delinquency computation (real once real Payments exist for a loan, simulated
// otherwise) -- this module doesn't re-decide whether a loan is delinquent, it
// triages and works whatever that computation already says. "AI Collection
// Prioritization" is a real, transparent rules engine (days past due + broken
// promises + payment consistency) -- NOT a machine-learning model or LLM call.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type CollectionStage = "friendly_reminder" | "late_notice" | "demand_notice" | "recovery_review" | "repossession_referral";
export type QueueBucket = "3_day" | "7_day" | "15_day" | "30_day" | "60_day";
export type ContactChannel = "call" | "text" | "email";
export type PriorityRecommendation = "recovery_risk" | "high_probability_to_pay" | "standard_follow_up";

export const COLLECTION_STAGES: CollectionStage[] = ["friendly_reminder", "late_notice", "demand_notice", "recovery_review", "repossession_referral"];
export const QUEUE_BUCKETS: QueueBucket[] = ["3_day", "7_day", "15_day", "30_day", "60_day"];
export const CONTACT_CHANNELS: ContactChannel[] = ["call", "text", "email"];

export const STAGE_LABELS: Record<CollectionStage, string> = {
  friendly_reminder: "Friendly Reminder",
  late_notice: "Late Notice",
  demand_notice: "Demand Notice",
  recovery_review: "Recovery Review",
  repossession_referral: "Repossession Referral",
};

export const BUCKET_LABELS: Record<QueueBucket, string> = {
  "3_day": "3+ Days",
  "7_day": "7+ Days",
  "15_day": "15+ Days",
  "30_day": "30+ Days",
  "60_day": "60+ Days",
};

export type QueueRow = {
  loan_id: string;
  finance_number: string | null;
  customer_name: string | null;
  days_past_due: number;
  amount_past_due: number | null;
  queue_bucket: QueueBucket;
  collection_stage: CollectionStage;
  priority: PriorityRecommendation | null;
  priority_label: string | null;
  basis: string;
};

export type CollectionQueue = {
  total_in_queue: number;
  bucket_counts: Record<QueueBucket, number>;
  loans: QueueRow[];
};

export type CollectionsDashboard = {
  total_in_queue: number;
  bucket_counts: Record<QueueBucket, number>;
  stage_counts: Record<CollectionStage, number>;
  recovery_risk_count: number;
  contact_today_count: number;
};

export type RiskScore = {
  loan_id: string;
  score: number;
  tier: "high" | "elevated" | "low";
  days_past_due: number;
  broken_promises: number;
  payment_count: number;
  basis: string;
  note: string;
};

export type PriorityRecommendationResult = {
  loan_id: string;
  recommendation: PriorityRecommendation;
  label: string;
  risk_score: number;
  risk_tier: "high" | "elevated" | "low";
  basis: string;
  note: string;
};

export type ContactHistoryEntry = {
  id: string;
  category: ContactChannel;
  body: string;
  created_by: string;
  created_at: string;
};

export type AgentWorkspace = {
  loan_id: string;
  finance_number: string | null;
  customer: Record<string, unknown> | null;
  vehicle: Record<string, unknown> | null;
  employment: { on_file: boolean; note?: string; employer_name?: string; monthly_income?: number; employment_status?: string; housing?: string };
  references: { on_file: boolean; note: string };
  last_payment: { amount: number; method: string; payment_date: string } | null;
  payment_status: Record<string, unknown>;
  risk_score: RiskScore;
  priority_recommendation: PriorityRecommendationResult;
  promises_to_pay: unknown[];
  collection_stage: CollectionStage;
  collection_stage_history: { stage: CollectionStage; by: string; reason: string; at: string }[];
  contact_history: ContactHistoryEntry[];
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

function post<T>(path: string, body: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body),
  }).then(handle<T>);
}

export function getCollectionQueue(bucket?: QueueBucket): Promise<CollectionQueue> {
  const params = new URLSearchParams();
  if (bucket) params.set("bucket", bucket);
  const qs = params.toString();
  return get(`/collections/queue${qs ? `?${qs}` : ""}`);
}

export function getCollectionsDashboard(): Promise<CollectionsDashboard> {
  return get(`/collections/dashboard`);
}

export function getAgentWorkspace(loanId: string): Promise<AgentWorkspace> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/collections/workspace`);
}

export function getCollectionStage(loanId: string): Promise<{ loan_id: string; collection_stage: CollectionStage }> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/collections/stage`);
}

export function advanceCollectionStage(loanId: string, stage: CollectionStage, reason = ""): Promise<unknown> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/collections/stage`, { stage, reason });
}

export function computeRiskScore(loanId: string): Promise<RiskScore> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/collections/risk-score`);
}

export function getPriorityRecommendation(loanId: string): Promise<PriorityRecommendationResult> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/collections/priority`);
}

export function logContact(loanId: string, channel: ContactChannel, notes: string): Promise<unknown> {
  return post(`/loan-servicing/${encodeURIComponent(loanId)}/collections/contact`, { channel, notes });
}

export function getContactHistory(loanId: string, limit = 50): Promise<{ loan_id: string; count: number; history: ContactHistoryEntry[] }> {
  return get(`/loan-servicing/${encodeURIComponent(loanId)}/collections/contact-history?limit=${limit}`);
}
