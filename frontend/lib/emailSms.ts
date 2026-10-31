// Marketing's "Email / SMS" Top Menu item (session 79). Sam: "add an Email/SMS dash
// with a fully functional email builder (for mass and individual campaigns). It
// should have an Ai build an email wizard as well as a traditional drag and drop
// modual / mailchimp builder. it should have a toggle to switch to a texting/sms
// builder. Both pull from the CRM." Talks to backend/core/email_templates_api.py's
// /email-templates/* routes.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type EmailChannel = "email" | "sms";

export type BlockField = {
  key: string;
  label: string;
  type: string;
  required: boolean;
  default?: unknown;
};

export type BlockType = {
  key: string;
  name: string;
  description: string;
  fields: BlockField[];
};

export type TemplateBlock = {
  block_key: string;
  fields: Record<string, unknown>;
};

export type EmailTemplate = {
  id: string;
  channel: EmailChannel;
  name: string;
  subject: string | null;
  preheader: string | null;
  blocks: TemplateBlock[];
  sms_body: string | null;
  ai_generated: boolean;
  linked_campaign_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type EmailSmsOverview = {
  total_templates: number;
  by_channel: Record<string, number>;
  ai_generated_count: number;
  attached_to_campaign_count: number;
  recent_templates: Array<{
    id: string;
    name: string;
    channel: EmailChannel;
    subject: string | null;
    ai_generated: boolean;
    created_by: string;
    updated_at: string;
  }>;
  block_catalog: BlockType[];
  available_campaign_types: Array<{
    key: string;
    name: string;
    category: string;
    description: string;
    default_channel: string;
    audience_fields: BlockField[];
  }>;
};

export type SmsSegmentInfo = {
  length: number;
  encoding: string;
  segments: number;
  chars_per_segment: number;
};

export type TemplatePreview =
  | { channel: "email"; subject: string | null; preheader: string | null; html: string; text: string }
  | { channel: "sms"; sms_body: string | null; segment_info: SmsSegmentInfo };

// Dynamic Personalization (Marketing Growth Platform, Email/SMS upgrades slice,
// 2026-07-18). Backend: core/email_personalization.py.

export type MergeField = { key: string; label: string; example: string; customers_only?: boolean };

export type MergeValues = Record<string, string>;

export type PersonalizedPreview =
  | { channel: "email"; subject: string | null; preheader: string | null; html: string; text: string; merge_values: MergeValues }
  | { channel: "sms"; sms_body: string | null; segment_info: SmsSegmentInfo; merge_values: MergeValues };

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();

  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }

  return data as T;
}

export async function fetchEmailSmsOverview(): Promise<EmailSmsOverview> {
  const res = await fetch(
    `${API_BASE}/menu/data?department=${encodeURIComponent("Marketing")}&item_key=email_sms`,
    { headers: { ...authHeaders() } }
  );
  return handle<EmailSmsOverview>(res);
}

export async function fetchBlockTypes(): Promise<BlockType[]> {
  const res = await fetch(`${API_BASE}/email-templates/blocks`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createTemplate(channel: EmailChannel, name?: string): Promise<EmailTemplate> {
  const res = await fetch(`${API_BASE}/email-templates`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ channel, name }),
  });
  return handle(res);
}

export async function updateTemplate(templateId: string, patch: Partial<EmailTemplate>): Promise<EmailTemplate> {
  const res = await fetch(`${API_BASE}/email-templates/${encodeURIComponent(templateId)}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function getTemplate(templateId: string): Promise<EmailTemplate> {
  const res = await fetch(`${API_BASE}/email-templates/${encodeURIComponent(templateId)}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function listMyTemplates(channel?: EmailChannel): Promise<EmailTemplate[]> {
  const params = channel ? `?channel=${encodeURIComponent(channel)}` : "";
  const res = await fetch(`${API_BASE}/email-templates/mine${params}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listAllTemplates(channel?: EmailChannel): Promise<EmailTemplate[]> {
  const params = channel ? `?channel=${encodeURIComponent(channel)}` : "";
  const res = await fetch(`${API_BASE}/email-templates/all${params}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function previewTemplate(templateId: string): Promise<TemplatePreview> {
  const res = await fetch(`${API_BASE}/email-templates/${encodeURIComponent(templateId)}/preview`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function fetchMergeFields(): Promise<MergeField[]> {
  const res = await fetch(`${API_BASE}/email-templates/merge-fields`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function fetchMergeValues(personId: string): Promise<MergeValues> {
  const res = await fetch(`${API_BASE}/email-templates/merge-values/${encodeURIComponent(personId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function previewPersonalized(templateId: string, personId: string): Promise<PersonalizedPreview> {
  const res = await fetch(
    `${API_BASE}/email-templates/${encodeURIComponent(templateId)}/personalize/${encodeURIComponent(personId)}`,
    { headers: { ...authHeaders() } }
  );
  return handle(res);
}

export async function draftFromWizard(input: {
  channel: EmailChannel;
  goal: string;
  audience_description: string;
  tone: string;
}): Promise<EmailTemplate> {
  const res = await fetch(`${API_BASE}/email-templates/wizard`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify(input),
  });
  return handle(res);
}

export async function fetchEmailDesignAccess():Promise<{theme_ids:string[];websites:{id:string;name:string;theme_id:string;dealer_name?:string;address?:string}[]}> {
 return handle(await fetch(`${API_BASE}/email-templates/design-access`,{headers:authHeaders()}));
}
