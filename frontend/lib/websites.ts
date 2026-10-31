// Website Builder overhaul (session 85). Sam: "the last bit is the website... it needs
// to be a full website builder, with drag and drop functionality, layout templates...
// image selection, inventory control... contact forms that feed into the crm, live
// chat functionality (wired into the crm)... each template section should have ai
// writing abilities... a toggle for customers between a traditional website and a
// drivefinder.xyz ai powered car builder... adjust the seo per page, control the DNS,
// and preview the site... personal url functionality... deployed by the sales rep or
// marketing / events... google analytics / umami style reporting... ai setup wizard."
//
// Talks to backend/core/websites_api.py (existing + session-85 additions),
// backend/core/personal_sites_api.py (new), and backend/core/website_chat_api.py
// (new). Includes both the authenticated builder-side calls (used by
// components/WebsiteBuilderBoard.tsx) and the PUBLIC, unauthenticated calls (no
// Authorization header sent) a real dealership-visitor-facing page would use --
// included here so a future public-facing page doesn't need a second client.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

// --- Types ---------------------------------------------------------------------

export type SectionField = {
  key: string;
  label: string;
  type: "text" | "textarea";
  required?: boolean;
  default?: unknown;
  ai_writable?: boolean;
};

export type SectionTemplate = {
  key: string;
  name: string;
  description: string;
  fields: SectionField[];
};

export type SiteTemplate = {
  key: string;
  name: string;
  dealer_type: "independent" | "franchise";
  description: string;
  pages: Record<string, { section_key: string; fields: Record<string, unknown>; locked: boolean }[]>;
};

// Freeform drag-and-drop canvas (2026-07-18) -- a section's real, stored pixel
// position/size on the CANVAS_WIDTH=1200 virtual canvas (backend/core/websites.py).
// Only meaningful when the page's own layout_mode === "canvas"; ignored entirely in
// "structured" mode, same as the backend.
export type SectionLayout = { x: number; y: number; width: number; height: number };

// Website Personalization (2026-07-19) -- a real per-section overlay matched against
// a real visitor's utm_source/referrer at render time. Never a second copy of a
// section's fields -- see backend/core/websites.py's add_personalization_variant()/
// _select_personalization_variant() docstrings.
export type PersonalizationVariant = {
  id: string;
  match: { utm_source: string | null; referrer_contains: string | null };
  field_overrides: Record<string, unknown>;
  created_by: string | null;
  created_at: string;
};

export type WebsiteSection = {
  social_links?: Record<string, string>;
  section_key: string;
  fields: Record<string, unknown>;
  locked: boolean;
  layout?: SectionLayout;
  live_vehicles?: Record<string, unknown>[];
  live_options?: Record<string, unknown>[];
  // Digital Retail widgets (2026-07-24, DR-5) -- resolved at render time by
  // backend/core/websites.py render_page().
  payment_config?: { default_down: number; default_term_months: number; assumed_apr: number };
  buy_online_level?: "browse" | "build" | "negotiate" | "purchase";
  delivery_options?: { store_pickup: boolean; home_delivery: boolean; try_before_you_buy: boolean; radius_miles: number };
  personalization_variants?: PersonalizationVariant[];
  personalization_applied?: { variant_id: string; match: PersonalizationVariant["match"] } | null;
};

export type WebsitePage = { sections: WebsiteSection[]; layout_mode?: "structured" | "canvas" };

export type PageSeo = { meta_title: string | null; meta_description: string | null; og_image_url: string | null };

export type AdminSettings = {
  custom_domain: string | null;
  meta_title: string | null;
  meta_description: string | null;
  sitemap_enabled: boolean;
  block_ai_crawlers: boolean;
  allow_search_engines: boolean;
  google_analytics_id: string | null;
  umami_site_id: string | null;
  umami_script_url: string | null;
  facebook_pixel_id: string | null;
  custom_head_snippet: string | null;
  custom_body_snippet: string | null;
  branding_mode: "independent" | "oem";
  oem_name: string | null;
  oem_logo_url: string | null;
  page_seo: Record<string, PageSeo>;
  ai_receptionist_enabled: boolean;
  conversion_goals?: {metric:string;target:number;enabled:boolean}[];
};

export type LibraryImage = { id: string; url: string; label: string | null; added_by: string | null; added_at: string };

export type HistoryEntry = { action: string; by: string | null; at: string; notes: string | null };

export type Website = {
  studio_events?: WebsiteStudioRenderedEvent[];
  studio_locations?: { id: string; name: string; address: string }[];
  studio_config?: WebsiteStudioConfig;
  studio_revision?: number;
  id: string;
  name: string;
  status: "draft" | "pending_approval" | "published" | "rejected";
  mode: "traditional" | "dealer_gpt";
  pages: Record<string, WebsitePage>;
  owners: string[];
  admin_settings: AdminSettings;
  image_library: LibraryImage[];
  history: HistoryEntry[];
  requested_by: string;
  reviewed_by: string | null;
  review_notes: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
  effective_mode?: string;
  both_modes_available?: boolean;
};

export type WebsiteStudioEvent = {
  template_id: string;
  enabled: boolean;
  title?: string;
  title_es?: string;
  summary?: string;
  summary_es?: string;
  terms?: string;
  terms_es?: string;
  starts_on?: string;
  ends_on?: string;
  image_url?: string;
  banner_url?: string;
  vehicle_ids: string[];
};

export type WebsiteStudioRenderedEvent = {
  id: string; title: string; title_es: string; summary: string; summary_es: string;
  terms: string; terms_es: string; starts_on: string; ends_on: string;
  image_url: string; banner_url: string; image_alt: string; image_alt_es: string;
  background: string; accent: string;
  vehicles: { id: string; year?: string | number; make?: string; model?: string; price?: number | string; image_url?: string; location_id?: string | null; location_name?: string | null; location_address?: string | null }[];
};

export type WebsiteStudioConfig = {
  approved_template?: import("@/components/LoneStarCustomizer").LoneStarConfig;
  lone_star?: import("@/components/LoneStarCustomizer").LoneStarConfig;
  version: 1;
  theme_id: string;
  language: "en" | "es";
  social_links: Record<string, string>;
  backgrounds: Record<string, string>;
  events: WebsiteStudioEvent[];
};

export async function saveWebsiteStudio(websiteId: string, config: WebsiteStudioConfig, expectedRevision: number): Promise<Website> {
  return handle(await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/studio`, {
    method: "PUT", headers: { ...authHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ config, expected_revision: expectedRevision }),
  }));
}

export async function getWebsiteStudioInventory(websiteId: string): Promise<WebsiteStudioRenderedEvent["vehicles"]> {
  return handle(await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/studio/inventory`, { headers: authHeaders() }));
}

export type BotTraffic = {
  bot_views: number;
  human_views: number;
  by_bot_name: Record<string, number>;
  note: string;
};

export type WebsiteAnalytics = {
  traffic?: {conversions:Record<string,number>;goals:{metric:string;target:number;enabled:boolean;actual:number}[];days:number;sessions:number;pageviews:number;leads:number;active_sessions:number;by_day:Record<string,number>;sources:Record<string,number>;devices:Record<string,number>;browsers:Record<string,number>;pages:Record<string,number>;events:Record<string,number>;bot_events:number;note:string};
  website_id: string;
  total_views: number;
  by_page: Record<string, number>;
  by_day: Record<string, number>;
  bot_traffic: BotTraffic;
  note: string;
};

export type PersonalSite = {
  id: string;
  employee_id: string;
  parent_website_id: string | null;
  slug: string;
  status: "draft" | "active" | "inactive";
  headline: string | null;
  subheadline: string | null;
  bio: string | null;
  photo_url: string | null;
  phone: string | null;
  email: string | null;
  cta_text: string | null;
  calendar_link: string | null;
  review_link?: string | null;
  featured_vehicle_ids: string[];
  history: HistoryEntry[];
  created_at: string;
  updated_at: string;
};

export type PersonalSiteRendered = Omit<PersonalSite, "featured_vehicle_ids"> & {
  featured_vehicles: Record<string, unknown>[];
  branding: { branding_mode: string; oem_name: string | null; oem_logo_url: string | null };
};

export type PublicPersonalSite = Pick<PersonalSiteRendered,
  "slug" | "headline" | "subheadline" | "bio" | "photo_url" | "phone" |
  "email" | "cta_text" | "calendar_link" | "review_link" | "featured_vehicles" | "branding">;

export type ChatDepartment = "sales" | "service" | "finance" | "general";

export type ChatSession = {
  id: string;
  website_id: string;
  website_name?: string | null; // only present on the unified cross-site inbox
  visitor_name: string | null;
  visitor_email: string | null;
  department?: ChatDepartment;
  status: "open" | "claimed" | "closed";
  claimed_by: string | null;
  lead_id: string | null;
  created_at: string;
  updated_at: string;
  last_message_at: string | null;
  last_ai_reply_at?: string | null;
};

export type ChatMessage = {
  id: string;
  session_id: string;
  sender: "visitor" | "employee" | "ai";
  sender_id: string | null;
  body: string;
  ai_generated?: boolean;
  created_at: string;
};

function hdrs(): Record<string, string> {
  return { "Content-Type": "application/json", ...authHeaders() };
}

// --- Catalogs --------------------------------------------------------------------

export async function listSectionTemplates(): Promise<SectionTemplate[]> {
  const res = await fetch(`${API_BASE}/websites/sections`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listPageKeys(): Promise<{ key: string; label: string }[]> {
  const res = await fetch(`${API_BASE}/websites/pages`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listModes(): Promise<string[]> {
  const res = await fetch(`${API_BASE}/websites/modes`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listSiteTemplates(dealerType?: string): Promise<SiteTemplate[]> {
  const params = new URLSearchParams();
  if (dealerType) params.set("dealer_type", dealerType);
  const res = await fetch(`${API_BASE}/website-templates?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

// --- Sites: create/list/fetch ------------------------------------------------------

export async function createWebsite(name: string, mode: string = "traditional"): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites`, { method: "POST", headers: hdrs(), body: JSON.stringify({ name, mode }) });
  return handle(res);
}

export async function createWebsiteWizard(dealershipInfo: Record<string, unknown>, mode: string = "traditional"): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/wizard`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ dealership_info: dealershipInfo, mode }),
  });
  return handle(res);
}

export async function listMyWebsites(): Promise<Website[]> {
  const res = await fetch(`${API_BASE}/websites`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listPendingWebsites(): Promise<Website[]> {
  const res = await fetch(`${API_BASE}/websites/pending`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getWebsite(websiteId: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function submitWebsite(websiteId: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/submit`, { method: "POST", headers: { ...authHeaders() } });
  return handle(res);
}

export async function approveWebsite(websiteId: string, notes?: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/approve`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ notes: notes || null }),
  });
  return handle(res);
}

export async function rejectWebsite(websiteId: string, notes?: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/reject`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ notes: notes || null }),
  });
  return handle(res);
}

// --- Sections: add/remove/lock/reorder/regenerate ----------------------------------

export async function addSection(websiteId: string, pageKey: string, sectionKey: string, fields: Record<string, unknown>): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/sections`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ section_key: sectionKey, fields }),
  });
  return handle(res);
}

export async function updateSectionFields(websiteId: string, pageKey: string, sectionIndex: number, fields: Record<string, unknown>): Promise<Website> {
  const res = await fetch(
    `${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/sections/${sectionIndex}/edit`,
    { method: "POST", headers: hdrs(), body: JSON.stringify({ fields }) }
  );
  return handle(res);
}

export async function removeSection(websiteId: string, pageKey: string, sectionIndex: number): Promise<Website> {
  const res = await fetch(
    `${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/sections/${sectionIndex}/remove`,
    { method: "POST", headers: { ...authHeaders() } }
  );
  return handle(res);
}

export async function setSectionLocked(websiteId: string, pageKey: string, sectionIndex: number, locked: boolean): Promise<Website> {
  const res = await fetch(
    `${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/sections/${sectionIndex}/lock`,
    { method: "POST", headers: hdrs(), body: JSON.stringify({ locked }) }
  );
  return handle(res);
}

export async function reorderSections(websiteId: string, pageKey: string, newOrder: number[]): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/reorder`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ new_order: newOrder }),
  });
  return handle(res);
}

// --- Website Personalization (2026-07-19) -------------------------------------------

export async function listPersonalizationVariants(
  websiteId: string,
  pageKey: string,
  sectionIndex: number
): Promise<{ variants: PersonalizationVariant[] }> {
  const res = await fetch(
    `${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/sections/${sectionIndex}/personalization-variants`,
    { headers: { ...authHeaders() } }
  );
  return handle(res);
}

export async function addPersonalizationVariant(
  websiteId: string,
  pageKey: string,
  sectionIndex: number,
  match: { utm_source?: string; referrer_contains?: string },
  fieldOverrides: Record<string, unknown>
): Promise<Website & { error?: string }> {
  const res = await fetch(
    `${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/sections/${sectionIndex}/personalization-variants`,
    { method: "POST", headers: hdrs(), body: JSON.stringify({ match, field_overrides: fieldOverrides }) }
  );
  const data = await res.json();
  // Same "return the error alongside the shape, don't throw" convention
  // regenerateSection() already established -- a validation rejection (e.g. "needs at
  // least one match rule") is a normal, expected outcome here, not a network failure.
  if (!res.ok && !("error" in data)) {
    throw new Error("Unable to reach NXTDeal backend.");
  }
  return data as Website & { error?: string };
}

export async function removePersonalizationVariant(
  websiteId: string,
  pageKey: string,
  sectionIndex: number,
  variantId: string
): Promise<Website> {
  const res = await fetch(
    `${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/sections/${sectionIndex}/personalization-variants/${encodeURIComponent(variantId)}/remove`,
    { method: "POST", headers: { ...authHeaders() } }
  );
  return handle(res);
}

// Freeform drag-and-drop canvas (2026-07-18) -- Sam: "have a button that says edit
// website where you can open it up fully into a wix drag and drop, fully editable
// website builder." The real, deferred "much larger build" from session 90.
export const CANVAS_WIDTH = 1200;

export async function setPageLayoutMode(websiteId: string, pageKey: string, mode: "structured" | "canvas"): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/layout-mode`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ mode }),
  });
  return handle(res);
}

export async function setSectionLayout(
  websiteId: string,
  pageKey: string,
  sectionIndex: number,
  layout: SectionLayout
): Promise<Website> {
  const res = await fetch(
    `${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/sections/${sectionIndex}/layout`,
    { method: "POST", headers: hdrs(), body: JSON.stringify(layout) }
  );
  return handle(res);
}

export async function regenerateSection(
  websiteId: string,
  pageKey: string,
  sectionIndex: number,
  instructions?: string
): Promise<Website & { error?: string }> {
  const res = await fetch(
    `${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/sections/${sectionIndex}/regenerate`,
    { method: "POST", headers: hdrs(), body: JSON.stringify({ instructions: instructions || null }) }
  );
  // Regeneration failures still return the (unchanged) website alongside an error --
  // surface both rather than throwing, so the caller can show "AI failed, nothing lost".
  const data = await res.json();
  return data as Website & { error?: string };
}

export async function applySiteTemplate(websiteId: string, templateKey: string, dealershipName?: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/apply-template`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ template_key: templateKey, dealership_name: dealershipName || null }),
  });
  return handle(res);
}

export async function setMode(websiteId: string, mode: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/mode`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ mode }),
  });
  return handle(res);
}

export async function addOwner(websiteId: string, employeeId: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/owners`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ employee_id: employeeId }),
  });
  return handle(res);
}

export async function removeOwner(websiteId: string, employeeId: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/owners/remove`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ employee_id: employeeId }),
  });
  return handle(res);
}

// --- Image library -----------------------------------------------------------------

export async function addLibraryImage(websiteId: string, url: string, label?: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/images`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ url, label: label || null }),
  });
  return handle(res);
}

export async function removeLibraryImage(websiteId: string, imageId: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/images/${encodeURIComponent(imageId)}/remove`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function listLibraryImages(websiteId: string): Promise<LibraryImage[]> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/images`, { headers: { ...authHeaders() } });
  return handle(res);
}

// --- SEO / admin settings / DNS / robots / preview / analytics ---------------------

export async function updateAdminSettings(websiteId: string, patch: Partial<AdminSettings>): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/admin-settings`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function updatePageSeo(websiteId: string, pageKey: string, patch: Partial<PageSeo>): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/seo`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function getPageSeo(websiteId: string, pageKey: string): Promise<PageSeo> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/seo`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function getDnsInstructions(websiteId: string): Promise<Record<string, unknown>> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/dns-instructions`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getRobotsTxt(websiteId: string): Promise<{ robots_txt: string }> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/robots-txt`, { headers: { ...authHeaders() } });
  return handle(res);
}

// --- Enterprise SEO automation (session 113 follow-up) -----------------------------

export type SeoHealthCheck = { check: string; pass: boolean; detail: string };
export type SeoPageHealth = { page_key: string; score_pct: number; checks: SeoHealthCheck[] };
export type SeoHealth = {
  website_id: string;
  overall_score_pct: number;
  pages: SeoPageHealth[];
  site_checks: SeoHealthCheck[];
};

export async function getSitemapXml(websiteId: string): Promise<{ sitemap_xml: string; url_count: number; domain: string }> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/sitemap-xml`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getSeoHealth(websiteId: string): Promise<SeoHealth> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/seo-health`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getStructuredData(websiteId: string): Promise<{ json_ld: Record<string, unknown> }> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/structured-data`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function generatePageSeoCopy(websiteId: string, pageKey: string): Promise<{ meta_title: string; meta_description: string; ai_generated: boolean }> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/pages/${encodeURIComponent(pageKey)}/generate-seo-copy`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function previewWebsite(websiteId: string, modeOverride?: string): Promise<Website> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/preview`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ mode_override: modeOverride || null }),
  });
  return handle(res);
}

export async function getWebsiteAnalytics(websiteId: string, days = 30): Promise<WebsiteAnalytics> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/analytics?days=${days}`, { headers: { ...authHeaders() } });
  return handle(res);
}

// --- PUBLIC: real dealership visitor-facing calls (no Authorization sent) ----------

export async function publicGetWebsite(websiteId: string, mode?: string, utmSource?: string): Promise<Website> {
  const params = new URLSearchParams();
  if (mode) params.set("mode", mode);
  // Website Personalization (2026-07-19) -- utm_source rides along as a real query
  // param a visitor's own URL carries; the matching Referer header is sent
  // automatically by the browser, read server-side, never set here.
  if (utmSource) params.set("utm_source", utmSource);
  const res = await fetch(`${API_BASE}/public/websites/${encodeURIComponent(websiteId)}?${params.toString()}`);
  return handle(res);
}

export type VehicleLandingPage = {
  theme_id?: string;
  social_links?: Record<string, string>;
  location_id?: string | null;
  location_name?: string | null;
  location_address?: string | null;
  website_id: string;
  website_name: string | null;
  vehicle_id: string;
  available: boolean;
  year: number | string | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  color: string | null;
  condition: string | null;
  mileage: number | string | null;
  price: number | string | null;
  vin: string | null;
  stock_number: string | null;
  images: string[];
  description: string | null;
  description_ai_generated: boolean;
  description_generated_at: string | null;
};

export async function publicGetVehiclePage(websiteId: string, vehicleId: string): Promise<VehicleLandingPage> {
  const res = await fetch(`${API_BASE}/public/websites/${encodeURIComponent(websiteId)}/vehicles/${encodeURIComponent(vehicleId)}`);
  return handle(res);
}

export async function regenerateVehicleDescription(
  websiteId: string,
  vehicleId: string
): Promise<{ vehicle_id: string; description: string; ai_generated: boolean }> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/vehicles/${encodeURIComponent(vehicleId)}/regenerate-description`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function publicSubmitContactForm(
  websiteId: string,
  input: { page_key: string; section_index: number; name: string; email?: string; phone?: string; message?: string; vehicle_id?: string; intent?: string; request_id?: string }
): Promise<{ lead_id: string; assigned_to: string }> {
  const res = await fetch(`${API_BASE}/public/websites/${encodeURIComponent(websiteId)}/contact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle(res);
}

// --- Personal URL microsites --------------------------------------------------------

export async function checkPersonalSiteSlug(slug: string): Promise<{ slug: string; available: boolean }> {
  const res = await fetch(`${API_BASE}/personal-sites/check-slug?slug=${encodeURIComponent(slug)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function createPersonalSite(slug: string, parentWebsiteId?: string): Promise<PersonalSite> {
  const res = await fetch(`${API_BASE}/personal-sites`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ slug, parent_website_id: parentWebsiteId || null }),
  });
  return handle(res);
}

export async function getMyPersonalSite(): Promise<PersonalSite | null> {
  const res = await fetch(`${API_BASE}/personal-sites/mine`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function listPersonalSites(mineOnly: boolean = true): Promise<PersonalSite[]> {
  const res = await fetch(`${API_BASE}/personal-sites?mine_only=${mineOnly}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getPersonalSite(siteId: string): Promise<PersonalSiteRendered> {
  const res = await fetch(`${API_BASE}/personal-sites/${encodeURIComponent(siteId)}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function updatePersonalSite(siteId: string, patch: Partial<PersonalSite>): Promise<PersonalSite> {
  const res = await fetch(`${API_BASE}/personal-sites/${encodeURIComponent(siteId)}`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ patch }),
  });
  return handle(res);
}

export async function setPersonalSiteSlug(siteId: string, slug: string): Promise<PersonalSite> {
  const res = await fetch(`${API_BASE}/personal-sites/${encodeURIComponent(siteId)}/slug`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ slug }),
  });
  return handle(res);
}

export async function setPersonalSiteParent(siteId: string, parentWebsiteId: string | null): Promise<PersonalSite> {
  const res = await fetch(`${API_BASE}/personal-sites/${encodeURIComponent(siteId)}/parent`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ parent_website_id: parentWebsiteId }),
  });
  return handle(res);
}

export async function setPersonalSiteStatus(siteId: string, status: PersonalSite["status"]): Promise<PersonalSite> {
  const res = await fetch(`${API_BASE}/personal-sites/${encodeURIComponent(siteId)}/status`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ status }),
  });
  return handle(res);
}

export async function previewPersonalSite(siteId: string): Promise<PersonalSiteRendered> {
  const res = await fetch(`${API_BASE}/personal-sites/${encodeURIComponent(siteId)}/preview`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function getPersonalSiteAnalytics(siteId: string): Promise<{ personal_site_id: string; total_views: number; by_day: Record<string, number> }> {
  const res = await fetch(`${API_BASE}/personal-sites/${encodeURIComponent(siteId)}/analytics`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function publicGetPersonalSite(slug: string): Promise<PublicPersonalSite> {
  const res = await fetch(`${API_BASE}/public/personal-sites/${encodeURIComponent(slug)}`);
  return handle(res);
}

export async function publicSubmitPersonalSiteContactForm(
  slug: string,
  input: { name: string; email?: string; phone?: string; message?: string }
): Promise<{ lead_id: string; assigned_to: string }> {
  const res = await fetch(`${API_BASE}/public/personal-sites/${encodeURIComponent(slug)}/contact`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return handle(res);
}

// --- Live chat, wired into the CRM --------------------------------------------------

export async function publicStartChat(
  websiteId: string,
  visitorName?: string,
  visitorEmail?: string,
  initialMessage?: string,
  department?: ChatDepartment
): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/public/websites/${encodeURIComponent(websiteId)}/chat/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      visitor_name: visitorName || null,
      visitor_email: visitorEmail || null,
      initial_message: initialMessage || null,
      department: department || null,
    }),
  });
  return handle(res);
}

export async function publicListChatDepartments(): Promise<ChatDepartment[]> {
  const res = await fetch(`${API_BASE}/public/chat/departments`);
  return handle(res);
}

export async function publicGetChatSession(sessionId: string): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/public/chat/${encodeURIComponent(sessionId)}`);
  return handle(res);
}

export async function publicSendChatMessage(sessionId: string, body: string): Promise<ChatMessage> {
  const res = await fetch(`${API_BASE}/public/chat/${encodeURIComponent(sessionId)}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ body }),
  });
  return handle(res);
}

export async function publicListChatMessages(sessionId: string, since?: string): Promise<ChatMessage[]> {
  const params = new URLSearchParams();
  if (since) params.set("since", since);
  const res = await fetch(`${API_BASE}/public/chat/${encodeURIComponent(sessionId)}/messages?${params.toString()}`);
  return handle(res);
}

export async function listChatInbox(websiteId: string): Promise<ChatSession[]> {
  const res = await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/chat/sessions`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function sendChatReply(sessionId: string, body: string): Promise<ChatMessage> {
  const res = await fetch(`${API_BASE}/websites/chat/${encodeURIComponent(sessionId)}/reply`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify({ body }),
  });
  return handle(res);
}

export async function listChatMessages(sessionId: string, since?: string): Promise<ChatMessage[]> {
  const params = new URLSearchParams();
  if (since) params.set("since", since);
  const res = await fetch(`${API_BASE}/websites/chat/${encodeURIComponent(sessionId)}/messages?${params.toString()}`, {
    headers: { ...authHeaders() },
  });
  return handle(res);
}

export async function claimChatSession(sessionId: string): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/websites/chat/${encodeURIComponent(sessionId)}/claim`, { method: "POST", headers: { ...authHeaders() } });
  return handle(res);
}

export async function closeChatSession(sessionId: string): Promise<ChatSession> {
  const res = await fetch(`${API_BASE}/websites/chat/${encodeURIComponent(sessionId)}/close`, { method: "POST", headers: { ...authHeaders() } });
  return handle(res);
}

export async function promoteChatSession(
  sessionId: string,
  input: { name?: string; email?: string; phone?: string } = {}
): Promise<{ lead_id: string; assigned_to: string }> {
  const res = await fetch(`${API_BASE}/websites/chat/${encodeURIComponent(sessionId)}/promote`, {
    method: "POST",
    headers: hdrs(),
    body: JSON.stringify(input),
  });
  return handle(res);
}

// --- Omnichannel / AI Receptionist (session 113 follow-up) ---------------------------

export async function listUnifiedChatInbox(status?: string, department?: ChatDepartment): Promise<ChatSession[]> {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (department) params.set("department", department);
  const res = await fetch(`${API_BASE}/chat/inbox?${params.toString()}`, { headers: { ...authHeaders() } });
  return handle(res);
}

export async function generateAiChatReply(sessionId: string): Promise<ChatMessage> {
  const res = await fetch(`${API_BASE}/chat/${encodeURIComponent(sessionId)}/ai-reply`, {
    method: "POST",
    headers: { ...authHeaders() },
  });
  return handle(res);
}


export async function createStudioWebsite(name: string, themeId: string, requestId: string, mode: "traditional" | "dealer_gpt"): Promise<Website> {
  const response = await fetch(`${API_BASE}/website-studio/sites`, {
    method: "POST", headers: hdrs(),
    body: JSON.stringify({ name, theme_id: themeId, request_id: requestId, mode }),
  });
  return handle(response);
}


export async function startWebsiteDraft(websiteId: string): Promise<Website> {
  return handle(await fetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}/studio/draft`, {
    method: "POST", headers: authHeaders(),
  }));
}


export type PublicInventoryPage = {
  vehicles: Record<string, unknown>[]; total: number; page: number; page_size: number; pages: number;
  locations: { id: string; name: string; count: number }[];
};
export async function publicWebsiteInventory(websiteId: string, params: URLSearchParams, signal?: AbortSignal): Promise<PublicInventoryPage> {
  return handle(await fetch(`${API_BASE}/public/websites/${encodeURIComponent(websiteId)}/inventory?${params}`, { signal }));
}
