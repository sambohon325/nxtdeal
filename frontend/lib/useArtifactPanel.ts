"use client";

// Shared workspace-panel state + loaders (session 27 — extracted out of /admin so
// /workspace, /readiness, and /network can render the exact same set of chat-triggered
// panels instead of four separately-drifting copies. Per Sam: "all of NXTDeal needs to
// function with the same ideology."). One artifact renders at a time, same
// single-item-array pattern established in /workspace originally.
//
// Covers every suggestion field core/ai_api.py's ask() can attach:
//   - suggested_dashboard      -> loadDashboardArtifact(key)
//   - suggested_profile        -> loadProfileArtifact(entityId)
//   - suggested_admin_panel    -> loadAdminPanelArtifact(key)   (roster/audit/compliance)
//   - suggested_reset_password -> loadResetConfirmArtifact(employeeId) -> confirmResetPassword
//   - suggested_panel          -> loadGeneralPanelArtifact(key) (readiness_score/
//                                  performance_rank/growth_opportunities)
//
// Any page can use as much or as little of this as its suggested prompts cover — the
// ADMIN-only panels/reset-password will just never get suggested to a non-admin caller
// (core/ai_api.py's own role gate), so wiring them in everywhere is harmless, not a
// security surface.

import { useState } from "react";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/api";
import { authHeaders, isAuthError, clearSession } from "@/lib/auth";
import {
  displayName,
  type Profile,
  type FallbackProfile,
  type CustomerProfile,
  type EmployeeProfile,
  type VehicleProfile,
} from "@/components/EntityProfile";
import type { PinKind } from "@/lib/pins";

function pinLabelForProfile(profile: Profile): string {
  // Explicit if/return + cast per entity type (session 87 -- the comment here already
  // correctly diagnosed the narrowing problem, but the fix wasn't actually applied: an
  // if-chain doesn't narrow away FallbackProfile any better than a ternary would, since
  // FallbackProfile's entity_type is a plain `string`, not a literal, so TypeScript
  // can't prove it's excluded either way. This was a real, previously-uncaught type
  // error -- see components/EntityProfile.tsx's identical fix for the fuller story.
  if (profile.entity_type === "Customer") {
    return `Customer: ${displayName((profile as CustomerProfile).customer)}`;
  }

  if (profile.entity_type === "Employee") {
    return `Employee: ${displayName((profile as EmployeeProfile).employee)}`;
  }

  if (profile.entity_type === "Vehicle") {
    return `Vehicle: ${displayName((profile as VehicleProfile).vehicle)}`;
  }

  const fallback = profile as FallbackProfile;

  return `${profile.entity_type}: ${displayName(fallback.entity)}`;
}

export type CredentialRecord = {
  employee_id: string;
  role: string;
  must_change_password: boolean;
  created_by: string | null;
  created_at: string | null;
  email: string | null;
};

export type AuditEvent = {
  id: string;
  event_type: string;
  entity_id: string | null;
  actor: string;
  summary: string;
  details: Record<string, unknown>;
  timestamp: string;
};

export type AuditDashboard = {
  total_events: number;
  by_type: Record<string, number>;
  recent: AuditEvent[];
};

// Marketing asset design/approval workflow (session 30 -- phase 1 of folding
// NXTDeal's product suite into NXTDeal). Template-fill, not a freeform canvas (Sam's
// explicit scoping answer): pick a template, fill its fields, submit for MARKETING/
// ADMIN approval.
export type AssetTemplateField = { key: string; label: string; type: string; required: boolean };

export type AssetTemplate = {
  key: string;
  name: string;
  category: string;
  description: string;
  fields: AssetTemplateField[];
};

export type AssetRecord = {
  id: string;
  template_key: string;
  status: "draft" | "pending_approval" | "approved" | "rejected";
  fields: Record<string, string>;
  vehicle_id: string | null;
  campaign_id: string | null;
  requested_by: string;
  reviewed_by: string | null;
  review_notes: string | null;
  created_at: string;
  updated_at: string;
};

// Campaign & customer-lifecycle engine (session 31 -- phase 2 of folding NXTDeal's
// product suite into NXTDeal: the Bumper-style product line -- Retention, Inventory
// Ads, Finance renewal, Accessory Accelerator -- as one generic campaign engine).
// Audience targeting is a small structured form per campaign type (same "template-fill,
// no freeform canvas" philosophy as the asset workflow above), not a query builder.
export type CampaignAudienceField = {
  key: string;
  label: string;
  type: string;
  required: boolean;
  default?: number;
};

export type CampaignType = {
  key: string;
  name: string;
  category: string;
  description: string;
  default_channel: string;
  audience_fields: CampaignAudienceField[];
};

export type CampaignRecord = {
  id: string;
  campaign_type: string;
  name: string;
  channel: string;
  status: "draft" | "active" | "completed" | "cancelled";
  params: Record<string, unknown>;
  audience_ids: string[];
  audience_entity_type: string;
  audience_count: number;
  linked_asset_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  activated_at: string | null;
  completed_at: string | null;
  sent_count: number;
};

export type AudiencePreview = {
  campaign_type: string;
  entity_type: string;
  count: number;
  sample: { id: string; entity_type: string; name: string }[];
};

// Website / inventory builder (session 32 -- phase 3, the last piece of the NXTDeal
// suite integration before "DMS style systems"). Fixed page set (Home/Inventory/About/
// Contact), fixed section-template catalog -- template-fill, no freeform canvas, no AI
// image generation (dealer-supplied photo URLs only, matching the asset workflow's
// `photo_url` fields). The Inventory page's sections carry a `live_vehicles` array
// resolved server-side at fetch time (core/websites.py's render_page()) -- the
// DriveFinder-lite piece, always current with the graph rather than a stored copy.
export type WebsiteSectionField = {
  key: string;
  label: string;
  type: string;
  required: boolean;
  default?: number;
};

export type WebsiteSectionTemplate = {
  key: string;
  name: string;
  description: string;
  fields: WebsiteSectionField[];
};

export type WebsitePageInfo = { key: string; label: string };

export type LiveVehicle = {
  id: string;
  year: string | number | null;
  make: string | null;
  model: string | null;
  trim: string | null;
  price: string | number | null;
  mileage: string | number | null;
  image_url: string | null;
};

// Session 58 -- DealerGPT "build your car" configurator options, computed live from
// inventory (core/websites.py's get_car_builder_options()).
export type CarBuilderTrim = { trim: string; count: number; price_min: number | null; price_max: number | null };
export type CarBuilderModel = { model: string; trims: CarBuilderTrim[] };
export type CarBuilderMake = { make: string; models: CarBuilderModel[] };

export type WebsiteSection = {
  section_key: string;
  fields: Record<string, string>;
  locked?: boolean;
  live_vehicles?: LiveVehicle[];
  live_options?: CarBuilderMake[];
};

export type WebsitePage = { sections: WebsiteSection[] };

// Session 58 -- DNS/SEO/Bot/Analytics/OEM-branding admin controls (core/websites.py's
// _default_admin_settings()). Flat, one form's worth of fields.
export type WebsiteAdminSettings = {
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
};

export type WebsiteHistoryEntry = { action: string; by: string; at: string; notes: string | null };

export type WebsiteRecord = {
  id: string;
  name: string;
  status: "draft" | "pending_approval" | "published" | "rejected";
  mode: "traditional" | "dealer_gpt";
  pages: Record<string, WebsitePage>;
  owners: string[];
  admin_settings: WebsiteAdminSettings;
  history: WebsiteHistoryEntry[];
  requested_by: string;
  reviewed_by: string | null;
  review_notes: string | null;
  created_at: string;
  updated_at: string;
  published_at: string | null;
};

// Session 58 -- the AI setup wizard's input form shape (POST /websites/wizard's
// dealership_info body).
export type WizardDealershipInfo = {
  dealership_name: string;
  address?: string;
  phone?: string;
  hours?: string;
  branding_mode: "independent" | "oem";
  oem_name?: string;
  oem_logo_url?: string;
  hero_image_url?: string;
  google_rating_text?: string;
  google_place_id?: string;
  social_links?: { facebook?: string; instagram?: string; tiktok?: string; x?: string };
  tone?: string;
};

// DMS Deal Desk (session 33 -- phase 1 of the DMS buildout modeled on DealerSocket/
// Tekion's Desking + F&I + Contracting modules). A Deal moves through
// desking (multiple pricing/term scenarios, compared side by side per Sam's explicit
// scoping choice) -> financing (in-house/BHPH or an outside Lender, simulated
// submit/decide) -> a generated on-screen contract -> funded (creates a real
// FinanceContract visible everywhere else in NXTDeal).
export type DealScenario = {
  id: string;
  label: string;
  sale_price: number;
  down_payment: number;
  term_months: number;
  amount_financed: number;
  estimated_apr: number;
  estimated_monthly_payment: number;
};

export type FinancingTerms = {
  apr: number;
  term_months: number;
  amount_financed: number;
  down_payment: number;
  monthly_payment: number;
};

export type DealContract = {
  deal_id: string;
  customer_id: string;
  customer_name: string;
  vehicle_id: string;
  vehicle_description: string;
  vin: string | null;
  sale_price: number;
  trade_in_value: number | null;
  down_payment: number;
  amount_financed: number;
  apr: number;
  term_months: number;
  monthly_payment: number;
  financing_type: string | null;
  lender_name: string | null;
  generated_at: string;
  disclosures: string[];
};

export type DealRecord = {
  id: string;
  customer_id: string;
  vehicle_id: string;
  trade_in: { vin?: string; description?: string; value: number } | null;
  status: "desking" | "financing" | "contract" | "funded" | "cancelled";
  scenarios: DealScenario[];
  selected_scenario_id: string | null;
  financing_type: "in_house" | "outside_lender" | null;
  lender_id: string | null;
  financing_status: "not_started" | "submitted" | "approved" | "declined" | "countered";
  financing_terms: FinancingTerms | null;
  financing_notes?: string | null;
  contract: DealContract | null;
  finance_contract_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  funded_at: string | null;
};

export type LenderOption = { id: string; name: string };

// Department Intelligence (session 35, renamed session 68 -- dropping the "Bumper BI"
// branding) -- `value` is always the raw number; `format` tells the UI how to render it
// ("currency"/"percent"/"number"/"ratio"), `suffix` is an optional unit tag like "/hr".
// `delta_pct`/`has_history`/`compared_to` come from core/kpi_snapshots.py's
// daily-snapshot trend math -- `has_history` is false (and `delta_pct` null) the first
// time a department's ever been opened, since there's no prior day to compare against
// yet.
export type IntelligenceKpi = {
  key: string;
  label: string;
  value: number;
  format: "currency" | "percent" | "number" | "ratio";
  suffix: string | null;
  delta_pct: number | null;
  has_history: boolean;
  compared_to: string | null;
};

export type IntelligenceCapability = { title: string; description: string };

export type IntelligenceAlert = { label: string; value: number; description: string };

export type IntelligenceDashboard = {
  department: string;
  title: string;
  subtitle: string;
  capabilities: IntelligenceCapability[];
  kpis: IntelligenceKpi[];
  alert?: IntelligenceAlert;
};

export type IntelligenceDepartmentOption = { key: string; title: string; subtitle: string };

// Agentic bot layer (session 36).
export type BotCoverageRecord = {
  id: string;
  employee_id: string;
  activated_by: string;
  role: string;
  section: string;
  starts_at: string;
  ends_at: string;
  mode: "draft" | "auto";
  note: string | null;
  status: "active" | "ended";
  created_at: string;
  ended_at: string | null;
  ended_by: string | null;
};

// Employee value/effectiveness (session 37) -- ADMIN/OPERATIONS only, see
// core/employee_value.py.
export type EmployeeValueRecord = {
  employee_id: string;
  name: string;
  department: string | null;
  title: string | null;
  tier: string;
  monthly_value_estimate: number;
  sample_size: number;
  basis: "ledger" | "industry_estimate" | "blended";
  automation_coverage: {
    distinct_task_types: number;
    automatable_task_types: number;
    automation_pct: number;
  } | null;
  note: string;
  disclaimer: string;
};

// Compliance agent (session 38) -- ADMIN/OPERATIONS only, see core/compliance.py.
// `violations` mirrors core/compliance_rules.py's RULE_CATALOG shape exactly (law/
// citation/category/severity/description per failed rule).
export type ComplianceViolation = {
  rule_id: string;
  law: string;
  citation: string;
  category: string;
  severity: "high" | "medium";
  description: string;
};

export type ComplianceAlertRecord = {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  violations: ComplianceViolation[];
  status: "open" | "resolved" | "overridden";
  created_at: string;
  updated_at: string;
  resolved_by: string | null;
  resolved_at: string | null;
  resolution_notes: string | null;
  notified_employee_ids: string[];
};

export type Artifact =
  | { id: number; type: "roster"; title: string; records: CredentialRecord[] }
  | { id: number; type: "audit"; title: string; dashboard: AuditDashboard }
  | {
      id: number;
      type: "compliance_alerts_list";
      title: string;
      alerts: ComplianceAlertRecord[];
      notice: string;
    }
  | { id: number; type: "readiness_score"; title: string; score: number }
  | { id: number; type: "performance_rank"; title: string; rank: number }
  | {
      id: number;
      type: "growth_opportunities";
      title: string;
      opportunities: string[];
    }
  | { id: number; type: "reset_confirm"; title: string; employeeId: string }
  | {
      id: number;
      type: "reset_result";
      title: string;
      employeeId: string;
      tempPassword: string;
    }
  | { id: number; type: "profile"; title: string; entityId: string; profile: Profile }
  | {
      id: number;
      type: "dashboard";
      title: string;
      key: string;
      data: { name: string; value: number }[];
    }
  | { id: number; type: "asset_templates"; title: string; templates: AssetTemplate[] }
  | { id: number; type: "asset_form"; title: string; template: AssetTemplate }
  | { id: number; type: "asset_list"; title: string; mode: "pending" | "mine"; assets: AssetRecord[] }
  | { id: number; type: "asset_detail"; title: string; asset: AssetRecord }
  | { id: number; type: "campaign_types"; title: string; types: CampaignType[] }
  | { id: number; type: "campaign_form"; title: string; campaignType: CampaignType }
  | { id: number; type: "campaign_list"; title: string; mode: "pending" | "mine"; campaigns: CampaignRecord[] }
  | { id: number; type: "campaign_detail"; title: string; campaign: CampaignRecord }
  | {
      id: number;
      type: "website_sections";
      title: string;
      sections: WebsiteSectionTemplate[];
      pages: WebsitePageInfo[];
    }
  | { id: number; type: "website_list"; title: string; mode: "pending" | "mine"; websites: WebsiteRecord[] }
  | { id: number; type: "website_wizard"; title: string }
  | {
      id: number;
      type: "website_detail";
      title: string;
      website: WebsiteRecord;
      sectionTemplates: WebsiteSectionTemplate[];
      pageKeys: WebsitePageInfo[];
    }
  | { id: number; type: "deal_start"; title: string }
  | { id: number; type: "deal_list"; title: string; mode: "pending" | "mine"; deals: DealRecord[] }
  | { id: number; type: "deal_detail"; title: string; deal: DealRecord; lenders: LenderOption[] }
  | { id: number; type: "intelligence_departments"; title: string; departments: IntelligenceDepartmentOption[] }
  | { id: number; type: "intelligence_dashboard"; title: string; dashboard: IntelligenceDashboard }
  | { id: number; type: "bot_coverage_list"; title: string; coverage: BotCoverageRecord[] }
  | {
      id: number;
      type: "employee_value_list";
      title: string;
      employees: EmployeeValueRecord[];
      disclaimer: string;
    };

export const ADMIN_PANEL_LABELS: Record<string, string> = {
  roster: "Employee Roster",
  audit: "Audit Log",
  bot_coverage: "Bot Coverage",
};

export const GENERAL_PANEL_LABELS: Record<string, string> = {
  readiness_score: "Readiness Score",
  performance_rank: "Performance Rank",
  growth_opportunities: "Growth Opportunities",
};

export const ASSET_PANEL_LABELS: Record<string, string> = {
  templates: "Asset Templates",
  pending_approvals: "Pending Approvals",
  my_assets: "My Assets",
};

export const CAMPAIGN_PANEL_LABELS: Record<string, string> = {
  types: "Campaign Types",
  pending_campaigns: "Pending Campaigns",
  my_campaigns: "My Campaigns",
};

export const WEBSITE_PANEL_LABELS: Record<string, string> = {
  sections: "Website Builder",
  wizard: "Website Setup Wizard",
  pending_sites: "Pending Websites",
  my_sites: "My Websites",
};

export const DEAL_PANEL_LABELS: Record<string, string> = {
  start_deal: "the Deal Desk",
  pending_financing: "Deals Awaiting Financing",
  my_deals: "My Deals",
};

export const INTELLIGENCE_PANEL_LABELS: Record<string, string> = {
  departments: "Department Intelligence",
  sales: "Sales Intelligence",
  service: "Service Intelligence",
  parts: "Parts Intelligence",
  fi: "F&I Intelligence",
  executive: "Executive Overview",
};

function assetLabel(asset: AssetRecord): string {
  const name =
    asset.fields?.headline || asset.fields?.offer_title || asset.fields?.customer_name || asset.template_key;

  return `${name} (${asset.status})`;
}

function campaignLabel(campaign: CampaignRecord): string {
  return `${campaign.name} (${campaign.status})`;
}

function websiteLabel(website: WebsiteRecord): string {
  return `${website.name} (${website.status})`;
}

function dealLabel(deal: DealRecord): string {
  return `Deal ${deal.id} (${deal.status})`;
}

function formatDashboardTitle(key: string): string {
  return `${key.charAt(0).toUpperCase()}${key.slice(1)} Dashboard`;
}

// The various /dashboard/{key} endpoints don't share one response shape -- some
// (sales/service/finance/executive/velocity) return a flat dict of counts, but
// several of the most useful ones (workload/leaderboard/manager/escalations/followup)
// return a LIST of per-employee-or-lead records instead. The old naive
// `Object.entries(data).map(([name, value]) => ({name, value: Number(value) || 0}))`
// only handled the flat-dict case: called on an array it iterates numeric indices
// ("0", "1", "2"...) with each record object as the "value", and
// `Number(someObject)` is NaN, so `|| 0` silently zeroed out every bar -- the chart
// frame/axes still rendered (matching "builds the graph properly") while every bar
// was invisible and mislabeled (matching "doesn't show the data"). This normalizer
// handles both shapes plus mixed flat dicts that include a non-numeric field (e.g.
// salesperson_dashboard's "employee_id" string alongside real numeric counts, which
// used to render as a bogus zero-height bar).
function normalizeDashboardChartData(data: unknown): { name: string; value: number }[] {
  if (Array.isArray(data)) {
    if (data.length === 0) return [];

    if (typeof data[0] !== "object" || data[0] === null) {
      // Plain list of primitives (ids, states, etc) -- chart the distribution.
      const counts = new Map<string, number>();
      for (const item of data) {
        const key = String(item);
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      return Array.from(counts.entries()).map(([name, value]) => ({ name, value }));
    }

    const sample = data[0] as Record<string, unknown>;
    const numericKey = Object.keys(sample).find((k) => typeof sample[k] === "number");
    const labelKey = Object.keys(sample).find((k) => typeof sample[k] === "string");

    if (numericKey) {
      return (data as Record<string, unknown>[]).map((row, i) => ({
        name: labelKey ? String(row[labelKey]) : `#${i + 1}`,
        value: Number(row[numericKey]) || 0,
      }));
    }

    if (labelKey) {
      // No numeric metric on these records at all (purely descriptive) -- fall back
      // to a distribution by the label field so the chart still shows something real
      // instead of an all-zero bar per record.
      const counts = new Map<string, number>();
      for (const row of data as Record<string, unknown>[]) {
        const key = String(row[labelKey]);
        counts.set(key, (counts.get(key) ?? 0) + 1);
      }
      return Array.from(counts.entries()).map(([name, value]) => ({ name, value }));
    }

    return data.map((_, i) => ({ name: `#${i + 1}`, value: 1 }));
  }

  const record = data as Record<string, unknown>;
  const bars: { name: string; value: number }[] = [];

  for (const [name, value] of Object.entries(record)) {
    if (typeof value === "number" || typeof value === "boolean") {
      bars.push({ name: name.replace(/_/g, " "), value: Number(value) || 0 });
    } else if (value && typeof value === "object" && !Array.isArray(value)) {
      // One level of nested flat-numeric dict (e.g. pipeline_metrics' "pipeline":
      // {NEW: 10, CONTACTED: 5, ...}) -- flatten with a prefix rather than dropping it
      // silently, since that's real data the chart should surface.
      for (const [subName, subValue] of Object.entries(value as Record<string, unknown>)) {
        if (typeof subValue === "number") {
          bars.push({
            name: `${name.replace(/_/g, " ")}: ${subName.replace(/_/g, " ")}`,
            value: subValue,
          });
        }
      }
    }
  }

  return bars;
}

export function useArtifactPanel() {
  const router = useRouter();

  const [artifacts, setArtifacts] = useState<Artifact[]>([]);
  const [panelLoading, setPanelLoading] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);

  function clearArtifacts() {
    setArtifacts([]);
  }

  async function guardedFetch(url: string, init?: RequestInit): Promise<unknown | null> {
    const response = await fetch(url, {
      ...init,
      headers: { ...(init?.headers ?? {}), ...authHeaders() },
    });

    const data = await response.json();

    if (isAuthError(data)) {
      clearSession();
      router.push("/");
      return null;
    }

    if (!response.ok || data.error) {

      const error = new Error(data.error ?? `Backend returned ${response.status}`) as Error & {
        payload?: unknown;
      };

      // Compliance-blocked responses (session 38) carry compliance_violations/notice
      // alongside the generic error string -- attached here so callers that want to
      // show the actual failed rule(s), not just "Compliance check failed", can read
      // error.payload rather than losing that detail to the plain Error message.
      error.payload = data;

      throw error;
    }

    return data;
  }

  // Formats a blocked-action response's compliance_violations into a readable,
  // multi-line message -- used by fundDealAction/activateCampaignAction/
  // approveAssetAction/approveWebsiteAction below so a compliance block shows the
  // actual law/citation/description, not just a generic error string.
  function formatComplianceError(payload: unknown): string | null {
    const data = payload as {
      error?: string;
      compliance_violations?: ComplianceViolation[];
      notice?: string;
    };

    if (!data?.compliance_violations?.length) return null;

    const lines = data.compliance_violations.map(
      (v) => `- [${v.law}, ${v.citation}] ${v.description}`
    );

    return [data.error ?? "Compliance check failed.", ...lines].join("\n");
  }

  async function loadRosterArtifact() {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/auth/admin/credentials`);
      if (data === null) return;

      setArtifacts([
        { id: Date.now(), type: "roster", title: "Employee Roster", records: data as CredentialRecord[] },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadAuditArtifact() {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/dashboard/audit`);
      if (data === null) return;

      setArtifacts([
        { id: Date.now(), type: "audit", title: "Audit Log", dashboard: data as AuditDashboard },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  // Compliance agent (session 38) -- replaces the old static "score: 92" placeholder
  // card with the real ADMIN/OPERATIONS-visible alert list from core/compliance.py.
  // Readiness/performance/growth below remain the pre-existing placeholder metrics
  // (no real backend source for those yet) -- only compliance got a real engine this
  // session.
  async function loadComplianceAlertsArtifact() {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/compliance/alerts`);
      if (data === null) return;

      const payload = data as { alerts: ComplianceAlertRecord[]; notice: string };

      setArtifacts([
        {
          id: Date.now(),
          type: "compliance_alerts_list",
          title: "Compliance Alerts",
          alerts: payload.alerts ?? [],
          notice: payload.notice ?? "",
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function resolveComplianceAlertAction(alertId: string, notes?: string) {
    setPanelError(null);

    try {
      const data = await guardedFetch(`${API_BASE}/compliance/alerts/${alertId}/resolve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes ?? null }),
      });
      if (data === null) return;
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      return;
    }

    loadComplianceAlertsArtifact();
  }

  async function overrideComplianceAlertAction(alertId: string, notes: string) {
    setPanelError(null);

    try {
      const data = await guardedFetch(`${API_BASE}/compliance/alerts/${alertId}/override`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes }),
      });
      if (data === null) return;
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      return;
    }

    loadComplianceAlertsArtifact();
  }

  function loadReadinessScoreArtifact() {
    setPanelError(null);
    setArtifacts([{ id: Date.now(), type: "readiness_score", title: "Readiness Score", score: 84 }]);
  }

  function loadPerformanceRankArtifact() {
    setPanelError(null);
    setArtifacts([{ id: Date.now(), type: "performance_rank", title: "Performance Rank", rank: 87 }]);
  }

  function loadGrowthOpportunitiesArtifact() {
    setPanelError(null);
    setArtifacts([
      {
        id: Date.now(),
        type: "growth_opportunities",
        title: "Growth Opportunities",
        opportunities: ["Used Vehicles", "Service Retention", "F&I Attach Rate"],
      },
    ]);
  }

  function loadResetConfirmArtifact(employeeId: string) {
    setPanelError(null);
    setArtifacts([{ id: Date.now(), type: "reset_confirm", title: "Reset Password", employeeId }]);
  }

  async function confirmResetPassword(employeeId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/auth/admin/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ employee_id: employeeId }),
      });
      if (data === null) return;

      const result = data as { employee_id: string; temp_password: string };

      setArtifacts([
        {
          id: Date.now(),
          type: "reset_result",
          title: "Reset Password",
          employeeId: result.employee_id,
          tempPassword: result.temp_password,
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  function loadAdminPanelArtifact(key: string) {
    if (key === "roster") return loadRosterArtifact();
    if (key === "audit") return loadAuditArtifact();
    if (key === "bot_coverage") return loadBotCoverageArtifact();
  }

  async function loadBotCoverageArtifact() {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/bot/coverage`);
      if (data === null) return;

      setArtifacts([
        {
          id: Date.now(),
          type: "bot_coverage_list",
          title: "Bot Coverage",
          coverage: (data as { coverage: BotCoverageRecord[] }).coverage ?? [],
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadEmployeeValueArtifact() {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/employees/value`);
      if (data === null) return;

      const payload = data as { employees: EmployeeValueRecord[]; disclaimer: string };

      setArtifacts([
        {
          id: Date.now(),
          type: "employee_value_list",
          title: "Employee Value & Effectiveness",
          employees: payload.employees ?? [],
          disclaimer: payload.disclaimer ?? "",
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  function loadGeneralPanelArtifact(key: string) {
    if (key === "readiness_score") return loadReadinessScoreArtifact();
    if (key === "performance_rank") return loadPerformanceRankArtifact();
    if (key === "growth_opportunities") return loadGrowthOpportunitiesArtifact();
  }

  async function loadDashboardArtifact(key: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/dashboard/${key}`);
      if (data === null) return;

      const chartData = normalizeDashboardChartData(data);

      setArtifacts([
        { id: Date.now(), type: "dashboard", title: formatDashboardTitle(key), key, data: chartData },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadProfileArtifact(entityId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/profile/${encodeURIComponent(entityId)}`);
      if (data === null) return;

      const profile = data as Profile & { entity_type: string };

      setArtifacts([
        {
          id: Date.now(),
          type: "profile",
          title: `${profile.entity_type} Profile`,
          entityId,
          profile,
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadAssetTemplatesArtifact() {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/assets/templates`);
      if (data === null) return;

      setArtifacts([
        { id: Date.now(), type: "asset_templates", title: "Asset Templates", templates: data as AssetTemplate[] },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadAssetFormArtifact(templateKey: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/assets/templates`);
      if (data === null) return;

      const template = (data as AssetTemplate[]).find((t) => t.key === templateKey);

      if (!template) {
        setPanelError(`Unknown asset template '${templateKey}'`);
        return;
      }

      setArtifacts([{ id: Date.now(), type: "asset_form", title: template.name, template }]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadAssetListArtifact(mode: "pending" | "mine") {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const endpoint = mode === "pending" ? "/assets/pending" : "/assets/mine";
      const data = await guardedFetch(`${API_BASE}${endpoint}`);
      if (data === null) return;

      setArtifacts([
        {
          id: Date.now(),
          type: "asset_list",
          title: mode === "pending" ? "Pending Approvals" : "My Assets",
          mode,
          assets: data as AssetRecord[],
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadAssetDetailArtifact(assetId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/assets/${encodeURIComponent(assetId)}`);
      if (data === null) return;

      const asset = data as AssetRecord;

      setArtifacts([{ id: Date.now(), type: "asset_detail", title: assetLabel(asset), asset }]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function createAndSubmitAsset(
    templateKey: string,
    fields: Record<string, string>,
    vehicleId?: string,
    campaignId?: string
  ) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const created = await guardedFetch(`${API_BASE}/assets`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          template_key: templateKey,
          fields,
          vehicle_id: vehicleId || null,
          campaign_id: campaignId || null,
        }),
      });
      if (created === null) return;

      const createdAsset = created as AssetRecord;

      const submitted = await guardedFetch(`${API_BASE}/assets/${createdAsset.id}/submit`, {
        method: "POST",
      });
      if (submitted === null) return;

      const asset = submitted as AssetRecord;

      setArtifacts([{ id: Date.now(), type: "asset_detail", title: assetLabel(asset), asset }]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function approveAssetAction(assetId: string, notes?: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/assets/${assetId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes || null }),
      });
      if (data === null) return;

      const asset = data as AssetRecord;

      setArtifacts([{ id: Date.now(), type: "asset_detail", title: assetLabel(asset), asset }]);
    } catch (error) {
      const compliancePayload = (error as { payload?: unknown })?.payload;
      setPanelError(
        formatComplianceError(compliancePayload) ??
          (error instanceof Error ? error.message : "Unable to reach NXTDeal backend.")
      );
    } finally {
      setPanelLoading(false);
    }
  }

  async function rejectAssetAction(assetId: string, notes?: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/assets/${assetId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes || null }),
      });
      if (data === null) return;

      const asset = data as AssetRecord;

      setArtifacts([{ id: Date.now(), type: "asset_detail", title: assetLabel(asset), asset }]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  function loadAssetPanelArtifact(key: string) {
    if (key === "templates") return loadAssetTemplatesArtifact();
    if (key === "pending_approvals") return loadAssetListArtifact("pending");
    if (key === "my_assets") return loadAssetListArtifact("mine");
  }

  async function loadCampaignTypesArtifact() {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/campaigns/types`);
      if (data === null) return;

      setArtifacts([
        { id: Date.now(), type: "campaign_types", title: "Campaign Types", types: data as CampaignType[] },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadCampaignFormArtifact(campaignTypeKey: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/campaigns/types`);
      if (data === null) return;

      const campaignType = (data as CampaignType[]).find((t) => t.key === campaignTypeKey);

      if (!campaignType) {
        setPanelError(`Unknown campaign type '${campaignTypeKey}'`);
        return;
      }

      setArtifacts([{ id: Date.now(), type: "campaign_form", title: campaignType.name, campaignType }]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadCampaignListArtifact(mode: "pending" | "mine") {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const endpoint = mode === "pending" ? "/campaigns/pending" : "/campaigns/mine";
      const data = await guardedFetch(`${API_BASE}${endpoint}`);
      if (data === null) return;

      setArtifacts([
        {
          id: Date.now(),
          type: "campaign_list",
          title: mode === "pending" ? "Pending Campaigns" : "My Campaigns",
          mode,
          campaigns: data as CampaignRecord[],
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadCampaignDetailArtifact(campaignId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/campaigns/${encodeURIComponent(campaignId)}`);
      if (data === null) return;

      const campaign = data as CampaignRecord;

      setArtifacts([{ id: Date.now(), type: "campaign_detail", title: campaignLabel(campaign), campaign }]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  // Doesn't touch `artifacts` state -- the campaign_form view calls this itself to show
  // a live "this will reach N people" count next to the audience fields, the same way a
  // real campaign tool previews reach before you commit to sending anything.
  async function previewCampaignAudience(
    campaignType: string,
    params: Record<string, unknown>
  ): Promise<AudiencePreview | null> {
    try {
      const data = await guardedFetch(`${API_BASE}/campaigns/audience/preview`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ campaign_type: campaignType, params }),
      });
      if (data === null) return null;

      return data as AudiencePreview;
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      return null;
    }
  }

  async function createCampaignAction(
    campaignType: string,
    name: string,
    channel: string,
    params: Record<string, unknown>,
    linkedAssetId?: string
  ) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/campaigns`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          campaign_type: campaignType,
          name,
          channel,
          params,
          linked_asset_id: linkedAssetId || null,
        }),
      });
      if (data === null) return;

      const campaign = data as CampaignRecord;

      setArtifacts([{ id: Date.now(), type: "campaign_detail", title: campaignLabel(campaign), campaign }]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function activateCampaignAction(campaignId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/campaigns/${campaignId}/activate`, { method: "POST" });
      if (data === null) return;

      const campaign = data as CampaignRecord;

      setArtifacts([{ id: Date.now(), type: "campaign_detail", title: campaignLabel(campaign), campaign }]);
    } catch (error) {
      const compliancePayload = (error as { payload?: unknown })?.payload;
      setPanelError(
        formatComplianceError(compliancePayload) ??
          (error instanceof Error ? error.message : "Unable to reach NXTDeal backend.")
      );
    } finally {
      setPanelLoading(false);
    }
  }

  async function completeCampaignAction(campaignId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/campaigns/${campaignId}/complete`, { method: "POST" });
      if (data === null) return;

      const campaign = data as CampaignRecord;

      setArtifacts([{ id: Date.now(), type: "campaign_detail", title: campaignLabel(campaign), campaign }]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function cancelCampaignAction(campaignId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/campaigns/${campaignId}/cancel`, { method: "POST" });
      if (data === null) return;

      const campaign = data as CampaignRecord;

      setArtifacts([{ id: Date.now(), type: "campaign_detail", title: campaignLabel(campaign), campaign }]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  function loadCampaignPanelArtifact(key: string) {
    if (key === "types") return loadCampaignTypesArtifact();
    if (key === "pending_campaigns") return loadCampaignListArtifact("pending");
    if (key === "my_campaigns") return loadCampaignListArtifact("mine");
  }

  async function loadWebsiteSectionsArtifact() {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const [sectionsData, pagesData] = await Promise.all([
        guardedFetch(`${API_BASE}/websites/sections`),
        guardedFetch(`${API_BASE}/websites/pages`),
      ]);
      if (sectionsData === null || pagesData === null) return;

      setArtifacts([
        {
          id: Date.now(),
          type: "website_sections",
          title: "Website Builder",
          sections: sectionsData as WebsiteSectionTemplate[],
          pages: pagesData as WebsitePageInfo[],
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadWebsiteListArtifact(mode: "pending" | "mine") {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const endpoint = mode === "pending" ? "/websites/pending" : "/websites/mine";
      const data = await guardedFetch(`${API_BASE}${endpoint}`);
      if (data === null) return;

      setArtifacts([
        {
          id: Date.now(),
          type: "website_list",
          title: mode === "pending" ? "Pending Websites" : "My Websites",
          mode,
          websites: data as WebsiteRecord[],
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  // Fetches the site alongside the section-template/page catalog so the builder UI
  // (ArtifactView's website_detail branch) has everything it needs to render an
  // "add a section" form without a separate round trip mid-render.
  async function loadWebsiteDetailArtifact(websiteId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const [websiteData, sectionsData, pagesData] = await Promise.all([
        guardedFetch(`${API_BASE}/websites/${encodeURIComponent(websiteId)}`),
        guardedFetch(`${API_BASE}/websites/sections`),
        guardedFetch(`${API_BASE}/websites/pages`),
      ]);
      if (websiteData === null || sectionsData === null || pagesData === null) return;

      const website = websiteData as WebsiteRecord;

      setArtifacts([
        {
          id: Date.now(),
          type: "website_detail",
          title: websiteLabel(website),
          website,
          sectionTemplates: sectionsData as WebsiteSectionTemplate[],
          pageKeys: pagesData as WebsitePageInfo[],
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function createWebsiteAction(name: string, mode: "traditional" | "dealer_gpt" = "traditional") {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/websites`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, mode }),
      });
      if (data === null) return;

      const website = data as WebsiteRecord;

      await loadWebsiteDetailArtifact(website.id);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  // Session 58 -- Sam: "have dealerOS create the website through a setup wizard...
  // let ai write the content and set it up." Just switches to the wizard form -- no
  // fetch needed until the dealer actually submits it (createWebsiteWizardAction
  // below), same "start-only screen" pattern as loadDealStartArtifact.
  function loadWebsiteWizardArtifact() {
    setPanelError(null);
    setArtifacts([{ id: Date.now(), type: "website_wizard", title: "Website Setup Wizard" }]);
  }

  async function createWebsiteWizardAction(
    dealershipInfo: WizardDealershipInfo,
    mode: "traditional" | "dealer_gpt"
  ) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/websites/wizard`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ dealership_info: dealershipInfo, mode }),
      });
      if (data === null) return;

      const website = data as WebsiteRecord;

      await loadWebsiteDetailArtifact(website.id);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  // Session 58 -- Sam: "we can lock stuff if we feel they'll mess it up." MARKETING/
  // ADMIN only (enforced server-side too).
  async function toggleSectionLockAction(
    websiteId: string,
    pageKey: string,
    sectionIndex: number,
    locked: boolean
  ) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(
        `${API_BASE}/websites/${websiteId}/pages/${pageKey}/sections/${sectionIndex}/lock`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ locked }),
        }
      );
      if (data === null) return;

      await loadWebsiteDetailArtifact(websiteId);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function setWebsiteModeAction(websiteId: string, mode: "traditional" | "dealer_gpt") {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/websites/${websiteId}/mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode }),
      });
      if (data === null) return;

      await loadWebsiteDetailArtifact(websiteId);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  // Session 58 -- Sam's admin-side controls: "DNS info... SEO, Bot stuff... Google /
  // umami style analytics... facebook ads codes... code snippits" plus OEM branding.
  // MARKETING/ADMIN only (enforced server-side).
  async function updateWebsiteAdminSettingsAction(websiteId: string, patch: Partial<WebsiteAdminSettings>) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/websites/${websiteId}/admin-settings`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ patch }),
      });
      if (data === null) return;

      await loadWebsiteDetailArtifact(websiteId);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  // Read-only lookups the Admin Settings panel calls on demand (not tied to the main
  // artifact state -- ArtifactView keeps the returned text in its own local state).
  async function fetchWebsiteDnsInstructions(websiteId: string) {
    return guardedFetch(`${API_BASE}/websites/${websiteId}/dns-instructions`);
  }

  async function fetchWebsiteRobotsTxt(websiteId: string) {
    return guardedFetch(`${API_BASE}/websites/${websiteId}/robots-txt`);
  }

  // Section-editing actions all re-fetch the full site afterward (rather than trusting
  // the mutation's own response body) because only GET /websites/{id} resolves
  // `inventory_grid` sections to a live vehicle list -- the create/add/remove/submit
  // endpoints return the raw entity, which is correct but unrendered.
  async function addSectionAction(
    websiteId: string,
    pageKey: string,
    sectionKey: string,
    fields: Record<string, string>
  ) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/websites/${websiteId}/pages/${pageKey}/sections`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ section_key: sectionKey, fields }),
      });
      if (data === null) return;

      await loadWebsiteDetailArtifact(websiteId);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function removeSectionAction(websiteId: string, pageKey: string, sectionIndex: number) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(
        `${API_BASE}/websites/${websiteId}/pages/${pageKey}/sections/${sectionIndex}/remove`,
        { method: "POST" }
      );
      if (data === null) return;

      await loadWebsiteDetailArtifact(websiteId);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function submitWebsiteAction(websiteId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/websites/${websiteId}/submit`, { method: "POST" });
      if (data === null) return;

      await loadWebsiteDetailArtifact(websiteId);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function approveWebsiteAction(websiteId: string, notes?: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/websites/${websiteId}/approve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes || null }),
      });
      if (data === null) return;

      await loadWebsiteDetailArtifact(websiteId);
    } catch (error) {
      const compliancePayload = (error as { payload?: unknown })?.payload;
      setPanelError(
        formatComplianceError(compliancePayload) ??
          (error instanceof Error ? error.message : "Unable to reach NXTDeal backend.")
      );
    } finally {
      setPanelLoading(false);
    }
  }

  async function rejectWebsiteAction(websiteId: string, notes?: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/websites/${websiteId}/reject`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ notes: notes || null }),
      });
      if (data === null) return;

      await loadWebsiteDetailArtifact(websiteId);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  function loadWebsitePanelArtifact(key: string) {
    if (key === "sections") return loadWebsiteSectionsArtifact();
    if (key === "wizard") return loadWebsiteWizardArtifact();
    if (key === "pending_sites") return loadWebsiteListArtifact("pending");
    if (key === "my_sites") return loadWebsiteListArtifact("mine");
  }

  function loadDealStartArtifact() {
    setPanelError(null);
    setArtifacts([{ id: Date.now(), type: "deal_start", title: "Deal Desk" }]);
  }

  async function loadDealListArtifact(mode: "pending" | "mine") {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const endpoint = mode === "pending" ? "/deals/pending-financing" : "/deals/mine";
      const data = await guardedFetch(`${API_BASE}${endpoint}`);
      if (data === null) return;

      setArtifacts([
        {
          id: Date.now(),
          type: "deal_list",
          title: mode === "pending" ? "Deals Awaiting Financing" : "My Deals",
          mode,
          deals: data as DealRecord[],
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadDealDetailArtifact(dealId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const [dealData, lendersData] = await Promise.all([
        guardedFetch(`${API_BASE}/deals/${encodeURIComponent(dealId)}`),
        guardedFetch(`${API_BASE}/deals/lenders`),
      ]);
      if (dealData === null || lendersData === null) return;

      const deal = dealData as DealRecord;

      setArtifacts([
        { id: Date.now(), type: "deal_detail", title: dealLabel(deal), deal, lenders: lendersData as LenderOption[] },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  // Every deal-mutating action below folds the mutation's own response (which is
  // already a complete, self-sufficient Deal record -- unlike the website builder,
  // nothing here needs a server-side render step) into the CURRENT artifact rather
  // than re-fetching the lender list every time, since that list doesn't change deal
  // to deal.
  function setDealDetailFromResponse(deal: DealRecord) {
    setArtifacts((prev) => {
      const current = prev[0];
      const lenders = current && current.type === "deal_detail" ? current.lenders : [];

      return [{ id: Date.now(), type: "deal_detail", title: dealLabel(deal), deal, lenders }];
    });
  }

  async function createDealAction(customerId: string, vehicleId: string, tradeInValue?: number) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          customer_id: customerId,
          vehicle_id: vehicleId,
          trade_in: tradeInValue ? { value: tradeInValue } : null,
        }),
      });
      if (data === null) return;

      await loadDealDetailArtifact((data as DealRecord).id);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function addScenarioAction(
    dealId: string,
    label: string,
    salePrice: number,
    downPayment: number,
    termMonths: number
  ) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/scenarios`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          label,
          sale_price: salePrice,
          down_payment: downPayment,
          term_months: termMonths,
        }),
      });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function removeScenarioAction(dealId: string, scenarioId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/scenarios/${scenarioId}/remove`, {
        method: "POST",
      });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function selectScenarioAction(dealId: string, scenarioId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/scenarios/${scenarioId}/select`, {
        method: "POST",
      });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function chooseInHouseFinancingAction(dealId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/financing/in-house`, { method: "POST" });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function submitToLenderAction(dealId: string, lenderId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/financing/submit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ lender_id: lenderId }),
      });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function recordLenderDecisionAction(
    dealId: string,
    decision: "approved" | "declined" | "countered",
    counteredTerms?: FinancingTerms,
    notes?: string
  ) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/financing/decision`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, countered_terms: counteredTerms || null, notes: notes || null }),
      });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      const compliancePayload = (error as { payload?: unknown })?.payload;
      setPanelError(
        formatComplianceError(compliancePayload) ??
          (error instanceof Error ? error.message : "Unable to reach NXTDeal backend.")
      );
    } finally {
      setPanelLoading(false);
    }
  }

  async function acceptCounteredTermsAction(dealId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/financing/accept-counter`, { method: "POST" });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function generateContractAction(dealId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/contract`, { method: "POST" });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  async function fundDealAction(dealId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/fund`, { method: "POST" });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      const compliancePayload = (error as { payload?: unknown })?.payload;
      setPanelError(
        formatComplianceError(compliancePayload) ??
          (error instanceof Error ? error.message : "Unable to reach NXTDeal backend.")
      );
    } finally {
      setPanelLoading(false);
    }
  }

  async function cancelDealAction(dealId: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/deals/${dealId}/cancel`, { method: "POST" });
      if (data === null) return;

      setDealDetailFromResponse(data as DealRecord);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
    } finally {
      setPanelLoading(false);
    }
  }

  function loadDealPanelArtifact(key: string) {
    if (key === "start_deal") return loadDealStartArtifact();
    if (key === "pending_financing") return loadDealListArtifact("pending");
    if (key === "my_deals") return loadDealListArtifact("mine");
  }

  async function loadIntelligenceDepartmentsArtifact() {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/intelligence/departments`);
      if (data === null) return;

      setArtifacts([
        {
          id: Date.now(),
          type: "intelligence_departments",
          title: "Department Intelligence",
          departments: data as IntelligenceDepartmentOption[],
        },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  async function loadIntelligenceDashboardArtifact(department: string) {
    setPanelError(null);
    setPanelLoading(true);

    try {
      const data = await guardedFetch(`${API_BASE}/intelligence/${department}`);
      if (data === null) return;

      const dashboard = data as IntelligenceDashboard;

      setArtifacts([
        { id: Date.now(), type: "intelligence_dashboard", title: dashboard.title, dashboard },
      ]);
    } catch (error) {
      setPanelError(error instanceof Error ? error.message : "Unable to reach NXTDeal backend.");
      setArtifacts([]);
    } finally {
      setPanelLoading(false);
    }
  }

  function loadIntelligencePanelArtifact(key: string) {
    if (key === "departments") return loadIntelligenceDepartmentsArtifact();
    return loadIntelligenceDashboardArtifact(key);
  }

  // Pin-candidate mapping — reset_confirm/reset_result are deliberately excluded
  // (transient action; reset_result briefly holds a real plaintext secret), and the
  // asset browsing views (asset_templates/asset_form/asset_list) aren't pinnable
  // either -- only a specific asset_detail is. Typed against lib/pins.ts's `PinKind`
  // (not the broader `Artifact["type"]`, which includes several non-pinnable variants)
  // so this can never produce a candidate `addPin()` would reject.
  function currentPinCandidate(): { label: string; kind: PinKind; refId?: string } | null {
    const artifact = artifacts[0];

    if (!artifact) return null;

    switch (artifact.type) {
      case "roster":
        return { label: "Employee Roster", kind: "roster" };
      case "audit":
        return { label: "Audit Log", kind: "audit" };
      case "compliance_alerts_list":
        return { label: "Compliance Alerts", kind: "compliance" };
      case "readiness_score":
        return { label: "Readiness Score", kind: "readiness_score" };
      case "performance_rank":
        return { label: "Performance Rank", kind: "performance_rank" };
      case "growth_opportunities":
        return { label: "Growth Opportunities", kind: "growth_opportunities" };
      case "profile":
        return { label: pinLabelForProfile(artifact.profile), kind: "profile", refId: artifact.entityId };
      case "dashboard":
        return { label: artifact.title, kind: "dashboard", refId: artifact.key };
      case "asset_detail":
        return { label: assetLabel(artifact.asset), kind: "asset", refId: artifact.asset.id };
      case "campaign_detail":
        return { label: campaignLabel(artifact.campaign), kind: "campaign", refId: artifact.campaign.id };
      case "website_detail":
        return { label: websiteLabel(artifact.website), kind: "website", refId: artifact.website.id };
      case "deal_detail":
        return { label: dealLabel(artifact.deal), kind: "deal", refId: artifact.deal.id };
      case "intelligence_dashboard":
        return { label: artifact.dashboard.title, kind: "department_intelligence", refId: artifact.dashboard.department };
      default:
        return null;
    }
  }

  return {
    artifacts,
    setArtifacts,
    clearArtifacts,
    panelLoading,
    panelError,
    loadRosterArtifact,
    loadAuditArtifact,
    loadReadinessScoreArtifact,
    loadPerformanceRankArtifact,
    loadGrowthOpportunitiesArtifact,
    loadResetConfirmArtifact,
    confirmResetPassword,
    loadAdminPanelArtifact,
    loadGeneralPanelArtifact,
    loadDashboardArtifact,
    loadProfileArtifact,
    loadAssetTemplatesArtifact,
    loadAssetFormArtifact,
    loadAssetListArtifact,
    loadAssetDetailArtifact,
    createAndSubmitAsset,
    approveAssetAction,
    rejectAssetAction,
    loadAssetPanelArtifact,
    loadCampaignTypesArtifact,
    loadCampaignFormArtifact,
    loadCampaignListArtifact,
    loadCampaignDetailArtifact,
    previewCampaignAudience,
    createCampaignAction,
    activateCampaignAction,
    completeCampaignAction,
    cancelCampaignAction,
    loadCampaignPanelArtifact,
    loadWebsiteSectionsArtifact,
    loadWebsiteListArtifact,
    loadWebsiteDetailArtifact,
    loadWebsiteWizardArtifact,
    createWebsiteAction,
    createWebsiteWizardAction,
    addSectionAction,
    removeSectionAction,
    toggleSectionLockAction,
    setWebsiteModeAction,
    updateWebsiteAdminSettingsAction,
    fetchWebsiteDnsInstructions,
    fetchWebsiteRobotsTxt,
    submitWebsiteAction,
    approveWebsiteAction,
    rejectWebsiteAction,
    loadWebsitePanelArtifact,
    loadDealStartArtifact,
    loadDealListArtifact,
    loadDealDetailArtifact,
    createDealAction,
    addScenarioAction,
    removeScenarioAction,
    selectScenarioAction,
    chooseInHouseFinancingAction,
    submitToLenderAction,
    recordLenderDecisionAction,
    acceptCounteredTermsAction,
    generateContractAction,
    fundDealAction,
    cancelDealAction,
    loadDealPanelArtifact,
    loadIntelligenceDepartmentsArtifact,
    loadIntelligenceDashboardArtifact,
    loadIntelligencePanelArtifact,
    loadEmployeeValueArtifact,
    loadComplianceAlertsArtifact,
    resolveComplianceAlertAction,
    overrideComplianceAlertAction,
    currentPinCandidate,
  };
}
