"use client";
import { WorkButton } from "./../WorkspaceUi";
import {useEffect,useState} from "react";
import type {Plan,Request} from "./LabWorkspace";
import styles from "./DealershipLab.module.css";

type Row={name:string;available:boolean;weight:number;reason?:string;establishments?:number;employees_per_store?:number;annual_pay_per_employee?:number;monthly_pay_per_store?:number};
type Reference={workspace_id:string;revision:number;name:string;source_hash:string;reference_hash:string;shared_engine_commit:string;basis:string;provenance:{commit:string};comparison:{period:string;source:string;checked:string;industry:string|null;notes:string[];rows:Row[];blend:null|{people:number;inventory:number;annual_pay_per_employee:number;monthly_payroll_proxy:number;monthly_payroll_per_vehicle:number|null}}};
const money=(value:number|undefined|null)=>value==null?"Unavailable":new Intl.NumberFormat('en-US',{style:'currency',currency:'USD',maximumFractionDigits:2}).format(value);

export function LabReferences({plan,request}:{plan:Plan;request:Request}){
 const [data,setData]=useState<Reference|null>(null),[error,setError]=useState(''),[retry,setRetry]=useState(0);
 useEffect(()=>{let active=true;request<Reference>(`/workspaces/${plan.id}/references?revision=${plan.revision}`).then(value=>{if(active){setData(value);setError('');}}).catch(e=>{if(active){setData(null);setError(e.message);}});return()=>{active=false;};},[plan.id,plan.revision,request,retry]);
 if(error)return <p role="alert">{error} <WorkButton type="submit" onClick={()=>setRetry(retry+1)}>Retry references</WorkButton></p>;
 if(!data||data.workspace_id!==plan.id||data.revision!==plan.revision)return <p>Loading historical references…</p>;
 const c=data.comparison;
 function download(){const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`nxtdeal-${plan.id}-references-r${data!.revision}.json`;a.click();URL.revokeObjectURL(url);}
 return <div style={{overflowWrap:"anywhere"}}>
  <section className={styles.panel}><h3>Public market references</h3><p>{data.basis}</p><p>Reference period: {c.period} · Checked: {c.checked} · Historical USD</p><p>Source: {c.source}</p><p>Saved model: {data.name} · revision {data.revision} · industry {c.industry??'unavailable'}</p><WorkButton type="submit" onClick={download}>Download reference snapshot</WorkButton></section>
  {c.rows.map(row=><section className={styles.panel} key={row.name}><h3>{row.name}</h3>{row.available?<dl><dt>Establishments</dt><dd>{row.establishments}</dd><dt>Employees per establishment</dt><dd>{row.employees_per_store}</dd><dt>Annual payroll per employee proxy</dt><dd>{money(row.annual_pay_per_employee)}</dd><dt>Monthly payroll per establishment</dt><dd>{money(row.monthly_pay_per_store)}</dd><dt>Model blend weight</dt><dd>{row.weight}</dd></dl>:<p>{row.reason}</p>}</section>)}
  {c.blend?<section className={styles.panel}><h3>Estimate using your baseline assumptions</h3><p>{c.blend.people} modeled staff · {c.blend.inventory} modeled vehicles across saved rooftops.</p><dl><dt>Annual payroll per employee proxy</dt><dd>{money(c.blend.annual_pay_per_employee)}</dd><dt>Monthly payroll proxy</dt><dd>{money(c.blend.monthly_payroll_proxy)}</dd><dt>Monthly payroll per modeled vehicle</dt><dd>{money(c.blend.monthly_payroll_per_vehicle)}</dd></dl><p>These estimates do not change your model. Review your own payroll evidence in the operating plan.</p></section>:<p>No comparable series is available for this saved model.</p>}
  <section className={styles.panel}><h3>Read before using these estimates</h3><ul>{c.notes.map(note=><li key={note}>{note}</li>)}</ul><details><summary>Reference provenance</summary><p>Composite source commit: {data.provenance.commit}</p><p style={{overflowWrap:'anywhere'}}>Reference hash: {data.reference_hash}</p><p style={{overflowWrap:'anywhere'}}>Saved input hash: {data.source_hash}</p><p>Shared engine: {data.shared_engine_commit}</p></details></section>
 </div>;
}
