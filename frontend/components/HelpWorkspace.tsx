"use client";
import {useEffect,useState} from "react";
import {GuidedWalkthrough} from "./GuidedWalkthrough";
import {helpGuides,helpGuideFor} from "@/lib/helpContent";
import {fetchMenuCatalog,type MenuCatalogItem} from "./DepartmentMenuBar";
import type {Catalog,WorkflowDef} from "./DepartmentWorkflowButtons";
import {WorkButton,WorkInput,WorkSelect,WorkSection} from "./WorkspaceUi";
import {WorkField} from "./WorkField";
import {bdcDailyDestinations} from "./bdc/BdcWorkspace";
import {CollectionPagination,collectionPage} from "./CollectionPagination";
import "./HelpWorkspace.css";
const label=(department:string)=>department==="Network"?"Dealer Lab":department==="BDC"?"BDC Center":department;
export function HelpWorkspace({department,departments,role,isSystemAdmin=false,workflows,onOpen,onWorkflow,onTour,onDepartmentTour}:{department:string;departments:string[];role:string;isSystemAdmin?:boolean;workflows:Catalog;onOpen:(item:string,department:string)=>void;onWorkflow:(workflow:WorkflowDef,department:string)=>void;onTour:()=>void;onDepartmentTour:(department:string)=>void}) {
 const [selected,setSelected]=useState(department),[query,setQuery]=useState(""),[page,setPage]=useState(0),[items,setItems]=useState<MenuCatalogItem[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(false),[retry,setRetry]=useState(0);
 useEffect(()=>{
  let active=true;setLoading(true);setItems([]);setError("");
  async function loadDirectory():Promise<MenuCatalogItem[]> {
   if(selected==="BDC"){
    const groups=await Promise.all([fetchMenuCatalog("Sales"),fetchMenuCatalog("Marketing"),fetchMenuCatalog("Service")]);
    const source=groups.flatMap((rows,index)=>rows.map(item=>({...item,key:`${["sales","marketing","service"][index]}:${item.key}`})));
    return bdcDailyDestinations(source,role).map(item=>({key:item.key,label:item.label,description:`Review ${item.label.toLowerCase()} in BDC Center.`}));
   }
   if(["Network","Extras"].includes(selected))return [{key:"overview",label:label(selected),description:"Open this workspace and use its left navigation to choose a tool. Review assumptions and available data before saving a plan."}];
   return fetchMenuCatalog(selected);
  }
  loadDirectory().then(value=>{if(active)setItems(value);}).catch(()=>{if(active)setError("The live section directory could not load. Your tutorial is still available.");}).finally(()=>{if(active)setLoading(false);});
  return()=>{active=false;};
 },[selected,retry,role]);
 const [guideStep,setGuideStep]=useState(0);
 const guide=helpGuideFor(selected,isSystemAdmin);
 const entries=[...items.map(item=>({key:`menu:${item.key}`,title:item.label,description:item.description,steps:[] as string[],tabs:[] as string[],features:[] as {title:string;description:string}[],open:()=>onOpen(item.key,selected)})),...(selected==="Administration"?[]:workflows[selected]||[]).map(workflow=>({key:`workflow:${workflow.key}`,title:workflow.title,description:workflow.description,steps:workflow.stages,tabs:workflow.tabs||[],features:workflow.core_functionality||[],open:()=>onWorkflow(workflow,selected)}))].filter(item=>`${item.title} ${item.description} ${item.steps.join(" ")} ${item.tabs.join(" ")} ${item.features.map(f=>f.title+" "+f.description).join(" ")}`.toLowerCase().includes(query.toLowerCase()));
 const pagination=collectionPage(entries.length,page,8);
 return <section className="help-workspace" data-department-work="" aria-label="Help & learning"><header className="work-section-heading"><div><p className="help-muted">NXTDeal knowledge base</p><h2>Help & learning</h2><p>Learn the daily routine, find a section, and continue your work.</p></div><WorkButton onClick={onTour}>Replay welcome tour</WorkButton></header>
 <div className="help-start"><WorkField label="Choose a department"><WorkSelect aria-label="Help department" value={selected} onChange={e=>{setSelected(e.target.value);setQuery("");setPage(0);setGuideStep(0);}}>{Array.from(new Set(departments)).filter(d=>helpGuides[d]).map(d=><option key={d} value={d}>{label(d)}</option>)}</WorkSelect></WorkField><WorkButton variant="primary" onClick={()=>onDepartmentTour(selected)}>Start {label(selected)} walkthrough</WorkButton></div>
 {guide&&<section className="help-reading" aria-label={`${label(selected)} getting started`}><p className="help-kicker">Getting started · {label(selected)}</p><h3>{guide.goal}</h3><p className="help-prerequisite"><strong>Before you start</strong><br/>{guide.before}</p><div className="help-instruction" aria-live="polite"><span className="help-step-number">{guideStep+1}</span><div><p className="help-kicker">Step {guideStep+1} of {guide.steps.length}</p><p>{guide.steps[guideStep]}</p></div></div><div className="work-actions"><WorkButton disabled={guideStep===0} onClick={()=>setGuideStep(v=>v-1)}>Previous step</WorkButton><WorkButton disabled={guideStep===guide.steps.length-1} onClick={()=>setGuideStep(v=>v+1)}>Next step</WorkButton></div><details><summary>How do I know I’m finished?</summary><p>{guide.check}</p></details><details><summary>What if I get stuck?</summary><p>{guide.trouble}</p></details></section>}
 <WorkSection title={`${label(selected)} Find a section`} description="Search for a task, read its instructions, or open it to work."><WorkField label="Search this department’s sections and workflows"><WorkInput value={query} onChange={e=>{setQuery(e.target.value);setPage(0);}} placeholder="Search tasks, titles, appointments…"/></WorkField>
 {loading&&<p role="status">Loading current sections…</p>}{error&&<p role="alert">{error} <WorkButton onClick={()=>setRetry(v=>v+1)}>Retry</WorkButton></p>}
 <div className="help-directory">{entries.slice(pagination.start,pagination.end).map(item=><details className="glass-inset" key={item.key}><summary aria-label={item.title}>{item.title}</summary><p>{item.description||`Open ${item.title} to review the available records and actions.`}</p>{item.steps.length>0&&<><h4>Workflow stages</h4><ol className="help-steps">{item.steps.map((step,index)=><li key={`${index}:${step}`}>{step}</li>)}</ol></>}{item.tabs.length>0&&<p><strong>Inside this workflow: </strong>{item.tabs.join(" · ")}</p>}{item.features.map(feature=><div key={feature.title}><h4>{feature.title}</h4><p>{feature.description}</p></div>)}<p>Review the current status and required fields, save any changes, then reopen the record to confirm the result. Follow any validation or approval requirements shown in this section.</p><WorkButton onClick={item.open}>Open {item.title}</WorkButton></details>)}</div>
 {!loading&&!entries.length&&!error&&<p>No matching sections. Try another search or department.</p>}<CollectionPagination label="Help directory" total={entries.length} page={pagination.current} pageSize={8} onPageChange={setPage}/></WorkSection>
 <WorkSection title="Common questions"><details><summary>Why is a section or action missing?</summary><p>Your role and connected systems determine availability. Ask your administrator to review your account and department access.</p></details><details><summary>What if a save fails?</summary><p>Keep the form open, review the error and correct the highlighted fields. Recheck the original record before retrying if the result is uncertain, to avoid duplicate entries.</p></details><details><summary>How do Notifications and VIN Lookup work?</summary><p>Notification read status is personal to this device; marking an alert read does not resolve the underlying work. VIN Lookup distinguishes decoded information from missing fields and checks for an inventory match.</p></details><details><summary>How are these guides maintained?</summary><p>The section directory reads the current app catalogs. Task tutorials are reviewed with workflow changes through the repository’s help review check. Catalog updates alone do not rewrite the tutorial instructions.</p></details></WorkSection></section>;
}
const welcomeContext={department:"Operations",title:"Welcome",welcome:true};
export function WelcomeTour({identity,replay,onHelp}:{identity:string;replay:boolean;onHelp:()=>void}) {
 const [open,setOpen]=useState(false);const key=`nxtdeal-welcome:v1:${identity}`;
 useEffect(()=>{try{setOpen(replay||localStorage.getItem(key)!=="done");}catch{setOpen(true);}},[key,replay]);
 function finish(){try{localStorage.setItem(key,"done");}catch{/* Tour can still close when storage is disabled. */}setOpen(false);}
 if(!open)return null;
 return <GuidedWalkthrough context={welcomeContext} onClose={finish} onHelp={()=>{finish();onHelp();}}/>;
}
