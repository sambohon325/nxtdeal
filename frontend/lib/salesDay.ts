import type { LeadTaskBrief } from "./leadRecord";
export type SalesDayTask = LeadTaskBrief & {lead_id:string;lead_name:string;owner_name:string};
export function salesDayQueue(tasks: SalesDayTask[], now: number) {
 const timestamp=(t:SalesDayTask)=>t.due_at && Number.isFinite(Date.parse(t.due_at)) ? Date.parse(t.due_at) : Infinity;
 return tasks.filter(t=>!t.completed).sort((a,b)=>timestamp(a)-timestamp(b)||a.id.localeCompare(b.id)).map(t=>({...t,overdue:timestamp(t)<now}));
}
