"use client";
import { WorkButton, WorkSelect, WorkInput , WorkStat, WorkOverlay} from "./WorkspaceUi";
import {RecordTable} from "./RecordTable";
import { WorkField } from "./WorkField";

// Finance's "Portfolio" item -- Loan Management, the first slice of Sam's "Retail
// Automotive Lending Platform" expansion (2026-07-17). Sam's own framing: Finance
// shouldn't stop at Funded/Delivered -- Funded is the START of a loan's real life
// (Lead -> Deal -> Credit -> Approval -> Contract -> Funding -> Loan Servicing ->
// Collections -> Repossession -> Recovery -> Payoff). This board is the master Loan
// record everything else (Payments, Collections, GPS & Devices, Repossessions -- all
// separately scoped future slices) will attach to.
//
// The amortization schedule/balance/terms-remaining are real math over each loan's
// real contract terms. The delinquency-bucket payment status is SIMULATED -- no real
// payment ledger exists yet (that's the next slice, Payments) -- every simulated
// figure carries its own visible "Simulated" badge + disclaimer, same convention as
// PricingDeskBoard.tsx/AcquisitionsBoard.tsx.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { CommsQuickActions } from "@/components/CommsQuickActions";
import {
  getPortfolioDashboard,
  getLoanDetail,
  setLoanStatus,
  type PortfolioDashboard,
  type LoanDetail,
  type DelinquencyBucket,
  type LoanStatus,
} from "@/lib/loanServicing";
import {
  recordPayment,
  listPaymentsForLoan,
  listAutoDrafts,
  createAutoDraft,
  setAutoDraftStatus,
  listPromisesToPay,
  createPromiseToPay,
  recordExtension,
  recordDeferral,
  requestPayoff,
  generatePaymentPortalLink,
  getPaymentPortalLinkStatus,
  revokePaymentPortalLink,
  PAYMENT_METHODS,
  type Payment,
  type AutoDraft,
  type PromiseToPay,
  type PaymentMethod,
} from "@/lib/payments";
import { Customer360Panel } from "@/components/Customer360Panel";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const BUCKET_ORDER: DelinquencyBucket[] = ["current", "30_day", "60_day", "90_day", "repossessed", "charged_off"];

const BUCKET_LABEL: Record<DelinquencyBucket, string> = {
  current: "Current",
  "30_day": "30 Day",
  "60_day": "60 Day",
  "90_day": "90 Day",
  repossessed: "Repossessed",
  charged_off: "Charged Off",
};

const BUCKET_TONE: Record<DelinquencyBucket, string> = {
  current: "bg-green-950/40 text-green-300",
  "30_day": "bg-amber-950/40 text-amber-300",
  "60_day": "bg-orange-950/40 text-orange-300",
  "90_day": "bg-red-950/40 text-red-300",
  repossessed: "bg-red-950/60 text-red-200",
  charged_off: "bg-zinc-800 text-zinc-400",
};

const LOAN_STATUS_OPTIONS: LoanStatus[] = ["active", "paid_off", "repossessed", "charged_off"];

function money(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function SimulatedBadge({ disclaimer, basis }: { disclaimer: string; basis?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <WorkButton type="submit"
        onClick={() => setOpen((o) => !o)}
        className="text-xs px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 font-brand uppercase tracking-wide cursor-help"
        title={disclaimer}
      >
        {basis === "real_payment_ledger" ? "Recorded payments" : "Simulated"}
      </WorkButton>
      {open && (
        <div className="absolute z-10 top-full left-0 mt-1 w-72 text-xs leading-snug p-2 rounded-lg bg-zinc-950 border border-amber-900/50 text-amber-200 shadow-xl">
          {disclaimer}
        </div>
      )}
    </span>
  );
}

export function LoanDetailModal({ theme, loanId, onClose, onChanged }: { theme: Theme; loanId: string; onClose: () => void; onChanged: () => void }) {
  const [data, setData] = useState<LoanDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"borrower" | "vehicle" | "contract" | "payments" | "timeline">("borrower");
  const [statusBusy, setStatusBusy] = useState(false);
  const [newStatus, setNewStatus] = useState<LoanStatus>("active");
  const [statusReason, setStatusReason] = useState("");
  const [full360Open, setFull360Open] = useState(false);

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function refresh() {
    if (!data) setLoading(true);
    setError(null);
    getLoanDetail(loanId)
      .then((d) => {
        setData(d);
        setNewStatus(d.loan_status);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [loanId]);

  async function handleSetStatus() {
    setStatusBusy(true);
    setError(null);
    try {
      await setLoanStatus(loanId, newStatus, statusReason);
      setStatusReason("");
      refresh();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setStatusBusy(false);
    }
  }

  if (loading || !data) {
    return (
      <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
        <div onClick={(e) => e.stopPropagation()} className={tc(theme, "rounded-xl border border-black/20 bg-brand-ink text-white p-5", "rounded-xl border border-zinc-200 bg-white text-black p-5")}>
          {loading ? <div className="text-sm text-zinc-500" role="status">Loading…</div> : <div role="alert"><p>{error || "Unable to load this record."}</p><WorkButton type="submit" onClick={refresh}>Try again</WorkButton></div>}
          <WorkButton type="submit" onClick={onClose}>Close record</WorkButton>
        </div>
      </WorkOverlay>
    );
  }

  const { borrower, vehicle, contract, payment_status, timeline, lender } = data;

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div onClick={(e) => e.stopPropagation()} className={tc(theme, "w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl border border-black/20 bg-brand-ink text-white p-5 space-y-3", "w-full max-w-3xl max-h-[90vh] overflow-y-auto rounded-xl border border-zinc-200 bg-white text-black p-5 space-y-3")}>
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-brand uppercase tracking-wide">
              {data.finance_number || data.loan_id} · {borrower.customer?.name || "Unknown Borrower"}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5 flex items-center gap-2">
              <span>{data.loan_id}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded ${BUCKET_TONE[payment_status.bucket]}`}>
                {BUCKET_LABEL[payment_status.bucket]}
              </span>
              <SimulatedBadge disclaimer={payment_status.disclaimer} basis={payment_status.basis} />
              <span>Status: {data.loan_status}</span>
            </div>
          </div>
          <WorkButton type="submit" onClick={onClose} className="text-xs text-zinc-500 hover:text-white transition">✕ Close</WorkButton>
        </div>

        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        <div className="flex items-center gap-1.5 text-xs">
          {(["borrower", "vehicle", "contract", "payments", "timeline"] as const).map((t) => (
            <WorkButton data-work-view aria-pressed={tab === t} type="submit"
              key={t}
              onClick={() => setTab(t)}
              className={`px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${
                tab === t ? "bg-brand-blue text-white" : tc(theme, "bg-zinc-800 text-zinc-400 hover:text-white", "bg-zinc-200 text-zinc-500 hover:text-black")
              }`}
            >
              {t}
            </WorkButton>
          ))}
        </div>

        {tab === "borrower" && (
          <div className="space-y-2">
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Borrower</div>
              {borrower.customer ? (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-zinc-500">Name</span><div>{borrower.customer.name}</div></div>
                  <div><span className="text-zinc-500">Credit Score</span><div>{borrower.customer.credit_score ?? "—"}</div></div>
                  <div><span className="text-zinc-500">Phone</span><div>{borrower.customer.phone || "—"}</div></div>
                  <div><span className="text-zinc-500">Email</span><div>{borrower.customer.email || "—"}</div></div>
                  <div className="col-span-2"><span className="text-zinc-500">Address</span><div>{borrower.customer.address}, {borrower.customer.city}, {borrower.customer.state} {borrower.customer.zip}</div></div>
                  {borrower.customer.phone && (
                    <div className="col-span-2 mt-1">
                      <CommsQuickActions customerId={borrower.customer.id} phone={borrower.customer.phone} name={borrower.customer.name} size="xs" />
                    </div>
                  )}
                </div>
              ) : (
                <div className="text-xs text-zinc-500">No customer linked to this loan.</div>
              )}
              {borrower.customer && (
                <WorkButton type="submit" onClick={() => setFull360Open(true)} className="mt-2 text-xs px-2.5 py-1 rounded bg-zinc-700 text-white hover:opacity-90 transition">
                  🔗 View Full Customer 360 →
                </WorkButton>
              )}
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Employer / Income</div>
              {borrower.employment.on_file ? (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-zinc-500">Employment Status</span><div>{borrower.employment.employment_status || "—"}</div></div>
                  <div><span className="text-zinc-500">Employer</span><div>{borrower.employment.employer_name || "—"}</div></div>
                  <div><span className="text-zinc-500">Monthly Income</span><div>{money(borrower.employment.monthly_income)}</div></div>
                  <div><span className="text-zinc-500">Housing Status</span><div>{borrower.employment.housing_status || "—"}</div></div>
                  <div className="col-span-2 text-xs text-zinc-500">From {borrower.employment.source_credit_application_id} on file.</div>
                </div>
              ) : (
                <div className="text-xs text-zinc-500">{borrower.employment.note}</div>
              )}
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">References</div>
              <div className="text-xs text-zinc-500">{borrower.references.note}</div>
            </div>
          </div>
        )}

        {tab === "vehicle" && (
          <div className="space-y-2">
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Collateral Vehicle</div>
              {vehicle.vehicle ? (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div><span className="text-zinc-500">Vehicle</span><div>{vehicle.vehicle.year} {vehicle.vehicle.make} {vehicle.vehicle.model} {vehicle.vehicle.trim}</div></div>
                  <div><span className="text-zinc-500">VIN</span><div>{vehicle.vehicle.vin}</div></div>
                  <div><span className="text-zinc-500">Stock #</span><div>{vehicle.vehicle.stock_number || "—"}</div></div>
                  <div><span className="text-zinc-500">Mileage</span><div>{vehicle.vehicle.mileage ?? "—"}</div></div>
                  <div><span className="text-zinc-500">Collateral Status</span><div>{vehicle.collateral_status}</div></div>
                </div>
              ) : (
                <div className="text-xs text-zinc-500">No vehicle linked to this loan.</div>
              )}
            </div>
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Lender</div>
              <div className="text-xs">{lender?.name || "—"}</div>
            </div>
            <div className="text-xs text-zinc-500 px-1">
              GPS Status and Starter-Interrupt Status aren&apos;t built yet -- separately scoped future Finance menu items.
            </div>
          </div>
        )}

        {tab === "contract" && (
          <div className="space-y-2">
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Contract</div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div><span className="text-zinc-500">Original Amount</span><div>{money(contract.original_amount)}</div></div>
                <div><span className="text-zinc-500">APR</span><div>{contract.apr}%</div></div>
                <div><span className="text-zinc-500">Term</span><div>{contract.term_months} mo</div></div>
                <div><span className="text-zinc-500">Monthly Payment</span><div>{money(contract.monthly_payment)}</div></div>
                <div><span className="text-zinc-500">Terms Remaining</span><div>{contract.terms_remaining} mo</div></div>
                <div><span className="text-zinc-500">{contract.current_balance_basis === "real_payment_ledger" ? "Balance from recorded payments" : "Estimated scheduled balance"}</span><div>{money(contract.current_balance ?? contract.schedule_implied_balance)}</div></div>
              </div>
              <div className="text-xs text-zinc-500 mt-2">{contract.note}</div>
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Payment Schedule (first 6 / last 3)</div>
              <RecordTable className="w-full text-xs">
                <thead className="text-zinc-500">
                  <tr><th className="text-left">#</th><th className="text-right">Payment</th><th className="text-right">Principal</th><th className="text-right">Interest</th><th className="text-right">Balance</th></tr>
                </thead>
                <tbody>
                  {contract.payment_schedule.map((r) => (
                    <tr key={r.period}><td>{r.period}</td><td className="text-right">{money(r.payment)}</td><td className="text-right">{money(r.principal_portion)}</td><td className="text-right">{money(r.interest_portion)}</td><td className="text-right">{money(r.balance)}</td></tr>
                  ))}
                  {contract.payment_schedule.length > 9 && <tr><td colSpan={5} className="text-center text-zinc-600">⋯</td></tr>}
                  {contract.payment_schedule.slice(-3).map((r) => (
                    <tr key={r.period}><td>{r.period}</td><td className="text-right">{money(r.payment)}</td><td className="text-right">{money(r.principal_portion)}</td><td className="text-right">{money(r.interest_portion)}</td><td className="text-right">{money(r.balance)}</td></tr>
                  ))}
                </tbody>
              </RecordTable>
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
                Payment / Delinquency Status <SimulatedBadge disclaimer={payment_status.disclaimer} basis={payment_status.basis} />
              </div>
              <div className="grid grid-cols-3 gap-2 text-xs">
                <div><span className="text-zinc-500">Bucket</span><div className={`inline-block text-xs px-1.5 py-0.5 rounded ${BUCKET_TONE[payment_status.bucket]}`}>{BUCKET_LABEL[payment_status.bucket]}</div></div>
                <div><span className="text-zinc-500">Days Past Due</span><div>{payment_status.days_past_due}</div></div>
                <div><span className="text-zinc-500">Amount Past Due</span><div>{money(payment_status.amount_past_due)}</div></div>
              </div>
            </div>

            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Loan Status</div>
              <div className="flex items-center gap-1.5">
                <WorkField label="New status"><WorkSelect value={newStatus} onChange={(e) => setNewStatus(e.target.value as LoanStatus)} className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}>
                  {LOAN_STATUS_OPTIONS.map((s) => <option key={s} value={s}>{s}</option>)}
                </WorkSelect></WorkField>
                <WorkField label="Reason (optional)"><WorkInput value={statusReason} onChange={(e) => setStatusReason(e.target.value)} placeholder="Reason (optional)…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
                <WorkButton type="submit" variant="primary" disabled={statusBusy} onClick={handleSetStatus} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                  {statusBusy ? "Saving…" : "Set Status"}
                </WorkButton>
              </div>
            </div>
          </div>
        )}

        {tab === "payments" && (
          <PaymentsTab theme={theme} loanId={loanId} cardClass={cardClass} textClass={textClass} onChanged={() => { refresh(); onChanged(); }} />
        )}

        {tab === "timeline" && (
          <div className="space-y-2">
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Loan Timeline</div>
              <div className="space-y-1.5">
                {timeline.events.map((e, i) => (
                  <div key={i} className="flex items-center justify-between text-xs">
                    <span className="capitalize">{e.type.replace(/_/g, " ")}</span>
                    <span className="text-zinc-500">{e.at}</span>
                  </div>
                ))}
                {timeline.events.length === 0 && <div className="text-xs text-zinc-500">No timeline events yet.</div>}
              </div>
            </div>
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Payment History</div>
              <div className="text-xs text-zinc-500">{timeline.payment_history.note}</div>
            </div>
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Collection Activity</div>
              <div className="text-xs text-zinc-500">{timeline.collection_activity.note}</div>
            </div>
            <div className={cardClass}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1">Repossession Events</div>
              <div className="text-xs text-zinc-500">{timeline.repossession_events.note}</div>
            </div>
          </div>
        )}
      </div>

      {full360Open && borrower.customer && (
        <Customer360Panel theme={theme} customerId={borrower.customer.id} onClose={() => setFull360Open(false)} />
      )}
    </WorkOverlay>
  );
}

// The real per-loan Payments workspace -- record a payment, manage Auto Drafts,
// track Promises To Pay, log an extension/deferral, request a payoff, and issue a
// real Customer Payment Portal link. Reused by both PortfolioBoard's LoanDetailModal
// (a tab scoped to whatever loan is open) and PaymentsBoard.tsx (the Payments Top
// Menu item's own screen, via the same exported LoanDetailModal below).
function PaymentsTab({ theme, loanId, cardClass, textClass, onChanged }: { theme: Theme; loanId: string; cardClass: string; textClass: string; onChanged: () => void }) {
  const [payments, setPayments] = useState<Payment[]>([]);
  const [drafts, setDrafts] = useState<AutoDraft[]>([]);
  const [promises, setPromises] = useState<PromiseToPay[]>([]);
  const [portalLink, setPortalLink] = useState<{ exists: boolean; token?: string; revoked?: boolean; path?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [amount, setAmount] = useState("");
  const [method, setMethod] = useState<PaymentMethod>("cash");
  const [notes, setNotes] = useState("");

  const [draftAmount, setDraftAmount] = useState("");
  const [draftMethod, setDraftMethod] = useState<PaymentMethod>("ach");
  const [draftDay, setDraftDay] = useState("1");

  const [promiseDate, setPromiseDate] = useState("");
  const [promiseAmount, setPromiseAmount] = useState("");
  const [promiseReason, setPromiseReason] = useState("");

  const [extDate, setExtDate] = useState("");
  const [deferMonths, setDeferMonths] = useState("1");
  const [adjustReason, setAdjustReason] = useState("");
  const [notice, setNotice] = useState<string | null>(null);

  function refresh() {
    const failed = (e: unknown) => setError(e instanceof Error ? e.message : "Payment records could not be loaded. Please try again.");
    listPaymentsForLoan(loanId).then((r) => setPayments(r.payments)).catch(failed);
    listAutoDrafts(loanId).then((r) => setDrafts(r.drafts)).catch(failed);
    listPromisesToPay(loanId).then((r) => setPromises(r.promises)).catch(failed);
    getPaymentPortalLinkStatus(loanId).then(setPortalLink).catch(failed);
  }

  useEffect(refresh, [loanId]);

  async function run<T>(fn: () => Promise<T>, success = "Changes saved.") {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await fn();
      setNotice(success);
      refresh();
      onChanged();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      {error && <div role="alert" className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error} <WorkButton type="submit" onClick={() => { setError(null); refresh(); }}>Try again</WorkButton></div>}
      {notice && <p role="status" className="text-sm text-green-600">{notice}</p>}

      <div className={cardClass}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Record a Payment</div>
        <div className="flex items-center gap-1.5">
          <WorkField label="Amount ($)"><WorkInput value={amount} onChange={(e) => setAmount(e.target.value)} type="number" placeholder="Amount ($)" className={`w-28 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkField label="Method"><WorkSelect value={method} onChange={(e) => setMethod(e.target.value as PaymentMethod)} className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}>
            {PAYMENT_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
          </WorkSelect></WorkField>
          <WorkField label="Notes (optional)"><WorkInput value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Notes (optional)…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkButton type="submit" variant="primary"
            disabled={busy || !amount}
            onClick={() => run(async () => { await recordPayment(loanId, parseFloat(amount), method, notes); setAmount(""); setNotes(""); })}
            className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
          >
            Record
          </WorkButton>
        </div>
        <div className="mt-2 space-y-1 max-h-32 overflow-y-auto">
          {payments.slice().reverse().map((p) => (
            <div key={p.id} className="flex items-center justify-between text-xs">
              <span>{p.payment_date} · {p.method} · {p.status}{p.decline_reason ? ` (${p.decline_reason})` : ""}</span>
              <span>{money(p.amount)}</span>
            </div>
          ))}
          {payments.length === 0 && <div className="text-xs text-zinc-500">No payments recorded yet.</div>}
        </div>
      </div>

      <div className={cardClass}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Auto Drafts</div>
        <div className="flex items-center gap-1.5 mb-2">
          <WorkField label="Amount ($)"><WorkInput value={draftAmount} onChange={(e) => setDraftAmount(e.target.value)} type="number" placeholder="Amount ($)" className={`w-24 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkField label="Payment method"><WorkSelect value={draftMethod} onChange={(e) => setDraftMethod(e.target.value as PaymentMethod)} className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`}>
            {PAYMENT_METHODS.map((m) => <option key={m} value={m}>{m}</option>)}
          </WorkSelect></WorkField>
          <WorkField label="Day (1-28)"><WorkInput value={draftDay} onChange={(e) => setDraftDay(e.target.value)} type="number" min={1} max={28} placeholder="Day (1-28)" className={`w-20 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkButton type="submit" variant="primary"
            disabled={busy || !draftAmount}
            onClick={() => run(async () => { await createAutoDraft(loanId, parseFloat(draftAmount), draftMethod, parseInt(draftDay, 10)); setDraftAmount(""); })}
            className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
          >
            + Draft
          </WorkButton>
        </div>
        <div className="space-y-1">
          {drafts.map((d) => (
            <div key={d.id} className="flex items-center justify-between text-xs">
              <span>{money(d.amount)}/mo · {d.method} · day {d.day_of_month} · {d.status}</span>
              <WorkButton type="submit"
                disabled={busy}
                onClick={() => run(() => setAutoDraftStatus(d.id, d.status === "active" ? "paused" : "active"))}
                className="text-xs px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition"
              >
                {d.status === "active" ? "Pause" : "Resume"}
              </WorkButton>
            </div>
          ))}
          {drafts.length === 0 && <div className="text-xs text-zinc-500">No auto drafts configured.</div>}
        </div>
      </div>

      <div className={cardClass}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Promises To Pay</div>
        <div className="flex items-center gap-1.5 mb-2">
          <WorkField label="Promise Date"><WorkInput value={promiseDate} onChange={(e) => setPromiseDate(e.target.value)} type="date" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkField label="Amount ($)"><WorkInput value={promiseAmount} onChange={(e) => setPromiseAmount(e.target.value)} type="number" placeholder="Amount ($)" className={`w-24 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkField label="Reason"><WorkInput value={promiseReason} onChange={(e) => setPromiseReason(e.target.value)} placeholder="Reason…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkButton type="submit" variant="primary"
            disabled={busy || !promiseDate || !promiseAmount}
            onClick={() => run(async () => { await createPromiseToPay(loanId, promiseDate, parseFloat(promiseAmount), promiseReason); setPromiseDate(""); setPromiseAmount(""); setPromiseReason(""); })}
            className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
          >
            + Promise
          </WorkButton>
        </div>
        <div className="space-y-1">
          {promises.map((p) => (
            <div key={p.id} className="flex items-center justify-between text-xs">
              <span>{p.promise_date} · {money(p.amount)} · {p.reason}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded ${p.status === "kept" ? "bg-green-950/40 text-green-300" : p.status === "broken" ? "bg-red-950/40 text-red-300" : "bg-zinc-800 text-zinc-400"}`}>{p.status}</span>
            </div>
          ))}
          {promises.length === 0 && <div className="text-xs text-zinc-500">No promises to pay on file.</div>}
        </div>
      </div>

      <div className={cardClass}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Extension / Deferral</div>
        <div className="flex items-center gap-1.5 mb-1.5">
          <WorkField label="Extension date"><WorkInput value={extDate} onChange={(e) => setExtDate(e.target.value)} type="date" className={`rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkField label="Reason"><WorkInput value={adjustReason} onChange={(e) => setAdjustReason(e.target.value)} placeholder="Reason…" className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <WorkButton type="submit"
            disabled={busy || !extDate}
            onClick={() => run(async () => { await recordExtension(loanId, extDate, adjustReason); setExtDate(""); setAdjustReason(""); })}
            className="text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition"
          >
            Log Extension
          </WorkButton>
        </div>
        <div className="flex items-center gap-1.5">
          <WorkField label="Months to defer"><WorkInput value={deferMonths} onChange={(e) => setDeferMonths(e.target.value)} type="number" min={1} className={`w-20 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
          <span className="text-xs text-zinc-500">month(s)</span>
          <WorkButton type="submit"
            disabled={busy}
            onClick={() => run(async () => { await recordDeferral(loanId, parseInt(deferMonths, 10), adjustReason); })}
            className="text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition"
          >
            Log Deferral
          </WorkButton>
        </div>
      </div>

      <div className={cardClass}>
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Customer Payment Portal</div>
        {portalLink?.exists && !portalLink.revoked ? (
          <div className="flex items-center gap-1.5">
            <code className="flex-1 text-xs px-2 py-1.5 rounded bg-zinc-900 text-zinc-300 truncate">{portalLink.path}</code>
            <WorkButton type="submit"
              onClick={() => navigator.clipboard?.writeText(`${window.location.origin}${portalLink.path}`)}
              className="text-xs px-2 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition"
            >
              Copy
            </WorkButton>
            <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => run(() => revokePaymentPortalLink(loanId))} className="text-xs px-2 py-1.5 rounded bg-red-950/40 text-red-300 hover:text-red-100 transition">
              Revoke
            </WorkButton>
          </div>
        ) : (
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => run(() => generatePaymentPortalLink(loanId))} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            {portalLink?.revoked ? "Generate New Link" : "Generate Payment Link"}
          </WorkButton>
        )}
        <WorkButton type="submit"
          disabled={busy}
          onClick={() => run(() => requestPayoff(loanId, "Requested by staff"), "Payoff request saved. Review it in Finance → Payments.")}
          className="mt-2 text-xs px-2.5 py-1.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition"
        >
          Request Payoff
        </WorkButton>
      </div>
    </div>
  );
}

export function PortfolioBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<PortfolioDashboard | null>(null);
  const [loading, setLoading] = useState(true);
  const [bucketFilter, setBucketFilter] = useState<DelinquencyBucket | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    getPortfolioDashboard(bucketFilter || undefined, 100)
      .then(setDashboard)
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [bucketFilter]);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Loans" value={String(dashboard?.total_loans ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Active Loans" value={String(dashboard?.active_loans ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Total Outstanding" value={money(dashboard?.total_outstanding_balance)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Payoffs" value={String(dashboard?.payoffs ?? 0)} color={RIBBON[3]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800 flex items-center gap-2">
        <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
          Payment status uses recorded payments where available. Loans without payment records use simulated status and an estimated scheduled balance. Open a loan to see its basis.
        </span>
      </div>

      <div className="px-4 py-2 border-b border-zinc-800 flex flex-wrap items-center gap-1.5">
        <WorkButton type="submit"
          onClick={() => setBucketFilter(null)}
          className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${!bucketFilter ? "bg-brand-blue text-white" : tc(theme, "bg-zinc-800 text-zinc-400 hover:text-white", "bg-zinc-200 text-zinc-500 hover:text-black")}`}
        >
          All ({dashboard?.total_loans ?? 0})
        </WorkButton>
        {BUCKET_ORDER.map((b) => (
          <WorkButton type="submit"
            key={b}
            onClick={() => setBucketFilter(b)}
            className={`text-xs px-2.5 py-1 rounded-full transition ${bucketFilter === b ? BUCKET_TONE[b] : tc(theme, "bg-zinc-800 text-zinc-400 hover:text-white", "bg-zinc-200 text-zinc-500 hover:text-black")}`}
          >
            {BUCKET_LABEL[b]} ({dashboard?.delinquency_buckets?.[b] ?? 0})
          </WorkButton>
        ))}
      </div>

      <div className="flex-1 p-4">
        {loading || !dashboard ? (
          <div className="text-sm text-zinc-500" role="status">Loading…</div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {dashboard.loans.map((l) => (
              <button
                key={l.id}
                onClick={() => setSelected(l.id)}
                className={tc(theme, "text-left rounded-lg border border-zinc-800 bg-brand-charcoal p-3 hover:border-brand-blue transition", "text-left rounded-lg border border-zinc-200 bg-zinc-50 p-3 hover:border-brand-blue transition")}
              >
                <div className="flex items-center justify-between mb-1">
                  <span className="text-sm font-medium">{l.customer?.name || l.finance_number || l.id}</span>
                  {l.bucket && (
                    <span className={`text-xs px-1.5 py-0.5 rounded ${BUCKET_TONE[l.bucket]}`}>{BUCKET_LABEL[l.bucket]}</span>
                  )}
                </div>
                <div className="text-xs text-zinc-500">
                  {l.vehicle ? `${l.vehicle.year} ${l.vehicle.make} ${l.vehicle.model}` : "—"} · {money(l.monthly_payment)}/mo · {l.apr}% APR
                </div>
              </button>
            ))}
            {dashboard.loans.length === 0 && <div className="text-sm text-zinc-500 col-span-2">No loans in this bucket.</div>}
          </div>
        )}
      </div>

      {selected && (
        <LoanDetailModal theme={theme} loanId={selected} onClose={() => setSelected(null)} onChanged={refresh} />
      )}
    </div>
  );
}
