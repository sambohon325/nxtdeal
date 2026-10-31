"use client";
import { WorkButton, WorkSelect, WorkInput } from "./../WorkspaceUi";
import {OverviewHeader} from "../DepartmentOverview";

import {useCallback, useEffect, useRef, useState} from "react";
import {createPortal} from "react-dom";
import {WorkspaceNavigation} from "../WorkspaceNavigation";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";
import {planFamilies} from "./lifecycle";
import {LabExperimentImport} from "./LabExperimentImport";
import {LabVersionHistory} from "./LabVersionHistory";
import {LabGoals} from "./LabGoals";
import {LabMix} from "./LabMix";
import {LabReferences} from "./LabReferences";
import {LabSoftware} from "./LabSoftware";
import {LabCampaigns} from "./LabCampaigns";
import {LabFinance} from "./LabFinance";
import {LabCustomers} from "./LabCustomers";
import {LabOperating} from "./LabOperating";
import {LabSetup} from "./LabSetup";
import {LabAnalysis} from "./LabAnalysis";
import {LabNotebooks} from "./LabNotebooks";
import {LabPeriodReviews} from "./LabPeriodReviews";
import {LabReports} from "./LabReports";
import {StartingFigures} from "./StartingFigures";
import {DecisionChange} from "./DecisionChange";
import styles from "./DealershipLab.module.css";

export type Section = {values:Record<string,string|number>;basis:"assumed"|"user_reported";note:string;reviewed_hash:string|null};
export type Plan = {id:string;name:string;parent_id:string|null;revision:number;archived:boolean;updated_at:string;sections:Record<string,Section>;model_definition?:unknown;report_source?:{workspace_id:string;revision:number;month:string;rooftop:string|null};recovered_from?:{workspace_id:string;revision:number};imported_from?:{file_sha256:string;claimed_data_path:string;input_schema:number}};
export type Definition = {title:string;description:string;fields:Record<string,[string,string,string|number,(string[]|number)?,number?]>};
export type Request = <T>(path:string,method?:string,body?:unknown)=>Promise<T>;
export type Decision = {id:string;title:string;help:string;fields:[string,string,number,number,number][]};
type Data = {workspaces:Plan[];sections:Record<string,Definition>};
type View = "references"|"reviews"|"goals"|"mix"|"software"|"campaigns"|"finance"|"customers"|"operating"|"setup"|"explore"|"saved"|"figures"|"change"|"compare"|"reports"|"notebooks"|"procedures";
const questions:Record<string,[string,string,string]> = {
 staffing:["People","Should we add to the team?","Compare staffing costs and capacity assumptions."],
 advertising:["Marketing","What if we change our ad spend?","Explore demand, cost and the sales funnel."],
 software:["Operations","Would new software be worth it?","Test costs and explicit performance assumptions."],
 margin:["Sales","What if we trade margin for volume?","Compare gross per sale and closing assumptions."],
 followup:["Sales","What if we improve follow-up?","Test response, appointment and show rates."],
 service:["Service","Could service handle more demand?","Explore demand, capacity and gross per repair order."],
 fi:["Finance","What if F&I gross changes?","Compare a change in gross per delivered vehicle."],
 portfolio:["Finance","How resilient are our collections?","Stress-test BHPH payment assumptions."],
 cost:["Operations","Can we support another expense?","See the effect of an additional monthly cost."],
};

export type LabWorkspaceProps={navigationHost?:HTMLElement|null;theme?:"light"|"dark";onDraftOpenChange?:(dirty:boolean)=>void;onSavingChange?:(busy:boolean)=>void};
export function LabWorkspace({navigationHost,theme="dark",onDraftOpenChange,onSavingChange}:LabWorkspaceProps) {
 const [data,setData]=useState<Data|null>(null),[decisions,setDecisions]=useState<Decision[]>([]);
 const [view,setView]=useState<View>("explore"),[baseline,setBaseline]=useState(""),[proposed,setProposed]=useState(""),[decision,setDecision]=useState("");
 const [name,setName]=useState(""),[error,setError]=useState(""),[busy,setBusy]=useState(false),[dirty,setDirty]=useState(false),[runId,setRunId]=useState("");
 const pending=useRef(false);
 const [pendingNavigation,setPendingNavigation]=useState<{next:View;action?:()=>void}|null>(null);
 const [editorRevision,setEditorRevision]=useState(0);
 useEffect(()=>{onDraftOpenChange?.(dirty);return()=>onDraftOpenChange?.(false);},[dirty,onDraftOpenChange]);
 useEffect(()=>{onSavingChange?.(busy);return()=>onSavingChange?.(false);},[busy,onSavingChange]);
 const request=useCallback<Request>(async(path,method="GET",body)=>{
  const response=await fetch(`${API_BASE}/dealership-lab${path}`,{method,headers:{"Content-Type":"application/json",...authHeaders()},body:body===undefined?undefined:JSON.stringify(body)});
  const result=await response.json();
  if(!response.ok)throw new Error(typeof result.detail==="string"?result.detail:"Unable to complete this action. Please try again.");
  return result;
 },[]);
 const reload=useCallback(async()=>{const next=await request<Data>("");setData(next);return next;},[request]);
 useEffect(()=>{Promise.all([request<Data>(""),request<{decisions:Decision[]}>("/decisions")]).then(([d,c])=>{setData(d);setDecisions(c.decisions);setBaseline(d.workspaces.find(w=>!w.archived&&!w.parent_id)?.id||d.workspaces.find(w=>!w.archived)?.id||"");setError("");}).catch(e=>setError(e.message));},[reload,request]);
 useEffect(()=>{if(!dirty)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);
 function remember(plan:Plan){setData(d=>d?{...d,workspaces:[...d.workspaces.filter(w=>w.id!==plan.id),plan]}:d);}
 const source=data?.workspaces.find(w=>w.id===baseline);
 const option=data?.workspaces.find(w=>w.id===proposed);
 const template=decisions.find(d=>d.id===decision);
 function finishNavigation(next:View,action?:()=>void){setPendingNavigation(null);setDirty(false);setName("");setError("");setEditorRevision(v=>v+1);action?.();setView(next);}
 function navigate(next:View,action?:()=>void){if(busy||pending.current)return;if(dirty){setPendingNavigation({next,action});return;}finishNavigation(next,action);}
 async function perform(work:()=>Promise<void>){if(pending.current)return;pending.current=true;setBusy(true);setError("");try{await work();}catch(e){setError(e instanceof Error?e.message:"Unable to save this change.");}finally{pending.current=false;setBusy(false);}}
 const question=view==="compare"?(option?.name||"Compare your decision"):template?(questions[template.id]?.[1]||template.title):"Review your starting figures";
 if(!data)return <section className={`${styles.shell} ${styles.integrated}`}><h2>Dealership lab</h2>{error?<p role="alert">{error} <WorkButton type="submit" onClick={()=>{setError("");reload().catch(e=>setError(e.message));}}>Retry</WorkButton></p>:<p>Loading your saved decisions…</p>}</section>;
 const active=data.workspaces.filter(w=>!w.archived);
 const isJourney=["figures","change","compare"].includes(view);
 const navigation=<WorkspaceNavigation department="Dealership lab" active={view==="change"||view==="compare"?"explore":view} onSelect={key=>navigate(key as View)} items={[
  {key:"setup",label:"Setup & data sources",group:"My dealership"},
  {key:"operating",label:"Departments & operating plan",group:"My dealership"},
  {key:"customers",label:"Customers & inventory",group:"My dealership"},
  {key:"finance",label:"Financial assumptions",group:"My dealership"},
  {key:"campaigns",label:"Campaigns & demand",group:"Planning tools"},
  {key:"mix",label:"Customer & inventory mix",group:"Planning tools"},
  {key:"references",label:"Public market references",group:"Planning tools"},
  {key:"software",label:"Software planning",group:"Planning tools"},
  {key:"explore",label:"Explore a decision",group:"Decisions"},
  {key:"goals",label:"Goal planner",group:"Decisions"},
  {key:"saved",label:"Saved decisions",group:"Decisions"},
  {key:"figures",label:"Starting figures",group:"Decisions"},
  {key:"reviews",label:"Monthly & quarterly reviews",group:"Reports & notes"},
  {key:"reports",label:"Monthly reports",group:"Reports & notes"},
  {key:"notebooks",label:"Success Workbooks",group:"Reports & notes"},
  {key:"procedures",label:"Procedure Bible",group:"Reports & notes"},
 ]}/>;
 return <section className={`${styles.shell} ${styles.integrated}`} data-department-work="" data-lab-theme={theme} aria-label="Dealership lab">
  {navigationHost?createPortal(navigation,navigationHost):navigation}
  {pendingNavigation&&<section role="alert" className={styles.panel}><h3>Leave your unsaved Lab changes?</h3><p>Your draft stays open below. Keep editing, or discard it and continue to the selected destination.</p><div className={styles.actions}><WorkButton type="submit" onClick={()=>setPendingNavigation(null)}>Keep editing Lab changes</WorkButton><WorkButton type="submit" disabled={busy} onClick={()=>{if(busy||pending.current)return;finishNavigation(pendingNavigation.next,pendingNavigation.action);}}>Discard Lab changes and continue</WorkButton></div></section>}
  <OverviewHeader context={view==="explore"?"At a glance":"Workspace"} department="Dealer Lab" title={isJourney?question:view==="references"?"Public market references":view==="reviews"?"Monthly & quarterly reviews":view==="goals"?"Goal planner":view==="mix"?"Customer & inventory mix":view==="software"?"Software planning":view==="campaigns"?"Campaigns & demand":view==="finance"?"Financial assumptions":view==="customers"?"Customers & inventory":view==="operating"?"Departments & operating plan":view==="setup"?"Setup & data sources":view==="saved"?"Saved decisions":view==="reports"?"Monthly reports":view==="procedures"?"Procedure Bible":view==="notebooks"?"Success Workbooks":"Explore your next move."} description="Test a change before you commit. Saved assumptions stay separate from live operations."/>
  {error&&<p role="alert" className={styles.error}>{error}</p>}
  {isJourney&&<ol className={styles.journey} aria-label="Decision progress">{["Starting figures","Your change","Comparison"].map((title,i)=><li key={title} aria-current={i===["figures","change","compare"].indexOf(view)?"step":undefined}><span>{i+1}</span>{title}</li>)}</ol>}
  {view==="goals"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabGoals key={`${source.id}:${source.revision}:${editorRevision}`} plan={source} request={request} onDirty={setDirty} onBusy={setBusy} onCreated={w=>{remember(w);setBaseline(w.id);setDirty(false);setView("setup");}}/>:<p>Create a starting plan in Starting figures first.</p>}</>}
  {view==="mix"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabMix key={`${source.id}:${editorRevision}`} plan={source} request={request} onSaved={remember} onDirty={setDirty} onBusy={setBusy}/>:<p>Create a starting plan in Starting figures first.</p>}</>}
  {view==="references"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabReferences key={`${source.id}:${editorRevision}`} plan={source} request={request}/>:<p>Create a starting plan in Starting figures first.</p>}</>}
  {view==="software"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabSoftware key={`${source.id}:${editorRevision}`} plan={source} request={request} onSaved={remember} onDirty={setDirty} onBusy={setBusy}/>:<p>Create a starting plan in Starting figures first.</p>}</>}
  {view==="campaigns"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabCampaigns key={`${source.id}:${editorRevision}`} plan={source} request={request} onSaved={remember} onDirty={setDirty} onBusy={setBusy}/>:<p>Create a starting plan in Starting figures first.</p>}</>}
  {view==="finance"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabFinance key={`${source.id}:${editorRevision}`} plan={source} request={request} onSaved={remember} onDirty={setDirty} onBusy={setBusy}/>:<p>Create a starting plan in Starting figures first.</p>}</>}
  {view==="customers"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabCustomers key={`${source.id}:${editorRevision}`} plan={source} request={request} onSaved={remember} onDirty={setDirty} onBusy={setBusy}/>:<p>Create a starting plan in Starting figures first.</p>}</>}
  {view==="operating"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabOperating key={`${source.id}:${editorRevision}`} plan={source} request={request} onSaved={remember} onDirty={setDirty} onBusy={setBusy}/>:<p>Create a starting plan in Starting figures first.</p>}</>}
  {view==="setup"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabSetup key={`${source.id}:${editorRevision}`} plan={source} request={request} onSaved={remember} onDirty={setDirty} onBusy={setBusy} onContinue={()=>navigate(template?"figures":"explore")} onOperating={()=>navigate("operating")} onReports={()=>navigate("reports")} reportSourcePlan={data.workspaces.find(w=>w.id===source.report_source?.workspace_id)} onSourceReports={id=>{if(active.some(w=>w.id===id))navigate("reports",()=>setBaseline(id));}}/>:<div className={styles.panel}><p>Create a starting plan to set up your dealership.</p><WorkButton type="submit" onClick={()=>navigate("figures")}>Create starting plan</WorkButton></div>}</>}
  {view==="explore"&&<><div className={styles.labIntro}><div><p className={styles.eyebrow}>START WITH A QUESTION</p><h3>What would you like to explore?</h3><p>Choose a decision. We’ll carry your starting figures through to the comparison.</p></div><div className={styles.startingPoint}><label>Starting figures<WorkSelect value={baseline} onChange={e=>setBaseline(e.target.value)}><option value="">Set up new starting figures</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<small>Saved {new Date(source.updated_at).toLocaleDateString()} · review before using</small>:<small>No live data is imported automatically.</small>}</div></div><div className={styles.decisionGrid}>{decisions.map(d=>{const copy=questions[d.id]||["Plan",d.title,d.help];return <button className={styles.decisionCard} key={d.id} onClick={()=>navigate("figures",()=>{setDecision(d.id);setProposed("");setRunId("");})}><span className={styles.eyebrow}>{copy[0]}</span><strong>{copy[1]}</strong><span>{copy[2]}</span><span className={styles.cardAction}>Explore this change <span aria-hidden="true">→</span></span></button>;})}</div>{!decisions.length&&<p role="alert">Decision templates could not be loaded. <WorkButton type="submit" onClick={()=>perform(async()=>setDecisions((await request<{decisions:Decision[]}>("/decisions")).decisions))}>Retry templates</WorkButton></p>}</>}
  {view==="figures"&&<><div className={styles.panel}><h3>Start with your dealership’s figures</h3><p>Reuse a saved plan, or create a private starting point. These figures are assumptions unless you identify a source and reporting period.</p><label>Saved starting point<WorkSelect disabled={busy} value={baseline} onChange={e=>{const selected=e.target.value;navigate("figures",()=>setBaseline(selected));}}><option value="">New starting figures</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{!source&&<form onSubmit={e=>{e.preventDefault();perform(async()=>{const w=await request<Plan>("/workspaces","POST",{name:name.trim()});remember(w);setBaseline(w.id);setName("");setDirty(false);});}}><label>Plan name<WorkInput required maxLength={100} placeholder="October operating assumptions" value={name} onChange={e=>{setName(e.target.value);setDirty(true);}}/></label><WorkButton type="submit" disabled={busy||!name.trim()}>Create starting figures</WorkButton></form>}</div>{source&&<StartingFigures key={`${source.id}:${editorRevision}`} plan={source} definitions={data.sections} request={request} onSaved={remember} onDirty={setDirty} onBusy={setBusy} onContinue={()=>navigate("change")} canContinue={!!template} onSetup={()=>navigate("setup")} onOperating={()=>navigate("operating")}/>}{!template&&<WorkButton type="submit" onClick={()=>navigate("explore")}>Choose a decision to explore →</WorkButton>}</>}
  {view==="change"&&source&&template&&<DecisionChange key={`${source.id}:${source.revision}:${template.id}:${editorRevision}`} plan={source} template={template} request={request} onDirty={setDirty} onBusy={setBusy} onBack={()=>navigate("figures")} onCreated={async w=>{remember(w);setProposed(w.id);setDirty(false);setView("compare");}}/>}
  {(view==="compare"||view==="saved")&&<>{view==="saved"&&<><LabExperimentImport key={editorRevision} request={request} busy={busy} onDirty={setDirty} onBusy={setBusy} onCreated={w=>{remember(w);setBaseline(w.id);setProposed("");setDecision("");setView("setup");}}/><div className={styles.labIntro}><div><h3>Your saved plans & decisions</h3><p>Resume an option with its original starting plan, or review completed comparisons below.</p></div></div><div>{planFamilies(data.workspaces).map(family=><section key={family.id} aria-label={`${family.name} plan family`}><h3>{family.name}</h3><p>Starting figures, related options and recovered versions. Each comparison keeps its immediate starting plan.</p><div className={styles.decisionGrid}>{family.plans.map(w=><article className={styles.savedDecision} key={w.id}><span className={styles.eyebrow}>{w.archived?"ARCHIVED":w.parent_id?"DECISION OPTION":"STARTING FIGURES"}</span><h3>{w.name}</h3><p>{new Date(w.updated_at).toLocaleDateString()} · revision {w.revision}</p><div className={styles.actions}>{!w.archived&&(w.parent_id?<WorkButton type="submit" disabled={busy||!active.some(p=>p.id===w.parent_id)} onClick={()=>navigate("compare",()=>{setBaseline(w.parent_id!);setProposed(w.id);setDecision("");setRunId("");})}>Resume comparison</WorkButton>:<WorkButton type="submit" disabled={busy} onClick={()=>navigate("figures",()=>{setBaseline(w.id);setDecision("");setProposed("");})}>Review figures</WorkButton>)}<WorkButton type="submit" disabled={busy} onClick={()=>perform(async()=>{await request(`/workspaces/${w.id}/archive`,"POST",{revision:w.revision});await reload();})}>{w.archived?"Restore":"Archive"}</WorkButton></div>{w.parent_id&&!active.some(p=>p.id===w.parent_id)&&<small>Restore the starting plan to resume this comparison.</small>}<LabVersionHistory plan={w} request={request} onCreated={remember} onBusy={setBusy} busy={busy}/></article>)}</div></section>)}</div></>}
   <LabAnalysis key={`${view==="saved"?"history":`${baseline}:${proposed}`}:${editorRevision}`} plans={data.workspaces} request={request} reload={reload} onDirty={setDirty} onBusy={setBusy} initialBaseline={view==="compare"?baseline:undefined} initialProposed={view==="compare"?proposed:undefined} historyOnly={view==="saved"} onRun={setRunId}/>
   {view==="compare"&&<div className={styles.actions}><WorkButton type="submit" disabled={busy} onClick={()=>navigate("figures")}>Review starting figures</WorkButton><WorkButton type="submit" disabled={busy} onClick={()=>navigate("explore")}>Explore another decision</WorkButton></div>}</>}
  {view==="reviews"&&<><label>Dealership model<WorkSelect value={baseline} disabled={busy||dirty} onChange={e=>setBaseline(e.target.value)}><option value="">Choose a saved plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label>{source?<LabPeriodReviews key={`${source.id}:${source.revision}:${editorRevision}`} plan={source} request={request} onDirty={setDirty} onBusy={setBusy}/>:<p>Choose a saved plan first.</p>}</>}
  {view==="reports"&&<><label>Plan for these reports<WorkSelect value={baseline} onChange={e=>{const selected=e.target.value;navigate("reports",()=>setBaseline(selected));}}><option value="">Choose a plan</option>{active.map(w=><option key={w.id} value={w.id}>{w.name}</option>)}</WorkSelect></label><LabReports key={`${baseline}:${editorRevision}`} plan={source} request={request} onDirty={setDirty} onBusy={setBusy} onCreated={reload} onOpenOption={id=>navigate("setup",()=>setBaseline(id))}/></>}
  {(view==="compare"||view==="saved")&&runId&&<div className={styles.actions}><WorkButton type="submit" disabled={busy} onClick={()=>navigate("notebooks")}>Create Success Workbook from this comparison</WorkButton><WorkButton type="submit" disabled={busy} onClick={()=>navigate("procedures")}>Create procedure from this comparison</WorkButton></div>}
  {(view==="notebooks"||view==="procedures")&&<LabNotebooks key={`${view}:${editorRevision}`} fixedKind={view==="procedures"?"procedure":"workbook"} request={request} onDirty={setDirty} onBusy={setBusy} initialRunId={runId}/>}
  {view==="compare"&&option&&<p className={styles.labFootnote}>Comparing {source?.name} with {option.name}. Changes here do not update staffing, advertising or other operational records.</p>}
 </section>;
}
