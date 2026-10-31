"use client";
import dynamic from "next/dynamic";
import {getSession} from "@/lib/auth";
import {WorkSection} from "./WorkspaceUi";
import {ReadinessPolicyBoard} from "./ReadinessPolicyBoard";
import {SchemaMappingBoard} from "./SchemaMappingBoard";
const loading=()=> <p role="status">Opening workflow...</p>;
const Users=dynamic(()=>import("./AdminUsersBoard").then(m=>m.AdminUsersBoard),{loading});
const Roles=dynamic(()=>import("./RolesPermissionsBoard").then(m=>m.RolesPermissionsBoard),{loading});
const Access=dynamic(()=>import("./IdentityAccessBoard").then(m=>m.IdentityAccessBoard),{loading});
const Audit=dynamic(()=>import("./AuditCenterBoard").then(m=>m.AuditCenterBoard),{loading});
const Tasks=dynamic(()=>import("./OperationsTasksBoard").then(m=>m.OperationsTasksBoard),{loading});
const Data=dynamic(()=>import("./DataManagementBoard").then(m=>m.DataManagementBoard),{loading});
const Governance=dynamic(()=>import("./GovernanceBoard").then(m=>m.GovernanceBoard),{loading});
const Connections=dynamic(()=>import("./ConnectionsBoard").then(m=>m.ConnectionsBoard),{loading});
const Integration=dynamic(()=>import("./ReadinessIntegrationPanel").then(m=>m.ReadinessIntegrationPanel),{loading});
const Health=dynamic(()=>import("./DataHealthBoard").then(m=>m.DataHealthBoard),{loading});
const Performance=dynamic(()=>import("./PerformanceReadinessBoard").then(m=>m.PerformanceReadinessBoard),{loading});
const Forecasts=dynamic(()=>import("./ReadinessForecastsBoard").then(m=>m.ReadinessForecastsBoard),{loading});
const Scenarios=dynamic(()=>import("./ReadinessScenariosBoard").then(m=>m.ReadinessScenariosBoard),{loading});
const Risks=dynamic(()=>import("./EnterpriseRiskCenterBoard").then(m=>m.EnterpriseRiskCenterBoard),{loading});
const Recommendations=dynamic(()=>import("./ReadinessRecommendationsBoard").then(m=>m.ReadinessRecommendationsBoard),{loading});
const Business=dynamic(()=>import("./BusinessHealthBoard").then(m=>m.BusinessHealthBoard),{loading});
const Planning=dynamic(()=>import("./StrategicPlanningBoard").then(m=>m.StrategicPlanningBoard),{loading});
type Step={tool:string;view?:string;instruction:string};
export const supportWorkflowSteps:Record<string,Record<string,Step>>={
 "administration.onboarding":{
  "Employee Profile":{tool:"users",instruction:"Create or open an employee and save their profile against the shared staff record."},
  "Role Assignment":{tool:"users",instruction:"Open the employee, review the role and dashboards, and save authorized access changes."},
  "System Access":{tool:"access",view:"all",instruction:"Review active credentials and revoke access that is no longer required."},
  "Activity Monitoring":{tool:"audit",view:"actors",instruction:"Find the employee and review their recorded activity and security events."},
  "Offboarding":{tool:"users",instruction:"Open the departing employee and use the deactivation controls; verify that active access is revoked."}
 },
 "administration.audit_monitoring":{
  "Activity Logs":{tool:"audit",view:"search",instruction:"Filter the audit log to the actor, date and record being investigated."},
  "Security Alerts":{tool:"audit",view:"security",instruction:"Review security events and identify the affected identity before changing access."},
  "Investigation Tools":{tool:"audit",view:"suspicious",instruction:"Review flagged activity and trace the underlying actor and evidence."},
  "Resolution Workflow":{tool:"tasks",instruction:"Create an assigned investigation task, record corrective work, then close it with resolution evidence."},
  "Audit Archive":{tool:"audit",view:"search",instruction:"Filter the audit events, export the matching audit CSV, and retain it according to dealership policy."}
 },
 "administration.vendor_management":{
  "Connected Systems":{tool:"connections",instruction:"Review provider capabilities and configure the supported connection. Unconfigured provider slots remain clearly identified."},
  "API Management":{tool:"access",view:"all",instruction:"Review and revoke staff API credentials. Provider credentials are managed in Connected Systems."},
  "Data Mapping":{tool:"mapping",instruction:"Map source CSV headers to canonical fields, then upload through the configured connection."},
  "Health Monitoring":{tool:"health",instruction:"Review connection freshness, completeness and accuracy; inspect the failing source before retrying ingestion."},
  "Optimization":{tool:"planning",instruction:"Record the integration improvement as an owned initiative with a target and due date."}
 },
 "administration.executive_approval":{
  "Approval Queue":{tool:"governance",view:"approvals",instruction:"Review pending requests and their required approval tier."},
  "Policy Review":{tool:"roles",view:"matrix",instruction:"Review the permission matrix and explicit overrides before deciding on access or policy changes."},
  "Impact Analysis":{tool:"business",instruction:"Inspect the affected department's current metrics and data basis before a decision."},
  "Executive Decision":{tool:"governance",view:"approvals",instruction:"Approve or reject the request through its existing permission-gated approval action."},
  "Audit Trail":{tool:"governance",view:"log",instruction:"Review the recorded decisions, actors and timestamps."}
 },
 "readiness.data_connection":{
  "Integration Setup":{tool:"integration",instruction:"Create the department connection, configure its source and test it before importing records."},
  "Schema Mapping":{tool:"mapping",instruction:"Save source-to-destination column mappings before importing department records."},
  "Pipeline Monitoring":{tool:"health",instruction:"Review connection status, ingestion counts and last successful refresh."},
  "Data Validation":{tool:"health",instruction:"Inspect missing fields, duplicate records and inventory inconsistencies at their source."},
  "Readiness Activation":{tool:"policy",instruction:"Review measured confidence and record an evidence-backed forecast activation decision."}
 },
 "readiness.data_maturity":{
  "Historical Data Review":{tool:"health",instruction:"Review historical coverage and ingestion freshness by department."},
  "Density Analysis":{tool:"health",instruction:"Inspect data completeness and available sample sizes before relying on forecasts."},
  "Ledger Validation":{tool:"health",instruction:"Review ledger accuracy findings and trace exceptions to their source records."},
  "Verification Thresholds":{tool:"policy",instruction:"Set the minimum forecast confidence with review evidence. Changing the threshold requires a new activation decision."},
  "Confidence Scoring":{tool:"policy",instruction:"Review the observed score, sample basis and goal progress; record an improvement initiative when needed."}
 },
 "readiness.forecasting":{
  "Tomorrow":{tool:"forecasts",view:"tomorrow",instruction:"Review the one-day forecast and its confidence and data basis."},
  "This Week":{tool:"forecasts",view:"week",instruction:"Review the seven-day forecast and compare it with current capacity."},
  "This Month":{tool:"forecasts",view:"month",instruction:"Review the monthly forecast and operating targets."},
  "This Quarter":{tool:"forecasts",view:"quarter",instruction:"Review the quarterly forecast and its supporting sample."},
  "Scenario Modeling":{tool:"scenarios",instruction:"Adjust scenario assumptions and compare the calculated outcomes before making a plan."}
 },
 "readiness.exception_escalation":{
  "Active Alerts":{tool:"risks",instruction:"Review prioritized financial and operational risks and their source evidence."},
  "Root Cause Analysis":{tool:"recommendations",instruction:"Trace recommendations to the actual condition and threshold that generated them."},
  "Impact Assessment":{tool:"business",instruction:"Review the affected department's metrics and distinguish measured impact from estimates."},
  "Resolution Workflow":{tool:"tasks",instruction:"Create and assign corrective work, update its status and close it with evidence."},
  "Readiness Recovery":{tool:"policy",instruction:"Refresh the department's measured readiness after corrective work and verify the resulting confidence and goal progress."}
 }
};
export function SupportWorkflowPanel({workflowKey,tab,theme,onDraftOpenChange,onSavingChange}:{workflowKey:string;tab:string;theme:"dark"|"light";onDraftOpenChange:(v:boolean)=>void;onSavingChange:(v:boolean)=>void}){
 const s=supportWorkflowSteps[workflowKey]?.[tab];if(!s)return null;const props={onDraftOpenChange,onSavingChange};
 return <WorkSection title={tab} description={s.instruction}>{s.tool==="policy"?<ReadinessPolicyBoard {...props}/>:s.tool==="mapping"?<SchemaMappingBoard {...props}/>:s.tool==="users"?<Users theme={theme} {...props}/>:s.tool==="roles"?<Roles theme={theme} initialTab="matrix"/>:s.tool==="access"?<Access theme={theme} initialTab="all"/>:s.tool==="audit"?<Audit theme={theme} initialTab={s.view as "search"|"actors"|"suspicious"|"security"}/>:s.tool==="tasks"?<Tasks theme={theme}/>:s.tool==="data"?<Data theme={theme} initialTab="export"/>:s.tool==="governance"?<Governance theme={theme} initialTab={s.view as "approvals"|"log"}/>:s.tool==="connections"?<Connections theme={theme}/>:s.tool==="integration"?<Integration canManageConnections={["ADMIN","OPERATIONS"].includes(getSession()?.role||"")}/>:s.tool==="health"?<Health theme={theme}/>:s.tool==="performance"?<Performance theme={theme}/>:s.tool==="forecasts"?<Forecasts theme={theme} horizon={s.view}/>:s.tool==="scenarios"?<Scenarios theme={theme}/>:s.tool==="risks"?<Risks theme={theme}/>:s.tool==="recommendations"?<Recommendations theme={theme}/>:s.tool==="business"?<Business theme={theme}/>:<Planning theme={theme}/>}</WorkSection>;
}
