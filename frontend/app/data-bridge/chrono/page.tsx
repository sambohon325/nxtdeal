"use client";
import Link from "next/link";
import {useEffect, useState} from "react";
import {useRequireAuth} from "@/lib/auth";
import {request} from "../events/api";
import styles from "../page.module.css";

type Receipt = {id: string; event_id: string; status: string; attempts: number; last_attempt_at: string | null; next_attempt_at: string | null; acknowledged_at: string | null; last_error: string | null; retry_available: boolean};
type Report = {receipts: Receipt[]; matching_receipts: number; next_before_id: string | null; excluded_receipts: number; destination: {name: string | null; revision: string | null}; effective_status: string; reason: string | null; notice: string};
function Retry({receipt,disabled,onRetry}: {receipt: Receipt; disabled: boolean; onRetry: (receipt: Receipt,reason: string) => Promise<void>}) {
  const [reason,setReason] = useState("");
  return <details><summary>Review delivery retry</summary><p>Retry retains this observation identity. An enabled delivery worker may send it after you queue the retry.</p>
    <label>Reason for retry<input aria-label={`Reason for retrying ${receipt.event_id}`} disabled={disabled} value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label>
    <button aria-label={`Queue retry for ${receipt.event_id}`} disabled={disabled || reason.trim().length < 8} onClick={() => onRetry(receipt,reason)}>Queue reviewed retry</button>
  </details>;
}
function Results({status}: {status: string}) {
  const [report,setReport] = useState<Report | null>(null);
  const [busy,setBusy] = useState(true);
  const [error,setError] = useState("");
  const [notice,setNotice] = useState("");
  const [cursor,setCursor] = useState<string | undefined>();
  function path(before?: string) {
    const query = new URLSearchParams({status,limit:"25"});
    if (before) query.set("before_id",before);
    return `/chrono/receipt-queue?${query}`;
  }
  useEffect(() => {
    let active=true;
    request(`/chrono/receipt-queue?status=${encodeURIComponent(status)}&limit=25`).then((result: Report) => {if(active)setReport(result);})
      .catch(problem=>{if(active)setError(problem.message);}).finally(()=>{if(active)setBusy(false);});
    return ()=>{active=false;};
  },[status]);
  async function load(before?: string) {
    setBusy(true);setError("");setNotice("");
    try {setReport(await request(path(before)));setCursor(before);}
    catch(problem){setError(problem instanceof Error?problem.message:"Delivery review unavailable.");}
    finally{setBusy(false);}
  }
  async function retry(receipt: Receipt,reason: string) {
    setBusy(true);setError("");setNotice("");
    try {
      await request(`/chrono/observations/${encodeURIComponent(receipt.event_id)}/retry`,{reason,receipt_id:receipt.id});
      setNotice("Retry queued for the reviewed destination using the same observation identity.");
      setReport(await request(path(cursor)));
    } catch(problem){setError(problem instanceof Error?problem.message:"Retry unavailable. Reload the delivery evidence.");}
    finally{setBusy(false);}
  }
  return <section><h2>Recorded delivery attempts</h2><button disabled={busy} onClick={()=>load()}>Refresh delivery review</button>
    {busy&&<p role="status">Loading delivery review...</p>}{error&&<p role="alert" className={styles.error}>{error}</p>}{notice&&<p role="status">{notice}</p>}
    {report&&<><p>Selected destination: {report.destination.name?`${report.destination.name} (${report.destination.revision})`:"No destination authorized"}</p>
      <p>Delivery policy: {report.effective_status.replaceAll("_"," ")}{report.reason?` - ${report.reason}`:""}</p><p>{report.notice}</p>
      <p>{report.matching_receipts} matching receipts. Each page contains up to 25.</p>
      {!!report.excluded_receipts&&<p role="alert">{report.excluded_receipts} receipts cannot be attributed consistently. Ask an operator to inspect retained delivery evidence.</p>}
      {!report.receipts.length&&<p>No recorded attempts match this page and filter.</p>}
      {report.receipts.map(receipt=><article key={receipt.id}><h3>{receipt.event_id} - {receipt.status.replaceAll("_"," ")}</h3><p>{receipt.attempts} attempts{receipt.last_attempt_at?` - Last attempt ${receipt.last_attempt_at}`:""}</p>
        {receipt.next_attempt_at&&<p>Next eligible attempt: {receipt.next_attempt_at}</p>}{receipt.acknowledged_at&&<p>Acknowledged: {receipt.acknowledged_at}</p>}{receipt.last_error&&<p>{receipt.last_error}</p>}
        {receipt.retry_available&&<Retry key={`${receipt.id}-${receipt.status}-${receipt.attempts}`} receipt={receipt} disabled={busy} onRetry={retry}/>}
      </article>)}
      {report.next_before_id&&<button disabled={busy} onClick={()=>load(report.next_before_id!)}>Older observation receipts</button>}
    </>}
  </section>;
}
function Workspace(){
  const [status,setStatus]=useState("unacknowledged");
  return <main className={styles.page}><Link href="/data-bridge#bridge-chrono">Back to Chrono delivery controls</Link><p className={styles.kicker}>DEALER DATA BRIDGE</p><h1>Chrono delivery review</h1>
    <p>Inspect retained delivery results for the selected destination. Retries require an administrator and current authorization for that destination.</p>
    <label>Delivery status<select value={status} onChange={event=>setStatus(event.target.value)}>{["unacknowledged","all","blocked","retrying","in_flight","delivered"].map(value=><option key={value} value={value}>{value.replaceAll("_"," ")}</option>)}</select></label>
    <Results key={status} status={status}/>
  </main>;
}
export default function ChronoReview(){const session=useRequireAuth("ADMIN");return session?<Workspace/>:<main className={styles.page}><p>Checking administrator access...</p></main>;}
