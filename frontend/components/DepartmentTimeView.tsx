"use client";
import { WorkButton } from "./WorkspaceUi";

import { useEffect, useState } from "react";
import { DEPARTMENT_TO_PREDICTION_KEY, fetchTimeline, type TimelineResponse } from "@/lib/predictionTimeline";
import styles from "./CommandCenter.module.css";

/** Only renders actual API period aggregates. Never substitutes live record lists. */
export function DepartmentTimeView({ department, period, onToday }: { department: string; period: string; onToday: () => void }) {
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [retry, setRetry] = useState(0);
  const source = DEPARTMENT_TO_PREDICTION_KEY[department];
  useEffect(() => {
    let active = true;
    setData(null);
    if (source) fetchTimeline(source).then(result => { if (active) setData(result); });
    return () => { active = false; };
  }, [source, retry]);
  const point = data?.points?.find(p => p.period === period);
  return <section className={styles.temporalEmpty} aria-label={`${department} time view`}>
    <h2>{department} · {period === "last_week" ? "Last 7 days" : period.replaceAll("_", " ")}</h2>
    {source && !data ? <p role="status">Loading dated department data…</p> : point ? <>
      <p>{point.kind === "actual" ? "Recorded period total" : "Forecast period total"} · {point.metric.replaceAll("_", " ")}</p>
      <strong className={styles.temporalValue}>{point.value.toLocaleString()} <small>{point.unit}</small></strong>
      <p>{point.kind === "predicted" ? `${point.confidence_pct.toFixed(0)}% model confidence · ` : ""}Basis: {point.basis.replaceAll("_", " ")} · {point.sample_size} source records</p>
      <p>{point.note}</p>
      <p>Department aggregate for this period. Individual records and this section’s detailed charts do not have dated snapshots yet.</p>
    </> : <p>{data?.note || `Dated totals are not available for ${department}.`} {source && <WorkButton type="submit" onClick={() => setRetry(v => v + 1)}>Retry</WorkButton>}</p>}
    <p>Your time selection stays with you across departments and sections.</p>
    <WorkButton type="submit" onClick={onToday}>View today's data</WorkButton>
  </section>;
}
