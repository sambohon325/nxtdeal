"use client";
import { WorkButton, WorkInput, WorkSelect, WorkTextarea , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Readiness reframe -- "Strategic Planning" (2026-07-19), item #9 of Sam's
// 10-item proposed structure. Sam's own words: "A completely new area."
// Real Quarterly Planning (Objectives/Goals/Budgets), Department Planning,
// and Initiative Tracking (core/strategic_planning.py). Status is computed
// LIVE, never manually set: real for Sales/Service/Marketing objectives
// (core/performance_readiness.py's own real signal sources, generalized
// from a calendar month to a calendar quarter), an honest manual self-
// report for every other department. A quarterly objective can be
// explicitly, one-way pushed into Performance Readiness's own monthly goal
// via "Sync to Monthly Goal" -- never automatic. Initiative progress is
// real where a real graph signal exists (a linked Website's own publish
// status, a real InstalledDevice count against a target) and an honest
// manual self-report otherwise (e.g. "New Service Center," "New BHPH
// Program" -- no backing entity for either). Viewing is open to every
// role; creating/editing is ADMIN/OPERATIONS-only, enforced by the
// backend.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getStrategicPlanningOverview,
  createObjective,
  updateObjectiveProgress,
  cancelObjective,
  reopenObjective,
  syncObjectiveToMonthlyGoal,
  createInitiative,
  updateInitiativeStatus,
  updateInitiativeProgress,
  type StrategicPlanningOverview,
  type StrategicObjective,
  type StrategicInitiative,
  type TrackingType,
} from "@/lib/strategicPlanning";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;
const QUARTERS = ["Q1", "Q2", "Q3", "Q4"];

const STATUS_COLOR: Record<string, string> = {
  on_track: "text-emerald-400",
  achieved: "text-emerald-400",
  at_risk: "text-amber-400",
  behind: "text-red-400",
  missed: "text-red-400",
  not_started: "text-zinc-500",
  no_target: "text-zinc-500",
  no_data: "text-zinc-500",
  cancelled: "text-zinc-600 line-through",
};

const INIT_STATUS_COLOR: Record<string, string> = {
  planned: "text-zinc-400",
  in_progress: "text-amber-400",
  completed: "text-emerald-400",
  cancelled: "text-zinc-600 line-through",
};

function fmtStatus(s: string): string {
  return s.replace(/_/g, " ");
}

function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return Number.isInteger(v) ? v.toLocaleString() : v.toFixed(2);
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function Btn({ onClick, children, disabled, tone }: { onClick: () => void; children: React.ReactNode; disabled?: boolean; tone?: "primary" | "danger" | "muted" }) {
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

function ObjectiveCard({ theme, obj, onRefresh }: { theme: Theme; obj: StrategicObjective; onRefresh: () => void }) {
  const [progressInput, setProgressInput] = useState(obj.manual_progress_pct != null ? String(obj.manual_progress_pct) : "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const isLive = obj.current_value_basis === "real";

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      onRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-3")}>
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: RIBBON[0] }} />
      <div className="pl-2">
        <div className="flex items-center justify-between">
          <div className="text-sm font-brand font-semibold">{obj.title}</div>
          <span className={`text-xs uppercase tracking-wide font-semibold ${STATUS_COLOR[obj.status] ?? "text-zinc-400"}`}>
            {fmtStatus(obj.status)}
          </span>
        </div>
        <div className="text-xs text-zinc-500 mt-0.5">
          {obj.department} · {obj.quarter} {obj.year} · basis: {obj.current_value_basis ?? "—"}
        </div>
        {obj.description && <div className="text-xs text-zinc-500 mt-1">{obj.description}</div>}

        <div className="grid grid-cols-3 gap-2 mt-2">
          <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-2 py-1", "rounded border border-zinc-200 bg-zinc-50 px-2 py-1")}>
            <div className="text-xs uppercase text-zinc-500">Target</div>
            <div className="text-xs font-semibold">{obj.target_value !== null ? `${fmtNum(obj.target_value)} ${obj.unit}` : "Not set"}</div>
          </div>
          <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-2 py-1", "rounded border border-zinc-200 bg-zinc-50 px-2 py-1")}>
            <div className="text-xs uppercase text-zinc-500">Current</div>
            <div className="text-xs font-semibold">{obj.current_value !== null ? `${fmtNum(obj.current_value)}${isLive ? ` ${obj.unit}` : "%"}` : "—"}</div>
          </div>
          <div className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-2 py-1", "rounded border border-zinc-200 bg-zinc-50 px-2 py-1")}>
            <div className="text-xs uppercase text-zinc-500">% of Target</div>
            <div className="text-xs font-semibold">{obj.pct_of_target !== null ? `${fmtNum(obj.pct_of_target)}%` : "—"}</div>
          </div>
        </div>

        {(obj.budget_allocated !== null || obj.budget_spent !== null) && (
          <div className="text-xs text-zinc-500 mt-1.5">
            Budget: ${fmtNum(obj.budget_allocated)} allocated, ${fmtNum(obj.budget_spent)} spent (manually entered)
          </div>
        )}

        {obj.synced_monthly_goal && (
          <div className="text-xs text-zinc-600 mt-1">
            Synced to Performance Readiness monthly goal: {fmtNum(obj.synced_monthly_target)} (at {obj.synced_at ? new Date(obj.synced_at).toLocaleDateString() : "—"})
          </div>
        )}

        {!isLive && (
          <div className="mt-2 flex items-center gap-2">
            <WorkField label="Manual progress % (0-100)"><WorkInput
              value={progressInput}
              onChange={(e) => setProgressInput(e.target.value)}
              placeholder="Manual progress % (0-100)"
              className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-40"
            /></WorkField>
            <Btn onClick={() => run(() => updateObjectiveProgress(obj.id, Number(progressInput)))} disabled={busy || !progressInput}>
              Record Progress
            </Btn>
          </div>
        )}

        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {obj.department.toLowerCase() !== "company-wide" && obj.target_value !== null && !obj.is_cancelled && (
            <Btn onClick={() => run(() => syncObjectiveToMonthlyGoal(obj.id))} disabled={busy} tone="muted">
              Sync to Monthly Goal
            </Btn>
          )}
          {obj.is_cancelled ? (
            <Btn onClick={() => run(() => reopenObjective(obj.id))} disabled={busy} tone="muted">
              Reopen
            </Btn>
          ) : (
            <Btn onClick={() => run(() => cancelObjective(obj.id))} disabled={busy} tone="danger">
              Cancel
            </Btn>
          )}
        </div>
        {msg && <div className="text-xs text-red-400 mt-1">{msg}</div>}
      </div>
    </div>
  );
}

function InitiativeCard({ theme, item, onRefresh }: { theme: Theme; item: StrategicInitiative; onRefresh: () => void }) {
  const [progressInput, setProgressInput] = useState(item.manual_progress_pct != null ? String(item.manual_progress_pct) : "");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const isManual = item.tracking_type === "manual";
  const nextSteps: Record<string, string[]> = { planned: ["in_progress", "cancelled"], in_progress: ["completed", "cancelled"], completed: [], cancelled: [] };

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setMsg(null);
    try {
      await fn();
      onRefresh();
    } catch (e) {
      setMsg(e instanceof Error ? e.message : "Action failed.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-3")}>
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: RIBBON[2] }} />
      <div className="pl-2">
        <div className="flex items-center justify-between">
          <div className="text-sm font-brand font-semibold">{item.name}</div>
          <span className={`text-xs uppercase tracking-wide font-semibold ${INIT_STATUS_COLOR[item.status] ?? "text-zinc-400"}`}>
            {fmtStatus(item.status)}
          </span>
        </div>
        <div className="text-xs text-zinc-500 mt-0.5">
          {item.department} · owner: {item.owner_employee_id ?? "—"}
        </div>
        {item.description && <div className="text-xs text-zinc-500 mt-1">{item.description}</div>}

        <div className="mt-2">
          <div className="flex items-center justify-between text-xs mb-0.5">
            <span className="uppercase text-zinc-500">
              Progress {item.progress.basis === "manual" ? "(manual self-report)" : "(real, auto-tracked)"}
            </span>
            <span className="font-semibold">{item.progress.progress_pct !== null ? `${fmtNum(item.progress.progress_pct)}%` : "—"}</span>
          </div>
          <div className={tc(theme, "h-1.5 rounded-full bg-zinc-800 overflow-hidden", "h-1.5 rounded-full bg-zinc-200 overflow-hidden")}>
            <div
              className="h-full"
              style={{ width: `${Math.max(0, Math.min(100, item.progress.progress_pct ?? 0))}%`, background: item.progress.basis === "manual" ? "#FBCF09" : "#3FBCC4" }}
            />
          </div>
          {item.progress.detail && (
            <div className="text-xs text-zinc-600 mt-1">
              {Object.entries(item.progress.detail).map(([k, v]) => `${k}: ${String(v)}`).join(" · ")}
            </div>
          )}
          {item.progress.error && <div className="text-xs text-red-400 mt-1">{item.progress.error}</div>}
        </div>

        {(item.budget_allocated !== null || item.budget_spent !== null) && (
          <div className="text-xs text-zinc-500 mt-1.5">
            Budget: ${fmtNum(item.budget_allocated)} allocated, ${fmtNum(item.budget_spent)} spent (manually entered)
          </div>
        )}

        {isManual && item.status !== "completed" && item.status !== "cancelled" && (
          <div className="mt-2 flex items-center gap-2">
            <WorkField label="Manual progress % (0-100)"><WorkInput
              value={progressInput}
              onChange={(e) => setProgressInput(e.target.value)}
              placeholder="Manual progress % (0-100)"
              className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-40"
            /></WorkField>
            <Btn onClick={() => run(() => updateInitiativeProgress(item.id, Number(progressInput)))} disabled={busy || !progressInput}>
              Record Progress
            </Btn>
          </div>
        )}

        {nextSteps[item.status]?.length > 0 && (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {nextSteps[item.status].map((s) => (
              <Btn key={s} onClick={() => run(() => updateInitiativeStatus(item.id, s))} disabled={busy} tone={s === "cancelled" ? "danger" : "muted"}>
                Mark {fmtStatus(s)}
              </Btn>
            ))}
          </div>
        )}
        {msg && <div className="text-xs text-red-400 mt-1">{msg}</div>}
      </div>
    </div>
  );
}

export function StrategicPlanningBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<StrategicPlanningOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"objectives" | "new_objective" | "initiatives" | "new_initiative">("objectives");

  // New Objective form state
  const [objQuarter, setObjQuarter] = useState("Q3");
  const [objYear, setObjYear] = useState(new Date().getFullYear());
  const [objDept, setObjDept] = useState("Sales");
  const [objTitle, setObjTitle] = useState("");
  const [objDesc, setObjDesc] = useState("");
  const [objTarget, setObjTarget] = useState("");
  const [objUnit, setObjUnit] = useState("");
  const [objBudget, setObjBudget] = useState("");
  const [objSaving, setObjSaving] = useState(false);
  const [objMsg, setObjMsg] = useState<string | null>(null);

  // New Initiative form state
  const [initName, setInitName] = useState("");
  const [initDept, setInitDept] = useState("Marketing");
  const [initType, setInitType] = useState<TrackingType>("manual");
  const [initDesc, setInitDesc] = useState("");
  const [initOwner, setInitOwner] = useState("");
  const [initLinkedId, setInitLinkedId] = useState("");
  const [initTargetMetric, setInitTargetMetric] = useState("");
  const [initBudget, setInitBudget] = useState("");
  const [initSaving, setInitSaving] = useState(false);
  const [initMsg, setInitMsg] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getStrategicPlanningOverview()
      .then((d) => {
        setData(d);
        if (!objYear) setObjYear(d.current_year);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Strategic Planning data."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), []);

  async function handleCreateObjective() {
    if (!objTitle.trim()) {
      setObjMsg("Title is required.");
      return;
    }
    setObjSaving(true);
    setObjMsg(null);
    try {
      await createObjective({
        quarter: objQuarter,
        year: objYear,
        department: objDept,
        title: objTitle,
        description: objDesc,
        target_value: objTarget ? Number(objTarget) : null,
        unit: objUnit,
        budget_allocated: objBudget ? Number(objBudget) : null,
      });
      setObjTitle("");
      setObjDesc("");
      setObjTarget("");
      setObjUnit("");
      setObjBudget("");
      setObjMsg("Objective created.");
      setTab("objectives");
      refresh();
    } catch (e) {
      setObjMsg(e instanceof Error ? e.message : "Unable to create objective.");
    } finally {
      setObjSaving(false);
    }
  }

  async function handleCreateInitiative() {
    if (!initName.trim()) {
      setInitMsg("Name is required.");
      return;
    }
    const catalogEntry = data?.tracking_type_catalog[initType];
    if (catalogEntry?.requires_linked_entity_id && !initLinkedId.trim()) {
      setInitMsg(`tracking_type '${initType}' requires a linked entity id (e.g. a real SITE- website id).`);
      return;
    }
    if (catalogEntry?.requires_target_metric && !initTargetMetric) {
      setInitMsg(`tracking_type '${initType}' requires a target metric value.`);
      return;
    }
    setInitSaving(true);
    setInitMsg(null);
    try {
      await createInitiative({
        name: initName,
        department: initDept,
        tracking_type: initType,
        description: initDesc,
        owner_employee_id: initOwner || null,
        linked_entity_id: initLinkedId || null,
        target_metric_value: initTargetMetric ? Number(initTargetMetric) : null,
        budget_allocated: initBudget ? Number(initBudget) : null,
      });
      setInitName("");
      setInitDesc("");
      setInitOwner("");
      setInitLinkedId("");
      setInitTargetMetric("");
      setInitBudget("");
      setInitMsg("Initiative created.");
      setTab("initiatives");
      refresh();
    } catch (e) {
      setInitMsg(e instanceof Error ? e.message : "Unable to create initiative.");
    } finally {
      setInitSaving(false);
    }
  }

  const rollup = data?.quarterly_rollup;
  const objectives = rollup?.objectives ?? [];
  const onTrackCount = (rollup?.status_counts?.on_track ?? 0) + (rollup?.status_counts?.achieved ?? 0);
  const atRiskCount = (rollup?.status_counts?.at_risk ?? 0) + (rollup?.status_counts?.behind ?? 0) + (rollup?.status_counts?.missed ?? 0);
  const initiatives = data?.initiatives ?? [];
  const activeInitiatives = (data?.initiatives_summary.by_status.planned ?? 0) + (data?.initiatives_summary.by_status.in_progress ?? 0);

  const currentInitType = data?.tracking_type_catalog[initType];

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="text-sm font-brand font-semibold">Strategic Planning</div>
        <div className="text-xs text-zinc-500 mt-0.5">
          Quarterly Objectives/Goals/Budgets, Department Planning, and Initiative Tracking. Status is computed
          live -- real for Sales/Service/Marketing off actual ledger pace, an honest manual self-report for
          every other department. A quarterly objective can be explicitly pushed into Performance Readiness&apos;s
          monthly goal (one-way, never automatic).
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      {loading ? (
        <div className="p-4 text-sm text-zinc-500">Loading…</div>
      ) : (
        <>
          <div className="grid grid-cols-4 gap-3 p-4 pb-0">
            <Kpi theme={theme} label={`${rollup?.quarter ?? ""} ${rollup?.year ?? ""} Objectives`} value={String(rollup?.count ?? 0)} color={RIBBON[0]} />
            <Kpi theme={theme} label="On Track / Achieved" value={String(onTrackCount)} color={RIBBON[1]} />
            <Kpi theme={theme} label="At Risk / Behind / Missed" value={String(atRiskCount)} color={RIBBON[3]} />
            <Kpi theme={theme} label="Active Initiatives" value={String(activeInitiatives)} color={RIBBON[2]} />
          </div>

          <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800 mt-3">
            {([
              ["objectives", "Objectives"],
              ["new_objective", "+ New Objective"],
              ["initiatives", "Initiatives"],
              ["new_initiative", "+ New Initiative"],
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

          <div className="flex-1 p-4">
            {tab === "objectives" ? (
              objectives.length === 0 ? (
                <div className="text-xs text-zinc-500">No objectives yet for {rollup?.quarter} {rollup?.year}. Use &quot;+ New Objective&quot; to add one.</div>
              ) : (
                <div className="space-y-4">
                  {Object.entries(rollup?.by_department ?? {}).map(([dept, deptObjs]) => (
                    <div key={dept}>
                      <div className="text-xs font-brand font-semibold uppercase tracking-wide text-zinc-500 mb-2">{dept}</div>
                      <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                        {deptObjs.map((o) => (
                          <ObjectiveCard key={o.id} theme={theme} obj={o} onRefresh={refresh} />
                        ))}
                      </div>
                    </div>
                  ))}
                </div>
              )
            ) : tab === "new_objective" ? (
              <div className={tc(theme, "rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 max-w-xl", "rounded-lg border border-zinc-200 bg-zinc-50 p-4 max-w-xl")}>
                <div className="text-xs font-brand font-semibold mb-3">New Quarterly Objective (ADMIN/OPERATIONS)</div>
                <div className="space-y-2">
                  <div className="flex gap-2">
                    <WorkField label="Quarter"><WorkSelect value={objQuarter} onChange={(e) => setObjQuarter(e.target.value)} className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200">
                      {QUARTERS.map((q) => <option key={q} value={q}>{q}</option>)}
                    </WorkSelect></WorkField>
                    <WorkField label="Year"><WorkInput type="number" value={objYear} onChange={(e) => setObjYear(Number(e.target.value))} className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-24" /></WorkField>
                    <WorkField label="Department"><WorkSelect value={objDept} onChange={(e) => setObjDept(e.target.value)} className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 flex-1">
                      {(data?.department_options ?? []).map((d) => <option key={d} value={d}>{d}</option>)}
                    </WorkSelect></WorkField>
                  </div>
                  <WorkField label="Title"><WorkInput value={objTitle} onChange={(e) => setObjTitle(e.target.value)} placeholder="Title (e.g. Sell 120 units this quarter)" className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full" /></WorkField>
                  <WorkField label="Description"><WorkTextarea value={objDesc} onChange={(e) => setObjDesc(e.target.value)} placeholder="Description" rows={2} className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full" /></WorkField>
                  <div className="flex gap-2">
                    <WorkField label="Target value (optional)"><WorkInput value={objTarget} onChange={(e) => setObjTarget(e.target.value)} placeholder="Target value (optional)" className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 flex-1" /></WorkField>
                    <WorkField label="Unit (units/$/leads/%)"><WorkInput value={objUnit} onChange={(e) => setObjUnit(e.target.value)} placeholder="Unit (units/$/leads/%)" className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-40" /></WorkField>
                  </div>
                  <WorkField label="Budget allocated (optional, $)"><WorkInput value={objBudget} onChange={(e) => setObjBudget(e.target.value)} placeholder="Budget allocated (optional, $)" className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full" /></WorkField>
                  {data?.goal_tracked_departments.includes(objDept.toLowerCase()) && (
                    <div className="text-xs text-zinc-500">
                      {objDept} status will be computed live against real quarterly pace. Set a target + unit to
                      also enable &quot;Sync to Monthly Goal&quot; afterward.
                    </div>
                  )}
                  <Btn onClick={handleCreateObjective} disabled={objSaving} tone="primary">
                    {objSaving ? "Creating…" : "Create Objective"}
                  </Btn>
                  {objMsg && <div className="text-xs text-zinc-400">{objMsg}</div>}
                </div>
              </div>
            ) : tab === "initiatives" ? (
              initiatives.length === 0 ? (
                <div className="text-xs text-zinc-500">No initiatives yet. Use &quot;+ New Initiative&quot; to add one.</div>
              ) : (
                <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
                  {initiatives.map((i) => (
                    <InitiativeCard key={i.id} theme={theme} item={i} onRefresh={refresh} />
                  ))}
                </div>
              )
            ) : (
              <div className={tc(theme, "rounded-lg border border-zinc-800 bg-zinc-900/40 p-4 max-w-xl", "rounded-lg border border-zinc-200 bg-zinc-50 p-4 max-w-xl")}>
                <div className="text-xs font-brand font-semibold mb-3">New Initiative (ADMIN/OPERATIONS)</div>
                <div className="space-y-2">
                  <WorkField label="Name"><WorkInput value={initName} onChange={(e) => setInitName(e.target.value)} placeholder="Name (e.g. New Website Launch, GPS Rollout, New Service Center)" className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full" /></WorkField>
                  <div className="flex gap-2">
                    <WorkField label="Department"><WorkSelect value={initDept} onChange={(e) => setInitDept(e.target.value)} className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 flex-1">
                      {(data?.department_options ?? []).map((d) => <option key={d} value={d}>{d}</option>)}
                    </WorkSelect></WorkField>
                    <WorkField label="Initiative type"><WorkSelect value={initType} onChange={(e) => setInitType(e.target.value as TrackingType)} className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 flex-1">
                      {Object.entries(data?.tracking_type_catalog ?? {}).map(([key, entry]) => (
                        <option key={key} value={key}>{entry.label}</option>
                      ))}
                    </WorkSelect></WorkField>
                  </div>
                  {currentInitType && (
                    <div className="text-xs text-zinc-500">{currentInitType.note}</div>
                  )}
                  <WorkField label="Description"><WorkTextarea value={initDesc} onChange={(e) => setInitDesc(e.target.value)} placeholder="Description" rows={2} className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full" /></WorkField>
                  <WorkField label="Owner employee id (optional"><WorkInput value={initOwner} onChange={(e) => setInitOwner(e.target.value)} placeholder="Owner employee id (optional, e.g. EMP-00001)" className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full" /></WorkField>
                  {currentInitType?.requires_linked_entity_id && (
                    <WorkField label="Linked website id"><WorkInput value={initLinkedId} onChange={(e) => setInitLinkedId(e.target.value)} placeholder="Linked website id (e.g. SITE-00001)" className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full" /></WorkField>
                  )}
                  {currentInitType?.requires_target_metric && (
                    <WorkField label="Target device count"><WorkInput value={initTargetMetric} onChange={(e) => setInitTargetMetric(e.target.value)} placeholder="Target device count" className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full" /></WorkField>
                  )}
                  <WorkField label="Budget allocated (optional, $)"><WorkInput value={initBudget} onChange={(e) => setInitBudget(e.target.value)} placeholder="Budget allocated (optional, $)" className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full" /></WorkField>
                  <Btn onClick={handleCreateInitiative} disabled={initSaving} tone="primary">
                    {initSaving ? "Creating…" : "Create Initiative"}
                  </Btn>
                  {initMsg && <div className="text-xs text-zinc-400">{initMsg}</div>}
                </div>
              </div>
            )}

            {data?.not_yet_tracked && Object.keys(data.not_yet_tracked).length > 0 && (
              <div className={tc(theme, "mt-4 text-xs text-zinc-500 bg-zinc-900/60 border border-zinc-800 rounded px-3 py-2", "mt-4 text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
                {Object.entries(data.not_yet_tracked).map(([k, v]) => (
                  <div key={k} className="mb-1">
                    <span className="font-semibold">{k}:</span> {v}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
