// Coaching (2026-07-19) -- the fourth "NXTDeal Workforce AI" pillar, folded
// into Operations' existing Workforce Management dash as a tab (not a new Top
// Menu item -- see components/WorkforceBoard.tsx). Backend: core/coaching.py /
// coaching_api.py. Caller identity (for ACL -- ADMIN/OPERATIONS, or a
// manager-/executive-tier employee via core/bot_tasks.py's own infer_tier())
// is derived server-side from the Authorization header, never passed in a
// request body.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type IntensityTier = "participant" | "productive" | "aggressive";
export type IntensityScope = "global" | "department" | "role" | "individual";

export type IntensityCatalog = {
  tiers: { key: IntensityTier; label: string; description: string }[];
  scopes: { key: IntensityScope; label: string }[];
  default_intensity: IntensityTier;
};

export type IntensityResolution = {
  employee_id: string;
  intensity: IntensityTier;
  resolved_from: "individual" | "role" | "department" | "global" | "default";
  error?: string;
};

export type IntensityOverride = {
  id: string;
  scope: IntensityScope;
  scope_target: string;
  intensity: IntensityTier;
  reason: string;
  active: boolean;
  set_by: string;
  created_at: string;
  superseded_at: string | null;
};

export type PerformanceReview = {
  id: string;
  employee_id: string;
  employee_name: string;
  department: string;
  tier: string | null;
  period_label: string;
  status: "draft" | "finalized" | "shared";
  metrics_snapshot: Record<string, unknown>;
  factual_summary: string[];
  manager_notes: string;
  created_by: string;
  created_at: string;
  finalized_by: string | null;
  finalized_at: string | null;
  shared_by: string | null;
  shared_at: string | null;
  error?: string;
};

export type CareerPathingSignalKey =
  | "insufficient_peer_data"
  | "ready_for_more_responsibility"
  | "skill_gap"
  | "on_par_with_peers";

export type CareerPathingResult = {
  employee_id: string;
  name: string;
  department: string;
  tier: string | null;
  next_tier: string | null;
  signal: CareerPathingSignalKey;
  finding: string;
  peer_average_monthly_value?: number;
  peer_sample_size?: number;
  delta_pct?: number | null;
  basis_note?: string;
  error?: string;
};

export type CareerPathingBoard = {
  count: number;
  by_signal: Record<string, number>;
  employees: CareerPathingResult[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

function post<T>(path: string, body?: Record<string, unknown>): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(body ?? {}),
  }).then(handle<T>);
}

export function getIntensityCatalog(): Promise<IntensityCatalog> {
  return get("/coaching/intensity/catalog");
}

export function resolveIntensity(targetEmployeeId?: string, department?: string): Promise<IntensityResolution> {
  const q = new URLSearchParams();
  if (targetEmployeeId) q.set("target_employee_id", targetEmployeeId);
  if (department) q.set("department", department);
  const qs = q.toString();
  return get(`/coaching/intensity/resolve${qs ? `?${qs}` : ""}`);
}

export function setIntensityOverride(input: {
  scope: IntensityScope;
  scope_target: string;
  intensity: IntensityTier;
  reason?: string;
}): Promise<IntensityOverride> {
  return post("/coaching/intensity/override", input);
}

export function listIntensityOverrides(): Promise<{ overrides: IntensityOverride[] }> {
  return get("/coaching/intensity/overrides");
}

export function createPerformanceReview(targetEmployeeId: string, periodLabel?: string): Promise<PerformanceReview> {
  return post("/coaching/reviews", { target_employee_id: targetEmployeeId, period_label: periodLabel ?? "" });
}

export function listPerformanceReviews(params?: { employee_id?: string; status?: string }): Promise<{ reviews: PerformanceReview[] }> {
  const q = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => v && q.set(k, v));
  const qs = q.toString();
  return get(`/coaching/reviews${qs ? `?${qs}` : ""}`);
}

export function getPerformanceReview(reviewId: string): Promise<PerformanceReview> {
  return get(`/coaching/reviews/${encodeURIComponent(reviewId)}`);
}

export function updateReviewNotes(reviewId: string, managerNotes: string): Promise<PerformanceReview> {
  return post(`/coaching/reviews/${encodeURIComponent(reviewId)}/notes`, { manager_notes: managerNotes });
}

export function finalizeReview(reviewId: string): Promise<PerformanceReview> {
  return post(`/coaching/reviews/${encodeURIComponent(reviewId)}/finalize`);
}

export function shareReview(reviewId: string): Promise<PerformanceReview> {
  return post(`/coaching/reviews/${encodeURIComponent(reviewId)}/share`);
}

export function discardReview(reviewId: string): Promise<{ success: boolean }> {
  return post(`/coaching/reviews/${encodeURIComponent(reviewId)}/discard`);
}

export function getCareerPathingSignal(targetEmployeeId?: string): Promise<CareerPathingResult> {
  const q = targetEmployeeId ? `?target_employee_id=${encodeURIComponent(targetEmployeeId)}` : "";
  return get(`/coaching/career-pathing${q}`);
}

export function getCareerPathingBoard(params?: { department?: string; signal?: string }): Promise<CareerPathingBoard> {
  const q = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => v && q.set(k, v));
  const qs = q.toString();
  return get(`/coaching/career-pathing/board${qs ? `?${qs}` : ""}`);
}
