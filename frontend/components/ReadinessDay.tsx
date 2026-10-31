"use client";
import {useEffect,useState} from "react";
import {getReadinessOverview,type ReadinessOverview} from "@/lib/readinessOverview";
import {OverviewHeader,OverviewMetrics} from "./DepartmentOverview";
import {ReadinessOverviewBoard} from "./ReadinessOverviewBoard";
import styles from "./DepartmentOverview.module.css";
export function ReadinessDay({theme}:{theme:"dark"|"light"}) {
 const [data,setData]=useState<ReadinessOverview|null>(null),[error,setError]=useState("");
 const [loading,setLoading]=useState(true),[revision,setRevision]=useState(0),[details,setDetails]=useState(false);
 useEffect(()=>{let active=true;setLoading(true);setError("");getReadinessOverview(false).then(d=>{if(active)setData(d);}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Readiness could not load.");}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[revision]);
 if(details)return <section><button className="work-button" onClick={()=>setDetails(false)}>← Back to Readiness overview</button><ReadinessOverviewBoard theme={theme} hideAssistant/></section>;
 return <section aria-label="Readiness overview"><OverviewHeader department="Readiness" title="Readiness overview" description="Review department confidence, current risks and the next areas to investigate."><button className="work-button" disabled={loading} onClick={()=>setRevision(v=>v+1)}>Refresh</button></OverviewHeader>
 <OverviewMetrics items={[
  {label:"Average confidence",icon:"health",value:loading||error||data?.heatmap.avg_confidence_pct==null?null:`${data.heatmap.avg_confidence_pct.toFixed(1)}%`,detail:"Across covered departments; may include estimates"},
  {label:"Departments covered",icon:"network",value:loading||error?null:data?.heatmap.covered_count,detail:"Departments with readiness scores"},
  {label:"Coverage gaps",icon:"content",value:loading||error?null:data?.heatmap.uncovered.length,detail:"Departments without readiness scores"},
 ].map(item=>({...item,action:"Review readiness",onClick:()=>setDetails(true)}))}/>
 {loading?<p role="status">Loading Readiness snapshot…</p>:error?<p role="alert">{error} <button className="work-button" onClick={()=>setRevision(v=>v+1)}>Retry</button></p>:data&&<><section className={styles.panel}><h3 className={styles.sectionTitle}>Current outlook</h3><p>{data.executive_summary.summary}</p></section><section className={styles.panel}><h3 className={styles.sectionTitle}>Risks needing attention</h3>{data.todays_risks.top_risks.length?data.todays_risks.top_risks.map(r=><div key={r.key} className={styles.row}><div><strong>{r.title}</strong><p>{r.count} records · {r.severity}</p></div><button className="work-button" onClick={()=>setDetails(true)}>Review risk →</button></div>):<p>No risks flagged in the current summary.</p>}</section></>}
 </section>;
}
