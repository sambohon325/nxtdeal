"use client";
import { WorkButton, WorkSelect, WorkInput, WorkTextarea } from "./../WorkspaceUi";

import {useEffect, useRef, useState} from "react";
import type {Plan, Request} from "./LabWorkspace";
import styles from "./DealershipLab.module.css";

type Model = {
 profile:{name:string;country:string;region:string;city:string;currency:string};
 dealership:{kind:string;size:string};rooftops:number;
 workflow:{mode:string;selected:boolean;setup_steps:string[];setup_complete:boolean;calibration:unknown[];review:unknown};
};
type Setup = {workspace:Plan;input:Model;modes:Record<string,string>;kinds:string[];sizes:string[];baseline_ready:boolean;source_summary:string};
type Props = {plan:Plan;request:Request;onSaved:(plan:Plan)=>void;onDirty:(dirty:boolean)=>void;onBusy:(busy:boolean)=>void;onContinue:()=>void;onReports?:()=>void;reportSourcePlan?:Plan;onSourceReports?:(id:string)=>void;onOperating?:()=>void};
const modeHelp:Record<string,string> = {
 simulation:"Practice with clearly identified assumptions. No imported records are presented as actual performance.",
 real:"Use your dealership records and identify the source and reporting period before running a scenario.",
 hybrid:"Use the records you have and identify estimates separately. Future outcomes remain modeled.",
};

export function LabSetup({plan,request,onSaved,onDirty,onBusy,onContinue,onOperating,onReports,reportSourcePlan,onSourceReports}:Props){
 const [data,setData]=useState<Setup|null>(null),[error,setError]=useState(""),[message,setMessage]=useState("");
 const [busy,setBusy]=useState(false),[identityDirty,setIdentityDirty]=useState(false),[noteDirty,setNoteDirty]=useState(false),[note,setNote]=useState(""),[confirmed,setConfirmed]=useState(false);
 const [identity,setIdentity]=useState({kind:"",size:"",country:"United States",region:"Texas",city:"",rooftops:1});
 const [resetConfirmed,setResetConfirmed]=useState(false);
 const dirty=identityDirty||noteDirty;
 const [retry,setRetry]=useState(0);
 const pending=useRef(false);
 const base=`/workspaces/${plan.id}/setup`;
 useEffect(()=>{let active=true;request<Setup>(base).then(value=>{if(!active)return;setData(value);setIdentity({...value.input.dealership,country:value.input.profile.country,region:value.input.profile.region,city:value.input.profile.city,rooftops:value.input.rooftops});}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[base,request,retry]);
 useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
 useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
 async function save(action:string,values:Record<string,unknown>){
  if(!data||pending.current)return;
  pending.current=true;setBusy(true);setError("");setMessage("");
  try{
   const saved=await request<Plan>(base,"POST",{revision:data.workspace.revision,action,values});
   onSaved(saved);if(action==="configure"){setIdentityDirty(false);setResetConfirmed(false);}if(action==="baseline_review"){setNoteDirty(false);setConfirmed(false);}
   // Keep the authoritative revision even if the following read is interrupted.
   setData({...data,workspace:saved,input:saved.model_definition as Model});
   const next=await request<Setup>(base);setData(next);
   if(action==="configure"||!identityDirty)setIdentity({...next.input.dealership,country:next.input.profile.country,region:next.input.profile.region,city:next.input.profile.city,rooftops:next.input.rooftops});
   setMessage("Setup saved. Your source history is preserved.");
  }catch(e){setError(e instanceof Error?e.message:"Unable to save setup.");}
  finally{pending.current=false;setBusy(false);}
 }
 if(!data)return <section className={styles.panel}>{error?<p role="alert">{error} <WorkButton type="submit" onClick={()=>{setError("");setRetry(v=>v+1);}}>Retry</WorkButton></p>:<p>Loading dealership setup…</p>}</section>;
 const needsReset=identity.kind!==data.input.dealership.kind||identity.size!==data.input.dealership.size;
 return <>
  {data.workspace.imported_from&&<section className={styles.panel}><h3>Imported experiment source</h3><p>Starting inputs came from an experiment file. Review them against your own records; importing does not verify the figures.</p><details><summary>Original file provenance</summary><p>File data path: {data.workspace.imported_from.claimed_data_path} · format {data.workspace.imported_from.input_schema}</p><p style={{overflowWrap:"anywhere"}}>SHA-256: {data.workspace.imported_from.file_sha256}</p></details></section>}
  <section className={styles.panel}><h3>{plan.name} · setup & data sources</h3><p>Build the current dealership first. Each decision creates a separate option from these figures.</p><p>{data.source_summary}</p>{error&&<p role="alert" className={styles.error}>{error}</p>}{message&&<p role="status">{message}</p>}</section>
  {data.workspace.report_source&&<section className={styles.panel}><h3>Reports used for this option</h3><p>{reportSourcePlan?.name||"Source plan unavailable"} · {data.workspace.report_source.month} · report revision {data.workspace.report_source.revision} · {data.workspace.report_source.rooftop||"All reported rooftops"}</p><p>This option keeps the unit economics reviewed at that revision. Monthly reports remain with the source plan; its current reports may include later corrections. Opening them does not update this option.</p>{reportSourcePlan&&!reportSourcePlan.archived&&onSourceReports?<WorkButton type="button" disabled={dirty||busy} onClick={()=>onSourceReports(reportSourcePlan.id)}>Open source monthly reports</WorkButton>:<p>{reportSourcePlan?.archived?"Restore the source plan from Decisions > Saved decisions to open its monthly reports.":"The source plan is not available in your workspace. The saved calibration register remains below."}</p>}</section>}

  <fieldset disabled={busy||plan.archived} className={styles.notebookFields}>
   <section className={styles.panel}><h3>1. Choose your data path</h3><div className={styles.grid}>{Object.entries(data.modes).map(([mode,title])=><article key={mode}><h4>{title}</h4><p>{modeHelp[mode]}</p><WorkButton type="submit" disabled={dirty||data.input.workflow.selected&&data.input.workflow.mode===mode} onClick={()=>save("path",{mode})}>{data.input.workflow.selected&&data.input.workflow.mode===mode?"Selected":"Use this data path"}</WorkButton></article>)}</div><p>Changing the label never verifies figures or removes their source history. Save any edits before changing paths.</p></section>
   <form className={styles.panel} onSubmit={e=>{e.preventDefault();void save("configure",{...identity,reset_confirmed:resetConfirmed});}}><h3>2. Define the dealership</h3><div className={styles.fields}>
    <label>Dealership type<WorkSelect value={identity.kind} onChange={e=>{setIdentity({...identity,kind:e.target.value});setIdentityDirty(true);setResetConfirmed(false);}}>{data.kinds.map(v=><option key={v}>{v}</option>)}</WorkSelect></label>
    <label>Size preset<WorkSelect value={identity.size} onChange={e=>{setIdentity({...identity,size:e.target.value});setIdentityDirty(true);setResetConfirmed(false);}}>{data.sizes.map(v=><option key={v}>{v}</option>)}</WorkSelect></label>
    <label>Country<WorkSelect value={identity.country} onChange={e=>{setIdentity({...identity,country:e.target.value,region:e.target.value==="Canada"?"Ontario":"Texas"});setIdentityDirty(true);}}><option>United States</option><option>Canada</option></WorkSelect></label>
    <label>State / province<WorkInput value={identity.region} maxLength={100} required onChange={e=>{setIdentity({...identity,region:e.target.value});setIdentityDirty(true);}}/></label>
    <label>City<WorkInput value={identity.city} maxLength={100} onChange={e=>{setIdentity({...identity,city:e.target.value});setIdentityDirty(true);}}/></label>
    <label>Rooftops<WorkInput type="number" min={1} max={100} step={1} value={identity.rooftops} onChange={e=>{setIdentity({...identity,rooftops:Number(e.target.value)});setIdentityDirty(true);}}/></label>
   </div><p>Location changes update regional planning defaults and wage assumptions. Existing money values are not currency-converted.</p>{needsReset&&<label><WorkInput type="checkbox" checked={resetConfirmed} onChange={e=>setResetConfirmed(e.target.checked)}/>Replace staffing, stock, campaign and mix presets for this type/size. Previous versions remain saved.</label>}<WorkButton type="submit" disabled={!identityDirty||needsReset&&!resetConfirmed}>Save dealership setup</WorkButton></form>
   <section className={styles.panel}><h3>3. Review the model and its sources</h3><p>Bring monthly figures from an authorized export into Monthly reports, review the proposed changes, then create a separate calibrated option. Live connections do not currently populate this Lab automatically.</p>{onReports&&<WorkButton type="button" disabled={dirty||busy} onClick={onReports}>Open monthly reports and import preview →</WorkButton>}<p>Presets are assumptions. Imported-derived figures do not establish complete payroll, demand, inventory or financial records.</p><details><summary>Source register</summary><pre>{JSON.stringify(data.input.workflow.calibration,null,2)}</pre></details><details><summary>Inspect the complete saved model</summary><pre>{JSON.stringify(data.input,null,2)}</pre></details>
    {data.input.workflow.mode==="real"&&<><p>{data.baseline_ready?"Your baseline review matches the saved figures.":"Baseline source review is required. Changing the baseline requires a fresh review."}</p><label>Records and reporting period<WorkTextarea value={note} minLength={10} maxLength={1000} onChange={e=>{setNote(e.target.value);setNoteDirty(true);}}/></label><label><WorkInput type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>I reviewed the baseline against the named records. This declaration is not independent verification.</label><WorkButton type="submit" disabled={!confirmed||note.trim().length<10} onClick={()=>save("baseline_review",{note,confirmed})}>Save baseline source review</WorkButton></>}
   </section>
   <section className={styles.panel}><h3>Finish dealership setup</h3><p>Confirm each area after reviewing it. Completing setup records your acknowledgment; it does not verify records independently.</p>{onOperating&&<WorkButton type="button" disabled={dirty} onClick={onOperating}>Open departments & operating plan →</WorkButton>}<div className={styles.fields}>{[["path","Data path selected"],["identity","Dealership identity reviewed"],["operations","Departments and operating assumptions reviewed"],["data","Sources and reporting periods reviewed"],["review","Complete model reviewed"]].map(([step,label])=><WorkButton type="button" key={step} disabled={dirty||data.input.workflow.setup_steps.includes(step)||step==="path"&&!data.input.workflow.selected||step==="review"&&data.input.workflow.mode==="real"&&!data.baseline_ready} onClick={()=>save("step",{step})}>{data.input.workflow.setup_steps.includes(step)?"✓ ":"Confirm: "}{label}</WorkButton>)}</div><p>{data.input.workflow.setup_complete?"Setup complete for this saved version.":"Complete all five confirmations to finish setup."}</p><WorkButton type="button" disabled={dirty||data.input.workflow.setup_complete||data.input.workflow.setup_steps.length!==5||data.input.workflow.mode==="real"&&!data.baseline_ready} onClick={()=>save("step",{step:"finish"})}>Finish setup</WorkButton></section>
  </fieldset>
  <WorkButton type="submit" disabled={busy||dirty} onClick={onContinue}>Continue to decisions →</WorkButton>
 </>;
}
