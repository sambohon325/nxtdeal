"use client";
import {RecordTable} from "./RecordTable";
import {WorkField} from "./WorkField";
import {WorkToolbar} from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import {useEffect,useState} from "react";
import {listAllDeals,type Deal} from "@/lib/deals";
import {getSession} from "@/lib/auth";
import {financeQueues,financeQueue,financeStep,type FinanceQueue} from "@/lib/financeDay";
import {DealDetailModal} from "./DealDeskBoard";
import {MenuDashBody} from "./MenuDashPanel";
import {OverviewHeader,OverviewMetrics} from "./DepartmentOverview";
import styles from "./FinanceDay.module.css";
export function FinanceDay({theme,onSelectItem}:{theme:"dark"|"light";onSelectItem:(key:string)=>void}) {
 const [pageSize,setPageSize]=useState(25);
 const [deals,setDeals]=useState<Deal[]>([]),[queue,setQueue]=useState<FinanceQueue>("handoff");
 const [search,setSearch]=useState(""),[page,setPage]=useState(0),[revision,setRevision]=useState(0);
 const [loading,setLoading]=useState(true),[error,setError]=useState("");
 const [summary,setSummary]=useState(false);
 const [selected,setSelected]=useState<Deal|null>(null);
 useEffect(()=>{let active=true;setLoading(true);setError("");listAllDeals().then(rows=>{if(active)setDeals(rows);}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Unable to load Finance work.");}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[revision]);
 const rows=financeQueue(deals,queue,search),pages=Math.max(1,Math.ceil(rows.length/pageSize)),current=Math.min(page,pages-1);
 if(summary)return <section><button className="work-button" onClick={()=>setSummary(false)}>← Back to Finance work</button><MenuDashBody initialTheme={theme} hideNav hideAssistant department="Finance" itemKey="overview" onSelectItem={onSelectItem}/></section>;
 if(selected)return <DealDetailModal inline theme={theme} dealId={selected.id} initialTab={financeStep(selected)?.tab??"worksheet"} session={getSession()} onClose={()=>setSelected(null)} onChanged={()=>setRevision(v=>v+1)}/>;
 return <section className={styles.workspace} aria-label="Finance daily work">
   <OverviewHeader department="Finance" title="Finance overview" description="See each stage of the finance queue, then open the deal that needs your next action."><button className="work-button" onClick={()=>setRevision(v=>v+1)} disabled={loading}>Refresh</button></OverviewHeader>
   <OverviewMetrics label="Finance work queues" items={financeQueues.slice(0,4).map(q=>({label:q.label,icon:"finance",value:loading||error?null:deals.filter(d=>financeStep(d)?.queue===q.key).length,detail:loading?"Loading current records…":error?"Unavailable":q.key==="funded"||q.key==="cancelled"?"Recorded deals · all dates":"Oldest updates first",selected:queue===q.key,action:"Review queue",onClick:()=>{setQueue(q.key);setPage(0);}}))}/>
   <nav className={styles.history} aria-label="Completed Finance queues">{financeQueues.slice(4).map(q=><button className="work-button" key={q.key} aria-pressed={queue===q.key} onClick={()=>{setQueue(q.key);setPage(0);}}>{q.label} · {loading||error?"—":deals.filter(d=>financeStep(d)?.queue===q.key).length}</button>)}</nav>
   <h3 className={styles.sectionTitle}>{financeQueues.find(q=>q.key===queue)?.label}</h3>
   <WorkToolbar label="Finance queue filters"><WorkField label="Find a deal"><input value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}} placeholder="Customer, vehicle or deal number"/></WorkField></WorkToolbar>
   {loading?<p role="status">Loading Finance work…</p>:error?<p role="alert">{error} <button className="work-button" onClick={()=>setRevision(v=>v+1)}>Retry</button></p>:<>
   <RecordTable label="Deals" paginate={false}><thead><tr><th scope="col">Customer &amp; vehicle</th><th scope="col">Status</th><th scope="col">Next step</th><th scope="col">Action</th></tr></thead><tbody>{rows.slice(current*pageSize,current*pageSize+pageSize).map(d=><tr key={d.id}><td><strong className="work-record-title">{d.customer?.name||"Customer not linked"}</strong><span className="work-record-meta">{d.vehicle?.description||"Vehicle not linked"} · {d.id}</span></td><td>{d.financing_status.replaceAll("_"," ")}</td><td>{!d.selected_scenario_id?"Review the missing pricing option.":d.trade_in&&!d.trade_in.approved?"Approve the trade appraisal.":"Review the deal and continue the handoff."}</td><td><button className="work-button" onClick={()=>setSelected(d)}>{financeStep(d)?.action} →</button></td></tr>)}</tbody></RecordTable>
   {!rows.length&&<p>{search?"No matching deals in this queue. Try another queue or search.":"No deals in this queue."}</p>}
   <CollectionPagination label="Deals" total={rows.length} page={current} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={setPageSize}/>
   </>}
   <button className="work-button" onClick={()=>setSummary(true)}>Financial overview &amp; reporting →</button>
   <p className={styles.note}>Sales worksheets still in preparation stay in Sales. Accounting, loan servicing, compliance and reporting remain in the left menu. Queue placement does not establish compliance or funding readiness.</p>
 </section>;
}


