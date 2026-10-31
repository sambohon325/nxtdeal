"use client";
import Link from "next/link";
import {Suspense, useEffect, useMemo, useState} from "react";
import {useRouter, useSearchParams} from "next/navigation";
import {useRequireAuth} from "@/lib/auth";
import {request} from "../events/api";
import styles from "../page.module.css";

type Source = {id: string; name: string};
type Batch = {review_advisory_rows?: number | null; id: string; kind: "snapshot" | "event"; system_id: string; system_name: string; vendor: string; source_paused: boolean; status: string; created_at: string; row_count: number; payload_removed: boolean};
type Report = {jobs: Batch[]; systems: Source[]; matching_jobs: number; status_counts: Record<string,number>; next_before_id: string | null; notice: string};
type Filters = {systemId: string; status: string; kind: string};
function path(filters: Filters, before?: string) {
  const query = new URLSearchParams({status:filters.status,kind:filters.kind,limit:"25"});
  if (filters.systemId) query.set("system_id",filters.systemId);
  if (before) query.set("before_id",before);
  return `/review-queue?${query}`;
}
function Results({filters,onSources}: {filters: Filters; onSources: (sources: Source[]) => void}) {
  const [report,setReport] = useState<Report | null>(null);
  const [busy,setBusy] = useState(true);
  const [error,setError] = useState("");
  useEffect(() => {
    let active = true;
    request(path(filters)).then((data: Report) => {if (active) {setReport(data); onSources(data.systems);}})
      .catch(problem => {if (active) setError(problem.message);}).finally(() => {if (active) setBusy(false);});
    return () => {active = false;};
  }, [filters,onSources]);
  async function load(before?: string) {
    setBusy(true); setError("");
    try {const data: Report = await request(path(filters,before)); setReport(data); onSources(data.systems);}
    catch (problem) {setError(problem instanceof Error ? problem.message : "Review queue unavailable.");}
    finally {setBusy(false);}
  }
  return <section><h2>Import batches</h2><button disabled={busy} onClick={() => load()}>Refresh newest batches</button>
    {busy && <p role="status">Loading review queue...</p>}{error && <p role="alert" className={styles.error}>{error}</p>}
    {report && <><p>{report.matching_jobs} batches match these filters. Showing up to 25 at a time.</p><p>{report.notice}</p>
      {!report.jobs.length && <p>No batches match this page and filter. Refresh to check for new work.</p>}
      {report.jobs.map(batch => <article key={batch.id}><h3>{batch.id} · {batch.status}</h3><p>{batch.system_name} ({batch.vendor}) · {batch.kind === "event" ? "ADF creation events" : "Snapshot import"}</p>
        <p>{batch.row_count} source rows · Staged {batch.created_at}{batch.payload_removed ? " · Staging copy removed" : ""}</p>
        {!!batch.review_advisory_rows && <p>Last validation: {batch.review_advisory_rows} {batch.review_advisory_rows === 1 ? "row has" : "rows have"} relationship review advisories. Open the batch to inspect them.</p>}
        {batch.source_paused && <p>Source paused. Review the pause before attempting activation.</p>}
        <Link href={batch.kind === "event" ? `/data-bridge/events?system=${encodeURIComponent(batch.system_id)}&job=${encodeURIComponent(batch.id)}` : `/data-bridge#bridge-job-${encodeURIComponent(batch.id)}`}>Open review for {batch.id}</Link>
      </article>)}
      {report.next_before_id && <button disabled={busy} onClick={() => load(report.next_before_id!)}>Older matching batches</button>}
    </>}
  </section>;
}
function Workspace() {
  const [systems,setSystems] = useState<Source[]>([]);
  const router = useRouter();
  const query = useSearchParams();
  const systemId = query.get("system_id") || "";
  const requestedStatus = query.get("status") || "pending";
  const requestedKind = query.get("kind") || "all";
  const status = ["pending","all","staged","validated","blocked","activated","cancelled"].includes(requestedStatus) ? requestedStatus : "pending";
  const kind = ["all","snapshot","event"].includes(requestedKind) ? requestedKind : "all";
  const filters = useMemo<Filters>(() => ({systemId,status,kind}), [systemId,status,kind]);
  function setFilters(next: Filters) {
    const updated = new URLSearchParams({status:next.status,kind:next.kind});
    if (next.systemId) updated.set("system_id",next.systemId);
    router.replace(`/data-bridge/review?${updated}`, {scroll:false});
  }
  return <main className={styles.page}><Link href="/data-bridge">Back to System Map</Link><p className={styles.kicker}>DEALER DATA BRIDGE</p><h1>Import review queue</h1>
    <p>Find snapshot and ADF batches across your systems. Opening a batch does not validate, activate or change it.</p>
    <div className={styles.row}><label>Source system<select value={filters.systemId} onChange={event => setFilters({...filters,systemId:event.target.value})}><option value="">All systems</option>{filters.systemId && !systems.some(source => source.id === filters.systemId) && <option value={filters.systemId}>Selected source (not loaded)</option>}{systems.map(source => <option key={source.id} value={source.id}>{source.name}</option>)}</select></label>
      <label>Batch status<select value={filters.status} onChange={event => setFilters({...filters,status:event.target.value})}>{["pending","all","staged","validated","blocked","activated","cancelled"].map(status => <option key={status} value={status}>{status === "pending" ? "Pending review" : status.charAt(0).toUpperCase()+status.slice(1)}</option>)}</select></label>
      <label>Import type<select value={filters.kind} onChange={event => setFilters({...filters,kind:event.target.value})}><option value="all">All import types</option><option value="snapshot">Snapshot imports</option><option value="event">ADF creation events</option></select></label>
    </div><Results key={JSON.stringify(filters)} filters={filters} onSources={setSystems} />
  </main>;
}
export default function ReviewQueue() {
  const session = useRequireAuth("ADMIN");
  return session ? <Suspense fallback={<main className={styles.page}><p>Loading review filters...</p></main>}><Workspace /></Suspense> : <main className={styles.page}><p>Checking administrator access...</p></main>;
}
