"use client";

import { dealerDisplayName } from "@/lib/brandDisplay";

import { BrandLogo } from "@/components/BrandLogo";

// NXTDeal Hub console (2026-07-16) -- Sam: "we need to flesh out the hub website. it
// should have the same look and feel as regular NXTDeal, but it has 3 purposes, to
// set up and deploy new dealerships on their own instance of NXTDeal, to provide
// analytics across the entire system, to show the health of the server(s), network,
// dealerships, etc - and as the center of the NXTDeal network, so the gathering truth
// sorce of dealership metrics."
//
// This is the one real page behind hub.dealeros.xyz (NEXT_PUBLIC_DEPLOYMENT_MODE=hub,
// see middleware.ts) -- a DIFFERENT deployment from every dealer's own NXTDeal
// instance, talking to a DIFFERENT backend (hub/app.py, via lib/hubApi.ts, not
// backend/api/app.py's lib/api.ts). Reuses the same brand chrome (BrandRibbon, dark
// theme, font-brand headers) as the rest of NXTDeal per Sam's "same look and feel"
// ask, but this is deliberately NOT built on useMenuDash/MenuDashPanel -- those are
// wired to a per-employee role/session model (core/permissions.py's six dealer roles)
// that has no meaning here; the Hub has its own separate username/password login
// (POST /hub/auth/login -> a bearer token, see lib/hubApi.ts).
//
// Four tabs today: NOC (unified status board), Dealer Management (provisioning +
// the full 12-item tenant-lifecycle console), Network (cross-network analytics, the
// anonymized aggregate from hub/core/network_analytics.py), and "Infrastructure &
// Platform Ops" (renamed 2026-07-19 from the old flat "Server Health" tab -- the same
// "health" Tab key, now rendering components/hub/InfrastructureSection.tsx's real
// 12-item Azure-Status-Page-style menu; see that component's own docstring). "Deploy
// new dealerships on their own instance" is scaffolding + manual-steps guidance, not
// real Coolify automation -- see docs/DEPLOYMENT.md, a decision Sam confirmed
// explicitly rather than this session guessing at real infra automation.

import { useEffect, useState } from "react";
import { BrandRibbon, AngledGlow } from "@/components/BrandAngles";
import {
  getStoredHubToken,
  hubLogin,
  hubWhoami,
  hubChangePassword,
  hubLogout,
  setHubUnauthorizedHandler,
  HubApiError,
  getNetworkOverview,
  collectNetworkSnapshots,
  getNetworkAnalytics,
  getNocStatusBoard,
  type NetworkOverview,
  type NetworkCollectResult,
  type NetworkAnalytics,
  type NocStatusBoard,
  type NocAlertSeverity,
} from "@/lib/hubApi";
import DealerManagementSection, { DealershipLabManagement } from "@/components/hub/DealerManagementSection";
import InfrastructureSection from "@/components/hub/InfrastructureSection";
import NetworkConnectSection from "@/components/hub/NetworkConnectSection";
import CodeAuditorSection from "@/components/hub/CodeAuditorSection";
import AiKillSwitchSection from "@/components/hub/AiKillSwitchSection";

type Tab = "noc" | "dealers" | "network" | "health" | "networkConnect" | "codeAuditor" | "aiKillSwitch";

// loading  -- validating a pre-existing sessionStorage token via whoami
// login    -- show the username/password gate
// changePassword -- logged in but must_change_password is true; force the change first
// ready    -- console is usable
type AuthState = "loading" | "login" | "changePassword" | "ready";

export default function HubConsolePage() {
  const [authState, setAuthState] = useState<AuthState>("loading");
  const [tab, setTab] = useState<Tab>("network");

  // Login gate
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loginError, setLoginError] = useState("");
  const [loggingIn, setLoggingIn] = useState(false);
  const [sessionExpired, setSessionExpired] = useState(false);

  // Forced change-password gate
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwError, setPwError] = useState("");
  const [changingPw, setChangingPw] = useState(false);

  // Any 401 from any console call (including the section components that swallow
  // their own errors) bounces the whole console back to the login gate.
  useEffect(() => {
    setHubUnauthorizedHandler(() => {
      setAuthState("login");
      setSessionExpired(true);
    });
    return () => setHubUnauthorizedHandler(null);
  }, []);

  // Revalidate a token left in this tab's sessionStorage from a prior view.
  useEffect(() => {
    if (!getStoredHubToken()) {
      setAuthState("login");
      return;
    }
    hubWhoami()
      .then((who) => {
        setAuthState(who.must_change_password ? "changePassword" : "ready");
      })
      .catch(() => {
        // hubFetch already cleared the rejected token and, via the handler above,
        // may have flipped us to "login" -- make sure we land there regardless.
        setAuthState("login");
      });
  }, []);

  async function handleLogin() {
    if (!username.trim() || !password) return;
    setLoggingIn(true);
    setLoginError("");
    try {
      const result = await hubLogin(username.trim(), password);
      setSessionExpired(false);
      setPassword("");
      setAuthState(result.must_change_password ? "changePassword" : "ready");
    } catch (error) {
      setLoginError(
        error instanceof HubApiError ? error.message : "Unable to reach the Hub."
      );
    } finally {
      setLoggingIn(false);
    }
  }

  async function handleChangePassword() {
    if (!oldPassword || !newPassword) return;
    if (newPassword !== confirmPassword) {
      setPwError("New passwords do not match.");
      return;
    }
    setChangingPw(true);
    setPwError("");
    try {
      await hubChangePassword(oldPassword, newPassword);
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setAuthState("ready");
    } catch (error) {
      if (error instanceof HubApiError && error.status === 401) {
        setAuthState("login");
        setSessionExpired(true);
      } else {
        setPwError(
          error instanceof HubApiError ? error.message : "Unable to reach the Hub."
        );
      }
    } finally {
      setChangingPw(false);
    }
  }

  function handleLogout() {
    hubLogout();
    setUsername("");
    setPassword("");
    setLoginError("");
    setSessionExpired(false);
    setTab("noc");
    setAuthState("login");
  }

  return (
    <div className={`nxt-hub ${authState === "login" || authState === "changePassword" ? "nxt-cinematic" : ""} h-[100dvh] overflow-hidden text-white flex flex-col`}>
      <header className="nxt-hub-header border-b border-white/10 px-4 md:px-8 py-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          {authState === "ready" && <BrandLogo />}<h1 className="text-sm font-brand font-semibold tracking-tight">Hub</h1>
          <span className="hidden lg:inline text-[10px] uppercase tracking-[0.3em] text-zinc-400">
            Dealership Control Center
          </span>
        </div>
        {(authState === "ready" || authState === "changePassword") && (
          <button
            onClick={handleLogout}
            className="text-xs text-zinc-500 hover:text-white transition uppercase tracking-wide"
          >
            Log Out
          </button>
        )}
      </header>

      <BrandRibbon height={5} />

      <main className="relative flex-1 overflow-hidden flex flex-col">
        {authState === "loading" ? (
          <div className="relative flex-1 flex items-center justify-center px-8">
            <div className="text-sm text-zinc-500">Loading…</div>
          </div>
        ) : authState === "login" ? (
          <div className="relative flex-1 flex items-center justify-center px-8">
            <AngledGlow color="blue" className="absolute -left-32 top-0 w-[420px] h-full" />
            <AngledGlow color="red" className="absolute -right-24 bottom-0 w-[360px] h-2/3" />

            <div className="relative z-10 w-full max-w-md bg-zinc-900/95 backdrop-blur-sm border border-zinc-800 rounded-2xl p-8">
              <h2 className="text-2xl font-brand font-bold tracking-tight mb-2">
                Hub Sign In
              </h2>
              <p className="text-sm text-zinc-400 mb-6">
                Sign in with your NXTDeal staff username and password. Access your network, dealerships, and platform operations.
              </p>

              {sessionExpired && !loginError && (
                <div className="mb-4 text-sm text-amber-400">
                  Session expired, please log in.
                </div>
              )}
              {loginError && <div className="mb-4 text-sm text-red-400">{loginError}</div>}

              <input
                type="text"
                placeholder="Username" aria-label="Username"
                value={username}
                autoComplete="username"
                onChange={(e) => setUsername(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                className="w-full h-12 px-4 mb-4 rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none"
              />

              <input
                type="password"
                placeholder="Password" aria-label="Password"
                value={password}
                autoComplete="current-password"
                onChange={(e) => setPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleLogin()}
                className="w-full h-12 px-4 mb-4 rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none"
              />

              <button
                onClick={handleLogin}
                disabled={loggingIn}
                className="w-full h-12 brand-cta font-brand font-bold uppercase tracking-wide text-sm transition disabled:opacity-50"
              >
                {loggingIn ? "Signing In…" : "Sign In"}
              </button>
            </div>
          </div>
        ) : authState === "changePassword" ? (
          <div className="relative flex-1 flex items-center justify-center px-8">
            <AngledGlow color="blue" className="absolute -left-32 top-0 w-[420px] h-full" />
            <AngledGlow color="red" className="absolute -right-24 bottom-0 w-[360px] h-2/3" />

            <div className="relative z-10 w-full max-w-md bg-zinc-900/95 backdrop-blur-sm border border-zinc-800 rounded-2xl p-8">
              <h2 className="text-2xl font-brand font-bold tracking-tight mb-2">
                Change Your Password
              </h2>
              <p className="text-sm text-zinc-400 mb-6">
                Your account requires a new password before you can use the console.
              </p>

              {pwError && <div className="mb-4 text-sm text-red-400">{pwError}</div>}

              <input
                type="password"
                placeholder="Current password"
                value={oldPassword}
                autoComplete="current-password"
                onChange={(e) => setOldPassword(e.target.value)}
                className="w-full h-12 px-4 mb-4 rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none"
              />

              <input
                type="password"
                placeholder="New password"
                value={newPassword}
                autoComplete="new-password"
                onChange={(e) => setNewPassword(e.target.value)}
                className="w-full h-12 px-4 mb-4 rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none"
              />

              <input
                type="password"
                placeholder="Confirm new password"
                value={confirmPassword}
                autoComplete="new-password"
                onChange={(e) => setConfirmPassword(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleChangePassword()}
                className="w-full h-12 px-4 mb-4 rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none"
              />

              <button
                onClick={handleChangePassword}
                disabled={changingPw}
                className="w-full h-12 brand-cta font-brand font-bold uppercase tracking-wide text-sm transition disabled:opacity-50"
              >
                {changingPw ? "Saving…" : "Set New Password"}
              </button>
            </div>
          </div>
        ) : (
          <>
            <div className="px-8 pt-4 flex gap-2">
              {(
                [
                  ["noc", "NOC"],
                  ["dealers", "Dealer Management"],
                  ["network", "Dealership Lab"],

                  ["health", "Infrastructure & Platform Ops"],
                  ["codeAuditor", "Code Auditor"],
                  ["aiKillSwitch", "AI Kill Switch"],
                ] as [Tab, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={
                    tab === key
                      ? "bg-zinc-200 text-black font-medium px-4 py-2 rounded-t-lg text-sm"
                      : "bg-zinc-900 text-zinc-400 hover:text-white px-4 py-2 rounded-t-lg text-sm transition"
                  }
                >
                  {label}
                </button>
              ))}
            </div>

            <div className="flex-1 overflow-y-auto px-8 py-6 bg-zinc-950/40">
              {tab === "noc" && <NocTab onNavigate={setTab} />}
              {tab === "dealers" && <DealerManagementSection />}
              {tab === "network" && <DealershipLabManagement />}
              {tab === "networkConnect" && <NetworkConnectSection />}
              {tab === "health" && <InfrastructureSection />}
              {tab === "codeAuditor" && <CodeAuditorSection />}
              {tab === "aiKillSwitch" && <AiKillSwitchSection />}
            </div>
          </>
        )}
      </main>
      <footer className="shrink-0 border-t border-white/5 px-4 py-2 text-[10px] text-zinc-500">© 2026 Chronos. All rights reserved.</footer>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared bits
// ---------------------------------------------------------------------------

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

function errorMessage(error: unknown): string {
  return error instanceof HubApiError ? error.message : "Unable to reach the Hub.";
}

// ---------------------------------------------------------------------------
// NOC (Network Operations Center) tab -- the new default landing view. One
// unified real-time status board composing the same real signals the
// Dealers/Network/Server Health tabs already surface separately, plus a real
// transparent Alerts feed (hub/core/noc.py) -- not a new monitoring engine, a
// real composition layer. See that module's own docstring for the deliberate
// privacy boundary this respects (no per-dealer network-coverage alert, since
// a collected snapshot is only ever keyed by an anonymous pseudonym).
// ---------------------------------------------------------------------------

const OVERALL_STATUS_STYLE: Record<NocStatusBoard["overall_status"], { bg: string; border: string; text: string; label: string }> = {
  critical: { bg: "bg-red-950/30", border: "border-red-800", text: "text-red-300", label: "Critical" },
  warning: { bg: "bg-amber-950/30", border: "border-amber-800", text: "text-amber-300", label: "Warning" },
  healthy: { bg: "bg-emerald-950/30", border: "border-emerald-800", text: "text-emerald-300", label: "Healthy" },
};

const ALERT_SEVERITY_STYLE: Record<NocAlertSeverity, { dot: string; text: string; label: string }> = {
  critical: { dot: "#EE3C25", text: "text-red-300", label: "Critical" },
  warning: { dot: "#F4C300", text: "text-amber-300", label: "Warning" },
  info: { dot: "#8AA0B0", text: "text-zinc-400", label: "Info" },
};

function NocTab({ onNavigate }: { onNavigate: (tab: Tab) => void }) {
  const [board, setBoard] = useState<NocStatusBoard | null>(null);
  const [error, setError] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  async function load() {
    setRefreshing(true);
    try {
      setBoard(await getNocStatusBoard());
      setError("");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setRefreshing(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  const statusStyle = board ? OVERALL_STATUS_STYLE[board.overall_status] : null;

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div
        className={`relative overflow-hidden rounded-lg border p-5 mb-6 ${
          statusStyle ? `${statusStyle.bg} ${statusStyle.border}` : "bg-zinc-900 border-zinc-800"
        }`}
      >
        <div className="flex items-center justify-between">
          <div>
            <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">Overall Network Status</div>
            <div className={`text-2xl font-brand font-bold ${statusStyle?.text ?? ""}`}>
              {board ? statusStyle?.label : "Loading…"}
            </div>
          </div>
          <button
            onClick={load}
            disabled={refreshing}
            className="bg-zinc-200 text-black font-medium px-4 py-2 rounded text-xs uppercase tracking-wide disabled:opacity-50"
          >
            {refreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
        {board && <p className="text-[11px] text-zinc-500 mt-3 leading-relaxed">{board.note}</p>}
      </div>

      <div className="grid grid-cols-4 gap-3 mb-6">
        <KpiCard label="Total Dealers" value={board?.dealer_counts.total ?? "..."} />
        <KpiCard label="Reachable" value={board?.reachability.reachable ?? "..."} />
        <KpiCard label="Unreachable" value={board?.reachability.unreachable ?? "..."} />
        <KpiCard
          label="Anonymized Snapshots"
          value={board?.network_coverage.dealers_contributing_anonymized_snapshots ?? "..."}
        />
      </div>

      <div className="flex items-center justify-between mb-3">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">
          Alerts
          {board && (
            <span className="ml-2 text-zinc-500 normal-case tracking-normal font-normal">
              {board.alert_counts.critical} critical · {board.alert_counts.warning} warning ·{" "}
              {board.alert_counts.info} info
            </span>
          )}
        </h3>
      </div>

      <div className="space-y-2 mb-6">
        {board?.alerts.length === 0 && (
          <div className="text-sm text-zinc-500 bg-zinc-900 rounded-lg p-5">
            No active alerts -- every registered dealer is reachable and configured.
          </div>
        )}
        {(board?.alerts ?? []).map((alert, i) => {
          const style = ALERT_SEVERITY_STYLE[alert.severity];
          return (
            <div key={i} className="bg-zinc-900 rounded-lg p-4 flex items-start gap-3">
              <span className="h-2.5 w-2.5 rounded-full mt-1.5 shrink-0" style={{ background: style.dot }} />
              <div className="flex-1 min-w-0">
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <div className="text-sm font-medium">{alert.title}</div>
                  <span className={`text-[10px] uppercase tracking-wide ${style.text}`}>{style.label}</span>
                </div>
                <div className="text-xs text-zinc-500 mt-1">{alert.reason}</div>
                {alert.dealer_id && (
                  <button
                    onClick={() => onNavigate("dealers")}
                    className="text-[10px] text-zinc-500 hover:text-white underline mt-1"
                  >
                    View {dealerDisplayName(alert.dealer_name)} on the Dealers tab →
                  </button>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="grid grid-cols-3 gap-3">
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Dealer Status</div>
          <div className="text-xs text-zinc-400 space-y-1">
            <div>Active: {board?.dealer_counts.active ?? "..."}</div>
            <div>Provisioning: {board?.dealer_counts.provisioning ?? "..."}</div>
            <div>Suspended: {board?.dealer_counts.suspended ?? "..."}</div>
          </div>
        </div>
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Network Opt-In</div>
          <div className="text-xs text-zinc-400">
            {board?.dealer_counts.network_opted_in_active ?? "..."} active dealer(s) opted into anonymized network
            analytics.
          </div>
        </div>
        <div className="bg-zinc-900 rounded-lg p-4">
          <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">Quick Links</div>
          <div className="flex flex-col gap-1.5">
            <button onClick={() => onNavigate("dealers")} className="text-xs text-left text-zinc-400 hover:text-white underline">
              Dealers →
            </button>
            <button onClick={() => onNavigate("network")} className="text-xs text-left text-zinc-400 hover:text-white underline">
              Dealership Lab →
            </button>
            <button onClick={() => onNavigate("health")} className="text-xs text-left text-zinc-400 hover:text-white underline">
              Infrastructure & Platform Ops →
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Network tab
// ---------------------------------------------------------------------------

function NetworkTab() {
  const [overview, setOverview] = useState<NetworkOverview | null>(null);
  const [analytics, setAnalytics] = useState<NetworkAnalytics | null>(null);
  const [collectResult, setCollectResult] = useState<NetworkCollectResult | null>(null);
  const [error, setError] = useState("");
  const [collecting, setCollecting] = useState(false);

  async function load() {
    try {
      const [o, a] = await Promise.all([getNetworkOverview(), getNetworkAnalytics()]);
      setOverview(o);
      setAnalytics(a);
    } catch (e) {
      setError(errorMessage(e));
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function runCollection() {
    setCollecting(true);
    setError("");
    try {
      const res = await collectNetworkSnapshots();
      setCollectResult(res);
      await load();
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setCollecting(false);
    }
  }

  return (
    <div>
      {error && <ErrorBanner message={error} />}

      <div className="grid grid-cols-4 gap-3 mb-6">
        <KpiCard label="Total Dealers" value={overview?.total_dealers ?? "..."} />
        <KpiCard label="Opted-In" value={overview?.opted_in_dealers ?? "..."} />
        <KpiCard label="Anonymized Snapshots" value={analytics?.dealers_contributing ?? "..."} />
        <KpiCard
          label="Unreachable This Pass"
          value={overview?.dealers_unreachable.length ?? 0}
        />
      </div>

      <div className="flex items-center justify-between mb-3">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">
          Network Intelligence
        </h3>
        <button
          onClick={runCollection}
          disabled={collecting}
          className="brand-cta font-brand font-bold uppercase tracking-wide text-xs px-5 py-2.5 disabled:opacity-50"
        >
          {collecting ? "Collecting..." : "Collect Anonymized Snapshots Now"}
        </button>
      </div>

      {collectResult && (
        <div className="mb-4 text-xs text-zinc-400 bg-zinc-900 rounded-lg px-4 py-3">
          {collectResult.dealers_reporting} of {collectResult.opted_in_dealers} opted-in
          dealer(s) reported this pass. {collectResult.total_snapshots_stored} snapshot(s)
          on file.
        </div>
      )}

      <div className="bg-zinc-900 rounded-lg p-5 mb-4">
        <p className="text-xs text-zinc-500 leading-relaxed">
          Every figure below is a real aggregate over anonymized, privacy-bucketed KPI
          snapshots pulled from each opted-in dealer&apos;s own instance -- each
          dealer&apos;s snapshot is tagged with a locally generated, one-way pseudonym
          that is never derived from (or linkable back to) their dealer_id, name, or
          contact info. See core/network_collector.py&apos;s docstring for the full
          design. With very few dealers reporting, treat this as illustrative, not a
          real industry benchmark yet.
        </p>
      </div>

      {analytics && Object.keys(analytics.departments).length === 0 && (
        <div className="text-sm text-zinc-500 bg-zinc-900 rounded-lg p-5">
          No anonymized snapshots collected yet -- click &quot;Collect Anonymized
          Snapshots Now&quot; above once at least one dealer has a real api_base_url on
          file.
        </div>
      )}

      {analytics &&
        Object.entries(analytics.departments).map(([deptKey, kpis]) => (
          <div key={deptKey} className="mb-6">
            <h4 className="text-sm font-brand font-bold uppercase tracking-wide text-zinc-400 mb-2">
              {deptKey}
            </h4>
            <div className="grid grid-cols-3 gap-3">
              {Object.entries(kpis).map(([kpiKey, stat]) => (
                <div key={kpiKey} className="bg-zinc-900 rounded-lg p-4">
                  <div className="text-[11px] uppercase tracking-wide text-zinc-500 mb-1">
                    {stat.label}
                  </div>
                  <div className="text-xl font-semibold mb-1">
                    {stat.average ?? "--"}
                  </div>
                  <div className="text-[11px] text-zinc-500">
                    median {stat.median ?? "--"} · range {stat.min ?? "--"}-{stat.max ?? "--"}
                    {" · n="}
                    {stat.sample_size}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
    </div>
  );
}

// Server Health tab was replaced 2026-07-19 by <InfrastructureSection /> --
// see components/hub/InfrastructureSection.tsx (Infrastructure & Platform
// Operations rebuild, slice 1 of 4). The same reachability data it used to
// render here now surfaces as part of that component's real Overview panel
// (hub/core/infra_overview.py's "dealers" field is the identical
// hub/core/server_health.py payload, just composed alongside real topology
// + a real Platform Status Board rather than shown alone).
