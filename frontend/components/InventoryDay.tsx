"use client";
import {useEffect,useState} from "react";
import {InventoryWorkspaceBoard} from "./InventoryWorkspaceBoard";
import {MenuDashBody} from "./MenuDashPanel";
import {getLifecycleBoard,type LifecycleBoard} from "@/lib/vehicleLifecycle";
import {OverviewHeader,OverviewMetrics,OverviewActions} from "./DepartmentOverview";
import styles from "./DepartmentOverview.module.css";
const stages=[
 {label:"Incoming",icon:"delivery",keys:["Acquired","In Transit","Received"],detail:"Acquired, in transit or received"},
 {label:"In preparation",icon:"service",keys:["Inspection","Recon"],detail:"Inspection and reconditioning"},
 {label:"Photos & listings",icon:"content",keys:["Photo","Merchandising"],detail:"Preparing for the front line"},
 {label:"Ready for sale",icon:"inventory",keys:["Front Line Ready"],detail:"Front line ready vehicles"},
 {label:"Awaiting delivery",icon:"deals",keys:["Sold"],detail:"Sold, not yet delivered"},
];
export function inventoryDayActions(allowed:Set<string>) {
 return [
  {key:"acquisitions",label:"Review incoming vehicles"},
  {key:"lot_management",label:"Locate vehicles & keys"},
  {key:"pricing",label:"Review vehicle pricing"},
  {key:"merchandising",label:"Prepare photos & listings"},
  {key:"wholesale",label:"Review wholesale vehicles"},
  {key:"syndication",label:"Check listing distribution"},
 ].filter(action=>allowed.has(action.key));
}
export function InventoryDay({theme,allowed,onSelectItem}:{theme:"dark"|"light";allowed:Set<string>;onSelectItem:(key:string)=>void}) {
 const [summary,setSummary]=useState(false),[board,setBoard]=useState<LifecycleBoard|null>(null),[error,setError]=useState("");
 const [loading,setLoading]=useState(true),[revision,setRevision]=useState(0),[showBoard,setShowBoard]=useState(false);
 const canView=allowed.has("inventory");
 useEffect(()=>{if(!canView)return;let active=true;setLoading(true);setError("");getLifecycleBoard().then(d=>{if(active)setBoard(d);}).catch(e=>{if(active)setError(e instanceof Error?e.message:"Inventory snapshot could not load.");}).finally(()=>{if(active)setLoading(false);});return()=>{active=false;};},[canView,revision]);
 if(summary)return <section><button className="work-button" onClick={()=>setSummary(false)}>Back to Inventory work</button><MenuDashBody initialTheme={theme} hideNav hideAssistant department="Inventory" itemKey="overview" onSelectItem={onSelectItem}/></section>;
 return <section aria-label="Inventory daily work" className="space-y-4">
  <OverviewHeader department="Inventory" title="Inventory overview" description="See where your stock stands, from arrival and preparation to the front line and delivery."><button className="work-button" disabled={loading||!canView} onClick={()=>setRevision(v=>v+1)}>Refresh</button></OverviewHeader>
  {canView&&<OverviewMetrics items={stages.map(g=>({label:g.label,icon:g.icon,value:loading||error||!board?null:g.keys.reduce((sum,stage)=>sum+(board[stage]?.length??0),0),detail:loading?"Loading current records…":error?"Unavailable":g.detail,action:"View vehicles",onClick:()=>onSelectItem("inventory")}))}/>}
  {canView&&(loading?<p role="status" className={styles.muted}>Loading Inventory snapshot…</p>:error?<p role="alert">{error} <button className="work-button" onClick={()=>setRevision(v=>v+1)}>Retry</button></p>:<section className={styles.panel}><h3 className={styles.sectionTitle}>Move vehicles forward</h3><p>Open the vehicle workspace to inspect a unit, update its preparation, or assign the next step.</p><button className="work-button" aria-expanded={showBoard} onClick={()=>setShowBoard(v=>!v)}>{showBoard?"Hide vehicle workspace":"Show vehicle workspace"}</button>{showBoard&&<InventoryWorkspaceBoard key={revision} theme={theme} compact onBoardUpdated={setBoard}/>}</section>)}
  <OverviewActions items={inventoryDayActions(allowed).map(a=>({label:a.label,icon:"inventory",onClick:()=>onSelectItem(a.key)}))}/>
  {!canView&&<p className={styles.muted}>Your available Inventory tools are listed above and in the department menu.</p>}
  <button className="work-button" onClick={()=>setSummary(true)}>Inventory metrics & reporting →</button>
 </section>;
}
