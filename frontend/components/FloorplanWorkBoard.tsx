"use client";
import {useEffect,useState} from "react";
import {crmRequest} from "@/lib/salesCrm";
import {getSession} from "@/lib/auth";
import {RecordTable} from "./RecordTable";
import {WorkButton,WorkInput,WorkSelect,WorkTextarea,WorkSection} from "./WorkspaceUi";
type Account={id:string;revision:number;vehicle_id:string;lender:string;balance_cents:number;principal_cents:number;currency:string;title_status:string;source_reference:string;history:{at:string;actor:string;event:string;detail:string}[]};
type Payoff={id:string;revision:number;account_id:string;amount_cents:number;currency:string;status:string;requested_by:string;bank_reference?:string};
type Data={accounts:Account[];payoffs:Payoff[];vehicles:{id:string;name:string}[];execution:string};
const path="/finance/floorplan-work";
export function FloorplanWorkBoard({section="accounts",onDraftOpenChange,onSavingChange}:{section?:string;onDraftOpenChange?:(v:boolean)=>void;onSavingChange?:(v:boolean)=>void}){
 const [data,setData]=useState<Data|null>(null),[selected,setSelected]=useState(""),[error,setError]=useState(""),[busy,setBusy]=useState(false),[saving,setSaving]=useState(false),[notice,setNotice]=useState("");
 const [create,setCreate]=useState(false),[draft,setDraft]=useState({vehicle_id:"",lender:"",principal:"",currency:"USD",source_reference:""});
 const [amount,setAmount]=useState(""),[evidence,setEvidence]=useState(""),[reference,setReference]=useState(""),[title,setTitle]=useState("requested");
 const dirty=create||!!amount||!!evidence||!!reference;const session=getSession();const canApprove=["ADMIN","OPERATIONS","FINANCE"].includes(session?.role||"");
 useEffect(()=>{onDraftOpenChange?.(dirty);return()=>onDraftOpenChange?.(false)},[dirty,onDraftOpenChange]);
 useEffect(()=>{onSavingChange?.(saving);return()=>onSavingChange?.(false)},[saving,onSavingChange]);
 async function load(){setBusy(true);setError("");try{setData(await crmRequest<Data>(path))}catch(e){setError((e as Error).message)}finally{setBusy(false)}}
 useEffect(()=>{void load()},[]);
 async function save(url:string,body:unknown){setBusy(true);setSaving(true);setError("");try{await crmRequest(path+url,{method:"POST",body:JSON.stringify(body)});setCreate(false);setAmount("");setEvidence("");setReference("");setNotice("Saved to the floorplan record.");setData(await crmRequest<Data>(path));}catch(e){setError((e as Error).message)}finally{setBusy(false);setSaving(false)}}
 const showRequest=["accounts","requests"].includes(section),showTitle=["accounts","titles"].includes(section),showApproval=["accounts","approvals"].includes(section),showPayment=["accounts","payments","reconciliation"].includes(section);
 const current=data?.accounts.find(a=>a.id===selected);const payoffs=data?.payoffs.filter(p=>p.account_id===selected)||[];
 const money=(cents:number,currency:string)=>new Intl.NumberFormat(undefined,{style:"currency",currency}).format(cents/100);
 return <WorkSection title="Floorplan records" description={data?.execution||"Record lender statements, approve payoff requests and reconcile externally completed payments."}>
  {error&&<p role="alert">{error}</p>}{notice&&<p role="status">{notice}</p>}
  <div className="work-actions"><WorkButton disabled={busy||dirty} onClick={()=>void load()}>Refresh</WorkButton><WorkButton disabled={busy||dirty} variant="primary" onClick={()=>setCreate(true)}>Record financing</WorkButton></div>
  {create&&<form className="workflow-start-form" onSubmit={e=>{e.preventDefault();void save("",draft)}}><fieldset disabled={busy}>
   <label>Vehicle<WorkSelect required value={draft.vehicle_id} onChange={e=>setDraft({...draft,vehicle_id:e.target.value})}><option value="">Choose a vehicle</option>{data?.vehicles.map(v=><option key={v.id} value={v.id}>{v.name} · {v.id}</option>)}</WorkSelect></label>
   <label>Lender<WorkInput required minLength={2} value={draft.lender} onChange={e=>setDraft({...draft,lender:e.target.value})}/></label><label>Statement principal<WorkInput type="number" min="0.01" step="0.01" required value={draft.principal} onChange={e=>setDraft({...draft,principal:e.target.value})}/></label>
   <label>Currency<WorkSelect value={draft.currency} onChange={e=>setDraft({...draft,currency:e.target.value})}><option>USD</option><option>CAD</option></WorkSelect></label><label>Lender statement reference<WorkInput required minLength={3} value={draft.source_reference} onChange={e=>setDraft({...draft,source_reference:e.target.value})}/></label>
   <div className="work-actions"><WorkButton type="submit" variant="primary">Save financing record</WorkButton><WorkButton onClick={()=>setCreate(false)}>Cancel</WorkButton></div>
  </fieldset></form>}
  <RecordTable label="Floorplan accounts"><thead><tr><th>Vehicle</th><th>Lender</th><th>Balance</th><th>Title</th><th>Action</th></tr></thead><tbody>{data?.accounts.map(a=><tr key={a.id}><td>{a.vehicle_id}</td><td>{a.lender}</td><td>{money(a.balance_cents,a.currency)}</td><td>{a.title_status.replaceAll("_"," ")}</td><td><WorkButton disabled={busy||dirty} onClick={()=>{setSelected(a.id);setNotice("")}}>Open account</WorkButton></td></tr>)}</tbody></RecordTable>
  {current&&<WorkSection title={`${current.lender} · ${current.vehicle_id}`} description={`Source: ${current.source_reference}. Outstanding: ${money(current.balance_cents,current.currency)}.`}>
   <form className="workflow-start-form" onSubmit={e=>{e.preventDefault();void save(`/${current.id}/payoffs`,{revision:current.revision,amount,evidence})}}><fieldset disabled={busy}>
    <label>Evidence / review notes<WorkTextarea minLength={10} required value={evidence} onChange={e=>setEvidence(e.target.value)}/></label>
    {showRequest&&<><label>Payoff amount<WorkInput required type="number" min="0.01" max={current.balance_cents/100} step="0.01" value={amount} onChange={e=>setAmount(e.target.value)}/></label><WorkButton type="submit" disabled={current.balance_cents===0}>Request payoff approval</WorkButton></>}
    {showTitle&&<><label>Title status<WorkSelect value={title} onChange={e=>setTitle(e.target.value)}>{["lender_held","requested","released","received"].map(s=><option key={s} value={s}>{s.replaceAll("_"," ")}</option>)}</WorkSelect></label><WorkButton disabled={evidence.trim().length<10} onClick={()=>void save(`/${current.id}/title`,{revision:current.revision,status:title,evidence})}>Save title evidence</WorkButton></>}
    {(showApproval||showPayment)&&<label>Approval or external bank reference<WorkInput value={reference} onChange={e=>setReference(e.target.value)}/></label>}
    <RecordTable label="Payoff requests"><thead><tr><th>Amount</th><th>Status</th><th>Action</th></tr></thead><tbody>{payoffs.map(p=><tr key={p.id}><td>{money(p.amount_cents,p.currency)}</td><td>{p.status}</td><td>{showApproval&&p.status==="requested"&&<><WorkButton disabled={!canApprove||p.requested_by===session?.employeeId||reference.trim().length<3||evidence.trim().length<10} onClick={()=>void save(`/payoffs/${p.id}/decision`,{revision:p.revision,action:"approve",reference,evidence})}>Approve payoff request</WorkButton><WorkButton disabled={!canApprove||reference.trim().length<3||evidence.trim().length<10} onClick={()=>void save(`/payoffs/${p.id}/decision`,{revision:p.revision,action:"reject",reference,evidence})}>Reject</WorkButton></>}{showPayment&&p.status==="approved"&&<WorkButton disabled={!canApprove||reference.trim().length<3||evidence.trim().length<10} onClick={()=>void save(`/payoffs/${p.id}/decision`,{revision:p.revision,action:"record_payment",reference,evidence})}>Record external payment</WorkButton>}{p.status==="recorded"&&p.bank_reference}</td></tr>)}</tbody></RecordTable>
   </fieldset></form>
   <RecordTable label="Floorplan history"><thead><tr><th>When</th><th>Employee</th><th>Action</th><th>Evidence</th></tr></thead><tbody>{current.history.map((h,i)=><tr key={i}><td>{h.at}</td><td>{h.actor}</td><td>{h.event.replaceAll("_"," ")}</td><td>{h.detail}</td></tr>)}</tbody></RecordTable>
  </WorkSection>}
 </WorkSection>;
}
