// Advertising -- Meta/Google ad campaigns with inventory integration (session 83).
// Sam: "advertising dash... start meta and google ad campaigns that include
// inventory and allow ai recommendations / building, or granular control."
//
// Talks to backend/core/advertising_api.py (via /advertising/* routes).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type AdPlatform = "meta" | "google";

export type AdObjective = { key: string; name: string };

export type AdLinkedVehicle = {
  id: string;
  year?: number | string;
  make?: string;
  model?: string;
  trim?: string;
  price?: number;
};

export type AdCampaign = {
  id: string;
  platform: AdPlatform;
  objective: string;
  name: string;
  headline: string;
  primary_text: string;
  description: string;
  disclaimer: string;
  daily_budget: number | null;
  targeting: Record<string, unknown>;
  linked_vehicle_ids: string[];
  ai_generated: boolean;
  status: "draft" | "active" | "paused" | "completed" | "cancelled";
  created_by: string;
  created_at: string;
  updated_at: string;
  launched_at: string | null;
  paused_at: string | null;
  completed_at: string | null;
  performance_note?: string;
  linked_vehicles?: AdLinkedVehicle[];
};

export type AdRecommendation = {
  headline: string;
  primary_text: string;
  description: string;
  disclaimer: string;
  targeting_suggestion: string;
  ai_generated: boolean;
  ai_error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function listAdPlatforms(): Promise<AdPlatform[]> {
  const res = await fetch(`${API_BASE}/advertising/platforms`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listAdObjectives(): Promise<AdObjective[]> {
  const res = await fetch(`${API_BASE}/advertising/objectives`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function generateAdRecommendation(input: {
  platform: AdPlatform;
  objective: string;
  audience_description?: string;
  vehicle_description?: string;
}): Promise<AdRecommendation> {
  const res = await fetch(`${API_BASE}/advertising/recommend`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function createAdCampaign(input: {
  platform: AdPlatform;
  objective: string;
  name?: string;
  fields?: Record<string, unknown>;
  linked_vehicle_ids?: string[];
}): Promise<AdCampaign> {
  const res = await fetch(`${API_BASE}/advertising/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function listAdCampaigns(opts: {
  platform?: AdPlatform;
  status?: string;
  mineOnly?: boolean;
} = {}): Promise<AdCampaign[]> {
  const params = new URLSearchParams();
  if (opts.platform) params.set("platform", opts.platform);
  if (opts.status) params.set("status", opts.status);
  if (opts.mineOnly) params.set("mine_only", "true");
  const res = await fetch(`${API_BASE}/advertising/campaigns?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getAdCampaign(adId: string): Promise<AdCampaign> {
  const res = await fetch(`${API_BASE}/advertising/campaigns/${encodeURIComponent(adId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updateAdCampaign(adId: string, patch: Partial<AdCampaign>): Promise<AdCampaign> {
  const res = await fetch(`${API_BASE}/advertising/campaigns/${encodeURIComponent(adId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function launchAdCampaign(adId: string): Promise<AdCampaign> {
  const res = await fetch(`${API_BASE}/advertising/campaigns/${encodeURIComponent(adId)}/launch`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function pauseAdCampaign(adId: string): Promise<AdCampaign> {
  const res = await fetch(`${API_BASE}/advertising/campaigns/${encodeURIComponent(adId)}/pause`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function completeAdCampaign(adId: string): Promise<AdCampaign> {
  const res = await fetch(`${API_BASE}/advertising/campaigns/${encodeURIComponent(adId)}/complete`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function cancelAdCampaign(adId: string): Promise<AdCampaign> {
  const res = await fetch(`${API_BASE}/advertising/campaigns/${encodeURIComponent(adId)}/cancel`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}
