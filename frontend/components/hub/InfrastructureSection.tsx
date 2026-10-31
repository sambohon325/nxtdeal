"use client";

import { dealerDisplayName } from "@/lib/brandDisplay";

// NXTDeal Hub -- "Infrastructure & Platform Operations" rebuild (2026-07-19), slice 1
// of 4. Sam's own framing, renaming the old flat "Server Health" tab: "think Azure
// Status Page," since the platform will eventually run thousands of dealer tenants --
// a real 12-item menu (Overview | Clusters | Services | Databases | AI Infrastructure
// | Network Health | Messaging | Storage | Backups | Disaster Recovery | Security |
// Monitoring).
//
// This slice ships the real menu shell for all 12 items, plus real content behind
// exactly two of them: Overview (real topology + a real Azure-style Platform Status
// Board, hub/core/infra_overview.py + hub/core/platform_status.py) and Services (real
// per-route-group request/error/latency metrics -- always-live for the Hub, on-demand
// "Recheck" for each dealer tenant -- hub/core/infra_services.py). The other 10 items
// render an honest "coming soon" placeholder, NOT fabricated data, each naming which
// future slice owns it (slice 2: Clusters/Databases/Storage/Backups/Disaster Recovery;
// slice 3: AI Infrastructure/Network Health; slice 4: Messaging/Security/Monitoring).
//
// UPDATE (2026-07-19, slice 3 of 4): AI Infrastructure and Network Health (with
// Privacy Audit) are now real too -- see hub/core/infra_ai.py and hub/core/
// infra_network_health.py. Only Messaging/Security/Monitoring (slice 4) remain
// honest placeholders.
//
// UPDATE (2026-07-19, slice 4 of 4, CLOSING): Messaging, Security, and Monitoring
// are now real too -- ALL 12 menu items are real, no placeholders remain. Messaging
// (hub/core/infra_messaging.py) states the honest primary gap (no cross-tenant/
// Hub-to-tenant messaging system exists anywhere) alongside one genuinely safe
// signal -- each tenant's own per-employee chat subsystem's coarse, non-PII
// connection/channel liveness, reusing the Services panel's already-fetched
// snapshot (backend/core/platform_metrics.py's new `messaging_subsystem` block --
// no new tenant route). Security (hub/core/infra_security.py) composes the Hub's
// own shared-secret-key configuration posture (a real env-var presence check,
// never the secret itself) with a real per-dealer account-lockout/IP-allowlist/
// password-policy rollup, reusing the Support Center panel's already-fetched
// snapshot (backend/core/audit_network_snapshot.py's new `security_posture` block
// -- no new tenant route). Monitoring (hub/core/infra_monitoring.py) is a genuine
// single-pane-of-glass composition of NOC + Platform Status + AI Infrastructure +
// Network Health's own already-real signals -- not a 4th independent monitoring
// engine.
//
// CRITICAL, restated from the backend modules this panel renders: every figure here is
// a real, in-memory request/error/latency counter or a real, live reachability check --
// NEVER a fabricated CPU/node/cluster number. Sam's own illustrative examples (e.g. "US
// East: 340 nodes") describe the eventual multi-region vision, not literal targets to
// reproduce with today's single-Hub-process, single/few-tenant-process deployment.
//
// Split into its own component from the start, matching DealerManagementSection.tsx's
// own "extract when a screen gets real" convention -- this file mirrors that one's
// shape (MenuItemKey union, MENU_ITEMS/REAL_ITEMS, shared KpiCard/ErrorBanner/
// DealerPicker/EnforcementNotice/PlaceholderPanel look) rather than reinventing it.

import { useEffect, useState } from "react";
import {
  HubApiError,
  listDealers,
  getInfraOverview,
  getPlatformStatusBoard,
  getServicesOverview,
  getDealerServices,
  recheckDealerServices,
  getClustersOverview,
  getDatabasesOverview,
  getDealerDatabases,
  getStorageOverview,
  recheckDealerStorage,
  getBackupsOverview,
  getDealerBackups,
  logDealerBackup,
  getDisasterRecoveryStatus,
  getAiInfrastructureOverview,
  recheckAllAiInfrastructure,
  recheckDealerAiInfrastructure,
  getNetworkHealthOverview,
  getPrivacyAudit,
  getMessagingOverview,
  getSecurityOverview,
  getMonitoringOverview,
  type Dealer,
  type InfraOverview,
  type PlatformStatusBoard,
  type PlatformStatusEntry,
  type ServicesOverview,
  type DealerPlatformMetricsResult,
  type ClustersOverview,
  type DatabasesOverview,
  type DealerDatabasesDetail,
  type StorageOverview,
  type BackupsOverview,
  type DealerBackupsDetail,
  type DisasterRecoveryStatus,
  type AiInfrastructureOverview,
  type NetworkHealthOverview,
  type PrivacyAudit,
  type MessagingOverview,
  type SecurityOverview,
  type MonitoringOverview,
} from "@/lib/hubApi";

type MenuItemKey =
  | "overview"
  | "clusters"
  | "services"
  | "databases"
  | "ai_infrastructure"
  | "network_health"
  | "messaging"
  | "storage"
  | "backups"
  | "disaster_recovery"
  | "security"
  | "monitoring";

const MENU_ITEMS: { key: MenuItemKey; label: string; blurb: string }[] = [
  { key: "overview", label: "Overview", blurb: "Real topology + a real Azure-style Platform Status Board." },
  { key: "clusters", label: "Clusters", blurb: "Real deployment topology grouped by region, honest gaps on CPU/auto-scale." },
  { key: "services", label: "Services", blurb: "Real per-route-group request/error/latency metrics, Hub + every dealer." },
  { key: "databases", label: "Databases", blurb: "Real Primary Data Store health; Replica/Analytics/Warehouse/AI Data Stores honestly not_applicable." },
  { key: "ai_infrastructure", label: "AI Infrastructure", blurb: "Real per-model usage across every dealer's last-known AI snapshot; Response Time/Accuracy/Training Jobs are confirmed gaps." },
  { key: "network_health", label: "Network Health", blurb: "Real Network Members/Anonymous Datasets + a real, re-runnable Privacy Audit." },
  { key: "messaging", label: "Messaging", blurb: "Honest gap: no cross-tenant messaging system exists. Real, non-PII per-tenant chat liveness signal instead." },
  { key: "storage", label: "Storage", blurb: "Real file sizes for every tenant + Hub storage file, no PII." },
  { key: "backups", label: "Backups", blurb: "Real observed backup files + a real NXTDeal-staff backup confirmation log." },
  { key: "disaster_recovery", label: "Disaster Recovery", blurb: "A real recovery playbook (the exact method used twice this session) + live status signals." },
  { key: "security", label: "Security", blurb: "Real Hub shared-key configuration posture + a real per-dealer account-lockout/IP-allowlist rollup." },
  { key: "monitoring", label: "Monitoring", blurb: "A real single-pane-of-glass composition of NOC + Platform Status + AI Infrastructure + Network Health." },
];

const REAL_ITEMS: MenuItemKey[] = [
  "overview",
  "services",
  "clusters",
  "databases",
  "storage",
  "backups",
  "disaster_recovery",
  "ai_infrastructure",
  "network_health",
  "messaging",
  "security",
  "monitoring",
];

function backupLogTime(entry: { logged_at: string | null; timestamp_status?: string }): string {
  if (!entry.logged_at || entry.timestamp_status === "unknown") return "Time unknown";
  const date = new Date(entry.logged_at);
  if (entry.timestamp_status === "invalid" || !Number.isFinite(date.getTime())) return "Time invalid";
  return date.toLocaleString();
}

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

function EnforcementNotice({ text }: { text: string }) {
  return (
    <div className="mb-4 text-[11px] text-yellow-500 bg-yellow-950/20 border border-yellow-900 rounded-lg px-4 py-3">
      {text}
    </div>
  );
}

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

const STATUS_STYLES: Record<string, string> = {
  operational: "text-green-400 bg-green-950/40",
  no_traffic_yet: "text-zinc-400 bg-zinc-800/60",
  performance_warning: "text-yellow-400 bg-yellow-950/40",
  degraded: "text-orange-400 bg-orange-950/40",
  down: "text-red-400 bg-red-950/40",
  unreachable: "text-red-400 bg-red-950/40",
  not_checked: "text-zinc-500 bg-zinc-800/60",
};

function StatusBadge({ status, label }: { status: string; label: string }) {
  return (
    <span
      className={`text-[10px] uppercase tracking-wide px-2 py-1 rounded whitespace-nowrap ${
        STATUS_STYLES[status] ?? "text-zinc-400 bg-zinc-800/60"
      }`}
    >
      {label}
    </span>
  );
}

export default function InfrastructureSection() {
  const [item, setItem] = useState<MenuItemKey>("overview");

  return (
    <div className="flex gap-6 h-full">
      <nav className="w-56 shrink-0">
        <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-600 mb-2 px-1">
          Infrastructure &amp; Platform Ops
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
        {item === "overview" && <InfraOverviewPanel />}
        {item === "services" && <ServicesPanel />}
        {item === "clusters" && <ClustersPanel />}
        {item === "databases" && <DatabasesPanel />}
        {item === "storage" && <StoragePanel />}
        {item === "backups" && <BackupsPanel />}
        {item === "disaster_recovery" && <DisasterRecoveryPanel />}
        {item === "ai_infrastructure" && <AiInfrastructurePanel />}
        {item === "network_health" && <NetworkHealthPanel />}
        {item === "messaging" && <MessagingPanel />}
        {item === "security" && <SecurityPanel />}
        {item === "monitoring" && <MonitoringPanel />}
        {!REAL_ITEMS.includes(item) && (
          <PlaceholderPanel item={MENU_ITEMS.find((m) => m.key === item)!} />
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Overview -- real topology + a real Azure-style Platform Status Board
// ---------------------------------------------------------------------------

function InfraOverviewPanel() {
  const [overview, setOverview] = useState<InfraOverview | null>(null);
  const [board, setBoard] = useState<PlatformStatusBoard | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      const [ov, pb] = await Promise.all([getInfraOverview(), getPlatformStatusBoard()]);
      setOverview(ov);
      setBoard(pb);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const overallLabel =
    board?.overall_status === "operational"
      ? "All Systems Operational"
      : board?.overall_status === "performance_warning"
      ? "Performance Warning"
      : board?.overall_status === "degraded"
      ? "Degraded"
      : board?.overall_status === "down"
      ? "Down / Unreachable Component(s)"
      : "…";

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div
        className={`mb-6 rounded-lg px-5 py-4 border ${
          board
            ? STATUS_STYLES[board.overall_status]?.replace("text-", "border-").split(" ")[0] ??
              "border-zinc-800"
            : "border-zinc-800"
        } bg-zinc-900`}
      >
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[10px] uppercase tracking-[0.2em] text-zinc-600 mb-1">
              Platform Status
            </div>
            <div className="text-lg font-brand font-bold">
              {overallLabel}
            </div>
          </div>
          <button
            onClick={load}
            disabled={loading}
            className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
          >
            {loading ? "Refreshing…" : "↻ Refresh"}
          </button>
        </div>
        {overview && (
          <p className="text-sm text-zinc-400 mt-2">{overview.platform_health.summary}</p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 mb-3">
        <KpiCard label="Hub Processes" value={overview?.topology.hub_processes ?? "…"} />
        <KpiCard
          label="Tenant Processes Registered"
          value={overview?.topology.tenant_processes_registered ?? "…"}
        />
        <KpiCard
          label="Tenants Reachable"
          value={overview?.topology.tenant_processes_reachable ?? "…"}
        />
      </div>
      <div className="grid grid-cols-3 gap-3 mb-6">
        <KpiCard
          label="Tenants Unreachable"
          value={overview?.topology.tenant_processes_unreachable ?? "…"}
        />
        <KpiCard
          label="Tenants Not Configured"
          value={overview?.topology.tenant_processes_not_configured ?? "…"}
        />
        <KpiCard
          label="Hub Uptime"
          value={
            overview
              ? `${Math.floor(overview.hub_uptime_seconds / 60)} min`
              : "…"
          }
        />
      </div>

      {overview && (
        <p className="text-[11px] text-zinc-600 leading-relaxed mb-6">
          {overview.topology.deployment_model}
        </p>
      )}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        Platform Status Board
      </h3>

      {board && (
        <div className="grid grid-cols-4 gap-2 mb-4">
          <KpiCard label="Down / Unreachable" value={board.counts.down + board.counts.unreachable} />
          <KpiCard label="Degraded" value={board.counts.degraded} />
          <KpiCard label="Performance Warning" value={board.counts.performance_warning} />
          <KpiCard label="Total Services Tracked" value={board.counts.total} />
        </div>
      )}

      <div className="bg-zinc-900 rounded-lg overflow-hidden mb-4">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Service</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Requests</th>
              <th className="text-left px-4 py-2">Error Rate</th>
              <th className="text-left px-4 py-2">Avg Latency</th>
            </tr>
          </thead>
          <tbody>
            {(board?.entries ?? []).map((e: PlatformStatusEntry) => (
              <tr key={e.service_id} className="border-t border-zinc-800">
                <td className="px-4 py-2">
                  {e.service_label}
                  <span className="text-[10px] text-zinc-600 ml-2 uppercase">
                    {e.scope === "hub" ? "hub" : "tenant"}
                  </span>
                </td>
                <td className="px-4 py-2">
                  <StatusBadge status={e.status} label={e.status_label} />
                </td>
                <td className="px-4 py-2 text-zinc-400">{e.request_count ?? "--"}</td>
                <td className="px-4 py-2 text-zinc-400">
                  {e.error_rate_pct != null ? `${e.error_rate_pct}%` : "--"}
                </td>
                <td className="px-4 py-2 text-zinc-400">
                  {e.avg_latency_ms != null ? `${e.avg_latency_ms} ms` : "--"}
                </td>
              </tr>
            ))}
            {board && board.entries.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                  No services to report yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {board && <p className="text-[11px] text-zinc-600 leading-relaxed">{board.note}</p>}
      {overview && (
        <p className="text-[11px] text-zinc-600 leading-relaxed mt-2">{overview.note}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Services -- real Hub metrics (always live) + per-dealer metrics (on-demand
// "Recheck", last-known snapshot shown between rechecks)
// ---------------------------------------------------------------------------

function ServicesPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [overview, setOverview] = useState<ServicesOverview | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [dealerMetrics, setDealerMetrics] = useState<DealerPlatformMetricsResult | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function loadOverview() {
    try {
      setOverview(await getServicesOverview());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    listDealers()
      .then(setDealers)
      .catch((e) => setError(errorMessage(e)));
    loadOverview();
  }, []);

  async function loadDealerMetrics(id: string) {
    if (!id) {
      setDealerMetrics(null);
      return;
    }
    try {
      setDealerMetrics(await getDealerServices(id));
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    loadDealerMetrics(dealerId);
  }, [dealerId]);

  async function runRecheck() {
    if (!dealerId) return;
    setBusy("recheck");
    setError("");
    try {
      const snapshot = await recheckDealerServices(dealerId);
      setDealerMetrics((prev) =>
        prev ? { ...prev, snapshot } : { dealer_id: dealerId, dealer_name: "", snapshot }
      );
      loadOverview();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  const hubGroups = overview
    ? Object.entries(overview.hub_metrics.groups).filter(([, g]) => g.request_count > 0)
    : [];
  const hubIdleGroups = overview
    ? Object.entries(overview.hub_metrics.groups).filter(([, g]) => g.request_count === 0)
    : [];

  const dealerGroups = dealerMetrics?.snapshot.data?.groups
    ? Object.entries(dealerMetrics.snapshot.data.groups)
    : [];

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice
        text="Real, in-memory request/error/latency counters -- reset to zero on every process restart, never fabricated. The Hub's own metrics below are always live; each dealer's metrics reflect their LAST-KNOWN snapshot -- click Recheck for a fresh live pull."
      />

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        NXTDeal Hub -- Live Route Groups
      </h3>

      <div className="bg-zinc-900 rounded-lg overflow-hidden mb-3">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Group</th>
              <th className="text-left px-4 py-2">Status</th>
              <th className="text-left px-4 py-2">Requests</th>
              <th className="text-left px-4 py-2">Errors</th>
              <th className="text-left px-4 py-2">Avg Latency</th>
            </tr>
          </thead>
          <tbody>
            {hubGroups.map(([key, g]) => (
              <tr key={key} className="border-t border-zinc-800">
                <td className="px-4 py-2">{g.label}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={g.status} label={g.status_label} />
                </td>
                <td className="px-4 py-2 text-zinc-400">{g.request_count}</td>
                <td className="px-4 py-2 text-zinc-400">
                  {g.error_count} ({g.error_rate_pct}%)
                </td>
                <td className="px-4 py-2 text-zinc-400">
                  {g.avg_latency_ms != null ? `${g.avg_latency_ms} ms` : "--"}
                </td>
              </tr>
            ))}
            {hubGroups.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                  No live Hub traffic recorded yet this process.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {hubIdleGroups.length > 0 && (
        <p className="text-[11px] text-zinc-600 mb-6">
          {hubIdleGroups.length} more Hub group(s) with no traffic yet:{" "}
          {hubIdleGroups.map(([, g]) => g.label).join(", ")}.
        </p>
      )}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        Dealer Tenant Route Groups
      </h3>

      <div className="flex items-center gap-3 mb-4">
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
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500 mb-6">
          Select a dealer above to view (or fetch a fresh) route-group metrics snapshot.
        </div>
      )}

      {dealerId && dealerMetrics && (
        <>
          <div className="flex items-center gap-2 mb-4">
            <span
              className={
                dealerMetrics.snapshot.reachable
                  ? "text-[10px] uppercase tracking-wide px-2 py-1 rounded text-green-400 bg-green-950/40"
                  : "text-[10px] uppercase tracking-wide px-2 py-1 rounded text-red-400 bg-red-950/40"
              }
            >
              {dealerMetrics.snapshot.fetched_at
                ? dealerMetrics.snapshot.reachable
                  ? "Reachable"
                  : "Unreachable"
                : "Never Checked"}
            </span>
            {dealerMetrics.snapshot.fetched_at && (
              <span className="text-[11px] text-zinc-600">
                last checked {new Date(dealerMetrics.snapshot.fetched_at).toLocaleString()}
              </span>
            )}
            {dealerMetrics.snapshot.error && (
              <span className="text-[11px] text-red-400">{dealerMetrics.snapshot.error}</span>
            )}
          </div>

          <div className="bg-zinc-900 rounded-lg overflow-hidden mb-4">
            <table className="w-full text-sm">
              <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left px-4 py-2">Group</th>
                  <th className="text-left px-4 py-2">Status</th>
                  <th className="text-left px-4 py-2">Requests</th>
                  <th className="text-left px-4 py-2">Errors</th>
                  <th className="text-left px-4 py-2">Avg Latency</th>
                </tr>
              </thead>
              <tbody>
                {dealerGroups.map(([key, g]) => (
                  <tr key={key} className="border-t border-zinc-800">
                    <td className="px-4 py-2">{g.label}</td>
                    <td className="px-4 py-2">
                      <StatusBadge status={g.status} label={g.status_label} />
                    </td>
                    <td className="px-4 py-2 text-zinc-400">{g.request_count}</td>
                    <td className="px-4 py-2 text-zinc-400">
                      {g.error_count} ({g.error_rate_pct}%)
                    </td>
                    <td className="px-4 py-2 text-zinc-400">
                      {g.avg_latency_ms != null ? `${g.avg_latency_ms} ms` : "--"}
                    </td>
                  </tr>
                ))}
                {dealerGroups.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                      {dealerMetrics.snapshot.fetched_at
                        ? "No group data available from the last check."
                        : "Click Recheck to fetch this dealer's live route-group metrics."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3 mt-6">
        All Dealers -- Last-Known Status
      </h3>

      <div className="bg-zinc-900 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Dealer</th>
              <th className="text-left px-4 py-2">Checked</th>
              <th className="text-left px-4 py-2">Reachable</th>
              <th className="text-left px-4 py-2">Groups</th>
              <th className="text-left px-4 py-2">Last Fetched</th>
            </tr>
          </thead>
          <tbody>
            {(overview?.dealers ?? []).map((d) => (
              <tr key={d.dealer_id} className="border-t border-zinc-800">
                <td className="px-4 py-2">{dealerDisplayName(d.dealer_name)}</td>
                <td className="px-4 py-2 text-zinc-400">{d.checked ? "Yes" : "Never"}</td>
                <td className="px-4 py-2 text-zinc-400">
                  {d.reachable === null ? "--" : d.reachable ? "Yes" : "No"}
                </td>
                <td className="px-4 py-2 text-zinc-400">{d.group_count}</td>
                <td className="px-4 py-2 text-zinc-500">
                  {d.fetched_at ? new Date(d.fetched_at).toLocaleString() : "--"}
                </td>
              </tr>
            ))}
            {overview && overview.dealers.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                  No dealers registered yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {overview && (
        <p className="text-[11px] text-zinc-600 leading-relaxed mt-4">{overview.note}</p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Clusters -- real deployment topology grouped by region, honest gaps on
// CPU/Memory/Network telemetry and auto-scaling (neither exists anywhere in
// this codebase). Growth Trend is real cumulative dealer-signup count.
// ---------------------------------------------------------------------------

function ClustersPanel() {
  const [data, setData] = useState<ClustersOverview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getClustersOverview()
      .then(setData)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice
        text="This is a real deployment topology view (one process per dealer tenant), not a multi-node cluster manager -- CPU/Memory/Network and true auto-scaling are honest gaps, stated per-region below rather than fabricated."
      />

      {data && (
        <>
          <div className="grid grid-cols-2 gap-3 mb-6">
            {data.clusters.map((c) => (
              <div key={c.region_key} className="bg-zinc-900 rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="font-brand font-bold text-sm">{c.region_label}</div>
                  <span className="text-[10px] uppercase tracking-wide px-2 py-1 rounded bg-zinc-800 text-zinc-400">
                    {c.current_nodes} node(s)
                  </span>
                </div>
                <div className="grid grid-cols-3 gap-2 mb-3 text-center">
                  <div>
                    <div className="text-lg font-semibold text-green-400">{c.reachable}</div>
                    <div className="text-[10px] text-zinc-600 uppercase">Reachable</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold text-red-400">{c.unreachable}</div>
                    <div className="text-[10px] text-zinc-600 uppercase">Unreachable</div>
                  </div>
                  <div>
                    <div className="text-lg font-semibold text-zinc-500">{c.not_configured}</div>
                    <div className="text-[10px] text-zinc-600 uppercase">Not Configured</div>
                  </div>
                </div>
                <div className="text-[11px] text-zinc-500 mb-2">
                  Avg latency:{" "}
                  {c.metrics.avg_latency_ms != null ? `${c.metrics.avg_latency_ms} ms` : c.metrics.latency_basis}
                </div>
                <div className="text-[11px] text-zinc-600 mb-1">CPU / Memory / Network: not applicable</div>
                <p className="text-[10px] text-zinc-700 leading-relaxed mb-2">
                  {c.metrics.resource_telemetry_note}
                </p>
                <p className="text-[10px] text-zinc-700 leading-relaxed mb-2">{c.auto_scale.auto_scale_note}</p>
                {c.dealers.length > 0 && (
                  <div className="mt-2 border-t border-zinc-800 pt-2">
                    {c.dealers.map((d) => (
                      <div key={d.dealer_id} className="flex items-center justify-between text-[11px] py-1">
                        <span>
                          {dealerDisplayName(d.dealer_name)} <span className="text-zinc-600">({d.slug})</span>
                        </span>
                        <StatusBadge status={d.reachability} label={d.reachability} />
                      </div>
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
            Growth Trend -- Real Dealer Signups
          </h3>
          <div className="bg-zinc-900 rounded-lg overflow-hidden mb-3">
            <table className="w-full text-sm">
              <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
                <tr>
                  <th className="text-left px-4 py-2">Month</th>
                  <th className="text-left px-4 py-2">New Dealers</th>
                  <th className="text-left px-4 py-2">Cumulative</th>
                </tr>
              </thead>
              <tbody>
                {data.growth_trend.points.map((p) => (
                  <tr key={p.month} className="border-t border-zinc-800">
                    <td className="px-4 py-2">{p.month}</td>
                    <td className="px-4 py-2 text-zinc-400">{p.new_dealers}</td>
                    <td className="px-4 py-2 text-zinc-400">{p.cumulative_dealers}</td>
                  </tr>
                ))}
                {data.growth_trend.points.length === 0 && (
                  <tr>
                    <td colSpan={3} className="px-4 py-6 text-center text-zinc-500">
                      No dealer signups recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          <p className="text-[11px] text-zinc-600 leading-relaxed mb-1">{data.growth_trend.note}</p>
          <p className="text-[11px] text-zinc-600 leading-relaxed">{data.deployment_model_note}</p>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Databases -- real Primary Data Store health per dealer (graph.json size +
// real entity/relationship counts), honest not_applicable for Replica/
// Analytics/Warehouse/AI Data Stores (none exist as separate systems).
// ---------------------------------------------------------------------------

function DatabasesPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [overview, setOverview] = useState<DatabasesOverview | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [detail, setDetail] = useState<DealerDatabasesDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function loadOverview() {
    try {
      setOverview(await getDatabasesOverview());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    listDealers().then(setDealers).catch((e) => setError(errorMessage(e)));
    loadOverview();
  }, []);

  useEffect(() => {
    if (!dealerId) {
      setDetail(null);
      return;
    }
    getDealerDatabases(dealerId).then(setDetail).catch((e) => setError(errorMessage(e)));
  }, [dealerId]);

  async function runRecheck() {
    if (!dealerId) return;
    setBusy("recheck");
    setError("");
    try {
      await recheckDealerStorage(dealerId);
      const d = await getDealerDatabases(dealerId);
      setDetail(d);
      loadOverview();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice text="This tenant's REAL, and only, data store is a set of plain JSON files -- there is no separate Replica, Analytics, Warehouse, or AI Data Store anywhere in this deployment. Reported honestly below, not fabricated." />

      <div className="flex items-center gap-3 mb-4">
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
        <button
          disabled={!dealerId || busy === "recheck"}
          onClick={runRecheck}
          className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
        >
          {busy === "recheck" ? "Checking…" : "↻ Recheck Primary Store"}
        </button>
      </div>

      {dealerId && detail && (
        <div className="bg-zinc-900 rounded-lg overflow-hidden mb-6">
          <table className="w-full text-sm">
            <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
              <tr>
                <th className="text-left px-4 py-2">Tier</th>
                <th className="text-left px-4 py-2">Health</th>
                <th className="text-left px-4 py-2">Detail</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-zinc-800">
                <td className="px-4 py-2 font-medium">{detail.primary.label}</td>
                <td className="px-4 py-2">
                  <StatusBadge status={detail.primary.health} label={detail.primary.health} />
                </td>
                <td className="px-4 py-2 text-zinc-400 text-[12px]">
                  {detail.primary.storage ? (
                    <>
                      {JSON.stringify(detail.primary.storage).slice(0, 5) === "{"
                        ? Object.entries(detail.primary.storage as Record<string, unknown>)
                            .map(([k, v]) => `${k}: ${JSON.stringify(v)}`)
                            .join(" · ")
                        : String(detail.primary.storage)}
                    </>
                  ) : (
                    detail.primary.note
                  )}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      )}
      {!dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500 mb-6">
          Select a dealer above to view its real Primary Data Store health.
        </div>
      )}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">All Dealers -- Tier Coverage</h3>
      <div className="bg-zinc-900 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Dealer</th>
              {["Primary", "Replica", "Analytics", "Warehouse", "AI Data Stores"].map((t) => (
                <th key={t} className="text-left px-4 py-2">
                  {t}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(overview?.dealers ?? []).map((d) => (
              <tr key={d.dealer_id} className="border-t border-zinc-800">
                <td className="px-4 py-2">{dealerDisplayName(d.dealer_name)}</td>
                {d.tiers.map((t) => (
                  <td key={t.tier} className="px-4 py-2">
                    <StatusBadge status={t.health} label={t.health} />
                  </td>
                ))}
              </tr>
            ))}
            {overview && overview.dealers.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                  No dealers registered yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {overview && <p className="text-[11px] text-zinc-600 leading-relaxed mt-4">{overview.note}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Storage -- real file sizes across every tenant + the Hub's own storage
// files. No PII, no entity content -- sizes/counts only.
// ---------------------------------------------------------------------------

function StoragePanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [overview, setOverview] = useState<StorageOverview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  async function load() {
    try {
      setOverview(await getStorageOverview());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    listDealers().then(setDealers).catch((e) => setError(errorMessage(e)));
    load();
  }, []);

  async function runRecheck(dealerId: string) {
    setBusy(dealerId);
    setError("");
    try {
      await recheckDealerStorage(dealerId);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  function fmtBytes(n: number) {
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(2)} MB`;
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">NXTDeal Hub -- Own Storage</h3>
      <div className="bg-zinc-900 rounded-lg overflow-hidden mb-6">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Store</th>
              <th className="text-left px-4 py-2">Exists</th>
              <th className="text-left px-4 py-2">Size</th>
            </tr>
          </thead>
          <tbody>
            {(overview?.hub_storage.files ?? []).map((f) => (
              <tr key={f.store} className="border-t border-zinc-800">
                <td className="px-4 py-2">{f.store}</td>
                <td className="px-4 py-2 text-zinc-400">{f.exists ? "Yes" : "No"}</td>
                <td className="px-4 py-2 text-zinc-400">{fmtBytes(f.size_bytes)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {overview && (
        <p className="text-[11px] text-zinc-600 mb-6">
          Hub total: {fmtBytes(overview.hub_storage.total_size_bytes)}
        </p>
      )}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">Dealer Tenant Storage</h3>
      <div className="bg-zinc-900 rounded-lg overflow-hidden mb-3">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Dealer</th>
              <th className="text-left px-4 py-2">Checked</th>
              <th className="text-left px-4 py-2">Graph.json</th>
              <th className="text-left px-4 py-2">Audit.json</th>
              <th className="text-left px-4 py-2">Backups Dir</th>
              <th className="text-left px-4 py-2"></th>
            </tr>
          </thead>
          <tbody>
            {(overview?.dealers ?? []).map((d) => {
              const g = (d.data as { graph_json?: { size_bytes?: number } })?.graph_json;
              const a = (d.data as { audit_json?: { size_bytes?: number } })?.audit_json;
              const b = (d.data as { backups?: { total_size_bytes?: number; file_count?: number } })?.backups;
              return (
                <tr key={d.dealer_id} className="border-t border-zinc-800">
                  <td className="px-4 py-2">{dealerDisplayName(d.dealer_name)}</td>
                  <td className="px-4 py-2 text-zinc-400">
                    {d.checked ? (d.reachable ? "Yes" : "Unreachable") : "Never"}
                  </td>
                  <td className="px-4 py-2 text-zinc-400">
                    {g?.size_bytes != null ? fmtBytes(g.size_bytes) : "--"}
                  </td>
                  <td className="px-4 py-2 text-zinc-400">
                    {a?.size_bytes != null ? fmtBytes(a.size_bytes) : "--"}
                  </td>
                  <td className="px-4 py-2 text-zinc-400">
                    {b ? `${fmtBytes(b.total_size_bytes ?? 0)} (${b.file_count} file(s))` : "--"}
                  </td>
                  <td className="px-4 py-2">
                    <button
                      disabled={busy === d.dealer_id}
                      onClick={() => runRecheck(d.dealer_id)}
                      className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-2 py-1 rounded text-[11px] uppercase tracking-wide disabled:opacity-50"
                    >
                      {busy === d.dealer_id ? "…" : "↻ Recheck"}
                    </button>
                  </td>
                </tr>
              );
            })}
            {overview && overview.dealers.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-6 text-center text-zinc-500">
                  No dealers registered yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {overview && <p className="text-[11px] text-zinc-600 leading-relaxed mt-2">{overview.note}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Backups -- real observed backup files (via the storage-snapshot fetch) +
// a real, honest-manual NXTDeal-staff backup confirmation log.
// ---------------------------------------------------------------------------

function BackupsPanel() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [overview, setOverview] = useState<BackupsOverview | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [detail, setDetail] = useState<DealerBackupsDetail | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [loggedBy, setLoggedBy] = useState("");
  const [label, setLabel] = useState("");
  const [note, setNote] = useState("");

  async function loadOverview() {
    try {
      setOverview(await getBackupsOverview());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    listDealers().then(setDealers).catch((e) => setError(errorMessage(e)));
    loadOverview();
  }, []);

  useEffect(() => {
    if (!dealerId) {
      setDetail(null);
      return;
    }
    getDealerBackups(dealerId).then(setDetail).catch((e) => setError(errorMessage(e)));
  }, [dealerId]);

  async function submitLog(e: React.FormEvent) {
    e.preventDefault();
    if (!dealerId || !loggedBy.trim()) return;
    setBusy(true);
    setError("");
    try {
      const result = await logDealerBackup(dealerId, {
        logged_by: loggedBy.trim(),
        label: label.trim() || undefined,
        note: note.trim() || undefined,
      });
      setDetail(result);
      setLabel("");
      setNote("");
      loadOverview();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice text="'Observed' below is a real, fetched count of files in this dealer's real backups/ directory (backend/core/data_backup.py's own ADMIN-triggered backup mechanism). 'Logged' is a separate, honest-manual record of a NXTDeal staffer confirming a backup happened (e.g. by phone) -- distinct signals, not conflated." />

      <div className="flex items-center gap-3 mb-4">
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
      </div>

      {dealerId && detail && (
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-zinc-900 rounded-lg p-4">
            <div className="text-[10px] uppercase tracking-wide text-zinc-600 mb-2">Observed (Real Fetch)</div>
            {detail.observed.checked ? (
              <>
                <div className="text-sm mb-1">
                  {detail.observed.backups?.file_count ?? 0} backup file(s),{" "}
                  {detail.observed.backups?.total_size_bytes
                    ? `${(detail.observed.backups.total_size_bytes / (1024 * 1024)).toFixed(2)} MB`
                    : "0 B"}
                </div>
                <div className="text-[11px] text-zinc-500">
                  Latest: {detail.observed.backups?.latest_file ?? "none"}
                </div>
                <div className="text-[11px] text-zinc-600 mt-1">
                  basis: {detail.observed.basis} · fetched{" "}
                  {detail.observed.fetched_at ? new Date(detail.observed.fetched_at).toLocaleString() : "--"}
                </div>
              </>
            ) : (
              <div className="text-sm text-zinc-500">Never checked -- visit Storage/Databases and Recheck.</div>
            )}
          </div>
          <div className="bg-zinc-900 rounded-lg p-4">
            <div className="text-[10px] uppercase tracking-wide text-zinc-600 mb-2">
              Logged Events ({detail.logged_events.length})
            </div>
            <div className="max-h-32 overflow-y-auto space-y-1">
              {detail.logged_events.map((ev) => (
                <div key={ev.log_id} className="text-[11px] text-zinc-400">
                  {ev.label || "(no label)"} — {ev.logged_by} — {backupLogTime(ev)}
                  {ev.note && <div className="text-zinc-600">{ev.note}</div>}
                </div>
              ))}
              {detail.logged_events.length === 0 && (
                <div className="text-[11px] text-zinc-600">No backup events logged yet for this dealer.</div>
              )}
            </div>
          </div>
        </div>
      )}

      {dealerId && (
        <form onSubmit={submitLog} className="bg-zinc-900 rounded-lg p-4 mb-6 flex flex-col gap-2">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">Log a Backup Confirmation</div>
          <input
            value={loggedBy}
            onChange={(e) => setLoggedBy(e.target.value)}
            placeholder="Logged by (your name)"
            className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
          />
          <input
            value={label}
            onChange={(e) => setLabel(e.target.value)}
            placeholder="Label (optional)"
            className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
          />
          <input
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Note (optional)"
            className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
          />
          <button
            type="submit"
            disabled={busy || !loggedBy.trim()}
            className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50 self-start"
          >
            {busy ? "Logging…" : "Log Backup Event"}
          </button>
        </form>
      )}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">All Dealers -- Backup Summary</h3>
      <div className="bg-zinc-900 rounded-lg overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-zinc-800 text-zinc-400 text-xs uppercase tracking-wide">
            <tr>
              <th className="text-left px-4 py-2">Dealer</th>
              <th className="text-left px-4 py-2">Observed Backups</th>
              <th className="text-left px-4 py-2">Latest Observed</th>
              <th className="text-left px-4 py-2">Logged Events</th>
              <th className="text-left px-4 py-2">Latest Logged</th>
            </tr>
          </thead>
          <tbody>
            {(overview?.dealers ?? []).map((d) => (
              <tr key={d.dealer_id} className="border-t border-zinc-800">
                <td className="px-4 py-2">{dealerDisplayName(d.dealer_name)}</td>
                <td className="px-4 py-2 text-zinc-400">{d.observed_backup_count ?? "not checked"}</td>
                <td className="px-4 py-2 text-zinc-500">
                  {d.observed_latest_backup_at ? new Date(d.observed_latest_backup_at).toLocaleString() : "--"}
                </td>
                <td className="px-4 py-2 text-zinc-400">{d.logged_event_count}</td>
                <td className="px-4 py-2 text-zinc-500">
                  {d.latest_logged_event_at ? new Date(d.latest_logged_event_at).toLocaleString() : "--"}
                </td>
              </tr>
            ))}
            {overview && overview.dealers.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-6 text-center text-zinc-500">
                  No dealers registered yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      {overview && <p className="text-[11px] text-zinc-600 leading-relaxed mt-4">{overview.note}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Disaster Recovery -- documentation-first: a real recovery playbook (the
// exact git-based method used twice this session) + real composed status
// signals. Deliberately NOT a one-click automated restore.
// ---------------------------------------------------------------------------

function DisasterRecoveryPanel() {
  const [data, setData] = useState<DisasterRecoveryStatus | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    getDisasterRecoveryStatus()
      .then(setData)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      {data && <EnforcementNotice text={data.disclosure} />}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">Recovery Playbook</h3>
      <div className="flex flex-col gap-2 mb-6">
        {(data?.playbook ?? []).map((s) => (
          <div key={s.step} className="bg-zinc-900 rounded-lg p-4">
            <div className="flex items-center gap-2 mb-1">
              <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded bg-zinc-800 text-zinc-400">
                Step {s.step}
              </span>
              <span className="font-medium text-sm">{s.title}</span>
            </div>
            <p className="text-[12px] text-zinc-400 leading-relaxed whitespace-pre-line">{s.detail}</p>
          </div>
        ))}
      </div>

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">Per-Dealer DR Status</h3>
      <div className="flex flex-col gap-3">
        {(data?.dealers ?? []).map((d) => (
          <div key={d.dealer_id} className="bg-zinc-900 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="font-medium text-sm">{dealerDisplayName(d.dealer_name)}</div>
              <StatusBadge status={d.current_reachability} label={d.current_reachability} />
            </div>
            <div className="grid grid-cols-3 gap-3 text-[11px]">
              <div>
                <div className="text-zinc-600 uppercase tracking-wide mb-1">Latest Observed Backup</div>
                <div className="text-zinc-400">
                  {d.latest_observed_backup?.latest_file ?? "none observed"}
                </div>
                {d.latest_observed_backup?.latest_modified_at && (
                  <div className="text-zinc-600">
                    {new Date(d.latest_observed_backup.latest_modified_at).toLocaleString()}
                  </div>
                )}
              </div>
              <div>
                <div className="text-zinc-600 uppercase tracking-wide mb-1">Latest Dated Logged Event</div>
                <div className="text-zinc-400">
                  {d.latest_logged_backup_event ? d.latest_logged_backup_event.label || "(no label)" : "No event with a valid timestamp"}
                </div>
                {d.latest_logged_backup_event && (
                  <div className="text-zinc-600">
                    {backupLogTime(d.latest_logged_backup_event)}
                  </div>
                )}
              </div>
              <div>
                <div className="text-zinc-600 uppercase tracking-wide mb-1">Git-Tracked Snapshot</div>
                {d.git_snapshot_check ? (
                  <>
                    <div className="text-zinc-400">{d.git_snapshot_check.last_commit_hash}</div>
                    <div className="text-zinc-600">
                      {d.git_snapshot_check.last_committed_at
                        ? new Date(d.git_snapshot_check.last_committed_at).toLocaleString()
                        : "--"}
                    </div>
                  </>
                ) : (
                  <div className="text-zinc-600">not tracked / dev-only check unavailable</div>
                )}
              </div>
            </div>
          </div>
        ))}
        {data && data.dealers.length === 0 && (
          <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
            No dealers registered yet.
          </div>
        )}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// AI Infrastructure -- real per-model usage aggregated across every dealer's
// last-known AI feature snapshot (hub/core/infra_ai.py, re-slicing the
// SAME real data hub/core/dealer_ai_management.py already fetches, no new
// tenant route). Response Time / Accuracy / Training Jobs are confirmed,
// stated gaps, not fabricated.
// ---------------------------------------------------------------------------

function AiInfrastructurePanel() {
  const [data, setData] = useState<AiInfrastructureOverview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");
  const [expanded, setExpanded] = useState<string>("");

  async function load() {
    try {
      setData(await getAiInfrastructureOverview());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runRecheckAll() {
    setBusy("all");
    setError("");
    try {
      await recheckAllAiInfrastructure();
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  async function runRecheckDealer(dealerId: string) {
    setBusy(dealerId);
    setError("");
    try {
      await recheckDealerAiInfrastructure(dealerId);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice text="Usage (attempted) is a real, in-memory, per-tenant-process call-attempt counter aggregated across every dealer's LAST-KNOWN AI snapshot -- not live-refetched on every page load. Response Time, Accuracy, and Training Jobs (Running/Queued/Failed) are all confirmed, stated gaps below, never fabricated." />

      <div className="grid grid-cols-3 gap-3 mb-3">
        <KpiCard label="Dealers Total" value={data?.dealers_total ?? "…"} />
        <KpiCard label="Dealers Checked" value={data?.dealers_checked ?? "…"} />
        <KpiCard label="Dealers Reachable" value={data?.dealers_reachable ?? "…"} />
      </div>

      <div className="flex justify-end mb-4">
        <button
          onClick={runRecheckAll}
          disabled={busy === "all"}
          className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
        >
          {busy === "all" ? "Rechecking…" : "↻ Recheck All Dealers"}
        </button>
      </div>

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        Models -- Hub-Wide Usage
      </h3>
      <div className="flex flex-col gap-2 mb-6">
        {(data?.models ?? []).map((m) => (
          <div key={m.key} className="bg-zinc-900 rounded-lg p-4">
            <div className="flex items-center justify-between mb-2">
              <div className="font-medium text-sm">{m.label}</div>
              <span className="text-[10px] uppercase tracking-wide px-2 py-1 rounded bg-zinc-800 text-zinc-400">
                {m.feature_count} real feature(s)
              </span>
            </div>
            {m.gap_note ? (
              <p className="text-[11px] text-yellow-500">{m.gap_note}</p>
            ) : (
              <div className="grid grid-cols-4 gap-2 text-center mb-2">
                <div>
                  <div className="text-lg font-semibold">{m.usage_attempted}</div>
                  <div className="text-[10px] text-zinc-600 uppercase">Attempted</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-green-400">{m.usage_succeeded}</div>
                  <div className="text-[10px] text-zinc-600 uppercase">Succeeded</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-yellow-400">{m.usage_fell_back}</div>
                  <div className="text-[10px] text-zinc-600 uppercase">Fell Back</div>
                </div>
                <div>
                  <div className="text-lg font-semibold text-red-400">{m.usage_blocked}</div>
                  <div className="text-[10px] text-zinc-600 uppercase">Blocked</div>
                </div>
              </div>
            )}
            <p className="text-[11px] text-zinc-600 leading-relaxed">{m.reasoning}</p>
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 gap-2 mb-6">
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wide text-red-400 mb-1">Response Time -- Confirmed Gap</div>
          <p className="text-[11px] text-zinc-500">{data?.response_time_gap}</p>
        </div>
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wide text-red-400 mb-1">Accuracy -- Confirmed Gap</div>
          <p className="text-[11px] text-zinc-500">{data?.accuracy_gap}</p>
        </div>
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wide text-red-400 mb-1">Cost -- Confirmed Gap</div>
          <p className="text-[11px] text-zinc-500">{data?.cost_gap}</p>
        </div>
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wide text-red-400 mb-1">
            Training Jobs (Running / Queued / Failed) -- Confirmed Structural Gap
          </div>
          <p className="text-[11px] text-zinc-500">{data?.training_jobs.note}</p>
        </div>
      </div>

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">Per-Dealer Snapshots</h3>
      <div className="flex flex-col gap-2">
        {(data?.per_dealer ?? []).map((d) => (
          <div key={d.dealer_id} className="bg-zinc-900 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{dealerDisplayName(d.dealer_name)}</span>
                <StatusBadge
                  status={!d.checked ? "not_checked" : d.reachable ? "operational" : "unreachable"}
                  label={!d.checked ? "Never Checked" : d.reachable ? "Reachable" : "Unreachable"}
                />
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() =>
                    setExpanded((prev) => (prev === d.dealer_id ? "" : d.dealer_id))
                  }
                  className="text-[11px] text-zinc-400 hover:text-white"
                >
                  {expanded === d.dealer_id ? "Hide models" : "Show models"}
                </button>
                <button
                  disabled={busy === d.dealer_id}
                  onClick={() => runRecheckDealer(d.dealer_id)}
                  className="bg-zinc-800 hover:bg-zinc-700 text-zinc-300 px-2 py-1 rounded text-[11px] uppercase tracking-wide disabled:opacity-50"
                >
                  {busy === d.dealer_id ? "…" : "↻ Recheck"}
                </button>
              </div>
            </div>
            {d.fetch_error && <p className="text-[11px] text-red-400 mt-1">{d.fetch_error}</p>}
            {expanded === d.dealer_id && (
              <div className="mt-3 grid grid-cols-1 gap-1">
                {d.models.map((m) => (
                  <div
                    key={m.key}
                    className="flex items-center justify-between text-[11px] text-zinc-400 border-t border-zinc-800 pt-1"
                  >
                    <span>{m.label}</span>
                    <span>
                      {m.feature_count === 0
                        ? "no real feature"
                        : `${m.usage_attempted} attempted / ${m.usage_succeeded} succeeded`}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}
        {data && data.per_dealer.length === 0 && (
          <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
            No dealers registered yet.
          </div>
        )}
      </div>

      {data && <p className="text-[11px] text-zinc-600 leading-relaxed mt-4">{data.note}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Network Health -- real Network Members / Active Snapshots / Anonymous
// Datasets (hub/core/infra_network_health.py), honest not_applicable for
// Prediction Runs / Benchmark Jobs (this system computes both on demand,
// not via a scheduled job queue), and a real, re-runnable Privacy Audit
// that inspects the actual NetworkSnapshot schema + every stored record
// against Sam's own never-collect field list.
// ---------------------------------------------------------------------------

function NetworkHealthPanel() {
  const [data, setData] = useState<NetworkHealthOverview | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function load() {
    try {
      setData(await getNetworkHealthOverview());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function rerunAudit() {
    setBusy(true);
    setError("");
    try {
      const audit = await getPrivacyAudit();
      setData((prev) => (prev ? { ...prev, privacy_audit: audit } : prev));
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  const audit: PrivacyAudit | undefined = data?.privacy_audit;

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-4 gap-3 mb-6">
        <KpiCard label="Network Members" value={data?.network_members ?? "…"} />
        <KpiCard label="Active Snapshots" value={data?.active_snapshots ?? "…"} />
        <KpiCard label="Anonymous Datasets" value={data?.anonymous_datasets ?? "…"} />
        <KpiCard label="Total Dealers" value={data?.total_dealers ?? "…"} />
      </div>
      {data && <p className="text-[11px] text-zinc-600 leading-relaxed mb-6">{data.datasets_note}</p>}

      <div className="grid grid-cols-2 gap-3 mb-6">
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
            Prediction Runs -- Not Applicable
          </div>
          <p className="text-[11px] text-zinc-500">{data?.prediction_runs.note}</p>
        </div>
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
            Benchmark Jobs -- Not Applicable
          </div>
          <p className="text-[11px] text-zinc-500">{data?.benchmark_jobs.note}</p>
        </div>
      </div>

      <div className="flex items-center justify-between mb-3">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">Privacy Audit</h3>
        <button
          onClick={rerunAudit}
          disabled={busy}
          className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
        >
          {busy ? "Auditing…" : "↻ Re-Run Privacy Audit"}
        </button>
      </div>

      {audit && (
        <>
          <div
            className={`mb-4 rounded-lg px-5 py-4 border ${
              audit.passed ? "border-green-900 bg-green-950/20" : "border-red-900 bg-red-950/20"
            }`}
          >
            <div className="text-lg font-brand font-bold">
              {audit.passed ? "PASSED -- No PII Detected" : "FAILED -- Review Findings Below"}
            </div>
            <p className="text-[11px] text-zinc-500 mt-1">{audit.method_note}</p>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-4">
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-2">
                Schema Check ({audit.schema_check.fields_inspected.length} field(s) inspected)
              </div>
              <div className="text-sm mb-1">
                Violations: {audit.schema_check.violations.length === 0 ? "none" : audit.schema_check.violations.join(", ")}
              </div>
              <p className="text-[11px] text-zinc-600">{audit.schema_check.note}</p>
            </div>
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-2">
                Stored Record Check ({audit.stored_record_check.records_inspected} record(s) inspected)
              </div>
              <div className="text-sm mb-1">
                Violations: {audit.stored_record_check.violations.length === 0 ? "none" : audit.stored_record_check.violations.join(", ")}
              </div>
              <div className="text-sm mb-1">
                PII pattern findings: {audit.stored_record_check.pii_pattern_findings.length}
              </div>
              <p className="text-[11px] text-zinc-600">{audit.stored_record_check.note}</p>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4 mb-4">
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-[10px] uppercase tracking-wide text-red-400 mb-2">
                NXTDeal NEVER Sees (checked against)
              </div>
              <div className="text-[11px] text-zinc-500 leading-relaxed">
                {audit.never_collect_fields.join(", ")}
              </div>
            </div>
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-[10px] uppercase tracking-wide text-green-400 mb-2">
                NXTDeal Sees
              </div>
              <div className="text-[11px] text-zinc-500 leading-relaxed">
                {audit.nxtdeal_sees_fields.join(", ")}
              </div>
            </div>
          </div>

          {audit.stored_record_check.distinct_keys_found.length > 0 && (
            <div className="bg-zinc-900 rounded-lg p-4">
              <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-2">
                Distinct Keys Found In Stored Records
              </div>
              <div className="text-[11px] text-zinc-500 leading-relaxed">
                {audit.stored_record_check.distinct_keys_found.join(", ")}
              </div>
            </div>
          )}
        </>
      )}

      {data && <p className="text-[11px] text-zinc-600 leading-relaxed mt-4">{data.note}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Messaging -- the honest primary gap (no cross-tenant/Hub-to-tenant messaging
// system exists anywhere in this platform) stated up front, alongside the one
// genuinely safe signal: each tenant's own per-employee chat subsystem's
// coarse, non-PII connection/channel liveness. Reuses the Services panel's
// already-fetched snapshot (hub/core/infra_services.py) -- no new fetch, no
// separate Recheck action here.
// ---------------------------------------------------------------------------

function MessagingPanel() {
  const [data, setData] = useState<MessagingOverview | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setData(await getMessagingOverview());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div className="mb-6 rounded-lg px-5 py-4 border border-yellow-900 bg-yellow-950/20">
        <div className="text-sm font-brand font-bold text-yellow-400 mb-1">
          Confirmed Gap -- Not A &quot;Coming Soon&quot; Placeholder
        </div>
        <p className="text-[11px] text-zinc-400 leading-relaxed">
          {data?.cross_tenant_messaging.note}
        </p>
      </div>

      <div className="grid grid-cols-4 gap-3 mb-6">
        <KpiCard label="Dealers Checked" value={data?.aggregate.dealers_checked ?? "…"} />
        <KpiCard label="Dealers Total" value={data?.aggregate.dealers_total ?? "…"} />
        <KpiCard label="Open Socket Count (Total)" value={data?.aggregate.total_open_socket_count ?? "…"} />
        <KpiCard label="Employees Connected (Total)" value={data?.aggregate.total_employees_with_open_connection ?? "…"} />
      </div>

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        Per-Dealer Chat Subsystem Liveness
      </h3>
      <div className="flex flex-col gap-2">
        {(data?.per_dealer_chat_liveness ?? []).map((d) => (
          <div key={d.dealer_id} className="bg-zinc-900 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{dealerDisplayName(d.dealer_name)}</span>
                <StatusBadge
                  status={!d.checked ? "not_checked" : d.reachable ? "operational" : "unreachable"}
                  label={!d.checked ? "Never Checked" : d.reachable ? "Reachable" : "Unreachable"}
                />
              </div>
              {d.messaging_subsystem && (
                <div className="flex items-center gap-4 text-[11px] text-zinc-400">
                  <span>{d.messaging_subsystem.employees_with_open_connection} employee(s) connected</span>
                  <span>{d.messaging_subsystem.open_socket_count} open socket(s)</span>
                  <span>{d.messaging_subsystem.channels_configured} channel(s) configured</span>
                </div>
              )}
            </div>
            {d.messaging_subsystem && (
              <p className="text-[11px] text-zinc-600 leading-relaxed mt-2">{d.messaging_subsystem.note}</p>
            )}
          </div>
        ))}
        {data && data.per_dealer_chat_liveness.length === 0 && (
          <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
            No dealers registered yet.
          </div>
        )}
      </div>

      {data && <p className="text-[11px] text-zinc-600 leading-relaxed mt-4">{data.note}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Security -- the Hub's own shared-secret-key configuration posture (a real
// env-var presence check, never the secret itself) composed with a real
// per-dealer account-lockout/IP-allowlist/password-policy rollup off
// backend/core/auth.py. Reuses the Support Center panel's already-fetched
// snapshot (hub/core/dealer_support.py) -- no new fetch, no separate Recheck
// action here.
// ---------------------------------------------------------------------------

function SecurityPanel() {
  const [data, setData] = useState<SecurityOverview | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setData(await getSecurityOverview());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  const hub = data?.hub_security_posture;
  const tenant = data?.tenant_account_security;
  const hubKeyChecked = hub?.hub_shared_key_using_dev_fallback !== undefined;
  const networkKeyChecked = hub?.network_shared_key_using_dev_fallback !== undefined;
  const hubKeyNonDefault = hub?.hub_shared_key_configured_from_env === true && hub?.hub_shared_key_using_dev_fallback === false;
  const networkKeyNonDefault = hub?.network_shared_key_configured_from_env === true && hub?.network_shared_key_using_dev_fallback === false;

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        Hub&apos;s Own Security Posture
      </h3>
      <div
        className={`mb-3 rounded-lg px-5 py-4 border ${
          hubKeyNonDefault && networkKeyNonDefault
            ? "border-green-900 bg-green-950/20"
            : "border-red-900 bg-red-950/20"
        }`}
      >
        <p className="text-sm">{hubKeyChecked && networkKeyChecked ? hub?.summary : "Known development fallback checks are unavailable. Configuration presence alone does not establish key safety."}</p>
      </div>
      <div className="grid grid-cols-2 gap-3 mb-3">
        <div className="bg-zinc-900 rounded-lg p-4 flex items-center justify-between">
          <span className="text-[11px] text-zinc-400">NXTDEAL_HUB_KEY break-glass key</span>
          <StatusBadge
            status={hubKeyNonDefault ? "operational" : "down"}
            label={!hubKeyChecked ? "Unverified" : hubKeyNonDefault ? "Non-default" : "Dev Fallback"}
          />
        </div>
        <div className="bg-zinc-900 rounded-lg p-4 flex items-center justify-between">
          <span className="text-[11px] text-zinc-400">DEALEROS_NETWORK_KEY</span>
          <StatusBadge
            status={networkKeyNonDefault ? "operational" : "down"}
            label={!networkKeyChecked ? "Unverified" : networkKeyNonDefault ? "Non-default" : "Dev Fallback"}
          />
        </div>
      </div>
      {hub && <p className="text-[11px] text-zinc-600 leading-relaxed mb-6">{hub.note}</p>}

      <h3 className="font-brand font-bold uppercase tracking-wide text-sm mb-3">
        Per-Dealer Account Security
      </h3>
      <div className="grid grid-cols-3 gap-3 mb-3">
        <KpiCard label="Dealers Checked" value={tenant?.aggregate.dealers_checked ?? "…"} />
        <KpiCard label="Total Accounts" value={tenant?.aggregate.total_accounts_across_checked_dealers ?? "…"} />
        <KpiCard label="Locked Accounts" value={tenant?.aggregate.total_locked_accounts_across_checked_dealers ?? "…"} />
      </div>

      <div className="flex flex-col gap-2 mb-4">
        {(tenant?.dealers ?? []).map((d) => (
          <div key={d.dealer_id} className="bg-zinc-900 rounded-lg p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-medium text-sm">{dealerDisplayName(d.dealer_name)}</span>
                <StatusBadge
                  status={!d.checked ? "not_checked" : d.reachable ? "operational" : "unreachable"}
                  label={!d.checked ? "Never Checked" : d.reachable ? "Reachable" : "Unreachable"}
                />
              </div>
              {d.security_posture && (
                <div className="flex items-center gap-4 text-[11px] text-zinc-400">
                  <span>{d.security_posture.total_accounts} account(s)</span>
                  <span className={d.security_posture.locked_accounts_count > 0 ? "text-red-400" : ""}>
                    {d.security_posture.locked_accounts_count} locked
                  </span>
                  <span>{d.security_posture.ip_allowlisting_in_use ? "IP allowlisting in use" : "No IP allowlisting"}</span>
                </div>
              )}
            </div>
            {d.security_posture && (
              <p className="text-[11px] text-zinc-600 mt-2">
                Password policy: min {d.security_posture.password_policy.min_length} chars, letter+digit required.
                Lockout: {d.security_posture.lockout_policy.max_failed_attempts} failed attempts /
                {" "}{d.security_posture.lockout_policy.lockout_minutes} min lockout.
              </p>
            )}
          </div>
        ))}
        {tenant && tenant.dealers.length === 0 && (
          <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
            No dealers registered yet.
          </div>
        )}
      </div>

      {tenant && <p className="text-[11px] text-zinc-600 leading-relaxed">{tenant.note}</p>}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Monitoring -- a genuine single-pane-of-glass composition of NOC + Platform
// Status + AI Infrastructure + Network Health's own already-real signals, NOT
// a 4th independent monitoring engine. See each summary's `see_full_view`
// pointer for the underlying tab with full detail.
// ---------------------------------------------------------------------------

function MonitoringPanel() {
  const [data, setData] = useState<MonitoringOverview | null>(null);
  const [error, setError] = useState("");

  async function load() {
    try {
      setData(await getMonitoringOverview());
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div
        className={`mb-6 rounded-lg px-5 py-4 border ${
          data?.overall_status === "healthy" ? "border-green-900 bg-green-950/20" : "border-red-900 bg-red-950/20"
        }`}
      >
        <div className="text-lg font-brand font-bold">
          {data?.overall_status === "healthy" ? "HEALTHY -- All Subsystems Nominal" : "ATTENTION NEEDED"}
        </div>
        {data && data.subsystems_needing_attention.length > 0 && (
          <p className="text-[11px] text-red-400 mt-1">
            Needs attention: {data.subsystems_needing_attention.join(", ")}
          </p>
        )}
      </div>

      <div className="grid grid-cols-2 gap-4 mb-4">
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">NOC</span>
            <StatusBadge
              status={data?.noc_summary.overall_status === "healthy" ? "operational" : "degraded"}
              label={data?.noc_summary.overall_status ?? "…"}
            />
          </div>
          <div className="flex gap-4 text-[11px] text-zinc-400 mb-2">
            <span className="text-red-400">{data?.noc_summary.alert_counts.critical ?? 0} critical</span>
            <span className="text-yellow-400">{data?.noc_summary.alert_counts.warning ?? 0} warning</span>
            <span>{data?.noc_summary.alert_counts.info ?? 0} info</span>
          </div>
          <p className="text-[10px] text-zinc-600">{data?.noc_summary.see_full_view}</p>
        </div>

        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="flex items-center justify-between mb-2">
            <span className="text-sm font-medium">Platform Status</span>
            <StatusBadge
              status={data?.platform_status_summary.overall_status === "operational" ? "operational" : "degraded"}
              label={data?.platform_status_summary.overall_status ?? "…"}
            />
          </div>
          <div className="flex gap-4 text-[11px] text-zinc-400 mb-2">
            <span className="text-red-400">{data?.platform_status_summary.counts.down ?? 0} down</span>
            <span className="text-yellow-400">{data?.platform_status_summary.counts.degraded ?? 0} degraded</span>
            <span>{data?.platform_status_summary.counts.total ?? 0} total</span>
          </div>
          <p className="text-[10px] text-zinc-600">{data?.platform_status_summary.see_full_view}</p>
        </div>

        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-sm font-medium mb-2">AI Infrastructure</div>
          <div className="flex gap-4 text-[11px] text-zinc-400 mb-2">
            <span>{data?.ai_infrastructure_summary.dealers_reachable ?? 0} / {data?.ai_infrastructure_summary.dealers_total ?? 0} reachable</span>
            <span>{data?.ai_infrastructure_summary.dealers_checked ?? 0} checked</span>
          </div>
          <p className="text-[11px] text-yellow-500 mb-2">
            Confirmed gaps: {data?.ai_infrastructure_summary.confirmed_gaps.join(", ")}
          </p>
          <p className="text-[10px] text-zinc-600">{data?.ai_infrastructure_summary.see_full_view}</p>
        </div>

        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-sm font-medium mb-2">Network Health</div>
          <div className="flex gap-4 text-[11px] text-zinc-400 mb-2">
            <span>{data?.network_health_summary.network_members ?? 0} members</span>
            <span>{data?.network_health_summary.active_snapshots ?? 0} active snapshots</span>
            <span className={data?.network_health_summary.privacy_audit_passed ? "text-green-400" : "text-red-400"}>
              Privacy Audit {data?.network_health_summary.privacy_audit_passed ? "Passed" : "Failed"}
            </span>
          </div>
          <p className="text-[10px] text-zinc-600">{data?.network_health_summary.see_full_view}</p>
        </div>
      </div>

      {data && <p className="text-[11px] text-zinc-600 leading-relaxed mt-2">{data.note}</p>}
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
      </p>
    </div>
  );
}
