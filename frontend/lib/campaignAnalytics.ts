// A/B Testing + Revenue Tracking for Campaigns (Marketing Growth Platform,
// Email/SMS upgrades slice, 2026-07-18). Backend: core/campaign_analytics.py.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type AbConfig = {
  campaign_id: string;
  is_ab_test: boolean;
  variant_a_template_id: string | null;
  variant_b_template_id: string | null;
  variant_a_audience_count: number;
  variant_b_audience_count: number;
};

export type AbVariantStats = {
  audience_count: number;
  revenue: number;
  funded_deals_count: number;
  leads_sold_count: number;
  conversion_rate: number;
};

export type AbTestResults =
  | { error: string }
  | {
      campaign_id: string;
      eligible: true;
      basis: string;
      disclaimer: string;
      variant_a_template_id: string | null;
      variant_b_template_id: string | null;
      results: { a: AbVariantStats; b: AbVariantStats };
      winner: "a" | "b" | null;
    }
  | { campaign_id: string; eligible: false; reason: string };

export type CampaignRevenue =
  | { error: string }
  | { campaign_id: string; eligible: false; reason: string }
  | {
      campaign_id: string;
      eligible: true;
      basis: string;
      disclaimer: string;
      activated_at: string;
      audience_count: number;
      funded_deals_count: number;
      leads_sold_count: number;
      revenue: number;
    };

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data && response.status >= 400)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function setAbVariant(campaignId: string, variantBTemplateId: string): Promise<{ error?: string; campaign_id?: string }> {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/ab-test`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ variant_b_template_id: variantBTemplateId }),
  });
  return res.json();
}

export async function clearAbVariant(campaignId: string): Promise<{ error?: string; campaign_id?: string }> {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/ab-test/clear`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  });
  return res.json();
}

export async function getAbConfig(campaignId: string): Promise<AbConfig> {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/ab-test`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getAbTestResults(campaignId: string): Promise<AbTestResults> {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/ab-test/results`, { headers: { ...authHeaders() } });
  return res.json();
}

export async function getCampaignRevenue(campaignId: string): Promise<CampaignRevenue> {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/revenue`, { headers: { ...authHeaders() } });
  return res.json();
}
