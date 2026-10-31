"use client";
import { WorkButton, WorkInput, WorkTextarea, WorkSelect } from "./WorkspaceUi";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { saveWebsiteStudio, getWebsiteStudioInventory, submitWebsite, startWebsiteDraft, type Website } from "@/lib/websites";
import { uploadMedia } from "@/lib/mediaLibrary";
import { API_BASE } from "@/lib/api";
import catalogue from "@/lib/websiteStudioCatalogue.json";
import backgrounds from "@/lib/websiteBackgroundGallery.json";
import styles from "./LoneStarCustomizer.module.css";

import approvedTemplates from "@/lib/approvedWebsiteTemplates.json";
const art = "/website-studio/assets/";
const imageSource=(url:string)=>url.startsWith("/public/media-library/")?API_BASE+url:url;
export const loneStarDefaults = {
  name: "Lone Star Auto", headline: "Big plans.\nMeet your next truck.",
  intro: "Find the truck, SUV, or everyday car that fits your life. Explore your options with a local team.",
  story: "A dealership’s story starts with its people. Use this space to share how your business began, the community you serve, and what customers can expect when they walk through your doors.",
  hero: art + "lone-star-truck-hero.png", teamPhoto: art + "lone-star-about-team.png",
  locations: [{ id: "main", name: "Lone Star Auto", address: "123 Main Street · Your City", phone: "(555) 010-2026", hours: "Monday–Friday · 9 AM–6 PM\nSaturday · 10 AM–4 PM\nSunday · Closed" }],
  socials: {} as Record<string, string>, backgrounds: {} as Record<string, string>,
  event: { template: "fall", enabled: true, bannerEnabled: true, title: "Fall Truck Event · Find your next adventure", titleEs: "Evento de otoño · Encuentra tu próxima aventura", summary: "Explore our featured trucks and talk with the Lone Star team about your next move.", summaryEs: "Explora nuestras camionetas destacadas y habla con el equipo de Lone Star sobre tu próximo paso.", terms: "Sample event for this design preview. No discount or financing offer is implied. Confirm availability and terms with the dealership.", termsEs: "Evento de ejemplo. No implica descuentos ni ofertas de financiamiento. Confirma la disponibilidad y los términos con el concesionario.", start: "", end: "", target: "type", bodyType: "Truck", banner: "", event: "" },
};
export type ServiceCoupon = {id:string;enabled:boolean;title:string;titleEs:string;summary:string;summaryEs:string;terms:string;termsEs:string;code:string;start:string;end:string};
export type LoneStarConfig = typeof loneStarDefaults & {coupons?:ServiceCoupon[]};
type Config = LoneStarConfig;
type Panel = "business" | "photos" | "offers" | "socials";
const panels: {id: Panel; name: string; glyph: string; jump: string}[] = [
  {id:"business",name:"Your business",glyph:"01",jump:"main"}, {id:"photos",name:"Photos",glyph:"02",jump:"main"},
  {id:"offers",name:"Offers",glyph:"03",jump:"promotions"}, {id:"socials",name:"Social links",glyph:"04",jump:"contact"},
];
function Field({label,children}: {label:string;children:ReactNode}) { return <label className={styles.field}><span>{label}</span>{children}</label>; }

/** The approved template, embedded in the authenticated Website board. */
export function LoneStarCustomizer({website,onWebsiteChange,onDirtyChange}: {website?:Website;onWebsiteChange?:(site:Website)=>void;onDirtyChange?:(dirty:boolean)=>void} = {}) {
  const themeId=website?.studio_config?.theme_id||"lone-star";
  const template=approvedTemplates[themeId as keyof typeof approvedTemplates]||approvedTemplates["lone-star"];
  const templateDefaults:Config=themeId==="lone-star"?loneStarDefaults:{...loneStarDefaults,...template.defaults,backgrounds:{},locations:[{...loneStarDefaults.locations[0],name:template.defaults.name}],event:{...loneStarDefaults.event,summary:"Explore our featured vehicles and talk with our team about your next move.",summaryEs:"Explora nuestros vehículos destacados y habla con nuestro equipo sobre tu próximo paso."}};
  const saved = website?.studio_config?.approved_template || website?.studio_config?.lone_star || templateDefaults;
  const [config,setConfig]=useState<Config>(saved);
  const [baseline,setBaseline]=useState(website&&!website.studio_config?.lone_star&&!website.studio_config?.approved_template?"":JSON.stringify(saved));
  const [busy,setBusy]=useState(false);
  const [inventory,setInventory]=useState<unknown[]|null>(null);
  const [inventoryError,setInventoryError]=useState("");
  const [inventoryVersion,setInventoryVersion]=useState(0);
  const dirty=JSON.stringify(config)!==baseline;
  const editable=!website||["draft","rejected"].includes(website.status);
  useEffect(()=>{onDirtyChange?.(dirty);},[dirty,onDirtyChange]);
  useEffect(()=>{if(!dirty)return;const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue="";};window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);},[dirty]);
  useEffect(()=>{if(!website)return;let active=true;setInventory(null);setInventoryError("");getWebsiteStudioInventory(website.id).then(rows=>{if(active)setInventory(rows);}).catch(error=>{if(active)setInventoryError(error.message);});return()=>{active=false;};},[website?.id,inventoryVersion]);
  async function save(){if(!website||busy)return;setBusy(true);setNotice("");try{const next=await saveWebsiteStudio(website.id,{...(website.studio_config||{version:1 as const,theme_id:"lone-star",language:"en" as const,social_links:{},backgrounds:{},events:[]}),[themeId==="lone-star"?"lone_star":"approved_template"]:config},website.studio_revision||0);setBaseline(JSON.stringify(config));onWebsiteChange?.(next);setNotice("Your changes are saved.");}catch(error){setNotice(error instanceof Error?error.message:"Unable to save. Your edits are still here.");}finally{setBusy(false);}}
  async function review(){if(!website||dirty||busy)return;setBusy(true);try{onWebsiteChange?.(await submitWebsite(website.id));setNotice("Submitted for approval.");}catch(error){setNotice(String(error));}finally{setBusy(false);}}
  async function newDraft(){if(!website)return;setBusy(true);try{onWebsiteChange?.(await startWebsiteDraft(website.id));}catch(error){setNotice(String(error));}finally{setBusy(false);}}

  const [panel,setPanel]=useState<Panel>("business");
  const [device,setDevice]=useState<"desktop"|"mobile">("desktop");
  const [language,setLanguage]=useState("en");
  const [wide,setWide]=useState(false);
  const [ready,setReady]=useState(false);
  const [size,setSize]=useState({width:900,height:720});
  const [gallery,setGallery]=useState<string|null>(null);
  const [photoGroup,setPhotoGroup]=useState("All");
  const [notice,setNotice]=useState("");
  const frame=useRef<HTMLIFrameElement>(null),stage=useRef<HTMLDivElement>(null);
  const latest=useRef(config);latest.current=config;
  function send(payload: Record<string,unknown>) { frame.current?.contentWindow?.postMessage({channel:"nxt-lone-star-review",...payload},"*"); }
  useEffect(()=>{const listener=(event:MessageEvent)=>{if(event.source===frame.current?.contentWindow&&event.data?.channel==="nxt-lone-star-review"&&event.data.ready){setReady(true);send({config:latest.current,connected:!!website,inventory,apiBase:API_BASE});}};window.addEventListener("message",listener);return()=>window.removeEventListener("message",listener);},[website?.id,inventory]);
  useEffect(()=>{if(ready)send({config:{...config,locations:config.locations.filter(location=>location.name.trim())},connected:!!website,inventory,apiBase:API_BASE});},[config,ready,inventory,website?.id]);
  useEffect(()=>{if(!stage.current)return;const observer=new ResizeObserver(([entry])=>setSize({width:entry.contentRect.width,height:entry.contentRect.height}));observer.observe(stage.current);return()=>observer.disconnect();},[]);
  const scale=Math.min(1,(size.width-32)/(device==="desktop"?1440:390));
  function patch(value:Partial<Config>){if(!editable)return;setConfig(current=>({...current,...value}));}
  function eventPatch(value:Partial<Config["event"]>){if(!editable)return;setConfig(current=>({...current,event:{...current.event,...value}}));}
  function locationPatch(index:number,key:string,value:string){if(!editable)return;setConfig(current=>({...current,locations:current.locations.map((location,i)=>i===index?{...location,[key]:value}:location)}));}
  function photo(target:string,url:string){if(target==="hero"||target==="teamPhoto")patch({[target]:url});else if(target==="banner"||target==="event")eventPatch({[target]:url});else patch({backgrounds:{...config.backgrounds,[target]:url}});setGallery(null);send({jump:target==="teamPhoto"?"team":target==="hero"?"main":target==="banner"||target==="event"?"promotions":target});}
  async function upload(file:File|undefined,target:string){if(!file||!editable)return;setNotice("");if(website){try{const result=await uploadMedia(file,file.name,"general");photo(target,result.image.url);}catch(error){setNotice(error instanceof Error?error.message:"Upload failed");}return;}if(!["image/jpeg","image/png","image/webp"].includes(file.type)||file.size>2*1024*1024){setNotice("Choose a JPG, PNG or WebP image under 2 MB for this preview.");return;}const url=await new Promise<string>((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=reject;reader.readAsDataURL(file);});photo(target,url);}
  function selectEvent(id:string){const item=catalogue.events.find(event=>event.id===id);if(!item)return;eventPatch({template:id,title:item.name+" · "+item.title,titleEs:item.nameEs+" · "+item.titleEs,summary:item.summary,summaryEs:item.summaryEs,terms:item.terms,termsEs:item.termsEs,banner:"",event:""});}
  const event=catalogue.events.find(item=>item.id===config.event.template)!;
  return <section aria-label="Website customization" className={`${styles.app} ${website?styles.embedded:""}`}>
    {!website&&<header className={styles.topbar}><div className={styles.wordmark}><span>NXT</span>Deal<span className={styles.divider}>/</span><span className={styles.breadcrumb}>Marketing <b>›</b> Content <b>›</b> Website</span></div><span className={styles.reviewPill}><i/>Lone Star review</span></header>}
    <div className={styles.titlebar}><div><p>YOUR WEBSITE</p><h1>{website?`Customize ${template.name}`:"A finished design. Make it yours."}</h1><span>Your {template.name} website, with all the details that make it your dealership.</span></div><div className={styles.actions}>{website&&<><span className={styles.status}>{dirty?"Unsaved changes":website.status.replaceAll("_"," ")}</span>{editable?<><WorkButton type="submit" variant="primary" className={styles.primary} disabled={busy||!dirty} onClick={()=>void save()}>Save changes</WorkButton><details className={styles.moreActions}><summary aria-label="More website actions">More <span aria-hidden="true">⌄</span></summary><div><WorkButton type="submit" disabled={busy||dirty||!website.studio_config?.lone_star&&!website.studio_config?.approved_template} onClick={()=>void review()}>Submit for approval</WorkButton><WorkButton type="submit" disabled={busy||!dirty} onClick={()=>{setConfig(saved);setBaseline(JSON.stringify(saved));}}>Discard changes</WorkButton></div></details></>:website.status==="published"?<WorkButton type="submit" disabled={busy} onClick={()=>void newDraft()}>Edit website</WorkButton>:null}</>}<WorkButton type="submit" className={styles.previewAction} onClick={()=>setWide(!wide)}>{wide?"Back to customization":"Preview website"}<span>↗</span></WorkButton></div></div>
    <div className={`${styles.workspace} ${wide?styles.wide:""}`}>
      <aside className={styles.sidebar} hidden={wide}>
        <div className={styles.design}><img src={templateDefaults.hero} alt={`${template.name} design`}/><div><strong>{template.name}</strong><span>Approved dealership design</span></div><span className={styles.check}>✓</span></div>
        <nav className={styles.tabs} aria-label={`Customize ${template.name}`}>{panels.map(item=><WorkButton type="submit" key={item.id} aria-pressed={panel===item.id} onClick={()=>{setPanel(item.id);send({jump:item.jump});}}>{item.name}</WorkButton>)}</nav>
        <fieldset disabled={!editable||busy} className={styles.settings}>
          {panel==="business"&&<><h2>Let’s make it yours.</h2><p>Add your details. The design is already taken care of.</p>
            <Field label="Dealership name"><WorkInput value={config.name} onChange={event=>patch({name:event.target.value})}/></Field>
            <Field label="Your headline"><WorkTextarea rows={2} value={config.headline} onChange={event=>patch({headline:event.target.value})}/></Field>
            <Field label="A short introduction"><WorkTextarea rows={3} value={config.intro} onChange={event=>patch({intro:event.target.value})}/></Field>
            <details className={styles.detail}><summary>Your story</summary><Field label="About your dealership"><WorkTextarea rows={6} value={config.story} onFocus={()=>send({jump:"team"})} onChange={event=>patch({story:event.target.value})}/></Field></details>
            <details className={styles.detail}><summary>Locations & hours <small>{config.locations.length} location{config.locations.length!==1?"s":""}</small></summary>{config.locations.map((location,index)=><div className={styles.location} key={location.id}><strong>Location {index+1}</strong>{(["name","address","phone","hours"] as const).map(key=><Field key={key} label={key==="name"?"Location name":key[0].toUpperCase()+key.slice(1)}>{key==="hours"?<WorkTextarea rows={3} value={location[key]} onChange={event=>locationPatch(index,key,event.target.value)}/>:<WorkInput value={location[key]} onChange={event=>locationPatch(index,key,event.target.value)}/>}</Field>)}{index>0&&<WorkButton type="submit" onClick={()=>patch({locations:config.locations.filter((_,i)=>i!==index)})}>Remove location</WorkButton>}</div>)}<WorkButton type="submit" className={styles.secondary} onClick={()=>patch({locations:[...config.locations,{id:crypto.randomUUID(),name:"Additional location",address:"",phone:"",hours:""}]})}>+ Add another location</WorkButton></details>
            <div className={styles.included}><strong>Already part of your website</strong><p>Inventory & vehicle details · Payment shopping · Financing · Trade-in · Service · About us · Events · Contact forms · English / Spanish · Privacy & terms</p><span>Keep the full experience. No page building required.</span></div>
          </>}
          {panel==="photos"&&<><h2>Set the scene.</h2><p>Keep the approved photos, explore the gallery, or use your own.</p>{[{id:"hero",name:"Main hero photo",url:config.hero},{id:"teamPhoto",name:"Your dealership team",url:config.teamPhoto},{id:"trade",name:"Trade-in background",url:config.backgrounds.trade||art+"scene-desert.png"},{id:"contact",name:"Contact background",url:config.backgrounds.contact||art+"lone-star-truck-hero.png"}].map(item=><div className={styles.photo} key={item.id}><strong>{item.name}</strong><img src={imageSource(item.url)} alt={item.name}/><div><WorkButton type="submit" onClick={()=>setGallery(item.id)}>Browse gallery</WorkButton><label className={styles.upload}>Upload your own<WorkInput type="file" accept="image/png,image/jpeg,image/webp" onChange={event=>void upload(event.target.files?.[0],item.id)}/></label></div></div>)}</>}
          {panel==="offers"&&<><h2>A reason to stop by.</h2><p>Your seasonal artwork, offer details and featured vehicles—together.</p><label className={styles.toggle}><span>Show this event</span><WorkInput type="checkbox" checked={config.event.enabled} onChange={event=>eventPatch({enabled:event.target.checked})}/></label>
            <Field label="Choose a season or event"><WorkSelect value={event.id} onChange={event=>selectEvent(event.target.value)}>{catalogue.events.map(item=><option value={item.id} key={item.id}>{item.name}</option>)}</WorkSelect></Field>
            <img className={styles.eventArt} src={imageSource(config.event.event||event.image)} alt={event.imageAlt}/>
            <div className={styles.pair}><WorkButton type="submit" onClick={()=>setGallery("event")}>Change event photo</WorkButton><label className={styles.upload}>Upload banner<WorkInput type="file" accept="image/png,image/jpeg,image/webp" onChange={event=>void upload(event.target.files?.[0],"banner")}/></label></div>
            <label className={styles.toggle}><span>Show banner above navigation</span><WorkInput type="checkbox" checked={config.event.bannerEnabled} onChange={event=>eventPatch({bannerEnabled:event.target.checked})}/></label>
            <Field label="Headline"><WorkTextarea rows={2} value={config.event.title} onChange={event=>eventPatch({title:event.target.value})}/></Field>
            <Field label="Offer details"><WorkTextarea rows={3} value={config.event.summary} onChange={event=>eventPatch({summary:event.target.value})}/></Field>
            <div className={styles.pair}><Field label="Starts"><WorkInput type="date" value={config.event.start} onChange={event=>eventPatch({start:event.target.value})}/></Field><Field label="Ends"><WorkInput type="date" value={config.event.end} onChange={event=>eventPatch({end:event.target.value})}/></Field></div>
            <Field label="Vehicles included"><WorkSelect value={config.event.target==="all"?"all":config.event.bodyType} onChange={event=>eventPatch(event.target.value==="all"?{target:"all"}:{target:"type",bodyType:event.target.value})}><option value="all">All available vehicles</option><option>Truck</option><option>SUV</option><option>Coupe</option></WorkSelect></Field>
            <details className={styles.detail}><summary>Spanish copy & offer terms</summary><Field label="Spanish headline"><WorkTextarea value={config.event.titleEs} onChange={event=>eventPatch({titleEs:event.target.value})}/></Field><Field label="Spanish details"><WorkTextarea value={config.event.summaryEs} onChange={event=>eventPatch({summaryEs:event.target.value})}/></Field><Field label="Offer terms"><WorkTextarea value={config.event.terms} onChange={event=>eventPatch({terms:event.target.value})}/></Field><Field label="Spanish offer terms"><WorkTextarea value={config.event.termsEs} onChange={event=>eventPatch({termsEs:event.target.value})}/></Field></details>
          </>}
          {panel==="offers"&&<section><h2>Service coupons</h2><p>Published, active coupons also appear in Sales / BDC and My Garage.</p>{(config.coupons||[]).map((coupon,index)=><details className={styles.detail} key={coupon.id}><summary>{coupon.title || `Coupon ${index+1}`}</summary><label className={styles.toggle}><span>Show coupon</span><WorkInput type="checkbox" checked={coupon.enabled} onChange={e=>patch({coupons:config.coupons!.map(c=>c.id===coupon.id?{...c,enabled:e.target.checked}:c)})}/></label>{([["title","Coupon title"],["summary","Offer / discount details"],["code","Coupon code"],["terms","Terms & eligibility"],["titleEs","Spanish title"],["summaryEs","Spanish details"],["termsEs","Spanish terms"],["start","Valid from"],["end","Valid through"]] as const).map(([key,label])=><Field label={label} key={key}><WorkInput type={key==="start"||key==="end"?"date":"text"} value={coupon[key]} onChange={e=>patch({coupons:config.coupons!.map(c=>c.id===coupon.id?{...c,[key]:e.target.value}:c)})}/></Field>)}<WorkButton type="submit" onClick={()=>patch({coupons:config.coupons!.filter(c=>c.id!==coupon.id)})}>Remove coupon</WorkButton></details>)}<WorkButton type="submit" disabled={(config.coupons||[]).length>=30} onClick={()=>patch({coupons:[...(config.coupons||[]),{id:crypto.randomUUID(),enabled:false,title:"New service coupon",titleEs:"",summary:"",summaryEs:"",terms:"",termsEs:"",code:"",start:"",end:""}]})}>+ Add service coupon</WorkButton></section>}
          {panel==="socials"&&<><h2>Stay connected.</h2><p>Your links appear beside the contact form, in colors that match {template.name}.</p>{["Facebook","Instagram","YouTube","TikTok","X","LinkedIn","Threads","Pinterest","Snapchat","WhatsApp"].map(name=><Field key={name} label={name}><WorkInput type="url" placeholder="https://" value={config.socials[name]||""} onChange={event=>patch({socials:{...config.socials,[name]:event.target.value}})}/></Field>)}</>}
          {notice&&<p role="alert">{notice}</p>}
        </fieldset><footer className={styles.sidebarFooter}><i/>Changes appear in the preview instantly.</footer>
      </aside>
      <section className={styles.preview} aria-label={`Finished ${template.name} website`}>
        <div className={styles.previewbar}>
          <div className={styles.previewTitle}><span className={styles.liveDot}/><strong>Live preview</strong>{website&&<WorkButton type="submit" className={styles.refresh} title="Refresh dealership inventory" aria-label="Refresh dealership inventory" onClick={()=>setInventoryVersion(v=>v+1)}>↻</WorkButton>}</div>
          <div className={styles.viewControls}>
            <div className={styles.deviceToggle} role="group" aria-label="Preview size"><WorkButton type="submit" aria-pressed={device==="desktop"} onClick={()=>setDevice("desktop")}>Desktop</WorkButton><WorkButton type="submit" aria-pressed={device==="mobile"} onClick={()=>setDevice("mobile")}>Mobile</WorkButton></div>
            <WorkSelect aria-label="Preview language" value={language} onChange={event=>{setLanguage(event.target.value);send({language:event.target.value});}}><option value="en">EN</option><option value="es">ES</option></WorkSelect>
            <WorkSelect aria-label="Jump to website section" defaultValue="" onChange={event=>send({jump:event.target.value})}><option value="" disabled>Jump to…</option>{[["main","Home"],["inventory","Inventory"],["payment-shop","Payments"],["team","About us"],["service","Service"],["promotions","Offers"],["contact","Contact"]].map(([id,label])=><option key={id} value={id}>{label}</option>)}</WorkSelect>
          </div>
        </div>
        {inventoryError&&<p role="alert">{inventoryError} <WorkButton type="submit" onClick={()=>setInventoryVersion(v=>v+1)}>Retry inventory</WorkButton></p>}<div className={styles.stage} ref={stage}><div style={{width:(device==="desktop"?1440:390)*scale,height:Math.max(300,size.height-24)}}><iframe key={website?inventoryVersion:0} ref={frame} title={`Complete approved ${template.name} website`} src={website?`${template.path}/connected.html`:"/website-studio/lone-star-preview/lone-star-review.html"} sandbox="allow-scripts allow-forms" style={{width:device==="desktop"?1440:390,height:Math.max(300,(size.height-24)/scale),transform:`scale(${scale})`,transformOrigin:"top left"}}/></div>{!ready&&<span className={styles.loading}>Opening your {template.name} website…</span>}</div>
        <footer className={styles.previewFooter}>{website?"Saved to your dealership website. Preview inquiries are disabled. Publishing requires approval.":"Design review only. No live records are changed."}</footer>
      </section>
    </div>
    {gallery&&<div className={styles.modalBackdrop}><section className={styles.modal} role="dialog" aria-modal="true" aria-label="Choose a photo"><header><div><h2>Find your setting.</h2><p>Choose from the shared gallery.</p></div><WorkButton type="submit" onClick={()=>setGallery(null)}>Close ×</WorkButton></header><WorkSelect aria-label="Photo collection" value={photoGroup} onChange={event=>setPhotoGroup(event.target.value)}>{["All",...new Set(backgrounds.map(item=>item.category))].map(value=><option key={value}>{value}</option>)}</WorkSelect><div className={styles.gallery}>{backgrounds.filter(item=>photoGroup==="All"||item.category===photoGroup).map(item=><WorkButton type="submit" key={item.id} onClick={()=>photo(gallery,item.url)}><img src={imageSource(item.url)} alt={item.name}/><span>{item.name}</span></WorkButton>)}</div></section></div>}
  </section>;
}

