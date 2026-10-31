"use client";
import { WorkInput, WorkButton, WorkSelect } from "./../WorkspaceUi";
import {CollectionPagination} from "../CollectionPagination";
import {RecordTable} from "../RecordTable";
import { bdcDestination } from "@/lib/bdcNavigation";
import { InventoryBoard } from "../InventoryBoard";
import { DealDeskBoard, NewDealModal } from "../DealDeskBoard";
import type { LinkedVehicle } from "@/lib/socialReputation";
import { AppointmentsBoard } from "../AppointmentsBoard";
import { departmentWorkDescription } from "@/lib/departmentWork";
import { OverviewHeader } from "../DepartmentOverview";
import { SalesDay } from "./SalesDay";
import { WorkspaceNavigation } from "../WorkspaceNavigation";
import { createPortal } from "react-dom";

import { useEffect, useState } from "react";
import dynamic from "next/dynamic";
import { EntityDashPanel } from "@/components/EntityDashPanel";
import type { Session } from "@/lib/auth";
import type { MenuCatalogItem } from "@/components/DepartmentMenuBar";
import { MenuDashBody } from "@/components/MenuDashPanel";
import { LeadRecordModal } from "@/components/ProspectsBoard";
import { advanceLeadPipeline } from "@/lib/marketingCrm";
import { completeLeadTask, type LeadTaskBrief } from "@/lib/leadRecord";
import { crmRequest, defaultFilters, fetchCrmRecords, stageLabel, type CrmFilters, type CrmRecords, type CrmView } from "@/lib/salesCrm";
import { CrmBulkFollowup } from "./CrmBulkFollowup";
import styles from "./SalesCrmWorkspace.module.css";


const Advanced = dynamic(() => import("./CrmAdvanced").then(m => m.CrmAdvanced));
const Accounts = dynamic(() => import("./SalesAccounts").then(m => m.SalesAccounts));
const Routing = dynamic(() => import("@/components/LeadRoutingBoard").then(m => m.LeadRoutingBoard));
const sections = [
  ["overview", "My day", "overview"], ["prospects", "Leads & opportunities", "prospects"],
  ["contacts", "Contacts", "customers"], ["segments", "Advanced segments", "prospects"], ["duplicates", "Duplicate review", "prospects"], ["accounts", "Households & fleet", "customers"], ["pipeline", "Sales pipeline", "prospects"],
  ["tasks", "Tasks & follow-up", "prospects"], ["appointments", "Appointments & showroom", "appointments"],
  ["deals", "Deals & desking", "deals"], ["inventory", "Vehicle matching", "inventory"],
  ["communications", "Conversations", "communications"], ["sequences", "Communication sequences", "workflows"],
  ["customers", "Ownership & retention", "customers"], ["equity_center", "Equity opportunities", "equity_center"],
  ["workflows", "Sales workflows", "workflows"], ["reporting", "Reports", "reporting"],
] as const;
const date = (value: string | null) => value && Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleDateString() : "—";

export function SalesCrmWorkspace({compact=false,onOpenBdc,navigationHost, theme = "dark", session, items, initialItem, onOpenEntity: openStandaloneEntity}: {compact?:boolean;onOpenBdc?:(item:string)=>void; navigationHost?: HTMLElement | null; theme?: "light" | "dark"; session: Session; items: MenuCatalogItem[]; initialItem: string; onOpenEntity: (id: string) => void}) {
  const [entity, setEntity] = useState<string | null>(null);
  const onOpenEntity = (id: string) => setEntity(id);
  const [active, setActive] = useState(initialItem);
  const [filters, setFilters] = useState<CrmFilters>(defaultFilters);
  const [layout, setLayout] = useState<"table" | "board">("table");
  const [data, setData] = useState<CrmRecords | null>(null);
  const [offset, setOffset] = useState(0);
  const [refresh, setRefresh] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [lead, setLead] = useState<string | null>(null);
  const [viewError, setViewError] = useState("");
  const [views, setViews] = useState<CrmView[]>([]);
  const [viewName, setViewName] = useState("");
  const [saving, setSaving] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [taskFilter, setTaskFilter] = useState("mine");
  const [tasks, setTasks] = useState<(LeadTaskBrief & {lead_id: string; lead_name: string; owner_name: string})[] | null>(null);
  const [selected, setSelected] = useState<string[]>([]);
  const [draftVehicle,setDraftVehicle]=useState<LinkedVehicle|null>(null);
  const [createdDeal,setCreatedDeal]=useState<string|undefined>();
  useEffect(() => {setSelected([]);}, [filters,offset,active]);
  const [columns, setColumns] = useState(["contact", "owner", "source", "vehicle", "activity", "tasks"]);
  const [taskSearch, setTaskSearch] = useState("");
  const keys = new Set(items.map(i => i.key));
  const list = ["prospects", "contacts", "pipeline"].includes(active);
  const changeFilters = (patch: Partial<CrmFilters>) => {setFilters(f => ({...f, ...patch})); setOffset(0);};
  function select(key: string) {
    const destination=bdcDestination("Sales",key);if(destination&&onOpenBdc){onOpenBdc(destination);return;}
    setEntity(null);setLead(null);setDraftVehicle(null);
    setActive(key); setError(""); setNotice(""); setShowCreate(false);
    if (["prospects", "contacts", "pipeline"].includes(key)) {setFilters({...defaultFilters, kind:key === "contacts" ? "Customer" : "Lead"}); setLayout(key === "pipeline" ? "board" : "table"); setOffset(0);}
  }
  useEffect(() => {select(initialItem);}, [initialItem]);
  useEffect(() => {
    if (!list) return;
    let current = true; setLoading(true); setError("");
    const timer = setTimeout(() => fetchCrmRecords(filters, offset).then(d => {if(current) setData(d);}).catch(e => {if(current) {setError(e.message); setData(null);}}).finally(() => {if(current) setLoading(false);}), 200);
    return () => {current=false; clearTimeout(timer);};
  }, [list, filters, offset, refresh]);
  useEffect(() => {let current = true; crmRequest<CrmView[]>("/sales/crm/views").then(v => {if(current) setViews(v);}).catch(() => {if(current) setViewError("Saved views could not be loaded. Refresh the workspace to retry.");}); return () => {current=false;};}, []);
  useEffect(() => {
    if (active !== "tasks") return;
    let current=true; setLoading(true); setError("");
    crmRequest<(LeadTaskBrief & {lead_id: string; lead_name: string; owner_name: string})[]>(`/sales/crm/tasks?scope=${taskFilter}`).then(t => {if(current) setTasks(t);}).catch(e => {if(current) {setTasks(null);setError(e.message);}}).finally(() => {if(current) setLoading(false);});
    return () => {current=false;};
  }, [active, taskFilter, session.employeeId, refresh]);
  async function act(action: () => Promise<unknown>, message: string) {setBusy(true);setError("");setNotice("");try {await action();setNotice(message);setRefresh(v=>v+1);}catch(e){setError(e instanceof Error ? e.message : "Action failed");}finally{setBusy(false);}}
  const title = sections.find(([key])=>key===active)?.[1] || items.find(i=>i.key===active)?.label || "Lead routing";
  const allowed = sections.find(([key])=>key===active)?.[2];
  const canRead = allowed ? keys.has(allowed) : active === "routing" ? session.role === "ADMIN" : keys.has(active);
  const openRecord = (id: string, kind: string) => kind === "Lead" ? setLead(id) : onOpenEntity(id);
  const visibleTasks = (tasks || []).filter(t=>taskFilter === "completed" ? t.completed : taskFilter === "overdue" ? !t.completed && t.due_at && Date.parse(t.due_at)<Date.now() : !t.completed);
  const navigation = navigationHost ? <WorkspaceNavigation department="Sales" active={active} onSelect={select} items={[
    ...sections.filter(([, ,gate])=>keys.has(gate)).map(([key,label])=>({key,label})),
    ...items.filter(i=>!sections.some(([key])=>key===i.key)),
    ...(session.role==="ADMIN"?[{key:"routing",label:"Lead routing"}]:[]),
  ]}/> : <aside className={styles.sidebar}><div className={styles.brand}>Sales <span>CRM</span></div><label className={styles.taskSearch}>Find a sales task<WorkInput type="search" value={taskSearch} onChange={e=>setTaskSearch(e.target.value)} placeholder="Search tasks…" /></label>{taskSearch&&<WorkButton type="submit" className={styles.taskSearch} onClick={()=>setTaskSearch("")}>Show all tasks</WorkButton>}<label className={styles.mobileTasks}>Go to a sales task<WorkSelect value={active} onChange={e=>select(e.target.value)}>{sections.filter(([, ,gate])=>keys.has(gate)).map(([key,label])=><option key={key} value={key}>{label}</option>)}{session.role==="ADMIN"&&<option value="routing">Lead routing</option>}{items.filter(i=>!sections.some(([key])=>key===i.key)).map(i=><option key={i.key} value={i.key}>{i.label}</option>)}</WorkSelect></label><nav aria-label="Sales CRM navigation">{sections.filter(([,label,gate])=>keys.has(gate)&&label.toLowerCase().includes(taskSearch.trim().toLowerCase())).map(([key,label],i)=><WorkButton type="submit" key={key} aria-label={label} title={label} aria-current={active===key?"page":undefined} onClick={()=>select(key)}><svg viewBox="0 0 24 24" aria-hidden="true"><path d={i%3===0?"M4 4h6v6H4zm10 0h6v6h-6zM4 14h6v6H4zm10 0h6v6h-6z":i%3===1?"M8 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM3 20v-4c0-5 10-5 10 0v4m4-14h4m-4 6h4m-4 6h4":"M4 4h16v16H4zm4 5h8m-8 5h8"}/></svg><span>{label}</span></WorkButton>)}{session.role==="ADMIN"&&<WorkButton type="submit" aria-label="Lead routing" title="Lead routing" onClick={()=>select("routing")}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 5h14v4H5zm7 4v6m-7 0h14M5 15v5m14-5v5"/></svg><span>Lead routing</span></WorkButton>}<details><summary>More sales tools</summary>{items.filter(i=>!sections.some(([key])=>key===i.key)&&i.label.toLowerCase().includes(taskSearch.trim().toLowerCase())).map(i=><WorkButton type="submit" key={i.key} onClick={()=>select(i.key)}>{i.label}</WorkButton>)}</details></nav><small>One customer record.<br/>Every step to delivery.</small></aside>;
  if (entity) return <section data-department-work="" aria-label="Sales record details">{navigationHost && createPortal(navigation, navigationHost)}<button className={styles.recordLink} style={{minHeight:44}} onClick={() => { setEntity(null); setRefresh(v => v + 1); }}>← Back to {sections.find(([key]) => key === active)?.[1] || "sales"}</button><EntityDashPanel theme={theme} key={entity} entityId={entity} onClose={() => { setEntity(null); setRefresh(v => v + 1); }} onPopOut={() => openStandaloneEntity(entity)} /></section>;
  return <section className={`${styles.workspace} ${active === "overview" ? styles.dayView : ""} ${theme === "light" ? styles.light : ""} ${navigationHost || compact ? styles.embedded : ""}`} data-department-work={active === "overview" ? undefined : ""} aria-label="Sales CRM">
    {!compact && (navigationHost ? createPortal(navigation, navigationHost) : navigation)}

    <div hidden={!!lead || !!draftVehicle} className={styles.content}>{!compact && active !== "overview" && <OverviewHeader department="Sales" context="Workspace" title={title} description={departmentWorkDescription(active,title)}><WorkButton type="submit" onClick={()=>select("overview")}>← Overview</WorkButton>{list&&filters.kind==="Lead"&&<WorkButton type="submit" disabled={loading} onClick={()=>setShowCreate(v=>!v)}>＋ New lead</WorkButton>}</OverviewHeader>}
      {error&&<div className={styles.error} role="alert">{error} <WorkButton type="submit" onClick={()=>setRefresh(v=>v+1)}>Retry</WorkButton></div>}{notice&&<p role="status" className={styles.notice}>{notice}</p>}
      {!canRead ? <p>This view is unavailable for your current access.</p> : <>
      {showCreate&&<form className={styles.panel} onSubmit={async e=>{e.preventDefault();const form=e.currentTarget;const f=new FormData(form);await act(async()=>{const result=await crmRequest<{id:string}>("/leads",{method:"POST",body:JSON.stringify(Object.fromEntries(f))});setShowCreate(false);setLead(result.id);},"Lead saved to dealership records.");}}><h3>New inquiry</h3><div className={styles.fields}><label>First name<WorkInput name="first_name" required maxLength={80}/></label><label>Last name<WorkInput name="last_name" required maxLength={80}/></label><label>Email<WorkInput name="email" type="email" maxLength={200}/></label><label>Phone<WorkInput name="phone" maxLength={40}/></label><label>Lead source<WorkSelect name="source">{data?.intake_sources.map(s=><option key={s}>{s}</option>)}</WorkSelect></label><label>Vehicle VIN<WorkInput name="vin" maxLength={17}/></label></div><p>Assigned to you. This records the inquiry and does not send a message.</p><WorkButton type="submit" disabled={busy}>Save lead</WorkButton> <WorkButton type="button" onClick={()=>setShowCreate(false)}>Cancel</WorkButton></form>}
      {active === "overview" ? <SalesDay allowed={keys} revision={refresh} onLead={setLead} onNewLead={()=>{select("prospects");changeFilters({owner:"mine"});setShowCreate(true);}} onNavigate={key=>{select(key);if(["prospects","pipeline"].includes(key))changeFilters({owner:"mine"});if(key==="tasks")setTaskFilter("mine");}}/> : list ? <>{viewError && <p role="alert">{viewError}</p>}
        <nav className={styles.views} aria-label="CRM saved views">{[["", "All records"],["mine","My records"],["unassigned","Unassigned"]].map(([value,label])=><WorkButton type="submit" key={label} aria-pressed={filters.owner===value&&!filters.overdue} onClick={()=>changeFilters({owner:value,overdue:false})}>{label}</WorkButton>)}<WorkButton type="submit" aria-pressed={filters.overdue} onClick={()=>changeFilters({overdue:!filters.overdue})}>Overdue follow-up</WorkButton>{views.filter(v=>v.kind===filters.kind).map(v=><WorkButton type="submit" key={v.id} onClick={()=>{const {id: _id,name: _name,layout: l,...f}=v;setFilters(f);setOffset(0);setLayout(l);}}>{v.name}</WorkButton>)}<WorkButton type="submit" onClick={()=>setSaving(v=>!v)}>＋ Save view</WorkButton></nav>
        {saving&&<form className={styles.toolbar} onSubmit={async e=>{e.preventDefault();await act(async()=>{const v=await crmRequest<CrmView>("/sales/crm/views",{method:"POST",body:JSON.stringify({...filters,layout,name:viewName})});setViews(vs=>[...vs,v]);setViewName("");setSaving(false);},"Personal view saved.");}}><WorkInput aria-label="Saved view name" placeholder="Name this personal view" value={viewName} onChange={e=>setViewName(e.target.value)} required maxLength={80}/><WorkButton type="submit" disabled={busy||!viewName.trim()}>Save</WorkButton><WorkButton type="button" onClick={()=>setSaving(false)}>Cancel</WorkButton></form>}
        <div className={styles.toolbar}><WorkInput aria-label="Search CRM records" placeholder="Search name, email, phone, VIN…" value={filters.q} onChange={e=>changeFilters({q:e.target.value})}/><label>Owner<WorkSelect value={filters.owner} onChange={e=>changeFilters({owner:e.target.value})}><option value="">All owners</option><option value="mine">Me</option><option value="unassigned">Unassigned</option>{data?.owners.map(o=><option key={o.id} value={o.id}>{o.name}</option>)}</WorkSelect></label><label>Stage<WorkSelect value={filters.stage} onChange={e=>changeFilters({stage:e.target.value})}><option value="">All stages</option>{(filters.kind==="Lead"?[...(data?.states||[]),"UNTRACKED"]:["CUSTOMER"]).map(s=><option key={s} value={s}>{stageLabel(s)}</option>)}</WorkSelect></label><label>Source<WorkSelect value={filters.source} onChange={e=>changeFilters({source:e.target.value})}><option value="">All sources</option>{data?.sources.map(s=><option key={s}>{s}</option>)}</WorkSelect></label><label>Sort<WorkSelect value={filters.sort} onChange={e=>changeFilters({sort:e.target.value as CrmFilters["sort"]})}><option value="newest">Newest first</option><option value="oldest">Oldest first</option><option value="name">Name</option><option value="overdue">Overdue tasks</option></WorkSelect></label><WorkButton type="submit" onClick={()=>changeFilters({...defaultFilters,kind:filters.kind})}>Reset</WorkButton></div>
        <div className={styles.toolbar}><WorkButton type="submit" aria-pressed={layout==="table"} onClick={()=>setLayout("table")}>Table</WorkButton><WorkButton type="submit" aria-pressed={layout==="board"} onClick={()=>setLayout("board")}>Board</WorkButton><details><summary>Columns</summary>{["contact","owner","source","vehicle","activity","tasks"].map(c=><label key={c}><WorkInput type="checkbox" checked={columns.includes(c)} onChange={()=>setColumns(cs=>cs.includes(c)?cs.filter(k=>k!==c):[...cs,c])}/>{c}</label>)}</details><span className={styles.meta}>{loading?"Refreshing…":`${data?.total ?? "—"} matching records`}</span><WorkButton type="submit" disabled={loading} onClick={()=>setRefresh(v=>v+1)}>Refresh</WorkButton></div>
        {filters.kind==="Lead"&&<CrmBulkFollowup ids={selected} onClear={()=>setSelected([])} onSaved={ids=>{setSelected(current=>current.filter(id=>!ids.includes(id)));setRefresh(v=>v+1);}}/>}<div aria-busy={loading} className={loading?styles.pending:""}>{!data ? <p role="status">{loading?"Loading dealership records…":"Records unavailable."}</p> : layout==="table" ? <div className={styles.table}><RecordTable paginate={false}><thead><tr>{filters.kind==="Lead"&&<th><WorkInput type="checkbox" aria-label="Select leads on this page" checked={data.records.length>0&&data.records.every(r=>selected.includes(r.id))} onChange={e=>setSelected(e.target.checked?data.records.map(r=>r.id):[])}/></th>}<th>Name</th><th>Stage</th>{columns.map(c=><th key={c}>{c}</th>)}</tr></thead><tbody>{data.records.map(r=><tr key={r.id}>{filters.kind==="Lead"&&<td><WorkInput type="checkbox" aria-label={`Select ${r.name}`} checked={selected.includes(r.id)} onChange={e=>setSelected(current=>e.target.checked?[...current,r.id]:current.filter(id=>id!==r.id))}/></td>}<td><button className={styles.recordLink} onClick={()=>openRecord(r.id,r.kind)}>{r.name}</button><small>{r.id}</small></td><td><span className={styles.badge}>{stageLabel(r.stage)}</span></td>{columns.map(c=><td key={c}>{c==="contact"?<>{r.email||"—"}<small>{r.phone||"—"}</small></>:c==="owner"?r.owner_name||"Unassigned":c==="source"?r.source||"—":c==="vehicle"?<>{r.vehicles.map(v=><button key={v.id} className={styles.recordLink} onClick={()=>onOpenEntity(v.id)}>{v.label}</button>)}{!r.vehicles.length&&(r.vin||"—")}</>:c==="activity"?<>{date(r.last_contact)}<small>Created {date(r.created_at)}</small></>:<>{r.open_tasks} open{r.overdue_tasks>0&&<small className={styles.overdue}>{r.overdue_tasks} overdue</small>}</>}</td>)}</tr>)}</tbody></RecordTable>{!data.records.length&&<p>No records match these filters.</p>}</div> : <div className={styles.pipeline}>{(filters.stage?[filters.stage]:filters.kind==="Customer"?["CUSTOMER"]:[...data.states,"UNTRACKED"]).map(s=><section key={s}><header><h3>{stageLabel(s)}</h3><span>{data.stage_counts[s]||0}</span></header>{data.records.filter(r=>r.stage===s).map(r=><article key={r.id}><button className={styles.recordLink} onClick={()=>openRecord(r.id,r.kind)}>{r.name}</button><small>{r.source||"Source not recorded"} · {r.owner_name||"Unassigned"}</small><p>{r.vehicles.map(v=>v.label).join(", ")||r.vin||"Vehicle not selected"}</p><small>Stage since {date(r.stage_since)}</small>{r.overdue_tasks>0&&<p className={styles.overdue}>{r.overdue_tasks} overdue follow-ups</p>}{(data.transitions[s]?.length||0)>0&&<label>Move to<WorkSelect aria-label={`Move ${r.name} to stage`} value="" disabled={busy||loading} onChange={e=>{const next=e.target.value;if(next) void act(()=>advanceLeadPipeline(r.id,next),`${r.name} moved to ${stageLabel(next)}.`);}}><option value="">Select next stage</option>{data.transitions[s].map(next=><option key={next} value={next}>{stageLabel(next)}</option>)}</WorkSelect></label>}</article>)}</section>)}</div>}</div>
        <CollectionPagination label="Customer records" total={data?.total??0} page={Math.floor(offset/50)} pageSize={50} onPageChange={page=>setOffset(page*50)} busy={loading}/>{layout === "board" && <p>Board shows the current page of results.</p>}
      </> : active === "inventory" ? <InventoryBoard inline theme={theme} onPrepare={keys.has("deals") ? v=>setDraftVehicle({id:v.id,year:v.year??undefined,make:v.make??undefined,model:v.model??undefined,trim:v.trim??undefined,price:v.price==null?undefined:Number(v.price)}) : undefined}/> : active === "deals" ? <DealDeskBoard inline theme={theme} initialDealId={createdDeal}/> : active === "appointments" ? <AppointmentsBoard workflow theme={theme} onOpenCustomer={openRecord}/> : ["segments","duplicates","sequences"].includes(active) ? <Advanced key={active} mode={active as "segments"|"duplicates"|"sequences"} employeeId={session.employeeId} role={session.role} onOpen={openRecord}/> : active==="accounts" ? <Accounts onOpen={openRecord}/> : active==="tasks" ? <><div className={styles.views}>{[["mine","My open tasks"],["all","All open"],["overdue","Overdue"],["completed","Completed"]].map(([key,label])=><WorkButton type="submit" key={key} aria-pressed={taskFilter===key} onClick={()=>setTaskFilter(key)}>{label}</WorkButton>)}</div><p className={styles.meta}>Create a task from a lead’s record. Completing a task records work; it does not send a message.</p>{loading?<p role="status">Loading tasks…</p>:<div className={styles.table}><RecordTable paginate={false}><thead><tr><th>Task</th><th>Lead</th><th>Due</th><th>Owner</th><th>Status</th></tr></thead><tbody>{visibleTasks.map(t=><tr key={t.id}><td>{t.description||t.task_type}<small>{t.task_type.replaceAll("_"," ")}</small></td><td><button className={styles.recordLink} onClick={()=>setLead(t.lead_id)}>{t.lead_name || t.lead_id}</button></td><td>{t.due_at && Number.isFinite(Date.parse(t.due_at)) ? new Date(t.due_at).toLocaleString([], {month:"short", day:"numeric", hour:"numeric", minute:"2-digit"}) : "No due date"}</td><td>{t.owner_name || t.assigned_to}</td><td>{t.completed?"Completed":<WorkButton type="submit" disabled={busy} onClick={()=>act(()=>completeLeadTask(t.id),"Task completed.")}>Complete</WorkButton>}</td></tr>)}</tbody></RecordTable>{tasks&&!visibleTasks.length&&<p>No tasks in this view.</p>}</div>}</> : <div className={styles.native}>{active==="routing"?<Routing theme={theme}/>:<MenuDashBody initialTheme={theme} hideNav hideAssistant key={active} department="Sales" itemKey={active === "cadences" ? "workflows" : active} onSelectItem={select}/>}</div>}
      </>}
    </div>{draftVehicle&&<NewDealModal inline theme={theme} initialVehicle={draftVehicle} onClose={()=>setDraftVehicle(null)} onCreated={id=>{setDraftVehicle(null);setCreatedDeal(id);select("deals");}}/>}{lead&&<LeadRecordModal inline key={lead} theme={theme} leadId={lead} onClose={()=>setLead(null)} onChanged={()=>setRefresh(v=>v+1)}/>}
  </section>;
}
