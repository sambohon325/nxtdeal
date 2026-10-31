"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders, getSession } from "@/lib/auth";
import styles from "./page.module.css";
import ActionForm, { type InputSchema } from "./ActionForm";
import DepartmentWorkbench from "./DepartmentWorkbench";
import PolicyEditor, { type Policy } from "./PolicyEditor";

type Tool = { id: string; kind: string; risk: number; permitted: boolean; connected: boolean; input_schema?: InputSchema };
type Agent = { id: string; department: string; purpose: string; maturity: string; responsibilities: string[]; kpis: string[]; tools: Tool[]; automations: { id: string; description: string; trigger: string }[] };
type Proposal = { id: string; department: string; user_id: string; capability: string; status: string; approval_required: boolean; approved_by: string | null; input: { lead_id?: string; description?: string } };
type Catalog = { agents: Agent[]; providers: string[]; policy: Policy; chrono: { status: string } };

async function request(path: string, body?: unknown, method?: string) {
  const response = await fetch(`${API_BASE}/agent-fabric${path}`, {
    method: method || (body === undefined ? "GET" : "POST"),
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  const result = await response.json();
  if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Request could not be completed");
  return result;
}

export default function AgentsPage() {
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [department, setDepartment] = useState("");
  const [proposals, setProposals] = useState<Proposal[]>([]);
  const [record, setRecord] = useState("");
  const [provider, setProvider] = useState("chatgpt");
  const [result, setResult] = useState<unknown>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [identity, setIdentity] = useState({ employeeId: "", role: "" });
  const [actionTool, setActionTool] = useState<Tool | null>(null);
  const [subscriptions, setSubscriptions] = useState<{ automation_id: string; enabled: boolean }[]>([]);
  const agent = catalog?.agents.find(a => a.department === department);

  async function refresh() {
    const [next, queue, subscriptions] = await Promise.all([request("/catalog"), request("/proposals"), request("/subscriptions")]);
    setCatalog(next); setProposals(queue.proposals);
    setSubscriptions(subscriptions.subscriptions);
    setDepartment(previous => previous || next.agents[0]?.department || "");
  }
  useEffect(() => {
    let active = true;
    async function load() {
      const session = getSession();
      if (!session) throw new Error("Sign in to your NXTDeal workspace to use department agents.");
      const [next, queue, subscriptions] = await Promise.all([request("/catalog"), request("/proposals"), request("/subscriptions")]);
      if (!active) return;
      setIdentity(session); setCatalog(next); setProposals(queue.proposals);
      setSubscriptions(subscriptions.subscriptions);
      setDepartment(next.agents[0]?.department || "");
    }
    load().catch(e => { if (active) setError(e.message); });
    return () => { active = false; };
  }, []);

  async function act(action: () => Promise<unknown>) {
    setBusy(true); setError("");
    try { setResult(await action()); await refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Request failed"); }
    finally { setBusy(false); }
  }

  return <main className={styles.page}>
    <header className={styles.header}><Link href="/workspace">← NXTDeal workspace</Link><Link href="/agents/connections">Connections &amp; assistant access</Link></header>
    <div className={styles.intro}><p className={styles.eyebrow}>INTEGRATION &amp; AUTOMATION FABRIC</p><h1>Your departments.<br />One operating layer.</h1><p>Department agents share NXTDeal permissions, knowledge and actions across your chosen AI interfaces.</p></div>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {!catalog && !error && <p role="status">Loading your department capabilities…</p>}
    {catalog && <>
      <div className={styles.metrics}><div><strong>{catalog.agents.length}</strong><span>Departments available to you</span></div><div><strong>Human review</strong><span>Consequential actions require approval</span></div><div><strong>Chrono {catalog.chrono.status}</strong><span>Engine connection pending</span></div></div>
      <div className={styles.layout}>
        <nav aria-label="Department agents" className={styles.departments}>{catalog.agents.map(a => <button key={a.id} className={department === a.department ? styles.selected : ""} aria-pressed={department === a.department} onClick={() => { setDepartment(a.department); setResult(null); setActionTool(null); }}><strong>{a.department === "fi" ? "F&I" : a.department.toUpperCase()}</strong><small>{a.maturity === "native" ? "Native capabilities" : a.maturity === "reference" ? "Reference pack" : "Scaffold"}</small></button>)}</nav>
        {agent && <section className={styles.panel}>
          <p className={styles.eyebrow}>NXTDEAL {agent.department.toUpperCase()}</p><h2>{agent.purpose}</h2>
          <p>{agent.responsibilities.join(" · ")}</p>
          <div className={styles.workflow}><h3>Department workbench</h3><p>Review current exceptions, assign accountable follow-up, and track recorded outcomes.</p><button disabled={busy} onClick={() => { setRecord(""); act(() => request("/invoke", { department, capability: `${department}.workbench.read`, input: {} })); }}>Open department workbench</button></div><h3>Capabilities</h3><p>Available reads use current dealership records. Actions are prepared for review before execution.</p>
          <label className={styles.field}>Record ID (optional for lists; required for a customer timeline)<input value={record} onChange={e => setRecord(e.target.value)} placeholder="Customer, lead or other record ID" /></label><div className={styles.tools}>{agent.tools.map(tool => <div key={tool.id}><span>{tool.id}<small>{tool.kind} · Risk {tool.risk}</small></span><span>{!tool.permitted ? "Restricted" : !tool.connected ? "Connection pending" : tool.kind === "READ" ? <button disabled={busy} onClick={() => act(() => request("/invoke", { department, capability: tool.id, input: record.trim() ? { record_id: record.trim() } : {} }))}>Read</button> : <button disabled={busy} onClick={() => setActionTool(tool)}>Prepare</button>}</span></div>)}</div>
          {actionTool?.input_schema && <div className={styles.workflow}><h3>{actionTool.id}</h3><ActionForm key={actionTool.id} schema={actionTool.input_schema} busy={busy} submit={input => act(() => request("/invoke", { department, capability: actionTool.id, input, idempotency_key: crypto.randomUUID() }))} /></div>}
          <h3>Automations</h3>
          {agent.automations.length === 0 ? <p>No workflows registered for this department yet.</p> : <>
            {department === "sales" && <label className={styles.field}>Lead record ID<input value={record} onChange={e => setRecord(e.target.value)} placeholder="Enter an existing lead ID" /></label>}
            {agent.automations.map(a => <div className={styles.workflow} key={a.id}><p>{a.description}</p><button disabled={busy || (a.id === "sales.stale_lead_recovery" && !record.trim())} onClick={() => act(() => request(`/automations/${a.id}/run`, { record_id: record.trim() || null, provider: "nxtdeal", idempotency_key: crypto.randomUUID() }))}>{a.id === "sales.stale_lead_recovery" ? "Prepare follow-up task" : "Run review"}</button></div>)}
          </>}
          <h3>AI interface manifest</h3><p>Export the same authorized definition for each interface. The authenticated MCP endpoint is /agent-fabric/mcp. Optional assistant connections and department consent are managed in the connection center. These capabilities also work directly in NXTDeal.</p>
          <div className={styles.export}><label>Interface<select value={provider} onChange={e => setProvider(e.target.value)}>{catalog.providers.map(p => <option key={p}>{p}</option>)}</select></label><button disabled={busy} onClick={() => act(() => request(`/manifest/${department}/${provider}`))}>View manifest</button></div>
          {agent.automations.filter(a => a.trigger !== "manual").map(a => <label key={a.id} style={{ display: "block", marginTop: 12 }}><input type="checkbox" disabled={busy} checked={subscriptions.some(s => s.automation_id === a.id && s.enabled)} onChange={e => act(() => request(`/subscriptions/${a.id}`, { enabled: e.target.checked }, "PUT"))} /> Prepare {a.id.replaceAll("_", " ")} automatically when an event qualifies</label>)}
          <p className={styles.kpis}>Measures: {agent.kpis.join(" · ")}</p>
        </section>}
      </div>
      {identity.role === "ADMIN" && <section className={styles.panel}><PolicyEditor key={JSON.stringify(catalog.policy)} policy={catalog.policy} capabilities={[...new Set(catalog.agents.flatMap(a => a.tools.map(t => t.id)))].sort()} busy={busy} save={value => act(() => request("/policy", value, "PUT"))} /><p><Link href="/readiness">Manage dealership connections</Link></p><button disabled={busy} onClick={() => act(() => request("/events/process", {}))}>Process queued events</button><button disabled={busy} onClick={() => act(() => request("/receipts"))}>View automation activity</button><button disabled={busy} onClick={() => act(() => request("/audit"))}>View audit trail</button><button disabled={busy} onClick={() => act(() => request("/readiness"))}>View connection readiness</button></section>}
      <section className={styles.panel}><h2>Action review queue</h2><p>Review prepared actions. Approval requires a different administrator; the requesting employee executes the approved action.</p>
        {proposals.length === 0 && <p>No prepared actions yet.</p>}
        {proposals.map(p => <article className={styles.proposal} key={p.id}><div><strong>{p.capability}</strong><p>{p.input.description || JSON.stringify(p.input)}</p><small>{p.input.lead_id} · {p.status} · {p.approval_required ? "Approval required" : "Within dealer policy"}</small></div><div className={styles.actions}>
          {p.status === "proposed" && identity.role === "ADMIN" && p.user_id !== identity.employeeId && <button disabled={busy} onClick={() => act(() => request(`/proposals/${p.id}/approve`, {}))}>Approve</button>}
          {["proposed", "approved"].includes(p.status) && p.user_id === identity.employeeId && <button disabled={busy || (p.approval_required && !p.approved_by)} onClick={() => act(() => request(`/proposals/${p.id}/execute`, {}))}>Execute action</button>}
          {["proposed", "approved"].includes(p.status) && <button disabled={busy} onClick={() => act(() => request(`/proposals/${p.id}/reject`, {}))}>Reject</button>}
          {["executing", "needs_review"].includes(p.status) && identity.role === "ADMIN" && <details><summary>Reconcile uncertain outcome</summary><form onSubmit={e => { e.preventDefault(); const fields = new FormData(e.currentTarget); act(() => request(`/proposals/${p.id}/reconcile`, { outcome: fields.get("outcome"), evidence: fields.get("evidence") })); }}><label>Verified outcome<select name="outcome"><option value="confirmed_executed">Confirmed executed</option><option value="confirmed_not_executed">Confirmed not executed</option></select></label><label>Evidence reference<input name="evidence" required maxLength={500} /></label><button disabled={busy}>Record reviewed outcome</button></form></details>}
        </div></article>)}
      </section>
      {result !== null && <section className={styles.panel} aria-live="polite"><h2>Result</h2><DepartmentWorkbench result={result} busy={busy} prepare={(capability, input) => act(() => request("/invoke", { department, capability, input, idempotency_key: crypto.randomUUID() }))} /></section>}
    </>}
  </main>;
}
