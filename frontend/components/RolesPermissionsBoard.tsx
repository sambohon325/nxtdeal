"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";

// Administration's "Roles & Permissions" item (Administration Control Center
// rebuild, first slice, 2026-07-18) -- Sam's own "one of the most important
// modules." A real ADDITIVE layer on top of the platform's 6 core roles: a
// granular permission catalog (each permission's role default mirroring an
// already-real ACL set elsewhere in this codebase), per-employee overrides,
// field-level security (already wired into Customer 360's CreditScore /
// Credit Applications' ssn_last4 on the backend -- this board doesn't need to
// re-implement that, only manage the override that controls it), and a real
// Employee -> Manager -> Executive approval-hierarchy engine off each real
// Employee.Title (core/bot_tasks.py's infer_tier() -- no fabricated "Director"
// tier, since this codebase has no Title-keyword data to honestly distinguish
// one; a director-titled employee already collapses into "manager").
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";
import {
  getPermissionCatalog,
  getTierDistribution,
  listAllOverrides,
  setPermissionOverride,
  revokeOverride,
  listApprovalChains,
  listApprovalRequests,
  createApprovalRequest,
  approveApprovalStep,
  rejectApprovalStep,
  cancelApprovalRequest,
  type PermissionCatalog,
  type TierDistribution,
  type PermissionOverride,
  type ApprovalChain,
  type ApprovalRequest,
} from "@/lib/rolesPermissions";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const TIER_TONE: Record<string, string> = {
  staff: "bg-zinc-800 text-zinc-300",
  manager: "bg-blue-950/40 text-blue-300",
  executive: "bg-amber-950/40 text-amber-300",
};

const STATUS_TONE: Record<string, string> = {
  pending: "bg-amber-950/40 text-amber-300",
  approved: "bg-emerald-950/40 text-emerald-300",
  rejected: "bg-red-950/40 text-red-300",
  cancelled: "bg-zinc-800 text-zinc-400",
};

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function Btn({ onClick, children, disabled, tone }: { onClick: () => void; children: React.ReactNode; disabled?: boolean; tone?: "primary" | "danger" }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      className={`text-xs px-2.5 py-1 rounded font-medium disabled:opacity-40 ${
        tone === "danger" ? "bg-red-900/60 text-red-200 hover:bg-red-900" : tone === "primary" ? "bg-zinc-200 text-black hover:bg-white" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
      }`}
    >
      {children}
    </WorkButton>
  );
}

function Input({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <WorkField label={placeholder || "Value"}><WorkInput
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 w-full"
    /></WorkField>
  );
}

export function RolesPermissionsBoard({ theme, initialTab = "matrix" }: { theme: Theme; initialTab?: "matrix" | "overrides" | "approvals" }) {
  const session = getSession();
  const [tab, setTab] = useState<"matrix" | "overrides" | "approvals">(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [tiers, setTiers] = useState<TierDistribution | null>(null);
  const [overrides, setOverrides] = useState<PermissionOverride[]>([]);
  const [chains, setChains] = useState<ApprovalChain[]>([]);
  const [requests, setRequests] = useState<ApprovalRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [grantEmployeeId, setGrantEmployeeId] = useState("");
  const [grantKey, setGrantKey] = useState("");
  const [grantReason, setGrantReason] = useState("");

  const [reqChain, setReqChain] = useState("");
  const [reqSubject, setReqSubject] = useState("");
  const [reqDetails, setReqDetails] = useState("");
  const [approvalsView, setApprovalsView] = useState<"all" | "mine" | "pending_for_me">("pending_for_me");

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getPermissionCatalog(), getTierDistribution(), listAllOverrides(), listApprovalChains()])
      .then(([c, t, o, ch]) => {
        setCatalog(c);
        setTiers(t);
        setOverrides(o.overrides.filter((x) => x.active));
        setChains(ch.chains);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Roles & Permissions data."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  function refreshRequests(view: typeof approvalsView) {
    listApprovalRequests(
      view === "mine" ? { mine: true } : view === "pending_for_me" ? { pendingForMe: true } : {}
    )
      .then((r) => setRequests(r.requests))
      .catch(() => setRequests([]));
  }

  useEffect(() => {
    if (tab === "approvals") refreshRequests(approvalsView);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, approvalsView]);

  async function handleGrant(granted: boolean) {
    if (!grantEmployeeId.trim() || !grantKey) return;
    try {
      await setPermissionOverride(grantEmployeeId.trim().toUpperCase(), grantKey, granted, grantReason);
      setMessage(`${granted ? "Granted" : "Revoked"} '${grantKey}' for ${grantEmployeeId.trim().toUpperCase()}`);
      setGrantEmployeeId("");
      setGrantReason("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to set override.");
    }
  }

  async function handleDeactivate(id: string) {
    try {
      await revokeOverride(id);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to deactivate override.");
    }
  }

  async function handleCreateRequest() {
    if (!reqChain || !reqSubject.trim()) return;
    try {
      await createApprovalRequest(reqChain, reqSubject.trim(), reqDetails);
      setReqSubject("");
      setReqDetails("");
      setMessage("Approval request created.");
      refreshRequests(approvalsView);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create approval request.");
    }
  }

  async function handleApprove(id: string) {
    try {
      await approveApprovalStep(id);
      refreshRequests(approvalsView);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to approve this step.");
    }
  }

  async function handleReject(id: string) {
    const reason = window.prompt("Rejection reason?");
    if (!reason) return;
    try {
      await rejectApprovalStep(id, reason);
      refreshRequests(approvalsView);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to reject this step.");
    }
  }

  async function handleCancel(id: string) {
    try {
      await cancelApprovalRequest(id);
      refreshRequests(approvalsView);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to cancel this request.");
    }
  }

  const pendingCount = requests.filter((r) => r.status === "pending").length;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Permissions Tracked" value={String(catalog?.categories.reduce((n, c) => n + c.permissions.length, 0) || 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Active Overrides" value={String(overrides.length)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Managers/Execs" value={String((tiers?.manager.count || 0) + (tiers?.executive.count || 0))} color={RIBBON[2]} />
        <Kpi theme={theme} label="Pending Approvals" value={tab === "approvals" ? String(pendingCount) : "—"} color={RIBBON[3]} />
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {([
          ["matrix", "Permission Matrix"],
          ["overrides", "Overrides & Field Security"],
          ["approvals", "Approval Hierarchy"],
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
      {message && <div className="mx-4 mt-2 text-xs text-emerald-400">{message}</div>}

      <div className="flex-1 p-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "matrix" ? (
          <div className="space-y-4">
            <div className="text-xs text-zinc-500">
              Each permission&apos;s role default mirrors an already-real, already-enforced access
              rule elsewhere in this codebase — this is an additive layer on top of the platform&apos;s
              6 core roles ({catalog?.roles.join(", ")}), not a replacement of them.
            </div>
            {catalog?.categories.map((cat) => (
              <div key={cat.category}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">{cat.category}</div>
                <div className="space-y-1">
                  {cat.permissions.map((p) => (
                    <div key={p.key} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                      <div>
                        <span className="text-zinc-200">{p.label}</span>
                        <span className="text-zinc-600 ml-2">{p.key}</span>
                      </div>
                      <div className="flex gap-1">
                        {p.roles?.map((r) => (
                          <span key={r} className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 text-xs">{r}</span>
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ))}

            <div className="grid grid-cols-3 gap-3 pt-2">
              {(["staff", "manager", "executive"] as const).map((tier) => (
                <div key={tier} className="rounded border border-zinc-800 p-2">
                  <div className={`inline-block px-1.5 py-0.5 rounded text-xs mb-1 ${TIER_TONE[tier]}`}>{tier}</div>
                  <div className="text-lg font-semibold">{tiers?.[tier].count || 0}</div>
                  <div className="text-xs text-zinc-500 space-y-0.5 mt-1 max-h-24 overflow-y-auto">
                    <RecordCollection>{tiers?.[tier].employees.map((e) => (
                      <div key={e.id}>{e.name || e.id} — {e.title}</div>
                    ))}</RecordCollection>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : tab === "overrides" ? (
          <div className="space-y-4">
            <div className="rounded border border-zinc-800 p-3 space-y-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Grant / Revoke a Permission Override</div>
              <div className="grid grid-cols-3 gap-2">
                <Input value={grantEmployeeId} onChange={setGrantEmployeeId} placeholder="EMP-00001" />
                <WorkField label="Permission"><WorkSelect
                  value={grantKey}
                  onChange={(e) => setGrantKey(e.target.value)}
                  className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200"
                >
                  <option value="">Select permission…</option>
                  {catalog?.categories.map((cat) => (
                    <optgroup key={cat.category} label={cat.category}>
                      {cat.permissions.map((p) => (
                        <option key={p.key} value={p.key}>{p.label}</option>
                      ))}
                    </optgroup>
                  ))}
                </WorkSelect></WorkField>
                <Input value={grantReason} onChange={setGrantReason} placeholder="Reason (optional)" />
              </div>
              <div className="flex gap-2">
                <Btn tone="primary" onClick={() => handleGrant(true)} disabled={!grantEmployeeId.trim() || !grantKey}>Grant</Btn>
                <Btn tone="danger" onClick={() => handleGrant(false)} disabled={!grantEmployeeId.trim() || !grantKey}>Revoke (deny)</Btn>
              </div>
              <div className="text-xs text-zinc-600">
                Field-level security (e.g. Customer credit score, Credit Application SSN last-4)
                uses this same mechanism via a synthetic <code>field:EntityType.FieldName</code> key.
              </div>
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Active Overrides ({overrides.length})</div>
              <div className="space-y-1">
                {overrides.length === 0 && <div className="text-xs text-zinc-600">No active overrides.</div>}
                {overrides.map((o) => (
                  <div key={o.id} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                    <div>
                      <span className="text-zinc-200">{o.employee_id}</span>
                      <span className="text-zinc-600 ml-2">{o.permission_key}</span>
                      <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${o.granted ? "bg-emerald-950/40 text-emerald-300" : "bg-red-950/40 text-red-300"}`}>
                        {o.granted ? "granted" : "revoked"}
                      </span>
                      {o.reason && <span className="text-zinc-600 ml-2">— {o.reason}</span>}
                    </div>
                    <Btn onClick={() => handleDeactivate(o.id)}>Deactivate</Btn>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded border border-zinc-800 p-3 space-y-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Request Approval</div>
              <div className="grid grid-cols-2 gap-2">
                <WorkField label="Approval chain"><WorkSelect
                  value={reqChain}
                  onChange={(e) => setReqChain(e.target.value)}
                  className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200"
                >
                  <option value="">Select chain…</option>
                  {chains.map((c) => (
                    <option key={c.key} value={c.key}>{c.label} ({c.steps.join(" → ")})</option>
                  ))}
                </WorkSelect></WorkField>
                <Input value={reqSubject} onChange={setReqSubject} placeholder="Subject" />
              </div>
              <Input value={reqDetails} onChange={setReqDetails} placeholder="Details (optional)" />
              <Btn tone="primary" onClick={handleCreateRequest} disabled={!reqChain || !reqSubject.trim()}>Submit Request</Btn>
              <div className="text-xs text-zinc-600">
                Routed through a real Employee → Manager → Executive chain — each step checks the
                approver&apos;s own Employee.Title against a real tier (staff/manager/executive), not a
                role checkbox. No fabricated &quot;Director&quot; tier — a director-titled employee is
                already treated as manager-tier.
              </div>
            </div>

            <div className="flex items-center gap-1.5">
              {([
                ["pending_for_me", "Pending For Me"],
                ["mine", "My Requests"],
                ["all", "All (Admin)"],
              ] as const).map(([key, label]) => (
                <WorkButton type="submit"
                  key={key}
                  onClick={() => setApprovalsView(key)}
                  className={`text-xs px-2 py-1 rounded-full ${approvalsView === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-800 text-zinc-400"}`}
                >
                  {label}
                </WorkButton>
              ))}
            </div>

            <div className="space-y-1">
              {requests.length === 0 && <div className="text-xs text-zinc-600">No requests.</div>}
              {requests.map((r) => (
                <div key={r.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800 space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <div>
                      <span className="text-zinc-200">{r.subject}</span>
                      <span className="text-zinc-600 ml-2">{r.chain_label}</span>
                    </div>
                    <span className={`px-1.5 py-0.5 rounded text-xs ${STATUS_TONE[r.status]}`}>{r.status}</span>
                  </div>
                  <div className="text-xs text-zinc-500">
                    {r.requested_by} · step {Math.min(r.current_step_index + 1, r.steps.length)}/{r.steps.length}
                    {r.status === "pending" && ` (needs ${r.steps[r.current_step_index]}-tier)`} · {fmt(r.created_at)}
                  </div>
                  {r.status === "pending" && (
                    <div className="flex gap-1.5">
                      <Btn tone="primary" onClick={() => handleApprove(r.id)}>Approve Step</Btn>
                      <Btn tone="danger" onClick={() => handleReject(r.id)}>Reject</Btn>
                      {r.requested_by === session?.employeeId && <Btn onClick={() => handleCancel(r.id)}>Cancel</Btn>}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
