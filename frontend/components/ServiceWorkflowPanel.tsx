"use client";
import dynamic from "next/dynamic";
import {WorkSection} from "./WorkspaceUi";
import type {RoWorkspaceTab} from "./RepairOrderWorkspaceBoard";
const loading=()=> <p role="status">Opening workflow...</p>;
const Appointments=dynamic(()=>import("./ServiceAppointmentsBoard").then(m=>m.ServiceAppointmentsBoard),{loading});
const Orders=dynamic(()=>import("./RepairOrderWorkspaceBoard").then(m=>m.RepairOrderWorkspaceBoard),{loading});
const Warranty=dynamic(()=>import("./WarrantyDeskBoard").then(m=>m.WarrantyDeskBoard),{loading});
const Dispatch=dynamic(()=>import("./ShopControlBoard").then(m=>m.ShopControlBoard),{loading});
export const serviceWorkflowSteps:Record<string,Record<string,{tool:string;view?:RoWorkspaceTab;instruction:string}>>={
 "service.intake":{
  "Appointment Intake":{tool:"appointments",instruction:"Book or update an appointment against the existing customer and vehicle, then check the customer in."},
  "Customer & Vehicle Review":{tool:"orders",view:"overview",instruction:"Open or create the repair order and verify its customer, vehicle and service history."},
  "Walkaround Inspection":{tool:"orders",view:"inspection",instruction:"Open the repair order, record inspection findings and attach condition photos."},
  "Authorization & Signatures":{tool:"orders",view:"estimate",instruction:"Build the estimate and request customer approval. Record the actual authorization outcome before advancing repairs."},
  "Dispatch Assignment":{tool:"dispatch",instruction:"Assign the repair order to a technician and bay, then track its shop stage."}
 },
 "service.mpi":{
  "MPI Checklist":{tool:"orders",view:"inspection",instruction:"Select the repair order and record each inspection result against its checklist."},
  "Photos & Videos":{tool:"orders",view:"inspection",instruction:"Attach photo or video evidence URLs to the selected inspection finding."},
  "Parts & Pricing":{tool:"orders",view:"parts",instruction:"Request and track parts for the selected repair order, then review the estimate before approval."},
  "Recommendation Builder":{tool:"orders",view:"inspection",instruction:"Select inspection findings to create repair recommendations against this repair order."},
  "Approval Tracking":{tool:"orders",view:"estimate",instruction:"Review approval-link status and record customer decisions against the same estimate."}
 },
 "service.warranty_claims":{
  "Warranty Eligibility":{tool:"orders",view:"overview",instruction:"Review the vehicle's recorded warranty and recall evidence. Inferred eligibility is not an OEM coverage guarantee."},
  "Technician Documentation":{tool:"orders",view:"concerns",instruction:"Record the concern, diagnosis and resolution notes before preparing the claim."},
  "Labor Verification":{tool:"orders",view:"estimate",instruction:"Review the repair order estimate and labor evidence before claim submission."},
  "Claim Submission":{tool:"warranty",instruction:"Open the repair order's warranty claim, complete its fields and record its submission reference."},
  "Claim Tracking":{tool:"warranty",instruction:"Review submitted and rejected claims, record decisions and track payment evidence."}
 },
 "service.quality_control":{
  "Quality Control":{tool:"orders",view:"qc",instruction:"Complete required QC checks and resolve failed checks before delivery."},
  "Valet & Detail":{tool:"orders",view:"qc",instruction:"Complete wash and final presentation checks before arranging transport and handoff."},
  "Invoice Review":{tool:"orders",view:"estimate",instruction:"Review approved repair costs and customer decisions before checkout."},
  "Checkout & Delivery":{tool:"orders",view:"pickup",instruction:"Record settlement reference, recipient and actual handover evidence before completing pickup."},
  "CSI Follow-Up":{tool:"orders",view:"followup",instruction:"Record the follow-up outcome, date and next action on the completed repair order."}
 }
};
export function ServiceWorkflowPanel({workflowKey,tab,theme,onDraftOpenChange,onSavingChange}:{workflowKey:string;tab:string;theme:"dark"|"light";onDraftOpenChange:(v:boolean)=>void;onSavingChange:(v:boolean)=>void}){
 const step=serviceWorkflowSteps[workflowKey]?.[tab];if(!step)return null;const props={onDraftOpenChange,onSavingChange};
 return <WorkSection title={tab} description={step.instruction}>{step.tool==="appointments"?<Appointments theme={theme}/>:step.tool==="dispatch"?<Dispatch theme={theme}/>:step.tool==="warranty"?<Warranty theme={theme} {...props}/>:<Orders inline theme={theme} initialTab={step.view} {...props}/>}</WorkSection>;
}
