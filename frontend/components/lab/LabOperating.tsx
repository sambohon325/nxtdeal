"use client";
import { WorkInput, WorkSelect, WorkButton, WorkTextarea } from "./../WorkspaceUi";
import {RecordTable} from "../RecordTable";

import {useEffect, useRef, useState} from "react";
import type {Plan, Request} from "./LabWorkspace";
import {departments, roleDepartments} from "./departments";
import styles from "./DealershipLab.module.css";

type Row = {name:string;id?:string;department?:string;[key:string]:string|number|undefined};
type Operating = {size:string;open_days:number;open_hours:number;roles:Row[];expenses:Row[];tasks:Row[];facility?:Row};
type Model = {scenario:{operating:Operating};operating_enabled:boolean;staffing_capacity_enabled:boolean;profile:{currency:string}};
type Costs = {payroll:number;additional_payroll:number;overhead:number;cash_savings:number;operating_cost:number;paid_hours:number;overload_hours:number};
type Preview = {saved:Costs;draft:Costs;basis:string;currency:string;rooftops:number;operating_enabled:boolean};
type Loaded = {workspace:Plan;input:Model};
type Props = {plan:Plan;request:Request;onSaved:(plan:Plan)=>void;onDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void};
type Field = [string,string,number,number,number?];
const roleFields:Field[] = [
 ["people","People per shift",0,500,1],["shifts","Distinct crews",1,3,1],["wage","Hourly pay",0,1000],["salary","Monthly salary per person (0 uses hourly)",0,100000],
 ["shift_hours","Hours per shift",0,24],["unpaid_break","Unpaid break hours",0,8],["days_week","Days per week",0,7],
 ["burden","Employer costs %",0,100],["commission","Commission per vehicle sold",0,10000],["ot_threshold","Weekly overtime threshold",0,168],
 ["ot_multiplier","Overtime multiplier",1,3],["unavailable","Unavailable time %",0,100],["embedded","Payroll already included in gross %",0,100],["cash_realization","Saved labor realized as cash %",0,100],
];
const freshRole = (id:string,name:string,department:string):Row => ({id,name,department,scope:"rooftop",people:0,shifts:1,wage:25,salary:0,commission:0,shift_hours:8.5,unpaid_break:.5,days_week:5,burden:25,ot_threshold:40,ot_multiplier:1.5,unavailable:15,embedded:0,cash_realization:0});

function nextId(rows:Row[],prefix:string){let index=1;while(rows.some(row=>row.id===`${prefix}_${index}`))index++;return `${prefix}_${index}`;}

export function LabOperating({plan,request,onSaved,onDirty,onBusy}:Props){
 const [data,setData]=useState<Loaded|null>(null),[draft,setDraft]=useState<Operating|null>(null),[enabled,setEnabled]=useState(true),[capacity,setCapacity]=useState(false);
 const [dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[message,setMessage]=useState(""),[retry,setRetry]=useState(0),[department,setDepartment]=useState("all");
 const [preview,setPreview]=useState<Preview|null>(null);
 const pending=useRef(false);
 const base=`/workspaces/${plan.id}/setup`;
 useEffect(()=>{let active=true;request<Loaded>(base).then(value=>{if(!active)return;setData(value);setDraft(structuredClone(value.input.scenario.operating));setEnabled(value.input.operating_enabled);setCapacity(value.input.staffing_capacity_enabled);setError("");}).catch(e=>{if(active)setError(e.message);});return()=>{active=false;};},[base,request,retry]);
 useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
 useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
 const roleDepartment=(r:Row)=>String(r.department||roleDepartments[String(r.id)]||"admin");
 function change(next:Operating){setDraft(next);setDirty(true);setMessage("");setPreview(null);}
 function rowChange(group:"roles"|"tasks"|"expenses",index:number,key:string,value:string|number){if(draft)change({...draft,[group]:draft[group].map((row,i)=>i===index?{...row,[key]:value}:row)});}
 function numeric(row:Row|Operating,fields:Field[],update:(key:string,value:number)=>void){return fields.map(([key,label,min,max,step])=><label key={key}>{label}<WorkInput required type="number" min={min} max={max} step={step??"any"} value={Number.isFinite(row[key as keyof typeof row])?row[key as keyof typeof row] as number:""} onChange={e=>update(key,e.target.value===""?NaN:Number(e.target.value))}/></label>);}
 function deptSelect(row:Row,update:(value:string)=>void,fallback:string){const value=String(row.department||fallback);return <label>Department<WorkSelect value={value} onChange={e=>update(e.target.value)}>{departments.map(([id,label])=><option key={id} value={id}>{label}</option>)}{!departments.some(([id])=>id===value)&&<option>{value}</option>}</WorkSelect></label>;}
 function scope(row:Row,update:(value:string)=>void){return <label>Cost / staffing scope<WorkSelect value={row.scope} onChange={e=>update(e.target.value)}><option value="rooftop">Per rooftop</option><option value="group">Whole group</option></WorkSelect></label>;}
 function addDepartment(id:string){
  if(!draft)return;const entry=departments.find(d=>d[0]===id)!;const roles=[...draft.roles],tasks=[...draft.tasks];let role=roles.find(r=>roleDepartment(r)===id);
  if(!role){role=freshRole(nextId(draft.roles,"role"),`${entry[1]} coordinator`,id);roles.push(role);}
  entry[3].forEach((name,i)=>{if(!tasks.some(t=>t.id===`dept_${id}_${i}`||t.name===name))tasks.push({id:`dept_${id}_${i}`,name,role:role!.id,driver:"fixed",volume:0,minutes:15});});
  if(roles.length>80||tasks.length>200){setError("Maximum 80 roles and 200 jobs. Edit existing roles and jobs instead.");return;}
  change({...draft,roles,tasks});setDepartment(id);
 }
 async function showPreview(){
  if(!data||!draft||pending.current)return;pending.current=true;setBusy(true);setError("");setPreview(null);
  try{setPreview(await request<Preview>(`/workspaces/${plan.id}/operating-preview`,"POST",{revision:data.workspace.revision,values:{operating:draft,operating_enabled:enabled,staffing_capacity_enabled:capacity}}));}
  catch(e){setError(e instanceof Error?e.message:"Unable to preview. Real-data changes must be saved and their source reviewed first.");}finally{pending.current=false;setBusy(false);}
 }
 async function save(){
  if(!data||!draft||pending.current)return;pending.current=true;setBusy(true);setError("");setMessage("");
  try{const saved=await request<Plan>(base,"POST",{revision:data.workspace.revision,action:"operating",values:{operating:draft,operating_enabled:enabled,staffing_capacity_enabled:capacity}});const input=saved.model_definition as Model;setData({workspace:saved,input});setDraft(structuredClone(input.scenario.operating));setDirty(false);setPreview(null);onSaved(saved);setMessage("Operating plan saved. Review these inputs before running a comparison.");}
  catch(e){setError(e instanceof Error?e.message:"Unable to save operating plan.");}finally{pending.current=false;setBusy(false);}
 }
 if(!data||!draft)return <section className={styles.panel}>{error?<p role="alert">{error} <WorkButton type="submit" onClick={()=>setRetry(v=>v+1)}>Retry</WorkButton></p>:<p>Loading operating plan…</p>}</section>;
 return <form onSubmit={e=>{e.preventDefault();void save();}}>
  <section className={styles.panel}><h3>{plan.name} · operating plan</h3><p>{plan.parent_id?"You are editing a separate option. Its source dealership stays unchanged.":"You are editing the current dealership. These changes update its baseline and require a fresh real-data source review."}</p><p>Amounts in {data.input.profile.currency}. New department roles start with zero people and jobs with zero volume; 15 minutes is an editable placeholder.</p>{error&&<p role="alert" className={styles.error}>{error}</p>}{message&&<p role="status">{message}</p>}</section>
  <fieldset disabled={busy||plan.archived} className={styles.notebookFields}>
   <section className={styles.panel}><h3>How this plan affects results</h3><label><WorkInput type="checkbox" checked={enabled} onChange={e=>{setEnabled(e.target.checked);setDirty(true);setPreview(null);}}/>Include operating costs and workload</label><label><WorkInput type="checkbox" checked={capacity} onChange={e=>{setCapacity(e.target.checked);setDirty(true);setPreview(null);}}/>Use staffing capacity to constrain throughput</label><p>Staffing capacity scales the model’s existing sales, BDC and service role groups relative to the source baseline. Custom roles organize costs and work; they do not automatically increase throughput. Payroll already included in gross avoids double counting. Saved labor becomes cash only at your explicit realization percentage.</p><div className={styles.fields}>{numeric(draft,[["open_days","Open days per month",1,31],["open_hours","Open hours per day",1,24]],(key,value)=>change({...draft,[key]:value}))}</div></section>
   <section className={styles.panel}><h3>Departments</h3><p>Organize costs and responsibilities here. These departments do not add separate revenue engines for collision, rental or parts counter sales.</p><div className={styles.grid}>{departments.map(([id,label,description])=><details key={id}><summary>{label} · {draft.roles.filter(r=>roleDepartment(r)===id).length} roles</summary><p>{description}</p><WorkButton type="button" onClick={()=>setDepartment(id)}>View team</WorkButton><WorkButton type="button" onClick={()=>addDepartment(id)}>Add missing job checklist</WorkButton></details>)}</div></section>
   <section className={styles.panel}><h3>Team & shifts</h3><label>Show department<WorkSelect value={department} onChange={e=>setDepartment(e.target.value)}><option value="all">All departments</option>{departments.map(([id,label])=><option key={id} value={id}>{label}</option>)}</WorkSelect></label><p>People are counted per shift. Salary replaces hourly pay. Commission is per vehicle sold for the role, not per person.</p>
    {draft.roles.map((r,i)=>department!=="all"&&roleDepartment(r)!==department?null:<details key={r.id}><summary>{r.name} · {r.people} people × {r.shifts} crews</summary><div className={styles.fields}><label>Role name<WorkInput required maxLength={100} value={r.name} onChange={e=>rowChange("roles",i,"name",e.target.value)}/></label>{deptSelect(r,value=>rowChange("roles",i,"department",value),roleDepartment(r))}{scope(r,value=>rowChange("roles",i,"scope",value))}{numeric(r,roleFields,(key,value)=>rowChange("roles",i,key,value))}</div><WorkButton type="button" disabled={draft.tasks.some(t=>t.role===r.id)} onClick={()=>change({...draft,roles:draft.roles.filter((_,n)=>n!==i)})}>Remove role</WorkButton>{draft.tasks.some(t=>t.role===r.id)&&<p>Reassign or remove this role’s jobs before removing the role. Setting people to zero keeps its jobs visible.</p>}</details>)}
    <WorkButton type="button" disabled={draft.roles.length>=80} onClick={()=>change({...draft,roles:[...draft.roles,freshRole(nextId(draft.roles,"role"),"New role",department==="all"?"admin":department)]})}>Add role</WorkButton>
   </section>
   <section className={styles.panel}><h3>Building & monthly bills</h3><p>Each bill uses quantity × rate. Use quantity 1 for a flat monthly bill, or enter metered units and their tariff. Facility dimensions are descriptive; they do not create throughput.</p>
    <details><summary>Premises & facilities · descriptive assumptions</summary><div className={styles.fields}><label>Premises<WorkSelect value={draft.facility?.tenure||"leased"} onChange={e=>change({...draft,facility:{name:"",notes:"",building_sqft:0,lot_sqft:0,service_bays:0,detail_bays:0,parking_spaces:0,...draft.facility,tenure:e.target.value}})}><option value="leased">Leased</option><option value="owned">Owned</option><option value="mixed">Mixed</option></WorkSelect></label>{numeric(draft.facility||{name:"",building_sqft:0,lot_sqft:0,service_bays:0,detail_bays:0,parking_spaces:0},[["building_sqft","Building square feet",0,10000000],["lot_sqft","Lot square feet",0,100000000],["service_bays","Service bays",0,10000,1],["detail_bays","Detail bays",0,10000,1],["parking_spaces","Parking spaces",0,100000,1]],(key,value)=>change({...draft,facility:{name:"",tenure:"leased",notes:"",building_sqft:0,lot_sqft:0,service_bays:0,detail_bays:0,parking_spaces:0,...draft.facility,[key]:value}}))}<label>Facility notes<WorkTextarea maxLength={1000} value={draft.facility?.notes||""} onChange={e=>change({...draft,facility:{name:"",tenure:"leased",building_sqft:0,lot_sqft:0,service_bays:0,detail_bays:0,parking_spaces:0,...draft.facility,notes:e.target.value}})}/></label></div></details>
    {draft.expenses.map((r,i)=><details key={i}><summary>{r.name}</summary><div className={styles.fields}><label>Bill name<WorkInput required maxLength={100} value={r.name} onChange={e=>rowChange("expenses",i,"name",e.target.value)}/></label>{deptSelect(r,value=>rowChange("expenses",i,"department",value),"facilities")}{scope(r,value=>rowChange("expenses",i,"scope",value))}{numeric(r,[["quantity","Monthly quantity",0,10000000],["rate","Cost per unit",0,1000000]],(key,value)=>rowChange("expenses",i,key,value))}</div><WorkButton type="button" onClick={()=>change({...draft,expenses:draft.expenses.filter((_,n)=>n!==i)})}>Remove bill</WorkButton></details>)}
    <WorkButton type="button" disabled={draft.expenses.length>=120} onClick={()=>change({...draft,expenses:[...draft.expenses,{name:"New bill",quantity:1,rate:0,scope:"rooftop"}]})}>Add bill</WorkButton>
   </section>
   <section className={styles.panel}><h3>Work & phone activity</h3><p>Fixed volume is jobs per month. Other drivers multiply their monthly activity by the frequency entered. Avoid counting calls twice in lead follow-up and phone jobs.</p>
    {draft.tasks.map((r,i)=><details key={r.id}><summary>{r.name} · {r.minutes} minutes per job</summary><div className={styles.fields}><label>Job name<WorkInput required maxLength={100} value={r.name} onChange={e=>rowChange("tasks",i,"name",e.target.value)}/></label><label>Assigned role<WorkSelect value={r.role} onChange={e=>rowChange("tasks",i,"role",e.target.value)}>{draft.roles.map(role=><option key={role.id} value={role.id}>{role.name}</option>)}</WorkSelect></label><label>Workload driver<WorkSelect value={r.driver} onChange={e=>rowChange("tasks",i,"driver",e.target.value)}>{[["fixed","Fixed monthly jobs"],["leads","Leads"],["sales","Sales"],["arrivals","Vehicle arrivals"],["inventory","Inventory"],["service_ros","Service repair orders"]].map(([id,label])=><option key={id} value={id}>{label}</option>)}</WorkSelect></label>{numeric(r,[["volume","Monthly volume / frequency per activity",0,100000],["minutes","Hands-on minutes per job",0,10000]],(key,value)=>rowChange("tasks",i,key,value))}</div><WorkButton type="button" onClick={()=>change({...draft,tasks:draft.tasks.filter((_,n)=>n!==i)})}>Remove job</WorkButton><p>Saving a removed job also removes its software time-saving assumptions from this plan.</p></details>)}
    <WorkButton type="button" disabled={!draft.roles.length||draft.tasks.length>=200} onClick={()=>change({...draft,tasks:[...draft.tasks,{id:nextId(draft.tasks,"job"),name:"New job / phone activity",role:draft.roles[0].id,driver:"fixed",volume:0,minutes:15}]})}>Add job / phone activity</WorkButton><p>Record billed phone minutes separately as a monthly bill. Zero people or zero volume does not erase assigned jobs or saved history.</p>
   </section>
   <section className={styles.panel}><h3>Review operating costs</h3><p>Preview uses the shared calculation engine. For changed real-data baselines, save and renew the source review in Setup & data sources first.</p><WorkButton type="button" onClick={e=>{if(e.currentTarget.form?.reportValidity())void showPreview();}}>Preview costs & workload</WorkButton>
    {preview&&<><p>{preview.basis}</p><p>{preview.rooftops} rooftop(s) · {preview.currency}{!preview.operating_enabled?" · Operating costs are disabled in comparisons":""}</p><div className={styles.tableWrap}><RecordTable><thead><tr><th>Monthly measure · per rooftop</th><th>Saved plan</th><th>Edited plan</th></tr></thead><tbody>{([["payroll","Total payroll"],["additional_payroll","Payroll not already in gross"],["overhead","Monthly bills"],["cash_savings","Realized labor savings"],["operating_cost","Operating costs added to results"],["paid_hours","Paid hours"],["overload_hours","Work beyond available hours"]] as [keyof Costs,string][]).map(([key,label])=><tr key={key}><th>{label}</th><td>{preview.saved[key].toLocaleString(undefined,{maximumFractionDigits:2})}</td><td>{preview.draft[key].toLocaleString(undefined,{maximumFractionDigits:2})}</td></tr>)}</tbody></RecordTable></div></>}
   </section>
   <WorkButton type="submit" disabled={!dirty||busy}>Save operating plan</WorkButton>
  </fieldset>
 </form>;
}
