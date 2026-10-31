"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Finance's "Repossessions" item -- the fourth slice of Sam's "Retail Automotive
// Lending Platform" expansion (2026-07-17), the direct continuation of Collections'
// own "repossession_referral" collection stage. A real Referral Queue, a real case
// lifecycle (referred -> assigned -> located -> recovered -> stored -> disposed,
// with redeemed/cancelled as terminal off-ramps), a real Deficiency Balance
// calculation (Sam's own "Recovery" stage), and a customer redemption path.
// Disposition/redemption cascade real loan_status updates back onto Portfolio.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { CommsQuickActions } from "@/components/CommsQuickActions";
import {
  getReferralQueue,
  getRepossessionsDashboard,
  listCases,
  createCase,
  getCase,
  assignAgent,
  recordLocation,
  recordRecovery,
  recordStorage,
  recordDisposition,
  redeemCase,
  cancelCase,
  CASE_STAGES,
  STAGE_LABELS,
  DISPOSITION_TYPES,
  type ReferralRow,
  type CaseBrief,
  type CaseDetail,
  type RepossessionsDashboard,
  type DispositionType,
} from "@/lib/repossessions";
import { LoanDetailModal } from "@/components/PortfolioBoard";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

export function RepossessionsBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<RepossessionsDashboard | null>(null);
  const [referrals, setReferrals] = useState<ReferralRow[]>([]);
  const [cases, setCases] = useState<CaseBrief[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedCase, setSelectedCase] = useState<string | null>(null);
  const [fullLoanId, setFullLoanId] = useState<string | null>(null);
  const [creatingLoanId, setCreatingLoanId] = useState<string | null>(null);

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  function refresh() {
    setLoading(true);
    Promise.all([getRepossessionsDashboard(), getReferralQueue(), listCases()])
      .then(([d, r, c]) => {
        setDashboard(d);
        setReferrals(r.loans);
        setCases(c.cases);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleOpenCase(loanId: string) {
    setCreatingLoanId(loanId);
    try {
      const result = await createCase(loanId, "Referred from repossession queue");
      refresh();
      setSelectedCase(result.id);
    } catch {
      // surfaced implicitly via refresh
    } finally {
      setCreatingLoanId(null);
    }
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Referral Queue" value={String(dashboard?.referral_queue_count ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Open Cases" value={String(dashboard?.open_cases ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Disposed / Redeemed" value={`${dashboard?.disposed_count ?? 0} / ${dashboard?.redeemed_count ?? 0}`} color={RIBBON[2]} />
        <Kpi theme={theme} label="Total Deficiency Outstanding" value={money(dashboard?.total_deficiency_outstanding)} color={RIBBON[3]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800">
        <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
          The Referral Queue is real loans already in Collections&apos; own &quot;Repossession Referral&quot; stage with no open case yet. Deficiency Balance is real math over the loan&apos;s real-or-schedule-implied balance plus real recorded storage/transport costs, minus real recorded sale proceeds.
        </span>
      </div>

      <div className="flex-1 p-4 grid grid-cols-2 gap-3 overflow-y-auto">
        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Referral Queue</div>
          <div className="space-y-1 max-h-[28rem] overflow-y-auto">
            {loading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : referrals.length === 0 ? (
              <div className="text-xs text-zinc-500">No loans currently in the referral queue.</div>
            ) : (
              referrals.map((row) => (
                <div key={row.loan_id} className="flex items-center justify-between text-xs py-1 border-b border-zinc-800/50">
                  <span className="flex flex-col">
                    <span className="font-medium">{row.loan_id} · {row.customer_name || "—"}</span>
                    <span className="text-zinc-500">{row.vehicle} · {money(row.current_balance)}</span>
                  </span>
                  <WorkButton type="submit" variant="primary"
                    disabled={creatingLoanId === row.loan_id}
                    onClick={() => handleOpenCase(row.loan_id)}
                    className="text-xs px-2 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                  >
                    {creatingLoanId === row.loan_id ? "Opening…" : "Open Case"}
                  </WorkButton>
                </div>
              ))
            )}
          </div>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">All Cases</div>
          <div className="space-y-1 max-h-[28rem] overflow-y-auto">
            {loading ? (
              <div className="text-xs text-zinc-500">Loading…</div>
            ) : cases.length === 0 ? (
              <div className="text-xs text-zinc-500">No repossession cases yet.</div>
            ) : (
              cases.map((c) => (
                <WorkButton type="submit"
                  key={c.id}
                  onClick={() => setSelectedCase(c.id)}
                  className="w-full text-left flex items-center justify-between text-xs hover:text-brand-blue transition py-1 border-b border-zinc-800/50"
                >
                  <span>{c.id} · {c.loan_id} · {c.agent_name || "unassigned"}</span>
                  <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">{c.stage_label}</span>
                </WorkButton>
              ))
            )}
          </div>
        </div>
      </div>

      {selectedCase && (
        <CaseDetailModal
          theme={theme}
          caseId={selectedCase}
          onClose={() => setSelectedCase(null)}
          onChanged={refresh}
          onViewFullLoan={(id) => setFullLoanId(id)}
        />
      )}

      {fullLoanId && (
        <LoanDetailModal theme={theme} loanId={fullLoanId} onClose={() => setFullLoanId(null)} onChanged={refresh} />
      )}
    </div>
  );
}

function CaseDetailModal({
  theme,
  caseId,
  onClose,
  onChanged,
  onViewFullLoan,
}: {
  theme: Theme;
  caseId: string;
  onClose: () => void;
  onChanged: () => void;
  onViewFullLoan: (id: string) => void;
}) {
  const [detail, setDetail] = useState<CaseDetail | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);

  const [agentName, setAgentName] = useState("");
  const [agentAgency, setAgentAgency] = useState("");
  const [agentPhone, setAgentPhone] = useState("");
  const [location, setLocation] = useState("");
  const [condition, setCondition] = useState("");
  const [odometer, setOdometer] = useState("");
  const [storageFacility, setStorageFacility] = useState("");
  const [dailyRate, setDailyRate] = useState("");
  const [transportCost, setTransportCost] = useState("");
  const [dispositionType, setDispositionType] = useState<DispositionType>("auction_sale");
  const [salePrice, setSalePrice] = useState("");
  const [buyer, setBuyer] = useState("");
  const [redemptionAmount, setRedemptionAmount] = useState("");
  const [cancelReason, setCancelReason] = useState("");

  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function load() {
    setLoading(true);
    setError(null);
    getCase(caseId)
      .then(setDetail)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(load, [caseId]);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      load();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const stage = detail?.stage;
  const isTerminal = stage === "disposed" || stage === "redeemed" || stage === "cancelled";

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className={tc(theme, "w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-800 bg-brand-ink text-white p-5", "w-full max-w-3xl max-h-[85vh] overflow-y-auto rounded-lg border border-zinc-200 bg-white text-black p-5")}>
        <div className="flex items-center justify-between mb-3">
          <div>
            <div className="text-sm font-semibold">Repossession Case — {caseId}</div>
            {detail && <div className="text-xs text-zinc-500">{detail.loan_id} · {STAGE_LABELS[detail.stage]}</div>}
          </div>
          <div className="flex items-center gap-2">
            {detail && (
              <WorkButton type="submit" onClick={() => onViewFullLoan(detail.loan_id)} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">
                View Full Loan →
              </WorkButton>
            )}
            <WorkButton type="submit" onClick={onClose} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">
              Close
            </WorkButton>
          </div>
        </div>

        {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
        {loading ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : !detail ? (
          <div className="text-xs text-zinc-500">Unable to load case.</div>
        ) : (
          <div className="space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Customer</div>
                <div className="text-xs">{(detail.customer?.name as string) || "—"}</div>
                <div className="text-xs text-zinc-500">{(detail.customer?.phone as string) || ""} {(detail.customer?.email as string) || ""}</div>
                {(detail.customer?.phone as string) && (
                  <div className="mt-1.5">
                    <CommsQuickActions
                      customerId={(detail.customer?.id as string) || undefined}
                      phone={detail.customer?.phone as string}
                      name={detail.customer?.name as string}
                      size="xs"
                    />
                  </div>
                )}
              </div>
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Vehicle</div>
                <div className="text-xs">{detail.vehicle ? `${detail.vehicle.year ?? ""} ${detail.vehicle.make ?? ""} ${detail.vehicle.model ?? ""}`.trim() : "—"}</div>
                <div className="text-xs text-zinc-500">VIN: {(detail.vehicle?.vin as string) || "—"}</div>
              </div>
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Current Balance</div>
              <div className="text-xl font-semibold">{money(detail.current_balance)}</div>
              <div className="text-xs text-zinc-500">basis: {detail.current_balance_basis}</div>
            </div>

            {/* Stage progression strip */}
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Case Stage</div>
              <div className="flex items-center gap-1 flex-wrap">
                {CASE_STAGES.map((s, i) => (
                  <span key={s} className="flex items-center gap-1">
                    <span className={`text-xs px-2 py-1 rounded ${detail.stage === s ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-400"}`}>
                      {STAGE_LABELS[s]}
                    </span>
                    {i < CASE_STAGES.length - 1 && <span className="text-zinc-600">→</span>}
                  </span>
                ))}
                {(detail.stage === "redeemed" || detail.stage === "cancelled") && (
                  <span className="text-xs px-2 py-1 rounded bg-amber-950/40 text-amber-300 ml-1">{STAGE_LABELS[detail.stage]}</span>
                )}
              </div>
              {detail.stage_history.length > 0 && (
                <div className="mt-2 space-y-0.5 max-h-24 overflow-y-auto">
                  {detail.stage_history.slice().reverse().map((h, i) => (
                    <div key={i} className="text-xs text-zinc-500">
                      {STAGE_LABELS[h.stage]} · {h.by} · {h.reason || "no reason given"} · {h.at.slice(0, 16).replace("T", " ")}
                    </div>
                  ))}
                </div>
              )}
            </div>

            {/* Stage-appropriate action forms */}
            {stage === "referred" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Assign Recovery Agent</div>
                <div className="grid grid-cols-3 gap-2 mb-2">
                  <WorkField label="Agent name"><WorkInput value={agentName} onChange={(e) => setAgentName(e.target.value)} placeholder="Agent name…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkField label="Agency (optional)"><WorkInput value={agentAgency} onChange={(e) => setAgentAgency(e.target.value)} placeholder="Agency (optional)…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkField label="Phone (optional)"><WorkInput value={agentPhone} onChange={(e) => setAgentPhone(e.target.value)} placeholder="Phone (optional)…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                </div>
                <WorkButton type="submit" variant="primary"
                  disabled={busy || !agentName.trim()}
                  onClick={() => run(() => assignAgent(caseId, agentName, agentAgency, agentPhone))}
                  className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                >
                  Assign Agent
                </WorkButton>
              </div>
            )}

            {stage === "assigned" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Record Location</div>
                <div className="flex items-center gap-2">
                  <WorkField label="Location (manual, no GPS device pull)"><WorkInput value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Location (manual, no GPS device pull)…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkButton type="submit" variant="primary"
                    disabled={busy || !location.trim()}
                    onClick={() => run(() => recordLocation(caseId, location))}
                    className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                  >
                    Record Location
                  </WorkButton>
                </div>
              </div>
            )}

            {stage === "located" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Record Recovery</div>
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <WorkField label="Condition"><WorkInput value={condition} onChange={(e) => setCondition(e.target.value)} placeholder="Condition (e.g. fair)…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkField label="Odometer"><WorkInput value={odometer} onChange={(e) => setOdometer(e.target.value)} placeholder="Odometer…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                </div>
                <WorkButton type="submit" variant="primary"
                  disabled={busy}
                  onClick={() => run(() => recordRecovery(caseId, undefined, condition, odometer ? parseInt(odometer, 10) : undefined))}
                  className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                >
                  Record Recovery
                </WorkButton>
              </div>
            )}

            {stage === "recovered" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Record Storage</div>
                <div className="grid grid-cols-3 gap-2 mb-2">
                  <WorkField label="Storage facility"><WorkInput value={storageFacility} onChange={(e) => setStorageFacility(e.target.value)} placeholder="Storage facility…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkField label="Daily rate $"><WorkInput value={dailyRate} onChange={(e) => setDailyRate(e.target.value)} placeholder="Daily rate $…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkField label="Transport cost $"><WorkInput value={transportCost} onChange={(e) => setTransportCost(e.target.value)} placeholder="Transport cost $…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                </div>
                <WorkButton type="submit" variant="primary"
                  disabled={busy || !storageFacility.trim()}
                  onClick={() => run(() => recordStorage(caseId, storageFacility, undefined, parseFloat(dailyRate) || 0, parseFloat(transportCost) || 0))}
                  className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                >
                  Record Storage
                </WorkButton>
              </div>
            )}

            {stage === "stored" && detail.deficiency && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Deficiency Balance (pre-sale)</div>
                <div className="text-xl font-semibold">{money(detail.deficiency.deficiency_balance)}</div>
                <div className="text-xs text-zinc-500 mt-1">
                  Balance {money(detail.deficiency.outstanding_balance)} + storage {money(detail.deficiency.storage_fees_accrued)} + transport {money(detail.deficiency.transport_cost)} − sale proceeds {money(detail.deficiency.sale_price)}
                </div>
              </div>
            )}

            {stage === "stored" && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Record Disposition</div>
                <div className="grid grid-cols-3 gap-2 mb-2">
                  <WorkField label="Disposition Type"><WorkSelect value={dispositionType} onChange={(e) => setDispositionType(e.target.value as DispositionType)} className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}>
                    {DISPOSITION_TYPES.map((d) => <option key={d} value={d}>{d.replace("_", " ")}</option>)}
                  </WorkSelect></WorkField>
                  <WorkField label="Sale price $"><WorkInput value={salePrice} onChange={(e) => setSalePrice(e.target.value)} placeholder="Sale price $…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkField label="Buyer (optional)"><WorkInput value={buyer} onChange={(e) => setBuyer(e.target.value)} placeholder="Buyer (optional)…" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                </div>
                <WorkButton type="submit" variant="primary"
                  disabled={busy || !salePrice}
                  onClick={() => run(() => recordDisposition(caseId, dispositionType, parseFloat(salePrice) || 0, undefined, buyer))}
                  className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                >
                  Record Disposition
                </WorkButton>
              </div>
            )}

            {stage === "disposed" && detail.deficiency && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Final Deficiency Balance</div>
                <div className={`text-xl font-semibold ${detail.deficiency.deficiency_balance > 0 ? "text-red-400" : "text-green-400"}`}>
                  {money(detail.deficiency.deficiency_balance)}
                </div>
                <div className="text-xs text-zinc-500 mt-1">
                  {detail.deficiency.deficiency_balance > 0 ? "Customer still owes this amount." : "Real surplus owed back to the customer."}
                </div>
                {detail.disposition && (
                  <div className="text-xs text-zinc-500 mt-2">
                    Sold via {detail.disposition.disposition_type.replace("_", " ")} to {detail.disposition.buyer || "—"} on {detail.disposition.sale_date}
                  </div>
                )}
              </div>
            )}

            {!isTerminal && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Redemption — Customer Pays Off / Reinstates</div>
                <div className="flex items-center gap-2">
                  <WorkField label="Redemption amount $"><WorkInput value={redemptionAmount} onChange={(e) => setRedemptionAmount(e.target.value)} placeholder="Redemption amount $…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkButton type="submit"
                    disabled={busy || !redemptionAmount}
                    onClick={() => run(() => redeemCase(caseId, parseFloat(redemptionAmount) || 0, "Customer redeemed"))}
                    className="text-xs px-2.5 py-1.5 rounded bg-green-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                  >
                    Redeem — Reactivate Loan
                  </WorkButton>
                </div>
              </div>
            )}

            {!isTerminal && (
              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Cancel Case</div>
                <div className="flex items-center gap-2">
                  <WorkField label="Reason"><WorkInput value={cancelReason} onChange={(e) => setCancelReason(e.target.value)} placeholder="Reason…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                  <WorkButton type="submit"
                    disabled={busy}
                    onClick={() => run(() => cancelCase(caseId, cancelReason))}
                    className="text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50"
                  >
                    Cancel Case
                  </WorkButton>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </WorkOverlay>
  );
}
