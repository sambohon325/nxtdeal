// Administration's "Compliance & Governance" item (Administration Control
// Center rebuild, continuing 2026-07-18). Backend: core/governance.py /
// _api.py -- composes core/compliance.py's cited-federal-rules alert engine
// and core/permissions_registry.py's tier-gated cross-department
// ApprovalRequest hierarchy into one real governance workspace, plus a
// governance-scoped slice of the audit log (Permissions/Approvals/
// Compliance categories only, reusing core/audit_center.py's own category
// catalog). The pre-existing content approval queue (campaigns/assets/
// websites/financing) and escalation-rules dashboard still come through
// the generic GET /menu/data?department=Administration&item_key=governance
// route (core/administration_menu.py's governance()) -- this client covers
// the dedicated /governance/* drill-down routes this board's own extra
// views need.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type GovernanceCategory = "Permissions" | "Approvals" | "Compliance";

export type ComplianceGovernanceSummary = {
  total_alerts: number;
  by_status: Record<string, number>;
  resolution_rate: number | null;
  avg_resolution_hours: number | null;
  by_law: Record<string, number>;
  notice: string;
};

export type ApprovalChain = { key: string; label: string; steps: string[] };

export type ApprovalRequestBrief = {
  id: string;
  chain_key: string;
  chain_label: string;
  steps: string[];
  current_step_index: number;
  status: "pending" | "approved" | "rejected" | "cancelled";
  subject: string;
  details: string;
  entity_id: string | null;
  requested_by: string;
  created_at: string;
  updated_at: string;
  history: { action: string; by: string; at: string; [k: string]: unknown }[];
};

export type ApprovalHierarchySummary = {
  total_requests: number;
  by_status: Record<string, number>;
  by_chain: Record<string, number>;
  chains: ApprovalChain[];
  throughput_rate: number | null;
  avg_turnaround_hours: number | null;
  pending_requests: ApprovalRequestBrief[];
};

export type GovernanceHealth = {
  blended_health_score: number | null;
  basis: string;
  compliance_resolution_rate: number | null;
  approval_throughput_rate: number | null;
  open_compliance_alerts: number;
  pending_approval_requests: number;
};

export type GovernanceEvent = {
  id: string;
  event_type: string;
  category: string;
  entity_id: string | null;
  actor: string;
  summary: string;
  details: Record<string, unknown>;
  timestamp: string;
};

export type GovernanceActionLog = {
  total_matches: number;
  returned: number;
  events: GovernanceEvent[];
};

export type GovernanceOverview = {
  compliance_summary: ComplianceGovernanceSummary;
  approval_hierarchy: ApprovalHierarchySummary;
  governance_health: GovernanceHealth;
  governance_action_log: GovernanceActionLog;
  not_yet_tracked: Record<string, string>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

export function getGovernanceOverview(): Promise<GovernanceOverview> {
  return get("/governance/overview");
}

export function getComplianceGovernanceSummary(): Promise<ComplianceGovernanceSummary> {
  return get("/governance/compliance-summary");
}

export function getApprovalHierarchySummary(): Promise<ApprovalHierarchySummary> {
  return get("/governance/approval-hierarchy");
}

export function getGovernanceHealth(): Promise<GovernanceHealth> {
  return get("/governance/health");
}

export function getGovernanceActionLog(opts?: { category?: GovernanceCategory; limit?: number }): Promise<GovernanceActionLog> {
  const params = new URLSearchParams();
  if (opts?.category) params.set("category", opts.category);
  if (opts?.limit) params.set("limit", String(opts.limit));
  const qs = params.toString();
  return get(`/governance/action-log${qs ? `?${qs}` : ""}`);
}


// The pre-existing content-approval queue (campaigns/assets/websites/
// financing) and escalation-rules dashboard still come through the generic
// GET /menu/data?department=Administration&item_key=governance route
// (core/administration_menu.py's governance()) -- reused here rather than
// duplicated, same "general dashboard stays behind /menu/data" precedent
// lib/lendingCompliance.ts's getFinanceComplianceOverview() established.
export type ContentApprovalQueue = {
  campaigns?: { count: number | null; items?: unknown[]; error?: string };
  assets?: { count: number | null; items?: unknown[]; error?: string };
  websites?: { count: number | null; items?: unknown[]; error?: string };
  financing?: { count: number | null; items?: unknown[]; error?: string };
};

export type EscalationDashboard = Record<string, unknown>;

export type GovernanceMenuOverview = {
  approval_queue?: ContentApprovalQueue;
  escalation_rules?: EscalationDashboard;
  audit_trail?: GovernanceActionLog;
  compliance_summary?: ComplianceGovernanceSummary;
  approval_hierarchy?: ApprovalHierarchySummary;
  governance_health?: GovernanceHealth;
  not_yet_tracked?: Record<string, string>;
  error?: string;
};

export function getGovernanceMenuOverview(): Promise<GovernanceMenuOverview> {
  const params = new URLSearchParams({ department: "Administration", item_key: "governance" });
  return get(`/menu/data?${params.toString()}`);
}
