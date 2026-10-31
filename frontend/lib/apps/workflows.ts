import type { AppDef } from "./registry";

export const WORKSPACES: Record<string, { role: string; purpose: string; start: string; note?: string }> = {
  mysales: { role: "Independent salespeople", purpose: "Plan follow-ups, manage your contacts and build your personal sales page.", start: "Open my day" },
  salesapp: { role: "Sales team & sales managers", purpose: "Work today's leads, manage walk-ins, find vehicles and prepare deals.", start: "Open today's work" },
  reception: { role: "Reception & front desk", purpose: "Check in visitors, review appointments and connect people with the right teammate.", start: "Check in a visitor" },
  serviceops: { role: "Service advisors, technicians & managers", purpose: "Review repair orders, inspections, technician workload and service priorities.", start: "Open repair orders" },
  showroom: { role: "Vehicle shoppers", purpose: "Browse dealership vehicles.", start: "Browse vehicles", note: "Saved vehicles, deals and messaging need customer verification, which is not available yet." },
  mygarage: { role: "Vehicle owners", purpose: "A future home for service updates, approvals and your vehicles.", start: "View availability", note: "Customer account features are not available yet. Contact your dealership for service." },
  kiosk: { role: "Service reception", purpose: "View the service arrival and waiting-room screens.", start: "View service reception", note: "Keep this device staff-supervised. Unattended kiosk access is not enabled." },
};

export function workspaceMatches(app: AppDef, query: string): boolean {
  const info = WORKSPACES[app.slug];
  const text = [app.name, info?.role, info?.purpose, ...app.screens.map(s => s.label)].join(" ").toLowerCase();
  return query.trim().toLowerCase().split(/\s+/).every(word => text.includes(word));
}