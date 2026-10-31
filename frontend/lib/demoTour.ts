// Per-department click-through coach-mark tours for the AI demo (2026-07-25, Sam: "build a click
// through, overlay tutorial (like when you first login) but build it for each dash to load as they
// click through so they can discover what each section does").
//
// Reuses components/OnboardingTour.tsx's spotlight mechanic: each step names a data-tour-id that the
// DepartmentMenuBar tags on its section buttons (via menuTourId below). When a demo visitor lands on
// a department, the workspace runs that department's tour once, spotlighting each section of the top
// menu with a plain-language callout. Steps whose target isn't on the page auto-skip, so a department
// whose menu hasn't loaded (or lacks a section) degrades gracefully.
//
// NOTE: this module must NOT import from DepartmentMenuBar (that component imports menuTourId from
// here — one-way only, no cycle). The section tokens below are kept in sync with
// DEPARTMENT_MENU_GROUPS by hand.

import type { TourStep } from "@/components/OnboardingTour";

// Stable id for a menu section button. token = a group label ("Engagement & Channels") or a direct
// item key ("overview"). Slugged so it's attribute-safe and matches on both ends.
export function menuTourId(department: string, token: string): string {
  const slug = token.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/(^-|-$)/g, "");
  return `deptmenu-${department}-${slug}`;
}

// The whole menu row (used for the intro step of every department tour).
export function menuBarTourId(department: string): string {
  return `deptmenu-${department}-bar`;
}

type SectionCopy = { token: string; title: string; description: string };

// Per-department: an intro line + one callout per section. Section tokens match the group labels /
// item keys in DepartmentMenuBar.DEPARTMENT_MENU_GROUPS.
const DEPARTMENTS: Record<string, { intro: string; sections: SectionCopy[] }> = {
  Operations: {
    intro: "Operations is the command center. This menu moves you between the store's daily boards — each section opens a live dashboard.",
    sections: [
      { token: "overview", title: "Overview", description: "A live snapshot of the whole store — readiness, the AI workforce, forecasting, and alerts." },
      { token: "Daily Execution", title: "Daily Execution", description: "Tasks, workflows, scheduling, and alerts — the day-to-day work that keeps the store moving." },
      { token: "Assets & Logistics", title: "Assets & Logistics", description: "Vehicles, inventory, and documents, shared across every department." },
      { token: "Team & Customers", title: "Team & Customers", description: "Workforce, the communications hub, and the end-to-end customer journey." },
      { token: "Intelligence", title: "Intelligence", description: "Operational reporting across the whole store." },
    ],
  },
  Sales: {
    intro: "Sales runs the retail workflow — from first lead to signed deal. Explore each section to see how it fits together.",
    sections: [
      { token: "overview", title: "Overview", description: "The sales floor at a glance — pipeline, goals, and today's priorities." },
      { token: "Pipeline & Deals", title: "Pipeline & Deals", description: "Prospects, customers, deals and desking, and appointments." },
      { token: "Communication & Engagement", title: "Communication & Engagement", description: "The communications hub, sales workflows, and the Equity Center for upgrade opportunities." },
      { token: "Inventory & Merchandising", title: "Inventory & Merchandising", description: "Live inventory and the accessories up-sell engine." },
      { token: "Intelligence", title: "Intelligence", description: "Pipeline and velocity reporting." },
    ],
  },
  Marketing: {
    intro: "Marketing is demand generation and brand. Each section is a full marketing workspace on the same customer data.",
    sections: [
      { token: "overview", title: "Overview", description: "Campaign performance and marketing health at a glance." },
      { token: "Engagement & Channels", title: "Engagement & Channels", description: "CRM, campaigns, email and SMS, PURLs, and events." },
      { token: "Digital & Media", title: "Digital & Media", description: "The website studio, advertising, inventory advertising, and social/reputation." },
      { token: "Intelligence", title: "Intelligence", description: "Marketing analytics and attribution reporting." },
      { token: "Retention & Loyalty", title: "Retention & Loyalty", description: "The customer loyalty and VIP rewards program." },
    ],
  },
  Inventory: {
    intro: "Inventory is the vehicle supply chain — acquisition through syndication.",
    sections: [
      { token: "overview", title: "Overview", description: "A live stocking overview and inventory health." },
      { token: "Stock & Sourcing", title: "Stock & Sourcing", description: "Acquisitions, intake, and lot management." },
      { token: "Pricing & Merchandising", title: "Pricing & Merchandising", description: "The pricing desk, photo and description merchandising, and syndication." },
      { token: "Disposition & Intel", title: "Disposition & Intel", description: "Wholesale disposition and turn/aging analytics." },
    ],
  },
  Service: {
    intro: "Service is fixed operations — the highest-retention part of the store.",
    sections: [
      { token: "overview", title: "Overview", description: "Fixed-ops performance and today's service drive at a glance." },
      { token: "Service Lane", title: "Service Lane", description: "Appointments, repair orders, and service customers." },
      { token: "Shop Operations", title: "Shop Operations", description: "Shop control, the parts desk, and warranty administration." },
      { token: "Intelligence", title: "Intelligence", description: "Fixed-ops and retention reporting." },
    ],
  },
  Finance: {
    intro: "Finance & F&I is the money layer — deal funding, accounting, and the full in-house-finance portfolio.",
    sections: [
      { token: "overview", title: "Overview", description: "The financial picture at a glance." },
      { token: "Origination", title: "Origination", description: "Deals and F&I, funding, compliance, and commissions." },
      { token: "Portfolio & Assets", title: "Portfolio & Assets", description: "The loan portfolio, floorplan, accounting, and assets." },
      { token: "Servicing & Recovery", title: "Servicing & Recovery", description: "Payments, collections, repossessions, and GPS / starter-interrupt devices." },
      { token: "Analytics & Intelligence", title: "Analytics & Intelligence", description: "Lender intelligence and financial reporting." },
    ],
  },
};

// Compose a department's tour: intro (spotlight the whole menu row) → one step per section → a final
// "ask the host" pointer at the chat input (a data-tour-id the workspace already tags).
export function departmentTourSteps(department: string): TourStep[] {
  const spec = DEPARTMENTS[department];
  if (!spec) return [];
  const steps: TourStep[] = [
    { targetId: menuBarTourId(department), title: `${department}`, description: spec.intro, placement: "bottom" },
    ...spec.sections.map((s) => ({
      targetId: menuTourId(department, s.token),
      title: s.title,
      description: s.description,
      placement: "bottom" as const,
    })),
    {
      targetId: "tour-chat-input",
      title: "Ask anything",
      description: "The Demo Host can see what's on your screen — ask it about any section here and it'll answer from the live data.",
      placement: "top",
    },
  ];
  return steps;
}

export function hasDepartmentTour(department: string): boolean {
  return Boolean(DEPARTMENTS[department]);
}
