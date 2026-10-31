"use client";
import {useState} from "react";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";
import styles from "./page.module.css";

type Activity = {id: string; action: string; actor: string; record_id: string; at: string; principal: string | null};
type Report = {activities: Activity[]; next_before_id: string | null; total_activities: number; notice: string};

export default function SystemActivity({systemId}: {systemId: string}) {
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function load(older = false) {
    if (busy) return;
    setBusy(true); setError("");
    try {
      const cursor = older ? report?.next_before_id : null;
      const response = await fetch(`${API_BASE}/dealer-bridge/systems/${encodeURIComponent(systemId)}/activity?limit=25${cursor ? `&before_id=${encodeURIComponent(cursor)}` : ""}`, {headers: authHeaders()});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Unable to load source activity.");
      setReport(previous => ({...data, activities: older && previous ? [...previous.activities, ...data.activities] : data.activities}));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to load source activity.");
    } finally {setBusy(false);}
  }
  return <details><summary>Source activity history</summary>
    <p>Review retained mapping, import, collection and recovery actions for this system.</p>
    <button disabled={busy} onClick={() => load()}>{report ? "Refresh activity" : "Load activity"}</button>
    {error && <p role="alert">{error}</p>}
    {report && <div><p>{report.activities.length} of {report.total_activities} retained actions shown.</p>
      <ol className={styles.activityList} aria-label="Source activity entries" tabIndex={0}>{report.activities.map(row => <li key={row.id}>
        <strong>{row.action.replaceAll(".", " ").replaceAll("_", " ")}</strong>
        <p>{row.actor} - {row.principal || "credential type not recorded"}</p>
        <p><time dateTime={row.at}>{row.at}</time></p><p>Record <code>{row.record_id}</code></p>
      </li>)}</ol>
      {report.next_before_id && <button disabled={busy} onClick={() => load(true)}>Load older activity</button>}
      <p>{report.notice}</p>
    </div>}
  </details>;
}
