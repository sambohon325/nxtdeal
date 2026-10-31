"use client";
import {useState} from "react";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";
import styles from "./page.module.css";

type Details = {product_version: string; deployment: string; record_types: string[]; evidence: Record<string, string>};
type Setup = {revision: number; details: Details; updated_by: string | null; updated_at: string | null; evidence_states: string[]; deployments: string[]; unresolved_evidence: string[]; notice: string};
const labels: Record<string, string> = {
  dealer_authorization: "Dealer authorization", product_documentation: "Product documentation",
  sample_export: "Authorized sample export", stable_ids: "Stable source identifiers",
  source_timestamps: "Source time definitions", relationship_keys: "Links between source records",
  independent_totals: "Independent source totals", unknown: "Not yet checked", requested: "Requested",
  available: "Available for review", not_applicable: "Not applicable to this scope",
  cloud: "Cloud", on_premise: "On premises", hosted: "Hosted", file_only: "Export files only",
};

export default function SystemSetup({systemId, recordTypes}: {systemId: string; recordTypes: string[]}) {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  async function exchange(save: boolean) {
    setBusy(true); setMessage(""); setError("");
    try {
      const response = await fetch(`${API_BASE}/dealer-bridge/systems/${systemId}/onboarding`, {
        method: save ? "POST" : "GET", headers: {...authHeaders(), "Content-Type": "application/json"},
        ...(save && setup ? {body: JSON.stringify({revision: setup.revision, details: setup.details})} : {}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Setup details could not be saved. Check your entries and administrator session.");
      setSetup(result);
      if (save) setMessage("Setup details saved. This does not connect the system or approve an import.");
    } catch (problem) {setError(problem instanceof Error ? problem.message : "Unable to load setup details.");}
    finally {setBusy(false);}
  }
  function change(values: Partial<Details>) {
    setSetup(current => current ? {...current, details: {...current.details, ...values}} : current);
    setMessage("");
  }
  return <details><summary>Connection setup details</summary>
    <p>Track the product, intended records and evidence you have requested. Do not enter passwords, API keys or customer information.</p>
    {!setup && <button disabled={busy} onClick={() => exchange(false)}>Load setup details</button>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {setup && <fieldset disabled={busy}>
      <label>Product version<input maxLength={120} value={setup.details.product_version} onChange={event => change({product_version: event.target.value})} placeholder="Known version, or leave blank" /></label>
      <label>Deployment<select value={setup.details.deployment} onChange={event => change({deployment: event.target.value})}>{setup.deployments.map(value => <option key={value} value={value}>{labels[value] || value}</option>)}</select></label>
      <details><summary>Records to plan ({setup.details.record_types.length} selected)</summary>{recordTypes.map(kind => <label className={styles.checkOption} key={kind}><input type="checkbox" checked={setup.details.record_types.includes(kind)} onChange={event => change({record_types: event.target.checked ? [...setup.details.record_types, kind] : setup.details.record_types.filter(value => value !== kind)})} />{kind}</label>)}</details>
      {Object.entries(setup.details.evidence).map(([key, value]) => <label key={key}>{labels[key] || key}<select value={value} onChange={event => change({evidence: {...setup.details.evidence, [key]: event.target.value}})}>{setup.evidence_states.map(state => <option key={state} value={state}>{labels[state] || state}</option>)}</select></label>)}
      <p>{setup.notice}</p>
      {setup.updated_at && <p>Last saved by {setup.updated_by} at {setup.updated_at}</p>}
      <button onClick={() => exchange(true)}>Save setup details</button>{" "}<button onClick={() => exchange(false)}>Reload saved details</button>
    </fieldset>}
  </details>;
}
