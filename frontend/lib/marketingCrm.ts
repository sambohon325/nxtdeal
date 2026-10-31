// Marketing's "CRM" Top Menu item (session 79). Sam: "combine campaigns, audiences,
// and opportunities into one Hubspot style workflow dash called CRM." Talks to
// backend/core/marketing_menu.py's crm() (via the generic GET /menu/data, same as
// every other Top Menu item) for the read-only glance data, plus the dedicated
// campaign CRUD routes (backend/core/campaigns_api.py) and the new
// POST /lead/{lead_id}/advance-pipeline (backend/core/lead_pipeline_api.py) for the
// board's real actions -- creating/activating a campaign and dragging a Lead card
// between pipeline stages.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type PipelineCard = {
  id: string;
  name: string;
  source: string | null;
  since: string | null;
};

export type PipelineBoard = {
  states: string[];
  columns: Record<string, PipelineCard[]>;
  total: number;
};

export type CampaignSummary = {
  id: string;
  name: string;
  campaign_type: string;
  channel: string;
  status: string;
  audience_count: number;
  sent_count: number;
};

export type CampaignAudienceField = {
  key: string;
  label: string;
  type: string;
  required: boolean;
  default?: unknown;
};

export type CampaignType = {
  key: string;
  name: string;
  category: string;
  description: string;
  default_channel: string;
  audience_fields: CampaignAudienceField[];
};

export type CampaignsData = {
  total_campaigns: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  by_channel: Record<string, number>;
  available_types: CampaignType[];
  available_channels: string[];
  pending_drafts: { count: number };
  compliance_approval: { count: number; alerts: unknown[] };
  recent_campaigns: CampaignSummary[];
  not_yet_tracked?: Record<string, string>;
};

export type AudiencePool = {
  count: number;
  sample?: Array<{ id: string; entity_type: string; name: string }>;
  candidates?: Array<{ id: string; entity_type: string; name: string }>;
};

export type AudiencesData = {
  equity_mining: AudiencePool;
  lease_maturity: AudiencePool & { campaign_type?: string };
  service_conquest: AudiencePool;
  service_defection: AudiencePool;
  upgrade_opportunities: AudiencePool;
  previous_buyers: { count: number };
  unsold_leads: { count: number };
  not_yet_tracked?: Record<string, string>;
};

export type OpportunityPool = {
  label: string;
  count: number;
  projected_revenue_estimate?: number;
  sample: Array<{ id: string; entity_type: string; name: string }>;
  note: string;
};

export type OpportunitiesData = {
  equity_opportunities: OpportunityPool;
  trade_opportunities: OpportunityPool;
  conquest_opportunities: OpportunityPool;
  lease_opportunities: OpportunityPool;
  service_opportunities: OpportunityPool;
  retention_opportunities: OpportunityPool;
  who_to_contact_today: Array<{ id: string; entity_type: string; name: string }>;
};

export type CrmData = {
  pipeline: PipelineBoard;
  campaigns: CampaignsData;
  audiences: AudiencesData;
  opportunities: OpportunitiesData;
  smart_audiences?: {
    presets: { key: string; name: string; basis: string; params: unknown[] }[];
    saved_count: number;
    saved: { id: string; name: string; preset_key: string | null }[];
  };
  lead_scoring?: {
    total_scored: number;
    by_tier: Record<string, number>;
    top_leads: { lead_id: string; pipeline_state: string; source: string | null; score: number; tier: string }[];
  };
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();

  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }

  return data as T;
}

export async function fetchCrmData(): Promise<CrmData> {
  const res = await fetch(
    `${API_BASE}/menu/data?department=${encodeURIComponent("Marketing")}&item_key=crm`,
    { headers: { ...authHeaders() } }
  );
  return handle<CrmData>(res);
}

// Session 113 follow-up -- Campaigns split back out into its own dedicated Top Menu
// item (components/CampaignsBoard.tsx), per Sam's later 12-item Growth Platform menu
// spec. Same real backend data as CrmData["campaigns"] (backend/core/marketing_menu.py's
// campaigns(), which just calls the same _campaigns(role) crm() already uses) -- this
// is a leaner fetch that skips Pipeline/Lists/Opportunities/Customer 360/Smart
// Audiences/Lead Scoring for a Marketing user who wants campaigns directly.
export async function fetchCampaignsData(): Promise<CampaignsData> {
  const res = await fetch(
    `${API_BASE}/menu/data?department=${encodeURIComponent("Marketing")}&item_key=campaigns`,
    { headers: { ...authHeaders() } }
  );
  return handle<CampaignsData>(res);
}

export async function advanceLeadPipeline(leadId: string, nextState: string): Promise<{ lead_id: string; previous_state: string; state: string }> {
  const res = await fetch(`${API_BASE}/lead/${encodeURIComponent(leadId)}/advance-pipeline`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ next_state: nextState }),
  });
  return handle(res);
}

export async function previewCrmAudience(campaignType: string, params: Record<string, unknown>): Promise<AudiencePool & { campaign_type: string; entity_type: string | null }> {
  const res = await fetch(`${API_BASE}/campaigns/audience/preview`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ campaign_type: campaignType, params }),
  });
  return handle(res);
}

export async function createCrmCampaign(input: {
  campaign_type: string;
  name: string;
  channel?: string;
  params: Record<string, unknown>;
  linked_asset_id?: string | null;
  linked_template_id?: string | null;
}): Promise<CampaignSummary & Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/campaigns`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function activateCrmCampaign(campaignId: string) {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/activate`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function completeCrmCampaign(campaignId: string) {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/complete`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function cancelCrmCampaign(campaignId: string) {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/cancel`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export type CrmSearchResult = { id: string; entity_type: string; name?: string };

export async function searchCrm(query: string): Promise<{ query: string; count: number; results: CrmSearchResult[] }> {
  const res = await fetch(
    `${API_BASE}/menu/data?department=${encodeURIComponent("Marketing")}&item_key=crm&query=${encodeURIComponent(query)}`,
    { headers: { ...authHeaders() } }
  );
  return handle(res);
}
