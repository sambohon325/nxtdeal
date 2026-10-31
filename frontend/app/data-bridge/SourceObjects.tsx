"use client";
import {useState} from "react";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";
import styles from "./page.module.css";

type Discovery = {objects: string[]; authorized_not_reported: string[]; binding_revision: string; environment: string; schema_inspection_available: boolean; notice: string};
export default function SourceObjects({systemId, disabled}: {systemId: string; disabled: boolean}) {
  const [result, setResult] = useState<Discovery | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function inspect() {
    setBusy(true); setError(""); setResult(null);
    try {
      const response = await fetch(`${API_BASE}/dealer-bridge/systems/${encodeURIComponent(systemId)}/discover-objects`, {headers: authHeaders()});
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Source object discovery failed.");
      setResult(data);
    } catch (problem) {setError(problem instanceof Error ? problem.message : "Source object discovery failed.");}
    finally {setBusy(false);}
  }
  return <details><summary>Discover authorized source objects</summary>
    <p>Ask the configured connector which authorized objects it currently exposes. No source records are imported.</p>
    <button disabled={disabled || busy} onClick={inspect}>{busy ? "Discovering objects..." : "Inspect authorized objects"}</button>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {result && <div><p>Connector revision {result.binding_revision} | Operator declares {result.environment.replaceAll("_", " ")}</p><p>{result.notice}</p>
      {result.objects.length ? <><p>Reported and authorized:</p><ul>{result.objects.map(name => <li key={name}><code>{name}</code></li>)}</ul></> : <p>No authorized objects were reported by this connector.</p>}
      {!!result.authorized_not_reported.length && <><p>Authorized but absent from this discovery response; confirm source access and product scope:</p><ul>{result.authorized_not_reported.map(name => <li key={name}><code>{name}</code></li>)}</ul></>}
      <p>{result.schema_inspection_available ? "Use an available object name in mapping discovery to inspect its columns before proposing a mapping." : "This connector does not implement column inspection. Use an authorized sample export to review field meanings."}</p>
    </div>}
  </details>;
}
