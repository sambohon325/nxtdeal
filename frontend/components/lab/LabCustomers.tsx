"use client";
import { WorkInput, WorkButton } from "./../WorkspaceUi";

import {useEffect,useRef,useState} from "react";
import type {Plan,Request} from "./LabWorkspace";
import styles from "./DealershipLab.module.css";

type Field=[string,string,number,number,number,string?];
type Values=Record<string,number>;
type Model={profile:Values&{currency:string};segments:Record<"new"|"used",Values>;workflow:{calibration:unknown[]}};
type Setup={workspace:Plan;input:Model;customer_fields:Field[];segment_fields:Field[];used_only:boolean};
type Props={plan:Plan;request:Request;onSaved:(plan:Plan)=>void;onDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void};

export function LabCustomers({plan,request,onSaved,onDirty,onBusy}:Props){
 const [data,setData]=useState<Setup|null>(null),[profile,setProfile]=useState<Values>({}),[segments,setSegments]=useState<Record<"new"|"used",Values>>({new:{},used:{}});
 const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState(""),[retry,setRetry]=useState(0);
 const pending=useRef(false),base=`/workspaces/${plan.id}/setup`;
 useEffect(()=>{let active=true;request<Setup>(base).then(value=>{if(!active)return;setData(value);setProfile(Object.fromEntries(value.customer_fields.map(([key])=>[key,value.input.profile[key]])));setSegments(structuredClone(value.input.segments));setError("");}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[base,request,retry]);
 useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
 useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
 function edit(){setDirty(true);setMessage("");}
 function field(spec:Field,value:number,update:(value:number)=>void,disabled=false){const[key,label,min,max,step]=spec;return <label key={key}>{label}<WorkInput type="number" required min={min} max={max} step={step===1?1:"any"} disabled={disabled} value={Number.isFinite(value)?value:""} onChange={e=>{update(e.target.value===""?NaN:Number(e.target.value));edit();}}/></label>;}
 async function save(){
  if(!data||pending.current)return;pending.current=true;setBusy(true);setError("");setMessage("");
  try{const saved=await request<Plan>(base,"POST",{revision:data.workspace.revision,action:"customers",values:{profile,segments}});const input=saved.model_definition as Model;setData({...data,workspace:saved,input});setProfile(Object.fromEntries(data.customer_fields.map(([key])=>[key,input.profile[key]])));setSegments(structuredClone(input.segments));setDirty(false);onSaved(saved);setMessage("Customer and inventory assumptions saved. Review the updated inputs before comparing.");}
  catch(e){setError(e instanceof Error?e.message:"Unable to save assumptions.");}finally{pending.current=false;setBusy(false);}
 }
 if(!data)return <section className={styles.panel}>{error?<p role="alert">{error} <WorkButton type="submit" onClick={()=>setRetry(v=>v+1)}>Retry</WorkButton></p>:<p>Loading customer and inventory assumptions…</p>}</section>;
 return <form onSubmit={e=>{e.preventDefault();void save();}}>
  <section className={styles.panel}><h3>{plan.name} · customers & inventory</h3><p>Monthly quantities are per rooftop; money is in {data.input.profile.currency}. These are planning assumptions, not live inventory or customer records.</p><p>{plan.parent_id?"Changes apply only to this option’s model. The source dealership remains unchanged.":"Changes update the current dealership’s model."} Real-data source reviews become stale when these inputs change.</p>{data.input.workflow.calibration.length>0&&<p>Recorded-source references remain in the source register. Manual edits are not automatically reconciled with those records.</p>}{error&&<p role="alert" className={styles.error}>{error}</p>}{message&&<p role="status">{message}</p>}</section>
  <fieldset className={styles.notebookFields} disabled={busy||plan.archived}>
   {[...new Set(data.customer_fields.map(f=>f[5]))].map(group=><section key={group} className={styles.panel}><h3>{group}</h3><div className={styles.fields}>{data.customer_fields.filter(f=>f[5]===group).map(f=>field(f,profile[f[0]],value=>setProfile({...profile,[f[0]]:value}),data.used_only&&f[0]==="new_share"))}</div>{group==="Sales funnel"&&<p>Each conversion rate applies to the preceding stage. New-vehicle demand share is separate from stock mix.</p>}{group==="Service"&&<p>Include repair labor in gross consistently with the operating plan’s payroll-already-in-gross setting.</p>}</section>)}
   <section className={styles.panel}><h3>Inventory & vehicle economics</h3><p>Combined stock and monthly arrivals cannot exceed 10,000 vehicles per rooftop. Vehicle gross may be negative, but cannot exceed selling price. Enter recon costs consistently to avoid counting them again in operating expenses.</p>{data.used_only&&<p>This dealership type requires zero new-vehicle demand, stock and arrivals.</p>}{(["new","used"] as const).map(side=><article key={side}><h4>{side==="new"?"New vehicles":"Pre-owned vehicles"}</h4><div className={styles.fields}>{data.segment_fields.map(f=>field(f,segments[side][f[0]],value=>setSegments({...segments,[side]:{...segments[side],[f[0]]:value}}),data.used_only&&side==="new"))}</div></article>)}</section>
   <WorkButton type="submit" disabled={!dirty||busy}>Save customer & inventory assumptions</WorkButton>
  </fieldset>
 </form>;
}
