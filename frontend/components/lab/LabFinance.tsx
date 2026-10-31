"use client";
import { WorkButton, WorkInput } from "./../WorkspaceUi";
import {useEffect,useRef,useState} from "react";
import type {Plan,Request} from "./LabWorkspace";
import styles from "./DealershipLab.module.css";
type Field=[string,string,number,number,number,string];
type Model={finance:{scenario:Record<string,number>};profile:{currency:string};dealership:{kind:string}};
type Setup={workspace:Plan;input:Model;finance_fields:Field[]};
type Props={plan:Plan;request:Request;onSaved:(plan:Plan)=>void;onDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void};
const help:Record<string,string>={
 "Cash & earnings":"Opening cash, expenses and cash payments are whole-group amounts, not per-rooftop amounts. Other expense reduces both profit and cash; depreciation reduces profit but is not a cash payment. Capital spending, principal payments and owner distributions reduce cash without reducing modeled profit. Avoid repeating costs already entered in the operating plan.",
 "Existing BHPH portfolio":"Opening receivables are the whole-group principal balance. Remaining term sets the existing portfolio’s payment schedule; the customer interest rate below also applies to this portfolio.",
 "New BHPH originations":"These assumptions apply to financed pre-owned sales. Down payment is per vehicle, and financing share applies to sold vehicles. New loan collections begin in the following month.",
 "Collections & losses":"Collection rate applies to scheduled payments. Defaults apply to outstanding principal each month. Recovery is delayed by the entered number of months. These are aggregate planning assumptions, not loan servicing or credit decisions.",
 "Repossession assumptions":"Repossession and recovery costs are modeled from defaults. This does not initiate repossessions, create inventory records or authorize customer contact.",
};
export function LabFinance({plan,request,onSaved,onDirty,onBusy}:Props){
 const [data,setData]=useState<Setup|null>(null),[values,setValues]=useState<Record<string,number>>({}),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState(""),[retry,setRetry]=useState(0);
 const pending=useRef(false),base=`/workspaces/${plan.id}/setup`;
 useEffect(()=>{let active=true;request<Setup>(base).then(d=>{if(active){setData(d);setValues(Object.fromEntries(d.finance_fields.map(([key])=>[key,d.input.finance.scenario[key]])));setError("");}}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[base,request,retry]);
 useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
 useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
 async function save(){if(!data||pending.current)return;pending.current=true;setBusy(true);setError("");setMessage("");try{const saved=await request<Plan>(base,"POST",{revision:data.workspace.revision,action:"finance",values:{assumptions:values}});const input=saved.model_definition as Model;setData({...data,workspace:saved,input});setValues(Object.fromEntries(data.finance_fields.map(([key])=>[key,input.finance.scenario[key]])));setDirty(false);onSaved(saved);setMessage("Financial assumptions saved. Compare profit and cash using the reviewed model.");}catch(e){setError(e instanceof Error?e.message:"Unable to save financial assumptions.");}finally{pending.current=false;setBusy(false);}}
 if(!data)return <section className={styles.panel}>{error?<p role="alert">{error} <WorkButton type="submit" onClick={()=>setRetry(v=>v+1)}>Retry</WorkButton></p>:<p>Loading financial assumptions…</p>}</section>;
 return <form onSubmit={e=>{e.preventDefault();void save();}}><section className={styles.panel}><h3>{plan.name} · financial assumptions</h3><p>{data.input.dealership.kind} · {data.input.profile.currency}</p><p>{plan.parent_id?"You are editing this option’s financial assumptions. Its source baseline remains unchanged.":"You are editing current-dealership financial assumptions. A real-data baseline needs a fresh source review after changes."}</p><p>Planning profit and cash are different outcomes. Inventory growth, receivables and cash payments can consume cash even when profit is positive.</p>{error&&<p role="alert" className={styles.error}>{error}</p>}{message&&<p role="status">{message}</p>}</section><fieldset className={styles.notebookFields} disabled={busy||plan.archived}>
 {[...new Set(data.finance_fields.map(f=>f[5]))].map(group=><section className={styles.panel} key={group}><h3>{group}</h3><p>{help[group]}</p><div className={styles.fields}>{data.finance_fields.filter(f=>f[5]===group).map(([key,label,min,max,integer])=><label key={key}>{label}<WorkInput required type="number" min={min} max={max} step={integer?1:"any"} value={Number.isFinite(values[key])?values[key]:""} onChange={e=>{setValues({...values,[key]:e.target.value===""?NaN:Number(e.target.value)});setDirty(true);setMessage("");}}/></label>)}</div></section>)}
 {!data.input.dealership.kind.includes("BHPH")&&<p>BHPH portfolio inputs apply only to a BHPH dealership model. Existing inactive assumptions are preserved.</p>}<WorkButton type="submit" disabled={!dirty||busy}>Save financial assumptions</WorkButton></fieldset></form>;
}
