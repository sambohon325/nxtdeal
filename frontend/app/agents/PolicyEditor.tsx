"use client";
import { useState } from "react";

export type Policy = { disabled: string[]; require_approval: string[]; employee_limits?: Record<string, string[]>; lead_response_sla_minutes: number; discount_limit: number; trade_appraisal_limit: number; max_autonomous_risk: number };

export default function PolicyEditor({ policy, capabilities, busy, save }: { policy: Policy; capabilities: string[]; busy: boolean; save: (value: Policy) => void }) {
  const [draft, setDraft] = useState(policy);
  const [employee, setEmployee] = useState("");
  const [limit, setLimit] = useState<string[]>([]);
  function toggle(key: "disabled" | "require_approval", name: string) {
    setDraft({ ...draft, [key]: draft[key].includes(name) ? draft[key].filter(c => c !== name) : [...draft[key], name] });
  }
  return <details><summary style={{ cursor: "pointer", fontWeight: 600 }}>Dealer policy controls</summary>
    <p>Employee limits narrow the department’s access. Consequential actions always require approval.</p>
    <form onSubmit={e => { e.preventDefault(); save(draft); }}>
      <label>Maximum risk without approval <select value={draft.max_autonomous_risk} onChange={e => setDraft({ ...draft, max_autonomous_risk: Number(e.target.value) })}>{[0, 1, 2, 3].map(n => <option key={n} value={n}>{["0 — Read", "1 — Recommend", "2 — Draft", "3 — Reversible action"][n]}</option>)}</select></label>
      <table style={{ width: "100%", fontSize: 12, margin: "18px 0", textAlign: "left" }}><thead><tr><th>Capability</th><th>Disabled</th><th>Always approve</th></tr></thead><tbody>{capabilities.map(c => <tr key={c}><td>{c}</td><td><input aria-label={`Disable ${c}`} type="checkbox" checked={draft.disabled.includes(c)} onChange={() => toggle("disabled", c)} /></td><td><input aria-label={`Require approval for ${c}`} type="checkbox" checked={draft.require_approval.includes(c)} onChange={() => toggle("require_approval", c)} /></td></tr>)}</tbody></table>
      <fieldset style={{ padding: 12, border: "1px solid #e0e5ed", marginBottom: 16 }}><legend>Employee access limits</legend>
        <label>Employee ID <input value={employee} onChange={e => { setEmployee(e.target.value); setLimit(draft.employee_limits?.[e.target.value] || []); }} /></label>
        {employee && <><p>Select permitted capabilities. An empty saved list disables all agent tools for this employee.</p><div style={{ display: "flex", gap: 10, flexWrap: "wrap" }}>{capabilities.map(c => <label key={c}><input type="checkbox" checked={limit.includes(c)} onChange={e => setLimit(e.target.checked ? [...limit, c] : limit.filter(v => v !== c))} />{c}</label>)}</div>
          <button type="button" onClick={() => setDraft({ ...draft, employee_limits: { ...draft.employee_limits, [employee]: limit } })}>Apply to policy draft</button>
          <button type="button" onClick={() => { const next = { ...draft.employee_limits }; delete next[employee]; setDraft({ ...draft, employee_limits: next }); }}>Restore department defaults</button>
        </>}
        <p>{Object.keys(draft.employee_limits || {}).length} employee overrides in this policy draft.</p>
      </fieldset><button disabled={busy} type="submit">Save dealer policy</button>
    </form>
  </details>;
}
