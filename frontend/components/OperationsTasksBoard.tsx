"use client";
import { WorkField } from "./WorkField";
import {WorkButton, WorkToolbar, WorkSelect, WorkInput} from "./WorkspaceUi";
import {RecordTable} from "./RecordTable";
import {CollectionPagination, collectionPage} from "./CollectionPagination";
import {OverviewMetrics} from "./DepartmentOverview";

// Operations' "Tasks" item -- the "Universal Operations Work Queue" (session 106
// follow-up #3, "keep going" autonomous continuation). Sam's spec: "Assign Owner
// (Inventory Manager, Title Clerk, Service Manager, Lot Manager, Accounting), SLA
// Tracking with auto-escalation, Bulk Actions, Workflow Actions." Backend:
// core/operations_tasks.py / _api.py.
//
// Two ways a task lands here: created directly (the "+ New Task" form), or synced
// (the "Sync From Signals" button) from real graph gaps core/operations_menu.py's
// old read-only tasks() view already surfaced -- wholesale candidates, lot-audit
// discrepancies, open compliance alerts -- now made into real, assignable,
// trackable tickets instead of just a reported list. SLA badges (hours_open/
// is_overdue) are computed live server-side on every fetch.

import { useEffect, useMemo, useState } from "react";
import {
  listOperationsTasks,
  getOperationsTaskStats,
  getOperationsTaskCatalog,
  createOperationsTask,
  updateOperationsTask,
  closeOperationsTask,
  escalateOperationsTask,
  bulkAssignOperationsTasks,
  bulkCloseOperationsTasks,
  bulkReprioritizeOperationsTasks,
  syncOperationsTasks,
  type OperationsTask,
  type OperationsTaskStats,
  type OperationsTaskCatalog,
  type TaskStatus,
  type TaskPriority,
  type OwnerBucket,
} from "@/lib/operationsTasks";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function NewTaskForm({ theme, catalog, onCreated }: { theme: Theme; catalog: OperationsTaskCatalog; onCreated: () => void }) {
  const [taskType, setTaskType] = useState<OperationsTaskCatalog["task_types"][number]>(catalog.task_types[catalog.task_types.length - 1] || "custom");
  const [detail, setDetail] = useState("");
  const [priority, setPriority] = useState<TaskPriority>("normal");
  const [ownerBucket, setOwnerBucket] = useState<OwnerBucket>("Unassigned");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);



  async function submit() {
    if (busy) return;
    if (!detail.trim()) {
      setError("A detail/description is required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await createOperationsTask({ task_type: taskType, detail: detail.trim(), priority, owner_bucket: ownerBucket });
      setDetail("");
      onCreated();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="work-form" aria-label="Create task" onSubmit={e=>{e.preventDefault();void submit();}}>
      <h3>New task</h3>
      {error && <div role="alert">{error}</div>}
      <div className="work-form-grid">
        <WorkField label="Task type"><WorkSelect value={taskType} onChange={(e) => setTaskType(e.target.value as OperationsTaskCatalog["task_types"][number])} disabled={busy}>
          {catalog.task_types.map((t) => (
            <option key={t} value={t}>{t.replace(/_/g, " ")}</option>
          ))}
        </WorkSelect></WorkField>
        <WorkField label="Priority"><WorkSelect value={priority} onChange={(e) => setPriority(e.target.value as TaskPriority)} disabled={busy}>
          {catalog.priorities.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </WorkSelect></WorkField>
        <WorkField label="Responsible team"><WorkSelect value={ownerBucket} onChange={(e) => setOwnerBucket(e.target.value as OwnerBucket)} disabled={busy}>
          {catalog.owner_buckets.map((b) => (
            <option key={b} value={b}>{b}</option>
          ))}
        </WorkSelect></WorkField>
      </div>
      <div className="work-form-grid">
        <WorkField label="Detail / description"><WorkInput
          value={detail}
          onChange={(e) => setDetail(e.target.value)}
          placeholder="Detail / description…"
          required disabled={busy}
        /></WorkField>
        </div><div className="work-actions"><WorkButton type="submit" disabled={busy} variant="primary">{busy?"Creating…":"Create task"}</WorkButton>
      </div>
    </form>
  );
}

function TaskRow({
  theme,
  task,
  selected,
  onToggleSelect,
  onChanged,
}: {
  theme: Theme;
  task: OperationsTask;
  selected: boolean;
  onToggleSelect: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);

  async function withBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setActionError("");
    try {
      await fn();
      onChanged();
    } catch {
      setActionError("Task update could not be confirmed. Refresh the task before trying again.");
    } finally {
      setBusy(false);
    }
  }

  const [actionError, setActionError] = useState("");

  return <tr><td><WorkInput type="checkbox" aria-label={`Select task ${task.id}`} checked={selected} onChange={onToggleSelect} disabled={busy}/></td><td><strong className="work-record-title">{task.detail}</strong><span className="work-record-meta">{task.task_type.replace(/_/g," ")} · {task.id}</span><span className="work-record-meta">Created {fmt(task.created_at)}{task.derived?" · Synced from signals":""}</span>{actionError&&<div role="alert">{actionError} <WorkButton disabled={busy} onClick={onChanged}>Refresh task</WorkButton></div>}</td><td>{task.status.replace("_"," ")}{task.is_overdue&&<span className="work-record-meta">Overdue · {task.hours_open}h open</span>}</td><td>{task.priority}</td><td>{task.owner_bucket}<span className="work-record-meta">{task.assigned_to||"No individual assigned"}</span></td><td><div className="work-actions">{task.status==="open"&&<WorkButton variant="primary" disabled={busy} onClick={()=>withBusy(()=>updateOperationsTask(task.id,{status:"in_progress"}))}>Start</WorkButton>}{task.status!=="closed"&&<><WorkButton disabled={busy} onClick={()=>withBusy(()=>escalateOperationsTask(task.id))}>Escalate</WorkButton><WorkButton disabled={busy} onClick={()=>withBusy(()=>closeOperationsTask(task.id))}>Close</WorkButton></>}</div></td></tr>;

}

export function OperationsTasksBoard({ theme }: { theme: Theme }) {
  const [page,setPage]=useState(0),[pageSize,setPageSize]=useState(25);
  const [catalog, setCatalog] = useState<OperationsTaskCatalog | null>(null);
  const [tasks, setTasks] = useState<OperationsTask[]>([]);
  const [stats, setStats] = useState<OperationsTaskStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());

  const [statusFilter, setStatusFilter] = useState<TaskStatus | "">("");
  const [ownerFilter, setOwnerFilter] = useState<OwnerBucket | "">("");
  const [overdueOnly, setOverdueOnly] = useState(false);

  function refresh() {
    setLoading(true);
    Promise.all([
      listOperationsTasks({
        status: statusFilter || undefined,
        owner_bucket: ownerFilter || undefined,
        overdue_only: overdueOnly || undefined,
      }),
      getOperationsTaskStats(),
    ])
      .then(([t, s]) => {
        setTasks(t.tasks);
        setPage(0);
        setStats(s);
        setSelectedIds(new Set());
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    getOperationsTaskCatalog().then(setCatalog).catch(() => {});
  }, []);

  useEffect(refresh, [statusFilter, ownerFilter, overdueOnly]);

  async function handleSync() {
    setSyncing(true);
    setError(null);
    try {
      await syncOperationsTasks();
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSyncing(false);
    }
  }

  const visiblePage=collectionPage(tasks.length,page,pageSize);
  const selectedArray = useMemo(() => Array.from(selectedIds), [selectedIds]);

  async function bulkAction(fn: () => Promise<unknown>) {
    setError(null);
    try {
      await fn();
      refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function toggleSelect(id: string) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  const selectClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white", "bg-white border-zinc-300 text-black");

  return (
    <div className="work-stack">
      <OverviewMetrics label="Task snapshot" items={[{label:"Total tasks",value:stats?.total},{label:"Open",value:stats?.open},{label:"Overdue",value:stats?.overdue},{label:"Closed",value:stats?.closed}].map(item=>({...item,icon:"operations",detail:loading?"Loading current tasks…":"Current matching work"}))}/>


      <div className="work-stack">
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        {catalog && <NewTaskForm theme={theme} catalog={catalog} onCreated={refresh} />}

        <WorkToolbar label="Task filters">
          <WorkField label="Status"><WorkSelect value={statusFilter} onChange={(e) => setStatusFilter(e.target.value as TaskStatus | "")} className={`rounded-md border px-2 py-1 text-xs ${selectClass}`}>
            <option value="">All Statuses</option>
            {catalog?.statuses.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
          </WorkSelect></WorkField>
          <WorkField label="Owner"><WorkSelect value={ownerFilter} onChange={(e) => setOwnerFilter(e.target.value as OwnerBucket | "")} className={`rounded-md border px-2 py-1 text-xs ${selectClass}`}>
            <option value="">All Owners</option>
            {catalog?.owner_buckets.map((b) => <option key={b} value={b}>{b}</option>)}
          </WorkSelect></WorkField>
          <label className="flex items-center gap-1.5 text-xs cursor-pointer">
            <WorkInput type="checkbox" checked={overdueOnly} onChange={(e) => setOverdueOnly(e.target.checked)} />
            Overdue only
          </label>
          <WorkButton disabled={syncing} onClick={handleSync} >
            {syncing ? "Syncing…" : "↻ Sync From Signals"}
          </WorkButton>
        </WorkToolbar>

        {selectedArray.length > 0 && catalog && (
          <div className={tc(theme, "rounded-lg border border-brand-blue/50 bg-brand-blue/10 p-2.5 flex flex-wrap items-center gap-1.5", "rounded-lg border border-brand-blue/50 bg-blue-50 p-2.5 flex flex-wrap items-center gap-1.5")}>
            <span className="text-xs font-medium">{selectedArray.length} selected</span>
            <WorkField label="Assign to owner"><WorkSelect
              className={`rounded-md border px-2 py-1 text-xs ${selectClass}`}
              onChange={(e) => {
                if (e.target.value) {
                  bulkAction(() => bulkAssignOperationsTasks(selectedArray, e.target.value as OwnerBucket));
                  e.target.value = "";
                }
              }}
              defaultValue=""
            >
              <option value="" disabled>Assign to owner…</option>
              {catalog.owner_buckets.map((b) => <option key={b} value={b}>{b}</option>)}
            </WorkSelect></WorkField>
            <WorkField label="Set priority"><WorkSelect
              className={`rounded-md border px-2 py-1 text-xs ${selectClass}`}
              onChange={(e) => {
                if (e.target.value) {
                  bulkAction(() => bulkReprioritizeOperationsTasks(selectedArray, e.target.value as TaskPriority));
                  e.target.value = "";
                }
              }}
              defaultValue=""
            >
              <option value="" disabled>Set priority…</option>
              {catalog.priorities.map((p) => <option key={p} value={p}>{p}</option>)}
            </WorkSelect></WorkField>
            <WorkButton onClick={() => bulkAction(() => bulkCloseOperationsTasks(selectedArray))} >Close Selected</WorkButton>
          </div>
        )}

        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tasks.length === 0 ? (
          <div className="text-sm text-zinc-500">No tasks match these filters.</div>
        ) : (
          <><RecordTable label="Tasks" paginate={false}><thead><tr><th scope="col">Select</th><th scope="col">Task</th><th scope="col">Status</th><th scope="col">Priority</th><th scope="col">Owner</th><th scope="col">Actions</th></tr></thead><tbody>{tasks.slice(visiblePage.start,visiblePage.end).map(t=><TaskRow key={t.id} theme={theme} task={t} selected={selectedIds.has(t.id)} onToggleSelect={()=>toggleSelect(t.id)} onChanged={refresh}/>)}</tbody></RecordTable><CollectionPagination label="Tasks" total={tasks.length} page={visiblePage.current} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={setPageSize}/></>
        )}

        {stats && Object.keys(stats.by_owner_bucket).length > 0 && (
          <div className="text-xs text-zinc-600 pt-2">
            Open by owner: {Object.entries(stats.by_owner_bucket).map(([k, v]) => `${k} (${v})`).join(" · ")}
          </div>
        )}
      </div>
    </div>
  );
}
