"use client";
import { WorkSelect, WorkInput, WorkButton } from "./../WorkspaceUi";
import {useState} from "react";
import {createLeadTask, type LeadTaskType} from "@/lib/leadRecord";
import styles from "./SalesCrmWorkspace.module.css";

/** Each existing task endpoint is independent; never hide partial successes or retry them. */
export function CrmBulkFollowup({ids, onSaved, onClear}: {ids:string[];onSaved:(ids:string[])=>void;onClear:()=>void}) {
  const [type,setType]=useState<LeadTaskType>("call");
  const [description,setDescription]=useState("");
  const [due,setDue]=useState("");
  const [busy,setBusy]=useState(false);
  const [result,setResult]=useState("");
  if(!ids.length&&!result) return null;
  return <section className={styles.panel} aria-label="Bulk follow-up"><h3>{ids.length} leads selected</h3><p>Create one follow-up task per selected lead. No customer messages are sent.</p>{result&&<p role="status">{result}</p>}{ids.length>0&&<form onSubmit={async e=>{e.preventDefault();if(busy)return;setBusy(true);setResult("");const saved:string[]=[];const failures:string[]=[];for(const id of ids){try{await createLeadTask(id,{task_type:type,description,due_at:due?new Date(due).toISOString():null});saved.push(id);}catch(e){failures.push(`${id}: ${e instanceof Error?e.message:"Unable to create task"}`);}}onSaved(saved);setResult(`${saved.length} tasks created.${failures.length?` ${failures.length} failed: ${failures.join("; ")}. Only failed leads remain selected.`:""}`);setBusy(false);}}><div className={styles.fields}><label>Task type<WorkSelect value={type} onChange={e=>setType(e.target.value as LeadTaskType)}><option value="call">Call</option><option value="send_pricing">Send pricing</option><option value="schedule_appraisal">Schedule appraisal</option><option value="follow_up_after_demo">Follow up after demo</option><option value="custom">Custom</option></WorkSelect></label><label>Description<WorkInput required value={description} maxLength={500} onChange={e=>setDescription(e.target.value)}/></label><label>Due in your local time<WorkInput type="datetime-local" required value={due} onChange={e=>setDue(e.target.value)}/></label></div><div className={styles.toolbar}><WorkButton type="submit" disabled={busy}>{busy?"Creating tasks…":"Create follow-up tasks"}</WorkButton><WorkButton type="button" disabled={busy} onClick={()=>{onClear();setResult("");}}>Clear selection</WorkButton></div></form>}</section>;
}
