"use client";
import {useEffect, useRef, useState} from "react";
import styles from "../page.module.css";
import {request, type Profile, type EventRow} from "./api";

const targets = ["first_name", "last_name", "email", "phone"];
const sources: Record<string, string> = {name_first: "First name", name_last: "Last name", name_full: "Full name (kept intact)", email: "Email", phone: "Phone"};
export default function EventProfiles({systemId, employeeId, onStaged}: {systemId: string; employeeId: string; onStaged: (jobId: string) => void}) {
  const [profiles, setProfiles] = useState<Profile[]>([]);
  const [provider, setProvider] = useState("");
  const [fields, setFields] = useState<Record<string, string>>({});
  const [selected, setSelected] = useState("");
  const [content, setContent] = useState("");
  const [rows, setRows] = useState<EventRow[] | null>(null);
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const fileSequence = useRef(0);
  useEffect(() => {
    let active = true;
    request(`/systems/${systemId}/event-profiles`).then(data => {if (active) setProfiles(data.profiles);}).catch(problem => {if (active) setError(problem.message);});
    return () => {active = false;};
  }, [systemId]);
  async function act(action: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try {await action(); setProfiles((await request(`/systems/${systemId}/event-profiles`)).profiles);}
    catch (problem) {setError(problem instanceof Error ? problem.message : "Event profile action failed.");}
    finally {setBusy(false);}
  }
  async function file(file?: File) {
    const current = ++fileSequence.current;
    setContent(""); setRows(null); setError("");
    if (!file) return;
    if (file.size > 1_000_000) {setError("Choose an authorized file up to 1 MB."); return;}
    try {
      const text = new TextDecoder("utf-8", {fatal: true, ignoreBOM: true}).decode(await file.arrayBuffer());
      if (current === fileSequence.current) setContent(text);
    } catch {if (current === fileSequence.current) setError("ADF must be valid UTF-8 XML.");}
  }
  return <>
    {error && <p role="alert" className={styles.error}>{error}</p>}{notice && <p role="status" className={styles.notice}>{notice}</p>}
    <section><h2>1. Propose an event profile</h2><p>Select the exact provider identifier from the source attribute of the ADF id element. This namespace is part of identity; the request date in the file always means creation time.</p>
      <fieldset disabled={busy}><label>Provider ID namespace<input value={provider} maxLength={120} onChange={event => setProvider(event.target.value)} /></label>
      {targets.map(target => <label key={target}>NXTDeal {target.replaceAll("_", " ")}<select value={fields[target] || ""} onChange={event => setFields({...fields, [target]: event.target.value})}><option value="">Do not map</option>{Object.entries(sources).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>)}
      <p>Names are not split automatically. Choose only fields supported by your authorized provider sample. Profiles import lead identity facts; they do not grant permission to contact a customer.</p>
      <button disabled={!provider.trim() || !Object.values(fields).some(Boolean)} onClick={() => act(async () => {const result = await request("/event-profiles", {system_id: systemId, id_source: provider, fields: Object.fromEntries(Object.entries(fields).filter(([, source]) => source).map(([target, source]) => [target, {source, transform: target === "email" ? "lower" : "text"}]))}); setNotice(`Profile ${result.id} proposed. A different administrator must approve it.`);})}>Propose event profile</button></fieldset>
    </section>
    <section><h2>2. Review profiles</h2><button disabled={busy} onClick={() => act(async () => {setNotice("Profiles refreshed.");})}>Refresh profiles</button>
      {!profiles.length && <p>No event profiles for this source.</p>}
      {profiles.map(profile => <article key={profile.id}><h3>{profile.id} - {profile.status}</h3><p>Provider namespace: {profile.id_source}</p><p>Created events only. Existing records receive history without overwriting current values.</p><p>Proposed by {profile.proposed_by}{profile.approved_by && ` | Approved by ${profile.approved_by}`}</p>
        <dl>{Object.entries(profile.fields).map(([target, spec]) => <div key={target}><dt>{target}</dt><dd>{sources[spec.source] || spec.source} ({spec.transform})</dd></div>)}</dl><p>Profile fingerprint: <code>{profile.hash}</code></p>
        {profile.status === "proposed" && <button disabled={busy || profile.proposed_by === employeeId} onClick={() => act(async () => {await request(`/event-profiles/${profile.id}/approve`, {}); setNotice("Event profile approved. Every batch still needs review and activation.");})}>Approve event profile {profile.id}</button>}
        {profile.status !== "revoked" && <details><summary>Revoke event profile {profile.id}</summary><label>Revocation reason<input value={reason} maxLength={500} onChange={event => setReason(event.target.value)} /></label><button disabled={busy || reason.trim().length < 8} onClick={() => act(async () => {await request(`/event-profiles/${profile.id}/revoke`, {reason}); setRows(null); setReason(""); setNotice("Event profile revoked.");})}>Revoke this event profile</button></details>}
      </article>)}
    </section>
    <section><h2>3. Test an authorized ADF file</h2><label>Event profile<select disabled={busy} value={selected} onChange={event => {setSelected(event.target.value); setRows(null);}}><option value="">Select profile</option>{profiles.filter(profile => profile.status !== "revoked").map(profile => <option key={profile.id} value={profile.id}>{profile.id} - {profile.id_source} - {profile.status}</option>)}</select></label>
      <label>ADF file to test<input type="file" accept=".adf,.xml,application/xml,text/xml" disabled={busy} onChange={event => file(event.target.files?.[0])} /></label>
      <button disabled={busy || !selected || !content} onClick={() => act(async () => {const result = await request(`/event-profiles/${selected}/test`, {content}); setRows(result.rows); setNotice(result.notice);})}>Simulate event mapping</button>{" "}<button disabled={busy || !selected || !content} onClick={() => act(async () => {const result = await request("/event-imports", {profile_id: selected, content}); onStaged(result.id); setNotice(`Batch ${result.id} staged. Review it below before activation.`);})}>Stage event batch</button>
      {rows && <div className={styles.scroll}><table><thead><tr><th>Row</th><th>Result</th><th>Source ID</th><th>Creation time</th><th>Mapped facts</th></tr></thead><tbody>{rows.map(row => <tr key={row.row_number}><td>{row.row_number}</td><td>{row.status}{row.error_code && `: ${row.error_code.replaceAll("_", " ")}`}</td><td>{row.external_id || "Unavailable"}</td><td>{row.occurred_at || "Unavailable"}</td><td>{Object.entries(row.values || {}).map(([field, value]) => <p key={field}>{field}: {value}</p>)}</td></tr>)}</tbody></table></div>}
    </section>
  </>;
}
