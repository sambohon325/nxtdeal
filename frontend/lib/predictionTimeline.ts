// Shared prediction-timeline fetch + types (session 78). Extracted from
// components/PredictionHorizonSlider.tsx so components/ReportDashboardBuilder.tsx's
// Overview board can fetch the same real department-level timeline once and hand it
// down to every module card's own compact horizon control
// (components/ModuleHorizonControl.tsx), instead of duplicating the fetch/types or
// having each module card re-fetch independently.
//
// Session 78, Sam (after the initial Overview BI-glance build): "predictive horizon
// needs to be available on all charts (to the departments that it applies to), so all
// the modules in the overview need to have the time horizon adjusters on them, and the
// top predictive horizon chart on all of the overviews (that have it) needs to be
// deleted."
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type TimelinePoint = {
  period: string;
  label: string;
  kind: "actual" | "predicted";
  department: string;
  metric: string;
  unit: string;
  value: number;
  confidence_pct: number;
  basis: "actual" | "ledger" | "blended" | "industry_estimate";
  sample_size: number;
  factors?: { volume: number; recency: number; completeness: number };
  note: string;
};

export type TimelineResponse = {
  department: string;
  available: boolean;
  points?: TimelinePoint[];
  note?: string;
};

// The Top Menu's display department names -> core/prediction.py's DEPARTMENTS keys.
// Only these four have a real dated-entity source to forecast from (see
// core/prediction.py's _DEPARTMENT_SOURCES) -- Operations/Inventory/Administration/
// Readiness/Network genuinely have no prediction entry anywhere in this codebase
// (confirmed sessions 65-67), so they're deliberately absent from this map rather than
// guessed at. This is also, by construction, exactly "the departments that it applies
// to" from Sam's session-78 request -- a module card on any other department's
// Overview board simply renders no horizon control at all.
export const DEPARTMENT_TO_PREDICTION_KEY: Record<string, string> = {
  Sales: "sales",
  Service: "service",
  Finance: "finance",
  Marketing: "marketing",
};

export function confidenceColor(pct: number): string {
  if (pct >= 90) return "#3FBCC4"; // brand-teal
  if (pct >= 70) return "#FBCF09"; // brand-yellow
  return "#EE3C25"; // brand-red
}

export async function fetchTimeline(predictionKey: string): Promise<TimelineResponse> {
  try {
    const res = await fetch(`${API_BASE}/readiness/timeline/${predictionKey}`, {
      headers: { ...authHeaders() },
    });
    return await res.json();
  } catch {
    return { department: predictionKey, available: false, note: "Unable to reach NXTDeal backend." };
  }
}
