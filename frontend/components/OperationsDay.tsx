"use client";
import {useEffect,useState} from "react";
import {getOperationsOverview,type OperationsOverview} from "@/lib/operationsOverview";
import {OverviewActions,OverviewHeader,OverviewMetrics} from "./DepartmentOverview";
import styles from "./DepartmentOverview.module.css";
const priorities = [
 {description:"Contracted or funded deals with unfinished delivery checks.",key:"deliveries_at_risk",label:"Deliveries at risk",icon:"delivery",item:"scheduling"},
 {description:"Vehicles whose title is not recorded as received.",key:"vehicles_missing_titles",label:"Missing titles",icon:"content",item:"inventory"},
 {description:"Vehicles recorded as awaiting inspection.",key:"vehicles_awaiting_inspection",label:"Awaiting inspection",icon:"service",item:"inventory"},
 {description:"Open compliance alerts to review in the alerts workspace.",key:"compliance_violations",label:"Compliance alerts",icon:"compliance",item:"alerts"},
 {description:"Wholesale candidates based on margin. This is not a count of vehicles over 90 days old.",key:"wholesale_candidates_needing_decision",label:"Wholesale decisions",icon:"pricing",item:"inventory"},
] as const;
export function OperationsDay({allowed,onSelectItem,onOpenEntity}:{allowed:Set<string>;onSelectItem:(key:string)=>void;onOpenEntity:(id:string)=>void}) {
 const [data,setData]=useState<OperationsOverview|null>(null),[error,setError]=useState("");
 const [loading,setLoading]=useState(true),[revision,setRevision]=useState(0),[selected,setSelected]=useState<(typeof priorities)[number]>(priorities[0]);
 useEffect(()=>{let active=true;setLoading(true);setError("");getOperationsOverview().then(d=>{if(active)setData(d);}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Operations could not load.");}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[revision]);
 const bucket=data?.action_center[selected.key];
 const records=bucket ? "deals" in bucket ? bucket.deals : "vehicles" in bucket ? bucket.vehicles : [] : [];
 return <section aria-label="Operations overview">
  <OverviewHeader department="Operations" title="Operations overview" description="Spot the exceptions, check your departments, and move the next piece of work forward."><button className="work-button" disabled={loading} onClick={()=>setRevision(v=>v+1)}>Refresh</button></OverviewHeader>
  <OverviewMetrics items={priorities.map(p=>{const b=data?.action_center[p.key];const unavailable=loading||!!error||b?.count==null;return {label:p.label,icon:p.icon,value:unavailable?null:b?.count,detail:loading?"Loading current records…":error?"Unavailable":b?.count==null?"Source unavailable":b.count>0?"Needs attention":"No flagged records",attention:!unavailable&&!!b?.count,selected:selected.key===p.key,action:"Review",onClick:()=>setSelected(p)};})}/>
  {loading?<p role="status" className={styles.muted}>Loading Operations snapshot…</p>:error?<p role="alert">{error} <button className="work-button" onClick={()=>setRevision(v=>v+1)}>Retry</button></p>:data&&<>
   <section className={styles.panel} aria-label="Operations priority records"><h3 className={styles.sectionTitle}>{selected.label}</h3>
    <p>{selected.description}</p>
    {bucket&&"error" in bucket&&bucket.error?<p role="alert">{bucket.error}</p>:<p>{bucket?.count??"—"} flagged records{records.length>0?` · showing ${Math.min(5,records.length)}`:""}</p>}
    <div className={styles.rows}>{records.slice(0,5).map((record,index)=>{const r=record as Record<string,unknown>;const id=String(r.deal_id||r.vehicle_id||"");return <div key={id||index} className={styles.row}><div><strong>{String(r.stock_number||r.deal_id||r.vehicle_id||"Record")}</strong><p>{[r.year,r.make,r.model,r.status].filter(Boolean).join(" ")||"Review this record and its next action."}</p></div><button className="work-button" disabled={!id} onClick={()=>onOpenEntity(id)}>Open record →</button></div>;})}</div>
    {bucket?.count===0&&<p>No records need attention in this category.</p>}
    {allowed.has(selected.item)&&<button className="work-button" onClick={()=>onSelectItem(selected.item)}>Open {selected.item} →</button>}
   </section>
   <div className={styles.columns}><section className={styles.panel}><h3 className={styles.sectionTitle}>Department health</h3>{data.department_health.checks.map(c=><div className={styles.row} key={c.area}><div><strong>{c.area} · {c.status==="healthy"?"On track":"Needs attention"}</strong><p>{c.area === "Funding Delays" ? "Financing deals without an update for at least three days. Based on the last deal update, not lender submission time." : c.area === "Aged Inventory" ? "Wholesale candidates with margins below 8%. Acquisition dates are unavailable for day-based aging." : c.detail}</p></div></div>)}</section>
   <section className={styles.panel}><h3 className={styles.sectionTitle}>Team workload</h3>{data.workload_distribution.areas.map(a=><div className={styles.row} key={a.area}><div><strong>{a.area} · {a.load}</strong><p>{a.headcount} staff · {a.open_task_count} open tasks</p></div></div>)}<p>Workload compares open tasks with assigned staff. It does not measure hours worked or staff utilization.</p></section></div>
  </>}
  <OverviewActions items={[["tasks","Review team tasks","operations"],["scheduling","Coordinate deliveries","delivery"],["inventory","Review vehicles","inventory"],["alerts","Resolve alerts","compliance"]].filter(([key])=>allowed.has(key)).map(([key,label,icon])=>({label,icon,onClick:()=>onSelectItem(key)}))}/>
 </section>;
}
