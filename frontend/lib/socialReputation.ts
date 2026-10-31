// Social media post builder + content calendar + reputation management (session 83).
// Sam: "hootsuit-style social suite... built in social media post builder that
// includes dropping in inventory... a toggle for reputation tracking... bot function
// to respond to reviews / alert for bad reviews... competitors social tracking."
//
// Talks to backend/core/social_posts_api.py (via /social/* routes) and
// backend/core/reputation_api.py (via /reputation/* routes).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type SocialPlatform = "facebook" | "instagram" | "x" | "linkedin" | "tiktok";

export type LinkedVehicle = {
  id: string;
  year?: number | string;
  make?: string;
  model?: string;
  trim?: string;
  price?: number;
};

export type SocialPost = {
  id: string;
  platform: SocialPlatform;
  content: string;
  media_url: string | null;
  linked_vehicle_ids: string[];
  status: "draft" | "scheduled" | "published" | "cancelled";
  scheduled_time: string | null;
  target_date: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  linked_vehicles?: LinkedVehicle[];
};

export type CalendarPost = {
  id: string;
  platform: SocialPlatform;
  content: string;
  status: string;
  scheduled_time: string | null;
  target_date: string | null;
};

export type CalendarResponse = {
  by_date: Record<string, CalendarPost[]>;
  total: number;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function listSocialPlatforms(): Promise<SocialPlatform[]> {
  const res = await fetch(`${API_BASE}/social/platforms`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createSocialPost(input: {
  platform: SocialPlatform;
  content: string;
  media_url?: string | null;
  linked_vehicle_ids?: string[];
  scheduled_time?: string | null;
  target_date?: string | null;
}): Promise<SocialPost> {
  const res = await fetch(`${API_BASE}/social/posts`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function listSocialPosts(opts: {
  platform?: SocialPlatform;
  status?: string;
  mineOnly?: boolean;
} = {}): Promise<SocialPost[]> {
  const params = new URLSearchParams();
  if (opts.platform) params.set("platform", opts.platform);
  if (opts.status) params.set("status", opts.status);
  if (opts.mineOnly) params.set("mine_only", "true");
  const res = await fetch(`${API_BASE}/social/posts?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getSocialCalendar(startDate?: string, endDate?: string): Promise<CalendarResponse> {
  const params = new URLSearchParams();
  if (startDate) params.set("start_date", startDate);
  if (endDate) params.set("end_date", endDate);
  const res = await fetch(`${API_BASE}/social/posts/calendar?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function searchInventoryForPost(query = ""): Promise<LinkedVehicle[]> {
  const params = new URLSearchParams();
  if (query) params.set("query", query);
  const res = await fetch(`${API_BASE}/social/inventory-search?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getSocialPost(postId: string): Promise<SocialPost> {
  const res = await fetch(`${API_BASE}/social/posts/${encodeURIComponent(postId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateSocialPost(postId: string, patch: Partial<SocialPost>): Promise<SocialPost> {
  const res = await fetch(`${API_BASE}/social/posts/${encodeURIComponent(postId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function publishSocialPost(postId: string): Promise<SocialPost> {
  const res = await fetch(`${API_BASE}/social/posts/${encodeURIComponent(postId)}/publish`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function cancelSocialPost(postId: string): Promise<SocialPost> {
  const res = await fetch(`${API_BASE}/social/posts/${encodeURIComponent(postId)}/cancel`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export type GeneratedCaption = { caption: string; ai_generated: boolean; error?: string };

// AI caption generation (session 113 follow-up) -- grounded in a real linked vehicle's
// attributes when vehicleId is given, never invents pricing/trim details.
export async function generateSocialCaption(input: {
  platform: SocialPlatform;
  goal?: string;
  tone?: string;
  vehicleId?: string;
}): Promise<GeneratedCaption> {
  const res = await fetch(`${API_BASE}/social/posts/generate-caption`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ platform: input.platform, goal: input.goal || null, tone: input.tone || null, vehicle_id: input.vehicleId || null }),
  });
  return handle(res);
}

// --- Reputation ---

export type Review = {
  id: string;
  platform: string;
  rating: number;
  author_name: string;
  text: string;
  review_date: string;
  responded: boolean;
  response_text?: string | null;
  responded_by?: string | null;
  responded_at?: string | null;
  auto_responded?: boolean;
};

export type BadReviewAlert = {
  id: string;
  platform: string;
  rating: number;
  author_name: string;
  text: string;
  review_date: string;
};

export type CompetitorTracking = {
  you: { avg_rating: number | null; review_count: number; posts_per_week: number | null };
  competitors: { label: string; avg_rating: number; review_count: number; posts_per_week: number }[];
  basis: string;
  notice: string;
};

export async function getReputationSummary(): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/reputation/summary`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listReviews(opts: {
  platform?: string;
  responded?: boolean;
  maxRating?: number;
} = {}): Promise<Review[]> {
  const params = new URLSearchParams();
  if (opts.platform) params.set("platform", opts.platform);
  if (opts.responded !== undefined) params.set("responded", String(opts.responded));
  if (opts.maxRating !== undefined) params.set("max_rating", String(opts.maxRating));
  const res = await fetch(`${API_BASE}/reputation/reviews?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listBadReviewAlerts(): Promise<BadReviewAlert[]> {
  const res = await fetch(`${API_BASE}/reputation/alerts`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function respondToReview(reviewId: string, responseText: string): Promise<Review> {
  const res = await fetch(`${API_BASE}/reputation/reviews/${encodeURIComponent(reviewId)}/respond`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ response_text: responseText }),
  });
  return handle(res);
}

export async function autoRespondToReview(reviewId: string): Promise<Review> {
  const res = await fetch(`${API_BASE}/reputation/reviews/${encodeURIComponent(reviewId)}/auto-respond`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function getCompetitorTracking(): Promise<CompetitorTracking> {
  const res = await fetch(`${API_BASE}/reputation/competitor-tracking`, { headers: { ...authHeaders() } });
  return handle(res);
}
