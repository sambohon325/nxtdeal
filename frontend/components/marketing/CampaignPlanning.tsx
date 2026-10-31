"use client";
import { WorkButton, WorkInput, WorkTextarea, WorkSelect } from "./../WorkspaceUi";
import { useEffect, useState } from "react";
import { crmRequest } from "@/lib/salesCrm";
import styles from "./MarketingWorkspace.module.css";

type Brief = { name:string; objective:string; department:string; starts_on:string; ends_on:string; budget:number; currency:string; target_appointments:number; confirmed_capacity:number|null; capacity_evidence:string; audience_id:string|null; campaign_id:string|null; offer:string; routing_owner_id:string|null; response_minutes:number; next_step:string; exclusions:string };
type Saved = Brief & {id:string;revision:number;capacity_review:string};
type Data = {briefs:Saved[];choices:Record<string,{id:string;name:string}[]>};
const blank = ():Brief => ({name:"",objective:"",department:"Service",starts_on:"",ends_on:"",budget:0,currency:"USD",target_appointments:0,confirmed_capacity:null,capacity_evidence:"",audience_id:null,campaign_id:null,offer:"",routing_owner_id:null,response_minutes:30,next_step:"Review the qualifying request and confirm an available appointment.",exclusions:"Exclude opted-out contacts, existing bookings and recently contacted customers."});
export function CampaignPlanning({canEdit,onDraftOpenChange,onSavingChange}:{canEdit:boolean;onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void}){
 const [data,setData]=useState<Data|null>(null),[draft,setDraft]=useState<Brief|null>(null),[selected,setSelected]=useState<Saved|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const dirty=Boolean(draft&&(!selected||Object.keys(blank()).some(k=>draft[k as keyof Brief]!==selected[k as keyof Brief])));
 useEffect(()=>{onDraftOpenChange?.(dirty);return()=>onDraftOpenChange?.(false)},[dirty,onDraftOpenChange]);
 useEffect(()=>{onSavingChange?.(busy);return()=>onSavingChange?.(false)},[busy,onSavingChange]);
 async function load(){setBusy(true);setError("");try{setData(await crmRequest<Data>("/marketing/planning"))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 useEffect(()=>{void load()},[]);
 async function save(){if(!draft)return;setBusy(true);setError("");try{
  const clean=Object.fromEntries(Object.keys(blank()).map(k=>[k,draft[k as keyof Brief]]));
  const saved=await crmRequest<Saved>(`/marketing/planning${selected?`/${encodeURIComponent(selected.id)}`:""}`,{method:selected?"PUT":"POST",body:JSON.stringify({...clean,...(selected?{revision:selected.revision}:{})})});
  setSelected(saved);setDraft(saved);setData(d=>d?{...d,briefs:[saved,...d.briefs.filter(x=>x.id!==saved.id)]}:d);setNotice("Brief saved. Campaign execution and channel approvals remain separate.");
 }catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 const patch=(key:keyof Brief,value:string|number|null)=>setDraft(d=>d?{...d,[key]:value}:d);
 return <section className={styles.panel} aria-label="Campaign planning">
  <h3>Plan demand around the dealership</h3><p>Set the objective, budget, timing and response owner. Link the existing audience and campaign so each team works from the same records.</p>
  <p>Budgets are planned allocations. Capacity is a dated team check, not a reservation or a forecast. Saving a brief does not send messages, approve spend or create BDC tasks.</p>
  {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  <div className={styles.tabs}><WorkButton type="submit" disabled={busy||dirty} onClick={()=>void load()}>Refresh briefs</WorkButton>{canEdit&&<WorkButton type="submit" disabled={busy||dirty} onClick={()=>{setSelected(null);setDraft(blank());setNotice("")}}>New campaign brief</WorkButton>}</div>
  {!data&&busy&&<p role="status">Loading campaign briefs…</p>}
  <div className={styles.journeyLayout}><aside>{data?.briefs.map(b=><button className={styles.result} disabled={busy||dirty} key={b.id} onClick={()=>{setSelected(b);setDraft(b);setNotice("")}}><span>{b.name}<small>{b.department} · {b.starts_on} to {b.ends_on}<br/>{b.currency} {b.budget.toLocaleString()} planned</small></span></button>)}{data&&!data.briefs.length&&<p>No campaign briefs yet.</p>}</aside>
  {draft&&<form onSubmit={e=>{e.preventDefault();void save()}}><fieldset disabled={busy||!canEdit} className={styles.journeyFields}>
   <label>Campaign brief name<WorkInput required maxLength={120} value={draft.name} onChange={e=>patch("name",e.target.value)}/></label>
   <label>Objective<WorkTextarea required minLength={3} maxLength={1000} value={draft.objective} onChange={e=>patch("objective",e.target.value)}/></label>
   <label>Department<WorkSelect value={draft.department} onChange={e=>patch("department",e.target.value)}><option>Sales</option><option>Service</option></WorkSelect></label>
   <label>Starts on<WorkInput required type="date" value={draft.starts_on} onChange={e=>patch("starts_on",e.target.value)}/></label><label>Ends on<WorkInput required type="date" min={draft.starts_on} value={draft.ends_on} onChange={e=>patch("ends_on",e.target.value)}/></label>
   <label>Planned budget<WorkInput required type="number" min={0} max={10000000} step="0.01" value={draft.budget} onChange={e=>patch("budget",Number(e.target.value))}/></label><label>Currency<WorkSelect value={draft.currency} onChange={e=>patch("currency",e.target.value)}><option>USD</option><option>CAD</option></WorkSelect></label>
   <label>Appointment target<WorkInput required type="number" min={0} max={100000} value={draft.target_appointments} onChange={e=>patch("target_appointments",Number(e.target.value))}/></label>
   <label>Team-confirmed capacity (optional)<WorkInput type="number" min={0} max={100000} value={draft.confirmed_capacity??""} onChange={e=>patch("confirmed_capacity",e.target.value===""?null:Number(e.target.value))}/></label>
   <label>Capacity source and check date<WorkTextarea required={draft.confirmed_capacity!==null} maxLength={1000} value={draft.capacity_evidence} onChange={e=>patch("capacity_evidence",e.target.value)}/></label>
   {draft.confirmed_capacity===null?<p>Capacity unknown. Check staffing and appointment availability before increasing demand.</p>:draft.confirmed_capacity<draft.target_appointments?<p role="status">The target exceeds recorded capacity. Review staffing, timing or the target before launch.</p>:<p>The recorded capacity covers the target. Confirm that this check is still current before launch.</p>}
   {([['audience_id','audiences','Shared audience'],['campaign_id','campaigns','Existing campaign or outreach sequence'],['routing_owner_id','owners','BDC response owner']] as const).map(([key,choices,label])=><label key={key}>{label}<WorkSelect value={draft[key]??""} onChange={e=>patch(key,e.target.value||null)}><option value="">Not selected</option>{data?.choices[choices]?.map(c=><option key={c.id} value={c.id}>{c.name} · {c.id}</option>)}</WorkSelect></label>)}
   <label>Offer and expiration details<WorkTextarea maxLength={2000} value={draft.offer} onChange={e=>patch("offer",e.target.value)}/></label>
   <label>Audience exclusions<WorkTextarea maxLength={1500} value={draft.exclusions} onChange={e=>patch("exclusions",e.target.value)}/></label><p>These are review instructions. Channel consent and eligibility must still pass at execution.</p>
   <label>Response target (minutes)<WorkInput required type="number" min={1} max={10080} value={draft.response_minutes} onChange={e=>patch("response_minutes",Number(e.target.value))}/></label>
   <label>BDC next step after a qualifying request<WorkTextarea required minLength={3} maxLength={500} value={draft.next_step} onChange={e=>patch("next_step",e.target.value)}/></label>
   <p>Opens and clicks are marketing signals. A reply, call or booking request needs an assessed reason, owner, deadline and next step before it becomes agent work.</p>
   <WorkButton type="submit" disabled={!dirty}>{busy?"Saving…":"Save campaign brief"}</WorkButton>
  </fieldset><WorkButton type="button" disabled={busy} onClick={()=>{setDraft(null);setSelected(null);setError("")}}>{dirty?"Discard brief edits":"Close brief"}</WorkButton></form>}
  </div>
 </section>;
}
