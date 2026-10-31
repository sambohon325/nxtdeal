"use client";
import { WorkButton, WorkInput, WorkSelect } from "./../WorkspaceUi";
import { CampaignWorkflow } from "./CampaignWorkflow";
import { CampaignPlanning } from "./CampaignPlanning";
import { BdcCampaigns } from "../bdc/BdcCampaigns";
import { bdcDestination } from "@/lib/bdcNavigation";
import {OverviewHeader,OverviewMetrics,OverviewActions} from "../DepartmentOverview";
import { WorkspaceNavigation } from "../WorkspaceNavigation";
import { createPortal } from "react-dom";

import { useEffect, useState } from "react";
import { EntityDashPanel } from "@/components/EntityDashPanel";
import dynamic from "next/dynamic";
import { MenuDashBody } from "@/components/MenuDashPanel";
import type { MenuCatalogItem } from "@/components/DepartmentMenuBar";
import type { Session } from "@/lib/auth";
import { fetchCampaignsData, searchCrm, type CampaignsData, type CrmSearchResult } from "@/lib/marketingCrm";
import styles from "./MarketingWorkspace.module.css";

const MarketingOperations = dynamic(() => import("./MarketingOperations").then(m => m.MarketingOperations));
const loading = () => <p role="status">Opening workspace…</p>;
const Social = dynamic(() => import("@/components/SocialReputationBoard").then(m => m.SocialReputationBoard), { loading });
const Campaigns = dynamic(() => import("@/components/CampaignsBoard").then(m => m.CampaignsBoard), { loading });
const Crm = dynamic(() => import("@/components/MarketingCRMBoard").then(m => m.MarketingCRMBoard), { loading });
const Content = dynamic(() => import("@/components/MarketingStudioBoard").then(m => m.MarketingStudioBoard), { loading });
const Communications = dynamic(() => import("@/components/OperationsCommunicationsBoard").then(m => m.OperationsCommunicationsBoard), { loading });
const DealerEmailStudio = dynamic(() => import("./DealerEmailStudio").then(m => m.DealerEmailStudio), { loading });
const JourneyPlans = dynamic(() => import("./JourneyPlans").then(m => m.JourneyPlans), { loading });
const Journeys = dynamic(() => import("@/components/OperationsCustomerJourneyBoard").then(m => m.OperationsCustomerJourneyBoard), { loading });
const Agents = dynamic(() => import("@/components/AiWorkforceBoard").then(m => m.AiWorkforceBoard), { loading });
const Connections = dynamic(() => import("@/components/ReadinessIntegrationPanel").then(m => m.ReadinessIntegrationPanel), { loading });
const Automation = dynamic(() => import("@/components/WorkflowAutomationBoard").then(m => m.WorkflowAutomationBoard), { loading });

type View = { key: string; label: string; description: string; gate?: string; admin?: boolean; tabs?: [string, string][] };
const views: View[] = [
  { key: "overview", label: "Marketing today", description: "Review campaign work, prepare the next audience, and follow up on results.", gate: "campaigns" },
  { key: "planning", label: "Planning & budgets", description: "Set campaign goals, planned budgets, timing, capacity checks and response ownership.", gate: "campaigns" },
  { key: "outreach", label: "Email & SMS campaigns", description: "Prepare audience outreach using shared templates, consent checks and channel approvals.", gate: "campaigns" },
  { key: "email", label: "Lifecycle planning", description: "Design retention and reactivation journeys around shared customer history.", gate: "email_sms", tabs: [["journey_plans", "Journey plans"], ["journeys", "Customer lifecycle"]] },
  { key: "social", label: "Social", description: "Plan posts, build content, and manage your publishing calendar.", gate: "social_reputation" },

  { key: "communications", label: "Delivery & approvals", description: "Review channel drafts, resolve requested changes, and inspect delivery evidence.", tabs: [["execution", "Draft review"], ["conversations", "Conversation log"]] },
  { key: "leads", label: "Audiences & lifecycle", description: "Choose eligible audiences using shared customer, ownership and service records.", gate: "crm", tabs: [["lists", "Lists"], ["audiences_scoring", "Audiences"], ["customer360", "Customer history"]] },
  { key: "reputation", label: "Reputation", description: "Review responses and reputation monitoring.", gate: "social_reputation" },
  { key: "analytics", label: "Performance & attribution", description: "Review recorded outcomes and attribution coverage; distinguish correlation from incremental revenue.", gate: "analytics", tabs: [["analytics", "Attribution"], ["reporting", "Reports"]] },
  { key: "advertising", label: "Paid media", description: "Manage paid campaigns and inventory advertising.", gate: "advertising", tabs: [["advertising", "Campaigns"], ["inventory_advertising", "Inventory ads"]] },
  { key: "agents", label: "Agent team", description: "Eight specialists for supervised marketing planning.", gate: "campaigns" },
  { key: "runs", label: "Agent runs", description: "Plans, provenance, approvals and channel outcomes.", gate: "campaigns" },
  { key: "inventory_advertising", label: "Inventory", description: "Turn canonical inventory into marketing opportunities.", gate: "inventory_advertising" },
  { key: "campaigns", label: "Campaigns & offers", description: "Coordinate inventory promotions, service offers, retention and reactivation.", gate: "campaigns", tabs: [["campaigns", "Campaigns"], ["campaign_library", "Templates"], ["campaign_scheduler", "Schedule"]] },
  { key: "content", label: "Content studio", description: "Generate, review, and apply content to dealership workflows.", tabs: [["content", "Create & review"], ["file_manager", "Asset library"]] },
  { key: "website", label: "Brand & Website", description: "Your website and matching emails, together. Choose a website design to unlock its email collection. Manage audiences and delivery in BDC Center.", tabs: [["website", "Website & DNS"], ["email_designs", "Matching emails & HTML"], ["email_sms", "Saved messages"]] },
  { key: "events", label: "Events & loyalty", description: "Bring customers back through events and retention programs.", gate: "events", tabs: [["events", "Events"], ["loyalty", "Loyalty"], ["purls", "Personal links"]] },
  { key: "integrations", label: "Connected channels", description: "Review connected providers, available execution and data coverage." },
  { key: "native_workers", label: "Dealership workers", description: "Existing NXTDeal workforce controls.", admin: true },
  { key: "automation", label: "Automation", description: "Manage explicit rules and inspect their execution history.", admin: true },
];

function Glyph({ index }: { index: number }) {
  const paths = ["M3 11h7V3H3zm11 10h7v-8h-7zM3 21h7v-6H3zm11-12h7V3h-7z", "M4 4h16v12H9l-5 4z", "M3 5h18v14H3zm0 0 9 8 9-8", "M4 4h12v12H4zm5 16h11V9", "M8 10a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm-5 9v-3c0-5 10-5 10 0v3m3-14h5m-5 5h5m-5 5h5", "m12 3 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z", "M4 20V11m8 9V4m8 16V8"];
  return <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round"><path d={paths[index % paths.length]} /></svg>;
}

export function MarketingWorkspace({onOpenBdc, navigationHost, theme = "dark",  session, items, initialItem, onOpenEntity: openStandaloneEntity, onSettings, onDraftOpenChange, onSavingChange }: { onOpenBdc?: (item:string)=>void; onDraftOpenChange?: (open: boolean) => void; onSavingChange?: (saving:boolean)=>void; navigationHost?: HTMLElement | null; theme?: "light" | "dark"; session: Session; items: MenuCatalogItem[]; initialItem: string; onOpenEntity: (id: string) => void; onSettings: () => void }) {
  const resolve = (key: string) => (views.find(v => v.key === key) ?? views.find(v => v.tabs?.some(([t]) => t === key)))?.key ?? (key === "email" ? "website" : key === "crm" ? "leads" : key === "social_reputation" ? "social" : "overview");
  const [active, setActive] = useState(resolve(initialItem));
  const [tab, setTab] = useState(initialItem);
  const [collapsed, setCollapsed] = useState(false);
  const [data, setData] = useState<CampaignsData | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [revision, setRevision] = useState(0);
  const [updated, setUpdated] = useState<Date | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CrmSearchResult[] | null>(null);
  const [searchError, setSearchError] = useState("");
  const [searching, setSearching] = useState(false);
  const [taskSearch, setTaskSearch] = useState("");
  const [entity, setEntity] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => { onSavingChange?.(saving); return () => onSavingChange?.(false); }, [saving,onSavingChange]);
  const [draftRevision, setDraftRevision] = useState(0);
  const [draftOpen, setDraftOpen] = useState(false);
  useEffect(() => { onDraftOpenChange?.(draftOpen); return () => onDraftOpenChange?.(false); }, [draftOpen, onDraftOpenChange]);
  const [pendingNavigation, setPendingNavigation] = useState<{ run: () => void } | null>(null);
  const navigate = (run: () => void) => { if (draftOpen || saving) setPendingNavigation({ run }); else run(); };
  const onOpenEntity = (id: string) => navigate(() => setEntity(id));
  const openSettings = () => navigate(onSettings);
  const keys = new Set(items.map(i => i.key));
  const canManage = session.role === "ADMIN";
  const allowed = (v: View) => v.key === "website" ? keys.has("website") || keys.has("email_sms") : v.admin ? canManage : v.gate ? keys.has(v.gate) : v.key === "content" ? ["ADMIN", "MARKETING"].includes(session.role) : true;
  const select = (key: string) => navigate(() => { const destination=bdcDestination("Marketing",key); if(destination&&onOpenBdc){onOpenBdc(destination);return;} setDraftOpen(false); setEntity(null); const next = views.find(v => v.key === resolve(key))!; setActive(next.key); setTab(next.tabs?.some(([t]) => t === key) ? key : next.tabs?.[0][0] ?? key); setResults(null); });
  useEffect(() => { select(initialItem); /* Route selection comes from the parent workspace. */ }, [initialItem]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    if (!keys.has("campaigns")) { setBusy(false); return; }
    let live = true; setBusy(true); setError(""); setData(null);
    fetchCampaignsData().then(d => { if (live) { setData(d); setUpdated(new Date()); } }).catch(e => { if (live) setError(e instanceof Error ? e.message : "Unable to load campaigns."); }).finally(() => { if (live) setBusy(false); });
    return () => { live = false; };
  }, [revision, items]); // keys is derived from items
  const view = views.find(v => v.key === active)!;
  const tabs = view.tabs?.filter(([key]) => active === "website" ? (key === "website" ? keys.has("website") : keys.has("email_sms")) : ["email_designs", "pipeline", "lists", "audiences_scoring", "customer360", "opportunities", "content", "journeys", "journey_plans", "execution", "conversations"].includes(key) || keys.has(key));
  const effectiveTab = tabs?.some(([key]) => key === tab) ? tab : tabs?.[0]?.[0] ?? active;
  const native = (key: string) => keys.has(key) ? <MenuDashBody initialTheme={theme} hideNav hideAssistant department="Marketing" itemKey={key} onSelectItem={select} /> : <p className={styles.panel}>This workspace is unavailable for your current access.</p>;
  const pending = data ? data.pending_drafts.count + data.compliance_approval.count : null;
  const navigation = navigationHost ? <WorkspaceNavigation department="Marketing" active={active} onSelect={select} items={[
    ...views.filter(v=>allowed(v)&&!bdcDestination("Marketing",v.key)).map(v=>({key:v.key,label:v.label,description:v.description})),
    {key:"bdc",label:"BDC Center",onSelect:()=>navigate(()=>onOpenBdc?.("today"))},
    {key:"settings",label:"Marketing settings",onSelect:openSettings},
  ]}/> : <aside className={styles.sidebar}><div className={styles.navTitle}><span>Marketing</span>{!navigationHost && <WorkButton type="submit" aria-label={collapsed ? "Expand marketing navigation" : "Collapse marketing navigation"} aria-expanded={!collapsed} onClick={() => setCollapsed(v => !v)}>{collapsed ? "→" : "←"}</WorkButton>}</div><label className={styles.taskSearch}>Find a marketing task<WorkInput type="search" value={taskSearch} onChange={e=>setTaskSearch(e.target.value)} placeholder="Search tasks…" /></label>{taskSearch&&<WorkButton type="submit" className={styles.taskSearch} onClick={()=>setTaskSearch("")}>Show all tasks</WorkButton>}<label className={styles.mobileTasks}>Go to a marketing task<WorkSelect value={active} onChange={e=>select(e.target.value)}>{views.filter(v=>allowed(v)&&!bdcDestination("Marketing",v.key)).map(v=><option key={v.key} value={v.key}>{v.label}</option>)}</WorkSelect></label><WorkButton type="submit" className={styles.mobileTasks} onClick={openSettings}>Settings</WorkButton><nav aria-label="Marketing workspaces">{views.filter(v=>allowed(v)&&!bdcDestination("Marketing",v.key)&&`${v.label} ${v.description}`.toLowerCase().includes(taskSearch.trim().toLowerCase())).map((v, i) => <WorkButton type="submit" key={v.key} title={v.label} aria-label={v.label} aria-current={active === v.key ? "page" : undefined} onClick={() => select(v.key)}><Glyph index={i} /><span>{v.label}</span></WorkButton>)}<WorkButton type="submit" onClick={openSettings} title="Settings"><Glyph index={0} /><span>Settings</span></WorkButton></nav><small>One dealership.<br />Every channel.</small></aside>;
  if (entity) return <section data-department-work="" aria-label="Marketing record details">{navigationHost && createPortal(navigation, navigationHost)}<WorkButton type="submit" className="min-h-11 text-sky-200 underline" onClick={()=>setEntity(null)}>← Back to {view.label}</WorkButton><EntityDashPanel theme={theme} key={entity} entityId={entity} onClose={()=>setEntity(null)} onPopOut={()=>openStandaloneEntity(entity)} /></section>;
  return <section className={`${styles.workspace} ${collapsed ? styles.collapsed : ""} ${theme === "light" ? styles.light : ""} ${navigationHost ? styles.embedded : ""}`} data-department-work={active === "overview" ? undefined : ""} aria-label="Marketing platform">
    {navigationHost ? createPortal(navigation, navigationHost) : navigation}

    <div className={styles.content}>
      {searchError && <p role="alert" className={styles.panel}>{searchError}</p>}{results && <section className={styles.panel} aria-label="Search results"><WorkButton type="submit" onClick={() => setResults(null)}>Close results</WorkButton>{results.length ? results.map(r => <button className={styles.result} key={r.id} onClick={() => onOpenEntity(r.id)}>{r.name || r.id}<small>{r.entity_type}</small></button>) : <p>No matching records.</p>}</section>}
      {active === "overview" ? <OverviewHeader department="Marketing" title="Marketing overview" description="Plan the audience, offer and channels. BDC handles qualifying conversations, appointments and handoffs on the same customer record."><WorkButton type="submit" disabled={busy} onClick={()=>setRevision(v=>v+1)}>Refresh</WorkButton>{keys.has("campaigns")&&<WorkButton type="submit" onClick={()=>select("campaigns")}>Open campaigns →</WorkButton>}</OverviewHeader> : <OverviewHeader department="Marketing" context="Workspace" title={view.label} description={view.description}><WorkButton type="submit" onClick={()=>select("overview")}>← Overview</WorkButton></OverviewHeader>}
      <div className={styles.topbar} hidden={active === "overview"}><form onSubmit={async e => { e.preventDefault(); if (!query.trim() || searching) return; setSearching(true); setSearchError(""); setResults(null); try { setResults((await searchCrm(query.trim())).results); } catch(e) { setSearchError(e instanceof Error ? e.message : "Search unavailable."); } finally { setSearching(false); } }}><WorkInput aria-label="Search marketing records" placeholder="Search customers, leads…" value={query} onChange={e => setQuery(e.target.value)} /><WorkButton type="submit" disabled={searching || !query.trim()}>{searching ? "Searching…" : "Search"}</WorkButton></form></div>
      {tabs && <nav className={styles.tabs} aria-label={`${view.label} views`}>{tabs.map(([key, label]) => <WorkButton type="submit" key={key} aria-current={effectiveTab === key ? "page" : undefined} onClick={() => navigate(() => { setDraftOpen(false); setTab(key); })}>{label}</WorkButton>)}</nav>}
      {pendingNavigation && <div role="alert" className={styles.panel}><h3>{saving ? "Marketing changes are saving" : "Unfinished Marketing work"}</h3><p>{saving ? "Wait for the result. Navigating cannot cancel this request." : draftOpen ? "Keep editing, or discard this draft and open the selected task." : "Review the result before continuing."}</p><WorkButton type="submit" onClick={() => setPendingNavigation(null)}>Keep editing draft</WorkButton><WorkButton type="submit" disabled={saving} onClick={() => { if(saving)return; const next = pendingNavigation; setPendingNavigation(null); setDraftOpen(false); setDraftRevision(v=>v+1); next.run(); }}>{saving ? "Wait for save" : draftOpen ? "Discard and continue" : "Continue"}</WorkButton></div>}
      {!allowed(view) ? <p className={styles.panel}>This workspace is unavailable for your current access.</p> : active === "overview" ? <>
        <section className={styles.panel} aria-label="Marketing and BDC responsibilities"><h3>From demand to the next customer step</h3><p>Marketing owns audiences, offers, campaigns and channel performance. BDC owns response, conversations, appointments and follow-up. Sales and Service complete the handoff.</p><p>Opens and clicks stay marketing signals. BDC work needs a qualifying reason, an owner, a deadline and a next step.</p>{keys.has("campaigns")&&<WorkButton type="submit" onClick={()=>select("planning")}>Plan a campaign →</WorkButton>}{onOpenBdc&&<WorkButton type="submit" onClick={()=>navigate(()=>onOpenBdc("today"))}>Open BDC response work →</WorkButton>}</section>
        <div className={styles.source}><span>{busy ? "Loading campaign records…" : error ? "Campaign data unavailable" : updated ? `Campaign records · refreshed ${updated.toLocaleTimeString()}` : "Campaign source not available"}</span></div>{error && <p role="alert" className={styles.panel}>{error}</p>}
        <OverviewMetrics label="Marketing snapshot" items={[
          {label:"Campaigns",value:busy||error?null:data?.total_campaigns,icon:"campaigns",detail:"Recorded campaigns · all dates"},
          {label:"Active campaigns",value:busy||error?null:data ? data.by_status.active??0 : null,icon:"marketing",detail:"Currently marked active"},
          {label:"Drafts to review",value:busy||error?null:data?.pending_drafts.count,icon:"content",detail:"Pending campaign drafts"},
          {label:"Compliance alerts",value:busy||error?null:data?.compliance_approval.count,icon:"compliance",detail:"Review before execution"},
        ].map(item=>({...item,action:"Review campaigns",onClick:()=>select("campaigns")}))}/>
        <div className={styles.columns}><section className={styles.panel}><h3>Work needing attention</h3><p>Check drafts and compliance alerts before preparing the next campaign.</p><strong className={styles.attention}>{pending ?? "—"}</strong><p>{!data ? "Load campaign records to see review counts." : pending ? `${data.pending_drafts.count} drafts · ${data.compliance_approval.count} compliance alerts` : "No pending campaign drafts or compliance alerts in this response."}</p><WorkButton type="submit" onClick={() => select("campaigns")}>Review campaigns →</WorkButton><WorkButton type="submit" onClick={() => select("execution")}>Review channel drafts & changes →</WorkButton></section>
        <OverviewActions items={[["leads","Choose your audience"],["content","Create content"],["website","Brand & Website"],["analytics","Review outcomes"]].filter(([key])=>allowed(views.find(v=>v.key===key)!)).map(([key,label])=>({label,onClick:()=>select(key==="leads"?"lists":key)}))}/></div>
        <details className={styles.panel}><summary>Campaign activity and channel counts</summary>
<h3>Recent campaigns</h3>{data?.recent_campaigns.length ? data.recent_campaigns.slice(0, 5).map(c => <button className={styles.result} key={c.id} onClick={() => select("campaigns")}><span>{c.name}<small>{c.channel} · {c.audience_count} recipients</small></span><em>{c.status}</em></button>) : <p>{data ? "No campaigns recorded yet." : "Campaign records unavailable."}</p>}        <section className={styles.panel}><h3>One strategy. Every channel.</h3><p>Counts reflect campaign records by channel, not provider delivery or attributed revenue.</p><div className={styles.channels}>{data ? Object.entries(data.by_channel).map(([channel, count]) => <button key={channel} onClick={() => select("campaigns")}><span>{channel}</span><strong>{count}</strong><small>campaign records</small></button>) : <p>Channel data is unavailable.</p>}{data && !Object.keys(data.by_channel).length && <p>No channel campaigns recorded yet.</p>}</div></section>
        </details>
        <details className={styles.panel}><summary>Planning assistant and channel approvals</summary><p>Optional planning tools and recorded channel actions. Review each action before execution.</p>
          <MarketingOperations key={draftRevision} onDraftOpenChange={setDraftOpen} onSavingChange={setSaving} mode="overview" canEdit={["ADMIN", "MARKETING"].includes(session.role)} />
        </details>
      </> : <div className={styles.board} key={`${active}:${effectiveTab}`}>
        {active === "analytics" && effectiveTab === "analytics" ? <CampaignWorkflow onDraftOpenChange={setDraftOpen} onSavingChange={setSaving} onOpen={onOpenEntity}/> : active === "planning" ? <CampaignPlanning canEdit={["ADMIN","MARKETING"].includes(session.role)} onDraftOpenChange={setDraftOpen} onSavingChange={setSaving}/> : active === "outreach" ? <BdcCampaigns onDraftOpenChange={setDraftOpen} onSavingChange={setSaving} onBrand={()=>select("email_designs")} onFollowups={()=>navigate(()=>onOpenBdc?.("followups"))}/> : active === "social" || active === "reputation" ? <Social theme={theme} initialSection={active} /> : active === "leads" && effectiveTab !== "lead_import" ? <Crm key={draftRevision} embedded onDraftOpenChange={setDraftOpen} onSavingChange={setSaving} theme={theme} initialTab={effectiveTab as "pipeline" | "lists" | "audiences_scoring" | "customer360" | "opportunities"} /> : active === "content" && effectiveTab === "content" ? <Content theme={theme} /> : active === "communications" ? (effectiveTab === "conversations" ? <Communications theme={theme} /> : <MarketingOperations key={draftRevision} onDraftOpenChange={setDraftOpen} onSavingChange={setSaving} mode="communications" canEdit={["ADMIN", "MARKETING"].includes(session.role)} />) : active === "website" && effectiveTab === "email_designs" ? <DealerEmailStudio onDraftOpenChange={setDraftOpen} onSavingChange={setSaving} canEdit={["ADMIN", "MARKETING"].includes(session.role)} /> : active === "email" && effectiveTab === "journey_plans" ? <JourneyPlans onDraftOpenChange={setDraftOpen} onSavingChange={setSaving} canEdit={["ADMIN", "MARKETING"].includes(session.role)} /> : active === "email" && effectiveTab === "journeys" ? <Journeys theme={theme} /> : active === "native_workers" ? <Agents hideHeading theme={theme} /> : active === "agents" || active === "runs" ? <MarketingOperations key={`${active}:${draftRevision}`} onDraftOpenChange={setDraftOpen} onSavingChange={setSaving} mode={active} canEdit={["ADMIN", "MARKETING"].includes(session.role)} /> : active === "integrations" ? <Connections canManageConnections={canManage || session.role === "OPERATIONS"} /> : active === "automation" ? <Automation theme={theme} /> : active === "campaigns" && effectiveTab === "campaigns" && keys.has("campaigns") ? <Campaigns key={draftRevision} theme={theme} onDraftOpenChange={setDraftOpen} onSavingChange={setSaving} /> : native(effectiveTab)}
      </div>}
    </div>
  </section>;
}
