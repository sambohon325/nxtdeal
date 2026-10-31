import type { Deal } from "./deals";
export const financeQueues = [
  {key:"handoff",label:"New handoffs"}, {key:"response",label:"Lender responses"},
  {key:"contract",label:"Prepare contracts"}, {key:"funding",label:"Awaiting funding"},
  {key:"funded",label:"Funded"}, {key:"cancelled",label:"Cancelled"},
] as const;
export type FinanceQueue = typeof financeQueues[number]["key"];
export function financeStep(deal: Deal): {queue:FinanceQueue; action:string; tab:"worksheet"|"financing"|"contract"} | null {
  if(deal.status==="cancelled")return {queue:"cancelled",action:"Review cancelled deal",tab:"worksheet"};
  if(deal.status==="funded")return {queue:"funded",action:"Review funded deal",tab:"contract"};
  if(deal.status==="contract")return {queue:"funding",action:"Review contract & funding",tab:"contract"};
  if(deal.status!=="financing")return null;
  if(deal.financing_status==="approved")return {queue:"contract",action:"Review terms & prepare contract",tab:"contract"};
  if(deal.financing_status==="submitted")return {queue:"response",action:"Review lender response",tab:"financing"};
  if(deal.financing_status==="countered")return {queue:"response",action:"Review counteroffer",tab:"financing"};
  if(deal.financing_status==="declined")return {queue:"response",action:"Review declined financing",tab:"financing"};
  return {queue:"handoff",action:"Review Sales handoff",tab:"financing"};
}
export function financeQueue(deals:Deal[], queue:FinanceQueue, search:string) {
  const query=search.trim().toLowerCase();
  return deals.filter(d=>financeStep(d)?.queue===queue && [d.id,d.customer?.name,d.vehicle?.description].join(" ").toLowerCase().includes(query))
    .sort((a,b)=>a.updated_at.localeCompare(b.updated_at)||a.id.localeCompare(b.id));
}
