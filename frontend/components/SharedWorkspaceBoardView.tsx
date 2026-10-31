"use client";

// Read-only render of someone ELSE's Workspace board (session 76 third follow-up) --
// opened from a "workspace_board" Knowledge pin whose owner isn't the current session.
// Deliberately NOT the same interactive canvas WorkspaceBoardBody.tsx renders for your
// OWN board: no drag, no remove, no note editing, no per-item anything -- a viewer with
// a shared pin can look, not touch. Charts still re-fetch live data (same "pin is a
// bookmark, not a frozen snapshot" rule every other pin kind follows) via
// GET /menu/data + resolveFieldPath, same mechanism lib/useWorkspaceBoard.ts's
// hydrateChartRows uses for the owner's own board.

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { resolveFieldPath } from "@/lib/useVisualizationWorkspace";
import type { ChartType } from "@/lib/useVisualizationWorkspace";
import type { WorkspaceChartItem } from "@/lib/useWorkspaceBoard";
import { MiniChart, prettify } from "@/components/WorkspaceBoardBody";
import type { SharedWorkspaceBoardItem } from "@/lib/sharedKnowledge";

type ResolvedChart = WorkspaceChartItem;

function toChartShape(raw: SharedWorkspaceBoardItem): ResolvedChart {
  return {
    id: String(raw.id),
    kind: "chart",
    span: 1,
    order: typeof raw.order === "number" ? raw.order : 0,
    createdAt: String(raw.created_at ?? ""),
    x: 0,
    y: 0,
    department: String(raw.department ?? ""),
    itemKey: String(raw.item_key ?? ""),
    fieldPath: Array.isArray(raw.field_path) ? (raw.field_path as string[]).map(String) : [],
    sourceLabel: String(raw.source_label ?? ""),
    labelColumn: String(raw.label_column ?? ""),
    chartType: (["bar", "line", "pie"].includes(String(raw.chart_type)) ? raw.chart_type : "bar") as ChartType,
    selectedColumns: Array.isArray(raw.selected_columns) ? (raw.selected_columns as string[]).map(String) : [],
    noteText: String(raw.note_text ?? ""),
    noteAiGenerated: !!raw.note_ai_generated,
    rows: [],
    rowsLoading: true,
  };
}

export function SharedWorkspaceBoardView({
  ownerLabel,
  items,
  onClose,
}: {
  ownerLabel: string;
  items: SharedWorkspaceBoardItem[];
  onClose: () => void;
}) {
  const [charts, setCharts] = useState<ResolvedChart[]>(() =>
    items.filter((i) => i.kind === "chart").map(toChartShape)
  );

  useEffect(() => {
    charts.forEach((chart) => {
      const params = new URLSearchParams({ department: chart.department, item_key: chart.itemKey });

      fetch(`${API_BASE}/menu/data?${params.toString()}`, { headers: { ...authHeaders() } })
        .then((r) => r.json())
        .then((data) => {
          const rows = resolveFieldPath(data, chart.fieldPath) ?? [];
          setCharts((prev) => prev.map((c) => (c.id === chart.id ? { ...c, rows, rowsLoading: false } : c)));
        })
        .catch(() => {
          setCharts((prev) => prev.map((c) => (c.id === chart.id ? { ...c, rows: [], rowsLoading: false } : c)));
        });
    });
    // Only ever run once per mount -- this is a static viewer of a fetched snapshot of
    // item configs, not a live-editing board that re-renders on its own state changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ordered = [...items].sort((a, b) => {
    const oa = typeof a.order === "number" ? a.order : 0;
    const ob = typeof b.order === "number" ? b.order : 0;
    return oa - ob;
  });

  return (
    <div className="bg-brand-charcoal border border-black/20 rounded-xl p-6">
      <div className="flex items-center justify-between mb-4">
        <div>
          <div className="text-sm font-brand font-medium">{ownerLabel}&apos;s Workspace</div>
          <div className="text-[11px] text-zinc-600">Shared with you — view only</div>
        </div>
        <button onClick={onClose} className="text-zinc-600 hover:text-white transition text-xs">
          × Close
        </button>
      </div>

      {ordered.length === 0 ? (
        <div className="text-xs text-zinc-600">This Workspace is empty.</div>
      ) : (
        <div className="flex flex-col gap-4">
          {ordered.map((raw) => {
            if (raw.kind === "chart") {
              const chart = charts.find((c) => c.id === String(raw.id));
              if (!chart) return null;

              return (
                <div key={chart.id} className="rounded-lg border border-black/20 bg-brand-charcoal overflow-hidden">
                  <div className="px-3 py-2 border-b border-zinc-900">
                    <div className="text-xs font-medium truncate">{chart.sourceLabel || prettify(chart.itemKey)}</div>
                    <div className="text-[10px] text-zinc-600 truncate">{chart.department}</div>
                  </div>
                  <div className="p-2">
                    <MiniChart item={chart} />
                  </div>
                  {chart.noteText && (
                    <div className="border-t border-zinc-900 px-3 py-2 text-xs text-zinc-300 whitespace-pre-wrap">
                      {chart.noteText}
                    </div>
                  )}
                </div>
              );
            }

            return (
              <div key={String(raw.id)} className="rounded-lg border border-black/20 bg-brand-charcoal overflow-hidden p-3">
                <div className="text-xs font-medium mb-1">{String(raw.title ?? "") || "Note"}</div>
                <div className="text-xs text-zinc-300 whitespace-pre-wrap">{String(raw.text ?? "")}</div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
