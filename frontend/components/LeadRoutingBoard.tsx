"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Bumper-parity Leads Configuration (2026-07-25): named lead-distribution rules. Create
// rules that route incoming leads by source to a team (round-robin / least-busy) or a
// specific rep, toggle them on/off, and test a rule against a sample lead. Backed by
// lib/leadRouting.ts (backend/api/routers/lead_routing_rules.py). ADMIN/OPERATIONS.
import { useEffect, useState } from "react";
import {
  getRoutingConfig,
  listRoutingRules,
  createRoutingRule,
  setRuleActive,
  deleteRoutingRule,
  previewRoute,
  type RoutingRule,
  type RoutingStrategy,
  type RoutePreview,
} from "@/lib/leadRouting";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

export function LeadRoutingBoard({ theme }: { theme: Theme }) {
  const [rules, setRules] = useState<RoutingRule[]>([]);
  const [sources, setSources] = useState<string[]>([]);
  const [strategies, setStrategies] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [preview, setPreview] = useState<RoutePreview | null>(null);

  const [name, setName] = useState("");
  const [strategy, setStrategy] = useState<RoutingStrategy>("round_robin");
  const [dept, setDept] = useState("Sales");
  const [empId, setEmpId] = useState("");
  const [matchSource, setMatchSource] = useState("");
  const [testSource, setTestSource] = useState("");

  const card = tc(theme, "rounded-md border border-zinc-800 bg-zinc-900/60 p-3", "rounded-md border border-zinc-200 bg-white p-3");
  const input = tc(theme, "rounded-md bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-[12px]", "rounded-md bg-white border border-zinc-300 px-2 py-1.5 text-[12px]");

  function refresh() {
    Promise.all([listRoutingRules(), getRoutingConfig()])
      .then(([r, c]) => {
        setRules(r.rules);
        setSources(c.sources);
        setStrategies(c.strategies);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load routing rules."));
  }

  useEffect(refresh, []);

  async function create() {
    setBusy(true); setError(null);
    try {
      await createRoutingRule({
        name,
        strategy,
        target_department: strategy === "specific_employee" ? null : dept,
        target_employee_id: strategy === "specific_employee" ? empId : null,
        match_sources: matchSource ? [matchSource] : [],
      });
      setName(""); setEmpId(""); setMatchSource(""); setShowForm(false);
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't create rule."); } finally { setBusy(false); }
  }

  async function toggle(r: RoutingRule) {
    try { await setRuleActive(r.id, !r.is_active); refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't toggle rule."); }
  }

  async function remove(r: RoutingRule) {
    try { await deleteRoutingRule(r.id); refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't delete rule."); }
  }

  async function test() {
    setError(null);
    try { setPreview(await previewRoute({ Source: testSource })); }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't test."); }
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
      <div className="px-3 pt-3 shrink-0 flex items-center justify-between">
        <div>
          <div className="text-base font-brand">Leads Configuration</div>
          <div className="text-xs text-zinc-500">Route incoming leads by source to a team or rep. Rules fire top-down by priority.</div>
        </div>
        <WorkButton type="submit" onClick={() => setShowForm((s) => !s)} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold">
          {showForm ? "Close" : "+ New rule"}
        </WorkButton>
      </div>

      {error && <div className="mx-3 mt-2 rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>}

      <div className="p-3 space-y-2">
        {showForm && (
          <div className={card + " space-y-2"}>
            <WorkField label="Rule name"><WorkInput className={input + " w-full"} placeholder="Rule name (e.g. Website → Internet team)" value={name} onChange={(e) => setName(e.target.value)} /></WorkField>
            <div className="flex flex-wrap gap-2 items-center">
              <WorkField label="Routing strategy"><WorkSelect className={input} value={strategy} onChange={(e) => setStrategy(e.target.value as RoutingStrategy)}>
                {strategies.map((s) => <option key={s} value={s}>{s.replace("_", " ")}</option>)}
              </WorkSelect></WorkField>
              {strategy === "specific_employee" ? (
                <WorkField label="Employee ID"><WorkInput className={input} placeholder="Employee ID (e.g. EMP-00001)" value={empId} onChange={(e) => setEmpId(e.target.value)} /></WorkField>
              ) : (
                <WorkField label="Department"><WorkInput className={input} placeholder="Department (e.g. Sales)" value={dept} onChange={(e) => setDept(e.target.value)} /></WorkField>
              )}
              <WorkField label="Match Source"><WorkSelect className={input} value={matchSource} onChange={(e) => setMatchSource(e.target.value)}>
                <option value="">Any source</option>
                {sources.map((s) => <option key={s} value={s}>{s}</option>)}
              </WorkSelect></WorkField>
              <WorkButton type="submit" onClick={create} disabled={busy || !name} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">Create (inactive)</WorkButton>
            </div>
          </div>
        )}

        <div className={card}>
          <div className="text-xs font-semibold mb-2">Rules ({rules.length})</div>
          {rules.map((r) => (
            <div key={r.id} className="flex items-center gap-2 text-xs py-1 border-b border-zinc-800/50">
              <div className="flex-1 truncate">{r.name}</div>
              <div className="text-zinc-500 truncate w-28">{r.strategy.replace("_", " ")}</div>
              <div className="text-zinc-500 truncate w-24">{r.match_sources.length ? r.match_sources.join(",") : "any"}</div>
              <div className="text-zinc-600 w-10">×{r.times_matched}</div>
              <WorkButton type="submit" onClick={() => toggle(r)} className={r.is_active ? "text-xs px-2 py-0.5 rounded bg-brand-teal text-black" : "text-xs px-2 py-0.5 rounded bg-zinc-700 text-white"}>
                {r.is_active ? "Active" : "Off"}
              </WorkButton>
              <WorkButton type="submit" onClick={() => remove(r)} className="text-xs px-1.5 text-zinc-500">✕</WorkButton>
            </div>
          ))}
          {rules.length === 0 && <div className="text-xs text-zinc-500">No rules yet.</div>}
        </div>

        <div className={card}>
          <div className="text-xs font-semibold mb-2">Test a configuration</div>
          <div className="flex gap-2 items-center">
            <WorkField label="Test Source"><WorkSelect className={input} value={testSource} onChange={(e) => setTestSource(e.target.value)}>
              <option value="">Pick a source…</option>
              {sources.map((s) => <option key={s} value={s}>{s}</option>)}
            </WorkSelect></WorkField>
            <WorkButton type="submit" onClick={test} disabled={!testSource} className="text-xs px-3 py-1.5 rounded-md bg-zinc-700 text-white disabled:opacity-50">Test</WorkButton>
          </div>
          {preview && (
            <div className="text-xs mt-2 text-zinc-400">
              {preview.matched
                ? `→ Rule "${preview.rule_name}" (${preview.strategy}) would assign to ${preview.would_assign_to || "—"}${preview.error ? ` (${preview.error})` : ""}`
                : "No active rule matches this source."}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default LeadRoutingBoard;
