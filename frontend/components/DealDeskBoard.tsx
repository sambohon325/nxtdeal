"use client";
import { WorkButton, WorkInput, WorkSelect, WorkTextarea , WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Sales' "Deals" Top Menu item -- the DMS Deal Desk (backend: core/deals.py/
// deals_api.py, session 33) finally gets a real frontend. Sam's Sales sub-menu spec
// (2026-07-16): "Deals... This is where dealerships spend most of their time...
// Currently this appears absent. Should function like a true deal desk." A real
// Pipeline Kanban (desking -> financing -> contract -> funded), a Deal Worksheet with
// a multi-scenario Pencil Tool, a Trade Appraisal panel with manager approval, and a
// Desking/Financing panel covering in-house/outside-lender submission through to
// funding -- all against the backend that's existed since session 33 but had zero
// routes wired to it until this session (see api/app.py's "DMS Deal Desk" route
// block).
//
// Scoping note (see BUILD_QUEUE.md's session-91 entry): this pass covers the real
// Deal lifecycle only. Sam's doc also describes a pre-desking funnel (Lead ->
// Appointment -> Showroom -> Demo Drive -> Negotiation) merged into the same board --
// that's the real core/lead_workflows.py pipeline already driving
// MarketingCRMBoard.tsx's Pipeline tab, but merging it here would need new Lead-to-
// Deal conversion plumbing that doesn't exist yet. Flagged for the future Prospects
// submenu rather than guessed at here.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState, type DragEvent, type ReactNode } from "react";
import {
  listAllDeals,
  listLenders,
  createDeal,
  getDeal,
  addScenario,
  removeScenario,
  selectScenario,
  updateTradeAppraisal,
  approveTradeAppraisal,
  decodeTradeInVin,
  chooseInHouseFinancing,
  submitToLender,
  recordLenderDecision,
  acceptCounteredTerms,
  generateContract,
  fundDeal,
  cancelDeal,
  searchCustomers,
  type Deal,
  type DealStatus,
  type Lender,
  type CustomerBrief,
  type TradeInVinDecodeResult,
} from "@/lib/deals";
import { searchInventoryForPost, type LinkedVehicle } from "@/lib/socialReputation";
import { getSession } from "@/lib/auth";
import { VISUALIZATION_DRAG_TYPE, type VisualizationDropPayload } from "@/lib/useVisualizationWorkspace";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const KPI_RIBBON = PRODUCT_ACCENT_COLORS;
const DRAG_TYPE = "application/x-dealeros-deal-id";

const COLUMNS: { status: DealStatus; label: string; color: string }[] = [
  { status: "desking", label: "Desking", color: "#2B68AB" },
  { status: "financing", label: "Financing", color: "#FBCF09" },
  { status: "contract", label: "Contract", color: "#3FBCC4" },
  { status: "funded", label: "Funded / Delivered", color: "#22c55e" },
];

const FINANCING_BADGE: Record<string, string> = {
  not_started: "bg-zinc-800 text-zinc-400",
  submitted: "bg-amber-900 text-amber-300",
  approved: "bg-green-900 text-green-300",
  declined: "bg-red-900 text-red-300",
  countered: "bg-purple-900 text-purple-300",
};

function money(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return `$${Number(n).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function DragHandle({
  theme,
  fieldPath,
  sourceLabel,
  rows,
  numericColumns,
  labelColumn,
}: {
  theme: Theme;
  fieldPath: string[];
  sourceLabel: string;
  rows: Record<string, unknown>[];
  numericColumns: string[];
  labelColumn: string;
}) {
  if (rows.length === 0 || numericColumns.length === 0) return null;

  function handleDragStart(event: DragEvent<HTMLButtonElement>) {
    const payload: VisualizationDropPayload = {
      department: "Sales",
      itemKey: "deals",
      fieldPath,
      sourceLabel,
      rows,
      numericColumns,
      labelColumn,
    };
    event.dataTransfer.setData(VISUALIZATION_DRAG_TYPE, JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "copy";
  }

  return (
    <WorkButton type="submit"
      draggable
      onDragStart={handleDragStart}
      title="Drag into the Workspace to build a chart, then pin it"
      className={tc(
        theme,
        "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-700 text-zinc-500 hover:text-white hover:border-zinc-500 transition cursor-grab active:cursor-grabbing",
        "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-400 text-zinc-600 hover:text-black hover:border-zinc-600 transition cursor-grab active:cursor-grabbing"
      )}
    >
      ⠿ Drag to Workspace
    </WorkButton>
  );
}

export function DealDeskBoard({ theme, inline = false, initialDealId, initialDetailTab="worksheet" }: { theme: Theme; inline?: boolean; initialDealId?: string; initialDetailTab?: DetailTab }) {
  const session = getSession();
  const [deals, setDeals] = useState<Deal[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCancelled, setShowCancelled] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [newDealOpen, setNewDealOpen] = useState(false);
  const [detail, setDetail] = useState<{ dealId: string; tab: DetailTab } | null>(initialDealId ? {dealId:initialDealId,tab:initialDetailTab} : null);

  function refresh() {
    setLoading(true);
    listAllDeals()
      .then((d) => setDeals(Array.isArray(d) ? d : []))
      .catch(() => setDeals([]))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  function flash(msg: string) {
    setToast(msg);
    setTimeout(() => setToast(null), 4500);
  }

  function openDetail(dealId: string, tab: DetailTab = initialDetailTab) {
    setDetail({ dealId, tab });
  }

  const activeDeals = useMemo(() => deals.filter((d) => d.status !== "cancelled"), [deals]);
  const cancelledDeals = useMemo(() => deals.filter((d) => d.status === "cancelled"), [deals]);

  const byStatus = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const d of activeDeals) counts[d.status] = (counts[d.status] || 0) + 1;
    return counts;
  }, [activeDeals]);

  const kpiRows = useMemo(() => Object.entries(byStatus).map(([status, count]) => ({ status, count })), [byStatus]);

  async function handleDrop(targetStatus: DealStatus, e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    const dealId = e.dataTransfer.getData(DRAG_TYPE);
    if (!dealId) return;
    const deal = deals.find((d) => d.id === dealId);
    if (!deal || deal.status === targetStatus) return;

    try {
      if (deal.status === "desking" && targetStatus === "financing") {
        if (deal.selected_scenario_id) {
          // already selected somehow -- nothing to do, backend already moved status
        } else if (deal.scenarios.length === 1) {
          openDetail(deal.id, "worksheet");
          return;
        } else {
          flash(deal.scenarios.length === 0 ? "Add a scenario in the Worksheet tab first." : "This deal has more than one scenario -- pick one to select in the Worksheet tab.");
          openDetail(deal.id, "worksheet");
          return;
        }
      } else if (deal.status === "financing" && targetStatus === "contract") {
        if (deal.financing_status !== "approved") {
          flash("Financing must be approved before generating a contract.");
          openDetail(deal.id, "financing");
          return;
        }
        await generateContract(deal.id);
      } else if (deal.status === "contract" && targetStatus === "funded") {
        await fundDeal(deal.id);
      } else {
        flash("That move isn't supported -- open the deal to advance it step by step.");
        return;
      }
      refresh();
    } catch (err) {
      flash(err instanceof Error ? err.message : "Couldn't move that deal.");
    }
  }

  if(inline && newDealOpen)return <NewDealModal inline theme={theme} onClose={()=>setNewDealOpen(false)} onCreated={id=>{setNewDealOpen(false);refresh();openDetail(id);}}/>;
  if(inline && detail)return <DealDetailModal inline theme={theme} dealId={detail.dealId} initialTab={detail.tab} session={session} onClose={()=>setDetail(null)} onChanged={refresh}/>;
  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      {/* KPI strip */}
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        {COLUMNS.map((c, i) => (
          <div key={c.status} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5" style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }} />
            <div className="text-2xl font-semibold">{byStatus[c.status] || 0}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{c.label}</div>
          </div>
        ))}
        <div className="col-span-4 flex justify-end">
          <DragHandle theme={theme} fieldPath={["deals", "by_status"]} sourceLabel="Deals by Status" rows={kpiRows} numericColumns={["count"]} labelColumn="status" />
        </div>
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2 flex items-center justify-between gap-2 flex-wrap", "border-b border-zinc-200 px-4 py-2 flex items-center justify-between gap-2 flex-wrap")}>
        <div className="text-lg font-semibold">Pipeline</div>
        <div className="flex items-center gap-2">
          <WorkButton type="submit"
            onClick={() => setShowCancelled((v) => !v)}
            className={
              showCancelled
                ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition border border-zinc-800", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition border border-zinc-300")
            }
          >
            {showCancelled ? "Hide Cancelled" : `Show Cancelled (${cancelledDeals.length})`}
          </WorkButton>
          <WorkButton type="submit" variant="primary" onClick={() => setNewDealOpen(true)} className="text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition">
            + New Deal
          </WorkButton>
        </div>
      </div>

      {toast && (
        <div className="mx-4 mt-2 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{toast}</div>
      )}

      <div className="flex-1 min-h-0 overflow-x-auto overflow-y-hidden p-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <div className="flex gap-3 h-full">
            {(showCancelled ? [...COLUMNS, { status: "cancelled" as DealStatus, label: "Cancelled", color: "#71717a" }] : COLUMNS).map((col) => {
              const cards = (col.status === "cancelled" ? cancelledDeals : activeDeals.filter((d) => d.status === col.status));
              return (
                <DealColumn key={col.status} theme={theme} col={col} cards={cards} onDrop={(e) => handleDrop(col.status, e)} onOpen={(id) => openDetail(id)} />
              );
            })}
          </div>
        )}
      </div>

      {newDealOpen && (
        <NewDealModal
          theme={theme}
          onClose={() => setNewDealOpen(false)}
          onCreated={(dealId) => {
            setNewDealOpen(false);
            refresh();
            openDetail(dealId, "worksheet");
          }}
        />
      )}

      {detail && (
        <DealDetailModal
          theme={theme}
          dealId={detail.dealId}
          initialTab={detail.tab}
          session={session}
          onClose={() => setDetail(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}

function DealColumn({
  theme,
  col,
  cards,
  onDrop,
  onOpen,
}: {
  theme: Theme;
  col: { status: DealStatus; label: string; color: string };
  cards: Deal[];
  onDrop: (e: DragEvent<HTMLDivElement>) => void;
  onOpen: (dealId: string) => void;
}) {
  const [isOver, setIsOver] = useState(false);

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        e.dataTransfer.dropEffect = "move";
        setIsOver(true);
      }}
      onDragLeave={() => setIsOver(false)}
      onDrop={(e) => {
        setIsOver(false);
        onDrop(e);
      }}
      className={
        isOver
          ? "w-72 shrink-0 flex flex-col rounded-lg border-2 border-brand-teal bg-brand-teal/5 overflow-hidden"
          : tc(theme, "w-72 shrink-0 flex flex-col rounded-lg border border-black/20 bg-brand-charcoal overflow-hidden", "w-72 shrink-0 flex flex-col rounded-lg border border-zinc-300 bg-zinc-50 overflow-hidden")
      }
    >
      <div className="px-2.5 py-2 flex items-center justify-between shrink-0" style={{ borderBottom: `2px solid ${col.color}` }}>
        <span className={tc(theme, "text-xs font-bold uppercase tracking-wide text-zinc-300", "text-xs font-bold uppercase tracking-wide text-zinc-700")}>{col.label}</span>
        <span className="text-xs font-bold px-1.5 py-0.5 rounded-full" style={{ backgroundColor: col.color, color: "#111" }}>
          {cards.length}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-1.5 space-y-1.5">
        {cards.length === 0 && <div className={tc(theme, "text-xs text-zinc-700 text-center py-4", "text-xs text-zinc-400 text-center py-4")}>Drop a deal here</div>}
        {cards.map((d) => (
          <div
            key={d.id}
            draggable
            onDragStart={(e) => {
              e.dataTransfer.setData(DRAG_TYPE, d.id);
              e.dataTransfer.effectAllowed = "move";
            }}
            onClick={() => onOpen(d.id)}
            className={tc(
              theme,
              "rounded-md border border-zinc-800 bg-zinc-900 px-2.5 py-2 cursor-grab active:cursor-grabbing hover:border-zinc-600 transition",
              "rounded-md border border-zinc-300 bg-white px-2.5 py-2 cursor-grab active:cursor-grabbing hover:border-zinc-400 transition"
            )}
          >
            <div className="text-xs font-medium truncate">{d.customer?.name || d.customer_id}</div>
            <div className="text-xs text-zinc-500 truncate">{d.vehicle?.description || d.vehicle_id}</div>
            <div className="flex items-center gap-1.5 mt-1 flex-wrap">
              {d.status === "financing" && (
                <span className={`text-xs px-1.5 py-0.5 rounded uppercase ${FINANCING_BADGE[d.financing_status] || "bg-zinc-800 text-zinc-400"}`}>{d.financing_status.replace("_", " ")}</span>
              )}
              {d.selected_scenario_id && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-black/30 text-zinc-300">
                  {money(d.scenarios.find((s) => s.id === d.selected_scenario_id)?.estimated_monthly_payment)}/mo
                </span>
              )}
              {d.vehicle?.gross !== null && d.vehicle?.gross !== undefined && (
                <span className="text-xs px-1.5 py-0.5 rounded bg-black/30 text-zinc-300">{money(d.vehicle.gross)} gross</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

export function NewDealModal({
  theme,
  inline = false,
  onClose,
  onCreated,
  initialCustomer,
  initialVehicle,
}: {
  theme: Theme;
  inline?: boolean;
  onClose: () => void;
  onCreated: (dealId: string) => void;
  initialCustomer?: CustomerBrief | null;
  initialVehicle?: LinkedVehicle | null;
}) {
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerResults, setCustomerResults] = useState<CustomerBrief[]>([]);
  const [customer, setCustomer] = useState<CustomerBrief | null>(initialCustomer || null);
  const [vehicleQuery, setVehicleQuery] = useState("");
  const [vehicleResults, setVehicleResults] = useState<LinkedVehicle[]>([]);
  const [vehicle, setVehicle] = useState<LinkedVehicle | null>(initialVehicle || null);
  const [saving, setSaving] = useState(false);
  const [saveError,setSaveError]=useState("");

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleSubmit() {
    if (!customer || !vehicle) return;
    setSaving(true);setSaveError("");
    try {
      const deal = await createDeal({ customer_id: customer.id, vehicle_id: vehicle.id });
      onCreated(deal.id);
    } catch (e) {
      setSaveError((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <WorkOverlay data-department-work="" className={inline ? "workspace-inline-editor" : "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"} onClick={inline ? undefined : onClose}>
      <div onClick={(e) => e.stopPropagation()} className={inline ? "workspace-editor-surface" : tc(theme, "w-full max-w-lg rounded-xl border border-black/20 bg-brand-charcoal text-white shadow-2xl", "w-full max-w-lg rounded-xl border border-zinc-200 bg-white text-black shadow-2xl")}>
        <div className={tc(theme, "flex items-center justify-between px-4 py-3 border-b border-zinc-800", "flex items-center justify-between px-4 py-3 border-b border-zinc-200")}>
          <div className="work-detail-title">Start a New Deal</div>
          <WorkButton type="submit" onClick={onClose} className="text-zinc-500 hover:text-white text-lg leading-none">{inline ? "← Back" : "✕"}</WorkButton>
        </div>
        <div className="p-4 space-y-3">
          {saveError&&<p role="alert">{saveError}</p>}
          <div>
            <label className="text-xs text-zinc-500">Customer</label>
            {customer ? (
              <div className="flex items-center justify-between mt-1 px-2.5 py-1.5 rounded-md bg-black/20 text-sm">
                <span>{customer.name}</span>
                <WorkButton type="submit" onClick={() => setCustomer(null)} className="text-zinc-500 hover:text-white text-xs">Change</WorkButton>
              </div>
            ) : (
              <>
                <WorkField label="Search customers by name/email/phone"><WorkInput
                  value={customerQuery}
                  onChange={(e) => {
                    setCustomerQuery(e.target.value);
                    searchCustomers(e.target.value).then(setCustomerResults);
                  }}
                  placeholder="Search customers by name/email/phone…"
                  className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`}
                /></WorkField>
                {customerResults.length > 0 && (
                  <div className={tc(theme, "mt-1.5 border border-zinc-800 rounded-md divide-y divide-zinc-800 max-h-32 overflow-y-auto", "mt-1.5 border border-zinc-200 rounded-md divide-y divide-zinc-200 max-h-32 overflow-y-auto")}>
                    {customerResults.map((c) => (
                      <WorkButton type="submit" key={c.id} onClick={() => { setCustomer(c); setCustomerResults([]); }} className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-zinc-800/50 transition">
                        {c.name} {c.email ? `— ${c.email}` : ""}
                      </WorkButton>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          <div>
            <label className="text-xs text-zinc-500">Vehicle (unsold inventory)</label>
            {vehicle ? (
              <div className="flex items-center justify-between mt-1 px-2.5 py-1.5 rounded-md bg-black/20 text-sm">
                <span>{vehicle.year} {vehicle.make} {vehicle.model} {vehicle.trim}</span>
                <WorkButton type="submit" onClick={() => setVehicle(null)} className="text-zinc-500 hover:text-white text-xs">Change</WorkButton>
              </div>
            ) : (
              <>
                <WorkField label="Search unsold inventory"><WorkInput
                  value={vehicleQuery}
                  onChange={(e) => {
                    setVehicleQuery(e.target.value);
                    searchInventoryForPost(e.target.value).then(setVehicleResults);
                  }}
                  placeholder="Search unsold inventory…"
                  className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`}
                /></WorkField>
                {vehicleResults.length > 0 && (
                  <div className={tc(theme, "mt-1.5 border border-zinc-800 rounded-md divide-y divide-zinc-800 max-h-32 overflow-y-auto", "mt-1.5 border border-zinc-200 rounded-md divide-y divide-zinc-200 max-h-32 overflow-y-auto")}>
                    {vehicleResults.map((v) => (
                      <WorkButton type="submit" key={v.id} onClick={() => { setVehicle(v); setVehicleResults([]); }} className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-zinc-800/50 transition">
                        {v.year} {v.make} {v.model} {v.trim} — {v.price ? money(Number(v.price)) : "—"}
                      </WorkButton>
                    ))}
                  </div>
                )}
              </>
            )}
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <WorkButton type="submit" onClick={onClose} className="text-xs px-3 py-2 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition">Cancel</WorkButton>
            <WorkButton type="submit" variant="primary"
              onClick={handleSubmit}
              disabled={!customer || !vehicle || saving}
              className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
            >
              {saving ? "Creating…" : "Start Deal"}
            </WorkButton>
          </div>
        </div>
      </div>
    </WorkOverlay>
  );
}

type DetailTab = "worksheet" | "trade" | "financing" | "contract";

export function DealDetailModal({
  theme,
  inline = false,
  dealId,
  initialTab,
  session,
  onClose,
  onChanged,
}: {
  theme: Theme;
  inline?: boolean;
  dealId: string;
  initialTab: DetailTab;
  session: { role: string; employeeId: string } | null;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [deal, setDeal] = useState<Deal | null>(null);
  const [loading, setLoading] = useState(true);
  const [tab, setTab] = useState<DetailTab>(initialTab);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canEdit = !!deal && (deal.created_by === session?.employeeId || ["ADMIN", "OPERATIONS", "FINANCE"].includes(session?.role || ""));
  const canDoFinancing = ["ADMIN", "OPERATIONS", "FINANCE"].includes(session?.role || "");

  function refresh() {
    setLoading(true);
    getDeal(dealId)
      .then(setDeal)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [dealId]);

  async function act<T>(fn: () => Promise<T>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      refresh();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const TABS: { key: DetailTab; label: string }[] = [
    { key: "worksheet", label: "Worksheet" },
    { key: "trade", label: "Trade Appraisal" },
    { key: "financing", label: "Finance handoff" },
    { key: "contract", label: "Contract" },
  ];

  return (
    <WorkOverlay data-department-work="" className={inline ? "workspace-inline-editor" : "fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"} onClick={inline ? undefined : onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={inline ? "workspace-editor-surface flex flex-col" : tc(theme, "w-full max-w-3xl max-h-[92vh] flex flex-col rounded-xl border border-black/20 bg-brand-charcoal text-white shadow-2xl", "w-full max-w-3xl max-h-[92vh] flex flex-col rounded-xl border border-zinc-200 bg-white text-black shadow-2xl")}
      >
        <div className={tc(theme, "flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0", "flex items-center justify-between px-4 py-3 border-b border-zinc-200 shrink-0")}>
          <div>
            <div className="work-detail-title">{deal ? `${deal.customer?.name || deal.customer_id} — ${deal.vehicle?.description || deal.vehicle_id}` : "Deal"}</div>
            {deal && <div className="text-xs text-zinc-500">{deal.id} · {deal.status}{deal.status === "financing" ? ` · financing ${deal.financing_status}` : ""}</div>}
          </div>
          <WorkButton type="submit" onClick={onClose} className="text-zinc-500 hover:text-white text-lg leading-none">{inline ? "← Back" : "✕"}</WorkButton>
        </div>

        {loading || !deal ? (
          <div className="p-4 text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div className={tc(theme, "border-b border-zinc-800 px-4 py-2 flex items-center gap-1.5 shrink-0", "border-b border-zinc-200 px-4 py-2 flex items-center gap-1.5 shrink-0")}>
              {TABS.map((t) => (
                <WorkButton data-work-view aria-pressed={tab === t.key} type="submit"
                  key={t.key}
                  onClick={() => setTab(t.key)}
                  className={
                    tab === t.key
                      ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                      : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition")
                  }
                >
                  {t.label}
                </WorkButton>
              ))}
            </div>

            {error && <div className="mx-4 mt-2 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300 shrink-0">{error}</div>}

            <div className="flex-1 overflow-y-auto p-4">
              {tab === "worksheet" && <WorksheetTab theme={theme} deal={deal} canEdit={canEdit} busy={busy} act={act} />}
              {tab === "trade" && <TradeAppraisalTab theme={theme} deal={deal} canEdit={canEdit} canApprove={canDoFinancing} busy={busy} act={act} />}
              {tab === "financing" && <FinancingTab theme={theme} deal={deal} canDoFinancing={canDoFinancing} busy={busy} act={act} />}
              {tab === "contract" && <ContractTab theme={theme} deal={deal} canDoFinancing={canDoFinancing} busy={busy} act={act} onNavigate={setTab} />}
            </div>

            <div className={tc(theme, "border-t border-zinc-800 px-4 py-2.5 flex items-center justify-between shrink-0", "border-t border-zinc-200 px-4 py-2.5 flex items-center justify-between shrink-0")}>
              <div>
                {canEdit && deal.status !== "funded" && deal.status !== "cancelled" && (
                  <WorkButton type="submit" disabled={busy} onClick={() => act(() => cancelDeal(deal.id))} className="text-xs px-3 py-1.5 rounded border border-zinc-700 text-zinc-400 hover:text-white transition disabled:opacity-50">
                    Cancel Deal
                  </WorkButton>
                )}
              </div>
              <WorkButton type="submit" onClick={onClose} className="text-xs px-3 py-2 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition">Close</WorkButton>
            </div>
          </>
        )}
      </div>
    </WorkOverlay>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div className="text-xs text-zinc-500">{label}</div>
      <div className="text-sm">{children}</div>
    </div>
  );
}

function WorksheetTab({
  theme,
  deal,
  canEdit,
  busy,
  act,
}: {
  theme: Theme;
  deal: Deal;
  canEdit: boolean;
  busy: boolean;
  act: <T>(fn: () => Promise<T>) => Promise<void>;
}) {
  const [label, setLabel] = useState("");
  const [salePrice, setSalePrice] = useState(deal.vehicle?.price ? String(deal.vehicle.price) : "");
  const [downPayment, setDownPayment] = useState("0");
  const [termMonths, setTermMonths] = useState("60");
  const [cashDeal, setCashDeal] = useState(false);

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const editable = canEdit && deal.status === "desking";

  async function handleAdd() {
    const price = parseFloat(salePrice || "0");
    await act(() =>
      addScenario(deal.id, {
        label: label || undefined,
        sale_price: price,
        down_payment: cashDeal ? price : parseFloat(downPayment || "0"),
        term_months: parseInt(termMonths, 10) || 60,
      })
    );
    setLabel("");
  }

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <Field label="Customer">{deal.customer?.name || deal.customer_id}{deal.customer?.credit_score ? ` (credit: ${deal.customer.credit_score})` : ""}</Field>
        <Field label="Vehicle">{deal.vehicle?.description || deal.vehicle_id}</Field>
        <Field label="List Price / Cost / Gross">{money(deal.vehicle?.price)} / {money(deal.vehicle?.cost)} / {money(deal.vehicle?.gross)}</Field>
      </div>

      <div>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Pencil Tool — Scenarios</div>
        {deal.scenarios.length === 0 ? (
          <div className="text-sm text-zinc-500">No scenarios yet — build one below.</div>
        ) : (
          <div className="grid grid-cols-1 gap-2">
            {deal.scenarios.map((s) => (
              <div key={s.id} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 flex items-center justify-between gap-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 flex items-center justify-between gap-3")}>
                <div>
                  <div className="text-sm font-medium flex items-center gap-1.5">
                    {s.label}
                    {deal.selected_scenario_id === s.id && <span className="text-xs px-1.5 py-0.5 rounded bg-brand-blue text-white uppercase">Selected</span>}
                  </div>
                  <div className="text-xs text-zinc-500">
                    {money(s.sale_price)} sale · {money(s.down_payment)} down · {s.term_months}mo · est. {s.estimated_apr}% APR · {money(s.estimated_monthly_payment)}/mo
                  </div>
                </div>
                {editable && (
                  <div className="flex items-center gap-1.5 shrink-0">
                    {!deal.selected_scenario_id && (
                      <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => act(() => selectScenario(deal.id, s.id))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
                        Choose option & hand off to Finance
                      </WorkButton>
                    )}
                    <WorkButton type="submit" disabled={busy} onClick={() => act(() => removeScenario(deal.id, s.id))} className="text-xs px-2 py-1 rounded border border-zinc-700 text-zinc-400 hover:text-white transition disabled:opacity-50">
                      Remove
                    </WorkButton>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {editable && (
        <div className={tc(theme, "rounded-lg border border-zinc-800 p-3 space-y-2", "rounded-lg border border-zinc-200 p-3 space-y-2")}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Add Scenario (Option {deal.scenarios.length + 1})</div>
          <div className="grid grid-cols-2 gap-2">
            <WorkField label="Label"><WorkInput value={label} onChange={(e) => setLabel(e.target.value)} placeholder={`Option ${deal.scenarios.length + 1}`} className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
            <WorkField label="Sale price"><WorkInput value={salePrice} onChange={(e) => setSalePrice(e.target.value)} placeholder="Sale price" type="number" className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
            <WorkField label="Down payment"><WorkInput value={downPayment} onChange={(e) => setDownPayment(e.target.value)} placeholder="Down payment" type="number" disabled={cashDeal} className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-50 ${textClass}`} /></WorkField>
            <WorkField label="Term Months"><WorkSelect value={termMonths} onChange={(e) => setTermMonths(e.target.value)} disabled={cashDeal} className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-50 ${textClass}`}>
              {[24, 36, 48, 60, 72, 84].map((m) => (
                <option key={m} value={m}>{m} months</option>
              ))}
            </WorkSelect></WorkField>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs cursor-pointer">
              <WorkInput type="checkbox" checked={cashDeal} onChange={(e) => setCashDeal(e.target.checked)} />
              Cash deal (down payment covers full sale price)
            </label>
            <label className="flex items-center gap-1.5 text-xs text-zinc-600 cursor-not-allowed" title="Lease math isn't supported by the desking engine yet.">
              <WorkInput type="radio" disabled />
              Lease scenario (not yet supported)
            </label>
          </div>
          <WorkButton type="submit" variant="primary" disabled={busy || !salePrice} onClick={handleAdd} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            + Add Scenario
          </WorkButton>
        </div>
      )}

      {deal.status !== "desking" && (
        <div className="text-xs text-zinc-500">Scenarios are locked once a deal moves past desking.</div>
      )}
    </div>
  );
}

function TradeAppraisalTab({
  theme,
  deal,
  canEdit,
  canApprove,
  busy,
  act,
}: {
  theme: Theme;
  deal: Deal;
  canEdit: boolean;
  canApprove: boolean;
  busy: boolean;
  act: <T>(fn: () => Promise<T>) => Promise<void>;
}) {
  const trade = deal.trade_in || {};
  const [vinCheck, setVinCheck] = useState<TradeInVinDecodeResult | null>(null);
  const [vinCheckError, setVinCheckError] = useState<string | null>(null);
  const [checkingVin, setCheckingVin] = useState(false);

  async function handleCheckVin() {
    setCheckingVin(true);
    setVinCheckError(null);
    try {
      const result = await decodeTradeInVin(deal.id);
      setVinCheck(result);
    } catch (e) {
      setVinCheckError((e as Error).message);
    } finally {
      setCheckingVin(false);
    }
  }

  const [form, setForm] = useState({
    vin: trade.vin || "",
    year: trade.year ? String(trade.year) : "",
    make: trade.make || "",
    model: trade.model || "",
    trim: trade.trim || "",
    mileage: trade.mileage ? String(trade.mileage) : "",
    condition: trade.condition || "Good",
    recon_estimate: trade.recon_estimate ? String(trade.recon_estimate) : "",
    acv: trade.acv ? String(trade.acv) : "",
    market_value_estimate: trade.market_value_estimate ? String(trade.market_value_estimate) : "",
    notes: trade.notes || "",
  });

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const editable = canEdit && deal.status === "desking";

  async function handleSave() {
    await act(() =>
      updateTradeAppraisal(deal.id, {
        vin: form.vin || null,
        year: form.year || null,
        make: form.make || null,
        model: form.model || null,
        trim: form.trim || null,
        mileage: form.mileage ? Number(form.mileage) : null,
        condition: form.condition || null,
        recon_estimate: form.recon_estimate ? Number(form.recon_estimate) : null,
        acv: form.acv ? Number(form.acv) : null,
        market_value_estimate: form.market_value_estimate ? Number(form.market_value_estimate) : null,
        notes: form.notes || null,
      })
    );
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-zinc-500">
        No market-data API is connected in this environment — enter the trade's condition/value details manually. Editable only while the deal is in desking. Once a VIN is saved, use "Check VIN Match" below to cross-check the entered year/make against a real (offline standards-based) VIN decode.
      </div>

      {trade.approved && (
        <div className="rounded-lg border border-green-900 bg-green-950/30 px-3 py-2 text-xs text-green-300">
          ✓ Approved by {trade.approved_by} at {trade.approved_at ? new Date(trade.approved_at).toLocaleString() : ""}
        </div>
      )}
      {!trade.approved && trade.appraised_at && (
        <div className="rounded-lg border border-amber-900 bg-amber-950/30 px-3 py-2 text-xs text-amber-300 flex items-center justify-between gap-2">
          <span>Awaiting manager approval — appraised by {trade.appraised_by}.</span>
          {canApprove && (
            <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => act(() => approveTradeAppraisal(deal.id))} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50 shrink-0">
              Approve Appraisal
            </WorkButton>
          )}
        </div>
      )}

      <div className="grid grid-cols-3 gap-2">
        <WorkField label="VIN"><WorkInput disabled={!editable} value={form.vin} onChange={(e) => setForm({ ...form, vin: e.target.value })} placeholder="VIN" className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`} /></WorkField>
        <WorkField label="Year"><WorkInput disabled={!editable} value={form.year} onChange={(e) => setForm({ ...form, year: e.target.value })} placeholder="Year" className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`} /></WorkField>
        <WorkField label="Mileage"><WorkInput disabled={!editable} value={form.mileage} onChange={(e) => setForm({ ...form, mileage: e.target.value })} placeholder="Mileage" type="number" className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`} /></WorkField>
        <WorkField label="Make"><WorkInput disabled={!editable} value={form.make} onChange={(e) => setForm({ ...form, make: e.target.value })} placeholder="Make" className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`} /></WorkField>
        <WorkField label="Model"><WorkInput disabled={!editable} value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} placeholder="Model" className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`} /></WorkField>
        <WorkField label="Trim"><WorkInput disabled={!editable} value={form.trim} onChange={(e) => setForm({ ...form, trim: e.target.value })} placeholder="Trim" className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`} /></WorkField>
        <WorkField label="Condition"><WorkSelect disabled={!editable} value={form.condition} onChange={(e) => setForm({ ...form, condition: e.target.value })} className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`}>
          {["Excellent", "Good", "Fair", "Poor"].map((c) => (
            <option key={c} value={c}>{c}</option>
          ))}
        </WorkSelect></WorkField>
        <WorkField label="Recon estimate ($)"><WorkInput disabled={!editable} value={form.recon_estimate} onChange={(e) => setForm({ ...form, recon_estimate: e.target.value })} placeholder="Recon estimate ($)" type="number" className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`} /></WorkField>
        <WorkField label="Market value estimate ($)"><WorkInput disabled={!editable} value={form.market_value_estimate} onChange={(e) => setForm({ ...form, market_value_estimate: e.target.value })} placeholder="Market value estimate ($)" type="number" className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`} /></WorkField>
        <WorkField label="ACV — what we'll allow ($)"><WorkInput disabled={!editable} value={form.acv} onChange={(e) => setForm({ ...form, acv: e.target.value })} placeholder="ACV — what we'll allow ($)" type="number" className={`rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 font-medium ${textClass}`} /></WorkField>
      </div>
      <WorkField label="Condition notes"><WorkTextarea disabled={!editable} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} rows={2} placeholder="Condition notes…" className={`w-full rounded-md border px-3 py-1.5 text-sm disabled:opacity-60 ${textClass}`} /></WorkField>

      <div className="flex items-center gap-2">
        <WorkButton type="submit" disabled={checkingVin || !trade.vin} onClick={handleCheckVin} className="text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50">
          {checkingVin ? "Checking…" : "Check VIN Match"}
        </WorkButton>
        {!trade.vin && <span className="text-xs text-zinc-600 italic">Save a VIN above first.</span>}
      </div>

      {vinCheckError && <div className="text-xs text-red-400">{vinCheckError}</div>}

      {vinCheck && (
        <div className="rounded-lg border border-zinc-800 px-3 py-2 text-xs space-y-1">
          <div className="text-zinc-500">VIN Match Check — {vinCheck.vin}</div>
          {vinCheck.valid_format ? (
            <>
              {vinCheck.check_digit_valid === false && (
                <div className="text-amber-400">⚠ Check digit does not validate — double-check the VIN was entered correctly.</div>
              )}
              {vinCheck.mismatches.length > 0 ? (
                <div className="text-amber-400">
                  ⚠ {vinCheck.mismatches.map((m) => `${m.field}: entered "${m.entered}" vs. decoded "${m.decoded}"`).join("; ")}
                </div>
              ) : (
                <div className="text-green-400">✅ Entered year/make match the decoded VIN.</div>
              )}
              <div className="text-xs text-zinc-600 italic">{vinCheck.gap_note}</div>
            </>
          ) : (
            <div className="text-zinc-500">{vinCheck.format_error}</div>
          )}
        </div>
      )}

      {editable && (
        <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleSave} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          Save Trade Appraisal
        </WorkButton>
      )}
    </div>
  );
}

function FinancingTab({
  theme,
  deal,
  canDoFinancing,
  busy,
  act,
}: {
  theme: Theme;
  deal: Deal;
  canDoFinancing: boolean;
  busy: boolean;
  act: <T>(fn: () => Promise<T>) => Promise<void>;
}) {
  const [lenders, setLenders] = useState<Lender[]>([]);
  const [lenderId, setLenderId] = useState("");
  const [decision, setDecision] = useState<"approved" | "declined" | "countered">("approved");
  const [notes, setNotes] = useState("");
  const [counterApr, setCounterApr] = useState("");
  const [counterTerm, setCounterTerm] = useState("60");
  const [counterDown, setCounterDown] = useState("");
  const [counterAmount, setCounterAmount] = useState("");
  const [counterPayment, setCounterPayment] = useState("");

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  useEffect(() => {
    listLenders().then(setLenders);
  }, []);

  if (deal.status === "desking") {
    return <div className="text-sm text-zinc-500">Review the worksheet and trade appraisal, then choose the agreed pricing option to move the deal to the Finance queue. This does not approve credit or submit to a lender.</div>;
  }

  async function handleDecision() {
    const countered_terms =
      decision === "countered"
        ? {
            apr: parseFloat(counterApr || "0"),
            term_months: parseInt(counterTerm, 10) || 60,
            down_payment: parseFloat(counterDown || "0"),
            amount_financed: parseFloat(counterAmount || "0"),
            monthly_payment: parseFloat(counterPayment || "0"),
          }
        : null;
    await act(() => recordLenderDecision(deal.id, decision, countered_terms, notes || null));
  }

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-zinc-500/30 p-3"><strong>Finance handoff</strong><p className="text-sm mt-2">This deal is in the {deal.status} stage. Customer and vehicle details, the selected pricing option, and trade appraisal remain on this shared deal record.</p>{deal.financing_status === "not_started" && <p className="text-sm mt-2">Waiting for Finance to review financing. No lender submission or credit approval has been recorded.</p>}{!canDoFinancing && <p className="text-sm mt-2">Finance actions are available to authorized Finance, Operations and Admin users.</p>}</div>
      {deal.financing_status === "not_started" && canDoFinancing && (
        <div className={tc(theme, "rounded-lg border border-zinc-800 p-3 space-y-2", "rounded-lg border border-zinc-200 p-3 space-y-2")}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Select Lender</div>
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => act(() => chooseInHouseFinancing(deal.id))} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            In-House Financing (BHPH)
          </WorkButton>
          <div className="flex items-center gap-2 pt-1">
            <WorkField label="Lender"><WorkSelect value={lenderId} onChange={(e) => setLenderId(e.target.value)} className={`flex-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`}>
              <option value="">Choose an outside lender…</option>
              {lenders.map((l) => (
                <option key={l.id} value={l.id}>{l.name}</option>
              ))}
            </WorkSelect></WorkField>
            <WorkButton type="submit" disabled={busy || !lenderId} onClick={() => act(() => submitToLender(deal.id, lenderId))} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition disabled:opacity-50">
              Submit
            </WorkButton>
          </div>
        </div>
      )}

      {deal.financing_type && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Financing Type">{deal.financing_type === "in_house" ? "In-House (BHPH)" : "Outside Lender"}</Field>
          <Field label="Status">
            <span className={`text-xs px-1.5 py-0.5 rounded uppercase ${FINANCING_BADGE[deal.financing_status] || ""}`}>{deal.financing_status.replace("_", " ")}</span>
          </Field>
        </div>
      )}

      {deal.financing_terms && (
        <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 grid grid-cols-3 gap-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 grid grid-cols-3 gap-2")}>
          <Field label="APR">{deal.financing_terms.apr}%</Field>
          <Field label="Term">{deal.financing_terms.term_months} months</Field>
          <Field label="Monthly Payment">{money(deal.financing_terms.monthly_payment)}</Field>
          <Field label="Down Payment">{money(deal.financing_terms.down_payment)}</Field>
          <Field label="Amount Financed">{money(deal.financing_terms.amount_financed)}</Field>
        </div>
      )}

      {deal.financing_status === "submitted" && canDoFinancing && (
        <div className={tc(theme, "rounded-lg border border-zinc-800 p-3 space-y-2", "rounded-lg border border-zinc-200 p-3 space-y-2")}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Record Lender Decision</div>
          <div className="flex gap-3">
            {(["approved", "declined", "countered"] as const).map((d) => (
              <label key={d} className="flex items-center gap-1.5 text-xs cursor-pointer">
                <WorkInput type="radio" name="decision" checked={decision === d} onChange={() => setDecision(d)} />
                {d[0].toUpperCase() + d.slice(1)}
              </label>
            ))}
          </div>
          {decision === "countered" && (
            <div className="grid grid-cols-3 gap-2">
              <WorkField label="APR %"><WorkInput value={counterApr} onChange={(e) => setCounterApr(e.target.value)} placeholder="APR %" type="number" className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
              <WorkField label="Term months"><WorkInput value={counterTerm} onChange={(e) => setCounterTerm(e.target.value)} placeholder="Term months" type="number" className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
              <WorkField label="Down payment"><WorkInput value={counterDown} onChange={(e) => setCounterDown(e.target.value)} placeholder="Down payment" type="number" className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
              <WorkField label="Amount financed"><WorkInput value={counterAmount} onChange={(e) => setCounterAmount(e.target.value)} placeholder="Amount financed" type="number" className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
              <WorkField label="Monthly payment"><WorkInput value={counterPayment} onChange={(e) => setCounterPayment(e.target.value)} placeholder="Monthly payment" type="number" className={`rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
            </div>
          )}
          <WorkField label="Notes (required for a decline)"><WorkTextarea value={notes} onChange={(e) => setNotes(e.target.value)} rows={2} placeholder="Notes (required for a decline)…" className={`w-full rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={handleDecision} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            Record Decision
          </WorkButton>
        </div>
      )}

      {deal.financing_status === "countered" && (
        <WorkButton type="submit" variant="primary" disabled={busy || !canDoFinancing} onClick={() => act(() => acceptCounteredTerms(deal.id))} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          Accept Countered Terms
        </WorkButton>
      )}

      {deal.financing_status === "declined" && (
        <div className="text-xs text-zinc-500">Financing was declined{deal.financing_notes ? `: ${deal.financing_notes}` : ""}. Choose in-house financing or submit to a different lender above.</div>
      )}
    </div>
  );
}

function ContractTab({
  theme,
  deal,
  canDoFinancing,
  busy,
  act,
  onNavigate,
}: {
  theme: Theme;
  deal: Deal;
  canDoFinancing: boolean;
  busy: boolean;
  act: <T>(fn: () => Promise<T>) => Promise<void>;
  onNavigate?: (tab: DetailTab) => void;
}) {
  const [reviewFunding, setReviewFunding] = useState(false);
  if (deal.status === "cancelled") return <p>This deal is cancelled. Contract and funding actions are unavailable.</p>;
  if (deal.status === "desking" || (deal.status === "financing" && deal.financing_status !== "approved")) {
    const worksheet = deal.status === "desking";
    return <section className="space-y-3" aria-label="Contract preparation">
      <h3 className="text-lg font-semibold">{worksheet ? "Complete the Sales worksheet" : "Resolve financing before preparing the contract"}</h3>
      <p className="text-sm">{worksheet ? "Review pricing and the trade appraisal, then choose the agreed option for Finance." : `Financing is ${deal.financing_status.replaceAll("_", " ")}. Finance must record approved terms before an internal contract summary can be generated.`}</p>
      <p className="text-sm">Customer: {deal.customer?.name || deal.customer_id} · Vehicle: {deal.vehicle?.description || deal.vehicle_id}</p>
      {onNavigate && <WorkButton type="submit" className="rounded-md border px-4 py-2 text-sm" onClick={()=>onNavigate(worksheet ? "worksheet" : "financing")}>{worksheet ? "Review worksheet" : "Review financing"} →</WorkButton>}
    </section>;
  }

  return (
    <div className="space-y-4">
      <section className="rounded-lg border border-zinc-500/30 p-3 space-y-2">
        <h3 className="text-lg font-semibold">{deal.status === "funded" ? "Funding recorded" : deal.status === "contract" ? "Review summary and record funding" : "Prepare the internal contract summary"}</h3>
        <p className="text-sm">This summary supports the dealership workflow. It is not a signed retail contract or proof that required documents are complete.</p>
        {!canDoFinancing && <p className="text-sm">Authorized Finance, Operations or Admin staff handle contract preparation and funding.</p>}
        {onNavigate && <WorkButton type="submit" className="rounded-md border px-3 py-2 text-sm" onClick={()=>onNavigate("financing")}>Review financing terms →</WorkButton>}
      </section>
      {deal.status === "financing" && deal.financing_status === "approved" && canDoFinancing && (
        <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => act(() => generateContract(deal.id))} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
          Generate internal contract summary
        </WorkButton>
      )}

      {deal.contract && (
        <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 space-y-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2")}>
          <div className="grid grid-cols-3 gap-2">
            <Field label="Customer">{deal.contract.customer_name}</Field>
            <Field label="Vehicle">{deal.contract.vehicle_description}</Field>
            <Field label="VIN">{deal.contract.vin || "—"}</Field>
            <Field label="Sale Price">{money(deal.contract.sale_price)}</Field>
            <Field label="Trade-In Value">{money(deal.contract.trade_in_value)}</Field>
            <Field label="Down Payment">{money(deal.contract.down_payment)}</Field>
            <Field label="Amount Financed">{money(deal.contract.amount_financed)}</Field>
            <Field label="APR / Term">{deal.contract.apr}% / {deal.contract.term_months}mo</Field>
            <Field label="Monthly Payment">{money(deal.contract.monthly_payment)}</Field>
            <Field label="Lender">{deal.contract.lender_name || "—"}</Field>
          </div>
          <div className="text-xs text-zinc-500 pt-1 border-t border-zinc-800/60">{deal.contract.disclosures.join(" ")}</div>
        </div>
      )}

      {deal.status === "contract" && canDoFinancing && (
        <section className="rounded-lg border border-zinc-500/30 p-3 space-y-3" aria-label="Record funding">
          {!reviewFunding ? <><p className="text-sm">After completing your dealership’s funding checks, review what recording funding will change.</p><WorkButton type="submit" disabled={busy || !deal.contract} onClick={()=>setReviewFunding(true)} className="rounded-md border px-4 py-2 text-sm">Review funding action →</WorkButton></> : <>
            <h4 className="font-semibold">Record funding for {deal.customer?.name || deal.customer_id}</h4>
            <p className="text-sm">This creates the Finance Contract record, links the customer to the vehicle purchase, and marks {deal.vehicle?.description || deal.vehicle_id} sold. It does not transfer money or verify that funds were received.</p>
            <div className="flex flex-wrap gap-3"><WorkButton type="submit" variant="primary" disabled={busy} onClick={() => act(() => fundDeal(deal.id))} className="text-sm px-4 py-2 rounded-md bg-brand-blue text-white disabled:opacity-50">Record funding &amp; mark vehicle sold</WorkButton><WorkButton type="submit" disabled={busy} className="rounded-md border px-4 py-2 text-sm" onClick={()=>setReviewFunding(false)}>Back to summary</WorkButton></div>
          </>}
          {!deal.contract && <p role="alert">The contract summary is missing. Funding is unavailable until the record is resolved.</p>}
        </section>
      )}

      {deal.status === "funded" && (
        <div className="rounded-lg border border-green-900 bg-green-950/30 px-3 py-2 text-xs text-green-300">
          ✓ Funded {deal.funded_at ? `on ${new Date(deal.funded_at).toLocaleString()}` : ""} — Finance Contract {deal.finance_contract_id}
        </div>
      )}
    </div>
  );
}
