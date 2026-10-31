"use client";
import { WorkButton } from "./../WorkspaceUi";
import {EntityDashPanel} from "../EntityDashPanel";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import dynamic from "next/dynamic";
import type { Session } from "@/lib/auth";
import type { MenuCatalogItem } from "../DepartmentMenuBar";
import { WorkspaceNavigation } from "../WorkspaceNavigation";
import { MenuDashBody } from "../MenuDashPanel";
import { OverviewHeader } from "../DepartmentOverview";
import { crmRequest } from "@/lib/salesCrm";
import { CampaignWorkflow } from "../marketing/CampaignWorkflow";
import { BdcDay } from "./BdcDay";
import { BdcCampaigns } from "./BdcCampaigns";
import styles from "./BdcWorkspace.module.css";
const BdcQueue=dynamic(()=>import("../BdcBoard").then(m=>m.BdcBoard));
const loading=()=> <p role="status">Opening BDC workspace…</p>;
const Crm=dynamic(()=>import("../MarketingCRMBoard").then(m=>m.MarketingCRMBoard),{loading});
const Advanced=dynamic(()=>import("../sales/CrmAdvanced").then(m=>m.CrmAdvanced),{loading});
const Sales=dynamic(()=>import("../sales/SalesCrmWorkspace").then(m=>m.SalesCrmWorkspace),{loading});
const Approvals=dynamic(()=>import("../marketing/MarketingOperations").then(m=>m.MarketingOperations),{loading});
const Conversations=dynamic(()=>import("../OperationsCommunicationsBoard").then(m=>m.OperationsCommunicationsBoard),{loading});
const Appointments=dynamic(()=>import("../AppointmentsBoard").then(m=>m.AppointmentsBoard),{loading});
const ServiceAppointments=dynamic(()=>import("../ServiceAppointmentsBoard").then(m=>m.ServiceAppointmentsBoard),{loading});
const Plans=dynamic(()=>import("../marketing/JourneyPlans").then(m=>m.JourneyPlans),{loading});
const Legacy=dynamic(()=>import("../CampaignsBoard").then(m=>m.CampaignsBoard),{loading});
const destinations=[{key:"inquiries",label:"Incoming inquiries",gates:["sales:overview"]},{key:"campaign_responses",label:"Campaign responses & outcomes",gates:["sales:overview","marketing:campaigns","service:appointments"]},{key:"qualification",label:"Qualify requests",gates:["sales:overview"]},{key:"handoff",label:"Sales handoffs",gates:["sales:overview"]},{key:"scorecard",label:"Response performance",gates:["sales:reporting"]},{key:"import",label:"Import leads",gates:["marketing:lead_import"]},{key:"service_appointments",label:"Service appointments",gates:["service:appointments"]},{key:"today",label:"BDC overview",gates:["sales:overview"]},{key:"conversations",label:"Conversations",gates:["sales:communications","marketing:crm"]},{key:"audiences",label:"Lists & audiences",gates:["marketing:crm","sales:prospects"]},{key:"segments",label:"Live segments",gates:["sales:prospects","marketing:crm"]},{key:"campaigns",label:"Campaigns & follow-ups",gates:["marketing:campaigns","sales:workflows"]},{key:"approvals",label:"Delivery & approvals",gates:["marketing:campaigns","sales:workflows"]},{key:"followups",label:"Scheduled follow-ups",gates:["sales:workflows","marketing:campaigns"]},{key:"tasks",label:"Tasks",gates:["sales:prospects"]},{key:"appointments",label:"Sales appointments",gates:["sales:appointments"]},{key:"results",label:"Results",gates:["sales:reporting","marketing:analytics"]},{key:"plans",label:"Saved journey plans",gates:["marketing:email_sms"]},{key:"legacy_campaigns",label:"Existing campaigns",gates:["marketing:campaigns"]}];
export function bdcDailyDestinations(items:MenuCatalogItem[],role:string){
 const keys=new Set(items.map(i=>i.key));return destinations.filter(d=>["ADMIN","OPERATIONS","SALES","MARKETING","BDC","SERVICE"].includes(role)&&d.gates.some(g=>keys.has(g))&&(d.key!=="service_appointments"||["ADMIN","OPERATIONS","SERVICE"].includes(role))&&(role!=="SERVICE"||(d.key==="service_appointments"||d.key==="campaign_responses")));
}
export function BdcWorkspace({navigationHost,theme,session,items,initialItem,onOpenEntity,onOpenBrand,onDraftOpenChange,onSavingChange}:{navigationHost?:HTMLElement|null;theme:"light"|"dark";session:Session;items:MenuCatalogItem[];initialItem:string;onOpenEntity:(id:string)=>void;onOpenBrand:()=>void;onDraftOpenChange:(v:boolean)=>void;onSavingChange:(v:boolean)=>void}){
 const [active,setActive]=useState(initialItem==="overview"?(session.role==="SERVICE"?"service_appointments":"today"):initialItem),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[pending,setPending]=useState<string|null>(null),[revision,setRevision]=useState(0);
 const [entity,setEntity]=useState<string|null>(null);
 useEffect(()=>{setActive(initialItem==="overview"?(session.role==="SERVICE"?"service_appointments":"today"):initialItem)},[initialItem]);
 useEffect(()=>{onDraftOpenChange(dirty);return()=>onDraftOpenChange(false)},[dirty,onDraftOpenChange]);
 useEffect(()=>{onSavingChange(busy);return()=>onSavingChange(false)},[busy,onSavingChange]);
 const visible=bdcDailyDestinations(items,session.role);
 function select(key:string){if(dirty||busy){setPending(key);return;}setActive(key);}
 const navigation=<WorkspaceNavigation department="BDC" active={active} items={visible} onSelect={select}/>;
 const view=visible.find(v=>v.key===active);
 const salesItems=items.filter(i=>i.key.startsWith("sales:")).map(i=>({...i,key:i.key.slice(6)}));
 const props={onDraftOpenChange:setDirty,onSavingChange:setBusy};
 return <section className={`${styles.workspace} ${theme==="light"?styles.light:""}`} data-department-work="" aria-label="BDC Center">{navigationHost?createPortal(navigation,navigationHost):navigation}<OverviewHeader context={active==="today"?"At a glance":"Workspace"} department="BDC" title={view?.label||"BDC Center"} description="Turn qualifying requests into conversations, appointments and completed handoffs. Marketing plans demand; Sales and Service complete the next customer step."><WorkButton type="submit" onClick={onOpenBrand} disabled={dirty||busy}>Brand & Website</WorkButton></OverviewHeader>
 {pending&&<div role="alert"><p>{busy?"Wait for the save to finish.":"You have unsaved changes. Keep editing or discard them to switch workspaces."}</p><WorkButton type="submit" onClick={()=>setPending(null)}>Keep editing</WorkButton><WorkButton type="submit" disabled={busy} onClick={()=>{setDirty(false);setRevision(v=>v+1);setActive(pending);setPending(null)}}>Discard and continue</WorkButton></div>}
 {!items.length?<p role="status">Loading your available BDC tools…</p>:!view?<p>This BDC tool is unavailable for your current access.</p>:<div key={`${active}:${revision}`} hidden={entity!==null}>
 {active==="campaign_responses"?<CampaignWorkflow {...props} onOpen={setEntity}/>:active==="inquiries"||active==="qualification"||active==="handoff"||active==="scorecard"?<BdcQueue section={active==="inquiries"?"queue":active}/>:active==="service_appointments"?<ServiceAppointments theme={theme}/>:active==="import"?<MenuDashBody {...props} initialTheme={theme} hideNav hideAssistant department="Marketing" itemKey="lead_import" onSelectItem={()=>select("audiences")}/>:active==="campaigns"?<BdcCampaigns {...props} onBrand={onOpenBrand} onFollowups={()=>select("followups")}/>:active==="audiences"?<Crm {...props} theme={theme} embedded initialTab="lists"/>:active==="segments"||active==="followups"?<Advanced {...props} activityOnly={active==="followups"} mode={active==="segments"?"segments":"sequences"} employeeId={session.employeeId} role={session.role} onOpen={setEntity}/>:active==="approvals"?<Approvals {...props} mode="communications" canEdit={["ADMIN","MARKETING"].includes(session.role)}/>:active==="conversations"?<Conversations theme={theme}/>:active==="appointments"?<Appointments theme={theme} onOpenCustomer={setEntity}/>:active==="plans"?<><p>These are your existing planning drafts. They do not send messages. Use Campaigns & follow-ups to schedule outreach.</p><Plans {...props} canEdit={["ADMIN","MARKETING"].includes(session.role)}/></>:active==="legacy_campaigns"?<Legacy {...props} theme={theme}/>:active==="results"?<Results/>:<>{active==="today"?<BdcDay available={new Set(visible.map(v=>v.key))} onSelect={select}/>:<Sales compact theme={theme} session={session} items={salesItems} initialItem={active==="today"?"overview":"tasks"} onOpenEntity={setEntity} onOpenBdc={key=>{if(key!==active)select(key)}}/>}</>}
 </div>}{entity&&<EntityDashPanel theme={theme} entityId={entity} onClose={()=>setEntity(null)} onPopOut={()=>onOpenEntity(entity)}/>}</section>
}
function Results(){
 const [data,setData]=useState<{messages:Record<string,number>;followups:Record<string,number>;attribution:string}|null>(null),[error,setError]=useState("");
 useEffect(()=>{crmRequest<{messages:Record<string,number>;followups:Record<string,number>;attribution:string}>("/bdc/results").then(setData).catch(e=>setError(e.message))},[]);
 return error?<p role="alert">{error}</p>:!data?<p>Loading recorded outcomes…</p>:<><p>{data.attribution}</p>{[["Messages",data.messages],["Follow-ups",data.followups]].map(([title,counts])=><section className={styles.panel} key={String(title)}><h3>{String(title)}</h3>{Object.entries(counts).map(([key,count])=><p key={key}>{key}: <strong>{count}</strong></p>)}{!Object.keys(counts).length&&<p>No activity recorded yet.</p>}</section>)}<p>Accepted means the provider acknowledged the message. Delivered requires separate delivery evidence.</p></>
}
