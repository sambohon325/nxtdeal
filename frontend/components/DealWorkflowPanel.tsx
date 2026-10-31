"use client";
import { WorkInput, WorkButton, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Deal-centric workflow tabs (session 102 follow-up, Sam: "it needs to be a working
// process, not just a list") -- rendered inside three of Sales' workflow-catalog
// modals that all operate on a Deal: Desking & Trade Evaluation, F&I Handoff, and
// Delivery Experience. Rather than building three separate bespoke boards, one panel
// covers all 15 named tabs across those three workflows (5 each) since they're all
// real actions against the same Deal entity -- reuses lib/deals.ts's already-built
// Deal Desk functions directly (core/deals.py, session 33/91) instead of duplicating
// any pricing/financing/appraisal logic.
//
// Delivery's 4 checklist tabs (vehicle_prep/quality_control/tech_setup/documentation)
// plus csi are backed by a real, lightweight new Deal field (core/deals.py's
// delivery_checklist, this session) -- Delivery Experience previously had nothing
// behind it at all.
import { useEffect, useState } from "react";
import {
  getDeal,
  updateTradeAppraisal,
  approveTradeAppraisal,
  addScenario,
  removeScenario,
  selectScenario,
  chooseInHouseFinancing,
  submitToLender,
  recordLenderDecision,
  acceptCounteredTerms,
  generateContract,
  updateDeliveryChecklist,
  listLenders,
  type Deal,
  type Lender,
  type DeliveryChecklistSection,
} from "@/lib/deals";

export type DealPanelSection =
  | "financial_profile" | "trade_appraisal" | "structuring" | "presentation" | "approval"
  | "packaging" | "transfer" | "product_presentation" | "lender_submission" | "contract_readiness"
  | "vehicle_prep" | "quality_control" | "tech_setup" | "documentation" | "csi";

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function NoDeal() {
  return (
    <div className="p-4 rounded-lg border border-dashed border-zinc-800 bg-zinc-900/40">
      <p className="text-xs text-zinc-500 leading-relaxed">
        This tab works against a specific Deal. Start or track an instance of this
        workflow from the <span className="text-zinc-300">Overview</span> tab with a real
        Deal ID (DEAL-…) to see it here.
      </p>
    </div>
  );
}

function Checklist({
  title,
  fields,
  values,
  busy,
  onToggle,
}: {
  title: string;
  fields: { key: string; label: string }[];
  values: Record<string, unknown>;
  busy: boolean;
  onToggle: (key: string, value: boolean) => void;
}) {
  return (
    <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
      <div className="text-xs font-medium text-zinc-200 mb-2">{title}</div>
      <div className="space-y-1.5">
        {fields.map((f) => (
          <label key={f.key} className="flex items-center gap-2 text-xs text-zinc-300">
            <WorkInput
              type="checkbox"
              checked={Boolean(values[f.key])}
              disabled={busy}
              onChange={(e) => onToggle(f.key, e.target.checked)}
            />
            {f.label}
          </label>
        ))}
      </div>
      {typeof values.updated_at === "string" && (
        <div className="text-xs text-zinc-600 mt-2">
          Last updated {new Date(values.updated_at).toLocaleString()}
          {typeof values.updated_by === "string" ? ` by ${values.updated_by}` : ""}
        </div>
      )}
    </div>
  );
}

export function DealWorkflowPanel({ dealId, section }: { dealId: string | null; section: DealPanelSection }) {
  const [deal, setDeal] = useState<Deal | null>(null);
  const [lenders, setLenders] = useState<Lender[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  // Trade appraisal form
  const [appraisal, setAppraisal] = useState<Record<string, string>>({});

  // Structuring form
  const [scenarioLabel, setScenarioLabel] = useState("");
  const [salePrice, setSalePrice] = useState("");
  const [downPayment, setDownPayment] = useState("");
  const [termMonths, setTermMonths] = useState("60");

  // Lender submission
  const [lenderId, setLenderId] = useState("");
  const [decisionNotes, setDecisionNotes] = useState("");

  function refresh() {
    if (!dealId) {
      setLoading(false);
      return;
    }
    setLoading(true);
    Promise.all([getDeal(dealId), listLenders()])
      .then(([d, l]) => {
        setDeal(d);
        setLenders(l);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load this deal."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [dealId]);

  async function withBusy(fn: () => Promise<Deal>, successMsg?: string) {
    setBusy(true);
    setError(null);
    try {
      const d = await fn();
      setDeal(d);
      if (successMsg) setMessage(successMsg);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't go through.");
    } finally {
      setBusy(false);
    }
  }

  async function saveAppraisal() {
    if (!dealId) return;
    const patch: Record<string, unknown> = {};
    Object.entries(appraisal).forEach(([k, v]) => {
      if (v.trim() === "") return;
      patch[k] = ["mileage", "acv", "recon_estimate", "market_value_estimate"].includes(k) ? Number(v) : v;
    });
    await withBusy(() => updateTradeAppraisal(dealId, patch), "Appraisal saved.");
  }

  async function addNewScenario() {
    if (!dealId || !salePrice.trim()) return;
    await withBusy(
      () =>
        addScenario(dealId, {
          label: scenarioLabel.trim() || undefined,
          sale_price: Number(salePrice),
          down_payment: downPayment.trim() ? Number(downPayment) : undefined,
          term_months: termMonths.trim() ? Number(termMonths) : undefined,
        }),
      "Scenario added."
    );
    setScenarioLabel("");
    setSalePrice("");
    setDownPayment("");
  }

  async function toggleChecklist(checklistSection: DeliveryChecklistSection, key: string, value: boolean) {
    if (!dealId) return;
    setBusy(true);
    setError(null);
    try {
      const d = await updateDeliveryChecklist(dealId, checklistSection, { [key]: value });
      setDeal(d);
    } catch (e) {
      setError(e instanceof Error ? e.message : "That didn't go through.");
    } finally {
      setBusy(false);
    }
  }

  if (!dealId) return <NoDeal />;
  if (loading) return <div className="text-xs text-zinc-600">Loading…</div>;
  if (!deal) return <div className="text-xs text-zinc-600">{error || "Deal not found."}</div>;

  const selectedScenario = deal.scenarios.find((s) => s.id === deal.selected_scenario_id) || null;
  const checklist = deal.delivery_checklist || {};

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}

      {section === "financial_profile" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Customer Financial Profile</div>
          {deal.customer ? (
            <div className="text-xs text-zinc-300 space-y-1">
              <div>{deal.customer.name}</div>
              <div className="text-zinc-500">{deal.customer.email || "—"} · {deal.customer.phone || "—"}</div>
              <div>Credit score: <span className="text-zinc-200">{deal.customer.credit_score ?? "—"}</span></div>
            </div>
          ) : (
            <div className="text-xs text-zinc-600">No customer resolved for this deal.</div>
          )}
          {deal.vehicle && (
            <div className="mt-3 pt-3 border-t border-zinc-800 text-xs text-zinc-300">
              <div>{deal.vehicle.description}</div>
              <div className="text-zinc-500">VIN {deal.vehicle.vin || "—"} · {money(deal.vehicle.price)}</div>
            </div>
          )}
        </div>
      )}

      {(section === "trade_appraisal" || section === "approval") && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">
            {section === "approval" ? "Management Approval — Trade Appraisal Review" : "Trade Appraisal"}
          </div>

          {deal.trade_in && (
            <div className="text-xs text-zinc-300 mb-2 space-y-0.5">
              <div>{deal.trade_in.year} {deal.trade_in.make} {deal.trade_in.model} {deal.trade_in.trim}</div>
              <div className="text-zinc-500">VIN {deal.trade_in.vin || "—"} · {deal.trade_in.mileage ?? "—"} mi · {deal.trade_in.condition || "—"}</div>
              <div>ACV {money(deal.trade_in.acv)} · Recon est. {money(deal.trade_in.recon_estimate)} · Market est. {money(deal.trade_in.market_value_estimate)}</div>
              <div>
                Status:{" "}
                {deal.trade_in.approved ? (
                  <span className="text-emerald-400">Approved by {deal.trade_in.approved_by}</span>
                ) : (
                  <span className="text-amber-400">Awaiting approval</span>
                )}
              </div>
            </div>
          )}

          {section === "trade_appraisal" && (
            <>
              <div className="grid grid-cols-3 gap-2 mb-2">
                {["vin", "year", "make", "model", "trim", "mileage", "condition", "acv", "recon_estimate", "market_value_estimate"].map((f) => (
                  <WorkInput
                    key={f}
                    value={appraisal[f] ?? ""}
                    onChange={(e) => setAppraisal((a) => ({ ...a, [f]: e.target.value }))}
                    aria-label={f.replace(/_/g, " ")} placeholder={f.replace(/_/g, " ")}
                    className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
                  />
                ))}
              </div>
              <WorkButton type="submit" onClick={saveAppraisal} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
                {busy ? "Saving…" : "Save Appraisal"}
              </WorkButton>
            </>
          )}

          {deal.trade_in && !deal.trade_in.approved && (
            <WorkButton type="submit" variant="primary"
              onClick={() => withBusy(() => approveTradeAppraisal(dealId), "Trade appraisal approved.")}
              disabled={busy}
              className="text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium disabled:opacity-50 ml-2"
            >
              Approve
            </WorkButton>
          )}
        </div>
      )}

      {section === "structuring" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Deal Structuring — Scenarios</div>
          <div className="space-y-1.5 mb-3">
            {deal.scenarios.length === 0 ? (
              <div className="text-xs text-zinc-600">No scenarios built yet.</div>
            ) : (
              deal.scenarios.map((s) => (
                <div key={s.id} className={`rounded-lg border p-2 text-xs ${s.id === deal.selected_scenario_id ? "border-emerald-800 bg-emerald-950/20" : "border-zinc-800"}`}>
                  <div className="flex items-center justify-between gap-2">
                    <div className="text-zinc-200">{s.label} — {money(s.sale_price)} · {s.term_months}mo · {money(s.estimated_monthly_payment)}/mo</div>
                    <div className="flex gap-1 shrink-0">
                      {s.id !== deal.selected_scenario_id && (
                        <WorkButton type="submit" onClick={() => withBusy(() => selectScenario(dealId, s.id), "Scenario selected.")} className="px-2 py-0.5 rounded bg-zinc-200 text-black font-medium">Select</WorkButton>
                      )}
                      <WorkButton type="submit" onClick={() => withBusy(() => removeScenario(dealId, s.id))} className="px-2 py-0.5 rounded border border-zinc-700 text-zinc-400">Remove</WorkButton>
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <WorkField label="Label (optional)"><WorkInput value={scenarioLabel} onChange={(e) => setScenarioLabel(e.target.value)} placeholder="Label (optional)" className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 w-32" /></WorkField>
            <WorkField label="Sale price"><WorkInput value={salePrice} onChange={(e) => setSalePrice(e.target.value)} placeholder="Sale price" className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 w-28" /></WorkField>
            <WorkField label="Down payment"><WorkInput value={downPayment} onChange={(e) => setDownPayment(e.target.value)} placeholder="Down payment" className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 w-28" /></WorkField>
            <WorkField label="Term (months)"><WorkInput value={termMonths} onChange={(e) => setTermMonths(e.target.value)} placeholder="Term (months)" className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 w-28" /></WorkField>
            <WorkButton type="submit" onClick={addNewScenario} disabled={busy || !salePrice.trim()} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">Add Scenario</WorkButton>
          </div>
        </div>
      )}

      {section === "presentation" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Payment Presentation</div>
          {!selectedScenario ? (
            <div className="text-xs text-zinc-600">No scenario selected yet -- pick one on the Deal Structuring tab.</div>
          ) : (
            <div className="text-sm text-zinc-200 space-y-1">
              <div className="text-2xl font-semibold">{money(selectedScenario.estimated_monthly_payment)}<span className="text-xs text-zinc-500">/mo</span></div>
              <div>Sale price {money(selectedScenario.sale_price)} · Down {money(selectedScenario.down_payment)}</div>
              <div>Financed {money(selectedScenario.amount_financed)} · {selectedScenario.term_months} months · {selectedScenario.estimated_apr}% APR est.</div>
            </div>
          )}
        </div>
      )}

      {section === "packaging" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Deal Packaging — Ready for F&I</div>
          <div className="text-xs text-zinc-300 space-y-1">
            <div>{deal.customer?.name || "—"} · {deal.vehicle?.description || "—"}</div>
            <div>Status: <span className="text-zinc-200">{deal.status}</span> · Financing: <span className="text-zinc-200">{deal.financing_status}</span></div>
            {selectedScenario ? (
              <div>Selected scenario: {money(selectedScenario.sale_price)} · {money(selectedScenario.estimated_monthly_payment)}/mo</div>
            ) : (
              <div className="text-amber-400">No scenario selected yet -- desking isn&rsquo;t complete.</div>
            )}
            <div>Trade appraisal: {deal.trade_in ? (deal.trade_in.approved ? "approved" : "pending approval") : "none"}</div>
          </div>
        </div>
      )}

      {section === "transfer" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Customer Transfer — Sales to F&amp;I</div>
          <div className="text-xs text-zinc-300 mb-2">
            Financing type: <span className="text-zinc-200">{deal.financing_type || "not chosen yet"}</span>
          </div>
          {!deal.financing_type && (
            <WorkButton type="submit" onClick={() => withBusy(() => chooseInHouseFinancing(dealId), "Financing set to in-house.")} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
              Start In-House Financing
            </WorkButton>
          )}
        </div>
      )}

      {section === "product_presentation" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Product Presentation</div>
          {deal.financing_terms ? (
            <div className="text-xs text-zinc-300 space-y-1">
              <div>{deal.financing_terms.apr}% APR · {deal.financing_terms.term_months} months</div>
              <div>Financed {money(deal.financing_terms.amount_financed)} · {money(deal.financing_terms.monthly_payment)}/mo</div>
            </div>
          ) : (
            <div className="text-xs text-zinc-600">No financing terms locked in yet.</div>
          )}
          <div className="text-xs text-zinc-600 mt-2">
            F&amp;I product add-ons (warranty, GAP, etc.) aren&rsquo;t tracked as their own data model yet.
          </div>
        </div>
      )}

      {section === "lender_submission" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Lender Submission</div>
          <div className="text-xs text-zinc-300 mb-2">Status: <span className="text-zinc-200">{deal.financing_status}</span> {deal.lender_id ? `· ${deal.lender_id}` : ""}</div>

          {deal.financing_status === "not_started" && (
            <div className="flex flex-wrap gap-2 items-center">
              <WorkField label="Lender"><WorkSelect value={lenderId} onChange={(e) => setLenderId(e.target.value)} className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200">
                <option value="">Select a lender…</option>
                {lenders.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
              </WorkSelect></WorkField>
              <WorkButton type="submit" onClick={() => withBusy(() => submitToLender(dealId, lenderId), "Submitted to lender.")} disabled={busy || !lenderId} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
                Submit
              </WorkButton>
            </div>
          )}

          {deal.financing_status === "submitted" && (
            <div className="flex flex-wrap gap-2 items-center">
              <WorkField label="Notes (optional)"><WorkInput value={decisionNotes} onChange={(e) => setDecisionNotes(e.target.value)} placeholder="Notes (optional)" className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 flex-1 min-w-[140px]" /></WorkField>
              <WorkButton type="submit" onClick={() => withBusy(() => recordLenderDecision(dealId, "approved", null, decisionNotes || null), "Lender approved.")} disabled={busy} className="text-xs px-2 py-1 rounded bg-emerald-900/50 border border-emerald-800 text-emerald-200">Approved</WorkButton>
              <WorkButton type="submit" variant="danger" onClick={() => withBusy(() => recordLenderDecision(dealId, "declined", null, decisionNotes || null), "Lender declined.")} disabled={busy} className="text-xs px-2 py-1 rounded bg-red-950/50 border border-red-900 text-red-200">Declined</WorkButton>
              <WorkButton type="submit" onClick={() => withBusy(() => recordLenderDecision(dealId, "countered", null, decisionNotes || null), "Lender countered.")} disabled={busy} className="text-xs px-2 py-1 rounded bg-amber-950/50 border border-amber-900 text-amber-200">Countered</WorkButton>
            </div>
          )}

          {deal.financing_status === "countered" && (
            <WorkButton type="submit" onClick={() => withBusy(() => acceptCounteredTerms(dealId), "Countered terms accepted.")} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
              Accept Countered Terms
            </WorkButton>
          )}
        </div>
      )}

      {section === "contract_readiness" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">Contract Readiness</div>
          {deal.contract ? (
            <div className="text-xs text-zinc-300 space-y-1">
              <div>{deal.contract.customer_name} · {deal.contract.vehicle_description}</div>
              <div>{money(deal.contract.sale_price)} · {money(deal.contract.monthly_payment)}/mo · {deal.contract.apr}% APR</div>
              {deal.contract.disclosures.map((d, i) => <div key={i} className="text-xs text-zinc-500">• {d}</div>)}
            </div>
          ) : (
            <>
              <div className="text-xs text-zinc-600 mb-2">No contract generated yet.</div>
              <WorkButton type="submit" onClick={() => withBusy(() => generateContract(dealId), "Contract generated.")} disabled={busy || deal.financing_status !== "approved"} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
                Generate Contract
              </WorkButton>
              {deal.financing_status !== "approved" && <div className="text-xs text-zinc-600 mt-1">Financing must be approved first.</div>}
            </>
          )}
        </div>
      )}

      {section === "vehicle_prep" && (
        <Checklist
          title="Vehicle Preparation"
          fields={[
            { key: "detailed", label: "Detailed / cleaned" },
            { key: "fuel_filled", label: "Fuel filled" },
            { key: "accessories_installed", label: "Accessories installed" },
          ]}
          values={checklist.vehicle_prep || {}}
          busy={busy}
          onToggle={(k, v) => toggleChecklist("vehicle_prep", k, v)}
        />
      )}

      {section === "quality_control" && (
        <Checklist
          title="Delivery Quality Control"
          fields={[{ key: "passed", label: "Final QC inspection passed" }]}
          values={checklist.quality_control || {}}
          busy={busy}
          onToggle={(k, v) => toggleChecklist("quality_control", k, v)}
        />
      )}

      {section === "tech_setup" && (
        <Checklist
          title="Technology Setup"
          fields={[
            { key: "bluetooth_paired", label: "Bluetooth paired" },
            { key: "app_configured", label: "Manufacturer app configured" },
            { key: "features_walkthrough", label: "Features walkthrough completed" },
          ]}
          values={checklist.tech_setup || {}}
          busy={busy}
          onToggle={(k, v) => toggleChecklist("tech_setup", k, v)}
        />
      )}

      {section === "documentation" && (
        <Checklist
          title="Delivery Documentation"
          fields={[
            { key: "title_signed", label: "Title signed" },
            { key: "warranty_docs_provided", label: "Warranty docs provided" },
            { key: "registration_submitted", label: "Registration submitted" },
          ]}
          values={checklist.documentation || {}}
          busy={busy}
          onToggle={(k, v) => toggleChecklist("documentation", k, v)}
        />
      )}

      {section === "csi" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-2">CSI &amp; Review Trigger</div>
          {checklist.csi?.review_requested ? (
            <div className="text-xs text-emerald-400">
              Flagged for review outreach{typeof checklist.csi.review_requested_at === "string" ? ` on ${new Date(checklist.csi.review_requested_at as string).toLocaleString()}` : ""}.
            </div>
          ) : (
            <>
              <p className="text-xs text-zinc-600 mb-2">
                No automated review-request send exists in this codebase yet -- this flags the
                deal for manual review outreach rather than actually sending anything.
              </p>
              <WorkButton type="submit" onClick={() => toggleChecklist("csi", "review_requested", true)} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-50">
                Flag for Review Outreach
              </WorkButton>
            </>
          )}
        </div>
      )}
    </div>
  );
}
