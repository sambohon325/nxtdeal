"use client";

import styles from "./page.module.css";

type Work = { id: string; title: string; category: string; status: string; assigned_to: string; due_at: string; overdue: boolean; resolution?: string };
type Report = { department: string; as_of: string; records: { id: string; entity_type: string; attributes: Record<string, unknown> }[]; exceptions: { record_id: string; reasons: string[] }[]; work_items: Work[]; totals: Record<string, number>; truncated: boolean; limitations: string[] };
function isReport(value: unknown): value is Report {
  return typeof value === "object" && value !== null && "work_items" in value && "exceptions" in value && "totals" in value;
}
export default function DepartmentWorkbench({ result, busy, prepare }: { result: unknown; busy: boolean; prepare: (capability: string, input: unknown) => void }) {
  if (!isReport(result)) return <pre className={styles.result}>{JSON.stringify(result, null, 2)}</pre>;
  return <div>
    <h3>{result.department.toUpperCase()} operating review</h3>
    <p>Observed as of {result.as_of}. {result.totals.records} records · {result.totals.exceptions} exceptions · {result.totals.open_work} open assignments · {result.totals.overdue_work} overdue · {result.totals.completed_work} completed</p>
    {result.truncated && <p>Showing up to 100 entries per section. Use a record ID above to inspect a specific record or work item.</p>}
    <h3>Exceptions to review</h3>
    {result.exceptions.length === 0 ? <p>No exceptions found by the available rules. This is not a complete audit.</p> : result.exceptions.map(item => <article className={styles.workflow} key={item.record_id}><strong>{item.record_id}</strong><ul>{item.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul></article>)}
    <h3>Assign department work</h3><p>Use a source record ID below. HR supports onboarding and training assignments against an employee record. Assignments and outcome updates pass through the action review queue.</p>
    <form onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); prepare(`${result.department}.work.create`, Object.fromEntries(data)); }}>
      <label className={styles.field}>Source record ID<input name="record_id" list="department-source-records" required maxLength={160} /><datalist id="department-source-records">{result.records.map(record => <option key={record.id} value={record.id}>{record.entity_type}</option>)}</datalist></label>
      <label className={styles.field}>Work to complete<input name="title" required maxLength={240} /></label>
      <label className={styles.field}>Assigned employee ID<input name="assigned_to" required maxLength={160} /></label>
      <label className={styles.field}>Due at (ISO timestamp with timezone)<input name="due_at" required placeholder="2026-10-05T17:00:00-05:00" /></label>
      <label className={styles.field}>Category<select name="category">{(result.department === "hr" ? ["onboarding", "training", "policy_review"] : ["follow_up", "document_review", "reconciliation", "parts_follow_up", "inventory_review", "policy_review", "exception"]).map(category => <option key={category} value={category}>{category.replaceAll("_", " ")}</option>)}</select></label>
      <button disabled={busy}>Prepare assignment</button>
    </form>
    <h3>Assigned work</h3>
    {result.work_items.length === 0 && <p>No assignments recorded for this department.</p>}
    {result.work_items.map(work => <article className={styles.workflow} key={work.id}><strong>{work.title}</strong><p>{work.id} · {work.status} · {work.assigned_to} · Due {work.due_at}{work.overdue ? " · OVERDUE" : ""}</p>{work.resolution && <p>{work.resolution}</p>}{!["completed", "cancelled"].includes(work.status) && <form onSubmit={event => { event.preventDefault(); const data = new FormData(event.currentTarget); prepare(`${result.department}.work.update`, { record_id: work.id, status: data.get("status"), resolution: data.get("resolution") }); }}><label className={styles.field}>Next status<select name="status"><option value="in_progress">In progress</option><option value="blocked">Blocked</option><option value="completed">Completed</option><option value="cancelled">Cancelled</option></select></label><label className={styles.field}>Outcome or evidence reference<input name="resolution" required maxLength={500} /></label><button disabled={busy}>Prepare outcome update</button></form>}</article>)}
    <details><summary>Source records ({result.records.length})</summary><pre className={styles.result}>{JSON.stringify(result.records, null, 2)}</pre></details>
    {result.limitations.map(note => <p key={note}>{note}</p>)}
  </div>;
}
