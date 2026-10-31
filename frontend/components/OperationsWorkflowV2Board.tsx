"use client";
import { WorkButton, WorkInput , WorkStat} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";

// Workflow Engine v2 -- the real Workflow -> Step -> Task -> Approval ->
// Automation -> Completion UI. Shipped as an Operations-only pilot
// (2026-07-20), then generalized (2026-07-21) into a department-parameterized
// board so Sales' own 18-workflow catalog (Prospecting/Engagement/Deals/
// Finance/Retention) could reuse it rather than duplicate ~1,100 lines --
// every department-specific string below reads the real `department` prop
// (default "Operations" for the original pilot call site) instead of a
// hardcoded literal. Two levels, per Sam's own spec: a Workflow Dashboard
// (Monday.com/Asana/Jira-style -- one row per real workflow DEFINITION with
// live instance counts and Continue/Start New) and, inside one instance, a
// Step Progression view -- a vertical, numbered list of real steps, never a
// tab bar, each with Tasks/Evidence/Approvals/Comments/AI Actions. Backed
// entirely by lib/workflowEngineV2.ts / core/workflow_engine_v2.py -- a
// deliberately PARALLEL engine to this codebase's existing v1
// workflow-catalog system (components/DepartmentWorkflowButtons.tsx's own
// floating WorkflowWindow manager, still backing every other department's
// job-workflow buttons and Operations'/Sales' own pre-existing job-workflow
// buttons). This board only talks to the new v2 engine and is mounted as its
// own Top Menu Dash item ("workflows") per department, completely separate
// from that older surface.

import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState } from "react";
import {
  getCatalogV2,
  getDashboardV2,
  getStalledInstancesV2,
  listInstancesV2,
  getInstanceV2,
  getInstanceAiStateV2,
  getWorkflowDefV2,
  startWorkflowInstanceV2,
  advanceStepV2,
  addStepTaskV2,
  completeStepTaskV2,
  addStepEvidenceV2,
  addStepCommentV2,
  blockStepV2,
  unblockStepV2,
  requestStepApprovalV2,
  decideStepApprovalV2,
  escalateInstanceV2,
  resolveEscalationV2,
  forceCloseInstanceV2,
  CATEGORY_LABELS,
  TIER_LABELS,
  INSTANCE_STATUSES,
  type CatalogV2,
  type WorkflowDefV2,
  type DashboardV2,
  type DashboardRow,
  type StalledInstance,
  type WorkflowInstanceV2,
  type RuntimeStep,
  type AiStateV2,
  type InstanceStatus,
  type StepStatus,
  type AutomationTier,
  type WorkflowCategory,
} from "@/lib/workflowEngineV2";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const STATUS_TONE: Record<InstanceStatus, string> = {
  not_started: "bg-zinc-800 text-zinc-400",
  in_progress: "bg-blue-950/40 text-blue-300",
  blocked: "bg-red-950/40 text-red-300",
  waiting_approval: "bg-amber-950/40 text-amber-300",
  completed: "bg-green-950/40 text-green-300",
  escalated: "bg-red-900/60 text-red-200 font-medium",
};

const STEP_STATUS_TONE: Record<StepStatus, string> = {
  not_started: "bg-zinc-800 text-zinc-500",
  in_progress: "bg-blue-950/40 text-blue-300",
  blocked: "bg-red-950/40 text-red-300",
  completed: "bg-green-950/40 text-green-300",
};

const TIER_TONE: Record<AutomationTier, string> = {
  human_only: "bg-zinc-800 text-zinc-400",
  assisted: "bg-purple-950/40 text-purple-300",
  autonomous: "bg-teal-950/40 text-teal-300",
};

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: number; color: string }) { return <WorkStat label={label} value={value}/>; }

function ErrorBanner({ message }: { message: string | null }) {
  if (!message) return null;
  return <div className="text-xs px-2 py-1.5 rounded bg-red-500/15 border border-red-500/40 text-red-300">{message}</div>;
}

function StatusBadge({ status }: { status: InstanceStatus }) {
  return <span className={`text-xs px-2 py-0.5 rounded ${STATUS_TONE[status]}`}>{status.replace("_", " ")}</span>;
}

function StepStatusBadge({ status }: { status: StepStatus }) {
  return <span className={`text-xs px-1.5 py-0.5 rounded ${STEP_STATUS_TONE[status]}`}>{status.replace("_", " ")}</span>;
}

function TierBadge({ tier }: { tier: AutomationTier }) {
  return <span className={`text-xs px-1.5 py-0.5 rounded ${TIER_TONE[tier]}`}>{TIER_LABELS[tier]}</span>;
}

function InlineReasonButton({
  theme,
  label,
  color,
  mutating,
  placeholder,
  onConfirm,
  allowEmpty,
}: {
  theme: Theme;
  label: string;
  color: string;
  mutating: boolean;
  placeholder: string;
  onConfirm: (value: string) => void;
  allowEmpty?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [value, setValue] = useState("");
  const inputClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  if (!open) {
    return (
      <WorkButton type="submit"
        onClick={() => setOpen(true)}
        disabled={mutating}
        className="text-xs px-2.5 py-1.5 rounded text-white hover:opacity-90 transition disabled:opacity-50"
        style={{ background: color }}
      >
        {label}
      </WorkButton>
    );
  }

  return (
    <div className="flex items-center gap-1.5">
      <WorkField label={placeholder || "Value"}><WorkInput value={value} onChange={(e) => setValue(e.target.value)} placeholder={placeholder} className={`rounded-md border px-2 py-1 text-xs ${inputClass}`} /></WorkField>
      <WorkButton type="submit"
        disabled={mutating || (!allowEmpty && !value.trim())}
        onClick={() => {
          onConfirm(value.trim());
          setOpen(false);
          setValue("");
        }}
        className="text-xs px-2 py-1.5 rounded text-white hover:opacity-90 transition disabled:opacity-50"
        style={{ background: color }}
      >
        Confirm
      </WorkButton>
      <WorkButton type="submit" onClick={() => { setOpen(false); setValue(""); }} className="text-xs px-2 py-1.5 rounded bg-zinc-700 text-white hover:opacity-90 transition">
        Cancel
      </WorkButton>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Root component -- routes between Dashboard / Instances list / Step
// Progression detail.
// ---------------------------------------------------------------------------

type ViewState =
  | { kind: "dashboard" }
  | { kind: "instances"; workflowKey: string }
  | { kind: "detail"; instanceId: string };

export function OperationsWorkflowV2Board({
  theme,
  department = "Operations",
}: {
  theme: Theme;
  department?: string;
}) {
  const [view, setView] = useState<ViewState>({ kind: "dashboard" });

  return (
    <div className="space-y-3">
      {view.kind === "dashboard" && (
        <WorkflowDashboardView
          theme={theme}
          department={department}
          onOpenInstances={(workflowKey) => setView({ kind: "instances", workflowKey })}
          onOpenInstance={(instanceId) => setView({ kind: "detail", instanceId })}
        />
      )}
      {view.kind === "instances" && (
        <InstancesListView
          theme={theme}
          department={department}
          workflowKey={view.workflowKey}
          onBack={() => setView({ kind: "dashboard" })}
          onOpenInstance={(instanceId) => setView({ kind: "detail", instanceId })}
        />
      )}
      {view.kind === "detail" && (
        <StepProgressionView theme={theme} instanceId={view.instanceId} onBack={() => setView({ kind: "dashboard" })} />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 1: Workflow Dashboard
// ---------------------------------------------------------------------------

function WorkflowDefRow({
  theme,
  row,
  def,
  starting,
  onOpenInstances,
  onStart,
}: {
  theme: Theme;
  row: DashboardRow;
  def?: WorkflowDefV2;
  starting: boolean;
  onOpenInstances: () => void;
  onStart: () => void;
}) {
  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-black/20 p-3", "rounded-lg border border-zinc-200 bg-white p-3")}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="text-xs font-medium">{row.title}</div>
          <div className="text-xs text-zinc-500 mt-0.5">{row.purpose}</div>
          <div className="text-xs text-zinc-500 mt-1">
            {row.step_count} step{row.step_count === 1 ? "" : "s"}
            {def?.entity_type ? ` · linked to ${def.entity_type}` : ""}
          </div>
          <div className="flex flex-wrap gap-1 mt-1.5">
            {row.active > 0 && <span className="text-xs px-1.5 py-0.5 rounded bg-blue-950/40 text-blue-300">{row.active} active</span>}
            {row.blocked > 0 && <span className="text-xs px-1.5 py-0.5 rounded bg-red-950/40 text-red-300">{row.blocked} blocked</span>}
            {row.waiting_approval > 0 && (
              <span className="text-xs px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300">{row.waiting_approval} awaiting approval</span>
            )}
            {row.escalated > 0 && <span className="text-xs px-1.5 py-0.5 rounded bg-red-900/60 text-red-200">{row.escalated} escalated</span>}
            {row.completed > 0 && <span className="text-xs px-1.5 py-0.5 rounded bg-green-950/40 text-green-300">{row.completed} completed</span>}
            {row.total === 0 && <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-500">no instances yet</span>}
          </div>
        </div>
        <div className="flex flex-col gap-1 shrink-0">
          {row.total > 0 && (
            <WorkButton type="submit" onClick={onOpenInstances} className="text-xs px-2.5 py-1.5 rounded bg-zinc-700 text-white hover:opacity-90 transition">
              View {row.total}
            </WorkButton>
          )}
          <WorkButton type="submit" variant="primary"
            disabled={starting}
            onClick={onStart}
            className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
          >
            {starting ? "Starting…" : "+ Start New"}
          </WorkButton>
        </div>
      </div>
    </div>
  );
}

function WorkflowDashboardView({
  theme,
  department,
  onOpenInstances,
  onOpenInstance,
}: {
  theme: Theme;
  department: string;
  onOpenInstances: (workflowKey: string) => void;
  onOpenInstance: (instanceId: string) => void;
}) {
  const [catalog, setCatalog] = useState<CatalogV2 | null>(null);
  const [dashboard, setDashboard] = useState<DashboardV2 | null>(null);
  const [stalled, setStalled] = useState<StalledInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<WorkflowCategory | "">("");
  const [startingKey, setStartingKey] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getCatalogV2(), getDashboardV2(department), getStalledInstancesV2(department)])
      .then(([c, d, s]) => {
        setCatalog(c);
        setDashboard(d);
        setStalled(s.stalled);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(refresh, [department]);

  const defsByKey = useMemo(() => {
    const m = new Map<string, WorkflowDefV2>();
    (catalog?.workflows ?? []).forEach((w) => m.set(w.key, w));
    return m;
  }, [catalog]);

  const rows = useMemo(() => {
    let list = dashboard?.workflows ?? [];
    if (categoryFilter) list = list.filter((w) => w.category === categoryFilter);
    return list;
  }, [dashboard, categoryFilter]);

  const grouped = useMemo(() => {
    const g = new Map<WorkflowCategory, DashboardRow[]>();
    rows.forEach((r) => {
      const list = g.get(r.category) ?? [];
      list.push(r);
      g.set(r.category, list);
    });
    return g;
  }, [rows]);

  async function startNew(workflowKey: string) {
    setStartingKey(workflowKey);
    setError(null);
    try {
      const instance = await startWorkflowInstanceV2({ workflow_key: workflowKey });
      onOpenInstance(instance.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStartingKey(null);
    }
  }

  if (loading && !dashboard) {
    return <div className="text-xs text-zinc-500">Loading workflows…</div>;
  }

  return (
    <div className="space-y-4">
      <div>
        <div className="text-sm font-brand font-semibold uppercase tracking-wide">{department} Workflows</div>
        <div className="text-xs text-zinc-500">
          The real Workflow → Step → Task → Approval → Automation → Completion engine.
        </div>
      </div>

      <ErrorBanner message={error} />

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
        <Kpi theme={theme} label="Active Instances" value={dashboard?.total_active ?? 0} color={RIBBON[0]} />
        <Kpi theme={theme} label="Completed" value={dashboard?.total_completed ?? 0} color={RIBBON[1]} />
        <Kpi theme={theme} label="Escalated" value={dashboard?.total_escalated ?? 0} color={RIBBON[3]} />
        <Kpi theme={theme} label="Stalled (SLA)" value={stalled.length} color={RIBBON[2]} />
      </div>

      {stalled.length > 0 && (
        <div className={tc(theme, "rounded-lg border border-red-900/60 bg-red-950/10 p-3 space-y-1.5", "rounded-lg border border-red-300 bg-red-50 p-3 space-y-1.5")}>
          <div className="text-xs font-brand uppercase tracking-wide text-red-400">Stalled — past SLA</div>
          <RecordCollection>{stalled.map((s) => (
            <WorkButton type="submit" variant="danger"
              key={s.instance_id}
              onClick={() => onOpenInstance(s.instance_id)}
              className="w-full text-left text-xs flex items-center justify-between gap-2 rounded px-2 py-1 hover:bg-red-900/10 transition"
            >
              <span className="truncate">
                {s.title} — <span className="text-zinc-500">{s.current_step_label}</span>
              </span>
              <span className="text-xs text-red-300 shrink-0">
                {s.elapsed_hours}h / {s.sla_hours}h SLA
              </span>
            </WorkButton>
          ))}</RecordCollection>
        </div>
      )}

      <div className="flex flex-wrap gap-1.5">
        <WorkButton type="submit"
          onClick={() => setCategoryFilter("")}
          className={`text-xs px-2.5 py-1 rounded-full border transition ${
            categoryFilter === "" ? "bg-brand-blue text-white border-brand-blue" : tc(theme, "border-zinc-700 text-zinc-400", "border-zinc-300 text-zinc-600")
          }`}
        >
          All Categories
        </WorkButton>
        {(Object.keys(CATEGORY_LABELS) as WorkflowCategory[]).map((cat) => (
          <WorkButton type="submit"
            key={cat}
            onClick={() => setCategoryFilter(cat)}
            className={`text-xs px-2.5 py-1 rounded-full border transition ${
              categoryFilter === cat ? "bg-brand-blue text-white border-brand-blue" : tc(theme, "border-zinc-700 text-zinc-400", "border-zinc-300 text-zinc-600")
            }`}
          >
            {CATEGORY_LABELS[cat]}
          </WorkButton>
        ))}
      </div>

      <div className="space-y-4">
        {Array.from(grouped.entries()).map(([category, list]) => (
          <div key={category} className="space-y-1.5">
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{CATEGORY_LABELS[category]}</div>
            <div className="space-y-1.5">
              {list.map((row) => (
                <WorkflowDefRow
                  key={row.workflow_key}
                  theme={theme}
                  row={row}
                  def={defsByKey.get(row.workflow_key)}
                  starting={startingKey === row.workflow_key}
                  onOpenInstances={() => onOpenInstances(row.workflow_key)}
                  onStart={() => startNew(row.workflow_key)}
                />
              ))}
            </div>
          </div>
        ))}
        {grouped.size === 0 && <div className="text-xs text-zinc-500">No workflow definitions match this filter.</div>}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 1.5: Instances list for one workflow definition
// ---------------------------------------------------------------------------

function InstancesListView({
  theme,
  department,
  workflowKey,
  onBack,
  onOpenInstance,
}: {
  theme: Theme;
  department: string;
  workflowKey: string;
  onBack: () => void;
  onOpenInstance: (instanceId: string) => void;
}) {
  const [instances, setInstances] = useState<WorkflowInstanceV2[]>([]);
  const [def, setDef] = useState<WorkflowDefV2 | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<InstanceStatus | "">("");
  const [starting, setStarting] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([
      listInstancesV2({ workflow_key: workflowKey, status: statusFilter || undefined, department }),
      getWorkflowDefV2(workflowKey),
    ])
      .then(([r, d]) => {
        setInstances(r.instances);
        setDef(d);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(refresh, [department, workflowKey, statusFilter]);

  async function startNew() {
    setStarting(true);
    setError(null);
    try {
      const instance = await startWorkflowInstanceV2({ workflow_key: workflowKey });
      onOpenInstance(instance.id);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStarting(false);
    }
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <WorkButton type="submit" onClick={onBack} className="text-xs text-zinc-500 hover:text-zinc-300 transition">
          ← Workflow Dashboard
        </WorkButton>
        <WorkButton type="submit" variant="primary"
          disabled={starting}
          onClick={startNew}
          className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
        >
          {starting ? "Starting…" : "+ Start New"}
        </WorkButton>
      </div>

      <div>
        <div className="text-sm font-brand font-semibold">{def?.title ?? workflowKey}</div>
        {def && <div className="text-xs text-zinc-500">{def.purpose}</div>}
      </div>

      <ErrorBanner message={error} />

      <div className="flex flex-wrap gap-1.5">
        <WorkButton type="submit"
          onClick={() => setStatusFilter("")}
          className={`text-xs px-2.5 py-1 rounded-full border transition ${
            statusFilter === "" ? "bg-brand-blue text-white border-brand-blue" : tc(theme, "border-zinc-700 text-zinc-400", "border-zinc-300 text-zinc-600")
          }`}
        >
          All
        </WorkButton>
        {INSTANCE_STATUSES.map((s) => (
          <WorkButton type="submit"
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`text-xs px-2.5 py-1 rounded-full border transition ${
              statusFilter === s ? "bg-brand-blue text-white border-brand-blue" : tc(theme, "border-zinc-700 text-zinc-400", "border-zinc-300 text-zinc-600")
            }`}
          >
            {s.replace("_", " ")}
          </WorkButton>
        ))}
      </div>

      {loading ? (
        <div className="text-xs text-zinc-500">Loading instances…</div>
      ) : instances.length === 0 ? (
        <div className="text-xs text-zinc-500">No instances{statusFilter ? ` with status "${statusFilter}"` : ""}.</div>
      ) : (
        <div className="space-y-1.5">
          {instances.map((inst) => (
            <button
              key={inst.id}
              onClick={() => onOpenInstance(inst.id)}
              className={tc(
                theme,
                "w-full text-left rounded-lg border border-zinc-800 bg-black/20 p-2.5 hover:border-zinc-600 transition",
                "w-full text-left rounded-lg border border-zinc-200 bg-white p-2.5 hover:border-zinc-400 transition"
              )}
            >
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-xs font-medium">
                    {inst.id}
                    {inst.linked_entity_id ? ` — ${inst.linked_entity_id}` : ""}
                  </div>
                  <div className="text-xs text-zinc-500">
                    step: {inst.current_step_key ?? "—"} · started by {inst.started_by} · updated {fmt(inst.updated_at)}
                  </div>
                </div>
                <span className="shrink-0">
                  <StatusBadge status={inst.status} />
                </span>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 2: AI State panel
// ---------------------------------------------------------------------------

function AiStatePanel({ theme, state }: { theme: Theme; state: AiStateV2 }) {
  return (
    <div className={tc(theme, "rounded-lg border border-teal-900/50 bg-teal-950/10 p-3 space-y-2", "rounded-lg border border-teal-300 bg-teal-50 p-3 space-y-2")}>
      <div className="text-xs font-brand uppercase tracking-wide text-teal-400">AI Workflow Awareness</div>
      <div className="grid grid-cols-2 gap-2 text-xs">
        <div>
          <div className="text-zinc-500">Current Step</div>
          <div>{state.current_step ? state.current_step.label : "—"}</div>
        </div>
        <div>
          <div className="text-zinc-500">Next Step</div>
          <div>{state.next_step ? state.next_step.label : "—"}</div>
        </div>
      </div>
      {state.blocked_steps.length > 0 && (
        <div className="text-xs">
          <div className="text-zinc-500">Blocked Steps</div>
          {state.blocked_steps.map((b) => (
            <div key={b.key}>
              {b.label}: <span className="text-red-300">{b.blocked_reason}</span>
            </div>
          ))}
        </div>
      )}
      {state.required_approvals.length > 0 && (
        <div className="text-xs">
          <div className="text-zinc-500">Required Approvals</div>
          {state.required_approvals.map((a) => (
            <div key={a.approval_id}>
              {a.step_label} — requested by {a.requested_by}
              {a.note ? `: ${a.note}` : ""}
            </div>
          ))}
        </div>
      )}
      {state.missing_information.length > 0 && (
        <div className="text-xs">
          <div className="text-zinc-500">Missing Information</div>
          <ul className="list-disc list-inside">
            {state.missing_information.map((m, i) => (
              <li key={i}>{m}</li>
            ))}
          </ul>
        </div>
      )}
      {state.stalled?.is_stalled && (
        <div className="text-xs text-red-300">
          Stalled — {state.stalled.elapsed_hours}h elapsed vs {state.stalled.sla_hours}h SLA.
        </div>
      )}
      {state.suggested_actions.length > 0 && (
        <div className="text-xs">
          <div className="text-zinc-500">Suggested Actions</div>
          <ul className="list-disc list-inside">
            {state.suggested_actions.map((a, i) => (
              <li key={i}>{a}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 2: Step card -- Tasks / Evidence / Approvals / Comments / AI Actions
// ---------------------------------------------------------------------------

function StepCard({
  theme,
  index,
  step,
  isCurrent,
  instanceStatus,
  expanded,
  onToggle,
  mutating,
  onAdvance,
  onAddTask,
  onCompleteTask,
  onAddEvidence,
  onAddComment,
  onBlock,
  onUnblock,
  onRequestApproval,
  onDecideApproval,
}: {
  theme: Theme;
  index: number;
  step: RuntimeStep;
  isCurrent: boolean;
  instanceStatus: InstanceStatus;
  expanded: boolean;
  onToggle: () => void;
  mutating: boolean;
  onAdvance: () => void;
  onAddTask: (description: string, assignedTo: string) => void;
  onCompleteTask: (taskId: string) => void;
  onAddEvidence: (description: string, url: string) => void;
  onAddComment: (text: string) => void;
  onBlock: (reason: string) => void;
  onUnblock: (notes: string) => void;
  onRequestApproval: (note: string) => void;
  onDecideApproval: (approvalId: string, approved: boolean, note: string) => void;
}) {
  const [taskDesc, setTaskDesc] = useState("");
  const [taskAssignee, setTaskAssignee] = useState("");
  const [evidenceDesc, setEvidenceDesc] = useState("");
  const [evidenceUrl, setEvidenceUrl] = useState("");
  const [commentText, setCommentText] = useState("");
  const [blockReason, setBlockReason] = useState("");
  const [showBlockForm, setShowBlockForm] = useState(false);
  const [decisionNotes, setDecisionNotes] = useState<Record<string, string>>({});

  const inputClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  const openTasks = step.tasks.filter((t) => t.status === "open");
  const pendingApproval = step.approvals.find((a) => a.status === "pending");
  const canAdvance = isCurrent && instanceStatus === "in_progress" && step.status !== "completed";

  return (
    <div
      className={tc(
        theme,
        `rounded-lg border ${step.status === "blocked" ? "border-red-900/60 bg-red-950/10" : isCurrent ? "border-brand-blue/60 bg-blue-950/10" : "border-zinc-800 bg-black/20"}`,
        `rounded-lg border ${step.status === "blocked" ? "border-red-300 bg-red-50" : isCurrent ? "border-brand-blue bg-blue-50" : "border-zinc-200 bg-white"}`
      )}
    >
      <button onClick={onToggle} className="w-full text-left p-3 flex items-start justify-between gap-3">
        <div className="flex items-start gap-2.5 min-w-0">
          <div
            className={`shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-semibold ${
              step.status === "completed" ? "bg-green-700 text-white" : isCurrent ? "bg-brand-blue text-white" : "bg-zinc-700 text-zinc-300"
            }`}
          >
            {step.status === "completed" ? "✓" : index}
          </div>
          <div className="min-w-0">
            <div className="text-xs font-medium flex items-center gap-1.5 flex-wrap">
              {step.label}
              <StepStatusBadge status={step.status} />
              <TierBadge tier={step.automation_tier} />
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">
              Owner: {step.owner_role}
              {step.owner ? ` (${step.owner})` : ""} · SLA {step.sla_hours}h
              {step.started_at ? ` · started ${fmt(step.started_at)}` : ""}
              {step.completed_at ? ` · completed ${fmt(step.completed_at)}` : ""}
            </div>
            {step.status === "blocked" && step.blocked_reason && <div className="text-xs text-red-300 mt-0.5">Blocked: {step.blocked_reason}</div>}
          </div>
        </div>
        <span className="text-xs text-zinc-500 shrink-0">{expanded ? "▲" : "▼"}</span>
      </button>

      {expanded && (
        <div className="px-3 pb-3 space-y-3 border-t border-black/10 pt-2.5">
          <div className="text-xs text-zinc-500 italic">{step.automation_note}</div>
          {step.real_source_hint && <div className="text-xs text-zinc-500">Real source: {step.real_source_hint}</div>}

          <div className="flex flex-wrap gap-1.5">
            {canAdvance && (
              <WorkButton type="submit"
                disabled={mutating}
                onClick={onAdvance}
                className="text-xs px-2.5 py-1.5 rounded bg-green-700 text-white font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                Advance Step →
              </WorkButton>
            )}
            {step.status === "blocked" ? (
              <InlineReasonButton theme={theme} label="Unblock" color="#2B68AB" mutating={mutating} placeholder="Notes (optional)…" onConfirm={onUnblock} allowEmpty />
            ) : showBlockForm ? (
              <div className="flex items-center gap-1.5">
                <WorkField label="Reason for blocking"><WorkInput
                  value={blockReason}
                  onChange={(e) => setBlockReason(e.target.value)}
                  placeholder="Reason for blocking…"
                  className={`rounded-md border px-2 py-1 text-xs ${inputClass}`}
                /></WorkField>
                <WorkButton type="submit" variant="danger"
                  disabled={mutating || !blockReason.trim()}
                  onClick={() => {
                    onBlock(blockReason.trim());
                    setBlockReason("");
                    setShowBlockForm(false);
                  }}
                  className="text-xs px-2 py-1.5 rounded bg-red-700 text-white hover:opacity-90 transition disabled:opacity-50"
                >
                  Confirm
                </WorkButton>
                <WorkButton type="submit" onClick={() => setShowBlockForm(false)} className="text-xs px-2 py-1.5 rounded bg-zinc-700 text-white hover:opacity-90 transition">
                  Cancel
                </WorkButton>
              </div>
            ) : (
              <WorkButton type="submit" variant="danger" disabled={mutating} onClick={() => setShowBlockForm(true)} className="text-xs px-2.5 py-1.5 rounded bg-red-800 text-white hover:opacity-90 transition disabled:opacity-50">
                Block
              </WorkButton>
            )}
            {!pendingApproval && (
              <InlineReasonButton theme={theme} label="Request Approval" color="#B08900" mutating={mutating} placeholder="Note (optional)…" onConfirm={onRequestApproval} allowEmpty />
            )}
          </div>

          {/* Tasks */}
          <div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">
              Tasks {openTasks.length > 0 && <span className="text-zinc-600">({openTasks.length} open)</span>}
            </div>
            <div className="space-y-1">
              {step.tasks.length === 0 && <div className="text-xs text-zinc-600">No tasks yet.</div>}
              {step.tasks.map((t) => (
                <div key={t.id} className="flex items-center justify-between gap-2 text-xs">
                  <span className={t.status === "completed" ? "line-through text-zinc-500" : ""}>
                    {t.description}
                    {t.assigned_to ? ` — ${t.assigned_to}` : ""}
                  </span>
                  {t.status === "open" && (
                    <WorkButton type="submit"
                      disabled={mutating}
                      onClick={() => onCompleteTask(t.id)}
                      className="text-xs px-1.5 py-0.5 rounded bg-green-800 text-white hover:opacity-90 transition disabled:opacity-50 shrink-0"
                    >
                      Complete
                    </WorkButton>
                  )}
                </div>
              ))}
            </div>
            <div className="flex items-center gap-1.5 mt-1.5">
              <WorkField label="New task"><WorkInput value={taskDesc} onChange={(e) => setTaskDesc(e.target.value)} placeholder="New task…" className={`flex-1 rounded-md border px-2 py-1 text-xs ${inputClass}`} /></WorkField>
              <WorkField label="Assigned to (optional)"><WorkInput
                value={taskAssignee}
                onChange={(e) => setTaskAssignee(e.target.value)}
                placeholder="Assigned to (optional)"
                className={`w-32 rounded-md border px-2 py-1 text-xs ${inputClass}`}
              /></WorkField>
              <WorkButton type="submit" variant="primary"
                disabled={mutating || !taskDesc.trim()}
                onClick={() => {
                  onAddTask(taskDesc.trim(), taskAssignee.trim());
                  setTaskDesc("");
                  setTaskAssignee("");
                }}
                className="text-xs px-2 py-1.5 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50 shrink-0"
              >
                Add
              </WorkButton>
            </div>
          </div>

          {/* Evidence */}
          <div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Evidence</div>
            <div className="space-y-1">
              {step.evidence.length === 0 && <div className="text-xs text-zinc-600">No evidence attached.</div>}
              {step.evidence.map((ev) => (
                <div key={ev.id} className="text-xs">
                  {ev.description}
                  {ev.url && (
                    <>
                      {" — "}
                      <a href={ev.url} target="_blank" rel="noreferrer" className="text-brand-blue underline">
                        link
                      </a>
                    </>
                  )}{" "}
                  <span className="text-zinc-500">({ev.added_by})</span>
                </div>
              ))}
            </div>
            <div className="flex items-center gap-1.5 mt-1.5">
              <WorkField label="Evidence description"><WorkInput
                value={evidenceDesc}
                onChange={(e) => setEvidenceDesc(e.target.value)}
                placeholder="Evidence description…"
                className={`flex-1 rounded-md border px-2 py-1 text-xs ${inputClass}`}
              /></WorkField>
              <WorkField label="URL (optional)"><WorkInput
                value={evidenceUrl}
                onChange={(e) => setEvidenceUrl(e.target.value)}
                placeholder="URL (optional)"
                className={`w-32 rounded-md border px-2 py-1 text-xs ${inputClass}`}
              /></WorkField>
              <WorkButton type="submit" variant="primary"
                disabled={mutating || !evidenceDesc.trim()}
                onClick={() => {
                  onAddEvidence(evidenceDesc.trim(), evidenceUrl.trim());
                  setEvidenceDesc("");
                  setEvidenceUrl("");
                }}
                className="text-xs px-2 py-1.5 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50 shrink-0"
              >
                Add
              </WorkButton>
            </div>
          </div>

          {/* Approvals */}
          <div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Approvals</div>
            <div className="space-y-1.5">
              {step.approvals.length === 0 && <div className="text-xs text-zinc-600">No approvals requested.</div>}
              {step.approvals.map((a) => (
                <div key={a.id} className="text-xs space-y-1">
                  <div>
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded mr-1 ${
                        a.status === "pending" ? "bg-amber-950/40 text-amber-300" : a.status === "approved" ? "bg-green-950/40 text-green-300" : "bg-red-950/40 text-red-300"
                      }`}
                    >
                      {a.status}
                    </span>
                    requested by {a.requested_by}
                    {a.note ? `: ${a.note}` : ""}
                    {a.decided_by && (
                      <span className="text-zinc-500">
                        {" "}
                        — decided by {a.decided_by}
                        {a.decision_note ? `: ${a.decision_note}` : ""}
                      </span>
                    )}
                  </div>
                  {a.status === "pending" && (
                    <div className="flex items-center gap-1.5">
                      <WorkField label="Decision note (optional)"><WorkInput
                        value={decisionNotes[a.id] ?? ""}
                        onChange={(e) => setDecisionNotes((prev) => ({ ...prev, [a.id]: e.target.value }))}
                        placeholder="Decision note (optional)…"
                        className={`flex-1 rounded-md border px-2 py-1 text-xs ${inputClass}`}
                      /></WorkField>
                      <WorkButton type="submit"
                        disabled={mutating}
                        onClick={() => onDecideApproval(a.id, true, (decisionNotes[a.id] ?? "").trim())}
                        className="text-xs px-2 py-1 rounded bg-green-800 text-white hover:opacity-90 transition disabled:opacity-50"
                      >
                        Approve
                      </WorkButton>
                      <WorkButton type="submit" variant="danger"
                        disabled={mutating}
                        onClick={() => onDecideApproval(a.id, false, (decisionNotes[a.id] ?? "").trim())}
                        className="text-xs px-2 py-1 rounded bg-red-800 text-white hover:opacity-90 transition disabled:opacity-50"
                      >
                        Reject
                      </WorkButton>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Comments */}
          <div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Comments</div>
            <div className="space-y-1">
              {step.comments.length === 0 && <div className="text-xs text-zinc-600">No comments.</div>}
              {step.comments.map((c) => (
                <div key={c.id} className="text-xs">
                  <span className="text-zinc-500">{c.by}:</span> {c.text}
                </div>
              ))}
            </div>
            <div className="flex items-center gap-1.5 mt-1.5">
              <WorkField label="Add a comment"><WorkInput
                value={commentText}
                onChange={(e) => setCommentText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && commentText.trim()) {
                    onAddComment(commentText.trim());
                    setCommentText("");
                  }
                }}
                placeholder="Add a comment…"
                className={`flex-1 rounded-md border px-2 py-1 text-xs ${inputClass}`}
              /></WorkField>
              <WorkButton type="submit" variant="primary"
                disabled={mutating || !commentText.trim()}
                onClick={() => {
                  onAddComment(commentText.trim());
                  setCommentText("");
                }}
                className="text-xs px-2 py-1.5 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50 shrink-0"
              >
                Post
              </WorkButton>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Level 2: Step Progression view (one instance)
// ---------------------------------------------------------------------------

function StepProgressionView({ theme, instanceId, onBack }: { theme: Theme; instanceId: string; onBack: () => void }) {
  const [instance, setInstance] = useState<WorkflowInstanceV2 | null>(null);
  const [aiState, setAiState] = useState<AiStateV2 | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [mutating, setMutating] = useState(false);
  const [expandedStep, setExpandedStep] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getInstanceV2(instanceId), getInstanceAiStateV2(instanceId)])
      .then(([inst, state]) => {
        setInstance(inst);
        setAiState(state);
        setExpandedStep((prev) => prev ?? inst.current_step_key ?? (inst.steps[0]?.key ?? null));
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(refresh, [instanceId]);

  async function run(fn: () => Promise<unknown>) {
    setMutating(true);
    setError(null);
    try {
      await fn();
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setMutating(false);
    }
  }

  if (loading && !instance) {
    return <div className="text-xs text-zinc-500">Loading workflow instance…</div>;
  }

  if (!instance) {
    return (
      <div className="space-y-2">
        <WorkButton type="submit" onClick={onBack} className="text-xs text-zinc-500 hover:text-zinc-300 transition">
          ← Workflow Dashboard
        </WorkButton>
        <ErrorBanner message={error ?? "Instance not found."} />
      </div>
    );
  }

  const canEscalate = instance.status !== "completed" && instance.status !== "escalated";
  const canResolveEscalation = instance.status === "escalated";
  const canForceClose = instance.status !== "completed";

  return (
    <div className="space-y-3">
      <WorkButton type="submit" onClick={onBack} className="text-xs text-zinc-500 hover:text-zinc-300 transition">
        ← Workflow Dashboard
      </WorkButton>

      <div className={tc(theme, "rounded-lg border border-zinc-800 bg-black/20 p-3", "rounded-lg border border-zinc-200 bg-white p-3")}>
        <div className="flex items-start justify-between gap-3 flex-wrap">
          <div>
            <div className="text-sm font-brand font-semibold">{instance.title}</div>
            <div className="text-xs text-zinc-500">
              {instance.id}
              {instance.linked_entity_id ? ` · linked to ${instance.linked_entity_id}` : ""}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">
              Started by {instance.started_by} on {fmt(instance.started_at)} · updated {fmt(instance.updated_at)}
            </div>
            {instance.force_closed && <div className="text-xs text-amber-400 mt-0.5">Force-closed: {instance.force_close_reason}</div>}
            {instance.status === "escalated" && instance.escalated_reason && (
              <div className="text-xs text-red-300 mt-0.5">Escalated: {instance.escalated_reason}</div>
            )}
          </div>
          <StatusBadge status={instance.status} />
        </div>
        <div className="flex flex-wrap gap-1.5 mt-2">
          {canEscalate && <InlineReasonButton theme={theme} label="Escalate" color="#EE3C25" mutating={mutating} placeholder="Reason for escalation…" onConfirm={(reason) => run(() => escalateInstanceV2(instance.id, reason))} />}
          {canResolveEscalation && (
            <WorkButton type="submit" variant="primary"
              disabled={mutating}
              onClick={() => run(() => resolveEscalationV2(instance.id))}
              className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50"
            >
              Resolve Escalation
            </WorkButton>
          )}
          {canForceClose && (
            <InlineReasonButton theme={theme} label="Force Close" color="#71717a" mutating={mutating} placeholder="Reason for force close…" onConfirm={(reason) => run(() => forceCloseInstanceV2(instance.id, reason))} />
          )}
        </div>
      </div>

      {aiState && <AiStatePanel theme={theme} state={aiState} />}

      <ErrorBanner message={error} />

      <div className="space-y-2">
        {instance.steps.map((step, idx) => (
          <StepCard
            key={step.key}
            theme={theme}
            index={idx + 1}
            step={step}
            isCurrent={instance.current_step_key === step.key}
            instanceStatus={instance.status}
            expanded={expandedStep === step.key}
            onToggle={() => setExpandedStep(expandedStep === step.key ? null : step.key)}
            mutating={mutating}
            onAdvance={() => run(() => advanceStepV2(instance.id))}
            onAddTask={(description, assignedTo) => run(() => addStepTaskV2(instance.id, { step_key: step.key, description, assigned_to: assignedTo || undefined }))}
            onCompleteTask={(taskId) => run(() => completeStepTaskV2(instance.id, { step_key: step.key, task_id: taskId }))}
            onAddEvidence={(description, url) => run(() => addStepEvidenceV2(instance.id, { step_key: step.key, description, url: url || undefined }))}
            onAddComment={(text) => run(() => addStepCommentV2(instance.id, { step_key: step.key, text }))}
            onBlock={(reason) => run(() => blockStepV2(instance.id, { step_key: step.key, reason }))}
            onUnblock={(notes) => run(() => unblockStepV2(instance.id, { step_key: step.key, notes: notes || undefined }))}
            onRequestApproval={(note) => run(() => requestStepApprovalV2(instance.id, { step_key: step.key, note: note || undefined }))}
            onDecideApproval={(approvalId, approved, note) =>
              run(() => decideStepApprovalV2(instance.id, { step_key: step.key, approval_id: approvalId, approved, note: note || undefined }))
            }
          />
        ))}
      </div>
    </div>
  );
}
