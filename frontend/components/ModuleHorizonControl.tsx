"use client";

// Compact per-module predictive-horizon control (session 78). Sam, right after the
// initial Overview BI-glance build: "predictive horizon needs to be available on all
// charts (to the departments that it applies to), so all the modules in the overview
// need to have the time horizon adjusters on them, and the top predictive horizon
// chart on all of the overviews (that have it) needs to be deleted."
//
// core/prediction.py only forecasts ONE real, canonical metric per department (e.g.
// "units_sold" for Sales, see INDUSTRY_BASELINES/_DEPARTMENT_SOURCES) -- there is no
// per-arbitrary-KPI forecasting engine, so this control deliberately does NOT pretend
// to re-derive a horizon-adjusted number for whatever specific KPI a given card
// happens to show (e.g. "Units In Recon"). Instead every module card on a predictable
// department's Overview board shares the same real, honestly-labeled department-level
// forecast -- fetched once by components/ReportDashboardBuilder.tsx and handed down
// here as `timeline` -- so moving a card's own slider surfaces genuine ledger-backed
// data with its real confidence/basis/reference-note, not a fabricated per-KPI
// projection. Renders nothing when `timeline` is null/unavailable, i.e. for any
// department with no real prediction source (lib/predictionTimeline.ts's
// DEPARTMENT_TO_PREDICTION_KEY) -- exactly "the departments that it applies to."
import { useWorkspaceTools } from "@/lib/workspaceTools";
import { useState } from "react";
import { confidenceColor, type TimelineResponse } from "@/lib/predictionTimeline";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

export function ModuleHorizonControl({
  timeline,
  theme,
}: {
  timeline: TimelineResponse | null | undefined;
  theme: Theme;
}) {
  const [index, setIndex] = useState(1); // default to "Current"

  const legacyControls = useWorkspaceTools();
  const points = timeline?.points ?? [];
  if (!legacyControls || points.length === 0) return null;

  const selected = points[index] ?? points[points.length - 1];

  return (
    <div
      className={tc(
        theme,
        "mb-2 rounded-md border border-zinc-800 bg-zinc-900/60 p-1.5",
        "mb-2 rounded-md border border-zinc-200 bg-zinc-50 p-1.5"
      )}
    >
      <div className="flex items-center justify-between gap-1.5 mb-1">
        <div className="flex items-center gap-0.5 flex-wrap">
          {points.map((p, i) => (
            <button
              key={p.period}
              onClick={() => setIndex(i)}
              title={p.label}
              className={
                i === index
                  ? "text-[9px] font-bold px-1.5 py-0.5 rounded bg-brand-blue text-white leading-none"
                  : tc(
                      theme,
                      "text-[9px] px-1.5 py-0.5 rounded text-zinc-500 hover:text-white transition leading-none",
                      "text-[9px] px-1.5 py-0.5 rounded text-zinc-500 hover:text-black transition leading-none"
                    )
              }
            >
              {p.label}
            </button>
          ))}
        </div>
        {selected && (
          <span
            className="text-[9px] font-bold px-1.5 py-0.5 rounded shrink-0 leading-none"
            style={{ color: "#111", backgroundColor: confidenceColor(selected.confidence_pct) }}
          >
            {selected.confidence_pct.toFixed(0)}%
          </span>
        )}
      </div>

      {selected && (
        <div className={tc(theme, "text-[10px] text-zinc-300", "text-[10px] text-zinc-700")}>
          <span className="font-semibold">{selected.value.toLocaleString()} {selected.unit}</span>
          <span className={tc(theme, "text-zinc-500", "text-zinc-500")}> ({selected.metric.replace(/_/g, " ")})</span>
          <div className={tc(theme, "text-zinc-500 mt-0.5", "text-zinc-500 mt-0.5")}>
            {selected.kind === "predicted" ? `Reference: ${selected.note}` : selected.note}
          </div>
        </div>
      )}
    </div>
  );
}
