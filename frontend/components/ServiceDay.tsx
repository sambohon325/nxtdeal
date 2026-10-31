"use client";
import {RecordTable} from "./RecordTable";
import {WorkField} from "./WorkField";
import {WorkToolbar} from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import {useEffect,useState} from "react";
import {getServiceMyDay,type ServiceMyDay,type RoBucket} from "@/lib/serviceOverview";
import {getRoCatalog,type RoCatalog} from "@/lib/repairOrders";
import {RoWorkspaceModal,NewRoModal,type RoWorkspaceTab} from "./RepairOrderWorkspaceBoard";
import {MenuDashBody} from "./MenuDashPanel";
import {OverviewHeader,OverviewMetrics,OverviewActions} from "./DepartmentOverview";
import styles from "./FinanceDay.module.css";
export function followupDueLabel(due:string, today=new Date()) {
 const localDay=`${today.getFullYear()}-${String(today.getMonth()+1).padStart(2,"0")}-${String(today.getDate()).padStart(2,"0")}`;
 return due<localDay?`Overdue · ${due}`:due===localDay?`Due today · ${due}`:`Due ${due}`;
}
export function serviceQueueAction(queue:string):{tab:RoWorkspaceTab;label:string} {
 if(["my_returns","returns"].includes(queue))return {tab:"followup",label:"Work on follow-up"};
 if(["approval","waiting_approval"].includes(queue))return {tab:"estimate",label:"Review estimate & approval"};
 if(["ready","waiting_delivery"].includes(queue))return {tab:"pickup",label:"Review pickup & return"};
 if(["waiting_parts","parts_delayed"].includes(queue))return {tab:"parts",label:"Review parts"};
 return {tab:"overview",label:"Open repair order"};
}
export function serviceQueues(data:ServiceMyDay) {
 const a=data.advisor_dashboard;
 const queues=[{key:"waiting",label:"My waiting customers",bucket:a.my_waiting_customers},{key:"approval",label:"My approvals",bucket:a.my_pending_approvals},{key:"ready",label:"My pickups",bucket:a.my_vehicles_ready}];
 if(a.my_returned_unfinished)queues.push({key:"my_returns",label:"My returned vehicles — unfinished work",bucket:a.my_returned_unfinished});
 if(data.is_manager_view&&data.command_center?.returned_unfinished)queues.push({key:"returns",label:"All returned vehicles — unfinished work",bucket:data.command_center.returned_unfinished});
 if(data.is_manager_view&&data.command_center)for(const [key,label] of [["open_ros","All open work"],["waiting_approval","Waiting approval"],["waiting_parts","Waiting parts"],["waiting_technician","Waiting technician"],["waiting_delivery","Ready for pickup"],["comebacks","Comebacks"]])queues.push({key,label,bucket:data.command_center[key as keyof typeof data.command_center] as RoBucket});
 if(data.is_manager_view&&data.todays_risks)for(const [key,label] of [["customers_waiting","Waiting at dealership"],["jobs_behind_schedule","Behind schedule"],["parts_delayed","Delayed parts"]])queues.push({key,label,bucket:data.todays_risks[key as keyof typeof data.todays_risks] as RoBucket});
 return queues;
}
export function ServiceDay({theme,allowed,onSelectItem}:{theme:"dark"|"light";allowed:Set<string>;onSelectItem:(key:string)=>void}) {
 const [pageSize,setPageSize]=useState(25);
 const [intake,setIntake]=useState(false);
 const [entryTab,setEntryTab]=useState<RoWorkspaceTab>("overview");
 const [data,setData]=useState<ServiceMyDay|null>(null),[catalog,setCatalog]=useState<RoCatalog|null>(null);
 const [error,setError]=useState(""),[loading,setLoading]=useState(true),[revision,setRevision]=useState(0);
 const [queue,setQueue]=useState("waiting"),[search,setSearch]=useState(""),[page,setPage]=useState(0),[selected,setSelected]=useState<string|null>(null),[summary,setSummary]=useState(false);
 useEffect(()=>{let active=true;setLoading(true);setError("");Promise.all([getServiceMyDay(),getRoCatalog()]).then(([d,c])=>{if(active){setData(d);setCatalog(c);setQueue(q=>q==="waiting"&&d.is_manager_view?"open_ros":q);}}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Service work could not load.");}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[revision]);
 if(intake)return <NewRoModal inline theme={theme} onClose={()=>setIntake(false)} onCreated={id=>{setIntake(false);setEntryTab("overview");setSelected(id);setRevision(v=>v+1);}}/>;
 if(selected&&catalog)return <RoWorkspaceModal inline initialTab={entryTab} theme={theme} roId={selected} catalog={catalog} onClose={()=>setSelected(null)} onChanged={()=>setRevision(v=>v+1)}/>;
 if(summary)return <section><button className="work-button" onClick={()=>setSummary(false)}>← Back to Service work</button><MenuDashBody initialTheme={theme} hideNav hideAssistant department="Service" itemKey="overview" onSelectItem={onSelectItem}/></section>;
 const queues=data?serviceQueues(data):[],currentQueue=queues.find(q=>q.key===queue)??queues[0];
 const rows=(currentQueue?.bucket.repair_orders??[]).filter(r=>[r.service_number,r.description,r.vin,r.technician].join(" ").toLowerCase().includes(search.toLowerCase().trim()));
 const pages=Math.max(1,Math.ceil(rows.length/pageSize)),current=Math.min(page,pages-1);
 return <section className={styles.workspace} aria-label="Service daily work">
 <OverviewHeader department="Service" title="Service overview" description="Check waiting customers, approvals and pickups. Open a queue to move the next repair forward."><button className="work-button" disabled={loading} onClick={()=>setRevision(v=>v+1)}>Refresh</button></OverviewHeader>
 <OverviewMetrics label="Service snapshot" items={[
 {label:"Appointments today",icon:"calendar",value:loading||error?null:data?.advisor_dashboard.my_appointments.today_count,detail:"Assigned advisor appointments",...(allowed.has("appointments")?{action:"View appointments",onClick:()=>onSelectItem("appointments")}: {})},
 ...(data?.is_manager_view?["open_ros","waiting_approval","waiting_parts","waiting_delivery"]:["waiting","approval","ready"]).map(key=>{const q=queues.find(q=>q.key===key);return {label:q?.label??({waiting:"My waiting customers",approval:"My approvals",ready:"My pickups"}[key]!),icon:key==="ready"?"delivery":"service",value:loading||error?null:q?.bucket.count,detail:loading?"Loading current records…":error?"Unavailable":data?.is_manager_view?"Current department work":"Current advisor work",selected:currentQueue?.key===key,action:"Review queue",onClick:()=>{setQueue(key);setPage(0);}};})
 ]}/>
 <OverviewActions items={[
 ...(allowed.has("repair_orders")&&catalog&&!loading&&!error?[{label:"Check in a service customer",icon:"people",onClick:()=>setIntake(true)}]:[]),
 ...[["appointments","Appointments & check-in"],["repair_orders","Repair orders"],["shop_control","Technician dispatch"]].filter(([key])=>allowed.has(key)).map(([key,label])=>({label,icon:"service",onClick:()=>onSelectItem(key)}))
 ]}/>
 <h3 className={styles.sectionTitle}>Work needing attention</h3>
 {loading?<p role="status">Loading Service work…</p>:error?<p role="alert">{error} <button className="work-button" onClick={()=>setRevision(v=>v+1)}>Retry</button></p>:<>
 <p>My work: {data?.advisor_dashboard.advisor.name||data?.advisor_dashboard.advisor.id} · {data?.advisor_dashboard.my_appointments.today_count} appointments today</p>
 <WorkToolbar label="Service queue filters"><WorkField label="Work queue"><select value={currentQueue?.key} onChange={e=>{setQueue(e.target.value);setPage(0);}}>{queues.map(q=><option key={q.key} value={q.key}>{q.label} ({q.bucket.count})</option>)}</select></WorkField><WorkField label="Find a repair order"><input placeholder="Repair order, concern, VIN or technician" value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}}/></WorkField></WorkToolbar>
 {currentQueue?.bucket.note&&<p>{currentQueue.bucket.note}</p>}
 <RecordTable label="Repair orders" paginate={false}><thead><tr><th scope="col">Repair order</th><th scope="col">Stage</th><th scope="col">Technician</th><th scope="col">Next step</th></tr></thead><tbody>{rows.slice(current*pageSize,current*pageSize+pageSize).map(r=><tr key={r.id}><td><strong className="work-record-title">{r.service_number||r.id}</strong><span className="work-record-meta">{r.description||"No concern recorded"}</span>{r.vehicle_returned_at&&<span className="work-record-meta">Vehicle returned · Work remains open</span>}</td><td>{r.ro_stage}{r.vehicle_returned_at&&<span className="work-record-meta">{r.return_followup?.status === "completed" ? `Follow-up recorded · ${r.return_followup.outcome} · Repairs remain open` : r.return_followup ? `${followupDueLabel(r.return_followup.due_date)} · Owner ${r.return_followup.owner_id} · ${r.return_followup.next_action}` : "Needs a follow-up plan"}</span>}</td><td>{r.technician||"Unassigned"}</td><td><button className="work-button" onClick={()=>{setEntryTab(serviceQueueAction(currentQueue?.key??"waiting").tab);setSelected(r.id);}}>{serviceQueueAction(currentQueue?.key??"waiting").label} →</button></td></tr>)}</tbody></RecordTable>
 {!rows.length&&<p>{search?"No matches in the loaded queue. Try another queue or open all repair orders.":"No repair orders in this queue."}</p>}
 <CollectionPagination label="Repair orders" total={rows.length} page={current} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={setPageSize}/>
 {currentQueue&&currentQueue.bucket.count>currentQueue.bucket.repair_orders.length&&<p>This summary includes {currentQueue.bucket.repair_orders.length} of {currentQueue.bucket.count} records. Open Repair orders to find the remaining work.</p>}
 </>}
 {allowed.has("repair_orders")&&<button className="work-button" onClick={()=>onSelectItem("repair_orders")}>Browse all repair orders →</button>}
 <button className="work-button" onClick={()=>setSummary(true)}>Service metrics &amp; capacity →</button>
 <p className={styles.note}>Parts requests, warranty, customer history and reporting remain in the left menu. Queue counts reflect the existing service records and your access.</p>
 </section>;
}
