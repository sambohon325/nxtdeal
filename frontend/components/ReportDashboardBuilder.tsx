"use client";
import { WorkButton } from "./WorkspaceUi";

// The customizable Reporting + Overview dashboards (session 73; Overview added
// session 77). Sam: "lets go ahead and set all the reporting to be graph based, so it
// should have two columns when the data is best represented in a square format, and if
// it needs more room it can stretch out across both. Lets also have each report /
// graph have a toggle where you can switch to text mode... They should also be able to
// snap them into place to create their own dashboards, and hide the modules
// (deactivate) - they still need to be listed somewhere theres available modules
// list, they drag what they want into the live area... We want them to have a good
// snapshot of that department in a way that they can put on a full screen or print
// out. This is for each department." Then, session 77: "in all overview dashes in the
// submenus for all departments, I'd like that to be a very BI visual glance as a
// default... same as the reporting, you should be able to drag and drop them in a grid
// system."
//
// Fully generic off GET /report-modules or /overview-modules (picked by the `board`
// prop) + GET/POST /dashboard-layout?board=... (lib/reportDashboard.ts) -- no
// per-department code here, matching this codebase's established one-engine
// convention. Mounted once per department by components/MenuDashPanel.tsx's
// MenuDashBody, once for itemKey === "reporting" (board="reporting") and once for
// itemKey === "overview" (board="overview") -- the exact same grid/drag/print
// mechanics serve both, only which catalog feeds the tray differs.
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  fetchReportModules,
  fetchOverviewModules,
  fetchDashboardLayout,
  saveDashboardLayout,
  type ReportModuleCatalogEntry,
  type DashboardModuleInstance,
  type DashboardBoard,
} from "@/lib/reportDashboard";
import { ReportDashboardModule } from "@/components/ReportDashboardModule";
import {
  DEPARTMENT_TO_PREDICTION_KEY,
  fetchTimeline,
  type TimelineResponse,
} from "@/lib/predictionTimeline";

type Theme = "dark" | "light";

const PALETTE = ["#8bd5fb", "#548fbd", "#c3dbe9", "#839bb7"];
const REORDER_DRAG_TYPE = "application/x-dealeros-dash-reorder";
const CATALOG_DRAG_TYPE = "application/x-dealeros-dash-catalog";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function isChartable(entry: ReportModuleCatalogEntry): boolean {
  const values = Object.values(entry.data);
  if (values.some((v) => typeof v === "number")) return true;
  return values.some(
    (v) => Array.isArray(v) && v.length > 0 && v.every((item) => item && typeof item === "object" && !Array.isArray(item))
  );
}

function makeInstanceId(): string {
  return `local-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

export function ReportDashboardBuilder({
  department,
  theme: workspaceTheme,
  board = "reporting",
}: {
  department: string;
  theme?: Theme;
  // Session 77: which board this instance renders -- "reporting" (session 73's
  // original, unchanged) or "overview" (the new BI-glance board). Picks which catalog
  // fetch feeds the tray and which board key the layout is saved/loaded under; the
  // grid/drag/print mechanics below are identical either way.
  board?: DashboardBoard;
}) {
  const [catalog, setCatalog] = useState<ReportModuleCatalogEntry[] | null>(null);
  const [modules, setModules] = useState<DashboardModuleInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [localTheme, setTheme] = useState<Theme>("dark");
  const theme=workspaceTheme??localTheme;
  const [showTray, setShowTray] = useState(false);
  const [fullScreen, setFullScreen] = useState(false);
  const [dragOverGrid, setDragOverGrid] = useState(false);
  // Session 78, Sam: "predictive horizon needs to be available on all charts (to the
  // departments that it applies to), so all the modules in the overview need to have
  // the time horizon adjusters on them, and the top predictive horizon chart on all of
  // the overviews (that have it) needs to be deleted." Fetched once here (not per
  // module -- there's only one real department-level forecast to share) and handed to
  // every module card below; null for a department with no real prediction source, or
  // on the Reporting board where the standalone PredictionHorizonSlider still owns
  // this instead.
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);

  const dragInstanceId = useRef<string | null>(null);
  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const loaded = useRef(false);
  const [retry,setRetry]=useState(0);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    loaded.current = false;

    const fetchCatalog = board === "overview" ? fetchOverviewModules : fetchReportModules;

    Promise.all([fetchCatalog(department), fetchDashboardLayout(department, board)])
      .then(([cat, layout]) => {
        if (cancelled) return;
        setCatalog(cat);
        setModules(layout.modules);
      })
      .catch(() => {
        if (!cancelled) setError("Unable to reach NXTDeal backend.");
      })
      .finally(() => {
        if (!cancelled) {
          setLoading(false);
          loaded.current = true;
        }
      });

    return () => {
      cancelled = true;
    };
  }, [department, board, retry]);

  // Session 78: fetch the department's real prediction timeline once for the Overview
  // board only (Reporting keeps its own standalone PredictionHorizonSlider, mounted by
  // MenuDashPanel.tsx, unchanged) -- every module card below shares this single fetch
  // rather than each re-fetching independently.
  useEffect(() => {
    if (board !== "overview") {
      setTimeline(null);
      return;
    }

    const predictionKey = DEPARTMENT_TO_PREDICTION_KEY[department];
    if (!predictionKey) {
      setTimeline(null);
      return;
    }

    let cancelled = false;
    fetchTimeline(predictionKey).then((d) => {
      if (!cancelled) setTimeline(d);
    });

    return () => {
      cancelled = true;
    };
  }, [department, board]);

  // Debounced persistence -- every drag/reorder/setting change updates local state
  // immediately (so the grid feels instant) and schedules a save shortly after,
  // rather than round-tripping to the backend on every single mouse movement.
  useEffect(() => {
    if (!loaded.current) return;

    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      saveDashboardLayout(department, modules, board).catch(() => {
        // Best-effort -- the board still works locally even if a save fails; the next
        // successful change will retry the full current state anyway.
      });
    }, 700);

    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [modules, department, board]);

  const catalogByKey = useMemo(() => {
    const map = new Map<string, ReportModuleCatalogEntry>();
    (catalog ?? []).forEach((c) => map.set(c.module_key, c));
    return map;
  }, [catalog]);

  function nextColor(index: number): string {
    return PALETTE[index % PALETTE.length];
  }

  function addModule(moduleKey: string) {
    const entry = catalogByKey.get(moduleKey);
    if (!entry) return;

    const instance: DashboardModuleInstance = {
      id: makeInstanceId(),
      module_key: moduleKey,
      mode: isChartable(entry) ? "graph" : "text",
      chart_type: "bar",
      color: nextColor(modules.length),
      span: 1,
      order: modules.length,
      fields: [],
      show_in_overview: false,
    };

    setModules((prev) => [...prev, instance]);
  }

  function updateModule(id: string, patch: Partial<DashboardModuleInstance>) {
    setModules((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)));
  }

  function removeModule(id: string) {
    setModules((prev) => prev.filter((m) => m.id !== id).map((m, i) => ({ ...m, order: i })));
  }

  function reorder(draggedId: string, targetId: string) {
    setModules((prev) => {
      const fromIndex = prev.findIndex((m) => m.id === draggedId);
      const toIndex = prev.findIndex((m) => m.id === targetId);
      if (fromIndex === -1 || toIndex === -1 || fromIndex === toIndex) return prev;

      const next = [...prev];
      const [moved] = next.splice(fromIndex, 1);
      next.splice(toIndex, 0, moved);
      return next.map((m, i) => ({ ...m, order: i }));
    });
  }

  function handleGridDragOver(e: DragEvent<HTMLDivElement>) {
    if (!e.dataTransfer.types.includes(CATALOG_DRAG_TYPE)) return;
    e.preventDefault();
    e.dataTransfer.dropEffect = "copy";
    setDragOverGrid(true);
  }

  function handleGridDrop(e: DragEvent<HTMLDivElement>) {
    const moduleKey = e.dataTransfer.getData(CATALOG_DRAG_TYPE);
    setDragOverGrid(false);
    if (!moduleKey) return;
    e.preventDefault();
    addModule(moduleKey);
  }

  function handlePrint() {
    requestAnimationFrame(() => requestAnimationFrame(() => window.print()));
  }

  if (loading) {
    return <div className={tc(theme, "text-sm text-zinc-600", "text-sm text-zinc-500")}>Loading dashboard…</div>;
  }

  if (error) {
    return <div role="alert">{error} <WorkButton type="submit" onClick={()=>setRetry(v=>v+1)}>Retry dashboard</WorkButton></div>;
  }

  const boardUI = (
    <div data-appearance={theme} className={tc(theme, "nxt-board flex flex-col h-full bg-brand-ink", "nxt-board flex flex-col h-full bg-white")}>
      <div className={tc(theme, "nxt-board-toolbar flex items-center justify-between gap-3 px-3 py-2 border-b border-zinc-800 print:hidden", "nxt-board-toolbar flex items-center justify-between gap-3 px-3 py-2 border-b border-zinc-300 print:hidden")}>
        <div className="flex items-center gap-2">
          <WorkButton type="submit"
            aria-expanded={showTray}
            onClick={() => setShowTray((s) => !s)}
            className={
              showTray
                ? "text-xs px-2.5 py-1 rounded-md bg-brand-teal text-black font-brand font-semibold uppercase tracking-wide"
                : tc(theme, "text-xs px-2.5 py-1 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition font-brand uppercase tracking-wide", "text-xs px-2.5 py-1 rounded-md border border-zinc-300 text-zinc-600 hover:text-black transition font-brand uppercase tracking-wide")
            }
          >
            Customize dashboard
          </WorkButton>
          <span className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>
            {modules.length} active
          </span>
        </div>

        <div className="flex items-center gap-1.5">
{!workspaceTheme &&           <div className={tc(theme, "flex items-center gap-1 text-xs rounded-lg border border-zinc-800 p-0.5", "flex items-center gap-1 text-xs rounded-lg border border-zinc-300 p-0.5")}>
            <WorkButton type="submit"
              onClick={() => setTheme("dark")}
              className={theme === "dark" ? "px-2 py-0.5 rounded-md bg-zinc-700 text-white text-xs" : "px-2 py-0.5 rounded-md text-zinc-500 hover:text-white transition text-xs"}
            >
              ● Dark
            </WorkButton>
            <WorkButton type="submit"
              onClick={() => setTheme("light")}
              className={theme === "light" ? "px-2 py-0.5 rounded-md bg-zinc-200 text-black text-xs" : "px-2 py-0.5 rounded-md text-zinc-500 hover:text-white transition text-xs"}
            >
              ○ Light
            </WorkButton>
          </div>}
          <WorkButton type="submit"
            onClick={() => setFullScreen((f) => !f)}
            title={fullScreen ? "Exit full screen" : "Full screen -- a clean snapshot of this department"}
            className={tc(theme, "text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 transition", "text-xs px-3 py-1.5 rounded-lg border border-zinc-300 text-zinc-700 hover:text-black hover:border-zinc-500 transition")}
          >
            {fullScreen ? "⤡ Exit Full Screen" : "⤢ Full Screen"}
          </WorkButton>
          <WorkButton type="submit"
            onClick={handlePrint}
            disabled={modules.length === 0}
            className={tc(theme, "text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 transition disabled:opacity-40", "text-xs px-3 py-1.5 rounded-lg border border-zinc-300 text-zinc-700 hover:text-black hover:border-zinc-500 transition disabled:opacity-40")}
          >
            🖨 Print
          </WorkButton>
        </div>
      </div>

      <div className="nxt-board-layout flex-1 flex flex-col min-w-0">
        {showTray && (
          <div className={tc(theme, "nxt-module-tray w-full border-b border-zinc-800 p-4 grid grid-cols-2 gap-3 print:hidden", "nxt-module-tray w-full border-b border-zinc-300 p-4 grid grid-cols-2 gap-3 print:hidden")}>
            <div className={tc(theme, "col-span-2 text-xs text-zinc-600 px-1 mb-1", "col-span-2 text-xs text-zinc-500 px-1 mb-1")}>
              Choose reports to add to this dashboard
            </div>
            {(catalog ?? []).map((entry) => (
              <div
                key={entry.module_key}
                draggable
                onDragStart={(e) => {
                  e.dataTransfer.setData(CATALOG_DRAG_TYPE, entry.module_key);
                  e.dataTransfer.effectAllowed = "copy";
                }}
                className={tc(
                  theme,
                  "flex items-center justify-between gap-2 rounded-lg border border-black/20 bg-brand-charcoal px-2.5 py-2 cursor-grab active:cursor-grabbing hover:border-zinc-600 transition",
                  "flex items-center justify-between gap-2 rounded-lg border border-zinc-300 bg-zinc-50 px-2.5 py-2 cursor-grab active:cursor-grabbing hover:border-zinc-400 transition"
                )}
              >
                <span className={tc(theme, "text-xs text-zinc-300 truncate", "text-xs text-zinc-700 truncate")}>
                  {isChartable(entry) ? "📊 " : "☰ "}
                  {entry.label}
                  {entry._source === "reporting" && (
                    <span className={tc(theme, "ml-1 text-xs text-zinc-600", "ml-1 text-xs text-zinc-400")}>
                      (from Reporting)
                    </span>
                  )}
                </span>
                <WorkButton type="submit"
                  onClick={() => addModule(entry.module_key)}
                  title="Add to board" aria-label={`Add ${entry.label} to dashboard`}
                  className="text-xs w-5 h-5 shrink-0 rounded bg-brand-teal text-black font-bold leading-none"
                >
                  +
                </WorkButton>
              </div>
            ))}
            {(catalog ?? []).length === 0 && (
              <div className={tc(theme, "text-xs text-zinc-600 px-1", "text-xs text-zinc-500 px-1")}>
                No {board === "overview" ? "overview" : "reporting"} data available for this department yet.
              </div>
            )}
          </div>
        )}

        <div
          onDragOver={handleGridDragOver}
          onDragLeave={() => setDragOverGrid(false)}
          onDrop={handleGridDrop}
          className={
            dragOverGrid
              ? "nxt-report-grid flex-1 min-w-0 grid grid-cols-2 gap-3 auto-rows-min ring-2 ring-inset ring-brand-teal"
              : "nxt-report-grid flex-1 min-w-0 grid grid-cols-2 gap-3 auto-rows-min dealeros-report-print-region"
          }
        >
          {modules.length === 0 && (
            <div className={tc(theme, "col-span-2 text-sm text-zinc-600 text-center py-10 print:hidden", "col-span-2 text-sm text-zinc-500 text-center py-10 print:hidden")}>
              <h3>Choose the reports you want to see.</h3><p>Add a report to build your department snapshot. Your saved layout stays with this department.</p><WorkButton type="button" onClick={()=>setShowTray(true)}>Choose reports</WorkButton>
            </div>
          )}

          {modules.map((instance) => (
            <ReportDashboardModule
              key={instance.id}
              instance={instance}
              catalogEntry={catalogByKey.get(instance.module_key)}
              theme={theme}
              board={board}
              timeline={timeline}
              onUpdate={(patch) => updateModule(instance.id, patch)}
              onRemove={() => removeModule(instance.id)}
              dragProps={{
                draggable: true,
                onDragStart: (e) => {
                  dragInstanceId.current = instance.id;
                  e.dataTransfer.setData(REORDER_DRAG_TYPE, instance.id);
                  e.dataTransfer.effectAllowed = "move";
                },
                onDragOver: (e) => {
                  if (!e.dataTransfer.types.includes(REORDER_DRAG_TYPE)) return;
                  e.preventDefault();
                  e.dataTransfer.dropEffect = "move";
                },
                onDrop: (e) => {
                  const draggedId = e.dataTransfer.getData(REORDER_DRAG_TYPE) || dragInstanceId.current;
                  if (!draggedId) return;
                  e.preventDefault();
                  e.stopPropagation();
                  reorder(draggedId, instance.id);
                },
                onDragEnd: () => {
                  dragInstanceId.current = null;
                },
              }}
            />
          ))}
        </div>
      </div>

      <style>{`
        @media print {
          body * { visibility: hidden; }
          .dealeros-report-print-region, .dealeros-report-print-region * { visibility: visible; }
          .dealeros-report-print-region {
            position: absolute; left: 0; top: 0; width: 100%;
            display: grid; grid-template-columns: 1fr 1fr; gap: 12px; padding: 24px;
          }
        }
      `}</style>
    </div>
  );

  if (fullScreen) {
    return (
      <div data-fullscreen="true" className="fixed inset-0 z-50">
        {boardUI}
      </div>
    );
  }

  return <div className="h-full min-h-[420px]">{boardUI}</div>;
}
