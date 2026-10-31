"use client";
import {useCallback,useEffect,useRef,useState} from "react";
import {getAlertFeed,type Alert} from "@/lib/operationsAlerts";
import type {Session} from "@/lib/auth";
import "./HelpWorkspace.css";
import {WorkButton} from "./WorkspaceUi";
import {CollectionPagination,collectionPage} from "./CollectionPagination";

const identity=(alert:Alert)=>`${alert.alert_type}:${alert.source_id}:${alert.severity}:${alert.title}:${alert.detail}`;
/** Reading is personal, device-local state; it never acknowledges a business alert. */
export function WorkspaceNotifications({session,onOpen,onSettings}:{session:Session;onOpen:(id:string)=>void;onSettings:()=>void}) {
 const key=`nxtdeal-notifications:${session.apiBaseUrl}:${session.employeeId}`;
 const [alerts,setAlerts]=useState<Alert[]>([]),[read,setRead]=useState<string[]>([]),[error,setError]=useState(""),[loading,setLoading]=useState(true),[page,setPage]=useState(0),[onlyUnread,setOnlyUnread]=useState(false);
 const dialog=useRef<HTMLDialogElement>(null);
 const load=useCallback(async()=>{setLoading(true);try{const feed=await getAlertFeed();setAlerts(feed.alerts);setError("");}catch{setError("Notifications could not be loaded. Try again.");}finally{setLoading(false);}},[]);
 useEffect(()=>{try{const value=JSON.parse(localStorage.getItem(key)||"[]");setRead(Array.isArray(value)?value.filter(x=>typeof x==="string"):[]);}catch{setRead([]);}void load();const timer=setInterval(()=>{if(document.visibilityState==="visible")void load();},60000);return()=>clearInterval(timer);},[key,load]);
 function markRead(ids:string[]){const next=Array.from(new Set([...read,...ids]));setRead(next);try{localStorage.setItem(key,JSON.stringify(next.slice(-2000)));}catch{/* Reading still works for this session. */}}
 const unread=alerts.filter(a=>!read.includes(identity(a))).length;
 const shown=onlyUnread?alerts.filter(a=>!read.includes(identity(a))):alerts;
 const p=collectionPage(shown.length,page,10);
 return <><button className="icon-button glass notification-trigger" aria-label={error?"Notifications unavailable":`Notifications, ${unread} unread`} title="Notifications" aria-haspopup="dialog" onClick={()=>{dialog.current?.showModal();void load();}}><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5zM10 21h4M12 2v2"/></svg>{!error&&unread>0&&<span className="notification-count" aria-hidden="true">{unread>99?"99+":unread}</span>}{error&&<span className="notification-count" aria-hidden="true">!</span>}</button>
 <dialog ref={dialog} className="notification-dialog nxt-utility-dialog nxt-workspace-content" aria-labelledby="notification-title"><header><div><h2 id="notification-title">Notifications</h2><p>Operational alerts · {unread} unread</p></div><WorkButton aria-label="Close notifications" onClick={()=>dialog.current?.close()}>Close</WorkButton></header><p className="notification-note">Read status is saved on this device. Reading an alert does not resolve it.</p><div className="work-actions"><WorkButton aria-pressed={onlyUnread} onClick={()=>{setOnlyUnread(v=>!v);setPage(0);}}>{onlyUnread?"Show all":"Unread only"}</WorkButton><WorkButton onClick={()=>void load()} disabled={loading}>Refresh</WorkButton><WorkButton disabled={!unread} onClick={()=>markRead(alerts.map(identity))}>Mark all as read</WorkButton><WorkButton onClick={()=>{dialog.current?.close();onSettings();}}>Preferences</WorkButton></div>
 {error?<p role="alert">{error}</p>:loading&&!alerts.length?<p role="status">Loading notifications…</p>:!shown.length?<p>{onlyUnread?"You’re all caught up. No unread alerts.":"No operational alerts right now."}</p>:<ul className="notification-list">{shown.slice(p.start,p.end).map(a=><li key={identity(a)} data-unread={!read.includes(identity(a))}><h3>{a.title}</h3><p>{a.detail}</p><div className="work-actions">{a.linked_entity_id&&<WorkButton onClick={()=>{markRead([identity(a)]);dialog.current?.close();onOpen(a.linked_entity_id!);}}>Open record</WorkButton>}{!read.includes(identity(a))&&<WorkButton onClick={()=>markRead([identity(a)])}>Mark as read</WorkButton>}</div></li>)}</ul>}
 <CollectionPagination label="Notifications" total={shown.length} page={p.current} pageSize={10} onPageChange={setPage}/></dialog></>;
}
