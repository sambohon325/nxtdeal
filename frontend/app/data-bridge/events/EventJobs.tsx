"use client";
import {useEffect, useState} from "react";
import styles from "../page.module.css";
import PayloadCleanup from "../PayloadCleanup";
import {request, type EventRow, type ValueConflict} from "./api";

type Summary = {id: string; profile_id: string; status: string; created_at: string; row_count: number};
type JobPage = {jobs: Summary[]; next_before_id: string | null; total_jobs: number};
type Receipt = {profile_proposed_by: string; profile_approved_by: string; activated_by: string; activated_at: string; checksum: string; duplicate_rows: number; created: {event_id: string; canonical_id: string; projection: string}[]};
type Ingestion = {status: string; receipt_id?: string; binding_revision?: string; environment?: string; received_at?: string; authorized_by?: string; checksum?: string; notice: string};
type Job = {ingestion_evidence?: Ingestion | null; created_principal?: string; payload_cleanup?: {row_count: number; removed_at: string; removed_by: string}; id: string; system_id: string; profile_id: string; status: string; rows: EventRow[]; preview: EventRow[]; validation_hash?: string; identity_reviews?: Record<string, string>; activation_available: boolean; receipt_integrity: string; activation_receipt?: Receipt; source_evidence: {export_sha256: string; byte_count: number}};
type History = {source: {source_namespace: string; external_id: string}; legacy_conflicts?: ValueConflict[]; canonical_id: string; current_values: Record<string, string>; receipt_integrity: string; notice: string; observation: {occurred_at: string; imported_at: string; time_semantics: string; identity_resolution: string; values: Record<string, string>}};
function Values({values}: {values: Record<string, string>}) {return <dl>{Object.entries(values).map(([field, value]) => <div key={field}><dt>{field.replaceAll("_", " ")}</dt><dd>{value}</dd></div>)}</dl>;}
function Conflicts({items}: {items?: ValueConflict[]}) {return <>{items?.map(item => <p key={item.field} role="status">This record stores different {item.field.replaceAll("_", " ")} values: {String(item.canonical_value)} / {String(item.legacy_value)}. Confirm which is correct before linking.</p>)}</>;}
type Action = (path: string, body: unknown) => Promise<void>;
function IdentityDecision({job, row, busy, action}: {job: Job; row: EventRow; busy: boolean; action: Action}) {
  const [choice, setChoice] = useState("");
  const [reason, setReason] = useState("");
  const existing = job.identity_reviews?.[String(row.row_number)];
  return <div>
    {(row.candidate_records || []).map(candidate => <article key={candidate.id}><h4>Candidate {candidate.id}</h4><Values values={candidate.values} /><Conflicts items={candidate.legacy_conflicts} /></article>)}
    {row.candidate_signature && row.status === "quarantined" && <><label>Identity decision for row {row.row_number}<select disabled={busy} value={choice} onChange={event => setChoice(event.target.value)}><option value="">Choose after reviewing evidence</option>{(row.candidates || []).map(id => <option key={id} value={id}>Link to {id}; preserve current values</option>)}<option value="__separate__">Keep as a separate lead</option></select></label><p>Linking adds source history without overwriting the existing lead. Keeping separate creates a distinct lead despite the possible match.</p></>}
    {(existing || row.candidate_signature) && <label>Identity review reason for row {row.row_number}<input disabled={busy} value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label>}
    {row.candidate_signature && row.status === "quarantined" && <button disabled={busy || !choice || reason.trim().length < 8} onClick={() => action(`/event-imports/${job.id}/rows/${row.row_number}/identity`, {action: choice === "__separate__" ? "keep_separate" : "link", target_id: choice === "__separate__" ? null : choice, reason, candidate_signature: row.candidate_signature})}>Record identity decision for row {row.row_number}</button>}
    {existing && <button disabled={busy || reason.trim().length < 8} onClick={() => action(`/event-imports/${job.id}/rows/${row.row_number}/identity/withdraw`, {reason})}>Withdraw identity decision for row {row.row_number}</button>}
  </div>;
}
function JobDetails({job, busy, action, onRemoved}: {job: Job; busy: boolean; action: Action; onRemoved: () => Promise<void>}) {
  const [ack, setAck] = useState(false);
  const [reason, setReason] = useState("");
  const [history, setHistory] = useState<History | null>(null);
  const [historyError, setHistoryError] = useState("");
  const [historyBusy, setHistoryBusy] = useState(false);
  const terminal = ["activated", "cancelled"].includes(job.status);
  async function perform(path: string, body: unknown) {setAck(false); await action(path, body);}
  async function showHistory(row: EventRow | string) {
    setHistoryBusy(true); setHistory(null); setHistoryError("");
    try {setHistory(typeof row === "string" ? await request(`/event-observations/${encodeURIComponent(row)}`) : await request("/event-lineage", {system_id: job.system_id, source_namespace: row.source_namespace, external_id: row.external_id}));}
    catch (problem) {setHistoryError(problem instanceof Error ? problem.message : "Source history unavailable.");}
    finally {setHistoryBusy(false);}
  }
  return <article id={`event-job-${job.id}`}><h3>{job.id} - {job.status}</h3><p>Profile {job.profile_id} | {job.payload_cleanup?.row_count ?? job.rows.length} source events | {job.source_evidence.byte_count} source bytes</p><p>Original file fingerprint: <code>{job.source_evidence.export_sha256}</code></p>
    {job.ingestion_evidence ? <section><h4>Signed gateway delivery evidence</h4><p>{job.ingestion_evidence.notice}</p>
      <p>Delivery evidence: {job.ingestion_evidence.status}</p>{job.ingestion_evidence.status === "consistent" && <><p>Received {job.ingestion_evidence.received_at} through revision {job.ingestion_evidence.binding_revision} · Environment {job.ingestion_evidence.environment}.</p><p>Gateway enabled by {job.ingestion_evidence.authorized_by}. {job.status === "activated" ? "Human activation is recorded separately below." : "Delivery receipt remains separate from human approval."}</p><details><summary>Delivery receipt fingerprint</summary><p>{job.ingestion_evidence.receipt_id}</p><code>{job.ingestion_evidence.checksum}</code></details></>}
    </section> : <p>Batch staged through an authenticated upload{job.created_principal === "api" ? " using API credentials" : job.created_principal === "session" ? " using an administrator session" : "; original credential type was not recorded"}.</p>}
    {!terminal && <button disabled={busy} onClick={() => perform(`/event-imports/${job.id}/validate`, {})}>Validate event batch</button>}
    {job.payload_cleanup ? <p role="status">The staging copy was removed by {job.payload_cleanup.removed_by} at {job.payload_cleanup.removed_at}. Original source observations and imported lead records remain; this batch cannot be revalidated.</p> : <p>Review mapped source facts, creation times and identity decisions below. Unresolved matches or conflicts block the whole batch.</p>}
    {(job.preview.length ? job.preview : job.rows).map(row => <article key={row.row_number}><h4>Row {row.row_number}: {row.status}{row.effect ? ` - ${row.effect.replaceAll("_", " ")}` : ""}</h4><p>{row.source_namespace} / {row.external_id} | Created {row.occurred_at}</p>{row.error_code && <p role="status">{row.error_code.replaceAll("_", " ")}</p>}<Values values={row.values || {}} />
      {!terminal && <IdentityDecision key={`${row.row_number}-${row.candidate_signature}-${row.identity_review_id}`} job={job} row={row} busy={busy} action={perform} />}
      {job.status === "activated" && row.external_id && <button disabled={busy || historyBusy} onClick={() => showHistory(row)}>View event history for row {row.row_number}</button>}
    </article>)}
    {!terminal && <><label className={styles.checkOption}><input type="checkbox" disabled={busy || !job.activation_available} checked={ack} onChange={event => setAck(event.target.checked)} />I reviewed the event facts and identity decisions for this batch.</label><button disabled={busy || !job.activation_available || !ack} onClick={() => perform(`/event-imports/${job.id}/activate`, {})}>Activate reviewed event batch</button>
      {!job.activation_available && <p>Activation requires an approved profile and a validated batch with every conflict resolved.</p>}
      <details><summary>Cancel event batch</summary><label>Event cancellation reason<input disabled={busy} value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label><button disabled={busy || reason.trim().length < 8} onClick={() => perform(`/event-imports/${job.id}/cancel`, {reason})}>Cancel this event batch</button></details></>}
    {job.activation_receipt && <details open><summary>Event approval evidence</summary><p>Receipt integrity: {job.receipt_integrity}</p><p>Profile proposed by {job.activation_receipt.profile_proposed_by}; approved by {job.activation_receipt.profile_approved_by}.</p><p>Batch activated by {job.activation_receipt.activated_by} at {job.activation_receipt.activated_at}.</p><p>{job.activation_receipt.created.length} source observations recorded; {job.activation_receipt.duplicate_rows} duplicate rows skipped.</p><p>Receipt checksum: <code>{job.activation_receipt.checksum}</code></p>{job.activation_receipt.created.map((item, index) => <button key={item.event_id} disabled={busy || historyBusy} onClick={() => showHistory(item.event_id)}>View retained observation {index + 1} for {item.canonical_id}</button>)}</details>}
    {terminal && <PayloadCleanup resource="event-imports" jobId={job.id} disabled={busy} onRemoved={onRemoved} />}
    {historyError && <p role="alert">{historyError}</p>}{history && <section><h4>Creation history for {history.canonical_id}</h4><p>Source {history.source.source_namespace} / {history.source.external_id}</p><p>{history.notice}</p><p>Source time: {history.observation.occurred_at} ({history.observation.time_semantics}) | Imported: {history.observation.imported_at}</p><p>Identity: {history.observation.identity_resolution} | Receipt: {history.receipt_integrity}</p><h4>Original creation facts</h4><Values values={history.observation.values} /><h4>Current dealership values</h4><Values values={history.current_values} /><Conflicts items={history.legacy_conflicts} /></section>}
  </article>;
}
export default function EventJobs({systemId, stagedJob}: {systemId: string; stagedJob: string}) {
  const [page, setPage] = useState<JobPage | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    Promise.all([request(`/systems/${systemId}/event-imports`), stagedJob ? request(`/event-imports/${encodeURIComponent(stagedJob)}`) : Promise.resolve(null)]).then(([list, detail]) => {if (active) {setPage(list); if (detail) {if (detail.system_id !== systemId) {setError("Event batch does not belong to the selected source.");} else setJob(detail);}}}).catch(problem => {if (active) setError(problem.message);});
    return () => {active = false;};
  }, [systemId, stagedJob]);
  const selectedJobId = job?.id;
  useEffect(() => {
    if (selectedJobId) document.getElementById(`event-job-${selectedJobId}`)?.scrollIntoView({block:"start"});
  }, [selectedJobId]);
  async function run(task: () => Promise<void>) {
    setBusy(true); setError("");
    try {await task();} catch (problem) {setError(problem instanceof Error ? problem.message : "Event review failed.");} finally {setBusy(false);}
  }
  async function action(path: string, body: unknown) {
    await run(async () => {await request(path, body); if (job) setJob(await request(`/event-imports/${job.id}`)); setPage(await request(`/systems/${systemId}/event-imports`));});
  }
  return <section><h2>4. Review staged events</h2>{error && <p role="alert" className={styles.error}>{error}</p>}
    <button disabled={busy} onClick={() => run(async () => {setPage(await request(`/systems/${systemId}/event-imports`)); if (job) setJob(await request(`/event-imports/${job.id}`));})}>Refresh event imports</button>
    {page && <><p>{page.total_jobs} event batches for this system</p><div className={styles.row}>{page.jobs.map(item => <button disabled={busy} key={item.id} onClick={() => run(async () => {setJob(await request(`/event-imports/${item.id}`));})}>{item.id} - {item.status} - {item.row_count} rows</button>)}</div>{page.next_before_id && <button disabled={busy} onClick={() => run(async () => setPage(await request(`/systems/${systemId}/event-imports?before_id=${encodeURIComponent(page.next_before_id!)}`)))}>Older event imports</button>}</>}
    {job && <JobDetails key={`${job.id}-${job.status}-${job.validation_hash}-${JSON.stringify(job.identity_reviews)}-${job.payload_cleanup?.removed_at}`} job={job} busy={busy} action={action} onRemoved={() => run(async () => {setJob(await request(`/event-imports/${job.id}`)); setPage(await request(`/systems/${systemId}/event-imports`));})} />}
  </section>;
}
