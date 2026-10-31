"use client";

// Reporting-tab prediction-horizon slider (2026-07-15, session 71). Sam: "all
// reporting tabs need to have sliding bars next to the view / pop out section where
// they can slide the information back in forth based on predictive knowledge with
// percentages. it also needs to be on the graphs. for now lets do last week / current
// / tomorrow/ next week/ next month/ next quarter, and have a sliding scale percentage
// next to it. when prediction is activated, please put in reference points on what its
// based on and a disclaimer for any knowledge gaps."
//
// Backed by GET /readiness/timeline/{department} (core/prediction.py's timeline(),
// new this session) -- a real 6-point series, not a fabricated animation: "Last Week"/
// "Current" are actual already-recorded ledger counts (basis="actual", 100%
// confidence), "Tomorrow"/"Next Week"/"Next Month"/"Next Quarter" reuse
// core/prediction.py's existing predict() forecast blend verbatim (basis
// "ledger"/"blended"/"industry_estimate", real confidence_pct). Only sales/service/
// finance/marketing have a real prediction source at all (core/prediction.py's
// DEPARTMENTS) -- every other Top Menu department renders the honest "not available"
// state below rather than a fabricated slider.
//
// Mounted from MenuDashPanel.tsx's MenuDashBody, directly under the Dark/Light "view"
// + Print/pop-out toolbar row, only when itemKey === "reporting".

import { useWorkspaceTools } from "@/lib/workspaceTools";
import { useEffect, useMemo, useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
} from "recharts";
import {
  DEPARTMENT_TO_PREDICTION_KEY,
  confidenceColor,
  fetchTimeline,
  type TimelineResponse,
} from "@/lib/predictionTimeline";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

export function PredictionHorizonSlider({
  department,
  theme,
}: {
  department: string;
  theme: Theme;
}) {
  const legacyControls = useWorkspaceTools();
  const predictionKey = DEPARTMENT_TO_PREDICTION_KEY[department];

  const [data, setData] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [index, setIndex] = useState(1); // default to "Current"

  useEffect(() => {
    if (!predictionKey) return;

    let cancelled = false;
    setLoading(true);

    fetchTimeline(predictionKey)
      .then((d) => {
        if (!cancelled) setData(d);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [predictionKey]);

  const points = data?.points ?? [];
  const selected = points[index];

  const chartData = useMemo(
    () => points.map((p) => ({ label: p.label, value: p.value, kind: p.kind, period: p.period })),
    [points]
  );

  if (!legacyControls) return null;

  if (!predictionKey) {
    return (
      <div
        className={tc(
          theme,
          "mb-4 rounded-lg border border-dashed border-zinc-800 bg-zinc-950 p-3 text-xs text-zinc-500",
          "mb-4 rounded-lg border border-dashed border-zinc-300 bg-zinc-50 p-3 text-xs text-zinc-500"
        )}
      >
        No predictive scoring source exists yet for {department} -- NXTDeal currently
        forecasts Sales, Service, Finance, and Marketing only.
      </div>
    );
  }

  return (
    <div
      className={tc(
        theme,
        "mb-4 rounded-lg border border-zinc-800 bg-zinc-950 p-3",
        "mb-4 rounded-lg border border-zinc-300 bg-zinc-50 p-3"
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span className={tc(theme, "font-brand text-[11px] font-bold uppercase tracking-wide text-zinc-400", "font-brand text-[11px] font-bold uppercase tracking-wide text-zinc-500")}>
          Predictive Horizon
        </span>
        {selected && (
          <span
            className="text-xs font-bold px-2 py-0.5 rounded"
            style={{
              color: "#111",
              backgroundColor: confidenceColor(selected.confidence_pct),
            }}
          >
            {selected.confidence_pct.toFixed(0)}% confidence
          </span>
        )}
      </div>

      {loading && <div className="text-xs text-zinc-500 mb-2">Loading predictive data…</div>}

      {!loading && points.length > 0 && (
        <>
          <div style={{ width: "100%", height: 140 }} className="mb-2">
            <ResponsiveContainer>
              <BarChart data={chartData} margin={{ top: 8, right: 8, left: -20, bottom: 0 }}>
                <XAxis dataKey="label" tick={{ fontSize: 10, fill: theme === "dark" ? "#a1a1aa" : "#52525b" }} interval={0} angle={-20} textAnchor="end" height={40} />
                <YAxis tick={{ fontSize: 10, fill: theme === "dark" ? "#a1a1aa" : "#52525b" }} />
                <Tooltip
                  contentStyle={{ background: theme === "dark" ? "#18181b" : "#fff", border: "1px solid #3f3f46", fontSize: 12 }}
                  formatter={(value: unknown, _name: unknown, props: unknown) => {
                    // recharts' Tooltip `formatter` generic signature (Formatter<ValueType, NameType>)
                    // doesn't line up cleanly with a plain `number` param -- ValueType can include
                    // `undefined` in some of its overloads, which a `value: number` annotation can't
                    // accept, and `props` is a union type where `.payload` isn't uniformly typed.
                    // Typing the params loosely here and narrowing at runtime (rather than fighting
                    // recharts' generics) is the standard workaround for this exact class of mismatch.
                    const period = (props as { payload?: { period?: unknown } })?.payload?.period;
                    return [`${value} ${period ? selected?.unit ?? "" : ""}`, "Value"];
                  }}
                />
                <Bar dataKey="value" radius={[3, 3, 0, 0]}>
                  {chartData.map((entry, i) => (
                    <Cell
                      key={entry.period}
                      fill={i === index ? "#2B68AB" : entry.kind === "actual" ? "#5c5c66" : "#3f3f46"}
                      stroke={i === index ? "#3FBCC4" : "none"}
                      strokeWidth={i === index ? 2 : 0}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          <input aria-label="Time horizon"
            type="range"
            min={0}
            max={points.length - 1}
            step={1}
            value={index}
            onChange={(e) => setIndex(Number(e.target.value))}
            className="w-full accent-[#2B68AB]"
          />

          <div className="flex justify-between mt-1 mb-3">
            {points.map((p, i) => (
              <button
                key={p.period}
                onClick={() => setIndex(i)}
                className={
                  i === index
                    ? "text-[10px] font-bold text-brand-blue"
                    : tc(theme, "text-[10px] text-zinc-500 hover:text-zinc-300 transition", "text-[10px] text-zinc-500 hover:text-zinc-800 transition")
                }
              >
                {p.label}
              </button>
            ))}
          </div>

          {selected && (
            <div
              className={tc(
                theme,
                "rounded-md border border-zinc-800 bg-zinc-900 p-2.5",
                "rounded-md border border-zinc-200 bg-white p-2.5"
              )}
            >
              <div className={tc(theme, "text-sm text-white mb-1", "text-sm text-black mb-1")}>
                {selected.value.toLocaleString()} {selected.unit}
                <span className={tc(theme, "text-zinc-500 text-xs ml-2", "text-zinc-500 text-xs ml-2")}>
                  ({selected.metric.replace(/_/g, " ")})
                </span>
              </div>

              {selected.kind === "predicted" ? (
                <>
                  <div className={tc(theme, "text-xs text-zinc-400 mb-1", "text-xs text-zinc-600 mb-1")}>
                    <span className="font-semibold text-brand-teal">Reference point: </span>
                    {selected.note}
                  </div>
                  <div className={tc(theme, "text-[11px] text-zinc-500 italic", "text-[11px] text-zinc-500 italic")}>
                    Disclaimer: this is a predictive estimate, not a guaranteed outcome.
                    Confidence reflects how much real ledger history backs it (volume,
                    recency, and day-to-day completeness) -- gaps in that history are
                    filled with a general industry rule-of-thumb, never presented as
                    real data.
                  </div>
                </>
              ) : (
                <div className={tc(theme, "text-xs text-zinc-400", "text-xs text-zinc-600")}>
                  {selected.note}
                </div>
              )}
            </div>
          )}
        </>
      )}

      {!loading && points.length === 0 && data?.note && (
        <div className="text-xs text-zinc-500">{data.note}</div>
      )}
    </div>
  );
}
