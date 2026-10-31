"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders, getSession } from "@/lib/auth";
import styles from "../page.module.css";

type Grant = { id: string; name: string; scopes: string; departments: string; expires: number; revoked: number };
type Client = { id: string; name: string; redirects: string; disabled: number };
type Setup = { mcp_url: string; issuer: string; grants: Grant[]; clients: Client[]; chrono?: { status: string; business: string | null; missing: string[]; credential_configured: boolean } };
type Review = { client_name: string; client_id: string; redirect_uri: string; scopes: string[]; departments: string[]; resource: string };

async function request(path: string, body?: unknown, method?: string) {
  const response = await fetch(`${API_BASE}/agent-oauth${path}`, { method: method || (body === undefined ? "GET" : "POST"),
    headers: { ...authHeaders(), "Content-Type": "application/json" }, ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
  const data = await response.json();
  if (!response.ok) throw new Error(response.status === 401 ? "Sign in to NXTDeal, then return here and retry." : typeof data.detail === "string" ? data.detail : "The request could not be completed.");
  return data;
}

export default function ConnectionsPage() {
  const [setup, setSetup] = useState<Setup | null>(null);
  const [review, setReview] = useState<Review | null>(null);
  const [departments, setDepartments] = useState<string[]>([]);
  const [name, setName] = useState("");
  const [callback, setCallback] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [busy, setBusy] = useState(false);
  const [admin, setAdmin] = useState(false);
  const [checkedAt, setCheckedAt] = useState(0);
  const load = useCallback(async () => {
    const session = getSession();
    if (!session) throw new Error("Sign in to NXTDeal, then return here and retry.");
    const data = await request("/connections");
    setError("");
    setAdmin(session.role === "ADMIN");
    setSetup(data);
    setCheckedAt(Date.now());
    const requestId = new URLSearchParams(window.location.search).get("request");
    if (requestId) setReview(await request(`/requests/${encodeURIComponent(requestId)}`));
  }, []);
  useEffect(() => { Promise.resolve().then(load).catch(e => setError(e.message)); }, [load]);
  async function act(fn: () => Promise<void>) {
    setBusy(true); setError(""); setNotice("");
    try { await fn(); } catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  }
  async function consent(approve: boolean) {
    const requestId = new URLSearchParams(window.location.search).get("request");
    const result = await request("/consent", { request_id: requestId, departments, approve });
    // The API returns only the exact administrator-registered callback.
    window.location.assign(result.redirect_url);
  }
  return <main className={styles.page}>
    <header className={styles.header}><Link href="/agents">← Department Agents</Link><Link href="/workspace">NXTDeal workspace</Link></header>
    <section className={styles.intro}><p className={styles.eyebrow}>CONNECTION CENTER</p><h1>Your assistants.<br />Your permissions.</h1><p>Connect an assistant to the departments you choose. Review and execute consequential actions inside NXTDeal.</p></section>
    {error && <section className={styles.panel} role="alert"><p>{error}</p><Link href="/" target="_blank" rel="noopener noreferrer">Open sign in</Link> <button disabled={busy} onClick={() => act(load)}>Retry</button></section>}
    {notice && <p role="status">{notice}</p>}
    {review && <section className={styles.panel} aria-label="Review assistant access"><h2>Connect {review.client_name}?</h2>
      <p>This assistant will act as your employee account within the selected departments. Access expires after 30 days and can be revoked here. Approval and execution remain in NXTDeal.</p>
      <p><strong>Requested access:</strong> read department data{review.scopes.includes("nxtdeal:propose") ? " and prepare action proposals" : " only"}.</p>
      <p>Return address: <code>{review.redirect_uri}</code></p><p>Client: <code>{review.client_id}</code></p>
      <fieldset><legend>Departments this assistant may access</legend>{review.departments.map(d => <label key={d} style={{ display: "block", margin: "10px 0" }}><input type="checkbox" checked={departments.includes(d)} onChange={e => setDepartments(prev => e.target.checked ? [...prev, d] : prev.filter(x => x !== d))} /> {d}</label>)}</fieldset>
      <div className={styles.export}><button disabled={busy || !departments.length} onClick={() => act(() => consent(true))}>Allow selected access</button><button disabled={busy} onClick={() => act(() => consent(false))}>Deny</button></div>
    </section>}
    {setup && <>
      <section className={styles.panel}><h2>Connect your AI interface</h2><p>Use this MCP server address in an assistant that supports remote MCP, OAuth authorization code, and S256 PKCE:</p><p style={{ overflowWrap: "anywhere" }}><code>{setup.mcp_url}</code></p>
        <ol><li>Start a custom MCP connection in your assistant’s settings.</li><li>Copy its exact OAuth callback URL and register it below (administrator required).</li><li>Enter the returned client ID in the assistant. This is a public client; no client secret is used.</li><li>Complete NXTDeal sign-in and approve the departments in the consent screen.</li></ol>
        <p>ChatGPT, Claude, Copilot and other interfaces have different setup options. Registration does not prove a connection: complete the assistant’s sign-in flow and verify a tool call. Never paste your NXTDeal session token into an assistant.</p>
      </section>
      {admin && <section className={styles.panel}><h2>Register an assistant</h2><p>Use the callback shown by your assistant’s connection settings. Registering it enables sign-in requests; each employee must still consent.</p>
        <form onSubmit={e => { e.preventDefault(); act(async () => { const created = await request("/clients", { name, redirect_uris: [callback] }); setName(""); setCallback(""); await load(); setNotice(`Registered ${created.client_name}. Client ID: ${created.client_id}`); }); }}>
          <label className={styles.field}>Assistant name<input required maxLength={100} value={name} onChange={e => setName(e.target.value)} placeholder="My ChatGPT connection" /></label>
          <label className={styles.field}>Exact HTTPS callback URL<input required type="url" value={callback} onChange={e => setCallback(e.target.value)} placeholder="Copy from the assistant’s connection settings" /></label>
          <p><button disabled={busy}>Register callback</button></p>
        </form>
        {setup.clients.map(c => <div className={styles.proposal} key={c.id}><strong>{c.name}</strong><p style={{ overflowWrap: "anywhere" }}><code>{c.id}</code><br />{JSON.parse(c.redirects).join(", ")}</p><p>{c.disabled ? "Disabled" : "Registered; employee consent required"}</p><button disabled={busy || !!c.disabled} onClick={() => act(async () => { if (!window.confirm(`Disable ${c.name} and revoke all of its employee connections?`)) return; await request(`/clients/${encodeURIComponent(c.id)}`, undefined, "DELETE"); await load(); })}>Disable and revoke access</button></div>)}
      </section>}
      <section className={styles.panel}><h2>Your assistant connections</h2><p>Revocation blocks future requests and refreshes. It does not cancel a request already in progress.</p>
        {!setup.grants.length && <p>No assistant has been granted access yet.</p>}
        {setup.grants.map(g => <div className={styles.proposal} key={g.id}><strong>{g.name}</strong><p>{JSON.parse(g.departments).join(", ")} · {g.scopes}</p><p>{g.revoked ? "Revoked" : g.expires * 1000 < checkedAt ? "Expired" : `Expires ${new Date(g.expires * 1000).toLocaleString()}`}</p><button disabled={busy || !!g.revoked} onClick={() => act(async () => { await request(`/connections/${encodeURIComponent(g.id)}`, undefined, "DELETE"); await load(); })}>Revoke connection</button></div>)}
      </section>
      {setup.chrono && <section className={styles.panel}><h2>Chrono</h2><p>Read-only workspace summaries and saved decision analyses. These reads do not export dealership data or recalculate predictions.</p><p>Status: <strong>{setup.chrono.status.replaceAll("_", " ")}</strong></p><p>Business: {setup.chrono.business || "Not selected"}. Credential: {setup.chrono.credential_configured ? "Configured" : "Not configured"}.</p>
        {!!setup.chrono.missing.length && <p>Server setup requires {setup.chrono.missing.join(" and ")}. Use a Chrono API token bound to the intended business; store it in the deployment’s secret settings.</p>}
        <button disabled={busy || !!setup.chrono.missing.length} onClick={() => act(async () => { const check = await request("/chrono/check", {}); setNotice(check.status === "available" ? "Chrono returned an authorized response for the configured business." : check.reason); })}>Verify Chrono connection</button>
      </section>}
    </>}
  </main>;
}
