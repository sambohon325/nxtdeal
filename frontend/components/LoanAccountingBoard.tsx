"use client";
import {CollectionPagination} from "./CollectionPagination";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Finance's "Accounting" item, extended (2026-07-17, session 112 follow-up) -- the
// eighth slice of Sam's "Retail Automotive Lending Platform" expansion. A real
// cash-basis loan sub-ledger: an Interest Income/Principal Reduction/Cash Collected
// summary, a daily journal-style ledger with a post/unposted workflow, and a real
// month-end close (rejecting close while unposted payments remain in the period,
// rejecting posting into an already-closed period).
//
// Extended further, same session, same follow-up thread -- per Sam's direct
// instruction after every explicitly-named Finance/Accounting item was closed
// ("lets keep going, simply create the fake data that is needed to build them") --
// with three more tabs: General Ledger (real entries synced from Loan Accounting/
// Deals, blended with clearly-labeled SIMULATED entries for floorplan interest/
// payroll/overhead/other income), Financial Statements (a real Trial Balance/Income
// Statement/Balance Sheet computed off that blended ledger), and Bank Reconciliation
// (a SIMULATED bank feed -- no real bank connection exists in this sandbox -- real-
// matched against the GL via a genuine amount/date-proximity algorithm). Every
// simulated figure is visibly labeled in this UI, matching each entry's own
// `basis`/`disclaimer` field from the backend -- nothing here is presented as real
// that isn't.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { PaymentReviewPanel } from "@/components/PaymentReviewPanel";
import {
  getLoanAccountingSummary,
  getUnpostedPayments,
  getAccountingPeriods,
  getDailyLedger,
  postAllDue,
  postPaymentToLedger,
  closeAccountingPeriod,
  reopenAccountingPeriod,
  type LoanAccountingSummary,
  type LedgerEntry,
  type AccountingPeriod,
  type DailyLedger,
} from "@/lib/loanAccounting";
import {
  getChartOfAccounts,
  syncRealGlEntries,
  generateSimulatedGlEntries,
  deleteGlEntry,
  getGeneralLedgerEntries,
  getTrialBalance,
  getIncomeStatement,
  getBalanceSheet,
  type GlAccount,
  type GlEntry,
  type TrialBalance,
  type IncomeStatement,
  type BalanceSheet,
} from "@/lib/generalLedger";
import {
  generateSimulatedBankFeed,
  getReconciliationStatus,
  listBankTransactions,
  confirmBankMatch,
  markBankTransactionReviewed,
  type ReconciliationStatus,
  type BankTransaction,
} from "@/lib/bankReconciliation";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function todayIso(): string {
  const date = new Date();
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function SimBadge({ label = "Simulated" }: { label?: string }) {
  return (
    <span className="text-xs px-1.5 py-0.5 rounded bg-purple-950/40 border border-purple-800/50 text-purple-300 font-medium uppercase tracking-wide">
      {label}
    </span>
  );
}

const TABS = ["Payments Ledger", "Payment Review", "General Ledger", "Financial Statements", "Bank Reconciliation"] as const;
type Tab = (typeof TABS)[number];

export function unpostedPaymentPage(entries: LedgerEntry[], query: string, page: number) {
  const term = query.trim().toLowerCase();
  const matches = entries.filter(e => !term || [e.payment_id, e.loan_id, e.payment_date, e.method].some(value => value.toLowerCase().includes(term)));
  const pages = Math.max(1, Math.ceil(matches.length / 4));
  const current = Math.max(0, Math.min(page, pages - 1));
  return { rows: matches.slice(current * 4, current * 4 + 4), total: matches.length, pages, current };
}

export function accountingPeriodStatus(periods: AccountingPeriod[], ready: boolean, year: number, month: number) {
  if (!ready || !Number.isInteger(year) || year < 1000 || year > 9999 || !Number.isInteger(month) || month < 1 || month > 12) return "unavailable";
  const key = `${year}-${String(month).padStart(2, "0")}`;
  return periods.find(p => p.period_key === key)?.status ?? "open";
}

export function bankHistoryPage(transactions: BankTransaction[], status: string, query: string, page: number) {
  const term = query.trim().toLowerCase();
  const matches = transactions.filter(t => (!status || t.status === status) && (!term ||
    [t.id, t.transaction_date, t.description, t.matched_gl_entry_id].some(value => String(value ?? "").toLowerCase().includes(term))));
  const pages = Math.max(1, Math.ceil(matches.length / 4));
  const current = Math.max(0, Math.min(page, pages - 1));
  return { rows: matches.slice(current * 4, current * 4 + 4), total: matches.length, pages, current };
}

export function LoanAccountingBoard({ theme, initialTab = "Payments Ledger" }: { theme: Theme; initialTab?: Tab }) {
  const [tab, setTab] = useState<Tab>(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);
  const [summary, setSummary] = useState<LoanAccountingSummary | null>(null);
  const [unposted, setUnposted] = useState<LedgerEntry[]>([]);
  const [periods, setPeriods] = useState<AccountingPeriod[]>([]);
  const [ledgerDate, setLedgerDate] = useState(todayIso());
  const [dailyLedger, setDailyLedger] = useState<DailyLedger | null>(null);
  const [ledgerLoading, setLedgerLoading] = useState(true);
  const [ledgerError, setLedgerError] = useState<string | null>(null);
  const [ledgerRevision, setLedgerRevision] = useState(0);
  const [closeYear, setCloseYear] = useState(new Date().getFullYear());
  const [closeMonth, setCloseMonth] = useState(new Date().getMonth() + 1);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  // General Ledger tab state
  const [accounts, setAccounts] = useState<GlAccount[]>([]);
  const [glEntries, setGlEntries] = useState<GlEntry[]>([]);
  const [genYear, setGenYear] = useState(new Date().getFullYear());
  const [genMonth, setGenMonth] = useState(new Date().getMonth() + 1);
  const [floorplanExposure, setFloorplanExposure] = useState(0);

  // Financial Statements tab state
  const [trialBalance, setTrialBalance] = useState<TrialBalance | null>(null);
  const [incomeStatement, setIncomeStatement] = useState<IncomeStatement | null>(null);
  const [balanceSheet, setBalanceSheet] = useState<BalanceSheet | null>(null);

  // Bank Reconciliation tab state
  const [recStatus, setRecStatus] = useState<ReconciliationStatus | null>(null);
  const [bankTxns, setBankTxns] = useState<BankTransaction[]>([]);
  const [matchTxnId, setMatchTxnId] = useState<string | null>(null);
  const [matchDrafts, setMatchDrafts] = useState<Record<string, string>>({});
  const [unpostedSearch, setUnpostedSearch] = useState("");
  const [unpostedPage, setUnpostedPage] = useState(0);
  const [unpostedRevision, setUnpostedRevision] = useState(0);
  const [unpostedLoading, setUnpostedLoading] = useState(true);
  const [unpostedError, setUnpostedError] = useState<string | null>(null);
  const unpostedQueue = unpostedPaymentPage(unposted, unpostedSearch, unpostedPage);
  const [overviewRevision, setOverviewRevision] = useState(0);
  const [overviewLoading, setOverviewLoading] = useState(true);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [detailRevision, setDetailRevision] = useState(0);
  const [detailState, setDetailState] = useState<{tab: Tab; loading: boolean; error: string | null}>({tab: "Payments Ledger", loading: false, error: null});
  const detailReady = detailState.tab === tab && !detailState.loading && !detailState.error;
  const [glPage, setGlPage] = useState(0);
  const [glTotal, setGlTotal] = useState(0);
  const [bankSearch, setBankSearch] = useState("");
  const [bankStatus, setBankStatus] = useState("");
  const [bankPage, setBankPage] = useState(0);
  const bankHistory = bankHistoryPage(bankTxns, bankStatus, bankSearch, bankPage);



  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");
  const tabBase = "text-[11px] px-3 py-1.5 rounded-full font-medium transition";
  const tabActive = tc(theme, "bg-white text-black", "bg-black text-white");
  const tabInactive = tc(theme, "bg-zinc-800 text-zinc-300 hover:text-white", "bg-zinc-200 text-zinc-600 hover:text-black");

  function refresh() {
    setOverviewRevision(value => value + 1);
  }

  function refreshGl() { setDetailRevision(value => value + 1); }
  function refreshStatements() { setDetailRevision(value => value + 1); }
  function refreshRec() { setDetailRevision(value => value + 1); }

  useEffect(refresh, []);
  useEffect(() => {
    let active = true;
    setDailyLedger(null);
    setLedgerError(null);
    setLedgerLoading(true);
    if (!ledgerDate) {
      setLedgerError("Choose a ledger date.");
      setLedgerLoading(false);
      return () => { active = false; };
    }
    getDailyLedger(ledgerDate).then(value => { if (active) setDailyLedger(value); })
      .catch(e => { if (active) setLedgerError(e instanceof Error ? e.message : "Unable to load this ledger date."); })
      .finally(() => { if (active) setLedgerLoading(false); });
    return () => { active = false; };
  }, [ledgerDate, ledgerRevision]);

  useEffect(() => {
    if (tab === "Payments Ledger" || tab === "Payment Review") return;
    let active = true;
    setDetailState({tab, loading: true, error: null});
    async function load() {
      try {
        if (tab === "General Ledger") {
          const [chart, ledger] = await Promise.all([getChartOfAccounts(), getGeneralLedgerEntries(undefined, undefined, undefined, glPage * 4, 4)]);
          if (active) { setAccounts(chart.accounts); setGlEntries(ledger.entries); setGlTotal(ledger.count); if (glPage > 0 && glPage * 4 >= ledger.count) setGlPage(Math.max(0, Math.ceil(ledger.count / 4) - 1)); }
        } else if (tab === "Financial Statements") {
          const [trial, income, balance] = await Promise.all([getTrialBalance(), getIncomeStatement(), getBalanceSheet()]);
          if (active) { setTrialBalance(trial); setIncomeStatement(income); setBalanceSheet(balance); }
        } else {
          const [status, transactions] = await Promise.all([getReconciliationStatus(), listBankTransactions()]);
          if (active) { setRecStatus(status); setBankTxns(transactions.transactions); }
        }
        if (active) setDetailState({tab, loading: false, error: null});
      } catch (e) {
        if (active) setDetailState({tab, loading: false, error: e instanceof Error ? e.message : `Unable to load ${tab}.`});
      }
    }
    void load();
    return () => { active = false; };
  }, [tab, detailRevision, glPage]);

  useEffect(() => {
    let active = true;
    setUnpostedLoading(true);
    setUnpostedError(null);
    setUnposted([]);
    getUnpostedPayments().then(result => { if (active) setUnposted(result.unposted); })
      .catch(e => { if (active) setUnpostedError(e instanceof Error ? e.message : "Unable to load unposted payments."); })
      .finally(() => { if (active) setUnpostedLoading(false); });
    return () => { active = false; };
  }, [unpostedRevision]);

  useEffect(() => {
    let active = true;
    setOverviewLoading(true);
    setOverviewError(null);
    setSummary(null);
    setPeriods([]);
    Promise.all([getLoanAccountingSummary(), getAccountingPeriods()])
      .then(([summaryResult, periodResult]) => { if (active) { setSummary(summaryResult); setPeriods(periodResult.periods); } })
      .catch(e => { if (active) setOverviewError(e instanceof Error ? e.message : "Unable to load accounting summary and period status."); })
      .finally(() => { if (active) setOverviewLoading(false); });
    return () => { active = false; };
  }, [overviewRevision]);

  async function run(fn: () => Promise<unknown>, after?: () => void) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      refresh();
      setLedgerRevision(value => value + 1);
      setUnpostedRevision(value => value + 1);
      after?.();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  const periodKey = `${closeYear}-${String(closeMonth).padStart(2, "0")}`;
  const periodStatus = accountingPeriodStatus(periods, !overviewLoading && !overviewError, closeYear, closeMonth);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Interest Income Recognized" value={money(summary?.interest_income_recognized)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Principal Reduction" value={money(summary?.principal_reduction)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Cash Collected" value={money(summary?.cash_collected)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Unposted Payments" value={summary ? String(summary.unposted_count) : "—"} color={RIBBON[3]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800 flex flex-wrap gap-2">
        {TABS.map((t) => (
          <WorkButton data-work-view aria-pressed={tab === t} type="submit" key={t} onClick={() => setTab(t)} className={`${tabBase} ${tab === t ? tabActive : tabInactive}`}>
            {t}
          </WorkButton>
        ))}
      </div>

      {overviewLoading && <p role="status" className="px-4 text-xs">Loading accounting summary and period status…</p>}
      {overviewError && <p role="alert" className="px-4 text-xs">{overviewError} <WorkButton type="submit" onClick={refresh}>Retry accounting status</WorkButton></p>}
      {error && <div className="text-xs text-red-400 px-4 pt-2">{error}</div>}

      {tab === "Payment Review" && <PaymentReviewPanel />}
      {tab !== "Payments Ledger" && tab !== "Payment Review" && !detailReady && <div className="p-4">
        {detailState.tab === tab && detailState.error ? <p role="alert">{detailState.error} <WorkButton type="submit" onClick={() => setDetailRevision(value => value + 1)}>Retry {tab}</WorkButton></p> : <p role="status">Loading {tab}…</p>}
      </div>}
      {tab === "Payments Ledger" && (
        <div className="flex-1 p-4 overflow-y-auto space-y-4">
          <div className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300 inline-block">
            {summary?.note}
          </div>

          <div className={cardClass}>
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Daily Ledger</div>
              <div className="flex items-center gap-2">
                <WorkInput aria-label="Ledger date" disabled={busy} type="date" value={ledgerDate} onChange={(e) => { setDailyLedger(null); setLedgerLoading(true); setLedgerDate(e.target.value); }} className={`rounded-md border px-2 py-1 text-xs ${textClass}`} />
                <WorkButton type="submit" variant="primary"
                  disabled={busy || ledgerLoading || !!ledgerError || !dailyLedger || dailyLedger.period_closed}
                  onClick={() => run(() => postAllDue(ledgerDate))}
                  className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                >
                  Post All Due
                </WorkButton>
              </div>
            </div>
            {ledgerLoading && <p role="status" className="text-xs mb-2">Loading ledger for {ledgerDate}…</p>}
            {ledgerError && <p role="alert" className="text-xs mb-2">{ledgerError} <WorkButton type="submit" onClick={() => setLedgerRevision(value => value + 1)}>Retry ledger</WorkButton></p>}
            {dailyLedger?.period_closed && (
              <div className="text-xs text-red-400 mb-2">This period is closed — no further posting until it's reopened.</div>
            )}
            <div className="grid grid-cols-3 gap-3 mb-2 text-xs">
              <div><span className="text-zinc-500">Cash</span><div className="font-semibold">{money(dailyLedger?.totals.cash)}</div></div>
              <div><span className="text-zinc-500">Interest Income</span><div className="font-semibold">{money(dailyLedger?.totals.interest_income)}</div></div>
              <div><span className="text-zinc-500">Principal Reduction</span><div className="font-semibold">{money(dailyLedger?.totals.principal_reduction)}</div></div>
            </div>
            <div className="max-h-64 overflow-y-auto space-y-1">
              {(dailyLedger?.entries ?? []).length === 0 ? (
                <div className="text-xs text-zinc-600">{ledgerLoading || ledgerError ? "Payment rows unavailable until this date loads." : "No approved payments on this date."}</div>
              ) : (
                dailyLedger!.entries.map((e) => (
                  <div key={e.payment_id} className="flex items-center justify-between text-xs px-2 py-1.5 rounded hover:bg-zinc-800/40 transition">
                    <span>{e.payment_id} · {e.loan_id} · {e.method} · {money(e.lines[0]?.debit)}</span>
                    {e.posting_status === "posted" ? (
                      <span className="text-xs px-1.5 py-0.5 rounded bg-green-950/40 text-green-300">posted</span>
                    ) : (
                      <WorkButton type="submit" disabled={busy || ledgerLoading || !!ledgerError || !dailyLedger || dailyLedger.period_closed} onClick={() => run(() => postPaymentToLedger(e.payment_id))} className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50">
                        Post
                      </WorkButton>
                    )}
                  </div>
                ))
              )}
            </div>
          </div>

          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Unposted Payments ({unpostedLoading || unpostedError ? "—" : unposted.length})</div>
            <label className="block text-xs mb-2">Find an unposted payment
              <WorkInput value={unpostedSearch} onChange={e => { setUnpostedSearch(e.target.value); setUnpostedPage(0); }} placeholder="Payment, loan, date or method" className={`block w-full rounded-md border px-2 py-1 mt-1 ${textClass}`} />
            </label>
            {unpostedLoading ? <p role="status">Loading unposted payments…</p> : unpostedError ? <p role="alert">{unpostedError} <WorkButton type="submit" onClick={() => setUnpostedRevision(value => value + 1)}>Retry unposted payments</WorkButton></p> : <>
            <div className="space-y-1">
              {unpostedQueue.rows.map((e) => (
                <div key={e.payment_id} className="flex items-center justify-between text-xs px-2 py-1.5 rounded hover:bg-zinc-800/40 transition">
                  <span>{e.payment_id} · {e.loan_id} · {e.payment_date} · {money(e.lines[0]?.debit)}</span>
                  <WorkButton type="submit" disabled={busy} onClick={() => run(() => postPaymentToLedger(e.payment_id))} className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50">
                    Post
                  </WorkButton>
                </div>
              ))}
            </div>
            {!unpostedQueue.total && <p className="text-xs">{unpostedSearch ? "No matching unposted payments. Clear or change your search." : "No unposted payments."}</p>}
            <CollectionPagination label="Unposted payments" total={unpostedQueue.total} page={unpostedQueue.current} pageSize={4} onPageChange={setUnpostedPage} busy={busy || unpostedLoading}/>
            </>}
          </div>

          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Month-End Close</div>
            <div className="flex items-center gap-2 mb-2">
              <WorkInput aria-label="Accounting year" disabled={busy} min={1000} max={9999} type="number" value={closeYear} onChange={(e) => setCloseYear(parseInt(e.target.value) || closeYear)} className={`w-20 rounded-md border px-2 py-1.5 text-xs ${textClass}`} />
              <WorkInput aria-label="Accounting month" disabled={busy} type="number" min={1} max={12} value={closeMonth} onChange={(e) => setCloseMonth(parseInt(e.target.value) || closeMonth)} className={`w-16 rounded-md border px-2 py-1.5 text-xs ${textClass}`} />
              <span className={`text-xs px-1.5 py-0.5 rounded ${periodStatus === "closed" ? "bg-green-950/40 text-green-300" : "bg-zinc-800 text-zinc-400"}`}>
                {periodKey} — {periodStatus}
              </span>
              {periodStatus === "closed" ? (
                <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => run(() => reopenAccountingPeriod(closeYear, closeMonth))} className="text-xs px-2.5 py-1.5 rounded bg-red-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                  Reopen (Admin only)
                </WorkButton>
              ) : (
                <WorkButton type="submit" variant="primary" disabled={busy || periodStatus === "unavailable"} onClick={() => run(() => closeAccountingPeriod(closeYear, closeMonth))} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
                  Close Period
                </WorkButton>
              )}
            </div>
            <div className="text-xs text-zinc-600">Closing rejects if any approved payment in the period is still unposted.</div>
          </div>
        </div>
      )}

      {tab === "General Ledger" && detailReady && (
        <div className="flex-1 p-4 overflow-y-auto space-y-4">
          <div className={cardClass}>
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Sync &amp; Generate</div>
            </div>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              <WorkButton type="submit" variant="primary"
                disabled={busy}
                onClick={() => run(() => syncRealGlEntries(), refreshGl)}
                className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                Sync Real Entries (Payments + Funded Deals)
              </WorkButton>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              <SimBadge />

              <WorkField label="Generate simulated entries for:"><WorkInput type="number" value={genYear} onChange={(e) => setGenYear(parseInt(e.target.value) || genYear)} className={`w-20 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
              <WorkField label="Month"><WorkInput type="number" min={1} max={12} value={genMonth} onChange={(e) => setGenMonth(parseInt(e.target.value) || genMonth)} className={`w-16 rounded-md border px-2 py-1.5 text-xs ${textClass}`} /></WorkField>
              <WorkField label="Floorplan exposure"><WorkInput
                type="number"
                placeholder="Floorplan exposure"
                value={floorplanExposure || ""}
                onChange={(e) => setFloorplanExposure(parseFloat(e.target.value) || 0)}
                className={`w-36 rounded-md border px-2 py-1.5 text-xs ${textClass}`}
              /></WorkField>
              <WorkButton type="submit"
                disabled={busy}
                onClick={() => run(() => generateSimulatedGlEntries(genYear, genMonth, floorplanExposure), refreshGl)}
                className="text-xs px-2.5 py-1.5 rounded bg-purple-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                Generate Simulated Entries
              </WorkButton>
            </div>
            <div className="text-xs text-zinc-600 mt-2">Floorplan interest, payroll, overhead, and other income are SIMULATED — real value from Finance's own Floorplan dashboard can be typed in above. One generation per period; rejects a closed period.</div>
          </div>

          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Chart of Accounts</div>
            <div className="grid grid-cols-2 gap-1 max-h-40 overflow-y-auto">
              {accounts.map((a) => (
                <div key={a.number} className="text-xs px-2 py-1 rounded hover:bg-zinc-800/40 transition">
                  <span className="text-zinc-500">{a.number}</span> {a.name} <span className="text-xs text-zinc-600 uppercase">{a.type}</span>
                </div>
              ))}
            </div>
          </div>

          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">General Ledger Entries ({glTotal})</div>
            <div className="space-y-1">
              {glEntries.length === 0 ? (
                <div className="text-xs text-zinc-600">No entries yet — sync real activity or generate simulated entries above.</div>
              ) : (
                glEntries.map((e) => (
                  <div key={e.id} className="text-xs px-2 py-1.5 rounded hover:bg-zinc-800/40 transition">
                    <div className="flex items-center justify-between">
                      <span className="font-medium">{e.entry_date} · {e.description}</span>
                      <div className="flex items-center gap-2">
                        {e.basis?.startsWith("simulated") ? <SimBadge /> : <span className="text-xs px-1.5 py-0.5 rounded bg-green-950/40 text-green-300 uppercase">Real</span>}
                        <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => run(() => deleteGlEntry(e.id), refreshGl)} className="text-xs text-red-400 hover:text-red-300 transition">
                          Delete
                        </WorkButton>
                      </div>
                    </div>
                    <div className="text-xs text-zinc-500 pl-2">
                      {e.lines.map((l, i) => (
                        <div key={i}>{l.account}: {l.debit ? `Dr ${money(l.debit)}` : `Cr ${money(l.credit)}`}</div>
                      ))}
                    </div>
                    {e.disclaimer && <div className="text-xs text-purple-400 pl-2 mt-0.5">{e.disclaimer}</div>}
                  </div>
                ))
              )}
            </div>
            <CollectionPagination label="General ledger entries" total={glTotal} page={glPage} pageSize={4} onPageChange={setGlPage} busy={busy || detailState.loading}/>
          </div>
        </div>
      )}

      {tab === "Financial Statements" && detailReady && (
        <div className="flex-1 p-4 overflow-y-auto space-y-4">
          <div className={cardClass}>
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Trial Balance</div>
              <span className={`text-xs px-1.5 py-0.5 rounded ${trialBalance?.balanced ? "bg-green-950/40 text-green-300" : "bg-red-950/40 text-red-300"}`}>
                {trialBalance?.balanced ? "Balanced" : "Out of Balance"}
              </span>
            </div>
            <div className="max-h-56 overflow-y-auto space-y-0.5">
              {(trialBalance?.rows ?? []).map((r) => (
                <div key={r.account_number} className="flex items-center justify-between text-xs px-2 py-1 rounded hover:bg-zinc-800/40 transition">
                  <span>{r.account_number} · {r.account}</span>
                  <span>{r.debit ? `Dr ${money(r.debit)}` : `Cr ${money(r.credit)}`}</span>
                </div>
              ))}
            </div>
            <div className="flex items-center justify-between text-xs font-semibold px-2 pt-2 border-t border-zinc-800 mt-2">
              <span>Totals</span>
              <span>Dr {money(trialBalance?.total_debit)} / Cr {money(trialBalance?.total_credit)}</span>
            </div>
          </div>

          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Income Statement</div>
            <div className="text-xs space-y-1">
              <div className="font-medium text-zinc-400">Revenue</div>
              {(incomeStatement?.revenue.lines ?? []).map((l) => (
                <div key={l.account} className="flex items-center justify-between pl-2"><span>{l.account}</span><span>{money(l.amount)}</span></div>
              ))}
              <div className="flex items-center justify-between font-semibold pl-2"><span>Total Revenue</span><span>{money(incomeStatement?.revenue.total)}</span></div>
              <div className="font-medium text-zinc-400 pt-2">Expenses</div>
              {(incomeStatement?.expenses.lines ?? []).map((l) => (
                <div key={l.account} className="flex items-center justify-between pl-2"><span>{l.account}</span><span>{money(l.amount)}</span></div>
              ))}
              <div className="flex items-center justify-between font-semibold pl-2"><span>Total Expenses</span><span>{money(incomeStatement?.expenses.total)}</span></div>
              <div className="flex items-center justify-between font-semibold pt-2 border-t border-zinc-800 mt-1"><span>Net Income</span><span>{money(incomeStatement?.net_income)}</span></div>
            </div>
            {incomeStatement?.note && <div className="text-xs text-purple-400 mt-2">{incomeStatement.note}</div>}
          </div>

          <div className={cardClass}>
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Balance Sheet ({balanceSheet?.as_of_date})</div>
              <span className={`text-xs px-1.5 py-0.5 rounded ${balanceSheet?.balances ? "bg-green-950/40 text-green-300" : "bg-red-950/40 text-red-300"}`}>
                {balanceSheet?.balances ? "Balances" : "Out of Balance"}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-4 text-xs">
              <div>
                <div className="font-medium text-zinc-400 mb-1">Assets</div>
                {(balanceSheet?.assets.lines ?? []).map((l) => (
                  <div key={l.account} className="flex items-center justify-between"><span>{l.account}</span><span>{money(l.balance)}</span></div>
                ))}
                <div className="flex items-center justify-between font-semibold pt-1 border-t border-zinc-800 mt-1"><span>Total Assets</span><span>{money(balanceSheet?.assets.total)}</span></div>
              </div>
              <div>
                <div className="font-medium text-zinc-400 mb-1">Liabilities &amp; Equity</div>
                {(balanceSheet?.liabilities.lines ?? []).map((l) => (
                  <div key={l.account} className="flex items-center justify-between"><span>{l.account}</span><span>{money(l.balance)}</span></div>
                ))}
                <div className="flex items-center justify-between"><span>Owner's Equity</span><span>{money(balanceSheet?.equity.owners_equity)}</span></div>
                <div className="flex items-center justify-between"><span>Retained Earnings</span><span>{money(balanceSheet?.equity.retained_earnings)}</span></div>
                <div className="flex items-center justify-between font-semibold pt-1 border-t border-zinc-800 mt-1"><span>Total L + E</span><span>{money((balanceSheet?.liabilities.total ?? 0) + (balanceSheet?.equity.total ?? 0))}</span></div>
              </div>
            </div>
            {balanceSheet?.note && <div className="text-xs text-purple-400 mt-2">{balanceSheet.note}</div>}
          </div>
        </div>
      )}

      {tab === "Bank Reconciliation" && detailReady && (
        <div className="flex-1 p-4 overflow-y-auto space-y-4">
          <div className={cardClass}>
            <div className="flex items-center justify-between mb-2">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 flex items-center gap-2">
                {recStatus?.bank_account.name} <SimBadge label="Simulated Feed" />
              </div>
              <WorkButton type="submit"
                disabled={busy}
                onClick={() => run(() => generateSimulatedBankFeed(), refreshRec)}
                className="text-xs px-2.5 py-1.5 rounded bg-purple-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50"
              >
                Generate Simulated Bank Feed
              </WorkButton>
            </div>
            <div className="text-xs text-zinc-500 mb-2">{recStatus?.bank_account.bank} · ···{recStatus?.bank_account.account_last4}</div>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div><span className="text-zinc-500">Book Balance</span><div className="font-semibold">{money(recStatus?.book_balance)}</div></div>
              <div><span className="text-zinc-500">Bank Balance</span><div className="font-semibold">{money(recStatus?.bank_balance)}</div></div>
              <div><span className="text-zinc-500">Difference</span><div className={`font-semibold ${(recStatus?.difference ?? 0) !== 0 ? "text-amber-400" : "text-green-400"}`}>{money(recStatus?.difference)}</div></div>
            </div>
            {recStatus?.note && <div className="text-xs text-purple-400 mt-2">{recStatus.note}</div>}
          </div>

          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
              Unmatched Bank Transactions ({recStatus?.unmatched_bank_count ?? 0})
            </div>
            <div className="max-h-56 overflow-y-auto space-y-1">
              {(recStatus?.unmatched_bank_transactions ?? []).map((t) => (
                <div key={t.id} className="text-xs px-2 py-1.5 rounded hover:bg-zinc-800/40 transition">
                  <div className="flex items-center justify-between">
                    <span>{t.transaction_date} · {t.description} · {money(t.amount)}</span>
                    <div className="flex items-center gap-1">
                      <WorkButton type="submit" disabled={busy} onClick={() => run(() => markBankTransactionReviewed(t.id), refreshRec)} className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition disabled:opacity-50">
                        Mark Reviewed
                      </WorkButton>
                      <WorkButton type="submit" disabled={busy} aria-label={`Review match for ${t.id}`} onClick={() => setMatchTxnId(matchTxnId === t.id ? null : t.id)} className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 hover:text-white transition">
                        Match…
                      </WorkButton>
                    </div>
                  </div>
                  {matchTxnId === t.id && (
                    <div className="flex items-center gap-2 mt-1.5 pl-2">
                      <label className="flex-1 text-xs">Ledger entry for {t.id}<WorkInput
                        aria-label={`Ledger entry for ${t.id}`}
                        disabled={busy}
                        placeholder="GL Entry ID (e.g. GLE-00012)"
                        value={matchDrafts[t.id] ?? ""}
                        onChange={(e) => setMatchDrafts(drafts => ({...drafts, [t.id]: e.target.value}))}
                        className={`flex-1 rounded-md border px-2 py-1 text-xs ${textClass}`}
                      /></label>
                      <WorkButton type="submit" variant="primary"
                        disabled={busy || !(matchDrafts[t.id] ?? "").trim()}
                        onClick={() => run(() => confirmBankMatch(t.id, (matchDrafts[t.id] ?? "").trim()), () => { refreshRec(); setMatchTxnId(null); setMatchDrafts(drafts => { const next = {...drafts}; delete next[t.id]; return next; }); })}
                        className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50"
                      >
                        Confirm match for {t.id}
                      </WorkButton>
                    </div>
                  )}
                </div>
              ))}
              {(recStatus?.unmatched_bank_transactions ?? []).length === 0 && <div className="text-xs text-zinc-600">Nothing unmatched right now.</div>}
            </div>
          </div>

          <div className={cardClass}>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">
              Unmatched GL Entries ({recStatus?.unmatched_gl_count ?? 0})
            </div>
            <div className="max-h-40 overflow-y-auto space-y-1">
              {(recStatus?.unmatched_gl_entries ?? []).map((g) => (
                <div key={g.id} className="text-xs px-2 py-1 rounded hover:bg-zinc-800/40 transition">
                  {g.id} · {g.entry_date} · {g.description} · {money(g.amount)}
                </div>
              ))}
              {(recStatus?.unmatched_gl_entries ?? []).length === 0 && <div className="text-xs text-zinc-600">Nothing unmatched right now.</div>}
            </div>
          </div>

          <div className={cardClass}>
            <h3 className="text-sm mb-2">Bank transaction history</h3>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <label className="text-xs">Find a bank transaction<WorkInput value={bankSearch} onChange={e => { setBankSearch(e.target.value); setBankPage(0); }} placeholder="Transaction, date, description or GL entry" className={`block w-full rounded-md border px-2 py-1 mt-1 ${textClass}`} /></label>
              <label className="text-xs">Transaction status<WorkSelect value={bankStatus} onChange={e => { setBankStatus(e.target.value); setBankPage(0); }} className={`block w-full rounded-md border px-2 py-1 mt-1 ${textClass}`}>
                <option value="">All statuses</option><option value="unmatched">Unmatched</option><option value="matched">Matched</option><option value="reviewed">Reviewed</option>
              </WorkSelect></label>
            </div>
            <div className="space-y-2">
              {bankHistory.rows.map(t => <article key={t.id} className="text-xs p-2 rounded border border-zinc-500/30">
                <div className="flex justify-between gap-2"><strong>{t.transaction_date} · {t.description}</strong><span>{money(t.amount)}</span></div>
                <p>{t.id} · {t.status}{t.matched_gl_entry_id ? ` · GL entry ${t.matched_gl_entry_id}` : ""}</p>
                {t.basis?.startsWith("simulated") && <SimBadge />}
                {t.disclaimer && <p className="text-purple-400">{t.disclaimer}</p>}
              </article>)}
              {!bankHistory.total && <p className="text-xs">{bankSearch || bankStatus ? "No matching transactions. Clear your search or choose All statuses." : "No bank transactions loaded."}</p>}
            </div>
            <CollectionPagination label="Bank transactions" total={bankHistory.total} page={bankHistory.current} pageSize={4} onPageChange={setBankPage} busy={busy || detailState.loading}/>
          </div>
        </div>
      )}
    </div>
  );
}
