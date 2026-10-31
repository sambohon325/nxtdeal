"use client";
import { WorkSelect, WorkInput, WorkButton } from "./../WorkspaceUi";
import {RecordTable} from "../RecordTable";
import {useRef,useState} from "react";
import type {Plan,Request} from "./LabWorkspace";
import styles from "./DealershipLab.module.css";
type Outcome={terminal_expected:Record<string,number>;warnings:string[]};
type Preview={seed:number;sales_per_person:number;can_adopt?:boolean;adopted_option?:Plan|null;id:string;source_revision:number;source_hash:string;shared_engine_commit:string;metric:string;target:number;months:number;basis:string;proposal:{changes:{label:string;before:number;after:number}[];input:{profile:{currency:string}}};result:Outcome;stress:Outcome};
export function LabGoals({plan,request,onCreated,onDirty,onBusy}:{plan:Plan;request:Request;onCreated:(p:Plan)=>void;onDirty:(v:boolean)=>void;onBusy:(v:boolean)=>void}){
 const [metric,setMetric]=useState('vehicle_revenue'),[target,setTarget]=useState(600000),[months,setMonths]=useState(12),[seed,setSeed]=useState(42),[productivity,setProductivity]=useState(10),[name,setName]=useState(`${plan.name} · goal option`.slice(0,100));
 const [draftChanged,setDraftChanged]=useState(false);
 const [pendingPreview,setPendingPreview]=useState<string|null>(null);
 const [history,setHistory]=useState<{id:string;created_at:string;metric:string;target:number;source_revision:number}[]|null>(null);
 const [preview,setPreview]=useState<Preview|null>(null),[busy,setBusy]=useState(false),[error,setError]=useState('');const pending=useRef(false);
 function edit(change:()=>void){change();setDraftChanged(true);setPreview(null);setError('');onDirty(true);}
 async function perform(work:()=>Promise<void>){if(pending.current)return;pending.current=true;setBusy(true);onBusy(true);setError('');try{await work();}catch(e){setError(e instanceof Error?e.message:'Unable to complete goal planning.');}finally{pending.current=false;setBusy(false);onBusy(false);}}
 function openSaved(id:string){perform(async()=>{const saved=await request<Preview>(`/workspaces/${plan.id}/goals/${id}`);setPreview(saved);setDraftChanged(false);setPendingPreview(null);setMetric(saved.metric);setTarget(saved.target);setMonths(saved.months);setSeed(saved.seed);setProductivity(saved.sales_per_person);setName(saved.adopted_option?.name||`${plan.name} · goal option`.slice(0,100));onDirty(false);});}
 const engineMetric=preview?.metric==='vehicle_revenue'?'revenue':'contribution';
 const amount=(n:number)=>n.toLocaleString(undefined,{maximumFractionDigits:2});
 const achieved=preview?preview.result.terminal_expected[engineMetric]/preview.months:0;
 return <section className={styles.panel}><h3>What would this goal require?</h3><p>Choose an average monthly revenue or operating contribution target. Review the demand, stock and staffing assumptions needed to pursue it, then create a separate option. Start with a Simulation or Hybrid model and a complete sales funnel in Customers & inventory.</p>
 {error&&<p role="alert" className={styles.error}>{error}</p>}
 <form onSubmit={e=>{e.preventDefault();perform(async()=>{setPreview(null);const result=await request<Preview>(`/workspaces/${plan.id}/goals/preview`,'POST',{revision:plan.revision,metric,target,months,seed,sales_per_person:productivity});setPreview(result);setDraftChanged(false);setPendingPreview(null);onDirty(true);});}}>
 <fieldset disabled={busy} className={styles.fields}><label>Goal measure<WorkSelect value={metric} onChange={e=>edit(()=>setMetric(e.target.value))}><option value="vehicle_revenue">Vehicle sales revenue</option><option value="contribution">Operating contribution</option></WorkSelect></label>
 <label>Average monthly target<WorkInput type="number" required min={1} max={100000000} step="any" value={target} onChange={e=>edit(()=>setTarget(Number(e.target.value)))}/></label>
 <label>Months<WorkInput type="number" required min={1} max={36} value={months} onChange={e=>edit(()=>setMonths(Number(e.target.value)))}/></label>
 <label>Sales per salesperson / month<WorkInput type="number" required min={1} max={100} step="any" value={productivity} onChange={e=>edit(()=>setProductivity(Number(e.target.value)))}/></label>
 <label>Repeatable seed<WorkInput type="number" required min={0} max={2147483647} value={seed} onChange={e=>edit(()=>setSeed(Number(e.target.value)))}/></label></fieldset>
 <WorkButton type="submit" disabled={busy}>{busy?'Working…':'Preview goal requirements'}</WorkButton></form>
 <section><h3>Saved goal previews</h3><WorkButton type="submit" disabled={busy} onClick={()=>perform(async()=>{const saved=await request<{previews:NonNullable<typeof history>}>(`/workspaces/${plan.id}/goals`);setHistory(saved.previews);})}>Load saved previews</WorkButton>{history?.length===0&&<p>No saved goal previews for this plan.</p>}{history?.map(item=><p key={item.id}><WorkButton type="submit" disabled={busy} onClick={()=>{if(draftChanged){setPendingPreview(item.id);return;}openSaved(item.id);}}>Open {new Date(item.created_at).toLocaleString()} · {item.metric==='vehicle_revenue'?'Revenue':'Contribution'} {amount(item.target)} · revision {item.source_revision}</WorkButton></p>)}</section>
 {pendingPreview&&<div role="alert" className={styles.panel}><p>Opening saved goal inputs will replace your current goal form.</p><div className={styles.actions}><WorkButton type="submit" disabled={busy} onClick={()=>setPendingPreview(null)}>Keep editing goal</WorkButton><WorkButton type="submit" disabled={busy} onClick={()=>openSaved(pendingPreview)}>Open saved goal inputs</WorkButton></div></div>}
 {preview&&<><h3>Review the proposed requirements</h3><p>{preview.basis}</p><p>Source revision {preview.source_revision} · {preview.months} months · {preview.proposal.input.profile.currency} · 100 trials</p>
 <div className={styles.tableWrap}><RecordTable><thead><tr><th>Average monthly outcome</th><th>Amount</th></tr></thead><tbody><tr><th>Your target</th><td>{amount(preview.target)}</td></tr><tr><th>Expected outcome with proposed requirements</th><td>{amount(achieved)}</td></tr><tr><th>Expected outcome with 20% lower demand index</th><td>{amount(preview.stress.terminal_expected[engineMetric]/preview.months)}</td></tr></tbody></RecordTable></div>
 <p role="status">{achieved>=preview.target?'The expected outcome reaches the target under these assumptions. Individual outcomes can fall short.':'The expected outcome still falls short of the target after the bounded search. Review conversion, margins and the target before adopting.'}</p>
 <div className={styles.tableWrap}><RecordTable><thead><tr><th>Requirement</th><th>Current</th><th>Proposed</th></tr></thead><tbody>{preview.proposal.changes.map(c=><tr key={c.label}><th>{c.label}</th><td>{amount(c.before)}</td><td>{amount(c.after)}</td></tr>)}</tbody></RecordTable></div>
 {[...new Set([...preview.result.warnings,...preview.stress.warnings])].map(w=><p key={w}>{w}</p>)}
 {preview.can_adopt===false&&<p>This is a historical preview. The source or engine has changed, or the source is archived. Calculate a fresh preview before creating another option.</p>}
 {preview.adopted_option&&<p>Already adopted as {preview.adopted_option.name}. {preview.adopted_option.archived?'Restore this option in Saved decisions to resume it.':<WorkButton type="submit" disabled={busy} onClick={()=>{onDirty(false);onCreated(preview.adopted_option!);}}>Open existing goal option</WorkButton>}</p>}
 <label>Separate option name<WorkInput maxLength={100} value={name} disabled={busy} onChange={e=>{setName(e.target.value);setDraftChanged(true);onDirty(true);}}/></label>
 <WorkButton type="submit" disabled={busy||!name.trim()||preview.source_revision!==plan.revision||preview.can_adopt===false||!!preview.adopted_option} onClick={()=>perform(async()=>{const option=await request<Plan>(`/workspaces/${plan.id}/goals/adopt`,'POST',{revision:preview.source_revision,preview_id:preview.id,name:name.trim()});onDirty(false);onCreated(option);})}>Create separate goal option</WorkButton>
 <details><summary>Calculation provenance and full preview</summary><p>Chrono {preview.shared_engine_commit} · source {preview.source_hash}</p><pre>{JSON.stringify(preview,null,2)}</pre></details></>}
 </section>;
}
