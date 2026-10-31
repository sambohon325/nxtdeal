"use client";
import { DepartmentDailyNavigation } from "./DepartmentDailyNavigation";
import { WorkspaceNotifications } from "./WorkspaceNotifications";
import { BdcWorkspace, bdcDailyDestinations } from "./bdc/BdcWorkspace";
import { bdcDestination } from "@/lib/bdcNavigation";
import { CommsWorkspaceMount } from "./CustomerCommsPanel";
import { departmentWorkDescription } from "@/lib/departmentWork";
import { OverviewHeader, OverviewMetrics, OverviewActions } from "./DepartmentOverview";
import {ReadinessDay} from "./ReadinessDay";
import {OperationsDay} from "./OperationsDay";
import {AdministrationDay} from "./AdministrationDay";
import {adminDailyKeys,retiredAdminWorkflows,adminAreas,adminDestinations} from "@/lib/administrationNavigation";
import {DispatchDay} from "./DispatchDay";
import {InventoryDay} from "./InventoryDay";
import {ServiceDay} from "./ServiceDay";
import { FinanceDay } from "./FinanceDay";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { WorkspaceNavigation } from "./WorkspaceNavigation";
import { AppearanceDialog, GlassBrand, GlassIcon, useGlassAppearance } from "./GlassAppearance";
import { getSession, clearSession, resolveStaffSession, subscribeStaffSessionChange, type Session } from "@/lib/auth";
import { getOperationsOverview, type OperationsOverview } from "@/lib/operationsOverview";
import { WorkspaceIcon } from "./WorkspaceIcon";
import {ContextHelp,GuidedWalkthrough,type WalkthroughContext} from "./GuidedWalkthrough";
import { HelpWorkspace, WelcomeTour } from "./HelpWorkspace";

import { VinLookupWidget } from "@/components/VinLookupWidget";
import { fetchCatalog, WorkflowWindowBody, type Catalog, type WorkflowDef } from "@/components/DepartmentWorkflowButtons";
import { AccountSettingsBody, type AccountTabKey } from "@/components/AccountSettings";
import { ReadinessIntegrationPanel } from "@/components/ReadinessIntegrationPanel";
import { NetworkBenchmarkPanel } from "@/components/NetworkBenchmarkPanel";
import {useEngagement} from "@/components/extras/useEngagement";
import { ProgressLink } from "@/components/extras/ProgressLink";
import { DealershipLab } from "@/components/lab/DealershipLab";
import { MenuDashBody } from "@/components/MenuDashPanel";
import { EntityDashPanel } from "@/components/EntityDashPanel";
import { EntityLinkActionsProvider } from "@/lib/entityLinkContext";
import { WorkspaceToolsContext } from "@/lib/workspaceTools";
import { fetchMenuCatalog, type MenuCatalogItem } from "@/components/DepartmentMenuBar";
import { DepartmentTimeView } from "@/components/DepartmentTimeView";
import styles from "./CommandCenter.module.css";
import { MarketingWorkspace } from "@/components/marketing/MarketingWorkspace";
import { SalesCrmWorkspace } from "@/components/sales/SalesCrmWorkspace";

const timeOffsets = [-7, 0, 1, 7, 30, 90];
const timePeriods = ["last_week", "current", "tomorrow", "next_week", "next_month", "next_quarter"];
const departments = ["Operations", "Sales", "BDC", "Marketing", "Inventory", "Service", "Finance"];
const gates: Record<string, string[] | null> = {
  Operations: ["workload", "escalations", "manager"], Sales: ["leaderboard", "pipeline", "followup", "salesperson"],
  BDC: ["bdc", "leaderboard", "pipeline", "followup", "salesperson", "service"], Marketing: ["pipeline", "followup"], Inventory: null, Service: ["service"], Finance: ["finance"],
};
type Detail = { kind: "connections" | "benchmarks" } | { kind: "account"; tab: AccountTabKey } | { kind: "workflow"; workflow: WorkflowDef } | { kind: "menu"; department: string; item: string } | { kind: "entity"; id: string } | { kind: "priority"; key: string; title: string } | { kind: "evidence" | "guide" | "help" };
const priorities = [
  { key: "deliveries_at_risk", title: "Deliveries at Risk", icon: "car", color: "#00d5ff", action: "View list" },
  { key: "vehicles_missing_titles", title: "Vehicles Missing Titles", icon: "file", color: "#a591ff", action: "View list" },
  { key: "compliance_violations", title: "Compliance Violations", icon: "shield", color: "#00dfdc", action: "View workflow" },
  { key: "vehicles_awaiting_inspection", title: "Awaiting Inspection", icon: "search", color: "#efcd74", action: "View details" },
  { key: "wholesale_candidates_needing_decision", title: "Wholesale Decision Needed", icon: "dollar", color: "#3ce3a1", action: "View opportunities" },
] as const;

function Icon({ name }: { name: string }) {
  const paths: Record<string, ReactNode> = {
    car: <><path d="m5 8 2-5h10l2 5M4 8h16v10H4zM6 18v3m12-3v3M4 13h16" /><path d="M6 10h2m8 0h2" /></>,
    file: <><path d="M6 2h8l5 5v15H6zM14 2v6h5M9 12h7m-7 4h7" /></>,
    shield: <><path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6z" /><path d="m7 11 3 3 7-7" /></>,
    search: <><circle cx="10" cy="10" r="7" /><path d="m15 15 7 7" /></>,
    dollar: <><circle cx="12" cy="12" r="10" /><path d="M16 7h-5a3 3 0 0 0 0 6h2a3 3 0 0 1 0 6H8m4-15v17" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 2v6m10-6v6M3 11h18" /></>,
    chart: <path d="M4 21V12m8 9V7m8 14V2" />,
    list: <path d="M8 5h14M8 12h14M8 19h14M2 5h1M2 12h1M2 19h1" />,
  };
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name] ?? paths.list}</svg>;
}

function DetailDialog({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current; dialog?.showModal(); return () => dialog?.close(); }, []);
  return <dialog ref={ref} className={styles.dialog} onCancel={onClose} onClick={e => { if (e.target === e.currentTarget) onClose(); }} aria-label={title}>
    <div className={styles.dialogHeader}><h2>{title}</h2><button onClick={onClose} aria-label="Close details">×</button></div>
    <div className={styles.dialogBody}>{children}</div>
  </dialog>;
}

export function CommandCenter({ initialDepartment = "Operations" }: { initialDepartment?: "Operations" | "Administration" | "Readiness" | "Network" | "Extras" }) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  const [progressTheme,setProgressTheme]=useState("glacier");
  const [department, setDepartment] = useState("Operations");
  const rewardsEnabled=useEngagement(department, !!session);
  const [taskSearch, setTaskSearch] = useState("");
  const [overview, setOverview] = useState<OperationsOverview | null>(null);
  const [error, setError] = useState("");
  const [detail, setDetail] = useState<Detail | null>(null);
  const [scenario, setScenario] = useState("Base Case");
  const [horizon, setHorizon] = useState(0);
  const [timelineOpen, setTimelineOpen] = useState(false);
  const [intervention, setIntervention] = useState("Do nothing");
  const [now, setNow] = useState<Date | null>(null);
  const [retry, setRetry] = useState(0);
  const [workflows, setWorkflows] = useState<Catalog>({});
  const [workflowError, setWorkflowError] = useState("");
  const [menuItems, setMenuItems] = useState<MenuCatalogItem[]>([]);
  const [navigationHost, setNavigationHost] = useState<HTMLDivElement | null>(null);
  const [navigationOpen, setNavigationOpen] = useState(false);
  useEffect(() => {
    // Lab destinations are portaled into the rail. React events follow the
    // portal's component ancestry, so the aside's handler cannot receive them.
    if (!navigationHost) return;
    const closeAfterSelection = (event: MouseEvent) => {
      if (event.target instanceof Element && event.target.closest('.workflow-destination')) setNavigationOpen(false);
    };
    navigationHost.addEventListener('click', closeAfterSelection, true);
    return () => navigationHost.removeEventListener('click', closeAfterSelection, true);
  }, [navigationHost]);
  const [menuError, setMenuError] = useState("");
  const glassRoot = useRef<HTMLDivElement>(null);
  const appearance = useGlassAppearance();
  const [appearanceOpen, setAppearanceOpen] = useState(false);
  const [contextHelp,setContextHelp]=useState(false);
  const [walkthrough,setWalkthrough]=useState<WalkthroughContext|null>(null);
  const [tourRevision, setTourRevision] = useState(0);
  const [utility, setUtility] = useState<"vin" | "knowledge" | "help" | null>(null);
  const timelineRef = useRef<HTMLInputElement>(null);
  const [homeRevision, setHomeRevision] = useState(0);
  const [campaignDraftOpen, setCampaignDraftOpen] = useState(false);
  const [pendingExit, setPendingExit] = useState<{ run: () => void } | null>(null);
  const [employeeDraftOpen, setEmployeeDraftOpen] = useState(false);
  const [employeeSaving, setEmployeeSaving] = useState(false);
  const [campaignSaving, setCampaignSaving] = useState(false);
  const [navigationCollapsed, setNavigationCollapsed] = useState(false);
  const [labDraftOpen,setLabDraftOpen]=useState(false);
  const [labSaving,setLabSaving]=useState(false);
  const [recordOrigin,setRecordOrigin] = useState<Detail|null>(null);
  const anySaving = employeeSaving || campaignSaving || labSaving;
  const navigate = (run: () => void) => {
    if (labDraftOpen || campaignDraftOpen || employeeDraftOpen || anySaving) setPendingExit({ run }); else run();
  };
  useEffect(() => {
    if (!labDraftOpen && !campaignDraftOpen && !employeeDraftOpen && !anySaving) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [labDraftOpen, campaignDraftOpen, employeeDraftOpen, anySaving]);
  useEffect(() => {
    const current = getSession();
    if (!current) { router.replace("/"); return; }
    let invalidated = false;
    const controller = new AbortController();
    setSession(null);
    resolveStaffSession(current, controller.signal).then(result => {
      if (invalidated) return;
      if (result.mustChangePassword) { router.replace("/change-password"); return; }
      const verified = result.session;
      if (initialDepartment === "Administration" && verified.role !== "ADMIN") { router.replace("/workspace"); return; }
      setSession(verified); setNow(new Date());
      try {
        const saved = Number(sessionStorage.getItem(`nxtdeal-time:${verified.employeeId}`));
        if (timeOffsets.includes(saved)) setHorizon(saved);
      } catch { /* Storage may be unavailable; in-memory navigation still works. */ }
      const visible = departments.filter(d => gates[d] === null || gates[d]?.some(k => verified.allowedDashboards?.includes(k)));
      const start = initialDepartment === "Operations" ? visible[0] ?? "Inventory" : initialDepartment;
      setDepartment(start);
      if (initialDepartment !== "Operations") setDetail({ kind: "menu", department: start, item: "overview" });
    }).catch(() => { if (!invalidated) router.replace("/"); });
    const unsubscribe = subscribeStaffSessionChange(() => {
      if (invalidated) return;
      invalidated = true;
      controller.abort();
      setSession(null);
      setOverview(null);
      setDetail(null);
      window.location.reload();
    });
    return () => { invalidated = true; controller.abort(); unsubscribe(); };
  }, [router, initialDepartment]);
  useEffect(() => {
    if (!session) return;
    try { sessionStorage.setItem(`nxtdeal-time:${session.employeeId}`, String(horizon)); } catch { /* Optional persistence. */ }
  }, [session, horizon]);
  const canSeeOperations = Boolean(session?.allowedDashboards?.some(k => gates.Operations?.includes(k)));
  useEffect(() => {
    if (!session || !canSeeOperations) return;
    let active = true; setError("");
    getOperationsOverview().then(data => { if (active) setOverview(data); }).catch(err => { if (active) setError(err instanceof Error ? err.message : "Unable to load current priorities."); });
    return () => { active = false; };
  }, [session, canSeeOperations, retry]);
  useEffect(() => {
    if (!session) return;
    if (["Network", "Extras"].includes(department)) { setMenuItems([]); return; }
    let active = true; setMenuItems([]); setMenuError("");
    (department === "BDC" ? Promise.all([fetchMenuCatalog("Sales"), fetchMenuCatalog("Marketing"), fetchMenuCatalog("Service")]).then(groups => groups.flatMap((items,index)=>items.map(item=>({...item,key:`${["sales","marketing","service"][index]}:${item.key}`})))) : fetchMenuCatalog(department)).then(items => {
      if (active) setMenuItems(items.filter(item => !(department === "Network" && item.key === "ai_advisors")));
    }).catch(() => { if (active) setMenuError("Navigation could not load. Please retry."); });
    return () => { active = false; };
  }, [session, department, retry]);
  useEffect(() => {
    if (!session) return;
    if (["Network", "Extras"].includes(department)) { setWorkflowError(""); return; }
    let active = true;
    fetchCatalog().then(data => { if (active) { setWorkflows(data); setWorkflowError(""); } })
      .catch(() => { if (active) setWorkflowError("Unable to load department workflows."); });
    return () => { active = false; };
  }, [session, retry, department]);
  useEffect(() => {
    const root = glassRoot.current;
    if (!root) return;
    let frame = 0;
    const place = () => {
      root.querySelectorAll<HTMLElement>(".departments, .side-nav, nav[aria-label='Sales CRM navigation'], nav[aria-label='Marketing workspaces']").forEach(nav => {
        const active = nav.querySelector<HTMLElement>("button[aria-current='page']");
        let indicator = nav.querySelector<HTMLElement>(":scope > .selection");
        if (!active) { if (indicator) indicator.hidden = true; return; }
        if (!indicator) { indicator = document.createElement("span"); indicator.className = "selection"; indicator.setAttribute("aria-hidden", "true"); nav.prepend(indicator); }
        indicator.hidden = false;
        indicator.style.width = `${active.offsetWidth}px`; indicator.style.height = `${active.offsetHeight}px`;
        indicator.style.transform = `translate(${active.offsetLeft}px,${active.offsetTop}px)`;
      });
    };
    const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(place); };
    const observer = new MutationObserver(schedule); observer.observe(root, {subtree:true,childList:true,attributes:true,attributeFilter:["aria-current"]});
    const resize = new ResizeObserver(schedule); resize.observe(root); schedule();
    return () => { observer.disconnect(); resize.disconnect(); cancelAnimationFrame(frame); root.querySelectorAll(".selection").forEach(el => el.remove()); };
  }, [session]);
  // Each destination owns its reading position. Returning from a record restores
  // the list; opening another department starts at that page's heading.
  const readingPositions = useRef(new Map<string, number>());
  const readingKey = `${department}:${detail?.kind === "menu" ? detail.item : detail?.kind === "entity" ? detail.id : detail?.kind ?? "today"}`;
  useEffect(() => {
    const root = glassRoot.current;
    if (!root) return;
    const frame = requestAnimationFrame(() => root.scrollTo({top:readingPositions.current.get(readingKey) ?? 0, behavior:"instant"}));
    return () => {cancelAnimationFrame(frame);readingPositions.current.set(readingKey,root.scrollTop);};
  }, [readingKey]);
  const hasMenuItem = (key: string) => menuItems.some(item => item.key === key);
  const openMenuNow = (item: string, dept = department) => {
    glassRoot.current?.querySelector('[aria-label="Account menu"]')?.closest("details")?.removeAttribute("open");
    const bdc = bdcDestination(dept,item); if(bdc){dept="BDC";item=bdc;}
    if (dept !== department) setTaskSearch(""); if (dept !== department) setMenuItems([]);
    setDepartment(dept); setTimelineOpen(false); setDetail({ kind: "menu", department: dept, item });
  };
  const openMenu = (item: string, dept = department) => navigate(() => openMenuNow(item, dept));
  const openEntity = (id: string) => navigate(() => { if(detail?.kind!=="entity")setRecordOrigin(detail); setTimelineOpen(false); setDetail({ kind: "entity", id }); });
  if (!session) return <main className={styles.loading}>Opening your dealership…</main>;
  const visible = [...departments.filter(d => gates[d] === null || gates[d]?.some(k => session.allowedDashboards?.includes(k))), "Network", ...(initialDepartment === "Readiness" || (initialDepartment === "Extras" && (rewardsEnabled || session.role === "ADMIN")) ? [initialDepartment] : [])];
  const departmentLabel = department === "Network" ? "Dealer Lab" : department === "BDC" ? "BDC Center" : department;
  const directoryName = session.employeeId === "NXT-PREVIEW" ? "Sam" : undefined;
  const firstName = directoryName?.split(" ")[0] || (session.employeeId === "NXT-PREVIEW" ? "Sam" : "");
  const greeting = !now ? "Welcome back" : now.getHours() < 12 ? "Good morning" : now.getHours() < 18 ? "Good afternoon" : "Good evening";
  const future = new Date(now ?? Date.now()); future.setDate(future.getDate() + horizon);
  const dateLabel = now?.toLocaleDateString(undefined, { weekday: "short", month: "short", day: "numeric", year: "numeric" }) ?? "";
  const bucket = detail?.kind === "priority" && overview ? overview.action_center[detail.key as keyof typeof overview.action_center] : null;
  const records = bucket && "deals" in bucket ? bucket.deals : bucket && "vehicles" in bucket ? bucket.vehicles : [];
  const specialistNavigation = ["Sales", "Marketing", "BDC"].includes(department) && detail?.kind === "menu" && horizon === 0;
  const showDepartmentSidebar = !specialistNavigation && !["Network", "Extras"].includes(department);
  const title = detail?.kind === "connections" ? "Data connections" : detail?.kind === "benchmarks" ? "Network benchmarks" : detail?.kind === "account" ? "Account settings" : detail?.kind === "workflow" ? detail.workflow.title : detail?.kind === "menu" ? `${detail.department} · ${detail.item.replaceAll("_", " ")}` : detail?.kind === "priority" ? detail.title : detail?.kind === "entity" ? "Record details" : detail?.kind === "help" ? "Help & learning" : detail?.kind === "guide" ? "Your dealership, at a glance" : "Model & Evidence";

  return <WorkspaceToolsContext.Provider value={false}><EntityLinkActionsProvider openInDash={openEntity}>
    <div ref={glassRoot} data-nxt-glass data-theme={appearance.theme} data-background={appearance.background} className={appearance.settings.motion ? "" : "no-motion"} style={appearance.style} data-progress-theme={progressTheme}>
      <div className="wallpaper" aria-hidden="true"/><div className="ambient" aria-hidden="true"><i/><i/><i/></div>
      <div className={`workspace ${navigationCollapsed ? "navigation-collapsed" : ""}`}>
      <a className={styles.skipLink} href="#dealership-content">Skip to workspace</a>
      <aside id="workflow-navigation" className={`sidebar glass ${navigationOpen ? "rail-open" : ""}`} aria-label="Dealership workflows" tabIndex={0} onClick={event => { if ((event.target as HTMLElement).closest(".workflow-destination")) setNavigationOpen(false); }}>
        <button className="tray-close" aria-label="Collapse navigation" aria-controls="workflow-navigation" onClick={() => { setNavigationCollapsed(true); setNavigationOpen(false); }}><Icon name="list"/><span>Collapse navigation</span></button>
        <button className="brand" aria-label="Return to overview" onClick={() => navigate(() => { setDetail(null); setHorizon(0); })}><GlassBrand/></button>
        <p className="eyebrow">DEALERSHIP WORKSPACE</p>
        <button className="today-link" aria-label="Today" title="Today" aria-current={!detail || (detail.kind === "menu" && detail.item === "overview") ? "page" : undefined} onClick={() => navigate(() => { setHorizon(0); setHomeRevision(v => v + 1); if (department === "Operations") setDetail(null); else openMenuNow("overview"); setTimelineOpen(false); setNavigationOpen(false); })}><GlassIcon name="home"/><span>Today</span></button>
        <div ref={setNavigationHost} />
        {showDepartmentSidebar && <WorkspaceNavigation key={department} department={department} items={menuItems} active={detail?.kind === "menu" ? detail.item : undefined} onSelect={openMenu}/>}
        {menuError && <p role="alert">Navigation unavailable. <button onClick={() => setRetry(v => v + 1)}>Retry</button></p>}
        {department === "Administration" && <WorkspaceNavigation department="Administration tools" items={[
          {key:"extras",label:"Extras & tools",group:"Extras & tools",onSelect:()=>navigate(()=>{setHorizon(0);openMenuNow("overview","Extras");})},
          {key:"knowledge",label:"Knowledge Base",group:"Extras & tools",onSelect:()=>navigate(()=>{setHorizon(0);setTimelineOpen(false);setDetail({kind:"help"});})},
        ]}/>}
        <div className="sidebar-screen-controls" role="group" aria-label="Screen controls"><button className="icon-button glass" title="Switch color mode" aria-label={`Switch to ${appearance.theme === "dark" ? "light" : "dark"} mode`} onClick={() => appearance.setSettings(v => ({...v, mode: appearance.theme === "dark" ? "light" : "dark"}))}><GlassIcon name={appearance.theme === "dark" ? "sun" : "moon"}/></button><button className="icon-button glass" title="Customize appearance" aria-label="Customize appearance" onClick={() => setAppearanceOpen(true)}><GlassIcon name="sliders"/></button><span>Screen controls</span></div>
        <div className="sidebar-footer">{department}<small>POWERED BY CHRONO</small></div>
      </aside>
      <div className="content">
      <header className="topbar">

        <button className="icon-button glass desktop-tray-toggle" aria-label={navigationCollapsed ? "Expand navigation" : "Collapse navigation"} aria-expanded={!navigationCollapsed} aria-controls="workflow-navigation" onClick={() => setNavigationCollapsed(v => !v)}><Icon name="list"/></button>
        <button className="icon-button glass workflow-toggle" aria-label="Workflows" aria-expanded={navigationOpen} aria-controls="workflow-navigation" onClick={() => setNavigationOpen(v => !v)}><Icon name="list" />Workflows</button>
        <nav className="departments glass" aria-label="Departments">{visible.map(d => <button key={d} title={d === "Network" ? "Dealer Lab" : d === "BDC" ? "BDC Center" : d} className={d === department ? "active" : ""} aria-current={d === department ? "page" : undefined} onClick={() => navigate(() => { setHorizon(0); openMenuNow("overview", d); })}><WorkspaceIcon name={d}/><span>{d === "Network" ? "Dealer Lab" : d === "BDC" ? "BDC Center" : d}</span></button>)}</nav>
        <div className="header-actions"><a className="icon-button glass" href="/apps" target="_blank" rel="noopener noreferrer" title="NXTDeal Apps (opens in a new tab)" aria-label="NXTDeal Apps (opens in a new tab)"><WorkspaceIcon name="apps"/></a><button className="icon-button glass" title="VIN Lookup" aria-label="VIN Lookup" onClick={()=>setUtility("vin")}><WorkspaceIcon name="vin"/></button><button className="icon-button glass" title="Help" aria-label="Help" onClick={()=>setContextHelp(true)}><WorkspaceIcon name="help"/></button><WorkspaceNotifications key={`${session.apiBaseUrl}:${session.employeeId}`} session={session} onOpen={openEntity} onSettings={()=>navigate(()=>{setTimelineOpen(false);setDetail({kind:"account",tab:"notifications"});})}/>
<div className={styles.account}><details><summary aria-label="Account menu"><span>{firstName ? firstName[0] : session.employeeId[0]}</span><span aria-hidden="true">⌄</span></summary><div><strong>{directoryName || session.employeeId}</strong><small>{session.role}</small><ProgressLink onTheme={setProgressTheme}/>{session.role === "ADMIN" && <button onClick={e => { e.currentTarget.closest("details")?.removeAttribute("open"); navigate(() => { setHorizon(0); openMenuNow("overview", "Administration"); }); }}>Administration</button>}<button onClick={() => navigate(() => { setTimelineOpen(false); setDetail({ kind: "account", tab: "profile" }); })}>Profile &amp; Password</button><button onClick={() => navigate(() => { setTimelineOpen(false); setDetail({ kind: "account", tab: "notifications" }); })}>Notifications</button><button onClick={() => openMenu("browse", "Marketplace")}>Marketplace</button><button onClick={() => navigate(() => router.push("/agents"))}>Department Agents</button>{session.isSystemAdmin === true && <button onClick={() => navigate(() => router.push("/data-bridge"))}>Dealer Data Bridge</button>}<button onClick={e => { e.currentTarget.closest("details")?.removeAttribute("open"); navigate(() => { setHorizon(0); openMenuNow("overview", "Readiness"); }); }}>Readiness</button><button onClick={() => navigate(() => { clearSession(); router.push("/"); })}>Sign out</button></div></details></div></div>
      </header>
      <main id="dealership-content" tabIndex={-1} className="main-panel glass nxt-workspace-content">
        {pendingExit && <section role="alert" className="glass" style={{ padding: 16, marginBottom: 16 }}><h3>{anySaving ? "Changes are still saving" : labDraftOpen ? "Leave your unsaved Lab changes?" : employeeDraftOpen ? (department === "Inventory" ? "Leave unfinished listing work?" : department === "Service" ? "Leave unfinished service work?" : "Leave unfinished employee work?") : campaignDraftOpen ? "Leave your unsaved campaign?" : "Continue to the selected destination?"}</h3><p>{anySaving ? "Wait for the save result below. A submitted change cannot be discarded by navigating away." : labDraftOpen || employeeDraftOpen || campaignDraftOpen ? "Your draft is still open below. Keep editing, or discard it and continue to the selected destination." : "The save has finished. Review its result below before continuing."}</p><button className="soft-button" onClick={() => setPendingExit(null)}>{anySaving ? "Stay with save" : labDraftOpen ? "Keep editing Lab changes" : employeeDraftOpen ? (department === "Inventory" ? "Keep editing listing" : department === "Service" ? "Keep editing service work" : "Keep editing employee") : campaignDraftOpen ? "Keep editing campaign" : "Stay here"}</button><button disabled={anySaving} className="soft-button" onClick={() => { if(anySaving)return; const next = pendingExit; setPendingExit(null); setLabDraftOpen(false); setCampaignDraftOpen(false); setEmployeeDraftOpen(false); setHomeRevision(v => v + 1); next.run(); }}>{anySaving ? "Wait for save to finish" : labDraftOpen ? "Discard Lab changes and continue" : employeeDraftOpen ? (department === "Inventory" ? "Discard listing work and continue" : department === "Service" ? "Discard service work and continue" : "Discard employee work and continue") : campaignDraftOpen ? "Discard campaign and continue" : "Continue"}</button></section>}
        <div className="page-top"><div><nav className="breadcrumb" aria-label="Breadcrumb"><button onClick={()=>navigate(()=>{setHorizon(0);setDetail(null);})}>Today</button><span aria-hidden="true">/</span><button onClick={()=>openMenu("overview",department)}>{departmentLabel}</button>{detail && detail.kind !== "menu" && <><span aria-hidden="true">/</span><span aria-current="page">{title}</span></>}</nav>{!detail && <h2>Today</h2>}</div>{detail?.kind!=="help"&&<DepartmentDailyNavigation key={department} department={departmentLabel} items={department === "Administration" ? adminDailyKeys.flatMap(key=>{const item=menuItems.find(row=>row.key===key);return item?[{key,label:item.label,onSelect:()=>openMenu(key)}]:[]}) : department === "BDC" ? bdcDailyDestinations(menuItems,session.role).filter(item=>["inquiries","conversations","followups","appointments","service_appointments","campaign_responses"].includes(item.key)).map(item=>({...item,onSelect:()=>openMenu(item.key)})) : (workflows[department]||[]).map(workflow=>({key:workflow.key,label:workflow.title,onSelect:()=>navigate(()=>{setHorizon(0);setTimelineOpen(false);setDetail({kind:"workflow",workflow});})}))} active={detail?.kind === "workflow" ? detail.workflow.key : ["BDC","Administration"].includes(department) && detail?.kind === "menu" ? detail.item : undefined}/>}</div>
        {!detail && <section className="welcome"><div><div className="eyebrow">A CLEAR VIEW OF WHAT&apos;S NEXT</div><h1>{greeting}{firstName ? `, ${firstName}` : ""}<span>.</span></h1><p>Your dealership. At a glance.</p></div><div className="today-date">{dateLabel}</div></section>}
        {horizon !== 0 && <div className={styles.compactTimeBar}><span>{horizon < 0 ? "Last 7 days" : `${horizon} days ahead`}</span><button onClick={() => setHorizon(0)}>Return to today</button></div>}
        <section id="shared-timeline" hidden={!timelineOpen} className={styles.exploration} aria-labelledby="scenario-heading">
          <div className={styles.hero}><p>Powered by Chrono</p><h2 id="scenario-heading">See what happens next.</h2><span>Adjust. Compare. Decide with confidence.</span></div>
          <div className={styles.controls}><label>What if we… <select value={intervention} onChange={e => setIntervention(e.target.value)}><option>Do nothing</option><option>Prioritize deliveries</option><option>Resolve title exceptions</option><option>Accelerate inspections</option></select></label><div className={styles.scenarios} aria-label="Illustrative scenarios">{["Base Case", "Best Case", "Conservative"].map(s => <button key={s} aria-pressed={scenario === s} className={scenario === s ? styles.selectedScenario : ""} onClick={() => setScenario(s)}>{s}</button>)}</div><button className={styles.evidence} onClick={() => navigate(() => setDetail({ kind: "evidence" }))}><Icon name="chart" />Model & Evidence <span>→</span></button></div>
          <div className={styles.chart}>
            <span className={styles.previewLabel}>Illustrative scenario · not a live forecast</span>
            <svg viewBox="0 0 1300 235" preserveAspectRatio="none" role="img" aria-label={`${scenario} illustration for ${intervention}. Selected offset: ${horizon} days. No model prediction connected.`}>
              <defs><radialGradient id="nxt-glow"><stop stopColor="#00aeff" stopOpacity=".3" /><stop offset="1" stopColor="#00aeff" stopOpacity="0" /></radialGradient><filter id="nxt-point-glow"><feGaussianBlur stdDeviation="4" /></filter></defs>
              <circle cx="590" cy="130" r="108" fill="url(#nxt-glow)" /><circle cx="590" cy="130" r="73" fill="none" stroke="#49b7ec" strokeOpacity=".4" />
              <g fill="none" stroke="#6dcaff" strokeWidth="1"><path d="M55 75C340 75 350 110 590 130" /><path d="M55 130H590" /><path d="M55 185C340 185 350 150 590 130" /></g>
              <g fill="#a6d5ee" fontSize="12" letterSpacing="1"><text x="55" y="62">Market trends</text><text x="55" y="118">Your historical data</text><text x="55" y="173">Current business activity</text></g>
              <path d="M590 48V208" stroke="#a8dfff" strokeDasharray="5 5" opacity=".6" /><text x="590" y="35" textAnchor="middle" fill="#d4ecff" fontSize="12" letterSpacing="3">TODAY</text>
              <g fill="none" strokeDasharray="6 6"><path d={`M590 130C760 130 850 ${90-horizon/5} 1090 ${65-horizon/4}`} stroke="#c4eeff" strokeWidth={scenario === "Best Case" ? 4 : 2} opacity={scenario === "Conservative" ? .35 : 1} /><path d="M590 130H1090" stroke="#a8d4fb" strokeWidth={scenario === "Base Case" ? 3 : 1.5} /><path d={`M590 130C780 130 920 ${165+horizon/7} 1090 ${180+horizon/6}`} stroke="#90b7d5" strokeWidth={scenario === "Conservative" ? 3 : 1.5} /></g>
              <g fill="#c5efff"><circle cx="590" cy="130" r="17" filter="url(#nxt-point-glow)" /><circle cx="590" cy="130" r="7" fill="white" /><circle cx="1090" cy={65-horizon/4} r="5" /><circle cx="1090" cy="130" r="5" /><circle cx="1090" cy={180+horizon/6} r="5" fill="#ff748b" /></g>
              <g fill="#bad7ed" fontSize="14"><text x="1115" y={70-horizon/4}>Upside scenario</text><text x="1115" y="135">Baseline</text><text x="1115" y={185+horizon/6}>Downside scenario</text></g>
            </svg>
          </div>
          <div className={styles.timeline}><div><label htmlFor="scenario-horizon">{horizon === 0 ? "Today" : `${Math.abs(horizon)} days ${horizon < 0 ? "ago" : "ahead"}`}</label><input ref={timelineRef} id="scenario-horizon" aria-label="Shared time period" type="range" min="0" max="5" step="1" value={timeOffsets.indexOf(horizon)} aria-valuetext={horizon === -7 ? "Last 7 days" : horizon === 0 ? "Today" : `${horizon} days ahead`} onChange={e => { const next = timeOffsets[Number(e.target.value)]; navigate(() => setHorizon(next)); }} /><div><span>Last 7 days</span><span>Today</span><span>90 days ahead</span></div></div><output><Icon name="calendar" />{future.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</output></div>
        </section>
        {!detail && horizon === 0 && <>{canSeeOperations ? <><div className="section-heading"><h3>Today&apos;s priorities <span className="count-pill">5</span></h3><span className="subtle">Operations overview</span></div>{error && <p role="alert" className={styles.error}>{error} <button className="work-button" onClick={() => setRetry(v => v + 1)}>Retry</button></p>}
        <OverviewMetrics label="Current dealership priorities" items={priorities.map(p => ({label:p.title,icon:p.icon,value:overview ? overview.action_center[p.key].count : undefined,detail:overview ? (overview.action_center[p.key].count ?? 0)>0 ? "Needs attention" : "No flagged records" : error ? "Unavailable" : "Loading…",attention:!!overview && (overview.action_center[p.key].count ?? 0)>0,action:p.action,disabled:!overview,onClick:()=>p.key === "compliance_violations" ? openMenu("alerts", "Operations") : setDetail({kind:"priority",key:p.key,title:p.title})}))}/>
        </> : <section className={styles.roleSummary}><h3>{department}</h3><p>Open your department overview to see the records available to your role.</p><button onClick={() => openMenu("overview")}>Open department overview →</button></section>}
        <OverviewActions items={[
          ...(hasMenuItem("tasks")?[{label:"Open today’s tasks",icon:"list",onClick:()=>openMenu("tasks")}]:[]),
          ...(hasMenuItem("inventory")?[{label:"Review inventory",icon:"car",onClick:()=>openMenu("inventory")}]:[]),
          ...(canSeeOperations?[{label:"Check compliance",icon:"shield",onClick:()=>openMenu("alerts","Operations")}]:[]),
          {label:"Explore scenarios",icon:"chart",onClick:()=>{setTimelineOpen(true);requestAnimationFrame(()=>timelineRef.current?.focus());}},
          ...(hasMenuItem("workflows")?[{label:"View workflows",icon:"list",onClick:()=>openMenu("workflows")}]:[])
        ]}/>

        <section className="bottom-grid"><div className="insight glass-inset"><span className="mini-icon"><GlassIcon name="sparkles"/></span><div><h3>A clearer day starts here.</h3><p>Keep titles, deliveries, and compliance moving in one place.</p></div><button className="text-button" onClick={() => openMenu("overview")}>Explore workspace <GlassIcon name="arrow"/></button></div><button className="customize-card glass-inset" onClick={() => setAppearanceOpen(true)}><span className="color-orbs"><i/><i/><i/></span><span><b>Make it yours</b><small>Color, glass &amp; motion</small></span><GlassIcon name="arrow"/></button></section>
        </>}
        {department === "Readiness" && <nav className={styles.sectionNav} aria-label="Department tools"><button onClick={() => { setTimelineOpen(false); setDetail({ kind: department === "Readiness" ? "connections" : "benchmarks" }); }}>{department === "Readiness" ? "Data connections" : "Peer benchmarks"}</button></nav>}
        {workflowError && department !== "Network" && <p role="alert" className={styles.error}>{workflowError} <button onClick={() => setRetry(v => v + 1)}>Retry</button></p>}

        {detail?.kind === "help" && <HelpWorkspace isSystemAdmin={session.isSystemAdmin===true} role={session.role} department={department} departments={[...visible,"Marketplace",...(session.role==="ADMIN"?["Administration","Readiness","Extras"]:[])]} workflows={workflows} onOpen={openMenu} onWorkflow={(workflow,dept)=>navigate(()=>{if(dept==="Administration"&&retiredAdminWorkflows[workflow.key]){openMenuNow(retiredAdminWorkflows[workflow.key],dept);}else{setDepartment(dept);setDetail({kind:"workflow",workflow});}})} onTour={()=>setTourRevision(v=>v+1)} onDepartmentTour={dept=>navigate(()=>{openMenuNow("overview",dept);setWalkthrough({department:dept,departmentTour:true,title:`${dept==="Network"?"Dealer Lab":dept} overview`});})}/>}
        <div className={styles.departmentContent}>

          <div>
        {horizon !== 0 && <DepartmentTimeView key={department} department={department} period={timePeriods[timeOffsets.indexOf(horizon)]} onToday={() => setHorizon(0)} />}

        {department === "BDC" && detail?.kind === "menu" && horizon === 0 && <BdcWorkspace key={homeRevision} navigationHost={navigationHost} theme={appearance.theme} session={session} items={menuItems} initialItem={detail.item} onOpenEntity={openEntity} onOpenBrand={()=>openMenu("email_designs","Marketing")} onDraftOpenChange={setCampaignDraftOpen} onSavingChange={setCampaignSaving}/>}
        {department === "Marketing" && detail?.kind === "menu" && horizon === 0 && <MarketingWorkspace onOpenBdc={item=>openMenu(item,"BDC")} onSavingChange={setCampaignSaving} onDraftOpenChange={setCampaignDraftOpen} key={homeRevision} navigationHost={navigationHost} theme={appearance.theme} session={session} items={menuItems} initialItem={detail.item} onOpenEntity={openEntity} onSettings={() => setDetail({ kind: "account", tab: "notifications" })} />}
        {["Network","Extras"].includes(department) && detail?.kind === "menu" && horizon === 0 && <DealershipLab key={`${department}:${homeRevision}`} extras={department==="Extras"} navigationHost={navigationHost} theme={appearance.theme} onDraftOpenChange={setLabDraftOpen} onSavingChange={setLabSaving} />}
        {department === "Sales" && detail?.kind === "menu" && horizon === 0 && <SalesCrmWorkspace onOpenBdc={item=>openMenu(item,"BDC")} key={homeRevision} navigationHost={navigationHost} theme={appearance.theme} session={session} items={menuItems} initialItem={detail.item} onOpenEntity={openEntity} />}
        {!(["Marketing", "Sales", "BDC", "Network", "Extras"].includes(department) && detail?.kind === "menu") && detail && (detail.kind === "menu" || detail.kind === "workflow" || detail.kind === "account" || detail.kind === "connections" || detail.kind === "benchmarks" || detail.kind === "entity" || detail.kind === "priority") && horizon === 0 && <section data-department-work={detail.kind === "menu" && detail.item === "overview" ? undefined : ""} className={`${styles.sectionPanel} ${detail.kind === "menu" && detail.item === "overview" ? styles.overviewPanel : ""}`} aria-label={title}>
          {!(["Readiness", "Operations", "Finance", "Service", "Inventory", "Administration"].includes(department) && detail.kind === "menu" && detail.item === "overview") && <OverviewHeader department={departmentLabel} context={department==="Administration"&&detail.kind==="menu"&&adminDestinations[detail.item]?adminAreas[adminDestinations[detail.item].area].label:"Workspace"} title={detail.kind === "menu" ? menuItems.find(item => item.key === detail.item)?.label || detail.item.replaceAll("_", " ") : title} description={detail.kind === "menu" ? departmentWorkDescription(detail.item, menuItems.find(item => item.key === detail.item)?.label || detail.item.replaceAll("_", " ")) : "Review the details and continue your work."}><button onClick={() => openMenu(department==="Marketplace"?"browse":"overview")} aria-label="Return to department home">← Overview</button></OverviewHeader>}
          <div className={styles.sectionBody}>
            {detail.kind === "connections" && <ReadinessIntegrationPanel canManageConnections={session.role === "ADMIN" || session.role === "OPERATIONS"} />}
            {detail.kind === "benchmarks" && <NetworkBenchmarkPanel hideAssistant canViewNetwork={["ADMIN", "OPERATIONS", "FINANCE"].includes(session.role)} />}
            {detail.kind === "account" && <AccountSettingsBody hideAssistant activeTab={detail.tab} onSelectTab={tab => setDetail({ kind: "account", tab })} />}
            {detail.kind === "workflow" && <WorkflowWindowBody theme={appearance.theme} onDraftOpenChange={setCampaignDraftOpen} onSavingChange={setCampaignSaving} key={detail.workflow.key} workflow={detail.workflow} color="#3FBCC4" onRequestClose={() => openMenu("overview")} />}
            {detail.kind === "menu" && department === "Readiness" && detail.item === "overview" ? <ReadinessDay theme={appearance.theme}/> : detail.kind === "menu" && department === "Operations" && detail.item === "overview" ? <OperationsDay allowed={new Set(menuItems.map(item=>item.key))} onSelectItem={item=>openMenu(item,"Operations")} onOpenEntity={openEntity}/> : detail.kind === "menu" && department === "Administration" && detail.item === "overview" ? <AdministrationDay theme={appearance.theme} allowed={new Set(menuItems.map(item=>item.key))} onSelectItem={item=>openMenu(item,"Administration")}/> : detail.kind === "menu" && department === "Inventory" && detail.item === "overview" ? <InventoryDay theme={appearance.theme} allowed={new Set(menuItems.map(item=>item.key))} onSelectItem={item=>openMenu(item,"Inventory")}/> : detail.kind === "menu" && department === "Finance" && detail.item === "overview" ? <FinanceDay theme={appearance.theme} onSelectItem={item=>openMenu(item,"Finance")}/> : detail.kind === "menu" && department === "Service" && detail.item === "overview" ? <ServiceDay theme={appearance.theme} allowed={new Set(menuItems.map(item=>item.key))} onSelectItem={item=>openMenu(item,"Service")}/> : detail.kind === "menu" && department === "Service" && detail.item === "shop_control" ? <DispatchDay theme={appearance.theme}/> : detail.kind === "menu" && <MenuDashBody initialTheme={appearance.theme} hideNav hideAssistant onDraftOpenChange={setEmployeeDraftOpen} onSavingChange={setEmployeeSaving} key={`${detail.department}:${detail.item}:${homeRevision}`} department={detail.department} itemKey={detail.item} onSelectItem={item => openMenu(item, detail.department)} />}
            {detail.kind === "entity" && <EntityDashPanel theme={appearance.theme} entityId={detail.id} onClose={() => navigate(()=>setDetail(recordOrigin))} onPopOut={() => router.push(`/profile/${encodeURIComponent(detail.id)}`)} />}
            {detail.kind === "priority" && <div className={styles.recordList}><p>{bucket?.count ?? 0} matching records. Showing {records.length}.</p>{records.map((r, i) => { const row = r as Record<string, unknown>; const id = String(row.deal_id || row.vehicle_id || ""); return <button key={`${id}-${i}`} onClick={() => openEntity(id)}><strong>{id}</strong><span>{String(row.stock_number || row.status || row.vin || "View record")}</span><span>→</span></button>; })}</div>}
          </div>
        </section>}
          </div>
        </div>
        <footer className={styles.footer}><span>Dealership workspace · {departmentLabel}</span><span>PEOPLE / PROCESS / PROGRESS</span></footer>
      </main></div></div>
      <CommsWorkspaceMount />
      <AppearanceDialog appearance={appearance} open={appearanceOpen} onClose={() => setAppearanceOpen(false)}/>
      {detail && (detail.kind === "evidence" || detail.kind === "guide") && <DetailDialog key={detail.kind} title={title} onClose={() => setDetail(null)}>
        {detail.kind === "evidence" && <div className={styles.explanation}><h3>Know what you’re looking at.</h3><p>The priority cards use the existing Operations API and your dealership’s current records. The current preview uses sample dealership data; deployed counts depend on the connected dealership.</p><h3>Scenario preview</h3><p>The lines, scenario choices and timeline illustrate the proposed experience. They are not calculated predictions, targets, or probabilities. This illustration is not a model output. The shared time view uses the existing department forecast feed for Sales, Marketing, Service and Finance; Operations and Inventory have no dated source yet.</p><p>Illustration only — not applied to the department forecast feed. Selected: {scenario} · {intervention} · {horizon} days. Selecting an action here does not change dealership records or execute it.</p></div>}
        {detail.kind === "guide" && <div className={styles.explanation}><h3>A clear view of your day.</h3><p>Choose a department at the top, then a daily workflow in the sidebar. Today returns to your current department. The NXTDeal logo opens dealership priorities. Specialist workflows and reports remain available in the sidebar.</p><p>Find Apps, VIN Lookup, Help and Notifications at the upper right. Screen controls are at the bottom of the left navigation. Administration contains Extras & tools and the Knowledge Base.</p><p>The scenario timeline is an illustrative preview. Open Model & Evidence for its current status.</p></div>}
      </DetailDialog>}
      {contextHelp&&<ContextHelp department={departmentLabel} title={detail?.kind==="menu"?(menuItems.find(item=>item.key===detail.item)?.label||detail.item.replaceAll("_"," ")):detail?title:"Today"} onClose={()=>setContextHelp(false)} onWalkthrough={()=>{setContextHelp(false);setWalkthrough({department,title:detail?.kind==="menu"?(menuItems.find(item=>item.key===detail.item)?.label||detail.item.replaceAll("_"," ")):detail?title:"Today"});}} onLibrary={()=>{setContextHelp(false);navigate(()=>{setHorizon(0);setTimelineOpen(false);setDetail({kind:"help"});});}}/>}
      {walkthrough&&<GuidedWalkthrough context={{...walkthrough,isSystemAdmin:session.isSystemAdmin===true}} onClose={()=>setWalkthrough(null)} onHelp={()=>{setWalkthrough(null);navigate(()=>{setHorizon(0);setDetail({kind:"help"});});}}/>}
      <WelcomeTour key={`${session.apiBaseUrl}:${session.employeeId}:${tourRevision}`} identity={`${session.apiBaseUrl}:${session.employeeId}`} replay={tourRevision>0} onHelp={()=>navigate(()=>{setHorizon(0);setDetail({kind:"help"});})}/>
      {utility === "vin" && <VinLookupWidget menuMode onDismiss={() => setUtility(null)} />}
    </div>
  </EntityLinkActionsProvider></WorkspaceToolsContext.Provider>;
}
