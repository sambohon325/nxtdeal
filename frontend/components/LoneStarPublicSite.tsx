"use client";
import { useEffect, useRef, useState } from "react";
import { publicWebsiteInventory, publicSubmitContactForm, type Website } from "@/lib/websites";
import { PublicChatWidget } from "./PublicChatWidget";
import approvedTemplates from "@/lib/approvedWebsiteTemplates.json";
import { API_BASE } from "@/lib/api";

/** Actual public Lone Star page; approved config only, canonical stock and CRM. */
export function LoneStarPublicSite({site}: {site:Website}) {
  const frame=useRef<HTMLIFrameElement>(null);
  const [stock,setStock]=useState<Record<string,unknown>[]|null>(null);
  const [error,setError]=useState("");
  const [attempt,setAttempt]=useState(0);
  const [ready,setReady]=useState(false);
  const config=(site.studio_config!.approved_template||site.studio_config!.lone_star)!;
  const themeId=site.studio_config!.theme_id;
  const template=approvedTemplates[themeId as keyof typeof approvedTemplates]||approvedTemplates["lone-star"];
  useEffect(()=>{const abort=new AbortController();setError("");setStock(null);(async()=>{const rows=new Map<string,Record<string,unknown>>();let page=1,pages=1;do{const result=await publicWebsiteInventory(site.id,new URLSearchParams({page:String(page),page_size:"48"}),abort.signal);result.vehicles.forEach(v=>rows.set(String(v.id),v));pages=result.pages;page++;}while(page<=pages);if(!abort.signal.aborted)setStock([...rows.values()]);})().catch(e=>{if(!abort.signal.aborted)setError(e.message);});return()=>abort.abort();},[site.id,attempt]);
  useEffect(()=>{const listener=async(event:MessageEvent)=>{
    if(event.source!==frame.current?.contentWindow||event.data?.channel!=="nxt-lone-star-review")return;
    if(event.data.ready)setReady(true);
    if(event.data.activity)window.dispatchEvent(new CustomEvent("nxt-website-activity",{detail:{site:site.id,event:event.data.activity.event,page:event.data.activity.page}}));
    if(event.data.inquiry){
      const requestId=event.data.requestId;
      let result;
      try{
        const index=site.pages.contact?.sections.findIndex(section=>section.section_key==="contact_form")??-1;
        if(index<0)throw Error("This website's contact form is unavailable.");
        const input=event.data.inquiry;
        result=await publicSubmitContactForm(site.id,{page_key:"contact",section_index:index,name:input.name,email:input.email,phone:input.phone,message:input.message,vehicle_id:input.vehicle_id,intent:input.intent,request_id:input.request_id});
      }catch(e){result={error:e instanceof Error?e.message:"Unable to send. Please retry."};}
      frame.current?.contentWindow?.postMessage({channel:"nxt-lone-star-review",requestId,result},"*");
    }
  };window.addEventListener("message",listener);return()=>window.removeEventListener("message",listener);},[site]);
  useEffect(()=>{if(ready&&stock)frame.current?.contentWindow?.postMessage({channel:"nxt-lone-star-review",config,inventory:stock,connected:true,public:true,apiBase:API_BASE},"*");},[ready,stock,config]);
  if(error)return <main role="alert">Inventory could not load: {error} <button onClick={()=>setAttempt(v=>v+1)}>Try again</button></main>;
  return <><PublicChatWidget theme={themeId} websiteId={site.id} siteName={config.name||site.name}/><iframe ref={frame} title={config.name||site.name} sandbox="allow-scripts allow-forms" src={`${template.path}/connected.html`} style={{border:0,width:"100%",height:"100dvh",display:"block"}}/>{!stock&&<p role="status">Loading dealership inventory…</p>}</>;
}
