"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Administration's "Workflow Automation" item (Administration Control
// Center rebuild, continuing 2026-07-18/19). A real, admin-configurable
// "if this real condition, then this real action" rule engine
// (core/workflow_automation.py) over real graph signals -- a Deal stalled
// in financing/contract, a Lead with no contact logged, an unsold Vehicle
// priced at/above a threshold -- firing a real action (a trackable
// OperationsTask, or a real notification DM) the moment a rule's condition
// is met. Evaluated on-demand ("Run Rules Now") or implicitly on every
// dashboard fetch -- deliberately NOT a third live background scheduler
// (see the backend module's own docstring for the full reasoning). This
// board is Administration-only, matching this whole rebuild's convention.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getAutomationDashboard,
  runRulesNow,
  createAutomationRule,
  setAutomationRuleActive,
  deleteAutomationRule,
  runSingleAutomationRule,
  listAutomationExecutions,
  type AutomationDashboard,
  type AutomationRule,
  type AutomationExecution,
  type TriggerCatalogEntry,
  type ActionCatalogEntry,
} from "@/lib/workflowAutomation";

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

function Input({ value, onChange, placeholder, type }: { value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <WorkField label={placeholder || "Rule value"}><WorkInput
      type={type || "text"}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 w-full"
    /></WorkField>
  );
}

function Select({ value, onChange, options, label }: { label:string; value: string; onChange: (v: string) => void; options: { value: string; label: string }[] }) {
  return (
    <WorkField label={label}><WorkSelect
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 w-full"
    >
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.label}
        </option>
      ))}
    </WorkSelect></WorkField>
  );
}

function paramDefault(kind: string, def: unknown): string {
  if (def === undefined || def === null) return "";
  return String(def);
}

function ParamFields({
  catalogEntry,
  values,
  onChange,
}: {
  catalogEntry: TriggerCatalogEntry | ActionCatalogEntry | undefined;
  values: Record<string, string>;
  onChange: (key: string, v: string) => void;
}) {
  if (!catalogEntry) return null;
  return (
    <div className="space-y-1.5">
      {catalogEntry.params.map((p) => (
        <div key={p.key} className="grid grid-cols-3 gap-1.5 items-center">
          <span className="text-xs text-zinc-500">{p.label}</span>
          <div className="col-span-2">
            {p.kind === "enum" ? (
              <Select label={p.label}
                value={values[p.key] ?? paramDefault(p.kind, p.default)}
                onChange={(v) => onChange(p.key, v)}
                options={(p.options || []).map((o) => ({ value: o, label: o }))}
              />
            ) : (
              <Input
                type={p.kind === "number" ? "number" : "text"}
                value={values[p.key] ?? paramDefault(p.kind, p.default)}
                onChange={(v) => onChange(p.key, v)}
                placeholder={p.label}
              />
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

export function WorkflowAutomationBoard({ theme }: { theme: Theme }) {
  const [tab, setTab] = useState<"rules" | "create" | "log">("rules");
  const [dashboard, setDashboard] = useState<AutomationDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [runningNow, setRunningNow] = useState(false);

  const [execRuleFilter, setExecRuleFilter] = useState<string>("all");
  const [executions, setExecutions] = useState<AutomationExecution[]>([]);
  const [execLoading, setExecLoading] = useState(false);

  // create-rule form state
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [triggerType, setTriggerType] = useState("");
  const [actionType, setActionType] = useState("");
  const [triggerParams, setTriggerParams] = useState<Record<string, string>>({});
  const [actionParams, setActionParams] = useState<Record<string, string>>({});
  const [createError, setCreateError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  function refresh(runNow = true) {
    setLoading(true);
    setError(null);
    getAutomationDashboard(runNow)
      .then((d) => {
        setDashboard(d);
        if (!triggerType && d.trigger_catalog.length > 0) setTriggerType(d.trigger_catalog[0].type);
        if (!actionType && d.action_catalog.length > 0) setActionType(d.action_catalog[0].type);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Workflow Automation data."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(false), []);

  useEffect(() => {
    if (tab !== "log") return;
    setExecLoading(true);
    listAutomationExecutions({ ruleId: execRuleFilter === "all" ? undefined : execRuleFilter, limit: 100 })
      .then((r) => setExecutions(r.executions))
      .catch(() => setExecutions([]))
      .finally(() => setExecLoading(false));
  }, [tab, execRuleFilter]);

  function handleRunNow() {
    setRunningNow(true);
    runRulesNow()
      .then(() => refresh(false))
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to run rules."))
      .finally(() => setRunningNow(false));
  }

  function handleToggleActive(rule: AutomationRule) {
    setAutomationRuleActive(rule.id, !rule.is_active)
      .then(() => refresh(false))
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to update rule."));
  }

  function handleDelete(rule: AutomationRule) {
    deleteAutomationRule(rule.id)
      .then(() => refresh(false))
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to delete rule."));
  }

  function handleRunSingle(rule: AutomationRule) {
    runSingleAutomationRule(rule.id)
      .then(() => refresh(false))
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to run rule."));
  }

  function handleCreate() {
    setCreateError(null);
    if (!name.trim() || !triggerType || !actionType) {
      setCreateError("Name, trigger, and action are all required.");
      return;
    }
    if (actionType === "send_notification_dm" && !actionParams["notify_employee_id"]) {
      setCreateError("send_notification_dm requires a Notify Employee ID (e.g. EMP-00001).");
      return;
    }
    setCreating(true);
    createAutomationRule({
      name,
      description,
      trigger_type: triggerType,
      trigger_params: triggerParams,
      action_type: actionType,
      action_params: actionParams,
    })
      .then(() => {
        setName("");
        setDescription("");
        setTriggerParams({});
        setActionParams({});
        setTab("rules");
        refresh(false);
      })
      .catch((e) => setCreateError(e instanceof Error ? e.message : "Unable to create rule."))
      .finally(() => setCreating(false));
  }

  const rules = dashboard?.rules ?? [];
  const triggerCatalog = dashboard?.trigger_catalog ?? [];
  const actionCatalog = dashboard?.action_catalog ?? [];
  const selectedTrigger = triggerCatalog.find((t) => t.type === triggerType);
  const selectedAction = actionCatalog.find((a) => a.type === actionType);
  const lastEval = dashboard?.last_evaluation;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Rules" value={String(rules.length)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Active Rules" value={String(dashboard?.active_rule_count ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Fired This Pass" value={String(lastEval?.fired_count ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Total Executions Logged" value={String(dashboard?.recent_executions.length ?? 0)} color={RIBBON[3]} />
      </div>

      <div className="flex items-center justify-between gap-2 px-4 py-2 border-b border-zinc-800">
        <div className="flex items-center gap-1.5">
          {([
            ["rules", "Rules"],
            ["create", "+ New Rule"],
            ["log", "Execution Log"],
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
        <Btn onClick={handleRunNow} disabled={runningNow} tone="primary">
          {runningNow ? "Running…" : "▶ Run Rules Now"}
        </Btn>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "rules" ? (
          <div className="space-y-4">
            <div className="text-xs text-zinc-500">
              Evaluated live on every fetch of this dashboard and via &quot;Run Rules Now&quot; --
              deliberately not a background scheduler (see the rule engine&apos;s own docstring).
              Each rule fires at most once per matched entity (permanent dedup, logged to the
              Execution Log below).
            </div>
            <div className="space-y-1.5">
              {rules.map((r) => (
                <div key={r.id} className="text-xs px-3 py-2 rounded border border-zinc-800">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <span className="text-zinc-200 font-medium">{r.name}</span>
                      <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${r.is_active ? "bg-emerald-950/40 text-emerald-300" : "bg-zinc-800 text-zinc-500"}`}>
                        {r.is_active ? "active" : "disabled"}
                      </span>
                    </div>
                    <div className="flex items-center gap-1.5 shrink-0">
                      <Btn onClick={() => handleRunSingle(r)}>Run Now</Btn>
                      <Btn onClick={() => handleToggleActive(r)}>{r.is_active ? "Disable" : "Enable"}</Btn>
                      <Btn onClick={() => handleDelete(r)} tone="danger">
                        Delete
                      </Btn>
                    </div>
                  </div>
                  <div className="text-xs text-zinc-500 mt-1">
                    IF {r.trigger_type} ({JSON.stringify(r.trigger_params)}) THEN {r.action_type} (
                    {JSON.stringify(r.action_params)})
                  </div>
                  <div className="text-xs text-zinc-600 mt-0.5">
                    fired {r.times_fired}x · created by {r.created_by} · last run {fmt(r.last_run_at)}
                  </div>
                  {r.description && <div className="text-xs text-zinc-500 mt-0.5">{r.description}</div>}
                </div>
              ))}
              {rules.length === 0 && <div className="text-xs text-zinc-500">No automation rules yet.</div>}
            </div>
          </div>
        ) : tab === "create" ? (
          <div className="space-y-4 max-w-xl">
            {createError && <div className="text-xs text-red-400">{createError}</div>}
            <div>
              <div className="text-xs text-zinc-500 mb-1">Rule Name</div>
              <Input value={name} onChange={setName} placeholder="e.g. Notify Finance on stalled deals" />
            </div>
            <div>
              <div className="text-xs text-zinc-500 mb-1">Description (optional)</div>
              <Input value={description} onChange={setDescription} placeholder="Why this rule exists" />
            </div>

            <div className="rounded border border-zinc-800 p-3 space-y-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-400">
                Trigger — IF this real condition is met
              </div>
              <Select label="Trigger condition"
                value={triggerType}
                onChange={(v) => {
                  setTriggerType(v);
                  setTriggerParams({});
                }}
                options={triggerCatalog.map((t) => ({ value: t.type, label: t.label }))}
              />
              {selectedTrigger && <div className="text-xs text-zinc-500">{selectedTrigger.description}</div>}
              <ParamFields
                catalogEntry={selectedTrigger}
                values={triggerParams}
                onChange={(k, v) => setTriggerParams((p) => ({ ...p, [k]: v }))}
              />
            </div>

            <div className="rounded border border-zinc-800 p-3 space-y-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-400">
                Action — THEN take this real action
              </div>
              <Select label="Action"
                value={actionType}
                onChange={(v) => {
                  setActionType(v);
                  setActionParams({});
                }}
                options={actionCatalog.map((a) => ({ value: a.type, label: a.label }))}
              />
              {selectedAction && <div className="text-xs text-zinc-500">{selectedAction.description}</div>}
              <ParamFields
                catalogEntry={selectedAction}
                values={actionParams}
                onChange={(k, v) => setActionParams((p) => ({ ...p, [k]: v }))}
              />
              {actionType === "send_notification_dm" && (
                <div className="text-xs text-amber-400">
                  Notify Employee ID must be a real employee id (e.g. EMP-00001).
                </div>
              )}
            </div>

            <Btn onClick={handleCreate} disabled={creating} tone="primary">
              {creating ? "Creating…" : "Create Rule"}
            </Btn>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="text-xs text-zinc-500">
              Every real, deduped rule firing -- one AutomationExecution entry per (rule, matched
              entity) pair, permanently, not a re-arming state machine.
            </div>
            <div className="flex items-center gap-1.5">
              <WorkButton type="submit"
                onClick={() => setExecRuleFilter("all")}
                className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${execRuleFilter === "all" ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
              >
                All Rules
              </WorkButton>
              {rules.map((r) => (
                <WorkButton type="submit"
                  key={r.id}
                  onClick={() => setExecRuleFilter(r.id)}
                  className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${execRuleFilter === r.id ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
                >
                  {r.name}
                </WorkButton>
              ))}
            </div>
            {execLoading ? (
              <div className="text-sm text-zinc-500">Loading…</div>
            ) : (
              <div className="space-y-1">
                {executions.map((e) => (
                  <div key={e.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800">
                    <span className="text-zinc-200">{e.detail}</span>
                    <div className="text-xs text-zinc-500 mt-0.5">
                      {e.rule_name} · {e.action_type} → {e.target_entity_id} · {fmt(e.fired_at)}
                    </div>
                  </div>
                ))}
                {executions.length === 0 && <div className="text-xs text-zinc-500">No executions logged yet.</div>}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
