"use client";
import {Line,LineChart,ResponsiveContainer,Tooltip,XAxis,YAxis,CartesianGrid,Legend} from "recharts";
import type {Run} from "./LabAnalysis";
import styles from "./DealershipLab.module.css";

export function ComparisonSummary({run}:{run:Run}) {
 const format=(n:number)=>new Intl.NumberFormat(undefined,{style:"currency",currency:run.currency,maximumFractionDigits:0}).format(n);
 const metrics=[["profit","Cumulative profit change"],["cash","Ending cash change"],["sales","Cumulative sales change"]] as const;
 const profit=run.payload.difference.profit;
 const last=profit.median.length-1;
 const rows=run.payload.baseline.bands.profit.median.map((value,i)=>({month:i,baseline:value,proposed:run.payload.proposed.bands.profit.median[i]}));
 return <section className={`${styles.panel} ${styles.resultSummary}`} aria-label="Comparison summary">
  <p className={styles.eyebrow}>YOUR COMPARISON · {run.intent.months} MONTHS</p><h2>{run.baseline.name} → {run.proposed.name}</h2>
  <p>{profit.median[last]>0?"The proposed plan has higher median cumulative profit in this model.":profit.median[last]<0?"The proposed plan has lower median cumulative profit in this model.":"The modeled median cumulative profit is unchanged."} Review the range and cash effects before deciding.</p>
  <div className={styles.outcomeGrid}>{metrics.map(([key,title])=>{const band=run.payload.difference[key];if(!band)return null;const index=band.median.length-1;const display=(n:number)=>key==="sales"?n.toLocaleString(undefined,{maximumFractionDigits:0}):format(n);return <div key={key}><span>{title}</span><strong>{display(band.median[index])}</strong><small>10th–90th percentile: {display(band.low[index])} to {display(band.high[index])}</small></div>;})}</div>
  <h3>Cumulative profit over time · {run.currency}</h3><p>Median model outcomes. Ranges above describe paired differences, not guaranteed returns.</p>
  <div className={styles.resultChart} role="img" aria-label={`Median cumulative profit over ${run.intent.months} months. Detailed monthly values are available below.`}><ResponsiveContainer width="100%" height={250}><LineChart data={rows} margin={{top:8,right:12,bottom:10,left:8}}><CartesianGrid stroke="var(--lab-border)" vertical={false}/><XAxis dataKey="month" stroke="var(--lab-muted)" label={{value:"Month",position:"insideBottomRight",offset:-6}}/><YAxis stroke="var(--lab-muted)" width={70} tickFormatter={v=>Intl.NumberFormat(undefined,{notation:"compact"}).format(Number(v))}/><Tooltip contentStyle={{background:"var(--lab-panel)",border:"1px solid var(--lab-border)",color:"var(--lab-text)"}} formatter={value=>format(Number(value))} labelFormatter={v=>`Month ${v}`}/><Legend/><Line name="Starting plan" dataKey="baseline" stroke="var(--lab-muted)" strokeDasharray="5 4" dot={false} strokeWidth={2} isAnimationActive={false}/><Line name="Proposed change" dataKey="proposed" stroke="var(--accent)" dot={false} strokeWidth={3} isAnimationActive={false}/></LineChart></ResponsiveContainer></div>
 </section>;
}
