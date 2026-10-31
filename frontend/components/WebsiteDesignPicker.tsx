"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";
import { useEffect, useRef, useState } from "react";
import library from "@/lib/websiteStudioCatalogue.json";
import styles from "./WebsiteDesignPicker.module.css";

export function WebsiteDesignPicker({value,disabled,onSelect}:{value:string;disabled:boolean;onSelect:(id:string)=>void}) {
 const [viewing,setViewing]=useState(value),[device,setDevice]=useState<"desktop"|"mobile">("desktop"),[expanded,setExpanded]=useState(false),[query,setQuery]=useState("");
 const dialog=useRef<HTMLDialogElement>(null),stage=useRef<HTMLDivElement>(null),opener=useRef<HTMLButtonElement>(null);
 const [width,setWidth]=useState(720),[height,setHeight]=useState(590),[section,setSection]=useState("main");
 const current=library.themes.find(t=>t.id===viewing)||library.themes[0];
 const choices=library.themes.filter(t=>t.name.toLowerCase().includes(query.toLowerCase()));
 useEffect(()=>{if(!expanded)return;const d=dialog.current;d?.showModal();const previous=document.body.style.overflow;document.body.style.overflow="hidden";return()=>{d?.close();document.body.style.overflow=previous;opener.current?.focus();};},[expanded]);
 useEffect(()=>{const el=stage.current;if(!el)return;const observer=new ResizeObserver(([entry])=>{setWidth(entry.contentRect.width);setHeight(entry.contentRect.height);});observer.observe(el);return()=>observer.disconnect();},[expanded]);
 const frameWidth=device==="mobile"?390:1440,scale=Math.min(1,Math.max(240,width-24)/frameWidth);
 const content=<>
  <header><div><h3 id={expanded?"design-preview-title":undefined}>Choose your website design</h3><p>Browse a design, preview it, then choose “Use this design”.</p></div><WorkButton type="submit" ref={expanded?undefined:opener} onClick={()=>setExpanded(!expanded)}>{expanded?"Close preview ✕":"Full screen"}</WorkButton></header>
  <div className={styles.layout}>
   <aside className={styles.choices}><label>Find a design<WorkInput type="search" value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search 20 designs"/></label><div className={styles.gallery} aria-label="Design choices">{choices.map(theme=><button key={theme.id} onClick={()=>setViewing(theme.id)} aria-pressed={viewing===theme.id} className={styles.card}><div className={styles.thumbnail} aria-hidden="true"><iframe title={`${theme.name} thumbnail`} tabIndex={-1} loading="lazy" sandbox="" src={`/website-studio/references/${theme.id}.html`}/></div><span>{theme.name}{value===theme.id&&<small>Selected</small>}</span></button>)}{!choices.length&&<p>No matching designs.</p>}</div></aside>
   <div className={styles.preview}><div className={styles.toolbar}><div><strong>{current.name}</strong><small>Design {library.themes.indexOf(current)+1} of {library.themes.length}</small></div><div role="group" aria-label="Preview device"><WorkButton type="submit" aria-pressed={device==="desktop"} onClick={()=>setDevice("desktop")}>Desktop</WorkButton><WorkButton type="submit" aria-pressed={device==="mobile"} onClick={()=>setDevice("mobile")}>Mobile</WorkButton></div><WorkButton type="submit" disabled={disabled||value===viewing} onClick={()=>{onSelect(viewing);setExpanded(false);}}>{value===viewing?"Selected design":"Use this design"}</WorkButton></div>
    <label className={styles.jump}>Explore a section<WorkSelect aria-label="Explore preview section" value={section} onChange={e=>setSection(e.target.value)}>{[["main","Top / hero"],["inventory","Inventory"],["service","Service"],["promotions","Events"],["team","About us"],["contact","Contact"]].map(([id,name])=><option key={id} value={id}>{name}</option>)}</WorkSelect></label><div className={styles.stage} ref={stage}><iframe key={`${viewing}-${device}`} title={`${current.name} ${device} design reference`} sandbox="" src={`/website-studio/references/${viewing}.html#${section}`} style={{width:frameWidth,height:`${Math.max(200,(height-24)/scale)}px`,zoom:scale}}/></div>
    <div className={styles.footer}><WorkButton type="submit" onClick={()=>setViewing(library.themes[(library.themes.indexOf(current)+library.themes.length-1)%library.themes.length].id)}>← Previous design</WorkButton><span>Scroll inside the website to explore. Sample content; your saved website is unchanged.</span><WorkButton type="submit" onClick={()=>setViewing(library.themes[(library.themes.indexOf(current)+1)%library.themes.length].id)}>Next design →</WorkButton></div>
   </div>
  </div></>;
 return expanded?<dialog ref={dialog} aria-labelledby="design-preview-title" className={`${styles.root} ${styles.expanded}`} onCancel={()=>setExpanded(false)}>{content}</dialog>:<section className={styles.root} aria-label="Website design library">{content}</section>;
}
