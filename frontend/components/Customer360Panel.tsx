"use client";
import { WorkButton , WorkOverlay} from "./WorkspaceUi";

// Shared "Customer Intelligence Layer" panel (2026-07-19, Sam's own framing:
// "the single biggest feature... every department sees the same timeline"). This is
// the one real merged Customer 360 view (core/customer_360.py, Marketing Growth
// Platform kickoff, session 113) extracted out of MarketingCRMBoard.tsx's own
// Customer360Tab (previously its only frontend consumer) into a standalone,
// self-contained modal any department's board can drop in given just a customer id --
// Sales' CustomersBoard.tsx, Service's CustomersServiceBoard.tsx, and Finance's
// PortfolioBoard.tsx all render this exact same component via a "Customer record"
// entry point, layered on top of (never replacing) each department's own
// specialized view, so a real department-specific screen (Sales' Purchase History/
// "+ Create Deal", Service's warranty-and-recall/Declined Services/Hand-off-to-Sales,
// Finance's Loan Detail) keeps its own real content while every department gets a
// one-click path to the identical underlying record -- Lead History, Vehicle
// Ownership, Trade Equity, Service History, Finance History, Communication
// (Email/SMS/Call/Video), Chat, Event Attendance, Campaign Activity, Purchase
// History, Credit Applications, and Trade-Ins, plus one real chronologically-merged
// Timeline. Field-level security (core/permissions_registry.py's
// filter_sensitive_fields, e.g. masking Customer.CreditScore) is already enforced
// server-side in the payload this fetches -- nothing extra to do client-side.
import { CustomerLoyaltyPanel } from "@/components/CustomerLoyaltyPanel";
import { useEffect, useState } from "react";
import { getCustomer360, type Customer360 } from "@/lib/customer360";
import { InlineEntityFields } from "@/components/InlineEntityFields";
import { CommsQuickActions } from "@/components/CommsQuickActions";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

function fmtDate(s: string | undefined | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

export function Customer360Panel({
  theme,
  customerId,
  onClose,
  inline = false,
}: {
  theme: Theme;
  customerId: string;
  onClose: () => void;
  inline?: boolean;
}) {
  const [customer, setCustomer] = useState<Customer360 | null>(null);
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setCustomer(null);
    getCustomer360(customerId)
      .then((c) => {
        if (!cancelled) setCustomer(c);
      })
      .catch((e) => {
        if (!cancelled) setError((e as Error).message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [customerId, revision]);

  const cardClass = tc(theme, "rounded-lg border border-zinc-800 bg-zinc-950 p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");

  return (
    <WorkOverlay data-department-work="" className={inline ? "workspace-inline-editor" : "fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4"} onClick={inline ? undefined : onClose}>
      <div data-record-detail=""
        onClick={(e) => e.stopPropagation()}
        className={inline ? "workspace-editor-surface flex flex-col" : tc(
          theme,
          "w-full max-w-3xl max-h-[90vh] flex flex-col rounded-xl border border-zinc-800 bg-black text-white shadow-2xl",
          "w-full max-w-3xl max-h-[90vh] flex flex-col rounded-xl border border-zinc-200 bg-white text-black shadow-2xl"
        )}
      >
        <div className={tc(theme, "flex items-center justify-between px-4 py-3 border-b border-zinc-800 shrink-0", "flex items-center justify-between px-4 py-3 border-b border-zinc-200 shrink-0")}>
          <div>
            <div className="work-detail-title">Customer record</div>
            <div className="text-xs text-zinc-500">One record. One timeline. — {customerId}</div>
          </div>
          <WorkButton type="submit" aria-label="Close customer record" onClick={onClose} className="text-zinc-500 hover:text-white text-lg leading-none">{inline ? "← Back to workspace" : "✕"}</WorkButton>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-4">
          {error && <div role="alert" className="text-xs text-red-400">{error}<WorkButton type="submit" className="record-back" onClick={()=>setRevision(value=>value+1)}>Try again</WorkButton></div>}
          {loading && <div role="status" className="text-xs text-zinc-500">Loading customer record…</div>}

          {customer && !("error" in customer) && (
            <>
              <div className={cardClass}>
                <div className="flex items-start justify-between gap-3">
                  <div className="text-sm font-semibold">
                    {String(customer.customer.attributes.FirstName ?? "")} {String(customer.customer.attributes.LastName ?? "")}
                    <span className="text-zinc-500 ml-2 text-xs">{customer.customer.id}</span>
                    {customer.customer.attributes.Phone ? (
                      <span className="ml-2 inline-block align-middle">
                        <CommsQuickActions
                          customerId={customer.customer.id}
                          phone={String(customer.customer.attributes.Phone)}
                          name={`${String(customer.customer.attributes.FirstName ?? "")} ${String(customer.customer.attributes.LastName ?? "")}`.trim()}
                          size="xs"
                        />
                      </span>
                    ) : null}
                  </div>
                  <InlineEntityFields
                    theme={theme}
                    entityId={customer.customer.id}
                    fields={[
                      { key: "FirstName", label: "First Name", value: customer.customer.attributes.FirstName },
                      { key: "LastName", label: "Last Name", value: customer.customer.attributes.LastName },
                      { key: "Email", label: "Email", value: customer.customer.attributes.Email },
                      { key: "Phone", label: "Phone", value: customer.customer.attributes.Phone },
                    ]}
                    onSaved={(patch) =>
                      setCustomer((prev) =>
                        prev && !("error" in prev)
                          ? { ...prev, customer: { ...prev.customer, attributes: { ...prev.customer.attributes, ...patch } } }
                          : prev
                      )
                    }
                  />
                </div>
                <div className="grid grid-cols-3 gap-3 mt-2 text-xs text-zinc-500">
                  <div>Email: {String(customer.customer.attributes.Email ?? "—")}</div>
                  <div>Phone: {String(customer.customer.attributes.Phone ?? "—")}</div>
                  <div>Credit Score: {String(customer.customer.attributes.CreditScore ?? "—")} <span className="text-zinc-600">(view only — field-masked)</span></div>
                </div>
              </div>

              <div className="grid grid-cols-3 gap-3">
                {[
                  { label: "Vehicles Owned", value: customer.vehicles_owned.count },
                  { label: "Purchase History", value: customer.purchase_history.count },
                  { label: "Service History", value: customer.service_history.count },
                  { label: "Finance Contracts", value: customer.finance_contracts.count },
                  { label: "Credit Applications", value: customer.credit_applications?.count ?? 0 },
                  { label: "Trade-Ins", value: customer.trade_ins?.count ?? 0 },
                  { label: "Trade Equity Signals", value: customer.trade_equity.count },
                  { label: "Communications", value: customer.communication_activity.count },
                  { label: "Chat Sessions", value: customer.chat_activity.count },
                  { label: "Event RSVPs", value: customer.event_attendance.count },
                  { label: "Campaign Activity", value: customer.campaign_activity.count },
                ].map((s) => (
                  <div key={s.label} className={cardClass}>
                    <div className="text-lg font-semibold">{s.value}</div>
                    <div className="text-xs uppercase tracking-wide text-zinc-500">{s.label}</div>
                  </div>
                ))}
              </div>

              {customer.credit_applications && customer.credit_applications.count > 0 && (
                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Credit Applications</div>
                  <div className="space-y-1">
                    {customer.credit_applications.applications.map((a) => (
                      <div key={a.id} className="text-xs px-2 py-1.5 rounded flex items-center justify-between gap-2">
                        <span>{a.id} {a.linked_deal_id ? `· ${a.linked_deal_id}` : ""}</span>
                        <span className="text-zinc-500">{a.decision ?? a.status}{a.estimated_apr != null ? ` · ${a.estimated_apr}% APR` : ""}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {customer.trade_ins && customer.trade_ins.count > 0 && (
                <div className={cardClass}>
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Trade-Ins</div>
                  <div className="space-y-1">
                    {customer.trade_ins.trades.map((t) => (
                      <div key={t.deal_id} className="text-xs px-2 py-1.5 rounded flex items-center justify-between gap-2">
                        <span>{[t.year, t.make, t.model].filter(Boolean).join(" ") || t.deal_id}</span>
                        <span className="text-zinc-500">{t.approved ? "approved" : "pending"} {t.acv != null ? `· ACV $${t.acv}` : ""}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className={cardClass}>
                <CustomerLoyaltyPanel customerId={customerId}/><div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">One Timeline</div>
                <div className="max-h-96 overflow-y-auto space-y-1.5">
                  {customer.timeline.length === 0 ? (
                    <div className="text-xs text-zinc-600">No activity recorded yet.</div>
                  ) : (
                    customer.timeline.map((t, i) => (
                      <div key={i} className="text-xs px-2 py-1.5 rounded hover:bg-zinc-800/40 transition">
                        <div className="flex items-center justify-between">
                          <span className="font-medium capitalize">{t.type.replace(/_/g, " ")}</span>
                          <span className="text-xs text-zinc-500">{fmtDate(t.timestamp)}</span>
                        </div>
                        <div className="text-zinc-400">{t.summary}</div>
                      </div>
                    ))
                  )}
                </div>
              </div>

              <div className={cardClass}>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Not Yet Tracked (honest gaps)</div>
                <div className="space-y-1 text-xs text-zinc-500">
                  {Object.entries(customer.not_yet_tracked).map(([k, v]) => (
                    <div key={k}><span className="text-zinc-400 font-medium">{k}:</span> {v}</div>
                  ))}
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </WorkOverlay>
  );
}
