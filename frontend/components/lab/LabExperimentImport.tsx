"use client";
import { WorkInput, WorkButton } from "./../WorkspaceUi";

import {useRef,useState} from "react";
import type {Plan,Request} from "./LabWorkspace";
import styles from "./DealershipLab.module.css";

type Preview={preview_id:string;input:{name:string;months:number;rooftops:number;profile:{name:string;country:string;region:string;currency:string};dealership:{kind:string};workflow:{mode:string}};provenance:{file_sha256:string;claimed_data_path:string};warnings:string[]};

export function LabExperimentImport({request,onCreated,onDirty,onBusy,busy}:{request:Request;onCreated:(plan:Plan)=>void;onDirty:(dirty:boolean)=>void;onBusy:(busy:boolean)=>void;busy:boolean}) {
 const [preview,setPreview]=useState<Preview|null>(null),[name,setName]=useState(""),[error,setError]=useState("");
 const pending=useRef(false);
 async function choose(file?:File){
  if(!file||pending.current)return;
  pending.current=true;onBusy(true);setPreview(null);setError("");onDirty(false);
  try{
   if(file.size>1_000_000)throw new Error("Choose a JSON file of 1 MB or less.");
   const p=await request<Preview>("/experiment-import/preview","POST",{content:await file.text()});
   setPreview(p);setName(p.input.name.slice(0,100));onDirty(true);
  }catch(e){setError(e instanceof Error?e.message:"Unable to preview this file.");}
  finally{pending.current=false;onBusy(false);}
 }
 async function save(){
  if(!preview||pending.current)return;
  pending.current=true;onBusy(true);setError("");
  try{
   const plan=await request<Plan>("/experiment-import/save","POST",{preview_id:preview.preview_id,name:name.trim()});
   onDirty(false);setPreview(null);onCreated(plan);
  }catch(e){setError(e instanceof Error?e.message:"Unable to import this plan.");}
  finally{pending.current=false;onBusy(false);}
 }
 return <section className={styles.panel} aria-label="Import experiment"><h3>Bring in a Composite experiment</h3><p>Choose an exported experiment JSON file. Preview its inputs, then save a new private plan and review your starting figures.</p>
  <label>Experiment JSON file<WorkInput type="file" accept=".json,application/json" disabled={busy} onChange={e=>{const file=e.target.files?.[0];e.target.value="";void choose(file);}}/></label>
  {error&&<p role="alert">{error}</p>}
  {preview&&<div><h4>Review imported inputs</h4><p>{preview.input.profile.name} · {preview.input.dealership.kind} · {preview.input.rooftops} rooftops · {preview.input.months} months · {preview.input.profile.currency}</p><p>{preview.input.profile.region}, {preview.input.profile.country}. Imported data path: {preview.provenance.claimed_data_path}.</p>
   <ul>{preview.warnings.map(w=><li key={w}>{w}</li>)}</ul>
   <details><summary>File provenance & normalized inputs</summary><p style={{overflowWrap:"anywhere"}}>SHA-256: {preview.provenance.file_sha256}</p><pre style={{maxHeight:300,overflow:"auto"}}>{JSON.stringify(preview.input,null,2)}</pre></details>
   <label>New plan name<WorkInput value={name} maxLength={100} disabled={busy} onChange={e=>setName(e.target.value)}/></label>
   <div className={styles.actions}><WorkButton type="submit" disabled={busy||!name.trim()} onClick={()=>void save()}>Import & review setup</WorkButton><WorkButton type="submit" disabled={busy} onClick={()=>{setPreview(null);onDirty(false);setError("");}}>Cancel import</WorkButton></div>
  </div>}
 </section>;
}
