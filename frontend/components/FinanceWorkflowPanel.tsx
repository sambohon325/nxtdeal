"use client";
import dynamic from "next/dynamic";
import {WorkSection} from "./WorkspaceUi";
const loading=()=> <p role="status">Opening workflow...</p>;
const Deals=dynamic(()=>import("./DealDeskBoard").then(m=>m.DealDeskBoard),{loading});
const Documents=dynamic(()=>import("./DocumentWorkflowsBoard").then(m=>m.DocumentWorkflowsBoard),{loading});
const Compliance=dynamic(()=>import("./LendingComplianceBoard").then(m=>m.LendingComplianceBoard),{loading});
const Accounting=dynamic(()=>import("./LoanAccountingBoard").then(m=>m.LoanAccountingBoard),{loading});
const Floorplan=dynamic(()=>import("./FloorplanWorkBoard").then(m=>m.FloorplanWorkBoard),{loading});
const Commissions=dynamic(()=>import("./CommissionWorkBoard").then(m=>m.CommissionWorkBoard),{loading});
export const financeWorkflowSteps:Record<string,Record<string,{tool:string;view?:string;instruction:string}>>={
 "finance.cit_funding":{
  "Lender Assignment":{tool:"deals",instruction:"Open the deal's Financing section and select the recorded lender or in-house financing path."},
  "Stipulation Tracking":{tool:"documents",instruction:"Open the deal jacket, request missing documents and track approval against the existing deal."},
  "Paperwork Audit":{tool:"documents",instruction:"Review document completeness and approve or reject the actual packet evidence."},
  "Submission Queue":{tool:"deals",instruction:"Review each pending deal and its lender submission. Provider and contracting readiness gates remain enforced."},
  "Funding Reconciliation":{tool:"deals",instruction:"Review the recorded lender decision and contract readiness before funding. Unmet readiness requirements must be resolved, never overridden by a workflow step."}
 },
 "finance.compliance":{
  "Identity Verification":{tool:"compliance",instruction:"Open the customer compliance record and record verification evidence."},
  "OFAC & Red Flags":{tool:"compliance",instruction:"Run the available screening checks and review potential matches before recording the decision."},
  "Secure Document Storage":{tool:"documents",instruction:"Request, review and retain the document in the shared deal jacket."},
  "Regulatory Filings":{tool:"compliance",instruction:"Review filing requirements and record the actual external filing reference. Saving evidence does not file with a regulator."},
  "Compliance Approval":{tool:"documents",instruction:"Review the compliance packet and record the authorized document decisions."}
 },
 "finance.floorplan_payoff":{
  "Payoff Requests":{tool:"floorplan",view:"requests",instruction:"Select the recorded vehicle financing account and request a payoff within its outstanding balance."},
  "Wire Authorization":{tool:"floorplan",view:"approvals",instruction:"A different authorized employee must approve the payoff. This records approval only; no wire is sent."},
  "Title Tracking":{tool:"floorplan",view:"titles",instruction:"Record lender-held, requested, released and received title evidence. Release requires full recorded payoff."},
  "Floorplan Reduction":{tool:"floorplan",view:"payments",instruction:"Record the externally completed payment and unique bank reference; the saved balance reduces once."},
  "Reconciliation":{tool:"floorplan",view:"reconciliation",instruction:"Compare the account history and outstanding balance with the lender statement and recorded bank references."}
 },
 "finance.deal_accounting":{
  "Deal Posting":{tool:"accounting",view:"General Ledger",instruction:"Review the ledger and sync eligible recorded transactions, inspecting the source and basis of every entry."},
  "Gross Reconciliation":{tool:"accounting",view:"Financial Statements",instruction:"Compare recorded vehicle-sale entries and financial statements; simulated entries remain labelled."},
  "Pay Plans":{tool:"commissions",instruction:"Create a pay plan from an approved policy, with an explicit percentage, flat amount and currency."},
  "Commission Approval":{tool:"commissions",instruction:"Prepare a commission for a funded deal using documented commissionable basis. Obtain independent approval before recording external payroll evidence."},
  "Financial Close":{tool:"accounting",view:"Payments Ledger",instruction:"Review unposted payments and period status before using the existing month-end close action."}
 }
};
export function FinanceWorkflowPanel({workflowKey,tab,theme,onDraftOpenChange,onSavingChange}:{workflowKey:string;tab:string;theme:"dark"|"light";onDraftOpenChange:(v:boolean)=>void;onSavingChange:(v:boolean)=>void}){
 const s=financeWorkflowSteps[workflowKey]?.[tab];if(!s)return null;const props={onDraftOpenChange,onSavingChange};
 return <WorkSection title={tab} description={s.instruction}>{s.tool==="deals"?<Deals inline theme={theme} initialDetailTab="financing"/>:s.tool==="documents"?<Documents theme={theme}/>:s.tool==="compliance"?<Compliance theme={theme}/>:s.tool==="accounting"?<Accounting theme={theme} initialTab={s.view as "General Ledger"|"Financial Statements"|"Payments Ledger"}/>:s.tool==="commissions"?<Commissions {...props}/>:<Floorplan section={s.view} {...props}/>}</WorkSection>;
}
