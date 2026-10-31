// Marketing's new "AI Studio" Top Menu item (2026-07-19). Backend:
// core/marketing_studio.py / marketing_studio_api.py -- a real dispatch table
// over 7 already-real, already-kill-switched AI wizard functions, logging every
// generation as a MarketingContentDraft with a real drafted/applied/discarded
// lifecycle.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type ContentType =
  | "email_copy"
  | "sms_copy"
  | "website_section"
  | "website_seo"
  | "vehicle_description"
  | "social_caption"
  | "ad_recommendation";

export type ContentTypeCatalogEntry = {
  key: ContentType;
  label: string;
  channel: string;
  params: string[];
  kill_switch_feature: string;
};

export type DraftStatus = "drafted" | "applied" | "discarded";

export type ContentDraft = {
  id: string;
  content_type: ContentType;
  params: Record<string, unknown>;
  content: Record<string, unknown>;
  used_fallback: boolean;
  fallback_reason: string | null;
  status: DraftStatus;
  created_by: string;
  created_at: string;
  decided_by: string | null;
  decided_at: string | null;
  error?: string;
};

export type StudioOverview = {
  content_type_catalog: ContentTypeCatalogEntry[];
  total_drafts: number;
  by_content_type: Record<string, number>;
  by_status: Record<string, number>;
  fallback_count: number;
  recent_drafts: ContentDraft[];
  error?: string;
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

export function getStudioOverview(): Promise<StudioOverview> {
  return get("/marketing-studio/overview");
}

export function listContentDrafts(params?: {
  content_type?: string;
  status?: string;
  created_by?: string;
}): Promise<{ drafts: ContentDraft[] }> {
  const q = new URLSearchParams();
  Object.entries(params ?? {}).forEach(([k, v]) => v && q.set(k, v));
  const qs = q.toString();
  return get(`/marketing-studio/drafts${qs ? `?${qs}` : ""}`);
}

export function generateContent(contentType: ContentType, params: Record<string, unknown>): Promise<ContentDraft> {
  return post("/marketing-studio/generate", { content_type: contentType, params });
}

export function applyDraft(draftId: string): Promise<ContentDraft> {
  return post(`/marketing-studio/drafts/${encodeURIComponent(draftId)}/apply`);
}

export function discardDraft(draftId: string): Promise<ContentDraft> {
  return post(`/marketing-studio/drafts/${encodeURIComponent(draftId)}/discard`);
}
