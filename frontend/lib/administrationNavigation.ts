/** Navigation ownership, not an authorization policy. Only project server-permitted items. */
export const adminAreas = {
 dealership: {label:"Dealership administration",description:"Manage your people, dealership profile, business rules and staff support."},
 system: {label:"System administration",description:"Maintain integrations, security, data recovery and NXTDeal platform services."},
 related: {label:"Customer workspaces",description:"Operational tools retained here for continuity; these are customer work, not administration."},
} as const;
export type AdminArea=keyof typeof adminAreas;
export const adminDestinations:Record<string,{area:AdminArea;label:string;description:string}>={
 overview:{area:"dealership",label:"Administration home",description:"Choose dealership administration or system administration."},
 organizations:{area:"dealership",label:"Dealership profile & locations",description:"Maintain the dealership identity, address, hours, locations and defaults."},
 users:{area:"dealership",label:"Employee directory",description:"Find existing employees and inspect their account, department and activity."},
 team_management:{area:"dealership",label:"Staff accounts & onboarding",description:"Create logins and maintain staff accounts. Use the directory to investigate an existing employee."},
 roles_permissions:{area:"dealership",label:"Roles & access requests",description:"Review role policy, individual permissions and access approvals."},
 vendors:{area:"dealership",label:"Vendors & contracts",description:"Manage suppliers, software contracts, costs and renewals."},
 governance:{area:"dealership",label:"Business approvals & compliance",description:"Review dealership approvals, escalations, compliance exceptions and decision history."},
 lead_routing:{area:"dealership",label:"Lead assignment rules",description:"Assign incoming demand to teams and staff using source and routing rules."},
 workflow_automation:{area:"dealership",label:"Task & notification rules",description:"Configure dealership conditions that create tasks or notifications; review executions."},
 ai_workforce:{area:"dealership",label:"AI worker assignments",description:"Configure customer-facing worker roles, review mode and assigned queues."},
 ai_spend:{area:"dealership",label:"AI usage & staff limits",description:"Review metered AI actions and per-user limits. These are usage counts, not invoices."},
 reporting:{area:"dealership",label:"Administration reports",description:"Review staff activity and administrative results."},
 systems:{area:"system",label:"System activity",description:"Review technical activity and workflow execution status."},
 integrations:{area:"system",label:"Data connections & sync",description:"Review imported data connections, status and department coverage."},
 connections:{area:"system",label:"Channel providers",description:"Configure execution providers for email, SMS and other services; distinguish live from simulated capabilities."},
 security:{area:"system",label:"Login security",description:"Investigate sign-ins, failed attempts, lockouts and credential events."},
 identity_access:{area:"system",label:"API keys",description:"Manage programmatic access credentials. Staff roles are managed under dealership administration."},
 data_management:{area:"system",label:"Exports, backups & recovery",description:"Export data, inspect backups and perform authorized recovery operations."},
 audit_center:{area:"system",label:"Audit log & investigations",description:"Search recorded changes, review actors and investigate security flags."},
 ai_management:{area:"system",label:"AI feature controls",description:"Manage AI feature switches and inspect call outcomes and fallbacks."},
 fleet:{area:"system",label:"Agent runtime & policies",description:"Review agent activity, execution modes and automation permissions."},
 modules:{area:"system",label:"Modules & entitlements",description:"Maintain the dealer's enabled modules and enforced platform limits."},
 success_center:{area:"system",label:"NXTDeal customer success",description:"Internal NXTDeal portfolio support, dealer objectives and account reviews."},
 connect:{area:"related",label:"Customer conversation history",description:"Read shared customer communications and appointment history."},
 digital_retail:{area:"related",label:"Digital sales results",description:"Review customer self-service purchase outcomes and funnel performance."},
};
export function organizeAdministration<T extends {key:string;label:string;description:string}>(items:T[]):T[]{
 return items.map(item=>{const definition=adminDestinations[item.key];return definition?{...item,label:definition.label,description:definition.description}:item;});
}
export const adminDailyKeys=["team_management","roles_permissions","connections","audit_center"];
export const retiredAdminWorkflows:Record<string,string>={"administration.onboarding":"team_management","administration.audit_monitoring":"audit_center","administration.vendor_management":"connections","administration.executive_approval":"governance"};
