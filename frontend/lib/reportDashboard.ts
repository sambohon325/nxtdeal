// Customizable Reporting + Overview dashboards (session 73; Overview added session 77).
// Sam: "lets go ahead and set all the reporting to be graph based... they should also
// be able to snap them into place to create their own dashboards... hide the modules
// (deactivate) - they still need to be listed somwhere theres available modules
// list... This is for each department." Then, session 77: "in all overview dashes in
// the submenus for all departments, I'd like that to be a very BI visual glance as a
// default that gives the top metrics that that department wants to see... Lets connect
// it to reporting in that if you create a report that you want to show in overview,
// you can select 'show in overview' and it shows up in available modules at the
// bottom, and then you jsut drag and drop them where you want... you should be able to
// drag and drop them in a grid system."
//
// Talks to backend/core/report_modules_api.py's GET /report-modules (Reporting's
// module catalog) + GET /overview-modules (Overview's own catalog -- one KPI card per
// top-level overview() field, plus any Reporting module flagged "Show in Overview")
// and backend/core/dashboard_layouts_api.py's GET/POST /dashboard-layout (the
// signed-in employee's own saved board -- "their own dashboards," per employee, not
// shared department-wide -- now keyed by a `board` param, "reporting" or "overview").

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// One entry in the department's report-module catalog. `data` is a plain nested JSON
// object (one "section" of that department's reporting() rollup) -- which fields
// within it are chartable is derived client-side by
// components/ReportDashboardModule.tsx, reusing the same numeric-column/label-column
// detection components/MenuDashPanel.tsx's ObjectListView already has for its
// Visualize toggle, rather than a second classifier living on the backend.
export type ReportModuleCatalogEntry = {
  module_key: string;
  label: string;
  data: Record<string, unknown>;
  // Session 77, Overview catalog entries only: "kpi" (auto-derived from that
  // department's overview() rollup) or "reporting" (a Reporting section the employee
  // flagged "Show in Overview"). Absent on plain Reporting catalog entries.
  _source?: "kpi" | "reporting";
};

export type ReportModuleMode = "graph" | "text";
export type ReportChartType = "bar" | "line" | "pie";

// One module *instance* on an employee's live board -- distinct from a catalog entry,
// since the same catalog entry can be dragged in more than once ("they can create
// several modules") with different chart types/fields/colors each time.
export type DashboardBoard = "reporting" | "overview";

export type DashboardModuleInstance = {
  id: string;
  module_key: string;
  mode: ReportModuleMode;
  chart_type: ReportChartType;
  color: string;
  span: 1 | 2;
  order: number;
  fields: string[];
  // Session 77: only meaningful on a "reporting"-board instance -- flips this section
  // into the Overview board's own available-modules tray (core/report_modules.py's
  // get_overview_modules). Always false/ignored on an "overview"-board instance.
  show_in_overview?: boolean;
};

export type DashboardLayout = {
  id: string | null;
  department: string;
  board: DashboardBoard;
  modules: DashboardModuleInstance[];
  updated_at: string | null;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();

  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && data.error) || "Unable to reach NXTDeal backend.");
  }

  return data as T;
}

export async function fetchReportModules(department: string): Promise<ReportModuleCatalogEntry[]> {
  const res = await fetch(`${API_BASE}/report-modules?department=${encodeURIComponent(department)}`, {
    headers: { ...authHeaders() },
  });
  const data = await handle<{ department: string; modules: ReportModuleCatalogEntry[] }>(res);
  return data.modules ?? [];
}

// Session 77: Overview's own catalog -- same {department, modules} shape as
// /report-modules, so components/ReportDashboardBuilder.tsx can treat both boards
// identically once it has the right fetch function for its `board` prop.
export async function fetchOverviewModules(department: string): Promise<ReportModuleCatalogEntry[]> {
  const res = await fetch(`${API_BASE}/overview-modules?department=${encodeURIComponent(department)}`, {
    headers: { ...authHeaders() },
  });
  const data = await handle<{ department: string; modules: ReportModuleCatalogEntry[] }>(res);
  return data.modules ?? [];
}

export async function fetchDashboardLayout(
  department: string,
  board: DashboardBoard = "reporting"
): Promise<DashboardLayout> {
  const res = await fetch(
    `${API_BASE}/dashboard-layout?department=${encodeURIComponent(department)}&board=${encodeURIComponent(board)}`,
    { headers: { ...authHeaders() } }
  );
  return handle<DashboardLayout>(res);
}

export async function saveDashboardLayout(
  department: string,
  modules: DashboardModuleInstance[],
  board: DashboardBoard = "reporting"
): Promise<DashboardLayout> {
  const res = await fetch(`${API_BASE}/dashboard-layout`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ department, modules, board }),
  });
  return handle<DashboardLayout>(res);
}
