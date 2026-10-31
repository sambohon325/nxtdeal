"use client";
import {useState} from "react";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";
import styles from "./page.module.css";

type Gateway = {review_token: string | null; review_reasons: string[]; can_review_policy: boolean; endpoint_id: string; enabled: boolean; effective_status: string; profile_id: string; binding_available: boolean; binding_revision: string | null; authorized_revision: string | null; environment: string; pending_batches: number; max_pending_batches: number | null};
const reviewGuidance: Record<string, string> = {
  binding_unavailable: "Ask the connector operator to restore the gateway binding.",
  durable_storage_required: "Delivery requires durable storage; it is unavailable in demo mode.",
  profile_approval_required: "A different administrator must approve the event profile first.",
  profile_unavailable_or_changed: "The event profile is unavailable, revoked or changed. Review a replacement profile with the connector operator.",
  source_paused: "Review the source pause before resuming imports.",
  environment_conflict: "Use a separate source for a different environment; retained source evidence conflicts with this binding.",
  authorizing_administrator_unavailable: "The administrator who authorized this gateway no longer has active administrator access. A current administrator must review it again.",
  binding_review_required: "The runtime binding differs from the authorized configuration. Review the displayed revision and profile again.",
};

type Report = {gateways: Gateway[]; notice: string; received_delivery_count: number; last_received_at: string | null; delivery_evidence_issues: number};
async function request(path: string, body?: unknown) {
  const response = await fetch(`${API_BASE}/dealer-bridge${path}`, {method: body === undefined ? "GET" : "POST", headers: {...authHeaders(), "Content-Type":"application/json"}, ...(body === undefined ? {} : {body:JSON.stringify(body)})});
  const data = await response.json();
  if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Gateway request failed.");
  return data;
}
function GatewayPolicy({gateway, paused, busy, save}: {gateway: Gateway; paused: boolean; busy: boolean; save: (gateway: Gateway, enabled: boolean) => Promise<void>}) {
  const [acknowledged, setAcknowledged] = useState(false);
  return <article><h4>ADF gateway policy · {gateway.effective_status.replaceAll("_", " ")}</h4>
    <p>Event profile {gateway.profile_id} · Operator declares {gateway.environment} · {gateway.pending_batches} batches waiting for review{gateway.max_pending_batches ? ` (limit ${gateway.max_pending_batches})` : ""}</p>
    <p>{gateway.binding_available ? `Configured revision: ${gateway.binding_revision}` : "No runtime gateway is currently configured. An operator must restore the reviewed binding before delivery can resume."}</p>
    <details><summary>Delivery address path</summary><code>{`/dealer-bridge/inbound/adf/${gateway.endpoint_id}`}</code><p>For an authorized sender implementing the NXTDeal signed ADF gateway contract. This path alone does not grant access.</p></details>
    {gateway.enabled && <button disabled={busy} onClick={() => save(gateway,false)}>Disable staged delivery</button>}
    {(!gateway.enabled || gateway.authorized_revision !== gateway.binding_revision || gateway.effective_status === "review_required") && gateway.binding_available && gateway.can_review_policy && <>
      <label className={styles.checkOption}><input type="checkbox" disabled={busy || paused} checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />I reviewed this gateway, source environment and approved event profile. Deliveries may create review jobs only.</label>
      <button disabled={busy || paused || !acknowledged || !gateway.review_token} onClick={async () => {setAcknowledged(false); await save(gateway,true);}}>{gateway.enabled ? "Reauthorize staged delivery for this revision" : "Enable staged delivery for this revision"}</button>
    </>}
    {paused && <p>The source is paused. Resume it before enabling delivery.</p>}
    {!!gateway.review_reasons.length && <ul>{gateway.review_reasons.map(reason => <li key={reason}>{reviewGuidance[reason] || "Review this gateway configuration with the connector operator."}</li>)}</ul>}
    {gateway.effective_status === "queue_full" && <p>Review and finish pending event batches before the sender retries.</p>}
  </article>;
}
export default function InboundGateway({systemId, paused}: {systemId: string; paused: boolean}) {
  const [report, setReport] = useState<Report | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [reviewVersion, setReviewVersion] = useState(0);
  async function load() {
    setBusy(true); setError(""); setNotice(""); setReport(null); setReviewVersion(value => value + 1);
    try {setReport(await request(`/systems/${systemId}/inbound`));}
    catch (problem) {setError(problem instanceof Error ? problem.message : "Gateway inspection failed.");}
    finally {setBusy(false);}
  }
  async function save(gateway: Gateway, enabled: boolean) {
    setBusy(true); setError(""); setNotice("");
    try {
      await request(`/inbound/${gateway.endpoint_id}/policy`, {enabled, revision: enabled ? gateway.binding_revision : null, review_token: enabled ? gateway.review_token : null});
      setReport(await request(`/systems/${systemId}/inbound`)); setReviewVersion(value => value + 1);
      setNotice(enabled ? "Signed deliveries may now stage review jobs for this revision." : "Further signed deliveries are disabled. Existing review jobs remain.");
    } catch (problem) {setReport(null); setError(problem instanceof Error ? problem.message : "Gateway policy update failed.");}
    finally {setBusy(false);}
  }
  return <details><summary>Signed ADF delivery</summary><p>Review operator-configured delivery gateways. Sending events requires a signed gateway contract; vendor webhook formats need their own adapter.</p>
    <button disabled={busy} onClick={load}>{busy ? "Loading gateways…" : report ? "Refresh gateway status" : "Inspect delivery gateways"}</button>
    {error && <p role="alert" className={styles.error}>{error}</p>}{notice && <p role="status">{notice}</p>}
    {report && <><p>{report.notice}</p><p>{report.received_delivery_count} retained deliveries for this source{report.last_received_at ? ` · Last received ${report.last_received_at}` : " · No verified receipt recorded yet"}.</p>{!!report.delivery_evidence_issues && <p role="alert">{report.delivery_evidence_issues} delivery receipts need evidence review.</p>}{report.gateways.length ? report.gateways.map(gateway => <GatewayPolicy key={`${gateway.endpoint_id}-${reviewVersion}`} gateway={gateway} paused={paused} busy={busy} save={save} />) : <p>No signed delivery gateway is configured for this source. Authorized ADF files can still be uploaded for discovery and review.</p>}</>}
  </details>;
}
