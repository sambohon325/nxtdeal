"use client";

// The Top Menu (session 60) -- Sam: "i want to create a menu under the color bar for
// each dash / page... well put a title over the 4 buttons and call that 'workflow'
// (like workspace)." Baked from operations.pdf's (and, for future departments,
// sales.pdf/service.pdf/etc's) "Menu Bar" spec: an 8-item DMS-style navigation row
// (Overview | Tasks | Vehicles | ... | Reporting), distinct from and positioned above
// the 4 job-workflow buttons (components/DepartmentWorkflowButtons.tsx). Fully
// data-driven off GET /menu/catalog (core/menu_catalog.py) -- renders nothing for any
// department without a catalogued menu yet (every department but Operations this
// pass), so this component is already correct for future departments without changes.
import { useEffect, useRef, useState } from "react";
import {organizeAdministration,adminDestinations,adminAreas} from "@/lib/administrationNavigation";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { MenuDash } from "@/lib/useMenuDash";
import { fetchCatalog, RIBBON_COLORS } from "@/components/DepartmentWorkflowButtons";
import { NeuralIcon } from "@/components/Icons";
import { angledClip } from "@/components/BrandAngles";
import { menuTourId, menuBarTourId } from "@/lib/demoTour";

export type MenuCatalogItem = {
  key: string;
  label: string;
  description: string;
};

export async function fetchMenuCatalog(department: string): Promise<MenuCatalogItem[]> {
  const response = await fetch(`${API_BASE}/menu/catalog?department=${encodeURIComponent(department)}`, {
    headers: { ...authHeaders() },
  });
  const data = await response.json();
  if (!response.ok || data?.error) {
    throw new Error(typeof data?.error === "string" ? data.error : "Navigation could not load.");
  }
  if (!Array.isArray(data?.items) || !data.items.every((item: unknown) =>
    item && typeof item === "object" && "key" in item && typeof item.key === "string"
      && "label" in item && typeof item.label === "string")) {
    throw new Error("Navigation response is incomplete. Please retry.");
  }
  return department === "Administration" ? organizeAdministration(data.items) : data.items;
}

// Session 72, Sam: "lets also add the worflow buttons to each of the sub menus at the
// top so they can be accesed easily while working, or maybe in a drop down, fan out
// area." -- a small "Workflows ▾" trigger on the left of the Top Menu row that fans
// out the department's 4 job-workflow buttons (same catalog/colors
// components/DepartmentWorkflowButtons.tsx's launcher row uses), so a workflow stays
// reachable while a Top Menu Dash is already open and occupying the workspace.
function WorkflowFanOut({ department, menuDash }: { department: string; menuDash: MenuDash }) {
  const [workflows, setWorkflows] = useState<{ key: string; title: string }[]>([]);
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchCatalog().then((catalog) => {
      if (!cancelled) setWorkflows((catalog[department] ?? []).map((w) => ({ key: w.key, title: w.title })));
    });
    return () => {
      cancelled = true;
    };
  }, [department]);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  if (department === "Administration" || workflows.length === 0) return null;

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        style={angledClip(8)}
        className={
          open
            ? "text-[11px] font-bold uppercase tracking-wide pl-4 pr-3 py-1 bg-brand-teal text-black transition flex items-center gap-1.5"
            : "text-[11px] font-semibold uppercase tracking-wide pl-4 pr-3 py-1 text-zinc-400 hover:text-white hover:bg-zinc-900 transition flex items-center gap-1.5"
        }
      >
        <NeuralIcon size={14} className="text-brand-blue shrink-0" />
        Workflows
        <span className={open ? "text-[9px] rotate-180 transition" : "text-[9px] transition"}>▾</span>
      </button>

      {open && (
        <div className="absolute left-0 top-full mt-1 z-30 w-56 bg-brand-charcoal border border-black/20 rounded-lg shadow-xl p-1.5 flex flex-col gap-2">
          {workflows.map((w, i) => {
            const color = RIBBON_COLORS[i % RIBBON_COLORS.length];
            const isActive =
              menuDash.active?.kind === "workflow" &&
              menuDash.active?.department === department &&
              menuDash.active?.itemKey === w.key;
            return (
              <button
                key={w.key}
                onClick={() => {
                  menuDash.open(department, w.key, "workflow");
                  setOpen(false);
                }}
                style={angledClip(6)}
                className={
                  isActive
                    ? "w-full relative flex items-center gap-2.5 text-left text-[11px] font-brand font-semibold uppercase tracking-wide bg-zinc-900 pl-4 pr-3 py-2 overflow-hidden"
                    : "w-full relative flex items-center gap-2.5 text-left text-[11px] font-brand font-semibold uppercase tracking-wide text-zinc-300 hover:bg-zinc-900 pl-4 pr-3 py-2 overflow-hidden transition"
                }
              >
                <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2"
                  style={{ background: color, clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
                />
                {w.title}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

// Sam: "on the workflow submenu, can we have it default to left justify with the
// center module (chat) - unless there's too many sub menu items, then itll push
// back to the left." A real, measured "flow to available space" rather than a
// guessed item-count threshold (this bar's real department item counts range
// 8-16 across departments, so a fixed count would misfire constantly): the
// trigger PREFERS to sit CHAT_ALIGN_OFFSET from the bar's left edge (roughly
// where the chat column starts beneath this bar, once the 344px Knowledge
// sidebar and this bar's own 24px padding are accounted for), but only when the
// row's real measured content (trigger + nav items, at their natural widths)
// actually fits the row's real available width with that offset applied --
// otherwise it collapses back to 0 so the nav items never get crowded or
// overlapped. Recomputed on any real resize of the row/trigger/items.
const CHAT_ALIGN_OFFSET = 320;

// Optional per-department consolidation of a long flat item bar into a few labeled
// dropdown groups (Sam's Finance ask: 16 items -> Overview + 4 groups). Departments
// absent from this map render the flat "/"-separated bar unchanged. Item KEYS are
// untouched, so board dispatch (MenuDashPanel) is unaffected -- this is presentation only.
export type MenuGroupEntry =
  | { type: "item"; key: string }
  | { type: "group"; label: string; keys: string[] };

export const DEPARTMENT_MENU_GROUPS: Record<string, MenuGroupEntry[]> = {
  Finance: [
    { type: "item", key: "overview" },
    { type: "group", label: "Origination", keys: ["deals", "funding", "compliance", "commissions"] },
    { type: "group", label: "Portfolio & Assets", keys: ["portfolio", "floorplan", "accounting", "assets"] },
    { type: "group", label: "Servicing & Recovery", keys: ["payments", "collections", "repossessions", "gps_devices", "starter_interrupt"] },
    { type: "group", label: "Analytics & Intelligence", keys: ["lender_intelligence", "reporting"] },
  ],
  Marketing: [
    { type: "item", key: "overview" },
    { type: "group", label: "Engagement & Channels", keys: ["crm", "campaigns", "email_sms", "purls", "events"] },
    { type: "group", label: "Growth Tools", keys: ["campaign_library", "campaign_scheduler", "lead_import", "file_manager"] },
    { type: "group", label: "Digital & Media", keys: ["website", "advertising", "inventory_advertising", "social_reputation"] },
    { type: "group", label: "Intelligence", keys: ["analytics", "reporting"] },
    { type: "group", label: "Retention & Loyalty", keys: ["loyalty"] },
  ],
  Operations: [
    { type: "item", key: "overview" },
    { type: "group", label: "Daily Execution", keys: ["tasks", "workflows", "scheduling", "alerts"] },
    { type: "group", label: "Assets & Logistics", keys: ["vehicles", "inventory", "documents"] },
    { type: "group", label: "Team & Customers", keys: ["workforce", "payroll", "communications", "customer_journey"] },
    { type: "group", label: "Intelligence", keys: ["reporting"] },
  ],
  Sales: [
    { type: "item", key: "overview" },
    { type: "group", label: "Pipeline & Deals", keys: ["prospects", "customers", "deals", "appointments"] },
    { type: "group", label: "Communication & Engagement", keys: ["communications", "workflows", "equity_center", "propensity"] },
    { type: "group", label: "Inventory & Merchandising", keys: ["inventory", "accessories"] },
    { type: "group", label: "Intelligence", keys: ["reporting"] },
  ],
  Inventory: [
    { type: "item", key: "overview" },
    { type: "group", label: "Stock & Sourcing", keys: ["inventory", "acquisitions", "lot_management"] },
    { type: "group", label: "Pricing & Merchandising", keys: ["pricing", "merchandising", "syndication"] },
    { type: "group", label: "Disposition & Intel", keys: ["wholesale", "reporting"] },
  ],
  Service: [
    { type: "item", key: "overview" },
    { type: "group", label: "Service Lane", keys: ["appointments", "repair_orders", "customers"] },
    { type: "group", label: "Shop Operations", keys: ["shop_control", "parts", "warranty"] },
    { type: "group", label: "Intelligence", keys: ["reporting"] },
  ],
  Administration: Object.entries(adminAreas).map(([area,definition])=>({type:"group" as const,label:definition.label,keys:Object.keys(adminDestinations).filter(key=>adminDestinations[key].area===area)})),
  Readiness: [
    { type: "item", key: "overview" },
    { type: "group", label: "Health & Diagnostics", keys: ["business_health", "data_health", "exceptions"] },
    { type: "group", label: "Forecasting & Simulation", keys: ["readiness", "forecasts", "simulations", "strategic_planning"] },
    { type: "group", label: "Action & Intel", keys: ["recommendations", "reporting"] },
  ],
  Network: [
    { type: "item", key: "overview" },
    { type: "group", label: "Benchmarks & Analytics", keys: ["peer_groups", "benchmarks", "gap_analysis", "trends"] },
    { type: "group", label: "Strategy & Advisory", keys: ["ai_advisors", "consulting_engine", "playbooks"] },
    { type: "group", label: "Projections & Growth", keys: ["forecasts", "opportunities", "reporting"] },
  ],
};

function MenuGroupDropdown({
  department,
  label,
  keys,
  items,
  menuDash,
}: {
  department: string;
  label: string;
  keys: string[];
  items: MenuCatalogItem[];
  menuDash: MenuDash;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClick(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [open]);

  const groupItems = keys
    .map((k) => items.find((it) => it.key === k))
    .filter((it): it is MenuCatalogItem => Boolean(it));

  if (groupItems.length === 0) return null;

  const groupActive =
    menuDash.active?.department === department &&
    groupItems.some((it) => menuDash.active?.itemKey === it.key);

  return (
    <div ref={rootRef} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        data-tour-id={menuTourId(department, label)}
        className={
          open || groupActive
            ? "text-[11px] font-bold uppercase tracking-wide px-2.5 py-1 rounded-md bg-brand-teal text-black transition flex items-center gap-1.5"
            : "text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition flex items-center gap-1.5"
        }
      >
        {label}
        <span className={open ? "text-[9px] rotate-180 transition" : "text-[9px] transition"}>▾</span>
      </button>

      {open && (
        <div className="absolute right-0 top-full mt-1 z-30 w-60 bg-brand-charcoal border border-black/20 rounded-lg shadow-xl p-1.5 flex flex-col gap-1">
          {groupItems.map((item) => {
            const isActive =
              menuDash.active?.department === department && menuDash.active?.itemKey === item.key;
            return (
              <button
                key={item.key}
                onClick={() => {
                  menuDash.open(department, item.key);
                  setOpen(false);
                }}
                title={item.description}
                className={
                  isActive
                    ? "w-full text-left text-[11px] font-semibold uppercase tracking-wide bg-brand-teal text-black px-3 py-2 rounded-md transition"
                    : "w-full text-left text-[11px] font-semibold uppercase tracking-wide text-zinc-300 hover:bg-zinc-900 px-3 py-2 rounded-md transition"
                }
              >
                {item.label}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export function DepartmentMenuBar({ department, menuDash }: { department: string; menuDash: MenuDash }) {
  const [items, setItems] = useState<MenuCatalogItem[]>([]);
  const [alignOffset, setAlignOffset] = useState(0);

  const rowRef = useRef<HTMLDivElement>(null);
  const triggerWrapRef = useRef<HTMLDivElement>(null);
  const itemsWrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    fetchMenuCatalog(department).then((result) => {
      if (!cancelled) setItems(result);
    });
    return () => {
      cancelled = true;
    };
  }, [department]);

  useEffect(() => {
    const row = rowRef.current;
    const trigger = triggerWrapRef.current;
    const itemsWrap = itemsWrapRef.current;
    if (!row || !trigger || !itemsWrap) return;

    function recompute() {
      const rowWidth = row!.offsetWidth;
      const triggerWidth = trigger!.offsetWidth;
      const itemsWidth = itemsWrap!.offsetWidth;
      const GAP_BUFFER = 24;
      const fits = CHAT_ALIGN_OFFSET + triggerWidth + itemsWidth + GAP_BUFFER <= rowWidth;
      setAlignOffset(fits ? CHAT_ALIGN_OFFSET : 0);
    }

    recompute();

    const observer = new ResizeObserver(recompute);
    observer.observe(row);
    observer.observe(trigger);
    observer.observe(itemsWrap);

    return () => observer.disconnect();
  }, [items, department]);

  if (items.length === 0) return null;

  return (
    <div className="border-b border-black/20 bg-brand-charcoal/60 px-6 py-2" data-tour-id={menuBarTourId(department)}>
      <div ref={rowRef} className="flex items-center gap-2 font-brand">
        <div
          ref={triggerWrapRef}
          style={{ marginLeft: alignOffset }}
          className="shrink-0 transition-[margin] duration-200"
        >
          <WorkflowFanOut department={department} menuDash={menuDash} />
        </div>
        <div ref={itemsWrapRef} className="flex items-center gap-1 flex-wrap justify-end ml-auto">
        {(DEPARTMENT_MENU_GROUPS[department]
          ? DEPARTMENT_MENU_GROUPS[department]
          : items.map((it): MenuGroupEntry => ({ type: "item", key: it.key }))
        ).map((entry, i) => {
          const sep = i > 0 ? <span className="text-zinc-800 mx-1 text-xs">/</span> : null;
          if (entry.type === "group" && entry.keys.length > 1) {
            return (
              <span key={"grp:" + entry.label} className="flex items-center">
                {sep}
                <MenuGroupDropdown
                  department={department}
                  label={entry.label}
                  keys={entry.keys}
                  items={items}
                  menuDash={menuDash}
                />
              </span>
            );
          }
          const directKey = entry.type === "group" ? entry.keys[0] : entry.key;
          const item = items.find((it) => it.key === directKey);
          if (!item) return null;
          const isActive = menuDash.active?.department === department && menuDash.active?.itemKey === item.key;
          // A single-key GROUP collapses to this direct button; tag it with the group LABEL so the
          // demo coach-mark tour (lib/demoTour.ts, which targets by label) can still find it.
          const tourToken = entry.type === "group" ? entry.label : item.key;
          return (
            <span key={item.key} className="flex items-center">
              {sep}
              <button
                onClick={() => menuDash.open(department, item.key)}
                title={item.description}
                data-tour-id={menuTourId(department, tourToken)}
                className={
                  isActive
                    ? "text-[11px] font-bold uppercase tracking-wide px-2.5 py-1 rounded-md bg-brand-teal text-black transition"
                    : "text-[11px] font-semibold uppercase tracking-wide px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition"
                }
              >
                {item.label}
              </button>
            </span>
          );
        })}
        </div>
      </div>
    </div>
  );
}
