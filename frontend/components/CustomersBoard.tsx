"use client";
import { WorkButton, WorkSelect, WorkInput , WorkOverlay} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { formatCalendarDate } from "@/lib/calendarDate";
import { WorkField } from "./WorkField";

// Sales' "Customers" item -- customer-centric search + a real Customer 360, plus
// Equity Mining and a Retention Center (session 95 follow-up). Retention Center and
// Equity Mining both reuse the real Trigger Alert Timeline built for Marketing's
// Events dash (core/trigger_alerts.py, session 84) rather than a second signal
// engine -- Sales' angle on the exact same alerts (lease/loan maturity, service
// win-back, open recalls, equity position) is "who should I call to retain," not
// Marketing's "who should I promote into a new lead," but the underlying real data
// and promote/dismiss actions are identical.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState, type ReactNode } from "react";
import {
  getCustomersSummary,
  getCustomerDetail,
  searchCustomerRecords,
  type CustomersSummary,
  type CustomerDetail,
  type CustomerListItem,
} from "@/lib/customers360";
import { getAlertFeed, promoteAlert, dismissAlert, type TriggerAlert } from "@/lib/events";
import { getSalesEmployees, type SalesEmployeeBrief } from "@/lib/salesOverview";
import { NewDealModal } from "@/components/DealDeskBoard";
import type { CustomerBrief } from "@/lib/deals";
import { Customer360Panel } from "@/components/Customer360Panel";
import { CommsQuickActions } from "@/components/CommsQuickActions";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const KPI_RIBBON = PRODUCT_ACCENT_COLORS;

const URGENCY_TONE: Record<string, string> = {
  high: "border-red-900 bg-red-950/30 text-red-300",
  medium: "border-amber-900 bg-amber-950/30 text-amber-300",
  low: "border-zinc-800 bg-zinc-900/40 text-zinc-400",
};

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return formatCalendarDate(ts);
  } catch {
    return ts;
  }
}

function AlertRow({
  theme,
  alert,
  busy,
  onOpenCustomer,
  onPromote,
  onDismiss,
}: {
  theme: Theme;
  alert: TriggerAlert;
  busy: boolean;
  onOpenCustomer: (id: string) => void;
  onPromote: (alert: TriggerAlert) => void;
  onDismiss: (alert: TriggerAlert) => void;
}) {
  return (
    <div className={tc(theme, `rounded-lg border p-2.5 ${URGENCY_TONE[alert.urgency] || URGENCY_TONE.low}`, `rounded-lg border p-2.5 ${URGENCY_TONE[alert.urgency] || URGENCY_TONE.low}`)}>
      <div className="flex items-start justify-between gap-2">
        <button onClick={() => onOpenCustomer(alert.target_entity_id)} className="text-left min-w-0">
          <div className="text-xs font-medium truncate">{alert.target_name}</div>
          <div className="text-xs opacity-90 mt-0.5">{alert.headline}</div>
          {alert.basis === "heuristic" && <div className="text-xs opacity-60 mt-0.5">Estimated — not a real quote.</div>}
        </button>
        <div className="flex items-center gap-1.5 shrink-0">
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => onPromote(alert)} className="text-xs px-2 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50">
            Promote
          </WorkButton>
          <WorkButton type="submit" disabled={busy} onClick={() => onDismiss(alert)} className="text-xs px-2 py-1 rounded border border-current text-current hover:opacity-80 transition disabled:opacity-50">
            Dismiss
          </WorkButton>
        </div>
      </div>
    </div>
  );
}

function PromoteModal({
  theme,
  alert,
  onClose,
  onDone,
}: {
  theme: Theme;
  alert: TriggerAlert;
  onClose: () => void;
  onDone: () => void;
}) {
  const [employees, setEmployees] = useState<SalesEmployeeBrief[]>([]);
  const [target, setTarget] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getSalesEmployees().then(setEmployees).catch(() => setEmployees([]));
  }, []);

  async function handlePromote() {
    setBusy(true);
    setError(null);
    try {
      await promoteAlert(alert.id, target || undefined);
      onDone();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={tc(theme, "w-full max-w-sm rounded-xl border border-black/20 bg-brand-charcoal text-white p-4 space-y-3", "w-full max-w-sm rounded-xl border border-zinc-200 bg-white text-black p-4 space-y-3")}
      >
        <div className="text-sm font-brand uppercase tracking-wide">Promote to Lead</div>
        <div className="text-xs text-zinc-500">{alert.target_name} — {alert.headline}</div>
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
        <WorkField label="Transfer to employee"><WorkSelect
          value={target}
          onChange={(e) => setTarget(e.target.value)}
          className={tc(theme, "w-full text-xs rounded-md border border-zinc-700 bg-zinc-900 text-white px-2 py-1.5", "w-full text-xs rounded-md border border-zinc-300 bg-white text-black px-2 py-1.5")}
        >
          <option value="">Assign to… (optional)</option>
          {employees.map((e) => (
            <option key={e.id} value={e.id}>{e.name || e.id}{e.title ? ` — ${e.title}` : ""}</option>
          ))}
        </WorkSelect></WorkField>
        <div className="flex items-center gap-2 justify-end">
          <WorkButton type="submit" onClick={onClose} className="text-xs px-3 py-1.5 rounded text-zinc-500 hover:text-white transition">Cancel</WorkButton>
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={handlePromote} className="text-xs px-3 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            Promote to Lead
          </WorkButton>
        </div>
      </div>
    </WorkOverlay>
  );
}

export function CustomersBoard({ theme }: { theme: Theme }) {
  const [summary, setSummary] = useState<CustomersSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CustomerListItem[]>([]);
  const [openCustId, setOpenCustId] = useState<string | null>(null);
  const [promoteTarget, setPromoteTarget] = useState<TriggerAlert | null>(null);
  const [busy, setBusy] = useState(false);

  function refresh() {
    setLoading(true);
    getCustomersSummary()
      .then(setSummary)
      .catch(() => setSummary(null))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleSearch(q: string) {
    setQuery(q);
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    try {
      const res = await searchCustomerRecords(q);
      setResults(
        res.results.map((r) => ({
          id: r.id,
          name: `${r.attributes.FirstName || ""} ${r.attributes.LastName || ""}`.trim() || r.id,
          email: (r.attributes.Email as string) || null,
          phone: (r.attributes.Phone as string) || null,
        }))
      );
    } catch {
      setResults([]);
    }
  }

  async function handleDismiss(alert: TriggerAlert) {
    setBusy(true);
    try {
      await dismissAlert(alert.id);
      refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "grid grid-cols-3 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-3 gap-3 p-4 border-b border-zinc-200")}>
        {[
          { label: "Recent Customers", value: summary?.customers.length ?? 0 },
          { label: "Equity Mining Candidates", value: summary?.equity_mining.count ?? 0 },
          { label: "Retention Opportunities", value: summary?.retention_center.count ?? 0 },
        ].map((k, i) => (
          <div key={k.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5" style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }} />
            <div className="text-2xl font-semibold">{k.value}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k.label}</div>
          </div>
        ))}
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2.5", "border-b border-zinc-200 px-4 py-2.5")}>
        <WorkField label="Search customers by name/email/phone/VIN, or paste a CUST- id"><WorkInput
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="Search customers by name/email/phone/VIN, or paste a CUST- id…"
          className={tc(
            theme,
            "w-full rounded-md border border-zinc-700 bg-zinc-900 text-white placeholder:text-zinc-600 px-3 py-1.5 text-sm",
            "w-full rounded-md border border-zinc-300 bg-white text-black placeholder:text-zinc-400 px-3 py-1.5 text-sm"
          )}
        /></WorkField>
        {results.length > 0 && (
          <div className={tc(theme, "mt-1.5 border border-zinc-800 rounded-md divide-y divide-zinc-800 max-h-48 overflow-y-auto", "mt-1.5 border border-zinc-200 rounded-md divide-y divide-zinc-200 max-h-48 overflow-y-auto")}>
            {results.map((r) => (
              <WorkButton type="submit"
                key={r.id}
                onClick={() => {
                  setOpenCustId(r.id);
                  setResults([]);
                  setQuery("");
                }}
                className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-zinc-800/50 transition"
              >
                {r.name} — {r.email || r.phone || r.id}
              </WorkButton>
            ))}
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Recent Customers</div>
              <div className="grid grid-cols-2 gap-2">
                {(summary?.customers || []).map((c) => (
                  <div
                    key={c.id}
                    className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2.5", "rounded-lg border border-zinc-200 bg-zinc-50 p-2.5")}
                  >
                    <button onClick={() => setOpenCustId(c.id)} className="w-full text-left hover:opacity-80 transition">
                      <div className="text-xs font-medium truncate">{c.name || c.id}</div>
                      <div className="text-xs text-zinc-500 truncate">{c.email || c.phone || "—"}</div>
                    </button>
                    {c.phone && (
                      <div className="mt-1.5">
                        <CommsQuickActions customerId={c.id} phone={c.phone} name={c.name || undefined} size="xs" />
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Equity Mining ({summary?.equity_mining.count ?? 0})
              </div>
              {(summary?.equity_mining.alerts.length ?? 0) === 0 ? (
                <div className="text-xs text-zinc-600">No equity-mining candidates right now.</div>
              ) : (
                <div className="space-y-1.5">
                  <RecordCollection>{summary!.equity_mining.alerts.map((a) => (
                    <AlertRow key={a.id} theme={theme} alert={a} busy={busy} onOpenCustomer={setOpenCustId} onPromote={setPromoteTarget} onDismiss={handleDismiss} />
                  ))}</RecordCollection>
                </div>
              )}
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Retention Center ({summary?.retention_center.count ?? 0})
              </div>
              {(summary?.retention_center.alerts.length ?? 0) === 0 ? (
                <div className="text-xs text-zinc-600">No retention opportunities right now.</div>
              ) : (
                <div className="space-y-1.5">
                  <RecordCollection>{summary!.retention_center.alerts.map((a) => (
                    <AlertRow key={a.id} theme={theme} alert={a} busy={busy} onOpenCustomer={setOpenCustId} onPromote={setPromoteTarget} onDismiss={handleDismiss} />
                  ))}</RecordCollection>
                </div>
              )}
            </div>
          </>
        )}
      </div>

      {openCustId && (
        <CustomerDetailModal
          theme={theme}
          custId={openCustId}
          onClose={() => setOpenCustId(null)}
        />
      )}

      {promoteTarget && (
        <PromoteModal
          theme={theme}
          alert={promoteTarget}
          onClose={() => setPromoteTarget(null)}
          onDone={() => {
            setPromoteTarget(null);
            refresh();
          }}
        />
      )}
    </div>
  );
}

function CustomerDetailModal({ theme, custId, onClose }: { theme: Theme; custId: string; onClose: () => void }) {
  const [detail, setDetail] = useState<CustomerDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [newDealOpen, setNewDealOpen] = useState(false);
  const [full360Open, setFull360Open] = useState(false);

  useEffect(() => {
    setLoading(true);
    getCustomerDetail(custId)
      .then(setDetail)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [custId]);

  const attrs = detail?.customer?.attributes || {};
  const name = `${attrs.FirstName || ""} ${attrs.LastName || ""}`.trim() || custId;
  const customerBrief: CustomerBrief = {
    id: custId,
    name,
    email: (attrs.Email as string) || null,
    phone: (attrs.Phone as string) || null,
  };

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={tc(theme, "w-full max-w-2xl max-h-[88vh] flex flex-col rounded-xl border border-black/20 bg-brand-charcoal text-white shadow-2xl", "w-full max-w-2xl max-h-[88vh] flex flex-col rounded-xl border border-zinc-200 bg-white text-black shadow-2xl")}
      >
        <div className={tc(theme, "flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0", "flex items-center justify-between px-4 py-3 border-b border-zinc-200 shrink-0")}>
          <div>
            <div className="text-sm font-brand uppercase tracking-wide">{name}</div>
            <div className="text-xs text-zinc-500">{custId}</div>
          </div>
          <WorkButton type="submit" onClick={onClose} className="text-zinc-500 hover:text-white text-lg leading-none">✕</WorkButton>
        </div>

        {loading || !detail ? (
          <div className="p-4 text-sm text-zinc-500">{error || "Loading…"}</div>
        ) : (
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 grid grid-cols-2 gap-2 text-xs", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 grid grid-cols-2 gap-2 text-xs")}>
              <div><span className="text-zinc-500">Phone: </span>{String(attrs.Phone || "—")}</div>
              <div><span className="text-zinc-500">Email: </span>{String(attrs.Email || "—")}</div>
              <div><span className="text-zinc-500">City/State: </span>{String(attrs.City || "—")}, {String(attrs.State || "—")}</div>
              <div><span className="text-zinc-500">Credit Score: </span>{String(attrs.CreditScore || "—")}</div>
            </div>

            <div className="flex items-center gap-2">
              <WorkButton type="submit" variant="primary" onClick={() => setNewDealOpen(true)} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition">
                + Create Deal
              </WorkButton>
              <WorkButton type="submit" onClick={() => setFull360Open(true)} className="text-xs px-2.5 py-1 rounded bg-zinc-700 text-white hover:opacity-90 transition">
                🔗 Full Customer 360
              </WorkButton>
            </div>

            <Section title={`Vehicles Owned (${detail.customer_360.vehicles_owned.count})`} theme={theme}>
              {detail.customer_360.vehicles_owned.vehicles.map((v) => (
                <Row key={v.id} theme={theme} primary={`${v.year || ""} ${v.make || ""} ${v.model || ""}`.trim() || v.id} secondary={v.vin || v.id} />
              ))}
            </Section>

            <Section title={`Purchase History (${detail.customer_360.purchase_history.count})`} theme={theme}>
              {detail.customer_360.purchase_history.deals.map((d) => (
                <Row key={d.id} theme={theme} primary={d.id} secondary={`${d.status || "—"} · ${fmt(d.funded_at)}`} />
              ))}
            </Section>

            <Section title={`Service History (${detail.customer_360.service_history.count})`} theme={theme}>
              {detail.customer_360.service_history.records.map((s) => (
                <Row key={s.id} theme={theme} primary={s.description || s.id} secondary={fmt(s.service_date)} />
              ))}
            </Section>

            <Section title={`Finance Contracts (${detail.customer_360.finance_contracts.count})`} theme={theme}>
              {detail.customer_360.finance_contracts.contracts.map((f) => (
                <Row key={f.id} theme={theme} primary={f.id} secondary={`${f.term_months || "—"} mo · ${fmt(f.contract_date)}`} />
              ))}
            </Section>
          </div>
        )}
      </div>

      {newDealOpen && (
        <NewDealModal
          theme={theme}
          initialCustomer={customerBrief}
          onClose={() => setNewDealOpen(false)}
          onCreated={() => setNewDealOpen(false)}
        />
      )}

      {full360Open && <Customer360Panel theme={theme} customerId={custId} onClose={() => setFull360Open(false)} />}
    </WorkOverlay>
  );
}

function Section({ title, theme, children }: { title: string; theme: Theme; children: ReactNode }) {
  const items = Array.isArray(children) ? children : [children];
  const hasContent = items.some((c) => c);
  return (
    <div>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">{title}</div>
      {!hasContent ? (
        <div className="text-xs text-zinc-600">None on file.</div>
      ) : (
        <div className="space-y-1">{children}</div>
      )}
    </div>
  );
}

function Row({ theme, primary, secondary }: { theme: Theme; primary: string; secondary: string }) {
  return (
    <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2 flex items-center justify-between gap-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-2 flex items-center justify-between gap-2")}>
      <div className="text-xs truncate">{primary}</div>
      <div className="text-xs text-zinc-500 shrink-0">{secondary}</div>
    </div>
  );
}
