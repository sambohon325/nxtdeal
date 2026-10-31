"use client";
import { WorkInput, WorkButton } from "./WorkspaceUi";
import {useState} from 'react';
import {updateAdminSettings,type Website,type WebsiteAnalytics} from '@/lib/websites';
import styles from './WebsiteTraffic.module.css';
const labels:Record<string,string>={all:'All website inquiries',information:'Information requests',test_drive:'Test drive requests',purchase:'Purchase inquiries',financing:'Financing inquiries',trade:'Trade-in inquiries',assistant:'Assistant leads'};
export function WebsiteConversionGoals({website,traffic,onChange}:{website:Website;traffic?:WebsiteAnalytics['traffic'];onChange:(w:Website)=>void}){
 const [goals,setGoals]=useState(()=>Object.keys(labels).map(metric=>website.admin_settings.conversion_goals?.find(g=>g.metric===metric)||{metric,target:10,enabled:false}));
 const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
 async function save(){setBusy(true);setMessage('');try{const updated=await updateAdminSettings(website.id,{conversion_goals:goals});onChange(updated);setMessage('Goals saved.')}catch(e){setMessage(e instanceof Error?e.message:'Unable to save goals')}finally{setBusy(false)}}
 return <section className={styles.card}><h3>Conversions & goals</h3><p>A conversion is a successfully saved inquiry in NXTDeal, not a button click. Purchase and financing inquiries do not mean a completed sale or approval.</p>
 <div className={styles.grid}>{Object.entries(traffic?.conversions||{}).map(([metric,count])=><div className={styles.row} key={metric}><span>{labels[metric]||metric}</span><b>{count}</b></div>)}</div>
 {!Object.keys(traffic?.conversions||{}).length&&<p>No captured inquiries in this period.</p>}
 <h3>Rolling 30-day goals</h3><p>Set targets for the outcomes that matter. These targets always use the last 30 days, independent of the report date filter.</p>
 {traffic?.goals.map(g=><div className={styles.row} key={g.metric}><span>{labels[g.metric]}</span><b>{g.actual} / {g.target}</b><i style={{width:`${Math.min(100,g.actual/g.target*100)}%`}}/></div>)}
 <details style={{marginTop:20}}><summary>Set up conversion goals</summary>{goals.map((g,index)=><div className={styles.connection} key={g.metric}><label><WorkInput type="checkbox" checked={g.enabled} onChange={e=>setGoals(v=>v.map((row,i)=>i===index?{...row,enabled:e.target.checked}:row))}/> {labels[g.metric]}</label><label>30-day target <WorkInput type="number" min={1} max={100000} step={1} aria-label={`${labels[g.metric]} target`} value={g.target} onChange={e=>setGoals(v=>v.map((row,i)=>i===index?{...row,target:Number(e.target.value)}:row))} style={{width:110}}/></label></div>)}<WorkButton type="submit" disabled={busy} onClick={()=>void save()}>Save goals</WorkButton></details>{message&&<p role="status">{message}</p>}</section>
}
