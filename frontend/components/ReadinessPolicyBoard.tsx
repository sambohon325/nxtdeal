"use client";
import {useEffect,useState} from "react";
import {crmRequest} from "@/lib/salesCrm";
import {getSession} from "@/lib/auth";
import {WorkButton,WorkInput,WorkSection,WorkTextarea} from "./WorkspaceUi";
import {RecordTable} from "./RecordTable";
type Policy={department:string;threshold:number;confidence_pct:number;basis:string;ready:boolean;enabled:boolean;active:boolean;revision:number;history:{at:string;actor:string;action:string;evidence:string;confidence_pct:number;threshold:number}[]};
export function ReadinessPolicyBoard({onDraftOpenChange,onSavingChange}:{onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void}){
 const [rows,setRows]=useState<Policy[]>([]),[selected,setSelected]=useState(""),[threshold,setThreshold]=useState("90"),[evidence,setEvidence]=useState(""),[busy,setBusy]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const current=rows.find(r=>r.department===selected);const dirty=!!evidence||!!current&&threshold!==String(current.threshold);const canManage=["ADMIN","OPERATIONS"].includes(getSession()?.role||"");
 useEffect(()=>{onDraftOpenChange?.(dirty);return()=>onDraftOpenChange?.(false)},[dirty,onDraftOpenChange]);
 useEffect(()=>{onSavingChange?.(saving);return()=>onSavingChange?.(false)},[saving,onSavingChange]);
 async function load(){setBusy(true);setError("");try{setRows((await crmRequest<{departments:Policy[]}>("/readiness/policies")).departments)}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 useEffect(()=>{void load()},[]);
 async function act(action:string){if(!current)return;setBusy(true);setSaving(true);setError("");setNotice("");try{const result=await crmRequest<Policy>(`/readiness/policies/${current.department}`,{method:"POST",body:JSON.stringify({revision:current.revision,action,threshold:Number(threshold),evidence})});setRows(rows.map(r=>r.department===result.department?result:r));setThreshold(String(result.threshold));setEvidence("");setNotice("Readiness decision saved with its evidence.");}catch(e){setError((e as Error).message)}finally{setBusy(false);setSaving(false)}}
 return <WorkSection title="Forecast readiness" description="Confidence is an estimate based on recorded coverage, not a guarantee. Activation records approval to use the forecast; it does not connect providers or launch campaigns. A drop below the threshold suspends active status automatically.">
 {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}<WorkButton disabled={busy||dirty} onClick={()=>void load()}>Refresh measured readiness</WorkButton>
 <RecordTable label="Department readiness"><thead><tr><th>Department</th><th>Confidence</th><th>Threshold</th><th>Data basis</th><th>Status</th><th>Action</th></tr></thead><tbody>{rows.map(r=><tr key={r.department}><td>{r.department}</td><td>{r.confidence_pct}%</td><td>{r.threshold}%</td><td>{r.basis.replaceAll("_"," ")}</td><td>{r.active?"Active":r.enabled?"Suspended — confidence below threshold":"Not activated"}</td><td><WorkButton disabled={busy||dirty} onClick={()=>{setSelected(r.department);setThreshold(String(r.threshold));setNotice("")}}>Review {r.department}</WorkButton></td></tr>)}</tbody></RecordTable>
 {current&&<WorkSection title={`${current.department} readiness decision`}><form className="workflow-start-form" onSubmit={e=>{e.preventDefault();void act('set_threshold')}}><fieldset disabled={busy||!canManage}>
 <label>Required confidence (%)<WorkInput type="number" min={50} max={100} step="0.1" required value={threshold} onChange={e=>setThreshold(e.target.value)}/></label><p>Changing the threshold pauses activation and requires a fresh review.</p>
 <label>Decision evidence<WorkTextarea required minLength={10} value={evidence} onChange={e=>setEvidence(e.target.value)}/></label>
 <div className="work-actions"><WorkButton type="submit" disabled={evidence.trim().length<10}>Save threshold</WorkButton><WorkButton disabled={!current.ready||current.basis==='industry_estimate'||threshold!==String(current.threshold)||evidence.trim().length<10||current.active} onClick={()=>void act('activate')}>Activate forecast</WorkButton><WorkButton disabled={!current.enabled||evidence.trim().length<10} onClick={()=>void act('pause')}>Pause forecast</WorkButton></div>
 </fieldset></form><RecordTable label="Readiness decision history"><thead><tr><th>Time</th><th>Actor</th><th>Decision</th><th>Evidence</th></tr></thead><tbody>{current.history.map((h,i)=><tr key={i}><td>{h.at}</td><td>{h.actor}</td><td>{h.action.replaceAll('_',' ')} · {h.confidence_pct}% / {h.threshold}%</td><td>{h.evidence}</td></tr>)}</tbody></RecordTable></WorkSection>}
 </WorkSection>;
}
