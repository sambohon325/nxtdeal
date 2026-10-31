"use client";
import { WorkInput, WorkButton } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// F&I Workflow (session 105 follow-up) -- rendered inside Sales' "F&I Workflow"
// workflow modal (core/workflow_catalog.py's sales.fi_products). The seventh of
// Sam's ~10 "completely missing" dealership workflows; follows the same bespoke
// per-tab-section pattern session 100-104 established (Up System/BDC/Demo Drive/
// Credit App/eSignature) -- a `section` prop matching this workflow's 5 real tabs
// (Product Menu, Customer Selections, Deal F&I Summary, Product Penetration,
// Compliance & Disclosures).
//
// This is the actual F&I menu -- presenting protection products, tracking
// accept/decline, and real cross-deal product penetration -- deliberately
// distinct from the eSignature workflow (contract signing) and the "F&I Handoff"
// tab under sales.fi_turnover (the process handoff from sales to F&I).
import { useEffect, useState } from "react";
import {
  getFIProductsDashboard,
  getFIMenu,
  presentFIProducts,
  updateFIProductPricing,
  decideFIProduct,
  getProductPenetrationStats,
  listDealsNeedingFIMenu,
  recommendFIProducts,
  type FIProductsDashboard,
  type FIMenu,
  type DealBrief,
  type ProductPenetrationStats,
  type FIRecommendationResult,
} from "@/lib/fiProducts";
import { listSignatureRequests, type SignatureRequest } from "@/lib/esignature";

export type FIProductsSection = "menu" | "selections" | "summary" | "penetration" | "compliance";

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function DealLabel({ deal }: { deal: DealBrief }) {
  if (!deal) return null;
  return (
    <span>
      {deal.customer?.name || deal.id} · {deal.vehicle?.description || deal.id} · {deal.id}
    </span>
  );
}

export function FIProductsBoard({ section = "menu" }: { section?: FIProductsSection }) {
  const [dashboard, setDashboard] = useState<FIProductsDashboard | null>(null);
  const [queue, setQueue] = useState<DealBrief[]>([]);
  const [penetration, setPenetration] = useState<ProductPenetrationStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [selectedDealId, setSelectedDealId] = useState<string>("");
  const [menu, setMenu] = useState<FIMenu | null>(null);

  const [dealIdInput, setDealIdInput] = useState("");
  const [selectedProductKeys, setSelectedProductKeys] = useState<string[]>([]);
  const [recs, setRecs] = useState<FIRecommendationResult | null>(null);

  async function handleRecommend() {
    if (!selectedDealId) return;
    setBusy(true);
    try {
      const r = await recommendFIProducts(selectedDealId);
      setRecs(r);
      setSelectedProductKeys(r.recommended_keys);  // pre-check the recommended ones
      setMessage(r.recommended_keys.length ? `Recommended ${r.recommended_keys.length} product(s) for this deal.` : "No strong recommendations for this deal.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't get recommendations.");
    } finally {
      setBusy(false);
    }
  }

  const [signatureStatus, setSignatureStatus] = useState<SignatureRequest[] | null>(null);
  const [signatureLoading, setSignatureLoading] = useState(false);

  function refreshDashboard() {
    setLoading(true);
    Promise.all([getFIProductsDashboard(), listDealsNeedingFIMenu(25), getProductPenetrationStats()])
      .then(([d, q, p]) => {
        setDashboard(d);
        setQueue(q);
        setPenetration(p);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load F&I data."))
      .finally(() => setLoading(false));
  }

  useEffect(refreshDashboard, []);

  function loadMenu(dealId: string) {
    if (!dealId.trim()) return;
    setBusy(true);
    getFIMenu(dealId.trim())
      .then((m) => {
        setMenu(m);
        setSelectedDealId(dealId.trim());
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load this deal's F&I menu."))
      .finally(() => setBusy(false));
  }

  useEffect(() => {
    if (section === "compliance" && selectedDealId) {
      setSignatureLoading(true);
      listSignatureRequests({ linked_deal_id: selectedDealId })
        .then((reqs) => setSignatureStatus(reqs))
        .catch(() => setSignatureStatus(null))
        .finally(() => setSignatureLoading(false));
    }
  }, [section, selectedDealId]);

  function toggleProductKey(key: string) {
    setSelectedProductKeys((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  }

  async function handlePresent() {
    if (!selectedDealId || selectedProductKeys.length === 0) return;
    setBusy(true);
    try {
      const m = await presentFIProducts(selectedDealId, selectedProductKeys);
      setMenu(m);
      setSelectedProductKeys([]);
      setMessage(`Presented ${selectedProductKeys.length} product(s).`);
      refreshDashboard();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to present products.");
    } finally {
      setBusy(false);
    }
  }

  async function handlePricing(productKey: string, field: "cost" | "price", value: string) {
    const num = parseFloat(value);
    if (isNaN(num)) return;
    setBusy(true);
    try {
      const m = await updateFIProductPricing(selectedDealId, productKey, { [field]: num });
      setMenu(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update pricing.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDecide(productKey: string, decision: "accepted" | "declined") {
    let reason: string | undefined;
    if (decision === "declined") {
      reason = window.prompt("Decline reason (optional):") || undefined;
    }
    setBusy(true);
    try {
      const m = await decideFIProduct(selectedDealId, productKey, decision, reason);
      setMenu(m);
      setMessage(`Marked ${productKey} as ${decision}.`);
      refreshDashboard();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to record decision.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="mb-5 text-xs text-zinc-600">Loading…</div>;
  }

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}

      {section === "menu" && (
        <>
          <div className="grid grid-cols-4 gap-2 mb-3">
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{queue.length}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Deals Needing a Menu</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{dashboard?.catalog.length ?? 6}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Catalog Products</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">
                {penetration?.products_per_deal_avg ?? "—"}
              </div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Products / Deal (Avg)</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-emerald-300">{money(penetration?.total_accepted_gross)}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Total F&I Gross</div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 mb-3">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Open a Deal's F&I Menu</div>
            <div className="flex items-center gap-2">
              <WorkField label="Deal ID (DEAL-…)"><WorkInput
                value={dealIdInput}
                onChange={(e) => setDealIdInput(e.target.value)}
                placeholder="Deal ID (DEAL-…)"
                className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
              /></WorkField>
              <WorkButton type="submit"
                onClick={() => loadMenu(dealIdInput)}
                disabled={busy || !dealIdInput.trim()}
                className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
              >
                Open
              </WorkButton>
            </div>

            {selectedDealId && (
              <div className="mt-3">
                <div className="text-xs text-zinc-400 mb-1.5">Present products on {selectedDealId}:</div>
                <div className="grid grid-cols-2 gap-1.5 mb-2">
                  {(dashboard?.catalog ?? []).map((p) => (
                    <label key={p.key} className="flex items-center gap-1.5 text-xs text-zinc-300">
                      <WorkInput
                        type="checkbox"
                        checked={selectedProductKeys.includes(p.key)}
                        onChange={() => toggleProductKey(p.key)}
                      />
                      {p.name}
                      <span className="text-zinc-600">({money(p.default_price)})</span>
                    </label>
                  ))}
                </div>
                <div className="flex gap-2">
                  <WorkButton type="submit"
                    onClick={handlePresent}
                    disabled={busy || selectedProductKeys.length === 0}
                    className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
                  >
                    Present Selected Products
                  </WorkButton>
                  <WorkButton type="submit"
                    onClick={handleRecommend}
                    disabled={busy}
                    className="bg-brand-teal text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
                    title="Personalized recommendation for this deal"
                  >
                    Recommend for this deal
                  </WorkButton>
                </div>

                {recs && (
                  <div className="mt-2 space-y-1">
                    {recs.recommendations.map((r) => (
                      <div
                        key={r.product_key}
                        className={
                          "flex items-start gap-2 text-xs px-2 py-1 rounded " +
                          (r.recommended ? "bg-brand-teal/10" : "bg-zinc-900")
                        }
                      >
                        <span className={"w-8 text-center rounded font-bold " + (r.recommended ? "text-brand-teal" : "text-zinc-500")}>{r.fit_score}</span>
                        <div className="min-w-0">
                          <div className="text-zinc-200">
                            {r.name} {r.already_on_menu && <span className="text-zinc-600">(on menu)</span>}
                          </div>
                          {r.reasons.length > 0 && <div className="text-zinc-500">{r.reasons.join("; ")}</div>}
                        </div>
                      </div>
                    ))}
                    <div className="text-xs text-zinc-600">{recs.basis}</div>
                  </div>
                )}
              </div>
            )}
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Deals Needing a Menu ({queue.length})</div>
            {queue.length === 0 ? (
              <div className="text-xs text-zinc-600">Every financing/contract-stage deal already has an F&I menu on file.</div>
            ) : (
              <div className="space-y-1.5">
                {queue.map((d) => (
                  <WorkButton type="submit"
                    key={d.id}
                    onClick={() => loadMenu(d.id)}
                    className="w-full text-left text-xs px-2 py-1.5 rounded border border-zinc-800 text-zinc-300"
                  >
                    <DealLabel deal={d} /> <span className="text-zinc-600">({d.status})</span>
                  </WorkButton>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {section === "selections" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Customer Selections</div>
          {!menu ? (
            <div className="text-xs text-zinc-600">Open a deal from the Product Menu tab first.</div>
          ) : menu.products.length === 0 ? (
            <div className="text-xs text-zinc-600">No products presented on {menu.deal_id} yet.</div>
          ) : (
            <div className="space-y-2">
              {menu.products.map((p) => (
                <div key={p.product_key} className="p-2.5 rounded-lg border border-zinc-800">
                  <div className="flex items-center justify-between gap-2 mb-1">
                    <span className="text-xs text-zinc-200">{p.name}</span>
                    <span
                      className={`text-xs uppercase tracking-wide ${
                        p.status === "accepted" ? "text-emerald-300" : p.status === "declined" ? "text-red-300" : "text-amber-300"
                      }`}
                    >
                      {p.status}
                    </span>
                  </div>
                  {p.status === "presented" ? (
                    <div className="flex flex-wrap items-center gap-2">
                      <label className="text-xs text-zinc-500">
                        Cost{" "}
                        <WorkInput
                          defaultValue={p.cost}
                          onBlur={(e) => handlePricing(p.product_key, "cost", e.target.value)}
                          className="w-20 bg-zinc-950 border border-zinc-800 rounded px-1.5 py-0.5 text-xs text-zinc-200"
                        />
                      </label>
                      <label className="text-xs text-zinc-500">
                        Price{" "}
                        <WorkInput
                          defaultValue={p.price}
                          onBlur={(e) => handlePricing(p.product_key, "price", e.target.value)}
                          className="w-20 bg-zinc-950 border border-zinc-800 rounded px-1.5 py-0.5 text-xs text-zinc-200"
                        />
                      </label>
                      <WorkButton type="submit"
                        onClick={() => handleDecide(p.product_key, "accepted")}
                        disabled={busy}
                        className="bg-emerald-900/50 border border-emerald-800 text-emerald-200 rounded px-2.5 py-1 text-xs disabled:opacity-40"
                      >
                        Accept
                      </WorkButton>
                      <WorkButton type="submit" variant="danger"
                        onClick={() => handleDecide(p.product_key, "declined")}
                        disabled={busy}
                        className="bg-red-950/50 border border-red-900 text-red-300 rounded px-2.5 py-1 text-xs disabled:opacity-40"
                      >
                        Decline
                      </WorkButton>
                    </div>
                  ) : (
                    <div className="text-xs text-zinc-500">
                      {money(p.cost)} cost / {money(p.price)} price
                      {p.status === "declined" && p.declined_reason && ` · ${p.declined_reason}`}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {section === "summary" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Deal F&I Summary</div>
          {!menu ? (
            <div className="text-xs text-zinc-600">Open a deal from the Product Menu tab first.</div>
          ) : (
            <div className="grid grid-cols-3 gap-2">
              <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
                <div className="text-base font-semibold text-zinc-100">{menu.totals.presented}</div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide">Presented</div>
              </div>
              <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
                <div className="text-base font-semibold text-emerald-300">{menu.totals.accepted}</div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide">Accepted</div>
              </div>
              <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
                <div className="text-base font-semibold text-red-300">{menu.totals.declined}</div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide">Declined</div>
              </div>
              <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
                <div className="text-base font-semibold text-zinc-100">{money(menu.totals.total_price_accepted)}</div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide">Accepted Price</div>
              </div>
              <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
                <div className="text-base font-semibold text-zinc-100">{money(menu.totals.total_cost_accepted)}</div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide">Accepted Cost</div>
              </div>
              <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
                <div className="text-base font-semibold text-emerald-300">{money(menu.totals.total_gross_accepted)}</div>
                <div className="text-xs text-zinc-500 uppercase tracking-wide">F&I Gross</div>
              </div>
            </div>
          )}
        </div>
      )}

      {section === "penetration" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">
            Product Penetration ({penetration?.deals_with_fi_menu ?? 0} deals with an F&I menu on file)
          </div>
          <p className="text-xs text-zinc-600 mb-2">
            Computed only over deals that have actually been taken through the F&I menu -- a deal never presented
            products isn't counted as a decline.
          </p>
          {!penetration || penetration.by_product.length === 0 ? (
            <div className="text-xs text-zinc-600">No F&I menus have been presented on any deal yet.</div>
          ) : (
            <div className="space-y-1.5">
              {penetration.by_product.map((p) => (
                <div key={p.product_key} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <span className="text-zinc-200">{p.name}</span>
                  <span className="text-zinc-400">
                    {p.accepted}/{p.presented} presented · {p.penetration_pct !== null ? `${p.penetration_pct}%` : "—"} penetration ·{" "}
                    <span className="text-emerald-300">{money(p.total_gross)}</span>
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {section === "compliance" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Compliance & Disclosures</div>
          <p className="text-xs text-zinc-400 leading-relaxed mb-3">
            Financed protection products must be reflected in the deal's disclosed Amount Financed and APR (Reg Z /
            Truth in Lending) -- pricing changes made here before a decision flow into the deal the same way any
            other financed amount does. This tab is informational, not a substitute for state-required disclosure
            forms or legal advice.
          </p>
          {!selectedDealId ? (
            <div className="text-xs text-zinc-600">Open a deal from the Product Menu tab to see its signature status.</div>
          ) : signatureLoading ? (
            <div className="text-xs text-zinc-600">Checking signature status…</div>
          ) : (
            <div className="text-xs text-zinc-300">
              <div className="mb-1">Deal {selectedDealId}:</div>
              {!signatureStatus || signatureStatus.length === 0 ? (
                <div className="text-amber-300">No eSignature envelope has been created for this deal yet.</div>
              ) : signatureStatus.some((r) => r.status === "completed") ? (
                <div className="text-emerald-300">Contract fully signed -- an eSignature envelope on this deal is complete.</div>
              ) : (
                <div className="text-amber-300">
                  An eSignature envelope exists for this deal but isn't complete yet (
                  {signatureStatus[0]?.status}).
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
