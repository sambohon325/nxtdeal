// CRM Lists + editable Campaigns + Opportunities workflow actions (session 82). Sam:
// "under lists we need to be able to click on the list names and have them show as a
// list of names... with a page up and down also adjustable by 25, 50, 100... you can
// filter by list, lead, customer... curate marketing lists for campaigns. Also the
// campaigns should be editable, and when you click on them they should show the list
// of people, all the information... as well as active measurements / analytics...
// [opportunities] each module needs to be a workable process."
//
// Talks to backend/core/marketing_lists_api.py (via the new /lists* routes),
// backend/core/campaigns_api.py's update/detail additions, and
// backend/core/opportunities_api.py (via /opportunities/*).

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ListMember = {
  id: string;
  entity_type: string;
  name: string;
  phone?: string | null;
  email?: string | null;
  source?: string | null;
  pipeline_state?: string | null;
};

export type MemberPage = {
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
  members: ListMember[];
};

export type MarketingList = {
  id: string;
  name: string;
  description: string;
  source: string;
  created_by: string;
  created_at: string;
  updated_at: string;
  archived?: boolean;
  // core/marketing_lists_api.py's _serialize() spreads the entity's real attributes
  // verbatim -- member_ids is the full membership array, not a precomputed count.
  member_ids?: string[];
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export async function createList(name: string, description = ""): Promise<MarketingList> {
  const res = await fetch(`${API_BASE}/lists`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, description }),
  });
  return handle(res);
}

export async function buildListFromPool(input: {
  name: string;
  campaign_type: string;
  params: Record<string, unknown>;
  description?: string;
}): Promise<MarketingList & { member_ids?: string[] }> {
  const res = await fetch(`${API_BASE}/lists/from-pool`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function listAllLists(mineOnly = false): Promise<MarketingList[]> {
  const res = await fetch(`${API_BASE}/lists?mine_only=${mineOnly ? "true" : "false"}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function getList(listId: string): Promise<MarketingList> {
  const res = await fetch(`${API_BASE}/lists/${encodeURIComponent(listId)}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function getListMembers(
  listId: string,
  page = 1,
  pageSize: 25 | 50 | 100 = 25,
  entityTypeFilter?: "Customer" | "Lead" | null
): Promise<MemberPage & { list_id: string }> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (entityTypeFilter) params.set("entity_type", entityTypeFilter);
  const res = await fetch(`${API_BASE}/lists/${encodeURIComponent(listId)}/members?${params.toString()}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function updateList(listId: string, patch: { name?: string; description?: string }): Promise<MarketingList> {
  const res = await fetch(`${API_BASE}/lists/${encodeURIComponent(listId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function addListMembers(listId: string, entityIds: string[]) {
  const res = await fetch(`${API_BASE}/lists/${encodeURIComponent(listId)}/members`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ entity_ids: entityIds }),
  });
  return handle(res);
}

export async function removeListMembers(listId: string, entityIds: string[]) {
  const res = await fetch(`${API_BASE}/lists/${encodeURIComponent(listId)}/members/remove`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ entity_ids: entityIds }),
  });
  return handle(res);
}

export async function archiveList(listId: string) {
  const res = await fetch(`${API_BASE}/lists/${encodeURIComponent(listId)}/archive`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

// --- Editable campaigns / detail view ---

export type CampaignStats = {
  status: string;
  campaign_type: string;
  channel: string;
  audience_count: number;
  sent_count: number;
  created_at: string;
  activated_at: string | null;
  completed_at: string | null;
  days_active: number | null;
  not_yet_tracked?: { open_rate: string; click_rate: string };
};

export type CampaignDetail = {
  campaign: Record<string, unknown> & { id: string; name: string; notes?: string; status: string };
  stats: CampaignStats;
  members: MemberPage;
  linked_template: { id: string; name: string; channel: string; subject: string } | null;
};

export async function updateCampaign(campaignId: string, patch: { name?: string; notes?: string }) {
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function getCampaignDetail(
  campaignId: string,
  page = 1,
  pageSize: 25 | 50 | 100 = 25,
  entityTypeFilter?: "Customer" | "Lead" | null
): Promise<CampaignDetail> {
  const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) });
  if (entityTypeFilter) params.set("entity_type", entityTypeFilter);
  const res = await fetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}/detail?${params.toString()}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

// --- Opportunities workflow actions ---

export type SalesEmployee = { id: string; name: string; title: string | null };

export async function listSalesEmployees(): Promise<SalesEmployee[]> {
  const res = await fetch(`${API_BASE}/opportunities/sales-employees`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function saveOpportunityPoolAsList(input: {
  name: string;
  campaign_type: string;
  params: Record<string, unknown>;
  description?: string;
}): Promise<MarketingList> {
  const res = await fetch(`${API_BASE}/opportunities/save-as-list`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function assignOpportunityToSales(leadId: string, assignToEmployeeId: string) {
  const res = await fetch(`${API_BASE}/opportunities/assign-to-sales`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ lead_id: leadId, assign_to_employee_id: assignToEmployeeId }),
  });
  return handle(res);
}
