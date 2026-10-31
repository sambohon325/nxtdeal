"use client";
import {CollectionPagination} from "./CollectionPagination";
import {useEffect,useState} from "react";
import {getDispatchBoard,assignTechnician,type DispatchBoard} from "@/lib/shopControl";
import {getRoCatalog,type RoCatalog} from "@/lib/repairOrders";
import {getSession} from "@/lib/auth";
import {RoWorkspaceModal} from "./RepairOrderWorkspaceBoard";
import {ShopControlBoard} from "./ShopControlBoard";
import styles from "./FinanceDay.module.css";
export function DispatchDay({theme}:{theme:"dark"|"light"}) {
 const [board,setBoard]=useState<DispatchBoard|null>(null),[catalog,setCatalog]=useState<RoCatalog|null>(null);
 const [error,setError]=useState(""),[loading,setLoading]=useState(true),[revision,setRevision]=useState(0),[busy,setBusy]=useState(false);
 const [filter,setFilter]=useState("unassigned"),[search,setSearch]=useState(""),[page,setPage]=useState(0),[selected,setSelected]=useState<string|null>(null);
 const [picks,setPicks]=useState<Record<string,string>>({}),[notice,setNotice]=useState(""),[metrics,setMetrics]=useState(false);
 const canAssign=["ADMIN","OPERATIONS","SERVICE"].includes(getSession()?.role??"");
 useEffect(()=>{let active=true;setLoading(true);setError("");Promise.all([getDispatchBoard(),getRoCatalog()]).then(([b,c])=>{if(active){setBoard(b);setCatalog(c);}}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Dispatch could not load.");}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[revision]);
 async function save(id:string){setBusy(true);setError("");setNotice("");try{await assignTechnician(id,picks[id]||null);setNotice("Technician assignment saved.");setPicks(p=>{const next={...p};delete next[id];return next;});setRevision(v=>v+1);}catch(e){setError(e instanceof Error?e.message:"Assignment failed. Your selection is retained.");}finally{setBusy(false);}}
 if(selected&&catalog)return <RoWorkspaceModal inline theme={theme} roId={selected} catalog={catalog} onClose={()=>setSelected(null)} onChanged={()=>setRevision(v=>v+1)}/>;
 if(metrics)return <section><button className="work-button" onClick={()=>setMetrics(false)}>← Back to dispatch</button><ShopControlBoard theme={theme}/></section>;
 const roster=Object.entries(board?.technicians??{});
 const all=[...(board?.unassigned??[]).map(r=>({...r,assigned:""})),...roster.flatMap(([id,t])=>t.repair_orders.map(r=>({...r,assigned:id})))];
 const rows=all.filter(r=>(filter==="all"||filter==="unassigned"&&!r.assigned||filter===r.assigned)&&[r.service_number,r.description,r.vin].join(" ").toLowerCase().includes(search.toLowerCase().trim()));
 const pages=Math.max(1,Math.ceil(rows.length/25)),current=Math.min(page,pages-1);
 return <section className={styles.workspace} aria-label="Technician dispatch">
 <header><div><h3>Assign work and keep the shop moving</h3><p>Review the repair order, select a technician, then save. Assignment does not advance the repair stage.</p></div><button className="work-button" disabled={busy||loading} onClick={()=>setRevision(v=>v+1)}>Refresh</button></header>
 {error&&<p role="alert">{error} <button className="work-button" onClick={()=>setRevision(v=>v+1)}>Retry</button></p>}{notice&&<p role="status">{notice}</p>}
 <label className={styles.search}>Assigned to<select className={styles.returnButton} value={filter} onChange={e=>{setFilter(e.target.value);setPage(0);}}><option value="unassigned">Unassigned</option><option value="all">All open work</option>{roster.map(([id,t])=><option key={id} value={id}>{t.name||id}</option>)}</select></label>
 <label className={styles.search}>Find a repair order<input value={search} onChange={e=>{setSearch(e.target.value);setPage(0);}} placeholder="RO number, concern or VIN"/></label>
 {loading?<p role="status">Loading dispatch…</p>:board&&<>
 {!roster.length&&<p>No service technicians are listed. An administrator needs to review the Service technician roster before jobs can be assigned.</p>}
 <div className={styles.records}>{rows.slice(current*25,current*25+25).map(r=><article key={r.id}><div><h3>{r.service_number||r.id}</h3><p>{r.description}</p><small>{r.ro_stage} · {board.technicians[r.assigned]?.name||r.assigned||"Unassigned"}</small><button className="work-button" disabled={busy} onClick={()=>setSelected(r.id)}>Open repair order →</button></div>{canAssign&&<div><label className={styles.search}>Technician for {r.service_number}<select className={styles.returnButton} disabled={busy} value={picks[r.id]??r.assigned} onChange={e=>setPicks(p=>({...p,[r.id]:e.target.value}))}><option value="">Unassigned</option>{roster.map(([id,t])=><option key={id} value={id}>{t.name||id}</option>)}</select></label><button className="work-button" disabled={busy||picks[r.id]===undefined||picks[r.id]===r.assigned} onClick={()=>save(r.id)}>Save assignment</button></div>}</article>)}</div>
 {!rows.length&&<p>No repair orders match this view.</p>}
 <CollectionPagination label="Jobs" total={rows.length} page={current} pageSize={25} onPageChange={setPage} busy={busy}/>
 </>}
 <button className="work-button" onClick={()=>setMetrics(true)}>Capacity, bottlenecks &amp; board view →</button>
 </section>;
}
