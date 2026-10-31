import { canonicalApiUrl } from "./canonicalApiUrl";

// API client for the NXTDeal Hub (hub/app.py) -- a SEPARATE FastAPI app from
// backend/api/app.py (lib/api.ts), reachable at NEXT_PUBLIC_HUB_API_URL, auth'd by a
// per-employee username/password login (POST /hub/auth/login) that returns a bearer
// token; every /hub/* request then carries `Authorization: Bearer <token>` rather than
// the old single shared X-NXTDeal-Hub-Key header -- see hub/app.py's own module
// docstring for the login model. The X-NXTDeal-Hub-Key secret survives only as a
// server-side break-glass fallback, never on the normal path this client uses.
//
// CRITICAL: the bearer token must NEVER be read from a NEXT_PUBLIC_* env var -- those
// are baked into the client-side JS bundle at build time and would ship a credential
// to anyone who opens devtools. Instead it's minted per login (see
// app/hub-console/page.tsx's login gate) and held only in sessionStorage, which never
// leaves this browser tab and clears when the tab closes.

export const HUB_API_BASE =
  canonicalApiUrl(process.env.NEXT_PUBLIC_HUB_API_URL ?? "http://127.0.0.1:9000");

const HUB_TOKEN_STORAGE = "dealeros_hub_token";

export function getStoredHubToken(): string {
  if (typeof window === "undefined") return "";
  return sessionStorage.getItem(HUB_TOKEN_STORAGE) ?? "";
}

export function setStoredHubToken(token: string) {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(HUB_TOKEN_STORAGE, token);
}

export function clearStoredHubToken() {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(HUB_TOKEN_STORAGE);
}

export class HubApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

// A single 401 hook so any console call -- including the section components that
// handle their own errors internally -- can bounce the whole console back to the
// login gate. hubFetch is the one choke point where a rejected token is seen.
type HubUnauthorizedHandler = () => void;
let hubUnauthorizedHandler: HubUnauthorizedHandler | null = null;

export function setHubUnauthorizedHandler(handler: HubUnauthorizedHandler | null) {
  hubUnauthorizedHandler = handler;
}

async function hubFetch(path: string, init: RequestInit = {}) {
  const token = getStoredHubToken();

  const response = await fetch(`${HUB_API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...(init.headers ?? {}),
    },
  });

  if (response.status === 401) {
    // A delayed rejection of an old token cannot invalidate a newer login.
    if (token === getStoredHubToken()) {
      clearStoredHubToken();
      hubUnauthorizedHandler?.();
    }
    throw new HubApiError(401, "Session expired, please log in.");
  }

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new HubApiError(response.status, data.detail ?? "Hub request failed.");
  }

  return data;
}

// ---------------------------------------------------------------------------
// Hub authentication -- per-employee username/password login (hub/auth). The
// returned bearer token is stored in sessionStorage and attached to every
// subsequent /hub/* request by hubFetch above.
// ---------------------------------------------------------------------------

export type HubLoginResult = {
  token: string;
  role: string;
  must_change_password: boolean;
};

export type HubWhoami = {
  employee_id: string;
  role: string;
  must_change_password: boolean;
};

export async function hubLogin(
  username: string,
  password: string
): Promise<HubLoginResult> {
  // Bypass hubFetch's bearer attachment -- there is no token yet, and a stale
  // one must not leak onto the login request.
  const response = await fetch(`${HUB_API_BASE}/hub/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new HubApiError(
      response.status,
      data.detail ?? "Invalid username or password."
    );
  }

  const result = data as HubLoginResult;
  setStoredHubToken(result.token);
  return result;
}

export async function hubWhoami(): Promise<HubWhoami> {
  return hubFetch("/hub/auth/whoami");
}

export async function hubChangePassword(
  oldPassword: string,
  newPassword: string
): Promise<{ ok: true; token?: string }> {
  const result = await hubFetch("/hub/auth/change-password", {
    method: "POST",
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
  if (result.token) setStoredHubToken(result.token);
  return result;
}

export function hubLogout() {
  clearStoredHubToken();
}

// ---------------------------------------------------------------------------
// Dealers
// ---------------------------------------------------------------------------

export type Dealer = {
  dealer_id: string;
  slug: string;
  name: string;
  contact_name: string | null;
  contact_email: string;
  contact_phone: string | null;
  address: string | null;
  city: string | null;
  state: string | null;
  plan_tier: string;
  status: string;
  storage_dir: string;
  network_opt_in: boolean;
  api_base_url: string | null;
  created_by: string;
  created_at: string;
  // Dealer Profile (added 2026-07-19, Dealer Management rebuild)
  group: string | null;
  oem: string | null;
  location_count: number;
  industry_type: string;
  // Subscription Info
  active_modules: string[];
  renewal_date: string | null;
  seat_count: number | null;
  // NXTDeal Version
  current_release: string | null;
  beta_programs: string[];
};

// The real lifecycle funnel stages -- matches hub/core/dealer.py's
// LIFECYCLE_FUNNEL_STAGES exactly (order matters, this drives the funnel UI).
export const DEALER_LIFECYCLE_STAGES = [
  "lead",
  "demo",
  "trial",
  "provisioning",
  "active",
  "expansion",
  "churn_risk",
] as const;

export const DEALER_ALL_STATUSES = [...DEALER_LIFECYCLE_STAGES, "suspended"] as const;

export const DEALER_INDUSTRY_TYPES = [
  "independent",
  "franchise",
  "bhph",
  "finance_company",
] as const;

export type CreateDealerInput = {
  name: string;
  contact_email: string;
  contact_name?: string;
  contact_phone?: string;
  address?: string;
  city?: string;
  state?: string;
  plan_tier?: string;
  network_opt_in?: boolean;
};

export async function listDealers(): Promise<Dealer[]> {
  return hubFetch("/hub/dealers");
}

export async function getDealer(dealerId: string): Promise<Dealer> {
  return hubFetch(`/hub/dealers/${dealerId}`);
}

export async function createDealer(input: CreateDealerInput) {
  return hubFetch("/hub/dealers", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateDealerStatus(dealerId: string, status: string) {
  return hubFetch(`/hub/dealers/${dealerId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export async function updateDealerApiBaseUrl(dealerId: string, apiBaseUrl: string) {
  return hubFetch(`/hub/dealers/${dealerId}/api-base-url`, {
    method: "POST",
    body: JSON.stringify({ api_base_url: apiBaseUrl }),
  });
}

// ---------------------------------------------------------------------------
// Dealer infrastructure auto-provisioning (2026-07-24) -- create + deploy a
// dealer's frontend + API in Coolify from the Hub (hub_core/infra_provisioning.py).
// ---------------------------------------------------------------------------
export type ProvisioningConfig = { configured: boolean; missing: string[] };

export type ProvisionResult = {
  dealer_id: string;
  slug: string;
  status: string;
  api?: { uuid: string; url: string };
  frontend?: { uuid: string; url: string };
  warnings?: string[];
  note?: string;
};

export type ProvisionStatus = {
  status: string; // none | provisioning | deploying | failed
  dealer_id?: string;
  slug?: string;
  api_url?: string;
  frontend_url?: string;
  error?: string | null;
  warnings?: string[];
  updated_at?: string;
  live?: Record<string, string>;
};

export async function getProvisioningConfig(): Promise<ProvisioningConfig> {
  return hubFetch(`/hub/provisioning/config`);
}

export async function provisionDealer(dealerId: string): Promise<ProvisionResult> {
  return hubFetch(`/hub/dealers/${dealerId}/provision`, { method: "POST" });
}

export async function getProvisionStatus(dealerId: string, live = false): Promise<ProvisionStatus> {
  return hubFetch(`/hub/dealers/${dealerId}/provision-status${live ? "?live=true" : ""}`);
}

// ---------------------------------------------------------------------------
// Dealer Management rebuild (2026-07-19) -- Overview KPIs/lifecycle funnel, plus
// the real Dealer Record (Profile / Subscription Info / NXTDeal Version) editable
// sections. See hub/core/dealer_overview.py + hub/core/dealer_profile.py.
// ---------------------------------------------------------------------------

export type DealerManagementOverview = {
  kpis: {
    total_dealers: number;
    trial_dealers: number;
    active_dealers: number;
    multi_rooftop_groups: number;
    network_members: number;
    enterprise_accounts: number;
  };
  lifecycle_funnel: { stage: string; label: string; count: number }[];
  suspended_count: number;
  single_location_named_groups: number;
  status_breakdown: Record<string, number>;
  note: string;
};

export async function getDealerManagementOverview(): Promise<DealerManagementOverview> {
  return hubFetch("/hub/dealer-management/overview");
}

export type UpdateDealerProfileInput = {
  group?: string;
  oem?: string;
  location_count?: number;
  industry_type?: string;
};

export async function updateDealerProfile(
  dealerId: string,
  input: UpdateDealerProfileInput
): Promise<Dealer> {
  return hubFetch(`/hub/dealers/${dealerId}/profile`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export type UpdateDealerSubscriptionInput = {
  plan_tier?: string;
  active_modules?: string[];
  renewal_date?: string;
  seat_count?: number;
};

export async function updateDealerSubscription(
  dealerId: string,
  input: UpdateDealerSubscriptionInput
): Promise<Dealer> {
  return hubFetch(`/hub/dealers/${dealerId}/subscription`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export type UpdateDealerVersionInput = {
  current_release?: string;
  beta_programs?: string[];
};

export async function updateDealerVersion(
  dealerId: string,
  input: UpdateDealerVersionInput
): Promise<Dealer> {
  return hubFetch(`/hub/dealers/${dealerId}/version`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

// ---------------------------------------------------------------------------
// Dealer Management rebuild, slice 2 of 5 -- Module Management + Feature
// Flags (hub/core/dealer_modules.py + hub/core/feature_flags.py). Both are
// real, persisted Hub-side CONFIGURATION RECORDS -- see each module's own
// docstring: toggling a module or resolving a flag here does NOT currently
// enforce anything on a running tenant backend process. No cross-process
// mechanism exists yet for the Hub to push either into a dealer's own
// running instance.
// ---------------------------------------------------------------------------

export type ModuleCategory = "core" | "add_on";

export type ModuleCatalogEntry = {
  key: string;
  label: string;
  category: ModuleCategory;
  real_capability: string;
  default_enabled: boolean;
};

export type EffectiveModule = ModuleCatalogEntry & {
  enabled: boolean;
  is_override: boolean;
};

export type DealerModuleConfig = {
  dealer_id: string;
  modules: EffectiveModule[];
  updated_by: string | null;
  updated_at: string | null;
  enforcement_note: string;
};

export async function getModuleCatalog(): Promise<{ modules: ModuleCatalogEntry[] }> {
  return hubFetch("/hub/dealer-management/modules/catalog");
}

export async function getDealerModules(dealerId: string): Promise<DealerModuleConfig> {
  return hubFetch(`/hub/dealer-management/modules/${dealerId}`);
}

export async function setDealerModule(
  dealerId: string,
  moduleKey: string,
  enabled: boolean
): Promise<DealerModuleConfig> {
  return hubFetch(`/hub/dealer-management/modules/${dealerId}`, {
    method: "POST",
    body: JSON.stringify({ module_key: moduleKey, enabled }),
  });
}

export type FeatureFlagScope = "global" | "group" | "dealer";

export type FeatureFlagOverride = {
  override_id: string;
  flag_key: string;
  scope: FeatureFlagScope;
  scope_target: string | null;
  enabled: boolean;
  note: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
};

export type FeatureFlagTrailEntry = {
  scope: FeatureFlagScope;
  scope_target: string | null;
  matched: boolean;
  override: FeatureFlagOverride | null;
  skipped_reason?: string;
};

export type FeatureFlagResolution = {
  flag_key: string;
  dealer_id: string;
  dealer_name: string;
  resolved_enabled: boolean;
  source: FeatureFlagScope | "default";
  matched_override: FeatureFlagOverride | null;
  evaluation_trail: FeatureFlagTrailEntry[];
};

export async function getFeatureFlagScopes(): Promise<{
  scopes: FeatureFlagScope[];
  known_flag_keys: string[];
}> {
  return hubFetch("/hub/dealer-management/feature-flags/scopes");
}

export async function listFeatureFlagOverrides(
  flagKey?: string
): Promise<{ overrides: FeatureFlagOverride[] }> {
  const query = flagKey ? `?flag_key=${encodeURIComponent(flagKey)}` : "";
  return hubFetch(`/hub/dealer-management/feature-flags${query}`);
}

export type CreateFeatureFlagOverrideInput = {
  flag_key: string;
  scope: FeatureFlagScope;
  enabled: boolean;
  scope_target?: string | null;
  note?: string | null;
};

export async function createFeatureFlagOverride(
  input: CreateFeatureFlagOverrideInput
): Promise<FeatureFlagOverride> {
  return hubFetch("/hub/dealer-management/feature-flags", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function deleteFeatureFlagOverride(
  overrideId: string
): Promise<{ deleted: boolean; override_id: string }> {
  return hubFetch(`/hub/dealer-management/feature-flags/${overrideId}`, {
    method: "DELETE",
  });
}

export async function resolveFeatureFlag(
  flagKey: string,
  dealerId: string
): Promise<FeatureFlagResolution> {
  const query = `?flag_key=${encodeURIComponent(flagKey)}&dealer_id=${encodeURIComponent(
    dealerId
  )}`;
  return hubFetch(`/hub/dealer-management/feature-flags/resolve${query}`);
}

// ---------------------------------------------------------------------------
// Network
// ---------------------------------------------------------------------------

export type NetworkOverview = {
  total_dealers: number;
  opted_in_dealers: number;
  dealers_reporting: { dealer_id: string; benchmark: unknown }[];
  dealers_unreachable: { dealer_id: string; reason: string }[];
  note: string;
};

export type NetworkCollectResult = {
  total_dealers: number;
  opted_in_dealers: number;
  dealers_reporting: number;
  dealers_unreachable: { dealer_id: string; reason: string }[];
  total_snapshots_stored: number;
  note: string;
};

export type NetworkKpiStat = {
  label: string;
  format: string;
  sample_size: number;
  average: number | null;
  median: number | null;
  min: number | null;
  max: number | null;
};

export type NetworkAnalytics = {
  dealers_contributing: number;
  departments: Record<string, Record<string, NetworkKpiStat>>;
  note: string;
};

export async function getNetworkOverview(): Promise<NetworkOverview> {
  return hubFetch("/hub/network/overview");
}

export async function collectNetworkSnapshots(): Promise<NetworkCollectResult> {
  return hubFetch("/hub/network/collect", { method: "POST" });
}

export async function getNetworkAnalytics(): Promise<NetworkAnalytics> {
  return hubFetch("/hub/network/analytics");
}

// ---------------------------------------------------------------------------
// Server health
// ---------------------------------------------------------------------------

export type DealerHealthCheck = {
  dealer_id: string;
  name: string;
  slug: string;
  status: "reachable" | "unreachable" | "not_configured";
  latency_ms: number | null;
  detail: string | null;
};

export type ServerHealthOverview = {
  hub_status: string;
  total_dealers: number;
  reachable_dealers: number;
  unreachable_dealers: number;
  dealers: DealerHealthCheck[];
  note: string;
};

export async function getServerHealthOverview(): Promise<ServerHealthOverview> {
  return hubFetch("/hub/health/overview");
}

// ---------------------------------------------------------------------------
// Dealer Management rebuild, slice 3 of 5 -- Onboarding Center + Migration
// Tracking (the "Provisioning" menu item). See hub/core/dealer_onboarding.py
// + hub/core/dealer_migration.py for the full real-automated-vs-honest-
// manual signal breakdown per onboarding step and the real, rule-based
// Go-Live Tracker thresholds (ready >= 95%, blocked < 80%).
// ---------------------------------------------------------------------------

export type OnboardingStepBasis = "auto" | "manual";

export type OnboardingStepCatalogEntry = {
  key: string;
  label: string;
  basis: OnboardingStepBasis;
};

export type OnboardingStep = OnboardingStepCatalogEntry & {
  catalog_basis: OnboardingStepBasis;
  complete: boolean;
  basis: OnboardingStepBasis | "not_started";
  completed_at: string | null;
  completed_by: string | null;
  note: string | null;
};

export type DealerOnboardingStatus = {
  dealer_id: string;
  dealer_name: string;
  steps: OnboardingStep[];
  complete_count: number;
  total_steps: number;
  progress_pct: number;
  updated_at: string;
  note: string;
};

export type OnboardingSummary = {
  dealer_id: string;
  dealer_name: string;
  slug: string;
  complete_count: number;
  total_steps: number;
  progress_pct: number;
};

export async function getOnboardingCatalog(): Promise<{ steps: OnboardingStepCatalogEntry[] }> {
  return hubFetch("/hub/dealer-management/onboarding/catalog");
}

export async function listOnboardingSummaries(): Promise<{ dealers: OnboardingSummary[] }> {
  return hubFetch("/hub/dealer-management/onboarding/summary");
}

export async function getDealerOnboarding(dealerId: string): Promise<DealerOnboardingStatus> {
  return hubFetch(`/hub/dealer-management/onboarding/${dealerId}`);
}

export async function recheckDealerOnboarding(dealerId: string): Promise<DealerOnboardingStatus> {
  return hubFetch(`/hub/dealer-management/onboarding/${dealerId}/recheck`, {
    method: "POST",
  });
}

export async function setDealerOnboardingStep(
  dealerId: string,
  stepKey: string,
  complete: boolean,
  note?: string
): Promise<DealerOnboardingStatus> {
  return hubFetch(`/hub/dealer-management/onboarding/${dealerId}/steps`, {
    method: "POST",
    body: JSON.stringify({ step_key: stepKey, complete, note: note || undefined }),
  });
}

export type MigrationSourceKey =
  | "cdk"
  | "reynolds"
  | "tekion"
  | "dealersocket"
  | "vinsolutions"
  | "hubspot"
  | "none"
  | "other";

export type MigrationCatalogEntry = { key: string; label: string };

export type MigrationCatalog = {
  sources: MigrationCatalogEntry[];
  readiness_categories: MigrationCatalogEntry[];
  go_live_thresholds: { ready_pct: number; blocked_pct: number };
};

export type GoLiveStatus = "not_started" | "blocked" | "at_risk" | "ready";

export type ReadinessCategoryStatus = {
  key: string;
  label: string;
  pct: number | null;
  note: string | null;
};

export type DealerMigrationStatus = {
  dealer_id: string;
  dealer_name: string;
  migrating_from: string | null;
  migrating_from_label: string | null;
  migrating_from_other_note: string | null;
  readiness: ReadinessCategoryStatus[];
  go_live_status: GoLiveStatus;
  go_live_reason: string;
  updated_by: string | null;
  updated_at: string;
  note: string;
};

export type MigrationSummary = {
  dealer_id: string;
  dealer_name: string;
  slug: string;
  migrating_from: string | null;
  migrating_from_label: string | null;
  go_live_status: GoLiveStatus;
};

export async function getMigrationCatalog(): Promise<MigrationCatalog> {
  return hubFetch("/hub/dealer-management/migration/catalog");
}

export async function listMigrationSummaries(): Promise<{ dealers: MigrationSummary[] }> {
  return hubFetch("/hub/dealer-management/migration/summary");
}

export async function getDealerMigration(dealerId: string): Promise<DealerMigrationStatus> {
  return hubFetch(`/hub/dealer-management/migration/${dealerId}`);
}

export async function setDealerMigrationSource(
  dealerId: string,
  migratingFrom: string | null,
  otherNote?: string
): Promise<DealerMigrationStatus> {
  return hubFetch(`/hub/dealer-management/migration/${dealerId}/source`, {
    method: "POST",
    body: JSON.stringify({ migrating_from: migratingFrom, other_note: otherNote || undefined }),
  });
}

export async function setDealerReadiness(
  dealerId: string,
  category: string,
  pct: number,
  note?: string
): Promise<DealerMigrationStatus> {
  return hubFetch(`/hub/dealer-management/migration/${dealerId}/readiness`, {
    method: "POST",
    body: JSON.stringify({ category, pct, note: note || undefined }),
  });
}

// ---------------------------------------------------------------------------
// NOC (Network Operations Center) -- the unified real-time status board,
// composing the same real signals the Dealers/Network/Server Health tabs
// already surface separately, plus a real transparent Alerts feed (hub/
// core/noc.py). Not a new monitoring engine, a real composition layer.
// ---------------------------------------------------------------------------

export type NocAlertSeverity = "critical" | "warning" | "info";

export type NocAlert = {
  severity: NocAlertSeverity;
  category: string;
  dealer_id: string | null;
  dealer_name: string | null;
  title: string;
  reason: string;
};

export type NocStatusBoard = {
  overall_status: "critical" | "warning" | "healthy";
  dealer_counts: {
    total: number;
    active: number;
    provisioning: number;
    suspended: number;
    network_opted_in_active: number;
  };
  reachability: {
    reachable: number;
    unreachable: number;
  };
  network_coverage: {
    dealers_contributing_anonymized_snapshots: number;
  };
  alerts: NocAlert[];
  alert_counts: {
    critical: number;
    warning: number;
    info: number;
  };
  note: string;
};

export async function getNocStatusBoard(): Promise<NocStatusBoard> {
  return hubFetch("/hub/noc/overview");
}

// ---------------------------------------------------------------------------
// Integrations Center (per dealer) -- Dealer Management rebuild, slice 4 of
// 5. Deliberately Hub-side manual data entry, not a live tenant read -- see
// hub/core/dealer_integrations.py's own module docstring for the full
// reasoning (no Google/Microsoft/Meta/CDK/DealerTrack/RouteOne/Xtime concept
// exists anywhere in the tenant's own Connection model, and an endpoint_url
// is a meaningfully riskier thing to expose than the coarse call-count data
// AI Management below reads live).
// ---------------------------------------------------------------------------

export type IntegrationHealth = "healthy" | "warning" | "failed";
export type IntegrationDataFlow = "inbound" | "outbound" | "bidirectional";

export type IntegrationProvider = {
  key: string;
  label: string;
  category: string;
};

export type IntegrationsCatalog = {
  providers: IntegrationProvider[];
  health_statuses: IntegrationHealth[];
  data_flows: IntegrationDataFlow[];
  sync_frequency_presets: string[];
};

export type DealerIntegration = {
  integration_id: string;
  dealer_id: string;
  provider_key: string;
  custom_label: string | null;
  connection_health: IntegrationHealth;
  data_flow: IntegrationDataFlow;
  sync_frequency: string;
  active: boolean;
  notes: string | null;
  created_by: string;
  created_at: string;
  updated_by: string | null;
  updated_at: string;
  label: string;
};

export type DealerIntegrationsStatus = {
  dealer_id: string;
  dealer_name: string;
  integrations: DealerIntegration[];
  active_count: number;
  by_health: { healthy: number; warning: number; failed: number };
  note: string;
};

export type AddDealerIntegrationInput = {
  provider_key: string;
  connection_health?: IntegrationHealth;
  data_flow?: IntegrationDataFlow;
  sync_frequency?: string;
  active?: boolean;
  notes?: string;
  custom_label?: string;
};

export type UpdateDealerIntegrationInput = {
  connection_health?: IntegrationHealth;
  data_flow?: IntegrationDataFlow;
  sync_frequency?: string;
  active?: boolean;
  notes?: string;
  custom_label?: string;
};

export async function getIntegrationsCatalog(): Promise<IntegrationsCatalog> {
  return hubFetch("/hub/dealer-management/integrations/catalog");
}

export async function getDealerIntegrations(dealerId: string): Promise<DealerIntegrationsStatus> {
  return hubFetch(`/hub/dealer-management/integrations/${dealerId}`);
}

export async function addDealerIntegration(
  dealerId: string,
  input: AddDealerIntegrationInput
): Promise<DealerIntegrationsStatus> {
  return hubFetch(`/hub/dealer-management/integrations/${dealerId}`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function updateDealerIntegration(
  dealerId: string,
  integrationId: string,
  input: UpdateDealerIntegrationInput
): Promise<DealerIntegrationsStatus> {
  return hubFetch(`/hub/dealer-management/integrations/${dealerId}/${integrationId}`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function removeDealerIntegration(
  dealerId: string,
  integrationId: string
): Promise<DealerIntegrationsStatus> {
  return hubFetch(`/hub/dealer-management/integrations/${dealerId}/${integrationId}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// AI Management (per dealer) -- Dealer Management rebuild, slice 4 of 5.
// REAL, via a live on-demand HTTP round trip to a new, narrowly-scoped
// tenant-side route (GET /network/ai-management-snapshot, gated by the same
// DEALEROS_NETWORK_KEY shared secret the anonymized peer-benchmark pull
// already uses) -- see hub/core/dealer_ai_management.py's module docstring
// for the full safety reasoning behind adding that one new tenant route.
// Fetched via "Recheck", not on every page load -- the last snapshot is
// persisted so the screen always has something to show.
// ---------------------------------------------------------------------------

export type AiAreaCatalogEntry = {
  key: string;
  label: string;
  feature_keys: string[];
};

export type AiFeatureSnapshot = {
  key: string;
  name: string;
  enabled: boolean;
  attempted: number;
  succeeded: number;
  fell_back: number;
  blocked: number;
};

export type AiAreaStatus = {
  key: string;
  label: string;
  feature_count: number;
  mapped_feature_count: number;
  enabled_count: number;
  total_attempted: number;
  total_succeeded: number;
  total_fell_back: number;
  total_blocked: number;
  features: AiFeatureSnapshot[];
  gap_note: string | null;
};

export type DealerAiManagementStatus = {
  dealer_id: string;
  dealer_name: string;
  checked: boolean;
  reachable: boolean;
  fetch_error: string | null;
  fetched_at: string | null;
  areas: AiAreaStatus[];
  consumption_note: string;
  note: string;
};

export async function getAiAreaCatalog(): Promise<{ areas: AiAreaCatalogEntry[] }> {
  return hubFetch("/hub/dealer-management/ai/catalog");
}

export async function getDealerAiManagement(dealerId: string): Promise<DealerAiManagementStatus> {
  return hubFetch(`/hub/dealer-management/ai/${dealerId}`);
}

export async function recheckDealerAiManagement(dealerId: string): Promise<DealerAiManagementStatus> {
  return hubFetch(`/hub/dealer-management/ai/${dealerId}/recheck`, {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// Network Membership / Support Center / Audit Center / Users -- Dealer
// Management rebuild, slice 5 of 5 (FINAL). See hub/core/
// dealer_network_membership.py, hub/core/dealer_support.py,
// hub/core/hub_audit.py, and hub/core/dealer_contacts.py for the full
// reasoning behind each of these -- especially why per-dealer Network
// Contribution/Score is honestly NOT computable without breaking the
// pseudonym-anonymity boundary, and why Churn Risk is a real, transparent
// rules engine rather than an AI/ML score.
// ---------------------------------------------------------------------------

export type NetworkTier = "none" | "standard" | "premium" | "enterprise";

export type NetworkTierCatalogEntry = { key: NetworkTier; label: string };

export type DealerNetworkMembership = {
  dealer_id: string;
  dealer_name: string;
  network_opt_in: boolean;
  tier: {
    dealer_id: string;
    tier: NetworkTier;
    tier_label: string;
    updated_by: string;
    updated_at: string;
  };
  benchmark_access: boolean;
  contribution: {
    computable_per_dealer: false;
    reason: string;
    pipeline_connectivity_proxy: string;
    network_wide_aggregate: {
      opted_in_active_dealers: number;
      total_anonymized_snapshots_collected: number;
      note: string;
    };
  };
};

export type PipelineConnectivityResult = {
  dealer_id: string;
  reachable: boolean;
  detail: string;
  checked_at: string;
};

export async function getNetworkMembershipCatalog(): Promise<{ tiers: NetworkTierCatalogEntry[] }> {
  return hubFetch("/hub/dealer-management/network/catalog");
}

export async function getDealerNetworkMembership(dealerId: string): Promise<DealerNetworkMembership> {
  return hubFetch(`/hub/dealer-management/network/${dealerId}`);
}

export async function setDealerNetworkTier(dealerId: string, tier: NetworkTier): Promise<DealerNetworkMembership> {
  return hubFetch(`/hub/dealer-management/network/${dealerId}/tier`, {
    method: "POST",
    body: JSON.stringify({ tier }),
  });
}

export async function recheckDealerPipelineConnectivity(dealerId: string): Promise<PipelineConnectivityResult> {
  return hubFetch(`/hub/dealer-management/network/${dealerId}/recheck-pipeline`, {
    method: "POST",
  });
}

export type DealerOperationalSnapshot = {
  dealer_id: string;
  fetched_at: string | null;
  reachable: boolean;
  error: string | null;
  data: {
    window_days?: number;
    current_window?: { login_success_count: number; login_failed_count: number; distinct_employees_logged_in: number; lockout_event_count: number };
    previous_window?: { login_success_count: number; login_failed_count: number; distinct_employees_logged_in: number; lockout_event_count: number };
    trend?: string;
    note?: string;
  };
};

export type HealthScore = {
  score: number | null;
  components: {
    feature_adoption_pct: number | null;
    login_activity_pct: number | null;
    training_completion_pct: null;
  };
  basis: string;
  blend_note: string;
  training_completion_gap: string;
  login_checked: boolean;
  trend: string | null;
};

export type ChurnRiskReason = { reason: string; points: number; detail: string };

export type ChurnRisk = {
  dealer_id: string;
  level: "low" | "medium" | "high";
  points: number;
  reasons: ChurnRiskReason[];
  basis: "rules_engine";
  disclosure: string;
};

export type DealerSupportStatus = {
  dealer_id: string;
  dealer_name: string;
  operational_snapshot: DealerOperationalSnapshot;
  health_score: HealthScore;
  churn_risk: ChurnRisk;
};

export async function getDealerSupportStatus(dealerId: string): Promise<DealerSupportStatus> {
  return hubFetch(`/hub/dealer-management/support/${dealerId}`);
}

export async function recheckDealerSupportSnapshot(dealerId: string): Promise<DealerSupportStatus> {
  return hubFetch(`/hub/dealer-management/support/${dealerId}/recheck`, {
    method: "POST",
  });
}

export type AuditCategory = "module_change" | "permission_change" | "billing_change" | "feature_enablement" | "other";

export type AuditCategoryEntry = { key: AuditCategory; label: string };

export type HubAuditEvent = {
  id: string;
  event_type: string;
  category: AuditCategory;
  category_label: string;
  dealer_id: string | null;
  actor: string;
  summary: string;
  details: Record<string, unknown>;
  timestamp: string;
};

export type AuditEventsResult = {
  events: HubAuditEvent[];
  total_matches: number;
  total_events: number;
  by_category: Record<string, number>;
  filters_applied: { dealer_id: string | null; category: string | null; event_type: string | null };
};

export type DealerAuditSummary = {
  dealer_id: string;
  dealer_name: string;
  event_count: number;
  by_category: Record<string, number>;
  recent_events: HubAuditEvent[];
};

export async function getAuditCatalog(): Promise<{ categories: AuditCategoryEntry[] }> {
  return hubFetch("/hub/dealer-management/audit/catalog");
}

export async function listAuditEvents(filters?: {
  dealer_id?: string;
  category?: string;
  event_type?: string;
  limit?: number;
}): Promise<AuditEventsResult> {
  const params = new URLSearchParams();
  if (filters?.dealer_id) params.set("dealer_id", filters.dealer_id);
  if (filters?.category) params.set("category", filters.category);
  if (filters?.event_type) params.set("event_type", filters.event_type);
  if (filters?.limit) params.set("limit", String(filters.limit));
  const qs = params.toString();
  return hubFetch(`/hub/dealer-management/audit/events${qs ? `?${qs}` : ""}`);
}

export async function getDealerAuditSummary(dealerId: string): Promise<DealerAuditSummary> {
  return hubFetch(`/hub/dealer-management/audit/dealer/${dealerId}`);
}

export type ContactRole = "general_manager" | "billing" | "it_integrations" | "sales_manager" | "service_manager" | "marketing" | "other";

export type ContactRoleEntry = { key: ContactRole; label: string };

export type DealerContact = {
  contact_id: string;
  dealer_id: string;
  name: string;
  role: ContactRole;
  role_label: string;
  email: string | null;
  phone: string | null;
  added_by: string;
  added_at: string;
};

export type DealerUsers = {
  dealer_id: string;
  dealer_name: string;
  primary_contact: {
    name: string | null;
    email: string | null;
    phone: string | null;
    role: "primary";
    role_label: string;
  };
  additional_contacts: DealerContact[];
  total_contacts: number;
  scope_note: string;
};

export async function getUsersCatalog(): Promise<{ roles: ContactRoleEntry[] }> {
  return hubFetch("/hub/dealer-management/users/catalog");
}

export async function getDealerUsers(dealerId: string): Promise<DealerUsers> {
  return hubFetch(`/hub/dealer-management/users/${dealerId}`);
}

export async function addDealerContact(
  dealerId: string,
  input: { name: string; role: ContactRole; email?: string; phone?: string }
): Promise<DealerUsers> {
  return hubFetch(`/hub/dealer-management/users/${dealerId}`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function removeDealerContact(contactId: string): Promise<DealerUsers> {
  return hubFetch(`/hub/dealer-management/users/contact/${contactId}`, {
    method: "DELETE",
  });
}

// ---------------------------------------------------------------------------
// Infrastructure & Platform Operations rebuild, slice 1 of 4 (Overview +
// Platform Status Board + Services; the other 9 menu items -- Clusters/
// Databases/Storage/Backups/Disaster Recovery [slice 2], AI Infrastructure/
// Network Health [slice 3], Messaging/Security/Monitoring [slice 4] -- are
// honest "coming soon" placeholders rendered client-side, no backend calls
// needed for those yet). See hub/core/infra_overview.py / platform_status.py
// / infra_services.py / hub_platform_metrics.py for the full real-signal-
// vs-fabricated-telemetry reasoning -- every figure here is a real request/
// error/latency count or a real, live reachability check, never a fabricated
// CPU/node/cluster number.
// ---------------------------------------------------------------------------

export type InfraTopology = {
  hub_processes: number;
  tenant_processes_registered: number;
  tenant_processes_reachable: number;
  tenant_processes_unreachable: number;
  tenant_processes_not_configured: number;
  deployment_model: string;
};

export type InfraOverview = {
  topology: InfraTopology;
  hub_uptime_seconds: number;
  platform_health: { summary: string; basis: string; note: string };
  dealers: DealerHealthCheck[];
  note: string;
};

export type PlatformMetricsGroup = {
  label: string;
  request_count: number;
  error_count: number;
  error_rate_pct: number;
  avg_latency_ms: number | null;
  sample_size: number;
  last_request_at: string | null;
  last_error_at: string | null;
  status: string;
  status_label: string;
};

export type PlatformMetricsSnapshot = {
  process_start_time: number;
  uptime_seconds: number;
  groups: Record<string, PlatformMetricsGroup>;
  note: string;
};

export type PlatformStatusEntry = {
  service_id: string;
  service_label: string;
  status: string;
  status_label: string;
  request_count: number | null;
  error_count: number | null;
  error_rate_pct: number | null;
  avg_latency_ms: number | null;
  scope: "hub" | "tenant";
  dealer_id: string | null;
};

export type PlatformStatusBoard = {
  overall_status: string;
  entries: PlatformStatusEntry[];
  counts: {
    down: number;
    degraded: number;
    performance_warning: number;
    unreachable: number;
    total: number;
  };
  note: string;
};

export type DealerServiceSummary = {
  dealer_id: string;
  dealer_name: string;
  checked: boolean;
  reachable: boolean | null;
  fetched_at: string | null;
  error: string | null;
  group_count: number;
};

export type ServicesOverview = {
  hub_metrics: PlatformMetricsSnapshot;
  dealers: DealerServiceSummary[];
  note: string;
};

export type DealerPlatformMetricsSnapshot = {
  dealer_id: string;
  fetched_at: string | null;
  reachable: boolean;
  error: string | null;
  data: Partial<PlatformMetricsSnapshot>;
};

export type DealerPlatformMetricsResult = {
  dealer_id: string;
  dealer_name: string;
  snapshot: DealerPlatformMetricsSnapshot;
};

export async function getInfraOverview(): Promise<InfraOverview> {
  return hubFetch("/hub/infra/overview");
}

export async function getPlatformStatusBoard(): Promise<PlatformStatusBoard> {
  return hubFetch("/hub/infra/platform-status");
}

export async function getServicesOverview(): Promise<ServicesOverview> {
  return hubFetch("/hub/infra/services");
}

export async function getDealerServices(dealerId: string): Promise<DealerPlatformMetricsResult> {
  return hubFetch(`/hub/infra/services/${dealerId}`);
}

export async function recheckDealerServices(dealerId: string): Promise<DealerPlatformMetricsSnapshot> {
  return hubFetch(`/hub/infra/services/${dealerId}/recheck`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// Infrastructure & Platform Operations rebuild, slice 2 of 4: Clusters /
// Databases / Storage / Backups / Disaster Recovery. Same discipline as
// slice 1: real signals (real file sizes, real entity/relationship counts,
// real reachability/latency, real dealer-signup growth trend) with explicit
// "not yet applicable -- single-process/single-file deployment today"
// framing wherever Sam's spec named something (CPU%, node count,
// replication lag, Replica/Analytics/Warehouse/AI Data Stores) that has no
// real backing mechanism anywhere in this codebase. See hub/core/clusters.py
// / databases.py / hub_storage_status.py / dealer_backups.py /
// disaster_recovery.py / tenant_storage_metrics.py for the full reasoning.
// ---------------------------------------------------------------------------

export type ClusterDealerBrief = {
  dealer_id: string;
  dealer_name: string;
  slug: string;
  status: string;
  reachability: string;
  latency_ms: number | null;
};

export type ClusterEntry = {
  region_key: string;
  region_label: string;
  current_nodes: number;
  reachable: number;
  unreachable: number;
  not_configured: number;
  dealers: ClusterDealerBrief[];
  metrics: {
    avg_latency_ms: number | null;
    latency_basis: string;
    cpu: null;
    memory: null;
    network: null;
    resource_telemetry_note: string;
  };
  auto_scale: {
    current_nodes: number;
    max_nodes: null;
    auto_scale_note: string;
  };
};

export type GrowthTrendPoint = { month: string; new_dealers: number; cumulative_dealers: number };

export type ClustersOverview = {
  clusters: ClusterEntry[];
  growth_trend: {
    basis: string;
    note: string;
    points: GrowthTrendPoint[];
  };
  deployment_model_note: string;
  available_regions: string[];
};

export async function getClustersOverview(): Promise<ClustersOverview> {
  return hubFetch("/hub/infra/clusters");
}

export type DatabaseTierEntry = {
  tier: string;
  label: string;
  health: string;
  basis: string | null;
  load: unknown;
  storage: unknown;
  note: string;
};

export type DealerDatabasesSummary = {
  dealer_id: string;
  dealer_name: string;
  tiers: DatabaseTierEntry[];
};

export type DatabasesOverview = {
  dealers: DealerDatabasesSummary[];
  note: string;
};

export type DealerDatabasesDetail = {
  dealer_id: string;
  dealer_name: string;
  primary: DatabaseTierEntry;
  raw_snapshot: {
    dealer_id: string;
    fetched_at: string | null;
    reachable: boolean;
    basis: string | null;
    error: string | null;
    data: Record<string, unknown>;
  };
};

export async function getDatabasesOverview(): Promise<DatabasesOverview> {
  return hubFetch("/hub/infra/databases");
}

export async function getDealerDatabases(dealerId: string): Promise<DealerDatabasesDetail> {
  return hubFetch(`/hub/infra/databases/${dealerId}`);
}

export type HubStorageFile = { store: string; path: string; exists: boolean; size_bytes: number };

export type StorageOverview = {
  hub_storage: { files: HubStorageFile[]; total_size_bytes: number };
  dealers: Array<{
    dealer_id: string;
    dealer_name: string;
    checked: boolean;
    reachable: boolean | null;
    basis: string | null;
    fetched_at: string | null;
    data: Record<string, unknown>;
  }>;
  note: string;
};

export type DealerStorageSnapshot = {
  dealer_id: string;
  fetched_at: string | null;
  reachable: boolean;
  basis: string | null;
  error: string | null;
  data: Record<string, unknown>;
};

export async function getStorageOverview(): Promise<StorageOverview> {
  return hubFetch("/hub/infra/storage");
}

export async function recheckDealerStorage(dealerId: string): Promise<DealerStorageSnapshot> {
  return hubFetch(`/hub/infra/storage/${dealerId}/recheck`, { method: "POST" });
}

export type DealerBackupsSummaryRow = {
  dealer_id: string;
  dealer_name: string;
  observed_backup_count: number | null;
  observed_latest_backup_at: string | null;
  logged_event_count: number;
  latest_logged_event_at: string | null;
};

export type BackupLogEntry = {
  log_id: string;
  dealer_id: string;
  logged_by: string;
  label: string | null;
  note: string | null;
  logged_at: string | null;
  timestamp_status?: "known" | "unknown" | "invalid";
};

export type BackupsOverview = {
  dealers: DealerBackupsSummaryRow[];
  recent_logged_events: BackupLogEntry[];
  summary: { total_dealers: number; total_observed_backups: number; total_logged_events: number };
  note: string;
};

export type DealerBackupsDetail = {
  dealer_id: string;
  dealer_name: string;
  observed: {
    checked: boolean;
    reachable: boolean;
    basis: string | null;
    fetched_at: string | null;
    backups: { file_count: number; total_size_bytes: number; latest_file: string | null; latest_modified_at: string | null } | null;
  };
  logged_events: BackupLogEntry[];
  note: string;
};

export async function getBackupsOverview(): Promise<BackupsOverview> {
  return hubFetch("/hub/infra/backups");
}

export async function getDealerBackups(dealerId: string): Promise<DealerBackupsDetail> {
  return hubFetch(`/hub/infra/backups/${dealerId}`);
}

export async function logDealerBackup(
  dealerId: string,
  input: { logged_by: string; label?: string; note?: string }
): Promise<DealerBackupsDetail> {
  return hubFetch(`/hub/infra/backups/${dealerId}/log`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export type RecoveryPlaybookStep = { step: number; title: string; detail: string };

export type DealerDisasterRecoveryRow = {
  dealer_id: string;
  dealer_name: string;
  current_reachability: string;
  latest_observed_backup: { file_count: number | null; latest_file: string | null; latest_modified_at: string | null } | null;
  latest_logged_backup_event: BackupLogEntry | null;
  git_snapshot_check: {
    tracked_in_git: boolean;
    last_commit_hash: string;
    last_committed_at: string | null;
    basis: string;
    note: string;
  } | null;
};

export type DisasterRecoveryStatus = {
  dealers: DealerDisasterRecoveryRow[];
  playbook: RecoveryPlaybookStep[];
  disclosure: string;
};

export async function getDisasterRecoveryStatus(): Promise<DisasterRecoveryStatus> {
  return hubFetch("/hub/infra/disaster-recovery");
}

// ---------------------------------------------------------------------------
// Infrastructure & Platform Operations rebuild, slice 3 of 4 -- AI
// Infrastructure + Network Health (with Privacy Audit). See
// hub/core/infra_ai.py / hub/core/infra_network_health.py for the full
// real-vs-honest-gap reasoning behind every field below.
// ---------------------------------------------------------------------------

export type AiModelSummary = {
  key: string;
  label: string;
  reasoning: string;
  feature_count: number;
  gap_note: string | null;
  usage_attempted: number;
  usage_succeeded: number;
  usage_fell_back: number;
  usage_blocked: number;
  enabled_count: number;
};

export type AiModelBreakdown = {
  key: string;
  label: string;
  feature_count: number;
  mapped_feature_count: number;
  enabled_count: number;
  usage_attempted: number;
  usage_succeeded: number;
  usage_fell_back: number;
  usage_blocked: number;
  features: AiFeatureSnapshot[];
  gap_note: string | null;
};

export type AiInfrastructureDealerRow = {
  dealer_id: string;
  dealer_name: string;
  checked: boolean;
  reachable: boolean;
  fetched_at: string | null;
  fetch_error: string | null;
  models: AiModelBreakdown[];
};

export type TrainingJobsStatus = {
  running: number | null;
  queued: number | null;
  failed: number | null;
  applicable: boolean;
  note: string;
};

export type AiInfrastructureOverview = {
  dealers_total: number;
  dealers_checked: number;
  dealers_reachable: number;
  models: AiModelSummary[];
  per_dealer: AiInfrastructureDealerRow[];
  response_time_gap: string;
  accuracy_gap: string;
  cost_gap: string;
  training_jobs: TrainingJobsStatus;
  note: string;
};

export type RecheckAllAiResult = {
  checked: number;
  skipped: number;
  results: {
    dealer_id: string;
    dealer_name: string;
    skipped: boolean;
    reason?: string;
    reachable?: boolean;
    fetch_error?: string | null;
  }[];
};

export async function getAiInfrastructureOverview(): Promise<AiInfrastructureOverview> {
  return hubFetch("/hub/infra/ai-infrastructure");
}

export async function recheckAllAiInfrastructure(): Promise<RecheckAllAiResult> {
  return hubFetch("/hub/infra/ai-infrastructure/recheck-all", { method: "POST" });
}

export async function recheckDealerAiInfrastructure(
  dealerId: string
): Promise<DealerAiManagementStatus> {
  return hubFetch(`/hub/infra/ai-infrastructure/${dealerId}/recheck`, { method: "POST" });
}

export type JobStatusPlaceholder = {
  running: number | null;
  queued: number | null;
  failed: number | null;
  applicable: boolean;
  note: string;
};

export type PrivacyAuditPiiFinding = {
  type: string;
  value_excerpt: string;
};

export type PrivacyAudit = {
  passed: boolean;
  schema_check: {
    fields_inspected: string[];
    violations: string[];
    note: string;
  };
  stored_record_check: {
    records_inspected: number;
    distinct_keys_found: string[];
    unexpected_keys: string[];
    violations: string[];
    pii_pattern_findings: PrivacyAuditPiiFinding[];
    note: string;
  };
  never_collect_fields: string[];
  nxtdeal_sees_fields: string[];
  method_note: string;
};

export type NetworkHealthOverview = {
  network_members: number;
  total_dealers: number;
  active_snapshots: number;
  anonymous_datasets: number;
  datasets_note: string;
  prediction_runs: JobStatusPlaceholder;
  benchmark_jobs: JobStatusPlaceholder;
  privacy_audit: PrivacyAudit;
  note: string;
};

export async function getNetworkHealthOverview(): Promise<NetworkHealthOverview> {
  return hubFetch("/hub/infra/network-health");
}

export async function getPrivacyAudit(): Promise<PrivacyAudit> {
  return hubFetch("/hub/infra/network-health/privacy-audit");
}

// ---------------------------------------------------------------------------
// Infrastructure & Platform Operations rebuild, slice 4 of 4 (CLOSING) --
// Messaging + Security + Monitoring. See hub/core/infra_messaging.py,
// hub/core/infra_security.py, and hub/core/infra_monitoring.py for the full
// real-vs-honest-gap reasoning. All three reuse already-fetched Hub state
// (no new tenant route, no new Recheck action for any of the three) -- this
// closes out the entire 12-item Infrastructure & Platform Operations menu.
// ---------------------------------------------------------------------------

export type MessagingSubsystemSnapshot = {
  employees_with_open_connection: number;
  open_socket_count: number;
  channels_configured: number;
  note: string;
};

export type DealerMessagingRow = {
  dealer_id: string;
  dealer_name: string;
  checked: boolean;
  reachable: boolean | null;
  fetched_at: string | null;
  messaging_subsystem: MessagingSubsystemSnapshot | null;
};

export type MessagingOverview = {
  cross_tenant_messaging: { applicable: boolean; note: string };
  per_dealer_chat_liveness: DealerMessagingRow[];
  aggregate: {
    dealers_checked: number;
    dealers_total: number;
    total_open_socket_count: number;
    total_employees_with_open_connection: number;
  };
  note: string;
};

export async function getMessagingOverview(): Promise<MessagingOverview> {
  return hubFetch("/hub/infra/messaging");
}

export type HubSecurityPosture = {
  hub_shared_key_configured_from_env: boolean;
  network_shared_key_configured_from_env: boolean;
  hub_shared_key_using_dev_fallback?: boolean;
  network_shared_key_using_dev_fallback?: boolean;
  summary: string;
  note: string;
};

export type TenantSecurityPosture = {
  total_accounts: number;
  locked_accounts_count: number;
  ip_allowlist_configured_count: number;
  ip_allowlisting_in_use: boolean;
  password_policy_enforced: boolean;
  password_policy: { min_length: number; requires_letter_and_digit: boolean };
  lockout_policy: { max_failed_attempts: number; lockout_minutes: number };
  note: string;
};

export type DealerSecurityRow = {
  dealer_id: string;
  dealer_name: string;
  checked: boolean;
  reachable: boolean | null;
  fetched_at: string | null;
  security_posture: TenantSecurityPosture | null;
};

export type SecurityOverview = {
  hub_security_posture: HubSecurityPosture;
  tenant_account_security: {
    dealers: DealerSecurityRow[];
    aggregate: {
      dealers_checked: number;
      dealers_total: number;
      total_accounts_across_checked_dealers: number;
      total_locked_accounts_across_checked_dealers: number;
      dealers_with_ip_allowlisting_in_use: number;
    };
    note: string;
  };
};

export async function getSecurityOverview(): Promise<SecurityOverview> {
  return hubFetch("/hub/infra/security");
}

export type MonitoringOverview = {
  overall_status: string;
  subsystems_needing_attention: string[];
  noc_summary: {
    overall_status: string;
    alert_counts: { critical: number; warning: number; info: number };
    top_alerts: NocAlert[];
    see_full_view: string;
  };
  platform_status_summary: {
    overall_status: string;
    counts: {
      down: number;
      degraded: number;
      performance_warning: number;
      unreachable: number;
      total: number;
    };
    worst_entries: PlatformStatusEntry[];
    see_full_view: string;
  };
  ai_infrastructure_summary: {
    dealers_checked: number;
    dealers_reachable: number;
    dealers_total: number;
    confirmed_gaps: string[];
    see_full_view: string;
  };
  network_health_summary: {
    network_members: number;
    active_snapshots: number;
    privacy_audit_passed: boolean;
    see_full_view: string;
  };
  note: string;
};

export async function getMonitoringOverview(): Promise<MonitoringOverview> {
  return hubFetch("/hub/infra/monitoring");
}

// ---------------------------------------------------------------------------
// NXTDeal Network Connect (2026-07-19) -- Hub-staff console client. Talks to
// the NXTDeal-staff-only /hub/network-connect/* routes (hub/core/
// network_connect_api.py), gated by the same bearer token hubFetch()
// already attaches to every Hub call. Deliberately does NOT wrap the
// self-service /network-connect/* routes (signup, connected-systems,
// kpi-snapshot, benchmark) -- those are account_token/pseudonym-gated and
// belong to the browser extension (network-connect-extension/popup.js), not
// a NXTDeal-staff session. See hub/core/network_connect.py's own module
// docstring for the full "two data flows, two privacy postures" design this
// whole feature is built on.
// ---------------------------------------------------------------------------

export type ConnectorProvider = {
  provider_key: string;
  display_name: string;
  integration_status: string;
};

export type ConnectorCategory = {
  category: string;
  label: string;
  providers: ConnectorProvider[];
};

export async function getNetworkConnectConnectorCatalog(): Promise<{ categories: ConnectorCategory[] }> {
  return hubFetch("/network-connect/connectors");
}

export type NetworkConnectGoLiveStatus = "not_started" | "blocked" | "at_risk" | "ready";

export type NetworkConnectAccountSummary = {
  account_id: string;
  company_name: string;
  contact_email: string;
  tier: "free" | "premium";
  status: "active" | "trial_expired" | "churned" | "converted_to_dealer";
  connected_system_count: number;
  go_live_status: NetworkConnectGoLiveStatus;
  converted_dealer_id: string | null;
  created_at: string;
};

export async function listNetworkConnectAccounts(): Promise<{ accounts: NetworkConnectAccountSummary[] }> {
  return hubFetch("/hub/network-connect/accounts");
}

export type NetworkConnectOverview = {
  total_accounts: number;
  by_tier: Record<string, number>;
  by_status: Record<string, number>;
  by_go_live_status: Record<string, number>;
  connector_adoption: Record<string, number>;
  converted_to_dealer_count: number;
  note: string;
};

export async function getNetworkConnectOverview(): Promise<NetworkConnectOverview> {
  return hubFetch("/hub/network-connect/overview");
}

export type NetworkConnectConnectedSystemDetail = {
  category: string;
  label: string;
  provider_key: string | null;
  provider_display_name: string | null;
};

export type NetworkConnectReadinessDetail = {
  key: string;
  label: string;
  pct: number | null;
  note: string | null;
};

export type NetworkConnectAccountDetail = {
  account_id: string;
  company_name: string;
  contact_email: string;
  contact_name: string | null;
  contact_phone: string | null;
  tier: "free" | "premium";
  status: "active" | "trial_expired" | "churned" | "converted_to_dealer";
  connected_systems: Record<string, string>;
  migration_readiness: Record<string, number>;
  migration_readiness_notes: Record<string, string>;
  converted_dealer_id: string | null;
  created_by: string;
  created_at: string;
  updated_at: string;
  connected_systems_detail: NetworkConnectConnectedSystemDetail[];
  migration_readiness_detail: NetworkConnectReadinessDetail[];
  go_live_status: NetworkConnectGoLiveStatus;
  go_live_reason: string;
  migration_readiness_note: string;
};

export async function getNetworkConnectAccount(accountId: string): Promise<NetworkConnectAccountDetail> {
  return hubFetch(`/hub/network-connect/accounts/${accountId}`);
}

export async function setNetworkConnectTier(
  accountId: string,
  tier: "free" | "premium"
): Promise<NetworkConnectAccountDetail> {
  return hubFetch(`/hub/network-connect/accounts/${accountId}/tier`, {
    method: "POST",
    body: JSON.stringify({ tier }),
  });
}

export async function setNetworkConnectStatus(
  accountId: string,
  status: "active" | "trial_expired" | "churned"
): Promise<NetworkConnectAccountDetail> {
  return hubFetch(`/hub/network-connect/accounts/${accountId}/status`, {
    method: "POST",
    body: JSON.stringify({ status }),
  });
}

export async function setNetworkConnectReadiness(
  accountId: string,
  category: string,
  pct: number,
  note?: string
): Promise<NetworkConnectAccountDetail> {
  return hubFetch(`/hub/network-connect/accounts/${accountId}/migration-readiness`, {
    method: "POST",
    body: JSON.stringify({ category, pct, note: note ?? null }),
  });
}

export type ConvertToDealerResult = {
  dealer: Dealer;
  admin_employee_id: string;
  admin_temp_password: string;
  network_connect_account: NetworkConnectAccountDetail;
  note: string;
};

export async function convertNetworkConnectAccountToDealer(
  accountId: string,
  planTier: string = "Standard"
): Promise<ConvertToDealerResult> {
  return hubFetch(`/hub/network-connect/accounts/${accountId}/convert-to-dealer`, {
    method: "POST",
    body: JSON.stringify({ plan_tier: planTier }),
  });
}

// ---------------------------------------------------------------------------
// AI-Powered Self-Auditing Code Layer (2026-07-19) -- hub/core/code_auditor.py.
// Sam's own kickoff request, scoped via AskUserQuestion into 3 binding
// decisions: build the auditor first, then run the first sweep; every
// small-issue auto-fix lands on its own dedicated git branch with a real
// commit, nothing ever auto-merges to main; scanning "deployed dealerships"
// means the one shared codebase every tenant runs, not per-tenant runtime
// health (that's the separate Infrastructure & Platform Ops/NOC system
// above). Every finding comes from a real, deterministic static-analysis
// rule over real files -- never an AI judgment call.
// ---------------------------------------------------------------------------

export type CodeAuditSeverity = "small" | "medium" | "large";
export type CodeAuditArea = "backend" | "hub" | "frontend" | "extension";
export type CodeAuditStatus =
  | "new"
  | "auto_fixed"
  | "awaiting_approval"
  | "approved"
  | "rejected"
  | "reported"
  | "resolved"
  | "dismissed";

export type CodeAuditCatalog = {
  severity_levels: CodeAuditSeverity[];
  status_values: CodeAuditStatus[];
  areas: CodeAuditArea[];
};

export type CodeAuditFinding = {
  finding_id: string;
  run_id: string;
  rule_key: string;
  rule_title: string;
  severity: CodeAuditSeverity;
  area: CodeAuditArea;
  file_path: string;
  line_number: number | null;
  description: string;
  evidence: string;
  recommendation: string;
  status: CodeAuditStatus;
  proposed_fix: string | null;
  branch_name: string | null;
  commit_sha: string | null;
  resolved_by: string | null;
  resolved_note: string | null;
  created_at: string;
  updated_at: string;
};

export type CodeAuditRun = {
  run_id: string;
  triggered_by: string;
  areas_scanned: CodeAuditArea[];
  started_at: string;
  completed_at: string | null;
  total_findings: number;
  by_severity: Record<CodeAuditSeverity, number>;
  status: "running" | "completed" | "failed";
  error: string | null;
};

export type CodeAuditOverview = {
  total_findings: number;
  open_findings: number;
  by_severity_open: Record<CodeAuditSeverity, number>;
  by_area_open: Record<CodeAuditArea, number>;
  auto_fixed_count: number;
  awaiting_approval_count: number;
  reported_large_count: number;
  last_run: CodeAuditRun | null;
  total_runs: number;
  severity_labels: Record<CodeAuditSeverity, string>;
  note: string;
};

export type CodeAuditSchedulerStatus = {
  running: boolean;
  tick_seconds: number;
  last_scheduled_run: CodeAuditRun | null;
  last_scheduled_run_at: string | null;
  next_scheduled_run_at: string | null;
};

export async function getCodeAuditCatalog(): Promise<CodeAuditCatalog> {
  return hubFetch("/hub/code-audit/catalog");
}

export async function getCodeAuditOverview(): Promise<CodeAuditOverview> {
  return hubFetch("/hub/code-audit/overview");
}

export async function getCodeAuditSchedulerStatus(): Promise<CodeAuditSchedulerStatus> {
  return hubFetch("/hub/code-audit/scheduler-status");
}

export async function runCodeAuditScan(
  triggeredBy: string = "nxtdeal_staff",
  areas?: CodeAuditArea[]
): Promise<CodeAuditRun> {
  return hubFetch("/hub/code-audit/scan", {
    method: "POST",
    body: JSON.stringify({ triggered_by: triggeredBy, areas: areas ?? null }),
  });
}

export async function listCodeAuditFindings(filters?: {
  severity?: CodeAuditSeverity;
  status?: CodeAuditStatus;
  area?: CodeAuditArea;
  run_id?: string;
}): Promise<{ findings: CodeAuditFinding[]; total_matches: number }> {
  const params = new URLSearchParams();
  if (filters?.severity) params.set("severity", filters.severity);
  if (filters?.status) params.set("status", filters.status);
  if (filters?.area) params.set("area", filters.area);
  if (filters?.run_id) params.set("run_id", filters.run_id);
  const qs = params.toString();
  return hubFetch(`/hub/code-audit/findings${qs ? `?${qs}` : ""}`);
}

export async function getCodeAuditFinding(findingId: string): Promise<CodeAuditFinding> {
  return hubFetch(`/hub/code-audit/findings/${findingId}`);
}

export async function approveCodeAuditFinding(
  findingId: string,
  approvedBy: string,
  note?: string
): Promise<CodeAuditFinding & { warning?: string }> {
  return hubFetch(`/hub/code-audit/findings/${findingId}/approve`, {
    method: "POST",
    body: JSON.stringify({ approved_by: approvedBy, note: note ?? null }),
  });
}

export async function rejectCodeAuditFinding(
  findingId: string,
  rejectedBy: string,
  note?: string
): Promise<CodeAuditFinding> {
  return hubFetch(`/hub/code-audit/findings/${findingId}/reject`, {
    method: "POST",
    body: JSON.stringify({ rejected_by: rejectedBy, note: note ?? null }),
  });
}

export async function resolveCodeAuditFinding(
  findingId: string,
  resolvedBy: string,
  note?: string
): Promise<CodeAuditFinding> {
  return hubFetch(`/hub/code-audit/findings/${findingId}/resolve`, {
    method: "POST",
    body: JSON.stringify({ resolved_by: resolvedBy, note: note ?? null }),
  });
}

export async function dismissCodeAuditFinding(
  findingId: string,
  dismissedBy: string,
  note: string
): Promise<CodeAuditFinding> {
  return hubFetch(`/hub/code-audit/findings/${findingId}/dismiss`, {
    method: "POST",
    body: JSON.stringify({ dismissed_by: dismissedBy, note }),
  });
}

export async function listCodeAuditRuns(): Promise<{ runs: CodeAuditRun[] }> {
  return hubFetch("/hub/code-audit/runs");
}

export async function getCodeAuditRun(
  runId: string
): Promise<{ run: CodeAuditRun; findings: CodeAuditFinding[] }> {
  return hubFetch(`/hub/code-audit/runs/${runId}`);
}

// ---------------------------------------------------------------------------
// AI Kill Switch -- security-hardening pass Task #6 ("Expand AI kill switch
// to dealer/department/bot/workflow scope"). A NXTDeal staffer can see one
// dealer's real, LIVE (never cached) 4-scope AI kill-switch state and push a
// real emergency stop to that dealer's own tenant process directly from the
// Hub console -- gated by the same DEALEROS_NETWORK_KEY shared secret
// hub_core/dealer_ai_management.py's own AI snapshot pull already uses. See
// hub_core/dealer_ai_kill_switch.py's own module docstring for the full
// design (why status is always live, why every push -- success or failure --
// is a permanent record).
// ---------------------------------------------------------------------------

export const KILL_SWITCH_SCOPES = [
  "dealer_wide",
  "department",
  "bot",
  "workflow_automation",
] as const;

export type KillSwitchScope = (typeof KILL_SWITCH_SCOPES)[number];

// Matches backend/core/ai_kill_switch.py's REAL_DEPARTMENTS exactly (order
// matters -- this drives the department picker in the push form).
export const KILL_SWITCH_DEPARTMENTS = [
  "Operations",
  "Sales",
  "Service",
  "Marketing",
  "Inventory",
  "Finance",
  "Administration",
  "Readiness",
  "Network",
] as const;

export type AiKillSwitchScopeState = {
  active: boolean;
  activated_by: string | null;
  activated_at: string | null;
  reason: string | null;
};

export type AiKillSwitchFeatureBrief = { key: string; name: string };

export type AiKillSwitchDepartmentState = AiKillSwitchScopeState & {
  department: string;
  governed_features: AiKillSwitchFeatureBrief[];
};

// The real, composed 4-scope dashboard payload -- backend/core/ai_kill_switch.py's
// get_kill_switch_overview(), fetched live over the network for the Hub's own
// incident-response console (core/ai_kill_switch_network_api.py's
// get_ai_kill_switch_status_network_api()).
export type AiKillSwitchOverviewState = {
  dealer_wide: AiKillSwitchScopeState;
  departments: AiKillSwitchDepartmentState[];
  cross_department_features: AiKillSwitchFeatureBrief[];
  bot: AiKillSwitchScopeState;
  workflow_automation: AiKillSwitchScopeState;
  generated_at: string;
};

export type DealerKillSwitchStatus = {
  dealer_id: string;
  dealer_name: string;
  reachable: boolean;
  fetch_error: string | null;
  fetched_at: string;
  state: AiKillSwitchOverviewState | null;
};

export type KillSwitchAction = {
  action_id: string;
  dealer_id: string;
  dealer_name?: string | null;
  pushed_by: string;
  scope: KillSwitchScope;
  active: boolean;
  reason: string | null;
  department: string | null;
  success: boolean;
  push_error: string | null;
  // The single pushed scope's resulting state (not the full 4-scope
  // overview) -- backend/core/ai_kill_switch_network_api.py's
  // push_ai_kill_switch_api() returns {scope, department, state}, and
  // resulting_state is that inner "state".
  resulting_state: AiKillSwitchScopeState | null;
  pushed_at: string;
};

export type DealerKillSwitchHistory = {
  dealer_id: string;
  dealer_name: string;
  actions: KillSwitchAction[];
};

export type AllKillSwitchHistory = {
  actions: KillSwitchAction[];
  summary: { total_actions: number; successful_pushes: number; failed_pushes: number };
  note: string;
};

export async function getDealerKillSwitchStatus(dealerId: string): Promise<DealerKillSwitchStatus> {
  return hubFetch(`/hub/ai-kill-switch/${dealerId}/status`);
}

export async function pushDealerKillSwitch(
  dealerId: string,
  input: {
    pushed_by: string;
    scope: KillSwitchScope;
    active: boolean;
    reason?: string;
    department?: string;
  }
): Promise<KillSwitchAction> {
  return hubFetch(`/hub/ai-kill-switch/${dealerId}/push`, {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export async function getDealerKillSwitchHistory(dealerId: string): Promise<DealerKillSwitchHistory> {
  return hubFetch(`/hub/ai-kill-switch/${dealerId}/history`);
}

export async function getAllKillSwitchHistory(): Promise<AllKillSwitchHistory> {
  return hubFetch("/hub/ai-kill-switch/history");
}

export type LabPolicyStatus = {dealer_id:string;desired:boolean;live:{enabled:boolean;revision:number;updated_at:string|null};synchronized:boolean};
export async function getLabPolicyStatus(dealerId:string):Promise<LabPolicyStatus>{return hubFetch(`/hub/dealer-management/lab-policy/${encodeURIComponent(dealerId)}`);}
export async function synchronizeLabPolicy(dealerId:string,revision:number):Promise<LabPolicyStatus>{return hubFetch(`/hub/dealer-management/lab-policy/${encodeURIComponent(dealerId)}`,{method:'POST',body:JSON.stringify({revision})});}
