"use client";
import { WorkField } from "./WorkField";

// The OneNote-style Workspace board renderer (session 76, reworked session 76 follow-
// up). Sam: "the idea is something like microsoft OneNote in that its a very dynamic
// workspace to add information in, and should be able to pull from dashes, reporting
// and from input on the chat" -- then, after the first cut rendered items as a plain
// stacked list: "I want to be able to add notes inside of workspace, not separately,
// and to be able to drag those around the canvas similar to OneNote."
//
// Free-form absolutely-positioned canvas now, not a flex stack -- every card carries
// its own x/y (lib/useWorkspaceBoard.ts, persisted server-side) and is draggable by its
// header, same window-level mousemove/mouseup drag-tracking pattern
// lib/useResizablePanel.ts already established for the Workspace panel's resize handle.
//
// Chrome-free, same split as AccountSettingsBody/WorkflowWindowBody -- reused both
// in-page (embedded in the Workspace column) and in the pop-out route
// (app/panel/workspaceboard/page.tsx), driven entirely by a WorkspaceBoard hook
// instance (lib/useWorkspaceBoard.ts) passed in from the page.
//
// Session 76 third follow-up (Sam: "move the pin to knowledge out of the reports and
// notes windows and put it into the workspace as a whole") -- there is deliberately no
// per-card Save-to-Knowledge button anymore. Pinning now happens once, for the whole
// board, from the single Workspace header in app/workspace/page.tsx (see
// PinWorkspaceButton) -- not per chart/note here.

import { useRef, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import type { WorkspaceBoard, WorkspaceChartItem, WorkspaceNoteItem, WorkspaceSnapshotItem, WorkspaceBoardItem } from "@/lib/useWorkspaceBoard";
import { WorkspaceTimeSlider } from "@/components/WorkspaceTimeSlider";

const SERIES_COLORS = ["#3FBCC4", "#2B68AB", "#FBCF09", "#EE3C25", "#8B5CF6", "#22C55E"];
const CARD_WIDTH = 320;

export function prettify(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Exported so components/SharedWorkspaceBoardView.tsx (a read-only render of someone
// ELSE's shared Workspace board) can reuse the exact same chart rendering instead of
// duplicating recharts wiring for a second, slightly-different chart shape.
export function MiniChart({ item }: { item: WorkspaceChartItem }) {
  if (item.rowsLoading) {
    return <div className="h-32 flex items-center justify-center text-xs text-zinc-600">Loading…</div>;
  }

  if (item.rows.length === 0 || item.selectedColumns.length === 0) {
    return <div className="h-32 flex items-center justify-center text-xs text-zinc-600">No data to chart.</div>;
  }

  const chartData = item.rows.slice(0, 15).map((r) => {
    const out: Record<string, unknown> = { _label: String(r[item.labelColumn] ?? "") };
    item.selectedColumns.forEach((c) => {
      out[c] = typeof r[c] === "number" ? r[c] : Number(r[c]) || 0;
    });
    return out;
  });

  const pieColumn = item.selectedColumns[0];
  const pieData = pieColumn ? chartData.map((d) => ({ name: String(d._label), value: Number(d[pieColumn]) || 0 })) : [];

  return (
    <div style={{ height: 160 }}>
      <ResponsiveContainer>
        {item.chartType === "pie" ? (
          <PieChart>
            <Tooltip contentStyle={{ fontSize: 11, background: "#18181b", border: "1px solid #3f3f46" }} />
            <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={60}>
              {pieData.map((_, i) => (
                <Cell key={i} fill={SERIES_COLORS[i % SERIES_COLORS.length]} />
              ))}
            </Pie>
          </PieChart>
        ) : item.chartType === "line" ? (
          <LineChart data={chartData}>
            <XAxis dataKey="_label" tick={{ fontSize: 9, fill: "#a1a1aa" }} interval={0} angle={-30} textAnchor="end" height={30} />
            <YAxis tick={{ fontSize: 9, fill: "#a1a1aa" }} />
            <Tooltip contentStyle={{ fontSize: 11, background: "#18181b", border: "1px solid #3f3f46" }} />
            {item.selectedColumns.map((c, i) => (
              <Line key={c} type="monotone" dataKey={c} stroke={SERIES_COLORS[i % SERIES_COLORS.length]} strokeWidth={2} dot={{ r: 2 }} />
            ))}
          </LineChart>
        ) : (
          <BarChart data={chartData}>
            <XAxis dataKey="_label" tick={{ fontSize: 9, fill: "#a1a1aa" }} interval={0} angle={-30} textAnchor="end" height={30} />
            <YAxis tick={{ fontSize: 9, fill: "#a1a1aa" }} />
            <Tooltip contentStyle={{ fontSize: 11, background: "#18181b", border: "1px solid #3f3f46" }} />
            {item.selectedColumns.map((c, i) => (
              <Bar key={c} dataKey={c} fill={SERIES_COLORS[i % SERIES_COLORS.length]} radius={[2, 2, 0, 0]} />
            ))}
          </BarChart>
        )}
      </ResponsiveContainer>
    </div>
  );
}

// Each card (chart or note) below is an absolutely positioned box within the canvas
// <div>'s relative coordinate space, dragged via its own "⠿" grip in the header --
// dragging is only armed from that grip, never from the card body, so clicking a
// button, editing a textarea, or reading a chart never accidentally starts a drag
// (every interactive element inside the header also stops propagation on mousedown).
function ChartCard({
  item,
  board,
  onDragTo,
  highlighted,
}: {
  item: WorkspaceChartItem;
  board: WorkspaceBoard;
  onDragTo: (x: number, y: number) => void;
  highlighted?: boolean;
}) {
  const [explaining, setExplaining] = useState(false);
  const dragState = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  async function handleExplain() {
    setExplaining(true);
    await board.explainChart(item);
    setExplaining(false);
  }

  function onGripMouseDown(e: React.MouseEvent) {
    e.preventDefault();
    dragState.current = { startX: e.clientX, startY: e.clientY, originX: item.x, originY: item.y };
    setDragging(true);

    const onMove = (moveEvent: MouseEvent) => {
      if (!dragState.current) return;
      const dx = moveEvent.clientX - dragState.current.startX;
      const dy = moveEvent.clientY - dragState.current.startY;
      onDragTo(Math.max(0, dragState.current.originX + dx), Math.max(0, dragState.current.originY + dy));
    };

    const onUp = () => {
      dragState.current = null;
      setDragging(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  return (
    <div
      style={{ position: "absolute", left: item.x, top: item.y, width: CARD_WIDTH, zIndex: dragging ? 20 : 1 }}
      className={
        dragging
          ? "select-none rounded-lg border border-[#3FBCC4] bg-brand-charcoal overflow-hidden shadow-xl"
          : highlighted
          ? "rounded-lg border-2 border-[#FBCF09] bg-brand-charcoal overflow-hidden shadow-xl transition-colors"
          : "rounded-lg border border-zinc-800 bg-brand-charcoal overflow-hidden shadow-lg transition-colors"
      }
    >
      <div
        onMouseDown={onGripMouseDown}
        title="Drag to move"
        className="flex items-center justify-between px-3 py-2 border-b border-zinc-900 cursor-grab active:cursor-grabbing"
      >
        <div className="min-w-0 flex items-center gap-1.5">
          <span className="text-zinc-700 text-xs shrink-0">⠿</span>
          <div className="min-w-0">
            <div className="text-xs font-medium truncate">{item.sourceLabel || prettify(item.itemKey)}</div>
            <div className="text-[10px] text-zinc-600 truncate">{item.department}</div>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={handleExplain}
            disabled={explaining}
            title="Generate an AI explanation of this chart"
            className="text-[11px] text-zinc-500 hover:text-[#3FBCC4] transition disabled:opacity-40"
          >
            {explaining ? "…" : "✨"}
          </button>
          <button
            onMouseDown={(e) => e.stopPropagation()}
            onClick={() => board.removeItem(item.id)}
            className="text-zinc-600 hover:text-white transition text-xs"
          >
            ×
          </button>
        </div>
      </div>
      <div className="p-2">
        <MiniChart item={item} />
      </div>

      {/* The chart's own attached note (session 76 second follow-up -- Sam: "create a
          chart, and then create a note under it explaining what it is, and save that
          as one single piece of knowledge") -- always visible, not conditional, so
          there's always somewhere to write the explanation without a separate note
          card. ✨ Explain fills this in via AI; typing here works exactly like a
          NoteCard's textarea. */}
      <div className="border-t border-zinc-900 px-3 py-2">
        {item.noteAiGenerated && item.noteText && (
          <div className="text-[10px] text-zinc-600 mb-1 flex items-center gap-1">
            <span>✨</span>
            <span>AI-generated</span>
          </div>
        )}
        <WorkField label="Add a note explaining this chart"><textarea
          value={item.noteText}
          onChange={(e) => board.updateChartNote(item.id, e.target.value)}
          onMouseDown={(e) => e.stopPropagation()}
          placeholder="Add a note explaining this chart…"
          rows={3}
          className="w-full text-xs bg-transparent resize-y focus:outline-none placeholder:text-zinc-700"
        /></WorkField>
      </div>
    </div>
  );
}

function NoteCard({
  item,
  board,
  onDragTo,
  highlighted,
}: {
  item: WorkspaceNoteItem;
  board: WorkspaceBoard;
  onDragTo: (x: number, y: number) => void;
  highlighted?: boolean;
}) {
  const dragState = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  function onGripMouseDown(e: React.MouseEvent) {
    e.preventDefault();
    dragState.current = { startX: e.clientX, startY: e.clientY, originX: item.x, originY: item.y };
    setDragging(true);

    const onMove = (moveEvent: MouseEvent) => {
      if (!dragState.current) return;
      const dx = moveEvent.clientX - dragState.current.startX;
      const dy = moveEvent.clientY - dragState.current.startY;
      onDragTo(Math.max(0, dragState.current.originX + dx), Math.max(0, dragState.current.originY + dy));
    };

    const onUp = () => {
      dragState.current = null;
      setDragging(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  return (
    <div
      style={{ position: "absolute", left: item.x, top: item.y, width: CARD_WIDTH, zIndex: dragging ? 20 : 1 }}
      className={
        dragging
          ? "select-none rounded-lg border border-[#3FBCC4] bg-brand-charcoal overflow-hidden shadow-xl"
          : highlighted
          ? "rounded-lg border-2 border-[#FBCF09] bg-brand-charcoal overflow-hidden shadow-xl transition-colors"
          : "rounded-lg border border-zinc-800 bg-brand-charcoal overflow-hidden shadow-lg transition-colors"
      }
    >
      <div
        onMouseDown={onGripMouseDown}
        title="Drag to move"
        className="flex items-center justify-between px-3 py-2 border-b border-zinc-900 cursor-grab active:cursor-grabbing"
      >
        <div className="min-w-0 flex items-center gap-1.5">
          <span className="text-zinc-700 text-xs shrink-0">⠿</span>
          {item.aiGenerated && <span title="AI-generated">✨</span>}
          <span className="text-xs font-medium truncate">{item.title || "Note"}</span>
          {item.sourceContext && (
            <span className="text-[10px] text-zinc-600 truncate">— {item.sourceContext}</span>
          )}
        </div>
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <button onMouseDown={(e) => e.stopPropagation()} onClick={() => board.removeItem(item.id)} className="text-zinc-600 hover:text-white transition text-xs">
            ×
          </button>
        </div>
      </div>
      <WorkField label="Type a note"><textarea
        value={item.text}
        onChange={(e) => board.updateNoteText(item.id, e.target.value)}
        onMouseDown={(e) => e.stopPropagation()}
        placeholder="Type a note…"
        rows={4}
        className="w-full p-3 text-xs bg-transparent resize-y focus:outline-none placeholder:text-zinc-700"
      /></WorkField>
    </div>
  );
}

// A grabbed data frame (Workspace grab-all, 2026-07-23) -- a frozen table/text snapshot
// captured from anywhere in the app. Read-only + honestly labelled "captured <when>";
// same drag/remove chrome as the other cards.
function SnapshotCard({
  item,
  board,
  onDragTo,
  highlighted,
}: {
  item: WorkspaceSnapshotItem;
  board: WorkspaceBoard;
  onDragTo: (x: number, y: number) => void;
  highlighted?: boolean;
}) {
  const dragState = useRef<{ startX: number; startY: number; originX: number; originY: number } | null>(null);
  const [dragging, setDragging] = useState(false);

  function onGripMouseDown(e: React.MouseEvent) {
    e.preventDefault();
    dragState.current = { startX: e.clientX, startY: e.clientY, originX: item.x, originY: item.y };
    setDragging(true);
    const onMove = (moveEvent: MouseEvent) => {
      if (!dragState.current) return;
      const dx = moveEvent.clientX - dragState.current.startX;
      const dy = moveEvent.clientY - dragState.current.startY;
      onDragTo(Math.max(0, dragState.current.originX + dx), Math.max(0, dragState.current.originY + dy));
    };
    const onUp = () => {
      dragState.current = null;
      setDragging(false);
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };
    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }

  const cols = item.columns.length ? item.columns : Object.keys(item.rows[0] ?? {});
  const fmtCell = (v: unknown) =>
    v === null || v === undefined ? "—" : typeof v === "number" ? v.toLocaleString() : String(v);
  const captured = (() => {
    try {
      return item.capturedAt ? new Date(item.capturedAt).toLocaleDateString([], { month: "short", day: "numeric", year: "numeric" }) : "";
    } catch {
      return item.capturedAt;
    }
  })();

  return (
    <div
      style={{ position: "absolute", left: item.x, top: item.y, width: CARD_WIDTH, zIndex: dragging ? 20 : 1 }}
      className={
        dragging
          ? "select-none rounded-lg border border-[#3FBCC4] bg-brand-charcoal overflow-hidden shadow-xl"
          : highlighted
          ? "rounded-lg border-2 border-[#FBCF09] bg-brand-charcoal overflow-hidden shadow-xl transition-colors"
          : "rounded-lg border border-zinc-800 bg-brand-charcoal overflow-hidden shadow-lg transition-colors"
      }
    >
      <div
        onMouseDown={onGripMouseDown}
        title="Drag to move"
        className="flex items-center justify-between px-3 py-2 border-b border-zinc-900 cursor-grab active:cursor-grabbing"
      >
        <div className="min-w-0 flex items-center gap-1.5">
          <span className="text-zinc-700 text-xs shrink-0">⠿</span>
          <div className="min-w-0">
            <div className="text-xs font-medium truncate">{item.title || "Captured data"}</div>
            {item.sourceLabel && <div className="text-[10px] text-zinc-600 truncate">{item.sourceLabel}</div>}
          </div>
        </div>
        <button onMouseDown={(e) => e.stopPropagation()} onClick={() => board.removeItem(item.id)} className="text-zinc-600 hover:text-white transition text-xs shrink-0 ml-2">
          ×
        </button>
      </div>

      <div className="p-2">
        {item.dataKind === "text" ? (
          <div className="text-xs whitespace-pre-wrap text-zinc-300 max-h-48 overflow-y-auto">{item.text}</div>
        ) : item.rows.length === 0 ? (
          <div className="text-xs text-zinc-600">No rows captured.</div>
        ) : (
          <div className="max-h-48 overflow-auto">
            <table className="w-full text-[11px]">
              <thead>
                <tr>
                  {cols.map((c) => (
                    <th key={c} className="text-left px-1.5 py-1 text-zinc-500 font-medium sticky top-0 bg-brand-charcoal">{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {item.rows.slice(0, 50).map((r, i) => (
                  <tr key={i} className="border-t border-zinc-900">
                    {cols.map((c) => (
                      <td key={c} className="px-1.5 py-1 text-zinc-300 whitespace-nowrap">{fmtCell(r[c])}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
            {item.rows.length > 50 && <div className="text-[10px] text-zinc-600 px-1.5 py-1">+{item.rows.length - 50} more rows</div>}
          </div>
        )}
      </div>

      {captured && (
        <div className="border-t border-zinc-900 px-3 py-1.5 text-[10px] text-zinc-600">📸 captured {captured}</div>
      )}
    </div>
  );
}

export function WorkspaceBoardBody({
  board,
  highlightedItemId,
}: {
  board: WorkspaceBoard;
  highlightedItemId?: string | null;
}) {
  // Canvas grows to fit its lowest/rightmost card rather than clipping -- the parent
  // <aside> is already the scroll container (overflow-y-auto), this <div> just needs to
  // be tall enough that absolutely-positioned children near the bottom aren't cut off.
  const maxBottom = board.items.reduce((max, i) => Math.max(max, i.y + (i.kind === "chart" ? 320 : i.kind === "snapshot" ? 280 : 160)), 0);
  const canvasHeight = Math.max(320, maxBottom + 40);

  // Pillar 2 (predictive layer): the Workspace time-slider forecasts exactly the
  // departments the user has pulled onto this board — derived from the chart cards'
  // own `department` field, not a fixed list. WorkspaceTimeSlider drops any
  // non-forecastable department and renders nothing when none remain.
  const chartDepartments = board.items
    .filter((i): i is WorkspaceChartItem => i.kind === "chart")
    .map((i) => i.department);

  return (
    <div className="flex flex-col gap-3">
      {chartDepartments.length > 0 && <WorkspaceTimeSlider departments={chartDepartments} />}

      <button
        onClick={() => board.addNote("")}
        className="text-xs px-3 py-2 rounded-lg border border-dashed border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500 transition self-start"
      >
        + Add Note
      </button>

      {board.loading ? (
        <div className="text-xs text-zinc-600 px-1">Loading your Workspace…</div>
      ) : board.items.length === 0 ? (
        <div className="text-xs text-zinc-600 px-1">
          Nothing here yet — drag a chart from a Reporting dashboard, add a note above,
          or ask in chat: <span className="text-zinc-400">&quot;add to workspace: ...&quot;</span> or{" "}
          <span className="text-zinc-400">&quot;build me a report on ...&quot;</span>
        </div>
      ) : (
        <div className="relative" style={{ height: canvasHeight }}>
          {board.items.map((item: WorkspaceBoardItem) =>
            item.kind === "chart" ? (
              <ChartCard
                key={item.id}
                item={item}
                board={board}
                onDragTo={(x, y) => board.updatePosition(item.id, x, y)}
                highlighted={highlightedItemId === item.id}
              />
            ) : item.kind === "snapshot" ? (
              <SnapshotCard
                key={item.id}
                item={item}
                board={board}
                onDragTo={(x, y) => board.updatePosition(item.id, x, y)}
                highlighted={highlightedItemId === item.id}
              />
            ) : (
              <NoteCard
                key={item.id}
                item={item}
                board={board}
                onDragTo={(x, y) => board.updatePosition(item.id, x, y)}
                highlighted={highlightedItemId === item.id}
              />
            )
          )}
        </div>
      )}

      {/* Print-only region -- hidden on screen (`hidden print:block`), shown instead of
          everything else on the page while printing, same "print this element only"
          technique components/MenuDashPanel.tsx established (own class name so the two
          never collide -- they're never both mounted at once on this page, but keeping
          them independent avoids any cross-page @media print surprises). Renders items
          top-to-bottom in document flow (order, not x/y -- canvas position is a screen-
          editing convenience, not part of the printed report) with a plain data table
          per chart instead of the interactive recharts SVG, which doesn't print well. */}
      <div className="hidden print:block dealeros-workspace-print-region">
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4, color: "#000" }}>
          NXTDeal — Workspace
        </div>
        <div style={{ fontSize: 11, color: "#555", marginBottom: 16 }}>
          Printed {new Date().toLocaleString()}
        </div>

        {[...board.items]
          .sort((a, b) => a.order - b.order)
          .map((item) =>
            item.kind === "chart" ? (
              <div key={item.id} style={{ marginBottom: 24, color: "#000" }} className="print-page-break">
                <div style={{ fontSize: 13, fontWeight: 600 }}>{item.sourceLabel || prettify(item.itemKey)}</div>
                <div style={{ fontSize: 10, color: "#555", marginBottom: 8 }}>{item.department}</div>
                {item.rows.length === 0 ? (
                  <div style={{ fontSize: 11, color: "#555" }}>No data.</div>
                ) : (
                  <table style={{ borderCollapse: "collapse", fontSize: 11, width: "100%" }}>
                    <thead>
                      <tr>
                        <th style={{ textAlign: "left", borderBottom: "1px solid #999", padding: "3px 6px" }}>
                          {prettify(item.labelColumn)}
                        </th>
                        {item.selectedColumns.map((c) => (
                          <th key={c} style={{ textAlign: "right", borderBottom: "1px solid #999", padding: "3px 6px" }}>
                            {prettify(c)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {item.rows.slice(0, 40).map((row, i) => (
                        <tr key={i}>
                          <td style={{ borderBottom: "1px solid #ddd", padding: "3px 6px" }}>
                            {String(row[item.labelColumn] ?? "")}
                          </td>
                          {item.selectedColumns.map((c) => (
                            <td key={c} style={{ textAlign: "right", borderBottom: "1px solid #ddd", padding: "3px 6px" }}>
                              {String(row[c] ?? "")}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {item.noteText && (
                  <div style={{ fontSize: 12, whiteSpace: "pre-wrap", marginTop: 8 }}>{item.noteText}</div>
                )}
              </div>
            ) : (
              <div key={item.id} style={{ marginBottom: 24, color: "#000" }} className="print-page-break">
                <div style={{ fontSize: 13, fontWeight: 600 }}>{item.title || "Note"}</div>
                {item.sourceContext && <div style={{ fontSize: 10, color: "#555", marginBottom: 8 }}>{item.sourceContext}</div>}
                <div style={{ fontSize: 12, whiteSpace: "pre-wrap" }}>{item.text}</div>
              </div>
            )
          )}
      </div>

      <style>{`
        @media print {
          body * { visibility: hidden; }
          .dealeros-workspace-print-region, .dealeros-workspace-print-region * { visibility: visible; }
          .dealeros-workspace-print-region { position: absolute; left: 0; top: 0; width: 100%; padding: 32px; background: #fff; }
          .print-page-break { break-inside: avoid; }
        }
      `}</style>
    </div>
  );
}
