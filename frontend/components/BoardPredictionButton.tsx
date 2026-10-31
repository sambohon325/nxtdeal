"use client";

// Board-level "Predictive Horizon" control (Pillar 2 — predictive layer, 2026-07-23).
// Mounted ONCE in MenuDashPanel over every board of a forecastable department, exactly
// like BoardCaptureButton went universal for Workspace grab-all. On open it reveals the
// existing, already-polished PredictionHorizonSlider (last week / current / tomorrow /
// next week / next month / next quarter, with a real confidence % + reference points +
// knowledge-gap disclaimer, backed by GET /readiness/timeline/{department}) — so the
// predictive horizon Sam wanted "on all charts / all reporting" reaches every dash of a
// forecastable department without wiring the slider into each of the ~93 board
// components individually.
//
// Deliberately NOT mounted on the Reporting/Overview boards (dispatchKey
// "reporting_overview"): those already surface prediction UI of their own — Reporting
// has the full-width PredictionHorizonSlider inline, and Overview has per-module
// ModuleHorizonControl adjusters (session 78, Sam: "the top predictive horizon chart on
// all of the overviews ... needs to be deleted"). MenuDashPanel gates on that.
//
// Only Sales/Service/Finance/Marketing have a real prediction source
// (DEPARTMENT_TO_PREDICTION_KEY / core/prediction.py's DEPARTMENTS); MenuDashPanel only
// mounts this button for those, so this component itself assumes a forecastable
// department and always renders the slider.

import { useEffect, useRef, useState } from "react";
import { PredictionHorizonSlider } from "@/components/PredictionHorizonSlider";

type Theme = "dark" | "light";

type Props = {
  department: string;
  theme?: Theme;
  // Open the panel upward (for a bottom-anchored placement).
  openUp?: boolean;
};

export default function BoardPredictionButton({ department, theme = "dark", openUp = false }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(e: MouseEvent) {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const panelCls =
    theme === "dark"
      ? "border-zinc-700 bg-brand-charcoal text-zinc-200"
      : "border-zinc-200 bg-white text-zinc-800";
  const chip =
    theme === "dark"
      ? "bg-zinc-800/90 text-zinc-200 hover:bg-zinc-700 border-zinc-700"
      : "bg-white/90 text-zinc-700 hover:bg-zinc-100 border-zinc-300";

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title="Show the predictive horizon for this department"
        className={`inline-flex items-center gap-1 text-[10px] font-medium px-2 py-1 rounded-md border shadow-sm backdrop-blur ${chip}`}
      >
        <span aria-hidden>📈</span> Predict
      </button>

      {open && (
        <div
          className={`absolute right-0 z-40 w-96 max-w-[92vw] rounded-lg border shadow-xl p-3 ${
            openUp ? "bottom-full mb-1" : "mt-1"
          } ${panelCls}`}
        >
          <div className="flex items-center justify-between px-0.5 pb-2">
            <div className="text-[10px] uppercase tracking-wide text-zinc-500">
              Predictive Horizon — {department}
            </div>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="text-zinc-500 hover:text-zinc-300 text-xs leading-none"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
          <PredictionHorizonSlider department={department} theme={theme} />
        </div>
      )}
    </div>
  );
}
