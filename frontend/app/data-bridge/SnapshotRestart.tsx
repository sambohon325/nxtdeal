"use client";
import {useState} from "react";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";
import styles from "./page.module.css";

type Plan = {review_token: string; replacement_fingerprint: string; binding_revision: string; pages_previously_accepted: number; notice: string};
export default function SnapshotRestart({stateId, busy, onRestart}: {stateId: string; busy: boolean; onRestart: (token: string, reason: string) => Promise<void>}) {
  const [plan, setPlan] = useState<Plan | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  async function inspect() {
    setPlan(null); setAcknowledged(false); setError(""); setLoading(true);
    try {
      const response = await fetch(`${API_BASE}/dealer-bridge/sync/${stateId}/snapshot-restart-preview`, {headers: authHeaders()});
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Could not inspect the replacement export.");
      setPlan(result);
    } catch (error) {setError(error instanceof Error ? error.message : "Inspection failed.");}
    finally {setLoading(false);}
  }
  return <details><summary>Restart an unfinished file import</summary>
    <p>Use this when an operator replaces a paginated source export before all pages are accepted. Review the currently configured file before starting it again.</p>
    <button disabled={busy || loading} onClick={inspect}>{loading ? "Inspecting replacement…" : plan ? "Refresh replacement review" : "Inspect replacement export"}</button>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {plan && <div><p>{plan.notice}</p><p>{plan.pages_previously_accepted} previously accepted pages stay recorded. The collection schedule will be disabled.</p>
      <details><summary>Replacement file fingerprint</summary><p>{plan.replacement_fingerprint}</p><p>Connector revision: {plan.binding_revision}</p></details>
      <label>Reason for restarting the file<textarea maxLength={500} value={reason} onChange={event => setReason(event.target.value)} /></label>
      <label className={styles.checkOption}><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />I reviewed the replacement file and understand that earlier imported records remain.</label>
      <button disabled={busy || loading || !acknowledged || reason.trim().length < 10} onClick={async () => {const token = plan.review_token; setPlan(null); setAcknowledged(false); await onRestart(token, reason);}}>Restart from reviewed file</button>
    </div>}
  </details>;
}
