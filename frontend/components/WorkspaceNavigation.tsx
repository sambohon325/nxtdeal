"use client";
import { useEffect, useId, useState } from "react";
import { WorkspaceIcon } from "./WorkspaceIcon";
import { groupNavigation, type NavigationItem } from "@/lib/workspaceNavigation";
export function WorkspaceNavigation({department,items,active,onSelect}:{department:string;items:NavigationItem[];active?:string;onSelect?:(key:string)=>void}) {
 const groups=groupNavigation(department,items);
 const [open,setOpen]=useState<string|null>(null);
 const [query,setQuery]=useState("");
 const id=useId();
 useEffect(()=>{setOpen(null);setQuery("");},[department]);
 const currentGroup=groups.find(group=>group.items.some(item=>item.key===active))?.label;
 useEffect(()=>{if(currentGroup)setOpen(currentGroup);},[currentGroup]);
 return <nav className="workflow-groups" aria-label={`${department} workflow groups`}>{groups.map((group,index)=>{
 const expanded=open===group.label;
 const matches=group.items.filter(item=>`${item.label} ${item.description||""}`.toLowerCase().includes(query.toLowerCase()));
 return <div className="workflow-group" key={group.label}>
 <button className="workflow-group-toggle" title={group.label} aria-expanded={expanded} aria-controls={`${id}-${index}`} data-current={group.items.some(item=>item.key===active)} onClick={()=>{setQuery("");setOpen(expanded?null:group.label);}}><WorkspaceIcon name={group.label}/><span>{group.label}</span><b aria-hidden="true">{expanded?"⌄":"›"}</b></button>
 <div id={`${id}-${index}`} className="workflow-inline" hidden={!expanded}>
 {group.items.length>6&&<label className="workflow-search">Find a tool<input type="search" aria-label={`Find ${group.label} tools`} placeholder="Filter this group…" value={expanded?query:""} onChange={event=>setQuery(event.target.value)}/></label>}
 <nav aria-label={`${group.label} destinations`}>{(expanded?matches:group.items).map(item=><button className="workflow-destination" key={item.key} aria-current={active===item.key?"page":undefined} title={item.description} onClick={()=>{item.onSelect ? item.onSelect() : onSelect?.(item.key);}}><span className="destination-label">{["vin","knowledge","help","apps"].includes(item.key)&&<WorkspaceIcon name={item.key}/>}<span>{item.label}</span></span></button>)}</nav>
 {expanded&&!matches.length&&<p role="status">No matching tools.</p>}
 </div></div>;
 })}</nav>;
}
