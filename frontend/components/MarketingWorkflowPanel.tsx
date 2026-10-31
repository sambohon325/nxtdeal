"use client";
import dynamic from "next/dynamic";
import {getSession} from "@/lib/auth";
import {WorkSection} from "./WorkspaceUi";
const loading=()=> <p role="status">Opening workflow...</p>;
const Planning=dynamic(()=>import("./marketing/CampaignPlanning").then(m=>m.CampaignPlanning),{loading});
const Campaigns=dynamic(()=>import("./CampaignsBoard").then(m=>m.CampaignsBoard),{loading});
const Delivery=dynamic(()=>import("./marketing/MarketingOperations").then(m=>m.MarketingOperations),{loading});
const Outcomes=dynamic(()=>import("./marketing/CampaignWorkflow").then(m=>m.CampaignWorkflow),{loading});
const Crm=dynamic(()=>import("./MarketingCRMBoard").then(m=>m.MarketingCRMBoard),{loading});
const Website=dynamic(()=>import("./WebsiteBuilderBoard").then(m=>m.WebsiteBuilderBoard),{loading});
const Reputation=dynamic(()=>import("./SocialReputationBoard").then(m=>m.SocialReputationBoard),{loading});
const Events=dynamic(()=>import("./EventsBoard").then(m=>m.EventsBoard),{loading});
export const marketingWorkflowSteps:Record<string,Record<string,{tool:string;view?:string;instruction:string}>>={
 "marketing.oem_incentive":{
  "OEM Incentives & Offers":{tool:"planning",instruction:"Record the offer, expiration, objective and budget in a campaign brief. Verify OEM eligibility against the source program before approval."},
  "Campaign Builder":{tool:"campaigns",instruction:"Create or open the shared campaign, choose inventory and audience, and save its content for review."},
  "Channel Deployment":{tool:"delivery",instruction:"Review channel drafts and approval status. Delivery uses the configured provider; accepted messages are not proof of delivery."},
  "Attribution & Analytics":{tool:"outcomes",instruction:"Link qualifying responses to appointments and recorded sales or service outcomes."},
  "Optimization Center":{tool:"planning",instruction:"Revise the existing brief's budget, target, timing or response owner using the recorded campaign results."}
 },
 "marketing.database_mining":{
  "Customer Intelligence":{tool:"crm",view:"customer360",instruction:"Find the existing customer and review ownership, service and activity history."},
  "Opportunity Scoring":{tool:"crm",view:"audiences_scoring",instruction:"Build an eligible audience using the available customer signals and review the score evidence."},
  "Equity & Lease Mining":{tool:"crm",view:"opportunities",instruction:"Review recorded opportunities and create work against the existing customer. Missing equity or lease data must remain unknown."},
  "Outreach Assignment":{tool:"outcomes",instruction:"Assign qualifying response work to an owner with a deadline and next action. Passive marketing signals do not become agent tasks."},
  "Conversion Tracking":{tool:"outcomes",instruction:"Record appointments and link completed sale or service outcomes to the same response record."}
 },
 "marketing.website_merchandising":{
  "Website Builder":{tool:"website",view:"sites",instruction:"Select or create the dealership website, edit its pages, then use its review and publication controls."},
  "Landing Pages & Forms":{tool:"website",view:"builder",instruction:"Choose a site and page, edit sections and lead-capture content, and save changes before publishing."},
  "Conversion Optimization":{tool:"website",view:"analytics",instruction:"Review website performance, then use Builder to revise the same site's content and capture flow."},
  "Review Management":{tool:"reputation",instruction:"Review imported customer reviews, prepare a response and use the connected publishing controls."},
  "Reputation Recovery":{tool:"reputation",instruction:"Prioritize unresponded negative reviews, record a response and track follow-up on the same customer."}
 },
 "marketing.reputation":{
  "Event Configuration":{tool:"events",view:"configuration",instruction:"Create an event with dates, location and capacity, or open an existing event to manage its lifecycle."},
  "Audience & Invitations":{tool:"events",view:"campaigns",instruction:"Open the event and prepare its audience campaign. Review consent and provider availability before outreach."},
  "RSVP Management":{tool:"events",view:"rsvps",instruction:"Open the event to record RSVPs, walk-ins and attendance against its guest list."},
  "Event Operations":{tool:"events",view:"tasks",instruction:"Open the event to assign operational tasks, update their status and manage event start/completion."},
  "Revenue & Follow-Up":{tool:"events",view:"war_room",instruction:"Open the event's results, review attendance and follow-up, and connect interested attendees to existing sales work."}
 }
};
export function MarketingWorkflowPanel({workflowKey,tab,theme,onDraftOpenChange,onSavingChange}:{workflowKey:string;tab:string;theme:"dark"|"light";onDraftOpenChange:(v:boolean)=>void;onSavingChange:(v:boolean)=>void}){
 const step=marketingWorkflowSteps[workflowKey]?.[tab];if(!step)return null;
 const props={onDraftOpenChange,onSavingChange};const canEdit=["ADMIN","MARKETING"].includes(getSession()?.role||"");
 return <WorkSection title={tab} description={step.instruction}>
  {step.tool==="planning"?<Planning canEdit={canEdit} {...props}/>:step.tool==="campaigns"?<Campaigns theme={theme} {...props}/>:step.tool==="delivery"?<Delivery mode="communications" canEdit={canEdit} {...props}/>:step.tool==="outcomes"?<Outcomes {...props}/>:step.tool==="crm"?<Crm key={tab} embedded theme={theme} initialTab={step.view as "customer360"|"audiences_scoring"|"opportunities"} {...props}/>:step.tool==="website"?<Website theme={theme} initialSection={step.view as "sites"|"builder"|"analytics"}/>:step.tool==="reputation"?<Reputation theme={theme} initialSection="reputation"/>:<Events onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} theme={theme} workflowStep={step.view as "configuration"|"campaigns"|"rsvps"|"tasks"|"war_room"}/>}
 </WorkSection>;
}
