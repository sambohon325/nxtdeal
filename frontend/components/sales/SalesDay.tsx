"use client";
import { WorkButton } from "./../WorkspaceUi";
import {CollectionPagination} from "../CollectionPagination";
import {PublishedWebsiteOffers} from "../PublishedWebsiteOffers";
import {useEffect,useState} from "react";
import {crmRequest} from "@/lib/salesCrm";
import {salesDayQueue,type SalesDayTask} from "@/lib/salesDay";
import {WorkspaceIcon} from "../WorkspaceIcon";
import {OverviewHeader,OverviewMetrics,OverviewActions} from "../DepartmentOverview";
import styles from "./SalesDay.module.css";
export function SalesDay({allowed,onNavigate,onLead,onNewLead,revision}:{allowed:Set<string>;onNavigate:(key:string)=>void;onLead:(id:string)=>void;onNewLead:()=>void;revision:number}) {
 const [tasks,setTasks]=useState<SalesDayTask[]|null>(null);
 const [error,setError]=useState(false);const [retry,setRetry]=useState(0);const [page,setPage]=useState(0);const [pageSize,setPageSize]=useState(25);
 const canFollowUp=allowed.has("prospects");
 useEffect(()=>{if(!canFollowUp)return;let current=true;setTasks(null);setError(false);
 crmRequest<SalesDayTask[]>("/sales/crm/tasks?scope=mine").then(data=>{if(current){setTasks(data);setPage(0);}}).catch(()=>{if(current)setError(true);});return()=>{current=false;};
 },[canFollowUp,retry,revision]);
 const queue=salesDayQueue(tasks||[],Date.now());const pages=Math.max(1,Math.ceil(queue.length/pageSize));const current=Math.min(page,pages-1);
 const steps=[
  {key:"appointments",icon:"calendar",title:"Prepare for a visit",text:"Check appointments and manage showroom arrivals.",action:"Open appointments"},
  {key:"inventory",icon:"inventory",title:"Find the right vehicle",text:"Match available stock to your customer's needs.",action:"Browse vehicles"},
  {key:"deals",icon:"deals",title:"Work the deal",text:"Open the deal, review figures and prepare the handoff.",action:"Open deals & desking"},
  {key:"customers",icon:"people",title:"Look after an owner",text:"Open the customer record for ownership and retention.",action:"Find a customer"},
 ].filter(step=>allowed.has(step.key));
 return <div className={styles.day}>
  <OverviewHeader department="Sales" title="Sales overview" description="Start with your follow-ups, then move each customer toward their next step.">{canFollowUp&&<WorkButton type="submit" onClick={onNewLead}>＋ Add an inquiry</WorkButton>}</OverviewHeader>
  {canFollowUp&&<OverviewMetrics label="Sales snapshot" items={[
   {label:"Open follow-ups",icon:"people",value:!tasks||error?null:queue.length,detail:"Assigned to you",action:"Review tasks",onClick:()=>onNavigate("tasks")},
   {label:"Overdue follow-ups",icon:"calendar",value:!tasks||error?null:queue.filter(t=>t.overdue).length,detail:"Past their recorded due time",attention:queue.some(t=>t.overdue),action:"Review tasks",onClick:()=>onNavigate("tasks")},
   {label:"Customers to contact",icon:"conversations",value:!tasks||error?null:new Set(queue.map(t=>t.lead_id)).size,detail:"Customers with open follow-ups",action:"Review my leads",onClick:()=>onNavigate("prospects")},
  ]}/>}
  <div className={styles.columns}>
   <section className={styles.queue} aria-label="My follow-up queue"><header><div><h3>My follow-ups</h3><p>Assigned to you · earliest due first</p></div>{tasks&&<span className={styles.count}>{queue.length} open</span>}</header>
    {!canFollowUp?<p>Follow-up tasks are not available for your role. Use the sales tools available to you below.</p>:error?<div role="alert"><p>Your follow-ups could not be loaded.</p><WorkButton type="submit" onClick={()=>setRetry(v=>v+1)}>Retry follow-ups</WorkButton></div>:tasks===null?<p role="status">Loading your follow-ups…</p>:!queue.length?<div className={styles.empty}><WorkspaceIcon name="calendar"/><h4>You have no open follow-ups.</h4><p>Review your leads and record the next action in each customer's record.</p><WorkButton type="submit" onClick={()=>onNavigate("prospects")}>Review my leads</WorkButton></div>:<ol className={styles.tasks}>{queue.slice(current*pageSize,current*pageSize+pageSize).map(task=><li key={task.id}><div><span className={task.overdue?styles.overdue:styles.due}>{task.overdue?"Overdue · ":""}{task.due_at&&Number.isFinite(Date.parse(task.due_at))?new Date(task.due_at).toLocaleString([],{month:"short",day:"numeric",hour:"numeric",minute:"2-digit"}):"No due date"}</span><h4>{task.description||task.task_type.replaceAll("_"," ")}</h4><p>{task.lead_name||task.lead_id}</p></div><WorkButton type="submit" onClick={()=>onLead(task.lead_id)}>Open customer →</WorkButton></li>)}</ol>}
    {canFollowUp&&<footer><WorkButton type="submit" onClick={()=>onNavigate("tasks")}>Manage all my tasks</WorkButton><CollectionPagination label="Follow-ups" total={queue.length} page={current} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={setPageSize}/></footer>}
   </section>
   <OverviewActions items={steps.map(step=>({label:step.action,icon:step.icon,onClick:()=>onNavigate(step.key)}))}/>
  </div>
  <PublishedWebsiteOffers/>
  {canFollowUp&&<nav className={styles.links} aria-label="Sales review tools"><WorkButton type="submit" onClick={()=>onNavigate("prospects")}>My leads & opportunities →</WorkButton><WorkButton type="submit" onClick={()=>onNavigate("pipeline")}>Review sales pipeline →</WorkButton>{allowed.has("reporting")&&<WorkButton type="submit" onClick={()=>onNavigate("reporting")}>Sales reports →</WorkButton>}</nav>}
 </div>;
}
