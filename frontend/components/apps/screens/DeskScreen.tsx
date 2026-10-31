"use client";

// Sales "Desk" — the deal builder, live off core/deals.py + equity/manager-T.O. This is
// App Suite roadmap Phase 1 ("wire the revenue-path shells first"): the Desk shell now
// drives the real deal state machine — scenarios with real payments, the trade appraisal,
// and manager turn-over requests — all through the existing lib/deals + lib/managerTo
// clients (the same ones the back-office desk uses), so no new backend.

import { useState } from "react";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import {
  listMyDeals,
  getDeal,
  addScenario,
  selectScenario,
  type Deal,
} from "@/lib/deals";
import { getOpenTOs, requestTO, type TurnOver } from "@/lib/managerTo";
import { useAsync, WiredScreen, StatGrid, ListCard, Row, EmptyNote, Badge } from "./kit";

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${Math.round(v).toLocaleString()}`;
}

export function DeskScreen({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data, reload } = useAsync<{ deals: Deal[]; tos: TurnOver[] }>(
    async () => {
      const [deals, tos] = await Promise.all([listMyDeals(), getOpenTOs()]);
      return { deals, tos };
    },
    [],
  );

  const [selected, setSelected] = useState<Deal | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  // add-scenario form
  const [sale, setSale] = useState("");
  const [down, setDown] = useState("");
  const [term, setTerm] = useState("72");

  const deals = data?.deals ?? [];
  const tos = data?.tos ?? [];

  async function open(dealId: string) {
    setNote(null);
    try {
      setSelected(await getDeal(dealId));
    } catch {
      setNote("Couldn't open that deal.");
    }
  }

  async function doAddScenario() {
    if (!selected) return;
    setBusy(true);
    setNote(null);
    try {
      const updated = await addScenario(selected.id, {
        sale_price: Number(sale) || 0,
        down_payment: Number(down) || 0,
        term_months: Number(term) || 72,
      });
      setSelected(updated);
      setSale("");
      setDown("");
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Couldn't add scenario.");
    } finally {
      setBusy(false);
    }
  }

  async function doSelectScenario(scenarioId: string) {
    if (!selected) return;
    setBusy(true);
    try {
      setSelected(await selectScenario(selected.id, scenarioId));
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Couldn't select scenario.");
    } finally {
      setBusy(false);
    }
  }

  async function doRequestTO() {
    if (!selected) return;
    setBusy(true);
    setNote(null);
    try {
      await requestTO(selected.id, "price", "Desk requested a manager turn-over from the app.");
      setNote("Manager turn-over requested.");
      reload();
    } catch (e) {
      setNote(e instanceof Error ? e.message : "Couldn't request a turn-over.");
    } finally {
      setBusy(false);
    }
  }

  const byStatus = (s: string) => deals.filter((d) => d.status === s).length;

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>
      <StatGrid
        app={app}
        stats={[
          { label: "My deals", value: deals.length },
          { label: "Desking", value: byStatus("desking") },
          { label: "Financing", value: byStatus("financing") },
          { label: "Open T.O.s", value: tos.length },
        ]}
      />

      {note && <div className="rounded-xl bg-white/[0.06] px-3 py-2 text-[11px] text-zinc-200">{note}</div>}

      {!selected ? (
        <>
          <ListCard title="My deals" count={deals.length}>
            {deals.length === 0 && <EmptyNote>No deals on your desk yet.</EmptyNote>}
            {deals.map((d) => {
              const sel = d.scenarios.find((s) => s.id === d.selected_scenario_id) || d.scenarios[0];
              return (
                <Row
                  key={d.id}
                  onClick={() => open(d.id)}
                  primary={d.customer?.name || d.customer_id}
                  secondary={d.vehicle?.description || d.vehicle_id}
                  meta={
                    <span className="flex flex-col items-end">
                      <Badge app={app}>{d.status}</Badge>
                      {sel && <span className="mt-0.5">{money(sel.estimated_monthly_payment)}/mo</span>}
                    </span>
                  }
                />
              );
            })}
          </ListCard>

          {tos.length > 0 && (
            <ListCard title="Open manager turn-overs" count={tos.length}>
              {tos.map((t) => (
                <Row key={t.id} primary={t.reason} secondary={t.status} meta={t.linked_entity_id} />
              ))}
            </ListCard>
          )}
        </>
      ) : (
        <>
          <button onClick={() => setSelected(null)} className="text-[11px] text-zinc-400">
            ← Back to deals
          </button>

          <ListCard title={`${selected.customer?.name || selected.customer_id} · ${selected.vehicle?.description || selected.vehicle_id}`}>
            <div className="flex items-center gap-2">
              <Badge app={app}>{selected.status}</Badge>
              <span className="text-[11px] text-zinc-500">{selected.scenarios.length} scenario(s)</span>
            </div>
          </ListCard>

          <ListCard title="Scenarios" count={selected.scenarios.length}>
            {selected.scenarios.length === 0 && <EmptyNote>No scenarios yet — build one below.</EmptyNote>}
            {selected.scenarios.map((s) => (
              <Row
                key={s.id}
                onClick={() => doSelectScenario(s.id)}
                primary={
                  <span className="flex items-center gap-1.5">
                    {s.label}
                    {s.id === selected.selected_scenario_id && <Badge app={app}>selected</Badge>}
                  </span>
                }
                secondary={`${money(s.sale_price)} · ${money(s.down_payment)} down · ${s.term_months} mo @ ${s.estimated_apr}%`}
                meta={`${money(s.estimated_monthly_payment)}/mo`}
              />
            ))}
          </ListCard>

          {selected.status === "desking" && (
            <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 space-y-2">
              <h3 className="text-sm font-semibold text-white">Add a scenario</h3>
              <div className="grid grid-cols-3 gap-2">
                <input value={sale} onChange={(e) => setSale(e.target.value)} placeholder="Sale $" inputMode="numeric" className="rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-[12px] text-white" />
                <input value={down} onChange={(e) => setDown(e.target.value)} placeholder="Down $" inputMode="numeric" className="rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-[12px] text-white" />
                <input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Term mo" inputMode="numeric" className="rounded-lg border border-white/10 bg-white/5 px-2 py-1.5 text-[12px] text-white" />
              </div>
              <button onClick={doAddScenario} disabled={busy || !sale} className="w-full rounded-full bg-[var(--app-accent)] py-2 text-[12px] font-semibold text-[var(--app-accent-text)] disabled:opacity-40">
                Add scenario
              </button>
            </div>
          )}

          {selected.trade_in && (selected.trade_in.year || selected.trade_in.vin) && (
            <ListCard title="Trade & payoff">
              <Row
                primary={`${selected.trade_in.year || ""} ${selected.trade_in.make || ""} ${selected.trade_in.model || ""}`.trim() || "Trade-in"}
                secondary={`ACV ${money(selected.trade_in.acv)} · recon ${money(selected.trade_in.recon_estimate)}`}
                meta={selected.trade_in.approved ? "approved" : "pending"}
              />
            </ListCard>
          )}

          <button onClick={doRequestTO} disabled={busy} className="w-full rounded-full bg-[var(--app-accent)] py-2.5 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-40">
            Request manager turn-over
          </button>
        </>
      )}
    </WiredScreen>
  );
}
