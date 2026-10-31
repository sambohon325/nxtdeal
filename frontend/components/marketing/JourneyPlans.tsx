"use client";
import { WorkButton, WorkInput, WorkSelect } from "./../WorkspaceUi";

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import styles from "./MarketingWorkspace.module.css";
import emailStyles from "./DealerEmailStudio.module.css";
import { DealerEmailStudio } from "./DealerEmailStudio";
import { listAllTemplates, type EmailTemplate } from "@/lib/emailSms";
import { listAllLists, type MarketingList } from "@/lib/marketingLists";

type Step = { type: "email" | "sms" | "wait" | "condition" | "sales_handoff"; label: string; delay_minutes: number; content_asset_id: string | null; email_template_id?: string | null };
type Draft = { name: string; objective: string; trigger_type: string; audience_rule: string; audience_list_id?: string | null; steps: Step[] };
type Journey = Draft & { id: string; status: "draft" | "ready" | "paused" | "archived"; revision: number; updated_at: string; history: { action: string; actor: string; recorded_at: string; revision: number }[] };
const objectives = ["lead_nurture", "lost_lead_recovery", "service_retention", "equity_upgrade", "ownership_onboarding", "review_and_referral"];
const triggers = ["lead_created", "lead_status_changed", "vehicle_purchased", "service_due", "equity_threshold", "manual_audience"];
const types: Step["type"][] = ["email", "sms", "wait", "condition", "sales_handoff"];
const label = (s: string) => s.replaceAll("_", " ");
const step = (type: Step["type"], name: string, delay = 0): Step => ({ type, label: name, delay_minutes: delay, content_asset_id: null });
const templates: Draft[] = [
  { name: "New lead response", objective: "lead_nurture", trigger_type: "lead_created", audience_rule: "", steps: [step("email", "Introduce the dealership"), step("wait", "Allow time for a response", 60), step("email", "Offer help with next steps"), step("sales_handoff", "Assign follow-up to sales")] },
  { name: "Lost lead recovery", objective: "lost_lead_recovery", trigger_type: "lead_status_changed", audience_rule: "Lost leads eligible for follow-up", steps: [step("wait", "Wait before re-engagement", 10080), step("email", "Share relevant inventory"), step("condition", "Review customer response"), step("sales_handoff", "Reconnect with sales")] },
  { name: "Service retention", objective: "service_retention", trigger_type: "service_due", audience_rule: "Customers due for service", steps: [step("email", "Service reminder"), step("wait", "Allow time to book", 4320), step("email", "Offer appointment support")] },
];
const blank = (): Draft => ({ name: "", objective: "lead_nurture", trigger_type: "manual_audience", audience_rule: "", steps: [step("email", "First message")] });
function draftOf(j: Draft): Draft { return { name: j.name, objective: j.objective, trigger_type: j.trigger_type, audience_rule: j.audience_rule, audience_list_id:j.audience_list_id ?? null, steps: j.steps.map(s => ({ ...s })) }; }
async function request<T>(path = "", method = "GET", body?: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}/marketing/journeys${path}`, { method, headers: { ...authHeaders(), ...(body ? { "Content-Type": "application/json" } : {}) }, ...(body ? { body: JSON.stringify(body) } : {}) });
  const data = await response.json();
  if (!response.ok || data.error) throw new Error(typeof data.detail === "string" ? data.detail : data.error || "Unable to save journey. Check the required fields and reload if needed.");
  return data;
}

export function JourneyPlans({ canEdit,onDraftOpenChange,onSavingChange }: { canEdit: boolean;onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void }) {
  const [stage,setStage]=useState(0);
  const [compose,setCompose]=useState<number|null>(null);
  const [emails,setEmails]=useState<EmailTemplate[]>([]);
  const [audiences,setAudiences]=useState<MarketingList[]>([]);
  useEffect(()=>{Promise.all([listAllTemplates("email"),listAllLists()]).then(([e,a])=>{setEmails(e);setAudiences(a.filter(x=>!x.archived));}).catch(e=>setError(e.message));},[]);
  const [plans, setPlans] = useState<Journey[]>([]);
  const [selected, setSelected] = useState<Journey | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [filter, setFilter] = useState("current");
  const [query, setQuery] = useState("");
  const dirty = !!draft && (!selected || JSON.stringify(draft) !== JSON.stringify(draftOf(selected)));
  useEffect(()=>{onDraftOpenChange?.(dirty);return ()=>onDraftOpenChange?.(false)},[dirty,onDraftOpenChange]);
  useEffect(()=>{onSavingChange?.(busy);return ()=>onSavingChange?.(false)},[busy,onSavingChange]);
  const refresh = async () => { setLoading(true); setError(""); try { setPlans((await request<{ journeys: Journey[] }>()).journeys); } catch (e) { setError((e as Error).message); } finally { setLoading(false); } };
  useEffect(() => { void refresh(); }, []);
  const open = (j: Journey) => { setStage(0); setSelected(j); setDraft(draftOf(j)); setError(""); setNotice(""); };
  const save = async () => {
    if (!draft || busy) return;
    setBusy(true); setError(""); setNotice("");
    try { const saved = await request<Journey>(selected ? `/${encodeURIComponent(selected.id)}` : "", selected ? "PUT" : "POST", { ...draft, ...(selected ? { revision: selected.revision } : {}) }); setPlans(p => [saved, ...p.filter(j => j.id !== saved.id)]); setSelected(saved); setDraft(draftOf(saved)); setNotice("Journey saved as a draft. No messages were sent."); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const status = async (next: Journey["status"]) => {
    if (!selected || busy || dirty) return;
    setBusy(true); setError(""); setNotice("");
    try { const saved = await request<Journey>(`/${encodeURIComponent(selected.id)}/status`, "POST", { status: next, revision: selected.revision }); setPlans(p => p.map(j => j.id === saved.id ? saved : j)); setSelected(saved); setDraft(draftOf(saved)); setNotice(`Plan marked ${next}. Automatic enrollment and delivery are not enabled.`); }
    catch (e) { setError((e as Error).message); } finally { setBusy(false); }
  };
  const updateStep = (index: number, patch: Partial<Step>) => setDraft(d => d && ({ ...d, steps: d.steps.map((s, i) => i === index ? { ...s, ...patch } : s) }));
  const move = (index: number, offset: number) => setDraft(d => { if (!d) return d; const steps = [...d.steps]; [steps[index], steps[index + offset]] = [steps[index + offset], steps[index]]; return { ...d, steps }; });
  if(compose!==null)return <div><WorkButton type="button" onClick={()=>setCompose(null)}>← Back to journey</WorkButton><DealerEmailStudio canEdit={canEdit} onSaved={email=>{setEmails(es=>[email,...es.filter(e=>e.id!==email.id)]);updateStep(compose,{email_template_id:email.id,label:email.name});setCompose(null);}}/></div>;
  return <section className={emailStyles.studio} aria-label="Journey builder">
    <header><div><small>STAY IN TOUCH, WITHOUT THE GUESSWORK</small><h3>One journey. A clear next step.</h3><p>Choose your audience, add matching emails, and set the pace.</p></div><span className={emailStyles.badge}>{selected?.status ?? 'Draft'} · delivery not connected</span></header>
    {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
    {!draft?<><div className={styles.tabs}><WorkButton type="submit" disabled={loading} onClick={()=>void refresh()}>Refresh</WorkButton>{canEdit&&<WorkButton type="submit" onClick={()=>{setDraft(blank());setSelected(null);setStage(0)}}>Create a journey</WorkButton>}</div>{canEdit&&<div className={styles.channels}>{templates.map(t=><button key={t.name} onClick={()=>{setDraft(draftOf(t));setSelected(null);setStage(0)}}><strong>{t.name}</strong><small>Start with a suggested sequence →</small></button>)}</div>}<label>Find a journey<WorkInput value={query} onChange={e=>setQuery(e.target.value)}/></label><label>Show<WorkSelect value={filter} onChange={e=>setFilter(e.target.value)}><option value="current">Current journeys</option><option value="archived">Archived journeys</option></WorkSelect></label>{loading?<p>Loading journeys…</p>:plans.filter(j=>(filter==='archived'?j.status==='archived':j.status!=='archived')&&j.name.toLowerCase().includes(query.toLowerCase())).map(j=><button className={styles.result} key={j.id} onClick={()=>open(j)}><strong>{j.name}</strong><span>{j.steps.length} steps · {j.status}</span></button>)}</>:
    <><nav aria-label="Journey setup steps">{['Audience','Emails','Timing','Review'].map((name,i)=><WorkButton type="button" key={name} aria-current={stage===i?'step':undefined} onClick={()=>setStage(i)}>{i+1}. {name}</WorkButton>)}</nav>
    <form onSubmit={e=>{e.preventDefault();void save()}}><fieldset className={styles.journeyFields} disabled={!canEdit||busy||selected?.status==='archived'}>
    {stage===0&&<><label>Journey name<WorkInput required maxLength={120} value={draft.name} onChange={e=>setDraft({...draft,name:e.target.value})}/></label><label>What do you want to accomplish?<WorkSelect value={draft.objective} onChange={e=>setDraft({...draft,objective:e.target.value})}>{objectives.map(v=><option key={v} value={v}>{label(v)}</option>)}</WorkSelect></label><label>Who is this for?<WorkSelect value={draft.audience_list_id??''} onChange={e=>setDraft({...draft,audience_list_id:e.target.value||null})}><option value="">Choose a saved CRM list</option>{audiences.map(a=><option key={a.id} value={a.id}>{a.name} · {a.member_ids?.length??0} contacts</option>)}</WorkSelect></label><p>Lists come from NXTDeal’s CRM. Delivery eligibility and unsubscribe preferences still apply.</p><label>Audience notes<WorkInput maxLength={240} value={draft.audience_rule} onChange={e=>setDraft({...draft,audience_rule:e.target.value})}/></label><label>When should this journey start?<WorkSelect value={draft.trigger_type} onChange={e=>setDraft({...draft,trigger_type:e.target.value})}>{triggers.map(v=><option key={v} value={v}>{label(v)}</option>)}</WorkSelect></label></>}
    {(stage===1||stage===2)&&<><ol className={styles.journeySteps}>{draft.steps.map((s,i)=><li key={i}><div className={styles.tabs}><strong>{i+1}. {s.type==='wait'?'Wait':s.type==='email'?'Email':label(s.type)}</strong><WorkButton type="button" aria-label={`Move step ${i+1} up`} disabled={i===0} onClick={()=>move(i,-1)}>↑</WorkButton><WorkButton type="button" aria-label={`Move step ${i+1} down`} disabled={i===draft.steps.length-1} onClick={()=>move(i,1)}>↓</WorkButton><WorkButton type="button" disabled={draft.steps.length===1} onClick={()=>setDraft({...draft,steps:draft.steps.filter((_,n)=>n!==i)})}>Remove</WorkButton></div>
    {stage===1?<><label>Description<WorkInput value={s.label} maxLength={100} onChange={e=>updateStep(i,{label:e.target.value})}/></label>{s.type==='email'&&<><label>Choose a saved email<WorkSelect value={s.email_template_id??''} onChange={e=>updateStep(i,{email_template_id:e.target.value||null})}><option value="">Choose an email</option>{emails.map(email=><option key={email.id} value={email.id}>{email.name}</option>)}</WorkSelect></label><WorkButton type="button" onClick={()=>setCompose(i)}>Create a matching email →</WorkButton></>}<details><summary>Step options</summary><label>Action<WorkSelect value={s.type} onChange={e=>updateStep(i,{type:e.target.value as Step['type'],email_template_id:null})}>{types.map(t=><option key={t} value={t}>{label(t)}</option>)}</WorkSelect></label>{s.content_asset_id&&<p>Existing content attachment: {s.content_asset_id}</p>}</details></>:<label>Wait before this step (hours)<WorkInput type="number" min={0} max={8760} step={1/60} value={s.delay_minutes/60} onChange={e=>updateStep(i,{delay_minutes:Math.round(Number(e.target.value)*60)})}/></label>}</li>)}</ol>{stage===1&&<div className={styles.tabs}><WorkButton type="button" disabled={draft.steps.length>=20} onClick={()=>setDraft({...draft,steps:[...draft.steps,step('email','Next email')]})}>+ Add email</WorkButton><WorkButton type="button" disabled={draft.steps.length>=20} onClick={()=>setDraft({...draft,steps:[...draft.steps,step('wait','Give them time',1440)]})}>+ Add a wait</WorkButton></div>}</>}
    {stage===3&&<><h4>{draft.name||'Name your journey'}</h4><p>Audience: {audiences.find(a=>a.id===draft.audience_list_id)?.name||'Not selected'}</p><ol>{draft.steps.map((s,i)=><li key={i}>{s.delay_minutes?`After ${s.delay_minutes/60} hours: `:''}{s.label}{s.type==='email'?` — ${emails.find(e=>e.id===s.email_template_id)?.name||'Choose an email'}`:''}</li>)}</ol><p>This saves your sequence for review. Automatic enrollment and sending are not connected yet; marking ready does not send emails.</p><WorkButton type="submit" disabled={!dirty||!draft.name.trim()||draft.steps.some(s=>!s.label.trim())}>{busy?'Saving…':'Save journey draft'}</WorkButton></>}
    </fieldset><footer><WorkButton type="button" disabled={busy} onClick={()=>{setDraft(null);setSelected(null)}}>{dirty?'Discard edits':'Back to journeys'}</WorkButton><div>{stage>0&&<WorkButton type="button" onClick={()=>setStage(stage-1)}>← Back</WorkButton>} {stage<3&&<WorkButton type="button" onClick={()=>setStage(stage+1)}>Continue →</WorkButton>}</div></footer></form>
    {stage===3&&selected&&canEdit&&<div className={styles.tabs}>{(selected.status==='archived'?['draft']:['ready','paused','archived']).filter(s=>s!==selected.status).map(s=><WorkButton type="button" key={s} disabled={busy||dirty||(s==='ready'&&draft.steps.some(step=>step.type==='email'&&!step.email_template_id))} onClick={()=>void status(s as Journey['status'])}>{s==='ready'?'Mark ready for review':s==='archived'?'Archive journey':s==='draft'?'Restore draft':'Pause plan'}</WorkButton>)}<WorkButton type="submit" disabled={busy||dirty} onClick={()=>{setSelected(null);setDraft({...draftOf(selected),name:`${selected.name.slice(0,110)} (copy)`});setStage(0)}}>Duplicate journey</WorkButton></div>}
    {selected&&<details><summary>Revision history</summary>{selected.history.map(h=><p key={h.revision}>Revision {h.revision}: {h.action} · {new Date(h.recorded_at).toLocaleString()}</p>)}</details>}</>}
  </section>;
}
