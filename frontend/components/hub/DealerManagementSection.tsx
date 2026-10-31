"use client";

import { dealerDisplayName } from "@/lib/brandDisplay";

// NXTDeal Hub -- "Dealer Management" rebuild (2026-07-19). Sam's own framing, after
// NXTDeal's tenant-side product grew well past a single "Dealers" list: "Dealer" is
// really a tenant, and this screen should become "Salesforce Trust + Azure Admin
// Center + HubSpot Operations Hub + Datadog + 20 Group Intelligence inside one
// control center" -- a 12-item real menu (Overview | Dealers | Provisioning |
// Licensing | Modules | Integrations | Users | Network | AI | Migration | Support |
// Audit).
//
// This slice (1 of 5 planned) ships the real menu shell for all 12 items, plus real
// content behind exactly two of them: Overview (real KPIs + a real Dealer Lifecycle
// Funnel off hub/core/dealer_overview.py) and Dealers (the existing dealer list,
// now click-through into a full Dealer Record view -- hub/core/dealer_profile.py's
// Profile/Subscription/Version fields). The other 10 items render an honest
// "coming soon" placeholder -- NOT fabricated data -- since their real backends are
// separately scoped, later slices (Module Management/Feature Flags, Onboarding/
// Migration Tracking, Integrations/AI Management, Network Membership/Support/Audit).
//
// Split out of app/hub-console/page.tsx (which was pushing 900 lines) into its own
// component, matching this codebase's own "extract when a page file gets unwieldy"
// convention.

import { useEffect, useState } from "react";
import {
  HubApiError,
  getLabPolicyStatus,
  synchronizeLabPolicy,
  type LabPolicyStatus,
  listDealers,
  getDealerManagementOverview,
  getModuleCatalog,
  getDealerModules,
  setDealerModule,
  getFeatureFlagScopes,
  listFeatureFlagOverrides,
  createFeatureFlagOverride,
  deleteFeatureFlagOverride,
  resolveFeatureFlag,
  getOnboardingCatalog,
  getDealerOnboarding,
  recheckDealerOnboarding,
  setDealerOnboardingStep,
  getMigrationCatalog,
  getDealerMigration,
  setDealerMigrationSource,
  setDealerReadiness,
  getIntegrationsCatalog,
  getDealerIntegrations,
  addDealerIntegration,
  updateDealerIntegration,
  removeDealerIntegration,
  getAiAreaCatalog,
  getDealerAiManagement,
  recheckDealerAiManagement,
  getNetworkMembershipCatalog,
  getDealerNetworkMembership,
  setDealerNetworkTier,
  recheckDealerPipelineConnectivity,
  getDealerSupportStatus,
  recheckDealerSupportSnapshot,
  getAuditCatalog,
  listAuditEvents,
  getUsersCatalog,
  getDealerUsers,
  addDealerContact,
  removeDealerContact,
  type Dealer,
  type DealerManagementOverview,
  type ModuleCatalogEntry,
  type DealerModuleConfig,
  type FeatureFlagScope,
  type FeatureFlagOverride,
  type FeatureFlagResolution,
  type OnboardingStepCatalogEntry,
  type DealerOnboardingStatus,
  type MigrationCatalog,
  type DealerMigrationStatus,
  type GoLiveStatus,
  type IntegrationsCatalog,
  type DealerIntegrationsStatus,
  type IntegrationHealth,
  type IntegrationDataFlow,
  type AiAreaCatalogEntry,
  type DealerAiManagementStatus,
  type NetworkTierCatalogEntry,
  type NetworkTier,
  type DealerNetworkMembership,
  type DealerSupportStatus,
  type AuditCategoryEntry,
  type HubAuditEvent,
  type ContactRoleEntry,
  type ContactRole,
  type DealerUsers,
} from "@/lib/hubApi";
import DealerRecordView from "./DealerRecordView";
import CreateDealerForm from "./CreateDealerForm";

type MenuItemKey =
  | "overview"
  | "dealers"
  | "provisioning"
  | "licensing"
  | "modules"
  | "integrations"
  | "users"
  | "network"
  | "ai"
  | "migration"
  | "support"
  | "audit";

const MENU_ITEMS: { key: MenuItemKey; label: string; blurb: string }[] = [
  { key: "overview", label: "Overview", blurb: "Real KPIs + the Dealer Lifecycle Funnel." },
  { key: "dealers", label: "Dealers", blurb: "The full tenant roster + Dealer Record." },
  { key: "provisioning", label: "Provisioning", blurb: "Onboarding Center -- new dealer setup pipeline." },
  { key: "licensing", label: "Licensing", blurb: "Feature Flags -- Global / Group / Dealer scoped rollout control." },
  { key: "modules", label: "Modules", blurb: "Module Management -- enable/disable per-dealer, no code required." },
  { key: "integrations", label: "Integrations", blurb: "Per-dealer data connections at a glance." },
  { key: "users", label: "Users", blurb: "Cross-dealer employee/user directory." },
  { key: "network", label: "Network", blurb: "Network Membership -- who's opted into the Intelligence Network." },
  { key: "ai", label: "AI", blurb: "AI Management rollup across every dealer." },
  { key: "migration", label: "Migration", blurb: "Migration Tracking for dealers moving onto NXTDeal." },
  { key: "support", label: "Support", blurb: "Support Center -- tickets, escalations, SLAs." },
  { key: "audit", label: "Audit", blurb: "Cross-dealer Audit Center." },
];

const REAL_ITEMS: MenuItemKey[] = [
  "overview",
  "dealers",
  "modules",
  "licensing",
  "provisioning",
  "migration",
  "integrations",
  "ai",
  "network",
  "support",
  "audit",
  "users",
];

function errorMessage(error: unknown): string {
  return error instanceof HubApiError ? error.message : "Unable to reach the Hub.";
}

function KpiCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-4">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-zinc-500 mt-1">{label}</div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 text-sm text-red-400 bg-red-950/30 border border-red-900 rounded-lg px-4 py-3">
      {message}
    </div>
  );
}

export default function DealerManagementSection() {
  const [item, setItem] = useState<MenuItemKey>("overview");

  return (
    <div className="flex gap-6 h-full">
      <nav className="w-52 shrink-0">
        <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-600 mb-2 px-1">
          Dealer Management
        </div>
        <div className="flex flex-col gap-1">
          {MENU_ITEMS.map((mi) => (
            <button
              key={mi.key}
              onClick={() => setItem(mi.key)}
              title={mi.blurb}
              className={
                item === mi.key
                  ? "bg-zinc-200 text-black font-medium text-left px-3 py-2 rounded text-sm"
                  : "bg-zinc-900 text-zinc-400 hover:text-white text-left px-3 py-2 rounded text-sm transition flex items-center justify-between"
              }
            >
              <span>{mi.label}</span>
              {item !== mi.key && !REAL_ITEMS.includes(mi.key) && (
                <span className="text-[9px] text-zinc-600 uppercase tracking-wide ml-2">
                  soon
                </span>
              )}
            </button>
          ))}
        </div>
      </nav>

      <div className="flex-1 min-w-0">
        {item === "overview" && <DealerManagementOverviewPanel />}
        {item === "dealers" && <DealersPanel />}
        {item === "modules" && <ModulesPanel />}
        {item === "licensing" && <LicensingPanel />}
        {item === "provisioning" && <ProvisioningPanel />}
        {item === "migration" && <MigrationPanel />}
        {item === "integrations" && <IntegrationsPanel />}
        {item === "ai" && <AiManagementPanel />}
        {item === "network" && <NetworkMembershipPanel />}
        {item === "support" && <SupportCenterPanel />}
        {item === "audit" && <AuditCenterPanel />}
        {item === "users" && <UsersPanel />}
        {!REAL_ITEMS.includes(item) && (
          <PlaceholderPanel item={MENU_ITEMS.find((m) => m.key === item)!} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview -- real KPIs + Dealer Lifecycle Funnel
// ---------------------------------------------------------------------------

const FUNNEL_STAGE_COLOR: Record<string, string> = {
  lead: "bg-zinc-700",
  demo: "bg-sky-800",
  trial: "bg-blue-700",
  provisioning: "bg-yellow-700",
  active: "bg-green-700",
  expansion: "bg-emerald-700",
  churn_risk: "bg-orange-800",
};

function DealerManagementOverviewPanel() {
  const [overview, setOverview] = useState<DealerManagementOverview | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setOverview(await getDealerManagementOverview());
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  const maxCount = Math.max(1, ...(overview?.lifecycle_funnel.map((s) => s.count) ?? [1]));

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-3 gap-3 mb-6">
        <KpiCard label="Total Dealers" value={overview?.kpis.total_dealers ?? "..."} />
        <KpiCard label="Trial Dealers" value={overview?.kpis.trial_dealers ?? "..."} />
        <KpiCard label="Active Dealers" value={overview?.kpis.active_dealers ?? "..."} />
        <KpiCard label="Multi-Rooftop Groups" value={overview?.kpis.multi_rooftop_groups ?? "..."} />
        <KpiCard label="Network Members" value={overview?.kpis.network_members ?? "..."} />
        <KpiCard label="Enterprise Accounts" value={overview?.kpis.enterprise_accounts ?? "..."} />
      </div>

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        Dealer Lifecycle Funnel
      </h3>

      <div className="bg-zinc-900 rounded-lg p-5 mb-4">
        <div className="flex items-end gap-2 h-40">
          {(overview?.lifecycle_funnel ?? []).map((stage) => (
            <div key={stage.stage} className="flex-1 flex flex-col items-center justify-end h-full">
              <div className="text-sm font-semibold mb-1">{stage.count}</div>
              <div
                className={`w-full rounded-t ${FUNNEL_STAGE_COLOR[stage.stage] ?? "bg-zinc-700"}`}
                style={{
                  height: `${Math.max(6, (stage.count / maxCount) * 100)}%`,
                }}
              />
              <div className="text-[10px] uppercase tracking-wide text-zinc-500 mt-2 text-center">
                {stage.label}
              </div>
            </div>
          ))}
        </div>
        {overview && overview.suspended_count > 0 && (
          <div className="text-[11px] text-red-400 mt-4">
            + {overview.suspended_count} suspended (off-ramp, not counted in the funnel above)
          </div>
        )}
      </div>

      {overview && (
        <p className="text-[11px] text-zinc-500 leading-relaxed">{overview.note}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dealers -- real roster + click-through Dealer Record
// ---------------------------------------------------------------------------

const STATUS_COLORS: Record<string, string> = {
  lead: "text-zinc-400",
  demo: "text-sky-400",
  trial: "text-blue-400",
  provisioning: "text-yellow-400",
  active: "text-green-400",
  expansion: "text-emerald-400",
  churn_risk: "text-orange-400",
  suspended: "text-red-400",
};

function DealersPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Dealer | null>(null);
  const [showCreate, setShowCreate] = useState(false);

  async function load() {
    try {
      setDealers(await listDealers());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  const active = dealers?.filter((d) => d.status === "active").length ?? 0;
  const provisioning = dealers?.filter((d) => d.status === "provisioning").length ?? 0;

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-4 gap-3 mb-6">
        <KpiCard label="Total Dealers" value={dealers?.length ?? "..."} />
        <KpiCard label="Active" value={active} />
        <KpiCard label="Provisioning" value={provisioning} />
        <KpiCard
          label="Network Opted-In"
          value={dealers?.filter((d) => d.network_opt_in).length ?? 0}
        />
      </div>

      <div className="flex items-center justify-between mb-3">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">Dealerships</h3>
        <button
          onClick={() => setShowCreate((v) => !v)}
          className="bg-zinc-200 text-black font-medium px-4 py-2 rounded text-xs uppercase tracking-wide"
        >
          {showCreate ? "Cancel" : "+ New Dealer"}
        </button>
      </div>

      {showCreate && (
        <CreateDealerForm
          onCreated={() => {
            setShowCreate(false);
            load();
          }}
        />
      )}

      <div className="bg-zinc-900 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Dealer</th>
              <th className="text-left px-4 py-2">Slug</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Plan</th>
              <th className="text-left px-4 py-2">Group</th>
              <th className="text-left px-4 py-2">Contact</th>
            </tr>
          </thead>
          <tbody>
            {(dealers ?? []).map((dealer) => (
              <tr
                key={dealer.dealer_id}
                onClick={() => setSelected(dealer)}
                className="border-t border-zinc-800 hover:bg-zinc-800/60 cursor-pointer"
              >
                <td className="px-4 py-2">{dealerDisplayName(dealer.name)}</td>
                <td className="px-4 py-2 text-zinc-400">{dealer.slug}</td>
                <td className={`px-4 py-2 ${STATUS_COLORS[dealer.status] ?? ""}`}>
                  {dealer.status.replace("_", " ")}
                </td>
                <td className="px-4 py-2 text-zinc-400">{dealer.plan_tier}</td>
                <td className="px-4 py-2 text-zinc-500">{dealer.group ?? "--"}</td>
                <td className="px-4 py-2 text-zinc-400">{dealer.contact_email}</td>
              </tr>
            ))}
            {dealers && dealers.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                  No dealers registered yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {selected && (
        <DealerRecordView
          dealer={selected}
          onClose={() => setSelected(null)}
          onChanged={(updated) => {
            setSelected(updated);
            load();
          }}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared dealer picker -- both Modules and Licensing operate on one selected
// dealer at a time (per-dealer toggles / per-dealer flag resolution).
// ---------------------------------------------------------------------------

function DealerPicker({
  dealers,
  selected,
  onSelect,
}: {
  dealers: Dealer[] | null;
  selected: string;
  onSelect: (dealerId: string) => void;
}) {
  return (
    <select
      value={selected}
      onChange={(e) => onSelect(e.target.value)}
      className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm min-w-[220px]"
    >
      <option value="">Select a dealer…</option>
      {(dealers ?? []).map((d) => (
        <option key={d.dealer_id} value={d.dealer_id}>
          {dealerDisplayName(d.name)} ({d.dealer_id})
        </option>
      ))}
    </select>
  );
}

function EnforcementNotice({ text }: { text: string }) {
  return (
    <div className="mb-4 text-[11px] text-yellow-500 bg-yellow-950/20 border border-yellow-900 rounded-lg px-4 py-3">
      {text}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Modules -- Module Management. Per-dealer enable/disable toggle grid, no
// code required, matching Sam's own "Enable Network, Enable Website Studio,
// Disable Collections" example. Hub-side configuration record only -- see
// hub/core/dealer_modules.py's own docstring.
// ---------------------------------------------------------------------------

export function DealershipLabManagement() {
  return <section aria-label="Dealership Lab administration"><h2 className="text-xl mb-3">Dealership Lab</h2><p className="text-sm text-zinc-400 mb-6">Manage access to dealership simulations and the learning program. Each dealer uses the shared Chrono engine; no peer-network dataset is required.</p><ModulesPanel labOnly /></section>;
}

function ModulesPanel({labOnly=false}:{labOnly?:boolean} = {}) {
  const [labPolicy,setLabPolicy]=useState<LabPolicyStatus|null>(null);
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [catalog, setCatalog] = useState<ModuleCatalogEntry[] | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [config, setConfig] = useState<DealerModuleConfig | null>(null);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    listDealers()
      .then(setDealers)
      .catch((e) => setError(errorMessage(e)));
    getModuleCatalog()
      .then((r) => setCatalog(r.modules))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    if (!dealerId) {
      setConfig(null);
      return;
    }
    setLabPolicy(null);
    getDealerModules(dealerId)
      .then(setConfig)
      .catch((e) => setError(errorMessage(e)));
  }, [dealerId]);

  async function toggle(moduleKey: string, enabled: boolean) {
    if (!dealerId) return;
    setSaving(moduleKey);
    setError("");
    try {
      setConfig(await setDealerModule(dealerId, moduleKey, enabled));
      if(moduleKey==="network")setLabPolicy(null);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  const coreModules = catalog?.filter((m) => m.category === "core" && (!labOnly || m.key === "network")) ?? [];
  const addOnModules = catalog?.filter((m) => m.category === "add_on") ?? [];

  function findEffective(key: string) {
    return config?.modules.find((m) => m.key === key);
  }

  function ModuleRow({ entry }: { entry: ModuleCatalogEntry }) {
    const effective = findEffective(entry.key);
    const enabled = effective?.enabled ?? entry.default_enabled;
    return (
      <div className="flex items-center justify-between bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3">
        <div className="min-w-0">
          <div className="text-sm font-medium flex items-center gap-2">
            {entry.label}
            {effective?.is_override && (
              <span className="text-[9px] uppercase tracking-wide text-yellow-500 bg-yellow-950/40 px-1.5 py-0.5 rounded">
                overridden
              </span>
            )}
          </div>
          <div className="text-[11px] text-zinc-500 mt-0.5 truncate">{entry.real_capability}</div>
        </div>
        <button
          disabled={!dealerId || saving === entry.key}
          onClick={() => toggle(entry.key, !enabled)}
          className={
            enabled
              ? "bg-green-700 text-white px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50 shrink-0 ml-3"
              : "bg-zinc-800 text-zinc-400 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50 shrink-0 ml-3"
          }
        >
          {saving === entry.key ? "Saving…" : enabled ? "Enabled" : "Disabled"}
        </button>
      </div>
    );
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice
        text="Toggles record desired configuration. Dealership Lab has an explicit live policy check and sync below; other modules remain configuration records. Lab sync requires a verified HTTPS tenant address, secure network key and matching tenant identity. No dealer report values are sent to the Hub."
      />

      <div className="flex items-center gap-3 mb-6">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">{labOnly ? "Dealer access" : "Module Management"}</h3>
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
      </div>

      {!dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
          Select a dealer above to view and edit their module configuration.
        </div>
      )}

      {dealerId && (
        <>
          <div className="border border-sky-900 bg-slate-950 p-4 mb-4"><h4>Dealership Lab · live enforcement</h4><p className="text-sm text-slate-400">Save the desired Lab toggle, then check the tenant and apply it explicitly. Disabling blocks staff Lab APIs; saved plans and reports remain intact. Existing Network data is not migrated.</p><button disabled={!!saving} onClick={async()=>{setSaving('lab-policy');setError('');try{setLabPolicy(await getLabPolicyStatus(dealerId));}catch(e){setError(errorMessage(e));setLabPolicy(null);}finally{setSaving('');}}}>Check live Lab policy</button>{labPolicy&&labPolicy.dealer_id===dealerId&&<><p>Tenant is {labPolicy.live.enabled?'enabled':'disabled'} · revision {labPolicy.live.revision}. {labPolicy.synchronized?'Matches Hub configuration.':'Differs from desired Hub configuration.'}</p><button disabled={!!saving||labPolicy.synchronized} onClick={async()=>{setSaving('lab-policy');setError('');try{setLabPolicy(await synchronizeLabPolicy(dealerId,labPolicy.live.revision));}catch(e){setError(errorMessage(e));setLabPolicy(null);}finally{setSaving('');}}}>Apply desired Lab policy</button></>}</div>
          <h4 className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
            {labOnly ? "Desired Lab access" : `Core Modules (${coreModules.length})`}
          </h4>
          <div className="grid grid-cols-2 gap-2 mb-6">
            {coreModules.map((m) => (
              <ModuleRow key={m.key} entry={m} />
            ))}
          </div>

          {!labOnly && <><h4 className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
            Optional Add-Ons ({addOnModules.length})
          </h4>
          <div className="grid grid-cols-2 gap-2 mb-4">
            {addOnModules.map((m) => (
              <ModuleRow key={m.key} entry={m} />
            ))}
          </div>

          </>}
          {config?.updated_at && (
            <p className="text-[11px] text-zinc-600">
              Last updated {new Date(config.updated_at).toLocaleString()} by {config.updated_by}
            </p>
          )}
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Licensing -- Feature Flags. Global / Group / Dealer scoped overrides + a
// real resolution preview, matching Sam's "AI Sales Advisor, Enable For:
// Beta Dealers" framing. Hub-side configuration record only -- see
// hub/core/feature_flags.py's own docstring, and note "Store" scope is
// deliberately collapsed into "Dealer" scope (explained in that same
// docstring) since this codebase has no separate Store/Location entity yet.
// ---------------------------------------------------------------------------

const SCOPE_LABEL: Record<FeatureFlagScope, string> = {
  global: "Global",
  group: "Group",
  dealer: "Dealer",
};

function LicensingPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [knownFlagKeys, setKnownFlagKeys] = useState<string[]>([]);
  const [overrides, setOverrides] = useState<FeatureFlagOverride[] | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);

  // Create form
  const [flagKey, setFlagKey] = useState("");
  const [scope, setScope] = useState<FeatureFlagScope>("global");
  const [scopeTarget, setScopeTarget] = useState("");
  const [enabled, setEnabled] = useState(true);
  const [note, setNote] = useState("");

  // Resolution preview
  const [previewFlagKey, setPreviewFlagKey] = useState("");
  const [previewDealerId, setPreviewDealerId] = useState("");
  const [resolution, setResolution] = useState<FeatureFlagResolution | null>(null);
  const [resolving, setResolving] = useState(false);

  async function loadOverrides() {
    try {
      const [ov, scopes] = await Promise.all([
        listFeatureFlagOverrides(),
        getFeatureFlagScopes(),
      ]);
      setOverrides(ov.overrides);
      setKnownFlagKeys(scopes.known_flag_keys);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    listDealers()
      .then(setDealers)
      .catch((e) => setError(errorMessage(e)));
    loadOverrides();
  }, []);

  async function submitOverride() {
    setSaving(true);
    setError("");
    try {
      await createFeatureFlagOverride({
        flag_key: flagKey.trim(),
        scope,
        enabled,
        scope_target: scope === "global" ? undefined : scopeTarget.trim(),
        note: note.trim() || undefined,
      });
      setNote("");
      await loadOverrides();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  async function removeOverride(overrideId: string) {
    setError("");
    try {
      await deleteFeatureFlagOverride(overrideId);
      await loadOverrides();
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  async function runResolve() {
    if (!previewFlagKey || !previewDealerId) return;
    setResolving(true);
    setError("");
    try {
      setResolution(await resolveFeatureFlag(previewFlagKey, previewDealerId));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setResolving(false);
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice
        text="Hub-side configuration record only. Resolving a flag here does not currently push anything into a running dealer backend -- no tenant process reads this yet. This is a real answer to 'would this flag be on for this dealer,' not a live switch."
      />

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        Resolution Preview
      </h3>
      <div className="bg-zinc-900 rounded-lg p-4 mb-6">
        <div className="flex flex-wrap items-end gap-3 mb-3">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Flag Key</div>
            <input
              value={previewFlagKey}
              onChange={(e) => setPreviewFlagKey(e.target.value)}
              placeholder="e.g. ai_sales_advisor"
              list="known-flag-keys"
              className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm w-56"
            />
            <datalist id="known-flag-keys">
              {knownFlagKeys.map((k) => (
                <option key={k} value={k} />
              ))}
            </datalist>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Dealer</div>
            <DealerPicker dealers={dealers} selected={previewDealerId} onSelect={setPreviewDealerId} />
          </div>
          <button
            onClick={runResolve}
            disabled={!previewFlagKey || !previewDealerId || resolving}
            className="bg-zinc-200 text-black font-medium px-4 py-2 rounded text-xs uppercase tracking-wide disabled:opacity-50"
          >
            {resolving ? "Resolving…" : "Resolve"}
          </button>
        </div>

        {resolution && (
          <div className="border-t border-zinc-800 pt-3 mt-1">
            <div className="text-sm mb-2">
              <span className="text-zinc-400">{resolution.flag_key}</span> for{" "}
              <span className="text-zinc-400">{dealerDisplayName(resolution.dealer_name)}</span> resolves to{" "}
              <span className={resolution.resolved_enabled ? "text-green-400 font-semibold" : "text-zinc-500 font-semibold"}>
                {resolution.resolved_enabled ? "ENABLED" : "DISABLED"}
              </span>{" "}
              <span className="text-zinc-600">(source: {resolution.source})</span>
            </div>
            <div className="space-y-1">
              {resolution.evaluation_trail.map((t, i) => (
                <div key={i} className="text-[11px] text-zinc-500 flex items-center gap-2">
                  <span className={t.matched ? "text-green-500" : "text-zinc-700"}>
                    {t.matched ? "✓" : "—"}
                  </span>
                  <span className="uppercase tracking-wide">{SCOPE_LABEL[t.scope]}</span>
                  {t.scope_target && <span className="text-zinc-600">({t.scope_target})</span>}
                  {t.skipped_reason && <span className="italic">{t.skipped_reason}</span>}
                  {t.override && (
                    <span>
                      → {t.override.enabled ? "enabled" : "disabled"}
                    </span>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        New Override
      </h3>
      <div className="bg-zinc-900 rounded-lg p-4 mb-6">
        <div className="grid grid-cols-4 gap-3 mb-3">
          <div>
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Flag Key</div>
            <input
              value={flagKey}
              onChange={(e) => setFlagKey(e.target.value)}
              placeholder="e.g. website_studio_2"
              className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
            />
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Scope</div>
            <select
              value={scope}
              onChange={(e) => setScope(e.target.value as FeatureFlagScope)}
              className="w-full h-9 px-2 rounded bg-zinc-950 border border-zinc-800 text-sm"
            >
              <option value="global">Global</option>
              <option value="group">Group</option>
              <option value="dealer">Dealer</option>
            </select>
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
              {scope === "dealer" ? "Dealer" : scope === "group" ? "Group Name" : "Target"}
            </div>
            {scope === "dealer" ? (
              <DealerPicker dealers={dealers} selected={scopeTarget} onSelect={setScopeTarget} />
            ) : scope === "group" ? (
              <input
                value={scopeTarget}
                onChange={(e) => setScopeTarget(e.target.value)}
                placeholder="e.g. NXTDeal Auto Group"
                className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
              />
            ) : (
              <input disabled placeholder="n/a for global" className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm opacity-40" />
            )}
          </div>
          <div>
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Enabled</div>
            <select
              value={enabled ? "true" : "false"}
              onChange={(e) => setEnabled(e.target.value === "true")}
              className="w-full h-9 px-2 rounded bg-zinc-950 border border-zinc-800 text-sm"
            >
              <option value="true">Enabled</option>
              <option value="false">Disabled</option>
            </select>
          </div>
        </div>
        <div className="flex gap-3 items-end">
          <div className="flex-1">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Note (optional)</div>
            <input
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="e.g. Beta Dealers rollout"
              className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
            />
          </div>
          <button
            onClick={submitOverride}
            disabled={!flagKey.trim() || (scope !== "global" && !scopeTarget.trim()) || saving}
            className="bg-zinc-200 text-black font-medium px-4 py-2 rounded text-xs uppercase tracking-wide disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save Override"}
          </button>
        </div>
      </div>

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        All Overrides ({overrides?.length ?? 0})
      </h3>
      <div className="bg-zinc-900 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Flag</th>
              <th className="text-left px-4 py-2">Scope</th>
              <th className="text-left px-4 py-2">Target</th>
              <th className="text-left px-4 py-2">Enabled</th>
              <th className="text-left px-4 py-2">Note</th>
              <th className="text-left px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {(overrides ?? []).map((o) => (
              <tr key={o.override_id} className="border-t border-zinc-800">
                <td className="px-4 py-2">{o.flag_key}</td>
                <td className="px-4 py-2 text-zinc-400">{SCOPE_LABEL[o.scope]}</td>
                <td className="px-4 py-2 text-zinc-500">{o.scope_target ?? "--"}</td>
                <td className={`px-4 py-2 ${o.enabled ? "text-green-400" : "text-zinc-500"}`}>
                  {o.enabled ? "Enabled" : "Disabled"}
                </td>
                <td className="px-4 py-2 text-zinc-500">{o.note ?? "--"}</td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => removeOverride(o.override_id)}
                    className="text-red-400 hover:text-red-300 text-xs"
                  >
                    Delete
                  </button>
                </td>
              </tr>
            ))}
            {overrides && overrides.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                  No feature flag overrides yet -- every flag resolves to its default (disabled).
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Provisioning -- Onboarding Center. A real per-dealer Setup Wizard checklist
// (Dealer Created / Users Invited / Inventory Imported / CRM Imported /
// Website Connected / Network Connected / Go Live). "Dealer Created" and
// "Network Connected" are real, checked signals (see hub/core/
// dealer_onboarding.py's module docstring) -- every other step is honest
// manual data entry a NXTDeal staffer records, a real feature on its own,
// not a placeholder.
// ---------------------------------------------------------------------------

const STEP_BASIS_BADGE: Record<string, string> = {
  auto: "text-green-400 bg-green-950/40",
  manual: "text-zinc-400 bg-zinc-800",
  not_started: "text-zinc-600 bg-zinc-900",
};

function ProvisioningPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [catalog, setCatalog] = useState<OnboardingStepCatalogEntry[] | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [status, setStatus] = useState<DealerOnboardingStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [noteDraft, setNoteDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    listDealers()
      .then(setDealers)
      .catch((e) => setError(errorMessage(e)));
    getOnboardingCatalog()
      .then((r) => setCatalog(r.steps))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function loadStatus(id: string) {
    if (!id) {
      setStatus(null);
      return;
    }
    try {
      setStatus(await getDealerOnboarding(id));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadStatus(dealerId);
  }, [dealerId]);

  async function runRecheck() {
    if (!dealerId) return;
    setBusy("recheck");
    setError("");
    try {
      setStatus(await recheckDealerOnboarding(dealerId));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  async function toggleStep(stepKey: string, complete: boolean) {
    if (!dealerId) return;
    setBusy(stepKey);
    setError("");
    try {
      setStatus(
        await setDealerOnboardingStep(dealerId, stepKey, complete, noteDraft[stepKey])
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice
        text="Setup Wizard tracking. 'Dealer Created' and 'Network Connected' (badged AUTO below) are real, checked signals -- Network Connected via a live call to this dealer's own /network/anonymous-snapshot endpoint, refreshed only when you click Recheck. Every other step is honest manual data entry by NXTDeal staff -- no unauthenticated tenant-side signal exists to compute Users Invited/Inventory Imported/CRM Imported/Website Connected/Go Live automatically."
      />

      <div className="flex items-center gap-3 mb-6">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">Onboarding Center</h3>
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
        <button
          disabled={!dealerId || busy === "recheck"}
          onClick={runRecheck}
          className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
        >
          {busy === "recheck" ? "Checking…" : "↻ Recheck"}
        </button>
      </div>

      {!dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
          Select a dealer above to view and work their Setup Wizard checklist.
        </div>
      )}

      {dealerId && status && (
        <>
          <div className="bg-zinc-900 rounded-lg p-4 mb-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-sm font-medium">{status.dealer_name}</div>
              <div className="text-sm text-zinc-400">
                {status.complete_count} / {status.total_steps} complete ({status.progress_pct}%)
              </div>
            </div>
            <div className="h-2 bg-zinc-800 rounded overflow-hidden">
              <div
                className="h-full bg-green-700"
                style={{ width: `${status.progress_pct}%` }}
              />
            </div>
          </div>

          <div className="space-y-2 mb-4">
            {status.steps.map((step) => (
              <div
                key={step.key}
                className="bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span
                      className={
                        step.complete
                          ? "w-5 h-5 rounded-full bg-green-700 flex items-center justify-center text-[10px] shrink-0"
                          : "w-5 h-5 rounded-full border border-zinc-700 shrink-0"
                      }
                    >
                      {step.complete ? "✓" : ""}
                    </span>
                    <span className="text-sm font-medium">{step.label}</span>
                    <span
                      className={`text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 ${
                        STEP_BASIS_BADGE[step.catalog_basis] ?? STEP_BASIS_BADGE.manual
                      }`}
                    >
                      {step.catalog_basis === "auto" ? "auto-checked" : "manual"}
                    </span>
                  </div>

                  {step.catalog_basis === "manual" && (
                    <div className="flex items-center gap-2 shrink-0">
                      {!step.complete && (
                        <input
                          value={noteDraft[step.key] ?? ""}
                          onChange={(e) =>
                            setNoteDraft((prev) => ({ ...prev, [step.key]: e.target.value }))
                          }
                          placeholder="note (optional)"
                          className="h-7 px-2 rounded bg-zinc-900 border border-zinc-800 text-xs w-40"
                        />
                      )}
                      <button
                        disabled={busy === step.key}
                        onClick={() => toggleStep(step.key, !step.complete)}
                        className={
                          step.complete
                            ? "bg-zinc-800 text-zinc-300 px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50"
                            : "bg-green-800 text-white px-3 py-1.5 rounded text-xs font-medium disabled:opacity-50"
                        }
                      >
                        {busy === step.key
                          ? "Saving…"
                          : step.complete
                          ? "Mark Incomplete"
                          : "Mark Complete"}
                      </button>
                    </div>
                  )}
                </div>

                {(step.note || step.completed_at) && (
                  <div className="text-[11px] text-zinc-500 mt-2 pl-7">
                    {step.note && <span>{step.note}</span>}
                    {step.completed_at && (
                      <span className="text-zinc-600">
                        {step.note ? " — " : ""}
                        {new Date(step.completed_at).toLocaleString()}
                        {step.completed_by ? ` by ${step.completed_by}` : ""}
                      </span>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>

          <p className="text-[11px] text-zinc-500 leading-relaxed">{status.note}</p>
        </>
      )}

      {catalog && !dealerId && (
        <p className="text-[11px] text-zinc-600 mt-4">
          {catalog.length}-step Setup Wizard sequence: {catalog.map((s) => s.label).join(" → ")}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Migration -- Migration Tracking. Source-system picklist + real manual
// migration-readiness data entry per category (Customer Records / Inventory
// / Service), plus a real, rule-based Go-Live Tracker (Blocked / At Risk /
// Ready) computed off those recorded percentages -- see hub/core/
// dealer_migration.py's module docstring for the exact thresholds.
// ---------------------------------------------------------------------------

const GO_LIVE_COLOR: Record<GoLiveStatus, string> = {
  not_started: "text-zinc-500 bg-zinc-800",
  blocked: "text-red-400 bg-red-950/40",
  at_risk: "text-yellow-400 bg-yellow-950/40",
  ready: "text-green-400 bg-green-950/40",
};

const GO_LIVE_LABEL: Record<GoLiveStatus, string> = {
  not_started: "Not Started",
  blocked: "Blocked",
  at_risk: "At Risk",
  ready: "Ready",
};

function MigrationPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [catalog, setCatalog] = useState<MigrationCatalog | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [status, setStatus] = useState<DealerMigrationStatus | null>(null);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState("");

  const [sourceDraft, setSourceDraft] = useState("");
  const [otherNoteDraft, setOtherNoteDraft] = useState("");
  const [readinessDraft, setReadinessDraft] = useState<Record<string, string>>({});

  useEffect(() => {
    listDealers()
      .then(setDealers)
      .catch((e) => setError(errorMessage(e)));
    getMigrationCatalog()
      .then(setCatalog)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function loadStatus(id: string) {
    if (!id) {
      setStatus(null);
      return;
    }
    try {
      const result = await getDealerMigration(id);
      setStatus(result);
      setSourceDraft(result.migrating_from ?? "");
      setOtherNoteDraft(result.migrating_from_other_note ?? "");
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadStatus(dealerId);
  }, [dealerId]);

  async function saveSource() {
    if (!dealerId) return;
    setSaving("source");
    setError("");
    try {
      setStatus(
        await setDealerMigrationSource(dealerId, sourceDraft || null, otherNoteDraft)
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  async function saveReadiness(category: string) {
    if (!dealerId) return;
    const raw = readinessDraft[category];
    const pct = Number(raw);
    if (raw === undefined || raw === "" || Number.isNaN(pct)) return;
    setSaving(category);
    setError("");
    try {
      setStatus(await setDealerReadiness(dealerId, category, pct));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice
        text="migrating_from and every readiness percentage below are honest manual data entry -- no CDK/Reynolds/Tekion/DealerSocket/VinSolutions/HubSpot connector or automatic record-count comparison exists anywhere in this codebase. The Go-Live Tracker status IS a real, rule-based computation over those recorded numbers, not a guess -- see the thresholds noted below each category."
      />

      <div className="flex items-center gap-3 mb-6">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">Migration Tracking</h3>
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
      </div>

      {!dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
          Select a dealer above to record migration source + readiness.
        </div>
      )}

      {dealerId && status && (
        <>
          <div className="bg-zinc-900 rounded-lg p-4 mb-4 flex items-center justify-between">
            <div>
              <div className="text-sm font-medium mb-1">{status.dealer_name}</div>
              <div className="text-[11px] text-zinc-500">{status.go_live_reason}</div>
            </div>
            <span
              className={`text-xs uppercase tracking-wide font-semibold px-3 py-1.5 rounded ${GO_LIVE_COLOR[status.go_live_status]}`}
            >
              {GO_LIVE_LABEL[status.go_live_status]}
            </span>
          </div>

          <h4 className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
            Migrating From
          </h4>
          <div className="bg-zinc-900 rounded-lg p-4 mb-6 flex items-end gap-3 flex-wrap">
            <div>
              <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">Source</div>
              <select
                value={sourceDraft}
                onChange={(e) => setSourceDraft(e.target.value)}
                className="h-9 px-2 rounded bg-zinc-950 border border-zinc-800 text-sm min-w-[200px]"
              >
                <option value="">Not set</option>
                {(catalog?.sources ?? []).map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.label}
                  </option>
                ))}
              </select>
            </div>
            {sourceDraft === "other" && (
              <div>
                <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
                  Other -- Describe
                </div>
                <input
                  value={otherNoteDraft}
                  onChange={(e) => setOtherNoteDraft(e.target.value)}
                  placeholder="e.g. custom legacy Access DB"
                  className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm w-64"
                />
              </div>
            )}
            <button
              disabled={saving === "source"}
              onClick={saveSource}
              className="bg-zinc-200 text-black font-medium px-4 py-2 rounded text-xs uppercase tracking-wide disabled:opacity-50"
            >
              {saving === "source" ? "Saving…" : "Save"}
            </button>
          </div>

          <h4 className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
            Migration Readiness
          </h4>
          <div className="space-y-2 mb-4">
            {status.readiness.map((r) => (
              <div
                key={r.key}
                className="bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 flex items-center justify-between gap-3"
              >
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium">{r.label}</div>
                  <div className="text-[11px] text-zinc-500">
                    {r.pct !== null ? `${r.pct}% recorded` : "not recorded yet"}
                    {r.note ? ` — ${r.note}` : ""}
                  </div>
                </div>
                <input
                  type="number"
                  min={0}
                  max={100}
                  step={0.1}
                  value={readinessDraft[r.key] ?? (r.pct !== null ? String(r.pct) : "")}
                  onChange={(e) =>
                    setReadinessDraft((prev) => ({ ...prev, [r.key]: e.target.value }))
                  }
                  placeholder="%"
                  className="h-9 w-20 px-2 rounded bg-zinc-900 border border-zinc-800 text-sm text-right"
                />
                <button
                  disabled={saving === r.key}
                  onClick={() => saveReadiness(r.key)}
                  className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50 shrink-0"
                >
                  {saving === r.key ? "Saving…" : "Save"}
                </button>
              </div>
            ))}
          </div>

          {catalog && (
            <p className="text-[11px] text-zinc-600 mb-2">
              Go-Live thresholds: Ready requires every category ≥ {catalog.go_live_thresholds.ready_pct}%.
              Blocked if any recorded category is below {catalog.go_live_thresholds.blocked_pct}%.
            </p>
          )}
          <p className="text-[11px] text-zinc-500 leading-relaxed">{status.note}</p>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Integrations -- Integrations Center. Real per-dealer connection records
// (provider, connection health, data flow, sync frequency) -- Hub-side
// manual data entry by NXTDeal staff, not a live tenant read. See hub/core/
// dealer_integrations.py's own docstring for why this landed on the manual
// side of the same judgment call AI Management (below) landed on the real
// side of: no Google/Microsoft/Meta/CDK/DealerTrack/RouteOne/Xtime concept
// exists anywhere in the tenant's own Connection model, and an endpoint_url
// is a meaningfully riskier thing to expose over a new tenant route than the
// coarse call-count data AI Management reads.
// ---------------------------------------------------------------------------

const HEALTH_COLOR: Record<IntegrationHealth, string> = {
  healthy: "text-green-400 bg-green-950/40",
  warning: "text-yellow-400 bg-yellow-950/40",
  failed: "text-red-400 bg-red-950/40",
};

function IntegrationsPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [catalog, setCatalog] = useState<IntegrationsCatalog | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [status, setStatus] = useState<DealerIntegrationsStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  // Add form
  const [providerKey, setProviderKey] = useState("");
  const [customLabel, setCustomLabel] = useState("");
  const [health, setHealth] = useState<IntegrationHealth>("healthy");
  const [dataFlow, setDataFlow] = useState<IntegrationDataFlow>("bidirectional");
  const [syncFrequency, setSyncFrequency] = useState("daily");
  const [notes, setNotes] = useState("");

  useEffect(() => {
    listDealers()
      .then(setDealers)
      .catch((e) => setError(errorMessage(e)));
    getIntegrationsCatalog()
      .then(setCatalog)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function loadStatus(id: string) {
    if (!id) {
      setStatus(null);
      return;
    }
    try {
      setStatus(await getDealerIntegrations(id));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadStatus(dealerId);
  }, [dealerId]);

  async function submitAdd() {
    if (!dealerId || !providerKey) return;
    setBusy("add");
    setError("");
    try {
      setStatus(
        await addDealerIntegration(dealerId, {
          provider_key: providerKey,
          connection_health: health,
          data_flow: dataFlow,
          sync_frequency: syncFrequency,
          notes: notes || undefined,
          custom_label: providerKey === "other" ? customLabel || undefined : undefined,
        })
      );
      setProviderKey("");
      setCustomLabel("");
      setNotes("");
      setHealth("healthy");
      setDataFlow("bidirectional");
      setSyncFrequency("daily");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  async function patchHealth(integrationId: string, newHealth: IntegrationHealth) {
    if (!dealerId) return;
    setBusy(integrationId);
    setError("");
    try {
      setStatus(
        await updateDealerIntegration(dealerId, integrationId, { connection_health: newHealth })
      );
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  async function toggleActive(integrationId: string, active: boolean) {
    if (!dealerId) return;
    setBusy(integrationId);
    setError("");
    try {
      setStatus(await updateDealerIntegration(dealerId, integrationId, { active }));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  async function remove(integrationId: string) {
    if (!dealerId) return;
    setBusy(integrationId);
    setError("");
    try {
      setStatus(await removeDealerIntegration(dealerId, integrationId));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice
        text="Honest manual data entry by NXTDeal staff -- there is no real tenant-side integration provider catalog (Google/Microsoft/Meta/CDK/DealerTrack/RouteOne/Xtime) anywhere in this codebase's Connection model. This is a real, useful Hub-side record of what's actually connected for this dealer, not a live read of the tenant's own state."
      />

      <div className="flex items-center gap-3 mb-6">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">Integrations Center</h3>
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
      </div>

      {!dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
          Select a dealer above to view and record their active integrations.
        </div>
      )}

      {dealerId && status && (
        <>
          <div className="grid grid-cols-4 gap-2 mb-4">
            <KpiCard label="Active Integrations" value={status.active_count} />
            <KpiCard label="Healthy" value={status.by_health.healthy} />
            <KpiCard label="Warning" value={status.by_health.warning} />
            <KpiCard label="Failed" value={status.by_health.failed} />
          </div>

          <div className="space-y-2 mb-6">
            {status.integrations.length === 0 && (
              <div className="bg-zinc-900 rounded-lg p-6 text-center text-sm text-zinc-500">
                No integrations recorded for this dealer yet.
              </div>
            )}
            {status.integrations.map((i) => (
              <div
                key={i.integration_id}
                className="bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className="text-sm font-medium">{i.label}</span>
                    <span
                      className={`text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 ${HEALTH_COLOR[i.connection_health]}`}
                    >
                      {i.connection_health}
                    </span>
                    {!i.active && (
                      <span className="text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded shrink-0 text-zinc-500 bg-zinc-800">
                        inactive
                      </span>
                    )}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <select
                      value={i.connection_health}
                      disabled={busy === i.integration_id}
                      onChange={(e) => patchHealth(i.integration_id, e.target.value as IntegrationHealth)}
                      className="h-7 px-2 rounded bg-zinc-900 border border-zinc-800 text-xs"
                    >
                      {(catalog?.health_statuses ?? []).map((h) => (
                        <option key={h} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                    <button
                      disabled={busy === i.integration_id}
                      onClick={() => toggleActive(i.integration_id, !i.active)}
                      className="bg-zinc-800 text-zinc-300 px-2 py-1.5 rounded text-xs font-medium disabled:opacity-50"
                    >
                      {i.active ? "Deactivate" : "Activate"}
                    </button>
                    <button
                      disabled={busy === i.integration_id}
                      onClick={() => remove(i.integration_id)}
                      className="bg-red-950/40 text-red-400 px-2 py-1.5 rounded text-xs font-medium disabled:opacity-50"
                    >
                      Remove
                    </button>
                  </div>
                </div>
                <div className="text-[11px] text-zinc-500 mt-2">
                  Data Flow: {i.data_flow} · Sync: {i.sync_frequency}
                  {i.notes ? ` · ${i.notes}` : ""}
                </div>
              </div>
            ))}
          </div>

          <div className="bg-zinc-900 rounded-lg p-4">
            <h4 className="text-[11px] uppercase tracking-wide text-zinc-500 mb-3">
              Add Integration
            </h4>
            <div className="flex flex-wrap items-center gap-2">
              <select
                value={providerKey}
                onChange={(e) => setProviderKey(e.target.value)}
                className="h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-xs"
              >
                <option value="">Provider…</option>
                {(catalog?.providers ?? []).map((p) => (
                  <option key={p.key} value={p.key}>
                    {p.label}
                  </option>
                ))}
              </select>
              {providerKey === "other" && (
                <input
                  value={customLabel}
                  onChange={(e) => setCustomLabel(e.target.value)}
                  placeholder="Custom label"
                  className="h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-xs w-32"
                />
              )}
              <select
                value={health}
                onChange={(e) => setHealth(e.target.value as IntegrationHealth)}
                className="h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-xs"
              >
                {(catalog?.health_statuses ?? []).map((h) => (
                  <option key={h} value={h}>
                    {h}
                  </option>
                ))}
              </select>
              <select
                value={dataFlow}
                onChange={(e) => setDataFlow(e.target.value as IntegrationDataFlow)}
                className="h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-xs"
              >
                {(catalog?.data_flows ?? []).map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
              <select
                value={syncFrequency}
                onChange={(e) => setSyncFrequency(e.target.value)}
                className="h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-xs"
              >
                {(catalog?.sync_frequency_presets ?? []).map((f) => (
                  <option key={f} value={f}>
                    {f}
                  </option>
                ))}
              </select>
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="notes (optional)"
                className="h-8 px-2 rounded bg-zinc-950 border border-zinc-800 text-xs flex-1 min-w-[140px]"
              />
              <button
                disabled={!providerKey || busy === "add"}
                onClick={submitAdd}
                className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
              >
                {busy === "add" ? "Adding…" : "+ Add"}
              </button>
            </div>
          </div>

          <p className="text-[11px] text-zinc-500 leading-relaxed mt-4">{status.note}</p>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// AI Management -- per dealer. REAL, via an on-demand live HTTP round trip to
// a new, narrowly-scoped tenant-side route (GET /network/ai-management-
// snapshot), gated by the SAME DEALEROS_NETWORK_KEY shared secret the
// anonymized peer-benchmark pull already uses -- see hub/core/
// dealer_ai_management.py's own docstring for the full safety reasoning
// behind adding that one new tenant route (a static feature-name catalog +
// plain call-attempt counters, no PII, no endpoint URLs, no freeform text).
// Sam's 5 named areas (Sales/Service/Finance/Marketing/Collections AI) are
// this Hub's own best-judgment mapping of the tenant's real 13-feature
// catalog -- most real AI capability lives in Marketing today, and Service/
// Finance/Collections AI honestly report a real zero-feature gap rather than
// a fabricated capability (see that module's docstring for the full mapping
// reasoning, including why Collections' own risk-scoring engine is
// deliberately NOT counted here -- it's a transparent rules engine, not an
// AI/LLM call).
// ---------------------------------------------------------------------------

function AiManagementPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [catalog, setCatalog] = useState<AiAreaCatalogEntry[] | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [status, setStatus] = useState<DealerAiManagementStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  useEffect(() => {
    listDealers()
      .then(setDealers)
      .catch((e) => setError(errorMessage(e)));
    getAiAreaCatalog()
      .then((r) => setCatalog(r.areas))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function loadStatus(id: string) {
    if (!id) {
      setStatus(null);
      return;
    }
    try {
      setStatus(await getDealerAiManagement(id));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadStatus(dealerId);
  }, [dealerId]);

  async function runRecheck() {
    if (!dealerId) return;
    setBusy("recheck");
    setError("");
    try {
      setStatus(await recheckDealerAiManagement(dealerId));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  const totalAttempted = status?.areas.reduce((sum, a) => sum + a.total_attempted, 0) ?? 0;
  const totalEnabled = status?.areas.reduce((sum, a) => sum + a.enabled_count, 0) ?? 0;
  const totalMapped = status?.areas.reduce((sum, a) => sum + a.mapped_feature_count, 0) ?? 0;

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice
        text="Real, on-demand live data (not stored/simulated) once you click Recheck -- a live HTTP call to this dealer's own tenant backend, gated by a shared server-to-server key. The last fetched snapshot is what's shown below; it does not auto-refresh on every visit."
      />

      <div className="flex items-center gap-3 mb-6">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">AI Management</h3>
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
        <button
          disabled={!dealerId || busy === "recheck"}
          onClick={runRecheck}
          className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
        >
          {busy === "recheck" ? "Checking…" : "↻ Recheck"}
        </button>
      </div>

      {!dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
          Select a dealer above to view their AI capability + consumption snapshot.
        </div>
      )}

      {dealerId && status && (
        <>
          {status.checked && (
            <div className="flex items-center gap-2 mb-4">
              <span
                className={
                  status.reachable
                    ? "text-[10px] uppercase tracking-wide px-2 py-1 rounded text-green-400 bg-green-950/40"
                    : "text-[10px] uppercase tracking-wide px-2 py-1 rounded text-red-400 bg-red-950/40"
                }
              >
                {status.reachable ? "Reachable" : "Unreachable"}
              </span>
              {status.fetched_at && (
                <span className="text-[11px] text-zinc-600">
                  last checked {new Date(status.fetched_at).toLocaleString()}
                </span>
              )}
              {status.fetch_error && (
                <span className="text-[11px] text-red-400">{status.fetch_error}</span>
              )}
            </div>
          )}

          {status.checked && status.reachable && (
            <div className="grid grid-cols-3 gap-2 mb-6">
              <KpiCard label="Mapped Features" value={`${totalMapped} / 13`} />
              <KpiCard label="Enabled" value={totalEnabled} />
              <KpiCard label="Prompts (Attempted)" value={totalAttempted} />
            </div>
          )}

          <div className="grid grid-cols-2 gap-2 mb-4">
            {status.areas.map((a) => (
              <div
                key={a.key}
                className="bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3"
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium">{a.label}</span>
                  <span className="text-[11px] text-zinc-500">
                    {a.enabled_count} / {a.mapped_feature_count} enabled
                  </span>
                </div>
                {a.gap_note ? (
                  <p className="text-[11px] text-zinc-600 leading-relaxed">{a.gap_note}</p>
                ) : (
                  <>
                    <div className="grid grid-cols-4 gap-1 text-center mb-2">
                      <div>
                        <div className="text-sm font-semibold">{a.total_attempted}</div>
                        <div className="text-[9px] uppercase text-zinc-600">Attempted</div>
                      </div>
                      <div>
                        <div className="text-sm font-semibold">{a.total_succeeded}</div>
                        <div className="text-[9px] uppercase text-zinc-600">Succeeded</div>
                      </div>
                      <div>
                        <div className="text-sm font-semibold">{a.total_fell_back}</div>
                        <div className="text-[9px] uppercase text-zinc-600">Fell Back</div>
                      </div>
                      <div>
                        <div className="text-sm font-semibold">{a.total_blocked}</div>
                        <div className="text-[9px] uppercase text-zinc-600">Blocked</div>
                      </div>
                    </div>
                    <div className="space-y-1">
                      {a.features.map((f) => (
                        <div
                          key={f.key}
                          className="flex items-center justify-between text-[11px] text-zinc-400"
                        >
                          <span className="truncate">{f.name}</span>
                          <span
                            className={
                              f.enabled
                                ? "text-green-500 shrink-0 ml-2"
                                : "text-zinc-600 shrink-0 ml-2"
                            }
                          >
                            {f.enabled ? "enabled" : "disabled"}
                          </span>
                        </div>
                      ))}
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>

          <p className="text-[11px] text-zinc-500 leading-relaxed mb-2">{status.consumption_note}</p>
          <p className="text-[11px] text-zinc-600 leading-relaxed">{status.note}</p>
        </>
      )}

      {catalog && !dealerId && (
        <p className="text-[11px] text-zinc-600 mt-4">
          {catalog.length} AI areas tracked: {catalog.map((c) => c.label).join(" · ")}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Network Membership -- Dealer Management rebuild, slice 5 of 5 (FINAL).
// Real Network Tier (manual, editable) + real, transparent Benchmark Access
// rule + an honest per-dealer Contribution gap (network snapshots are keyed
// only by an anonymous pseudonym never derived from dealer_id -- joining a
// specific snapshot back to a specific dealer would break that anonymity
// boundary by design) with two real, non-identifying signals shown instead:
// a live pipeline-connectivity recheck and a network-wide two-count
// aggregate. See hub/core/dealer_network_membership.py's own module
// docstring for the full reasoning.
// ---------------------------------------------------------------------------

const TIER_COLOR: Record<string, string> = {
  none: "text-zinc-500",
  standard: "text-sky-400",
  premium: "text-purple-400",
  enterprise: "text-yellow-400",
};

function NetworkMembershipPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [catalog, setCatalog] = useState<NetworkTierCatalogEntry[] | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [membership, setMembership] = useState<DealerNetworkMembership | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [pipelineResult, setPipelineResult] = useState("");

  useEffect(() => {
    listDealers().then(setDealers).catch((e) => setError(errorMessage(e)));
    getNetworkMembershipCatalog()
      .then((r) => setCatalog(r.tiers))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function loadMembership(id: string) {
    if (!id) {
      setMembership(null);
      return;
    }
    try {
      setMembership(await getDealerNetworkMembership(id));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadMembership(dealerId);
  }, [dealerId]);

  async function changeTier(tier: NetworkTier) {
    if (!dealerId) return;
    setBusy("tier");
    setError("");
    try {
      setMembership(await setDealerNetworkTier(dealerId, tier));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  async function runRecheckPipeline() {
    if (!dealerId) return;
    setBusy("pipeline");
    setError("");
    setPipelineResult("");
    try {
      const result = await recheckDealerPipelineConnectivity(dealerId);
      setPipelineResult(result.reachable ? `Reachable -- ${result.detail}` : `Unreachable -- ${result.detail}`);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div className="flex items-center gap-3 mb-6">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">Network Membership</h3>
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
      </div>

      {!dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
          Select a dealer above to view their Intelligence Network membership.
        </div>
      )}

      {dealerId && membership && (
        <>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Opted In</div>
              <div className={membership.network_opt_in ? "text-green-400 font-semibold" : "text-zinc-500 font-semibold"}>
                {membership.network_opt_in ? "Yes" : "No"}
              </div>
            </div>
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Network Tier</div>
              <div className={`font-semibold ${TIER_COLOR[membership.tier.tier] ?? "text-zinc-300"}`}>
                {membership.tier.tier_label}
              </div>
            </div>
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Benchmark Access</div>
              <div className={membership.benchmark_access ? "text-green-400 font-semibold" : "text-zinc-500 font-semibold"}>
                {membership.benchmark_access ? "Granted" : "Not Granted"}
              </div>
            </div>
          </div>

          <div className="bg-zinc-900 rounded-lg p-4 mb-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Set Network Tier</div>
            <div className="flex gap-2">
              {(catalog ?? []).map((t) => (
                <button
                  key={t.key}
                  disabled={busy === "tier"}
                  onClick={() => changeTier(t.key)}
                  className={
                    membership.tier.tier === t.key
                      ? "bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs disabled:opacity-50"
                      : "bg-zinc-950 border border-zinc-800 text-zinc-300 px-3 py-1.5 rounded text-xs disabled:opacity-50"
                  }
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>

          <EnforcementNotice text={membership.contribution.reason} />

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 mb-4">
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs uppercase tracking-wide text-zinc-500">Contribution -- Pipeline Connectivity Proxy</div>
              <button
                disabled={busy === "pipeline"}
                onClick={runRecheckPipeline}
                className="bg-zinc-200 text-black font-medium px-3 py-1 rounded text-[11px] uppercase tracking-wide disabled:opacity-50"
              >
                {busy === "pipeline" ? "Checking…" : "↻ Recheck Pipeline"}
              </button>
            </div>
            <p className="text-[11px] text-zinc-500 leading-relaxed mb-2">{membership.contribution.pipeline_connectivity_proxy}</p>
            {pipelineResult && <p className="text-[11px] text-zinc-300">{pipelineResult}</p>}
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Network-Wide Aggregate (never a per-dealer join)</div>
            <div className="grid grid-cols-2 gap-2">
              <KpiCard label="Opted-In Active Dealers" value={membership.contribution.network_wide_aggregate.opted_in_active_dealers} />
              <KpiCard label="Anonymized Snapshots Collected" value={membership.contribution.network_wide_aggregate.total_anonymized_snapshots_collected} />
            </div>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Support Center -- Dealer Management rebuild, slice 5 of 5 (FINAL). Real
// Health Score (50/50 blend of real Feature Adoption + real Login Activity,
// Training Completion an honest excluded gap), real Login Frequency / Usage
// Trend via a new tenant-side route, and real, transparent, points-based
// Churn Risk -- NOT an AI/ML score. See hub/core/dealer_support.py's own
// module docstring for every rule and its point value.
// ---------------------------------------------------------------------------

const CHURN_COLOR: Record<string, string> = {
  low: "text-green-400 bg-green-950/40",
  medium: "text-yellow-400 bg-yellow-950/40",
  high: "text-red-400 bg-red-950/40",
};

function SupportCenterPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [status, setStatus] = useState<DealerSupportStatus | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    listDealers().then(setDealers).catch((e) => setError(errorMessage(e)));
  }, []);

  async function loadStatus(id: string) {
    if (!id) {
      setStatus(null);
      return;
    }
    try {
      setStatus(await getDealerSupportStatus(id));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadStatus(dealerId);
  }, [dealerId]);

  async function runRecheck() {
    if (!dealerId) return;
    setBusy(true);
    setError("");
    try {
      setStatus(await recheckDealerSupportSnapshot(dealerId));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice text="Login Frequency / Usage Trend are real, on-demand data (click Recheck) -- a live HTTP call to this dealer's own tenant backend returning only coarse, aggregate, non-PII login/lockout counts. Training Completion has no backing data model anywhere in this codebase -- an honest, excluded gap, not a fabricated percentage." />

      <div className="flex items-center gap-3 mb-6">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">Support Center</h3>
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
        <button
          disabled={!dealerId || busy}
          onClick={runRecheck}
          className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
        >
          {busy ? "Checking…" : "↻ Recheck Login Activity"}
        </button>
      </div>

      {!dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
          Select a dealer above to view their Health Score and Churn Risk.
        </div>
      )}

      {dealerId && status && (
        <>
          <div className="grid grid-cols-3 gap-2 mb-4">
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-2xl font-semibold">
                {status.health_score.score === null ? "—" : `${status.health_score.score}%`}
              </div>
              <div className="text-[11px] uppercase tracking-wide text-zinc-500 mt-1">Health Score</div>
            </div>
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-2xl font-semibold">
                {status.health_score.components.feature_adoption_pct === null ? "—" : `${status.health_score.components.feature_adoption_pct}%`}
              </div>
              <div className="text-[11px] uppercase tracking-wide text-zinc-500 mt-1">Feature Adoption</div>
            </div>
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className={`text-[11px] uppercase tracking-wide px-2 py-1 rounded inline-block ${CHURN_COLOR[status.churn_risk.level]}`}>
                {status.churn_risk.level} churn risk
              </div>
              <div className="text-[11px] text-zinc-500 mt-2">{status.churn_risk.points} point(s)</div>
            </div>
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4 mb-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Operational Snapshot (Login Frequency / Usage Trend)</div>
            {!status.operational_snapshot.reachable && (
              <p className="text-[11px] text-zinc-500">
                {status.operational_snapshot.fetched_at
                  ? `Last checked ${new Date(status.operational_snapshot.fetched_at).toLocaleString()} -- ${status.operational_snapshot.error}`
                  : "Never checked yet -- click Recheck Login Activity above."}
              </p>
            )}
            {status.operational_snapshot.reachable && status.operational_snapshot.data.current_window && (
              <div className="grid grid-cols-4 gap-2">
                <KpiCard label="Logins (30d)" value={status.operational_snapshot.data.current_window.login_success_count} />
                <KpiCard label="Failed Logins (30d)" value={status.operational_snapshot.data.current_window.login_failed_count} />
                <KpiCard label="Distinct Employees" value={status.operational_snapshot.data.current_window.distinct_employees_logged_in} />
                <KpiCard label="Trend" value={status.operational_snapshot.data.trend ?? "—"} />
              </div>
            )}
          </div>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500 mb-2">Churn Risk -- Real Rules Engine (not AI)</div>
            <p className="text-[11px] text-zinc-500 leading-relaxed mb-3">{status.churn_risk.disclosure}</p>
            <div className="space-y-1">
              {status.churn_risk.reasons.map((r, i) => (
                <div key={i} className="flex items-center justify-between text-[11px] text-zinc-400">
                  <span>{r.reason} <span className="text-zinc-600">({r.detail})</span></span>
                  <span className={r.points > 0 ? "text-orange-400" : "text-zinc-600"}>+{r.points}</span>
                </div>
              ))}
            </div>
            <p className="text-[11px] text-zinc-600 mt-3">{status.health_score.training_completion_gap}</p>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Audit Center -- Dealer Management rebuild, slice 5 of 5 (FINAL). Real,
// append-only Hub-side audit log of every mutating Dealer Management action
// across all 5 slices. See hub/core/hub_audit.py's own module docstring for
// the full category-mapping reasoning.
// ---------------------------------------------------------------------------

function AuditCenterPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [categories, setCategories] = useState<AuditCategoryEntry[] | null>(null);
  const [dealerFilter, setDealerFilter] = useState("");
  const [categoryFilter, setCategoryFilter] = useState("");
  const [events, setEvents] = useState<HubAuditEvent[] | null>(null);
  const [byCategory, setByCategory] = useState<Record<string, number>>({});
  const [totalEvents, setTotalEvents] = useState(0);
  const [error, setError] = useState("");

  useEffect(() => {
    listDealers().then(setDealers).catch((e) => setError(errorMessage(e)));
    getAuditCatalog()
      .then((r) => setCategories(r.categories))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  useEffect(() => {
    listAuditEvents({
      dealer_id: dealerFilter || undefined,
      category: categoryFilter || undefined,
    })
      .then((r) => {
        setEvents(r.events);
        setByCategory(r.by_category);
        setTotalEvents(r.total_events);
      })
      .catch((e) => setError(errorMessage(e)));
  }, [dealerFilter, categoryFilter]);

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-4">Audit Center</h3>

      <div className="grid grid-cols-5 gap-2 mb-4">
        {(categories ?? []).map((c) => (
          <KpiCard key={c.key} label={c.label} value={byCategory[c.key] ?? 0} />
        ))}
      </div>

      <div className="flex items-center gap-3 mb-4">
        <DealerPicker dealers={dealers} selected={dealerFilter} onSelect={setDealerFilter} />
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
        >
          <option value="">All categories</option>
          {(categories ?? []).map((c) => (
            <option key={c.key} value={c.key}>{c.label}</option>
          ))}
        </select>
        <span className="text-[11px] text-zinc-500">{totalEvents} total event(s) recorded</span>
      </div>

      <div className="space-y-1">
        {(events ?? []).map((e) => (
          <div key={e.id} className="bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-2 flex items-center justify-between">
            <div className="min-w-0">
              <div className="text-sm truncate">{e.summary}</div>
              <div className="text-[11px] text-zinc-600">
                {e.category_label} · {e.dealer_id ?? "no dealer"} · {e.actor} · {new Date(e.timestamp).toLocaleString()}
              </div>
            </div>
          </div>
        ))}
        {events && events.length === 0 && (
          <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
            No audit events match these filters yet.
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Users -- Dealer Management rebuild, slice 5 of 5 (FINAL). A real Hub-side
// roster of named human contacts per dealer, distinct from the tenant's own
// internal Employee roster (which the Hub architecturally cannot see). See
// hub/core/dealer_contacts.py's own module docstring for the scope reasoning.
// ---------------------------------------------------------------------------

function UsersPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [roles, setRoles] = useState<ContactRoleEntry[] | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [users, setUsers] = useState<DealerUsers | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [name, setName] = useState("");
  const [role, setRole] = useState<ContactRole>("general_manager");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");

  useEffect(() => {
    listDealers().then(setDealers).catch((e) => setError(errorMessage(e)));
    getUsersCatalog()
      .then((r) => setRoles(r.roles))
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function loadUsers(id: string) {
    if (!id) {
      setUsers(null);
      return;
    }
    try {
      setUsers(await getDealerUsers(id));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadUsers(dealerId);
  }, [dealerId]);

  async function submitAdd() {
    if (!dealerId || !name.trim()) return;
    setBusy(true);
    setError("");
    try {
      setUsers(await addDealerContact(dealerId, { name, role, email: email || undefined, phone: phone || undefined }));
      setName("");
      setEmail("");
      setPhone("");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  async function removeContact(contactId: string) {
    setBusy(true);
    setError("");
    try {
      setUsers(await removeDealerContact(contactId));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div className="flex items-center gap-3 mb-6">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">Users</h3>
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
      </div>

      {!dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
          Select a dealer above to view their named contacts.
        </div>
      )}

      {dealerId && users && (
        <>
          <p className="text-[11px] text-zinc-500 leading-relaxed mb-4">{users.scope_note}</p>

          <div className="bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 mb-2">
            <div className="flex items-center justify-between">
              <div>
                <div className="text-sm font-medium">{users.primary_contact.name ?? "(no name on file)"}</div>
                <div className="text-[11px] text-zinc-500">
                  {users.primary_contact.email ?? "—"} · {users.primary_contact.phone ?? "—"}
                </div>
              </div>
              <span className="text-[10px] uppercase tracking-wide text-zinc-500 bg-zinc-900 px-2 py-1 rounded">
                {users.primary_contact.role_label}
              </span>
            </div>
          </div>

          {users.additional_contacts.map((c) => (
            <div key={c.contact_id} className="bg-zinc-950 border border-zinc-800 rounded-lg px-4 py-3 mb-2">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium">{c.name}</div>
                  <div className="text-[11px] text-zinc-500">{c.email ?? "—"} · {c.phone ?? "—"}</div>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-[10px] uppercase tracking-wide text-zinc-500 bg-zinc-900 px-2 py-1 rounded">
                    {c.role_label}
                  </span>
                  <button
                    disabled={busy}
                    onClick={() => removeContact(c.contact_id)}
                    className="text-red-400 text-[11px] disabled:opacity-50"
                  >
                    Remove
                  </button>
                </div>
              </div>
            </div>
          ))}

          <div className="bg-zinc-900 rounded-lg p-4 mt-4">
            <div className="text-xs uppercase tracking-wide text-zinc-500 mb-3">+ Add Contact</div>
            <div className="grid grid-cols-4 gap-2 mb-2">
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Name"
                className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
              />
              <select
                value={role}
                onChange={(e) => setRole(e.target.value as ContactRole)}
                className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
              >
                {(roles ?? []).map((r) => (
                  <option key={r.key} value={r.key}>{r.label}</option>
                ))}
              </select>
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email (optional)"
                className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
              />
              <input
                value={phone}
                onChange={(e) => setPhone(e.target.value)}
                placeholder="Phone (optional)"
                className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
              />
            </div>
            <button
              disabled={busy || !name.trim()}
              onClick={submitAdd}
              className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
            >
              {busy ? "Adding…" : "+ Add Contact"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Honest placeholder for the remaining not-yet-built menu items
// ---------------------------------------------------------------------------

function PlaceholderPanel({ item }: { item: { key: MenuItemKey; label: string; blurb: string } }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-8 text-center">
      <div className="text-[10px] uppercase tracking-[0.3em] text-zinc-600 mb-3">
        Coming Soon
      </div>
      <h3 className="text-lg font-brand font-bold mb-2">{item.label}</h3>
      <p className="text-sm text-zinc-400 max-w-md mx-auto">{item.blurb}</p>
      <p className="text-[11px] text-zinc-600 mt-4 max-w-md mx-auto">
        This menu item is real and navigable, but its real data/actions haven&apos;t
        been built yet -- this is an honest placeholder, not fabricated content.
        Planned for a future Dealer Management slice.
      </p>
    </div>
  );
}
