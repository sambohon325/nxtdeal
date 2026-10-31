"use client";
import { WorkButton , WorkStat} from "./WorkspaceUi";

// Administration's "Compliance & Governance" item (Administration Control
// Center rebuild, continuing 2026-07-18). Ties together core/compliance.py's
// cited-federal-rules alert engine and core/permissions_registry.py's real
// tier-gated cross-department ApprovalRequest hierarchy into one workspace,
// plus the pre-existing content approval queue (campaigns/assets/websites/
// financing) and escalation-rules dashboard, and a governance-scoped slice
// of the audit log. Full permission-override management and the full
// create/approve/reject/cancel approval-request workflow still live on
// Roles & Permissions (components/RolesPermissionsBoard.tsx) -- this board
// is deliberately a reporting/oversight surface over that same real data,
// not a second parallel place to take those actions.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getGovernanceMenuOverview,
  getComplianceGovernanceSummary,
  getApprovalHierarchySummary,
  getGovernanceActionLog,
  type GovernanceMenuOverview,
  type ComplianceGovernanceSummary,
  type ApprovalHierarchySummary,
  type GovernanceActionLog,
  type GovernanceCategory,
} from "@/lib/governance";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function pct(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `${Math.round(v * 100)}%`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function CountBadge({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex items-center justify-between text-xs px-2 py-1 rounded border border-zinc-800">
      <span className="text-zinc-300">{label}</span>
      <span className="text-zinc-500 ml-2">{value}</span>
    </div>
  );
}

const CATEGORY_TABS: { key: GovernanceCategory | "all"; label: string }[] = [
  { key: "all", label: "All" },
  { key: "Permissions", label: "Permissions" },
  { key: "Approvals", label: "Approvals" },
  { key: "Compliance", label: "Compliance" },
];

export function GovernanceBoard({ theme, initialTab = "overview" }: { theme: Theme; initialTab?: "overview" | "compliance" | "approvals" | "log" }) {
  const [tab, setTab] = useState<"overview" | "compliance" | "approvals" | "log">(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);
  const [menuData, setMenuData] = useState<GovernanceMenuOverview | null>(null);
  const [compliance, setCompliance] = useState<ComplianceGovernanceSummary | null>(null);
  const [approvals, setApprovals] = useState<ApprovalHierarchySummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [logCategory, setLogCategory] = useState<GovernanceCategory | "all">("all");
  const [log, setLog] = useState<GovernanceActionLog | null>(null);
  const [logLoading, setLogLoading] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getGovernanceMenuOverview(), getComplianceGovernanceSummary(), getApprovalHierarchySummary()])
      .then(([menu, comp, appr]) => {
        setMenuData(menu);
        setCompliance(comp);
        setApprovals(appr);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Compliance & Governance data."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  useEffect(() => {
    if (tab !== "log") return;
    setLogLoading(true);
    getGovernanceActionLog({ category: logCategory === "all" ? undefined : logCategory, limit: 100 })
      .then(setLog)
      .catch(() => setLog(null))
      .finally(() => setLogLoading(false));
  }, [tab, logCategory]);

  const health = menuData?.governance_health;
  const approvalQueue = menuData?.approval_queue;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Governance Health" value={health?.blended_health_score != null ? pct(health.blended_health_score) : "—"} color={RIBBON[0]} />
        <Kpi theme={theme} label="Open Compliance Alerts" value={String(compliance?.by_status?.open ?? 0)} color={RIBBON[3]} />
        <Kpi theme={theme} label="Pending Approval Requests" value={String(approvals?.by_status?.pending ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Approval Throughput" value={pct(approvals?.throughput_rate)} color={RIBBON[1]} />
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {([
          ["overview", "Overview"],
          ["compliance", "Compliance"],
          ["approvals", "Approval Hierarchy"],
          ["log", "Governance Action Log"],
        ] as const).map(([key, label]) => (
          <WorkButton data-work-view aria-pressed={tab === key} type="submit"
            key={key}
            onClick={() => setTab(key)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${tab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {label}
          </WorkButton>
        ))}
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "overview" ? (
          <div className="space-y-4">
            <div className="text-xs text-zinc-500">
              A real blend of two already-real rates — compliance resolution rate and approval
              throughput rate — into one governance health figure. Basis: {health?.basis || "n/a"}.
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Content Approval Queue
              </div>
              <div className="grid grid-cols-4 gap-1.5">
                <CountBadge label="Campaigns" value={approvalQueue?.campaigns?.count ?? 0} />
                <CountBadge label="Assets" value={approvalQueue?.assets?.count ?? 0} />
                <CountBadge label="Websites" value={approvalQueue?.websites?.count ?? 0} />
                <CountBadge label="Financing" value={approvalQueue?.financing?.count ?? 0} />
              </div>
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Escalation Rules
              </div>
              <pre className="text-xs p-2 rounded border border-zinc-800 overflow-x-auto whitespace-pre-wrap">
                {JSON.stringify(menuData?.escalation_rules ?? {}, null, 2)}
              </pre>
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Not Yet Tracked (honest gaps — no fabricated data)
              </div>
              <div className="space-y-1">
                {Object.entries(menuData?.not_yet_tracked || {}).map(([k, v]) => (
                  <div key={k} className="text-xs px-2 py-1 rounded border border-zinc-800">
                    <span className="text-zinc-300">{k}</span>
                    <span className="text-zinc-500"> — {v}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : tab === "compliance" ? (
          <div className="space-y-4">
            <div className="text-xs text-zinc-500">{compliance?.notice}</div>
            <div className="grid grid-cols-3 gap-1.5">
              {Object.entries(compliance?.by_status || {}).map(([status, count]) => (
                <CountBadge key={status} label={status} value={count} />
              ))}
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="px-2 py-1.5 rounded border border-zinc-800">
                <span className="text-zinc-500">Resolution Rate: </span>
                <span className="text-zinc-200">{pct(compliance?.resolution_rate)}</span>
              </div>
              <div className="px-2 py-1.5 rounded border border-zinc-800">
                <span className="text-zinc-500">Avg Resolution Time: </span>
                <span className="text-zinc-200">
                  {compliance?.avg_resolution_hours != null ? `${compliance.avg_resolution_hours} hrs` : "—"}
                </span>
              </div>
            </div>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Violations By Law
              </div>
              <div className="space-y-1">
                {Object.entries(compliance?.by_law || {})
                  .sort((a, b) => b[1] - a[1])
                  .map(([law, count]) => (
                    <CountBadge key={law} label={law} value={count} />
                  ))}
                {Object.keys(compliance?.by_law || {}).length === 0 && (
                  <div className="text-xs text-zinc-500">No violations recorded.</div>
                )}
              </div>
            </div>
          </div>
        ) : tab === "approvals" ? (
          <div className="space-y-4">
            <div className="text-xs text-zinc-500">
              Real ApprovalRequest data across every tier-gated chain (permission-change/
              role-change/policy-exception/expense). To create, approve, reject, or cancel a
              request, use Roles &amp; Permissions&apos; own Approval Hierarchy tab.
            </div>
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="px-2 py-1.5 rounded border border-zinc-800">
                <span className="text-zinc-500">Throughput Rate: </span>
                <span className="text-zinc-200">{pct(approvals?.throughput_rate)}</span>
              </div>
              <div className="px-2 py-1.5 rounded border border-zinc-800">
                <span className="text-zinc-500">Avg Turnaround: </span>
                <span className="text-zinc-200">
                  {approvals?.avg_turnaround_hours != null ? `${approvals.avg_turnaround_hours} hrs` : "—"}
                </span>
              </div>
            </div>
            <div className="grid grid-cols-2 gap-4">
              <div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">By Status</div>
                <div className="space-y-1">
                  {Object.entries(approvals?.by_status || {}).map(([status, count]) => (
                    <CountBadge key={status} label={status} value={count} />
                  ))}
                </div>
              </div>
              <div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">By Chain</div>
                <div className="space-y-1">
                  {Object.entries(approvals?.by_chain || {}).map(([chain, count]) => (
                    <CountBadge key={chain} label={chain} value={count} />
                  ))}
                </div>
              </div>
            </div>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Pending Requests ({approvals?.pending_requests.length ?? 0})
              </div>
              <div className="space-y-1">
                {(approvals?.pending_requests || []).map((r) => (
                  <div key={r.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800">
                    <span className="text-zinc-200">{r.subject}</span>
                    <div className="text-xs text-zinc-500 mt-0.5">
                      {r.chain_label} · step {r.current_step_index + 1}/{r.steps.length} · requested by{" "}
                      {r.requested_by} · {fmt(r.created_at)}
                    </div>
                  </div>
                ))}
                {(approvals?.pending_requests || []).length === 0 && (
                  <div className="text-xs text-zinc-500">No pending approval requests.</div>
                )}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-xs text-zinc-500">
              A governance-scoped slice of the platform-wide audit log — every permission
              override granted/revoked, every approval-chain step taken, and every compliance
              alert created/resolved/overridden.
            </div>
            <div className="flex items-center gap-1.5">
              {CATEGORY_TABS.map(({ key, label }) => (
                <WorkButton type="submit"
                  key={key}
                  onClick={() => setLogCategory(key)}
                  className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${logCategory === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
                >
                  {label}
                </WorkButton>
              ))}
            </div>
            {logLoading ? (
              <div className="text-sm text-zinc-500">Loading…</div>
            ) : (
              <div className="space-y-1">
                <div className="text-xs text-zinc-500">
                  {log?.total_matches ?? 0} matching event(s), showing {log?.returned ?? 0}
                </div>
                {(log?.events || []).map((e) => (
                  <div key={e.id} className="flex items-start justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                    <div className="min-w-0">
                      <span className="text-zinc-200">{e.summary}</span>
                      <div className="text-xs text-zinc-500 mt-0.5">
                        <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 mr-1.5">{e.category}</span>
                        {e.event_type} · {e.actor} {e.entity_id ? `→ ${e.entity_id}` : ""} · {fmt(e.timestamp)}
                      </div>
                    </div>
                  </div>
                ))}
                {(log?.events || []).length === 0 && (
                  <div className="text-xs text-zinc-500">No matching events.</div>
                )}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
