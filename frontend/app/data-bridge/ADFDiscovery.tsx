"use client";
import {useRef, useState} from "react";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";
import styles from "./page.module.css";

type Report = {source_bytes: number; content_hash: string; row_count: number; notice: string; rows: {row_number: number; source_id_count: number; customer_contact_count: number; vehicle_count: number; issues: string[]}[]};
const issues: Record<string, string> = {
  stable_source_id_required: "Stable provider ID needs review",
  source_id_selection_required: "Choose the authoritative provider ID",
  single_creation_time_required: "One lead creation time is required",
  timezone_aware_creation_time_required: "Creation time needs a valid timezone",
  customer_contact_selection_required: "Choose the customer contact",
  contact_value_selection_required: "Choose among repeated phone or email values",
  vehicle_selection_required: "Review multiple vehicles",
};

export default function ADFDiscovery({systemId}: {systemId: string}) {
  const sequence = useRef(0);
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [report, setReport] = useState<Report | null>(null);
  async function select(file?: File) {
    const current = ++sequence.current;
    setContent(""); setReport(null); setError("");
    if (!file) return;
    if (file.size > 1_000_000) {setError("Choose an ADF XML file up to 1 MB."); return;}
    try {
      const text = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(await file.arrayBuffer());
      if (current === sequence.current) setContent(text);
    } catch {if (current === sequence.current) setError("The file must contain valid UTF-8 text.");}
  }
  async function inspect() {
    const current = sequence.current;
    setBusy(true); setReport(null); setError("");
    try {
      const response = await fetch(`${API_BASE}/dealer-bridge/systems/${systemId}/discover-adf`, {
        method: "POST", headers: {...authHeaders(), "Content-Type": "application/json"}, body: JSON.stringify({content}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "ADF discovery could not be completed.");
      if (current === sequence.current) setReport(result);
    } catch (problem) {if (current === sequence.current) setError(problem instanceof Error ? problem.message : "ADF discovery failed.");}
    finally {setBusy(false);}
  }
  return <details><summary>Inspect an ADF lead file</summary>
    <p>Inspect an authorized XML lead file for missing identity and ambiguous contacts or vehicles. This review does not import leads. ADF request dates describe lead creation; source modification times are not supplied.</p>
    <label>Authorized ADF XML<input type="file" accept=".xml,.adf,application/xml,text/xml" disabled={busy} onChange={event => select(event.target.files?.[0])} /></label>
    <button disabled={busy || !content} onClick={inspect}>Inspect ADF structure</button>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {report && <div role="status"><p>{report.row_count} prospects | {report.source_bytes} source bytes | No lead values stored</p>
      <p>{report.notice}</p>
      <p>File fingerprint: <code>{report.content_hash}</code></p>
      <div className={styles.scroll}><table><thead><tr><th>Prospect</th><th>IDs</th><th>Contacts</th><th>Vehicles</th><th>Review</th></tr></thead><tbody>{report.rows.map(row => <tr key={row.row_number}><td>{row.row_number}</td><td>{row.source_id_count}</td><td>{row.customer_contact_count}</td><td>{row.vehicle_count}</td><td>{row.issues.length ? row.issues.map(issue => issues[issue] || "Structure needs review").join("; ") : "No ambiguity detected by these checks; import profile still required"}</td></tr>)}</tbody></table></div>
    </div>}
  </details>;
}
