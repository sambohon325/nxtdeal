"use client";
import dynamic from "next/dynamic";
import {WorkSection} from "./WorkspaceUi";
const loading=()=> <p role="status">Opening workflow...</p>;
const Acquisitions=dynamic(()=>import("./AcquisitionsBoard").then(m=>m.AcquisitionsBoard),{loading});
const Transport=dynamic(()=>import("./OperationsSchedulingBoard").then(m=>m.OperationsSchedulingBoard),{loading});
const Vehicles=dynamic(()=>import("./InventoryWorkspaceBoard").then(m=>m.InventoryWorkspaceBoard),{loading});
const Lot=dynamic(()=>import("./LotControlBoard").then(m=>m.LotControlBoard),{loading});
const Pricing=dynamic(()=>import("./PricingDeskBoard").then(m=>m.PricingDeskBoard),{loading});
const Aging=dynamic(()=>import("./InventoryAgingBoard").then(m=>m.InventoryAgingBoard),{loading});
const Merchandising=dynamic(()=>import("./MerchandisingBoard").then(m=>m.MerchandisingBoard),{loading});
const Wholesale=dynamic(()=>import("./WholesaleDeskBoard").then(m=>m.WholesaleDeskBoard),{loading});
const Floorplan=dynamic(()=>import("./FloorplanWorkBoard").then(m=>m.FloorplanWorkBoard),{loading});
export const inventoryWorkflowSteps:Record<string,Record<string,{tool:string;view?:string;instruction:string}>>={
 "inventory.auction_acquisition":{
  "Acquisition Source":{tool:"acquisitions",view:"new",instruction:"Record the source vehicle, proposed acquisition cost and recon estimate before requesting purchase approval."},
  "Purchase Management":{tool:"acquisitions",view:"pipeline",instruction:"Open the acquisition request, review its risk and complete the purchase approval chain."},
  "Transport Tracking":{tool:"transport",instruction:"Update the purchased vehicle's transport status against its existing auction transaction."},
  "Arrival Processing":{tool:"vehicles",instruction:"Open the arriving vehicle and record receipt, inspection, recon and ownership against its lifecycle record."},
  "Floorplan Funding":{tool:"floorplan",instruction:"Record the lender statement and financed principal against the existing vehicle. This does not request funds from a lender."}
 },
 "inventory.lot_audit":{
  "Vehicle Placement":{tool:"lot",view:"map",instruction:"Open a vehicle to set its physical lot row and space."},
  "Key Management":{tool:"lot",view:"keys",instruction:"Check keys out or in and record missing keys against the vehicle."},
  "Lot Audits":{tool:"lot",view:"map",instruction:"Open each observed vehicle and log a physical scan; compare its location with the recorded lot position."},
  "Damage & Exception Tracking":{tool:"lot",view:"damage",instruction:"Record damage, severity and supporting notes against the affected vehicle."},
  "Resolution Center":{tool:"lot",view:"damage",instruction:"Review open damage reports and update their resolution status after the work is completed."}
 },
 "inventory.aging_pricing":{
  "Aging Management":{tool:"aging",instruction:"Review inventory exposure, reduce price or request manager and wholesale review. Read the basis labels before acting on age estimates."},
  "Market Pricing":{tool:"pricing",instruction:"Open a vehicle's pricing review. Simulated comparisons are labelled; verify an external source before relying on them."},
  "Price Adjustments":{tool:"pricing",instruction:"Open the vehicle, review cost and margin, then apply and verify its saved price."},
  "Merchandising Refresh":{tool:"merchandising",instruction:"Update the same vehicle's photos, description and featured status; save the listing before leaving."},
  "Velocity Analysis":{tool:"aging",instruction:"Review slow-moving stock and take a recorded price, marketing or wholesale-review action."}
 },
 "inventory.wholesale_disposition":{
  "Wholesale Assignment":{tool:"wholesale",view:"candidates",instruction:"Review candidate vehicles and record a wholesale offer against the selected unit."},
  "Condition Reports":{tool:"vehicles",instruction:"Open the vehicle's inspection and recon checklist to document its condition before disposition."},
  "Auction Management":{tool:"aging",instruction:"Select the vehicle and record its auction assignment or request manager review."},
  "Bid Tracking":{tool:"wholesale",view:"offers",instruction:"Review offers and record acceptance, rejection or a counteroffer before marking a sale."},
  "Settlement & Titles":{tool:"wholesale",view:"funds",instruction:"Record funds collected against the sold wholesale unit. Use Floorplan & Payoffs for lender-held title release evidence."}
 }
};
export function InventoryWorkflowPanel({workflowKey,tab,theme,onDraftOpenChange,onSavingChange}:{workflowKey:string;tab:string;theme:"dark"|"light";onDraftOpenChange:(v:boolean)=>void;onSavingChange:(v:boolean)=>void}){
 const step=inventoryWorkflowSteps[workflowKey]?.[tab];if(!step)return null;const props={onDraftOpenChange,onSavingChange};
 return <WorkSection title={tab} description={step.instruction}>{step.tool==="acquisitions"?<Acquisitions {...props} theme={theme} initialTab={step.view as "new"|"pipeline"}/>:step.tool==="transport"?<Transport theme={theme} initialTab="transport"/>:step.tool==="vehicles"?<Vehicles theme={theme}/>:step.tool==="floorplan"?<Floorplan {...props}/>:step.tool==="lot"?<Lot theme={theme} initialTab={step.view as "map"|"keys"|"damage"}/>:step.tool==="pricing"?<Pricing theme={theme}/>:step.tool==="aging"?<Aging theme={theme}/>:step.tool==="merchandising"?<Merchandising theme={theme} {...props}/>:<Wholesale theme={theme} initialTab={step.view as "candidates"|"offers"|"funds"}/>}</WorkSection>;
}
