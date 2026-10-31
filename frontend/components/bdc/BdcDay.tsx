"use client";
import { WorkButton } from "./../WorkspaceUi";
import {useEffect,useState} from "react";
import {crmRequest} from "@/lib/salesCrm";
import {OverviewActions,OverviewMetrics} from "../DepartmentOverview";
import {RecordCollection} from "../RecordCollection";
import styles from "../DepartmentOverview.module.css";
type ResponseWork={id:string;person_name:string;department:string;closed:boolean;overdue:boolean;stage:string;next_step:string};
export function BdcDay({available,onSelect}:{available:Set<string>;onSelect:(key:string)=>void}) {
 const [work,setWork]=useState<ResponseWork[]|null>(null),[error,setError]=useState(""),[revision,setRevision]=useState(0);
 useEffect(()=>{let current=true;setError("");setWork(null);crmRequest<{cases:ResponseWork[]}>("/marketing/workflow").then(data=>{if(current)setWork(data.cases)}).catch(e=>{if(current)setError(e.message)});return()=>{current=false}},[revision]);
 const open=(work||[]).filter(w=>!w.closed),needs=open.filter(w=>w.overdue||w.stage==="response_due"||w.stage==="recover_appointment");
 const count=(predicate:(w:ResponseWork)=>boolean)=>work===null?null:open.filter(predicate).length;
 return <div>
  <OverviewMetrics label="BDC snapshot" items={[
   {label:"Open campaign responses",icon:"people",value:count(()=>true),detail:"Assigned response work",action:"Review responses",onClick:()=>onSelect("campaign_responses")},
   {label:"Overdue actions",icon:"calendar",value:count(w=>w.overdue),detail:"Past the recorded deadline",attention:needs.some(w=>w.overdue),action:"Review responses",onClick:()=>onSelect("campaign_responses")},
   {label:"Appointments booked",icon:"calendar",value:count(w=>w.stage==="appointment_booked"),detail:"Open responses with a linked booking",action:"Review appointments",onClick:()=>onSelect("campaign_responses")},
   {label:"Visits to recover",icon:"service",value:count(w=>w.stage==="recover_appointment"),detail:"Cancelled or missed appointments",action:"Review recovery",onClick:()=>onSelect("campaign_responses")},
  ]}/>
  <section className={styles.panel}><h3>Work needing attention</h3>{error?<p role="alert">{error} <WorkButton type="submit" onClick={()=>setRevision(v=>v+1)}>Try again</WorkButton></p>:work===null?<p role="status">Loading BDC work…</p>:!needs.length?<p>No campaign responses currently need action. Review the inquiry queue and conversations for other incoming work.</p>:<div className={styles.rows}><RecordCollection label="Responses">{needs.map(w=><div className={styles.row} key={w.id}><div><strong>{w.person_name}</strong><p>{w.department} · {w.stage.replaceAll("_"," ")}{w.overdue?" · Overdue":""}</p><p>{w.next_step}</p></div><WorkButton type="submit" onClick={()=>onSelect("campaign_responses")}>Open responses →</WorkButton></div>)}</RecordCollection></div>}</section>
  <OverviewActions items={[["inquiries","Review incoming inquiries"],["qualification","Qualify inquiries"],["conversations","Review conversations"],["service_appointments","Service appointments"],["appointments","Sales appointments"],["handoff","Complete sales handoffs"],["tasks","Review follow-up tasks"]].filter(([key])=>available.has(key)).map(([key,label])=>({label,icon:"people",onClick:()=>onSelect(key)}))}/>
 </div>;
}
