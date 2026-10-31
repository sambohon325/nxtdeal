"use client";
import {useState} from "react";
import "./DepartmentDailyNavigation.css";
type Destination={key:string;label:string;onSelect:()=>void};
/** Only receives the signed-in employee's permitted workflow catalog. */
export function DepartmentDailyNavigation({department,items,active}:{department:string;items:Destination[];active?:string}) {
  const [expanded,setExpanded]=useState(false);
  if(!items.length)return null;
  const shown=expanded?items:items.slice(0,4);
  const overflowActive=items.slice(4).some(item=>item.key===active);
  return <nav className="department-daily-navigation" aria-label={`${department} daily work`}>
    <span className="daily-work-label">Daily work</span>
    {shown.map(item=><button key={item.key} className="soft-button" aria-current={active===item.key?"page":undefined} onClick={item.onSelect}>{item.label}</button>)}
    {items.length>4&&<button className="soft-button" aria-expanded={expanded} onClick={()=>setExpanded(value=>!value)}>{expanded?"Fewer shortcuts":overflowActive?`More: ${items.find(item=>item.key===active)?.label}`:"More daily work"}</button>}
  </nav>;
}
