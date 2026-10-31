"use client";

// Workspace time-slider (Pillar 2 — predictive layer, 2026-07-23). Sam's ask: the
// Workspace should have "a time slider that auto-maps to workspace data" — slide the
// whole board back and forth across the same predictive horizons the reporting slider
// uses (last week / current / tomorrow / next week / next month / next quarter).
//
// "Auto-maps to workspace data" is taken literally: the departments this slider forecasts
// are DERIVED from the workspace's own chart cards (each WorkspaceChartItem carries a
// `department`), not a fixed list — so the slider only ever shows predictions relevant to
// what the user actually pulled onto their board. Only Sales/Service/Finance/Marketing
// have a real prediction source (DEPARTMENT_TO_PREDICTION_KEY / core/prediction.py); a
// workspace with none of those among its charts renders no slider at all (honest — there
// is nothing to map through time).
//
// Reuses the exact same GET /readiness/timeline/{department} data + confidence colouring
// as components/PredictionHorizonSlider.tsx, so a value shown here is identical to the one
// on that department's reporting board — one prediction engine, surfaced in two places.

import { useEffect, useMemo, useState } from "react";
import {
  DEPARTMENT_TO_PREDICTION_KEY,
  confidenceColor,
  fetchTimeline,
  type TimelinePoint,
  type TimelineResponse,
} from "@/lib/predictionTimeline";

// The forecastable display-department names, in a stable order, that appear among the
// workspace's chart cards. Deduped; non-forecastable departments dropped.
function forecastableDepartments(departments: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const d of departments) {
    if (DEPARTMENT_TO_PREDICTION_KEY[d] && !seen.has(d)) {
      seen.add(d);
      out.push(d);
    }
  }
  return out;
}

export function WorkspaceTimeSlider({ departments }: { departments: string[] }) {
  const depts = useMemo(() => forecastableDepartments(departments), [departments]);

  // department display name -> its full 6-point timeline.
  const [timelines, setTimelines] = useState<Record<string, TimelineResponse>>({});
  const [loading, setLoading] = useState(false);
  const [index, setIndex] = useState(1); // default to "Current"

  useEffect(() => {
    if (depts.length === 0) return;

    let cancelled = false;
    setLoading(true);

    Promise.all(
      depts.map((d) =>
        fetchTimeline(DEPARTMENT_TO_PREDICTION_KEY[d]).then(
          (res) => [d, res] as const
        )
      )
    )
      .then((pairs) => {
        if (cancelled) return;
        const map: Record<string, TimelineResponse> = {};
        for (const [d, res] of pairs) map[d] = res;
        setTimelines(map);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [depts]);

  // The shared list of period positions, taken from whichever department came back with
  // points first (all forecastable departments share the identical 6-period series).
  const periods = useMemo(() => {
    for (const d of depts) {
      const pts = timelines[d]?.points;
      if (pts && pts.length) return pts.map((p) => ({ period: p.period, label: p.label }));
    }
    return [];
  }, [depts, timelines]);

  if (depts.length === 0) return null;

  const clampedIndex = Math.min(index, Math.max(periods.length - 1, 0));
  const selectedPeriod = periods[clampedIndex];

  function pointFor(dept: string): TimelinePoint | undefined {
    const pts = timelines[dept]?.points;
    if (!pts || !selectedPeriod) return undefined;
    return pts.find((p) => p.period === selectedPeriod.period);
  }

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3">
      <div className="flex items-center justify-between mb-2">
        <span className="font-brand text-[11px] font-bold uppercase tracking-wide text-zinc-400">
          Workspace Time Machine
        </span>
        {selectedPeriod && (
          <span className="text-[10px] text-zinc-500">
            {selectedPeriod.label} · {depts.length} department{depts.length === 1 ? "" : "s"}
          </span>
        )}
      </div>

      {loading && <div className="text-xs text-zinc-500 mb-2">Loading predictive data…</div>}

      {!loading && periods.length > 0 && (
        <>
          <input aria-label="Time horizon"
            type="range"
            min={0}
            max={periods.length - 1}
            step={1}
            value={clampedIndex}
            onChange={(e) => setIndex(Number(e.target.value))}
            className="w-full accent-[#2B68AB]"
          />

          <div className="flex justify-between mt-1 mb-3">
            {periods.map((p, i) => (
              <button
                key={p.period}
                onClick={() => setIndex(i)}
                className={
                  i === clampedIndex
                    ? "text-[10px] font-bold text-brand-blue"
                    : "text-[10px] text-zinc-500 hover:text-zinc-300 transition"
                }
              >
                {p.label}
              </button>
            ))}
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            {depts.map((dept) => {
              const point = pointFor(dept);
              return (
                <div key={dept} className="rounded-md border border-zinc-800 bg-zinc-900 p-2.5">
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[11px] font-semibold text-zinc-300">{dept}</span>
                    {point && (
                      <span
                        className="text-[10px] font-bold px-1.5 py-0.5 rounded"
                        style={{ color: "#111", backgroundColor: confidenceColor(point.confidence_pct) }}
                      >
                        {point.confidence_pct.toFixed(0)}%
                      </span>
                    )}
                  </div>

                  {point ? (
                    <>
                      <div className="text-sm text-white mb-1">
                        {point.value.toLocaleString()} {point.unit}
                        <span className="text-zinc-500 text-[11px] ml-1.5">
                          ({point.metric.replace(/_/g, " ")})
                        </span>
                      </div>
                      <div className="text-[11px] text-zinc-400">
                        {point.kind === "predicted" ? (
                          <span className="font-semibold text-brand-teal">Reference: </span>
                        ) : null}
                        {point.note}
                      </div>
                    </>
                  ) : (
                    <div className="text-[11px] text-zinc-600">No data for this period.</div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="text-[10px] text-zinc-500 italic mt-2">
            Forward periods are predictive estimates, not guaranteed outcomes — confidence
            reflects how much real ledger history backs each number; gaps are filled with a
            general industry rule-of-thumb, never presented as real data. Departments shown
            are derived from the charts on this Workspace.
          </div>
        </>
      )}
    </div>
  );
}
