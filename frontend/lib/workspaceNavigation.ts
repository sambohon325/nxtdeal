import {adminAreas,adminDestinations} from "./administrationNavigation";
export type NavigationItem = { key: string; label: string; description?: string; group?: string; onSelect?: () => void };
// Presentation only: inputs must already be permission-filtered by their existing owner.
export const navigationGroups: Record<string, Record<string, string>> = {
 BDC: {"Response & appointments":"today inquiries campaign_responses qualification handoff conversations tasks appointments service_appointments scorecard results", "Shared outreach tools":"followups audiences segments campaigns approvals plans legacy_campaigns import"},
 Operations: {"Daily work":"overview tasks scheduling alerts", "Vehicles & delivery":"vehicles inventory documents", "Customers & team":"communications customer_journey workforce payroll", "Automation & insights":"workflows reporting"},
 Sales: {"My day & follow-up":"overview tasks appointments", "Customers & leads":"prospects contacts customers segments duplicates accounts propensity", "Deals & vehicles":"pipeline deals inventory accessories equity_center", "Engagement & insights":"communications sequences workflows reporting routing"},
 Service: {"Service desk":"overview appointments customers", "Workshop":"repair_orders shop_control", "Parts & warranty":"parts warranty", "Performance":"reporting"},
 Marketing: {"Plan & campaigns":"overview planning campaigns outreach campaign_library campaign_scheduler events loyalty purls", "Audiences & lifecycle":"leads crm lists audiences_scoring email email_sms journeys journey_plans lead_import", "Content & channels":"website content file_manager social reputation social_reputation advertising inventory_advertising integrations", "Controls & performance":"communications execution conversations bdc agents runs native_workers automation analytics reporting settings"},
 Inventory: {"Stock & acquisition":"overview inventory acquisitions", "Lot & pricing":"lot_management pricing", "Market & distribution":"merchandising wholesale syndication", "Performance":"reporting"},
 Finance: {"Deals & funding":"overview deals funding lender_intelligence", "Accounting & assets":"accounting floorplan assets commissions", "Portfolio & collections":"portfolio payments collections repossessions gps_devices starter_interrupt", "Compliance & insights":"compliance reporting"},
 Administration: Object.fromEntries(Object.entries(adminAreas).map(([area,definition])=>[definition.label,Object.keys(adminDestinations).filter(key=>adminDestinations[key].area===area).join(" ")])),
 Readiness: {"Health & exceptions":"overview business_health data_health readiness exceptions", "Planning & forecasts":"forecasts simulations recommendations strategic_planning", "Performance":"reporting"},
 Network: {"Peers & performance":"overview peer_groups benchmarks gap_analysis trends reporting", "Planning & opportunities":"forecasts playbooks ai_advisors consulting_engine opportunities"},
 Marketplace: {"Explore & manage":"browse installed oem phase2 partners"},
};
export function groupNavigation(department: string, items: NavigationItem[]) {
 const definitions=navigationGroups[department] || {};
 const groups: {label:string;items:NavigationItem[]}[]=[];
 for(const item of items) {
  const label=item.group || Object.entries(definitions).find(([,keys])=>keys.split(" ").includes(item.key))?.[0] || "Other tools";
  let group=groups.find(g=>g.label===label);
  if(!group){group={label,items:[]};groups.push(group);}
  group.items.push(item);
 }
 const order=Object.keys(definitions);
 return groups.sort((a,b)=>(order.includes(a.label)?order.indexOf(a.label):999)-(order.includes(b.label)?order.indexOf(b.label):999));
}
