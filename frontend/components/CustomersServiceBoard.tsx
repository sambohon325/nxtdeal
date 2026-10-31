"use client";
import { WorkButton, WorkInput , WorkStat, WorkOverlay} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { formatCalendarDate } from "@/lib/calendarDate";
import { WorkField } from "./WorkField";

// Service department's "Customers" item, fourth slice of Service's rebuild --
// Sam's own framing: "Service should be relationship-driven." A real Customer
// Service Profile (Vehicles Owned with warranty/recall status, Service
// History, Declined Services, Retention metrics), Lost Customer Recovery, and
// a Declined Services feed (Sam: "one of the biggest profit drivers"), each
// declined record opening the real RO Workspace (RepairOrderWorkspaceBoard.tsx)
// for a one-click follow-up via its Communication Center.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { CommsQuickActions } from "@/components/CommsQuickActions";
import {
  getCustomer360,
  getLostCustomerRecovery,
  getDeclinedServices,
  type CustomerServiceProfile,
  type LostCustomerRecovery,
  type DeclinedServices,
} from "@/lib/serviceCustomers";
import { searchCustomers, type CustomerBrief } from "@/lib/deals";
import { getRoCatalog, type RoCatalog } from "@/lib/repairOrders";
import { RoWorkspaceModal } from "@/components/RepairOrderWorkspaceBoard";
import { promoteToSales } from "@/lib/serviceSalesHandoff";
import { Customer360Panel } from "@/components/Customer360Panel";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return formatCalendarDate(ts);
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string | number; color: string }) { return <WorkStat label={label} value={value}/>; }

function Section({ title, theme, empty, children }: { title: string; theme: Theme; empty: boolean; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">{title}</div>
      {empty ? <div className="text-xs text-zinc-600">None on file.</div> : <div className="space-y-1">{children}</div>}
    </div>
  );
}

function Row({ theme, primary, secondary, onClick }: { theme: Theme; primary: string; secondary: string; onClick?: () => void }) {
  const cls = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2 flex items-center justify-between gap-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-2 flex items-center justify-between gap-2");
  const content = (
    <>
      <div className="text-xs truncate">{primary}</div>
      <div className="text-xs text-zinc-500 shrink-0">{secondary}</div>
    </>
  );
  return onClick ? (
    <WorkButton type="submit" onClick={onClick} className={`${cls} w-full text-left hover:border-brand-blue/60 transition`}>{content}</WorkButton>
  ) : (
    <div className={cls}>{content}</div>
  );
}

function CustomerDetailModal({ theme, custId, onClose, onOpenRo }: { theme: Theme; custId: string; onClose: () => void; onOpenRo: (roId: string) => void }) {
  const [detail, setDetail] = useState<CustomerServiceProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [full360Open, setFull360Open] = useState(false);

  useEffect(() => {
    setLoading(true);
    getCustomer360(custId)
      .then(setDetail)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [custId]);

  return (
    <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className={tc(theme, "w-full max-w-2xl max-h-[88vh] flex flex-col rounded-xl border border-black/20 bg-brand-charcoal text-white shadow-2xl", "w-full max-w-2xl max-h-[88vh] flex flex-col rounded-xl border border-zinc-200 bg-white text-black shadow-2xl")}
      >
        <div className={tc(theme, "flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0", "flex items-center justify-between px-4 py-3 border-b border-zinc-200 shrink-0")}>
          <div>
            <div className="text-sm font-brand uppercase tracking-wide">{detail?.customer.name || custId}</div>
            <div className="text-xs text-zinc-500">{custId}</div>
            {detail?.customer.phone && (
              <div className="mt-1.5">
                <CommsQuickActions customerId={custId} phone={detail.customer.phone} name={detail.customer.name} size="xs" />
              </div>
            )}
          </div>
          <WorkButton type="submit" onClick={onClose} className="text-zinc-500 hover:text-white text-lg leading-none">✕</WorkButton>
        </div>

        {loading || !detail ? (
          <div className="p-4 text-sm text-zinc-500">{error || "Loading…"}</div>
        ) : (
          <div className="flex-1 overflow-y-auto p-4 space-y-4">
            <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 grid grid-cols-2 gap-2 text-xs", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 grid grid-cols-2 gap-2 text-xs")}>
              <div><span className="text-zinc-500">Phone: </span>{detail.customer.phone || "—"}</div>
              <div><span className="text-zinc-500">Email: </span>{detail.customer.email || "—"}</div>
              <div><span className="text-zinc-500">Last Visit: </span>{fmt(detail.retention.last_visit)}</div>
              <div><span className="text-zinc-500">Avg Spend: </span>{money(detail.retention.average_spend)}</div>
              <div><span className="text-zinc-500">Total Visits: </span>{detail.retention.visit_count}</div>
              <div><span className="text-zinc-500">Visits / Year: </span>{detail.retention.visits_per_year ?? "—"}</div>
            </div>

            <WorkButton type="submit" onClick={() => setFull360Open(true)} className="text-xs px-2.5 py-1 rounded bg-zinc-700 text-white hover:opacity-90 transition">
              🔗 Full Customer 360
            </WorkButton>

            <Section title={`Vehicles Owned (${detail.vehicles_owned.count})`} theme={theme} empty={detail.vehicles_owned.count === 0}>
              {detail.vehicles_owned.vehicles.map((v) => (
                <Row
                  key={v.id}
                  theme={theme}
                  primary={`${v.year || ""} ${v.make || ""} ${v.model || ""}`.trim() || v.id}
                  secondary={`${v.warranty_status.status.replace(/_/g, " ")}${v.recall_status.count ? ` · ${v.recall_status.count} open recall(s)` : ""}`}
                />
              ))}
            </Section>

            <Section title={`Service History (${detail.service_history.count})`} theme={theme} empty={detail.service_history.count === 0}>
              <RecordCollection>{detail.service_history.records.map((s) => (
                <Row key={s.id} theme={theme} primary={s.description || s.id} secondary={`${fmt(s.service_date)} · ${money(typeof s.cost === "string" ? parseFloat(s.cost) : s.cost)}`} />
              ))}</RecordCollection>
            </Section>

            <Section title={`Declined Services (${detail.declined_services.count})`} theme={theme} empty={detail.declined_services.count === 0}>
              {detail.declined_services.records.map((d) => (
                <Row
                  key={d.ro_id}
                  theme={theme}
                  primary={d.description || d.ro_id}
                  secondary={`${money(d.amount)} · ${d.decline_reason || "no reason given"}`}
                  onClick={() => onOpenRo(d.ro_id)}
                />
              ))}
            </Section>
          </div>
        )}
      </div>

      {full360Open && <Customer360Panel theme={theme} customerId={custId} onClose={() => setFull360Open(false)} />}
    </WorkOverlay>
  );
}

export function CustomersServiceBoard({ theme }: { theme: Theme }) {
  const [lost, setLost] = useState<LostCustomerRecovery | null>(null);
  const [declined, setDeclined] = useState<DeclinedServices | null>(null);
  const [catalog, setCatalog] = useState<RoCatalog | null>(null);
  const [loading, setLoading] = useState(true);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CustomerBrief[]>([]);
  const [openCustId, setOpenCustId] = useState<string | null>(null);
  const [openRoId, setOpenRoId] = useState<string | null>(null);
  const [handoffBusyId, setHandoffBusyId] = useState<string | null>(null);
  const [handoffDoneIds, setHandoffDoneIds] = useState<Set<string>>(new Set());
  const [handoffError, setHandoffError] = useState<string | null>(null);

  async function handoffToSales(roId: string) {
    setHandoffBusyId(roId);
    setHandoffError(null);
    try {
      await promoteToSales(roId, "declined_service");
      setHandoffDoneIds((prev) => new Set(prev).add(roId));
    } catch (e) {
      setHandoffError((e as Error).message);
    } finally {
      setHandoffBusyId(null);
    }
  }

  function refresh() {
    setLoading(true);
    Promise.all([getLostCustomerRecovery(), getDeclinedServices(), getRoCatalog()])
      .then(([l, d, c]) => { setLost(l); setDeclined(d); setCatalog(c); })
      .catch(() => { setLost(null); setDeclined(null); })
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleSearch(q: string) {
    setQuery(q);
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    if (q.toUpperCase().startsWith("CUST-")) {
      setOpenCustId(q.toUpperCase());
      setQuery("");
      setResults([]);
      return;
    }
    try {
      setResults(await searchCustomers(q));
    } catch {
      setResults([]);
    }
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "grid grid-cols-3 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-3 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Lost Customers (12mo+)" value={lost?.count ?? 0} color={RIBBON[3]} />
        <Kpi theme={theme} label="Declined Services" value={declined?.count ?? 0} color={RIBBON[2]} />
        <Kpi theme={theme} label="Declined Value" value={money(declined?.total_value)} color={RIBBON[0]} />
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2.5", "border-b border-zinc-200 px-4 py-2.5")}>
        <WorkField label="Search customers by name/email/phone, or paste a CUST- id"><WorkInput
          value={query}
          onChange={(e) => handleSearch(e.target.value)}
          placeholder="Search customers by name/email/phone, or paste a CUST- id…"
          className={tc(
            theme,
            "w-full rounded-md border border-zinc-700 bg-zinc-900 text-white placeholder:text-zinc-600 px-3 py-1.5 text-sm",
            "w-full rounded-md border border-zinc-300 bg-white text-black placeholder:text-zinc-400 px-3 py-1.5 text-sm"
          )}
        /></WorkField>
        {results.length > 0 && (
          <div className={tc(theme, "mt-1.5 border border-zinc-800 rounded-md divide-y divide-zinc-800 max-h-48 overflow-y-auto", "mt-1.5 border border-zinc-200 rounded-md divide-y divide-zinc-200 max-h-48 overflow-y-auto")}>
            <RecordCollection>{results.map((r) => (
              <WorkButton type="submit"
                key={r.id}
                onClick={() => { setOpenCustId(r.id); setResults([]); setQuery(""); }}
                className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-zinc-800/50 transition"
              >
                {r.name} — {r.email || r.phone || r.id}
              </WorkButton>
            ))}</RecordCollection>
          </div>
        )}
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-5">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <>
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Lost Customer Recovery — no service in 12+ months ({lost?.count ?? 0})
              </div>
              {(lost?.customers.length ?? 0) === 0 ? (
                <div className="text-xs text-zinc-600">No lost customers right now.</div>
              ) : (
                <div className="space-y-1">
                  <RecordCollection>{lost!.customers.map((c) => (
                    <Row
                      key={c.customer_id}
                      theme={theme}
                      primary={c.name || c.customer_id}
                      secondary={`Last visit ${fmt(c.last_visit)} · ${c.days_since_last_visit}d ago · ${c.total_visits} past visits`}
                      onClick={() => setOpenCustId(c.customer_id)}
                    />
                  ))}</RecordCollection>
                </div>
              )}
              {lost && (
                <div className="text-xs text-zinc-600 italic mt-1.5">
                  Warranty Expired and Missed Maintenance aren&apos;t tracked yet — no warranty-term or service-interval data exists in this system.
                </div>
              )}
            </div>

            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">
                Declined Services ({declined?.count ?? 0} · {money(declined?.total_value)} at risk)
              </div>
              {handoffError && <div className="text-xs text-red-400 mb-1">{handoffError}</div>}
              {(declined?.records.length ?? 0) === 0 ? (
                <div className="text-xs text-zinc-600">No declined estimates right now.</div>
              ) : (
                <div className="space-y-1">
                  <RecordCollection>{declined!.records.map((d) => (
                    <div key={d.ro_id} className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-2 flex items-center justify-between gap-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-2 flex items-center justify-between gap-2")}>
                      <button onClick={() => setOpenRoId(d.ro_id)} className="flex-1 min-w-0 text-left">
                        <div className="text-xs truncate">{d.customer_name || d.customer_id || "—"} — {d.description || d.ro_id}</div>
                        <div className="text-xs text-zinc-500">{money(d.amount)} · {d.vehicle || "—"} · {d.decline_reason || "no reason given"}</div>
                      </button>
                      {handoffDoneIds.has(d.ro_id) ? (
                        <span className="text-xs text-green-400 shrink-0">✅ Handed off</span>
                      ) : (
                        <WorkButton type="submit" variant="primary"
                          disabled={handoffBusyId === d.ro_id}
                          onClick={() => handoffToSales(d.ro_id)}
                          className="text-xs px-2 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50 shrink-0"
                        >
                          🤝 Hand off to Sales
                        </WorkButton>
                      )}
                    </div>
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
          onOpenRo={(roId) => { setOpenCustId(null); setOpenRoId(roId); }}
        />
      )}

      {openRoId && catalog && (
        <RoWorkspaceModal
          theme={theme}
          roId={openRoId}
          catalog={catalog}
          onClose={() => setOpenRoId(null)}
          onChanged={refresh}
        />
      )}
    </div>
  );
}
