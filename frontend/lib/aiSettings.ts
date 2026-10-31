// AI Management dashboard settings client (2026-07-23) -- the dealer's own brand
// voice + reusable prompt templates, backing the two new sections Sam asked for
// on the AI Management page ("brand tone, prompt templates"). Talks to
// backend/api/routers/system_config.py's /ai-settings/* routes (brand settings
// feed core/ai_assist.py so every inline assist is on-brand). Mirrors
// lib/aiManagement.ts's client shape.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type BrandSettings = {
  brand_tone: string;
  brand_voice: string;
  style_guidelines: string;
};

export type BrandSettingsResponse = {
  brand_settings: BrandSettings;
  tones: string[];
};

export type PromptTemplate = {
  id: string;
  name: string;
  body: string;
  created_by: string | null;
  created_at: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error(
      (data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend."
    );
  }
  return data as T;
}

export function getBrandSettings(): Promise<BrandSettingsResponse> {
  return fetch(`${API_BASE}/ai-settings/brand`, { headers: { ...authHeaders() } }).then(
    handle<BrandSettingsResponse>
  );
}

export function updateBrandSettings(
  patch: Partial<BrandSettings>
): Promise<{ brand_settings: BrandSettings }> {
  return fetch(`${API_BASE}/ai-settings/brand`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(patch),
  }).then(handle<{ brand_settings: BrandSettings }>);
}

export function listPromptTemplates(): Promise<{ prompt_templates: PromptTemplate[] }> {
  return fetch(`${API_BASE}/ai-settings/prompt-templates`, {
    headers: { ...authHeaders() },
  }).then(handle<{ prompt_templates: PromptTemplate[] }>);
}

export function addPromptTemplate(name: string, body: string): Promise<PromptTemplate> {
  return fetch(`${API_BASE}/ai-settings/prompt-templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ name, body }),
  }).then(handle<PromptTemplate>);
}

export function removePromptTemplate(templateId: string): Promise<{ removed: string }> {
  return fetch(`${API_BASE}/ai-settings/prompt-templates/${encodeURIComponent(templateId)}`, {
    method: "DELETE",
    headers: { "Content-Type": "application/json", ...authHeaders() },
  }).then(handle<{ removed: string }>);
}
