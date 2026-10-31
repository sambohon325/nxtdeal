"use client";
import {useEffect,useState} from "react";
import {crmRequest} from "@/lib/salesCrm";
import {RecordTable} from "./RecordTable";
import {WorkButton,WorkInput,WorkSection,WorkSelect} from "./WorkspaceUi";
type Connection={id:string;name:string;department:string;revision:number;columns:Record<string,string>;history:{at:string;actor:string;revision:number}[]};
type Data={connections:Connection[];required:Record<string,string[]>};
export function SchemaMappingBoard({onDraftOpenChange,onSavingChange}:{onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void}){
 const [data,setData]=useState<Data|null>(null),[selected,setSelected]=useState(""),[rows,setRows]=useState<{source:string;target:string}[]>([]),[dirty,setDirty]=useState(false),[busy,setBusy]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 const current=data?.connections.find(c=>c.id===selected);
 useEffect(()=>{onDraftOpenChange?.(dirty);return()=>onDraftOpenChange?.(false)},[dirty,onDraftOpenChange]);
 useEffect(()=>{onSavingChange?.(saving);return()=>onSavingChange?.(false)},[saving,onSavingChange]);
 async function load(){setBusy(true);setError("");try{setData(await crmRequest<Data>("/readiness/mappings"))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 useEffect(()=>{void load()},[]);
 function choose(id:string){setSelected(id);setRows(Object.entries(data?.connections.find(c=>c.id===id)?.columns||{}).map(([source,target])=>({source,target})));setNotice("")}
 async function save(){if(!current)return;setError("");setNotice("");if(new Set(rows.map(r=>r.source)).size!==rows.length){setError("Each source column must be unique.");return}setBusy(true);setSaving(true);try{const result=await crmRequest<{revision:number;columns:Record<string,string>}>(`/readiness/mappings/${current.id}`,{method:"PUT",body:JSON.stringify({revision:current.revision,columns:Object.fromEntries(rows.map(r=>[r.source,r.target]))})});setData(d=>d?{...d,connections:d.connections.map(c=>c.id===current.id?{...c,...result}:c)}:d);setDirty(false);setNotice("Mapping saved. Future uploads on this connection use these column names.");}catch(e){setError((e as Error).message)}finally{setBusy(false);setSaving(false)}}
 return <WorkSection title="CSV column mapping" description="Match your file headers to NXTDeal fields. Unmapped columns keep their names. Uploads validate every row before importing.">
 {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
 <div className="work-actions"><WorkButton disabled={busy||dirty} onClick={()=>void load()}>Refresh connections</WorkButton></div>
 {data?.connections.length===0&&<p>Create a CSV connection in Integration Setup first.</p>}
 <label>CSV connection<WorkSelect disabled={busy||dirty} value={selected} onChange={e=>choose(e.target.value)}><option value="">Choose a connection</option>{data?.connections.map(c=><option key={c.id} value={c.id}>{c.name} · {c.department}</option>)}</WorkSelect></label>
 {current&&<form className="workflow-start-form" onSubmit={e=>{e.preventDefault();void save()}}><fieldset disabled={busy}>
 <p>Required destination fields: {data?.required[current.department]?.join(", ")}. Names are case-sensitive.</p>
 <RecordTable label="Column mappings" paginate={false}><thead><tr><th>Your file header</th><th>NXTDeal field</th><th>Action</th></tr></thead><tbody>{rows.map((r,i)=><tr key={i}><td><WorkInput aria-label={`Source column ${i+1}`} required maxLength={100} value={r.source} onChange={e=>{setRows(rows.map((v,j)=>j===i?{...v,source:e.target.value}:v));setDirty(true)}}/></td><td><WorkInput aria-label={`Destination column ${i+1}`} required maxLength={100} value={r.target} onChange={e=>{setRows(rows.map((v,j)=>j===i?{...v,target:e.target.value}:v));setDirty(true)}}/></td><td><WorkButton onClick={()=>{setRows(rows.filter((_,j)=>i!==j));setDirty(true)}}>Remove mapping {i+1}</WorkButton></td></tr>)}</tbody></RecordTable>
 <div className="work-actions"><WorkButton disabled={rows.length>=100} onClick={()=>{setRows([...rows,{source:"",target:""}]);setDirty(true)}}>Add column mapping</WorkButton><WorkButton type="submit" variant="primary" disabled={!dirty}>Save mapping</WorkButton><WorkButton disabled={!dirty} onClick={()=>{choose(selected);setDirty(false)}}>Discard changes</WorkButton></div>
 </fieldset></form>}
 </WorkSection>;
}
