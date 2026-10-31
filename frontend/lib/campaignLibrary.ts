// Bumper-parity Campaign-Template Library client (2026-07-25). Talks to
// backend/api/routers/content_library.py (/campaign-templates/*).
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export type CampaignTemplate = {
  id: string;
  name: string;
  description: string;
  category: string;
  campaign_type: string;
  channel: string;
  default_params: Record<string, unknown>;
  suggested_subject: string;
  suggested_body: string;
  tags: string[];
  is_starter: boolean;
  times_used: number;
};

export async function listTemplateCategories(): Promise<{ categories: { category: string; count: number }[] }> {
  const res = await fetch(`${API_BASE}/campaign-templates/categories`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listTemplates(opts?: { category?: string; campaign_type?: string; query?: string }): Promise<{ templates: CampaignTemplate[] }> {
  const qs = new URLSearchParams();
  if (opts?.category) qs.set("category", opts.category);
  if (opts?.campaign_type) qs.set("campaign_type", opts.campaign_type);
  if (opts?.query) qs.set("query", opts.query);
  const suffix = qs.toString() ? `?${qs.toString()}` : "";
  const res = await fetch(`${API_BASE}/campaign-templates${suffix}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function instantiateTemplate(
  templateId: string,
  input?: { name_override?: string | null; params_override?: Record<string, unknown> | null; channel_override?: string | null }
): Promise<Record<string, unknown> & { id: string; status: string }> {
  const res = await fetch(`${API_BASE}/campaign-templates/${encodeURIComponent(templateId)}/instantiate`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({
      name_override: input?.name_override ?? null,
      params_override: input?.params_override ?? null,
      channel_override: input?.channel_override ?? null,
    }),
  });
  return handle(res);
}

export async function deleteTemplate(templateId: string) {
  const res = await fetch(`${API_BASE}/campaign-templates/${encodeURIComponent(templateId)}`, {
    method: "DELETE",
    headers: { ...authHeaders() },
  });
  return handle<{ ok: boolean; template_id: string }>(res);
}
