"use client";
import { WorkButton } from "./WorkspaceUi";

// Readiness' "Data Health" Top Menu item, GREATLY EXPANDED -- Sam: "This is what
// the current screen appears focused on. I'd keep it but greatly expand it."
// core/data_health.py composes 4 new real sections (Integration Monitoring, Data
// Completeness, Data Accuracy, Data Freshness) on top of the pre-existing
// Connected Systems/Historical Coverage view (still reachable via the generic
// /menu/data?department=Readiness&item_key=data_health path, unchanged). Every
// number here is a real count off the live graph -- where this data model has no
// genuine backing signal (Pricing Discrepancies), that's stated plainly rather
// than fabricated; see core/data_health.py's own module docstring for the full
// reasoning, including why FinanceContract.SalePrice-vs-Vehicle.Price isn't
// treated as a discrepancy. ADMIN/OPERATIONS-only.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { getDataHealthOverview, type DataHealthOverview, type FieldGap, type DuplicateGroup } from "@/lib/dataHealth";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function fmtNum(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

function fmtPct(value: unknown): string {
  if (value === null || value === undefined || typeof value !== "number") return "—";
  return `${value.toFixed(1)}%`;
}

function fmtDate(value?: string | null): string {
  if (!value) return "never";
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function GapBadge() {
  return <span className="ml-1.5 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide bg-zinc-800 text-zinc-500">gap</span>;
}

function RealBadge() {
  return <span className="ml-1.5 px-1.5 py-0.5 rounded text-xs uppercase tracking-wide bg-emerald-950/40 text-emerald-300">real</span>;
}

function SectionCard({
  theme,
  title,
  color,
  children,
}: {
  theme: Theme;
  title: string;
  color: string;
  children: React.ReactNode;
}) {
  return (
    <div className={tc(theme, "relative overflow-hidden rounded-lg border border-zinc-800 bg-brand-charcoal p-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-white p-4")}>
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: color }} />
      <div className="pl-2">
        <div className="text-sm font-brand font-semibold mb-3">{title}</div>
        {children}
      </div>
    </div>
  );
}

function FieldGapRow({ label, gap }: { label: string; gap?: FieldGap }) {
  if (!gap) return null;
  const bad = gap.missing_count > 0;
  return (
    <div className="flex items-center justify-between py-1 border-b border-zinc-800/60 last:border-0">
      <span className="text-xs text-zinc-400">{label}</span>
      <span className={`text-xs font-medium ${bad ? "text-amber-300" : "text-emerald-300"}`}>
        {fmtNum(gap.missing_count)} / {fmtNum(gap.total_count)} missing{gap.missing_pct !== null ? ` (${fmtPct(gap.missing_pct)})` : ""}
      </span>
    </div>
  );
}

function DuplicateGroupList({ groups, theme }: { groups: DuplicateGroup[]; theme: Theme }) {
  if (groups.length === 0) {
    return <div className="text-xs text-emerald-300">0 groups found — clean.</div>;
  }
  return (
    <div className="space-y-1.5 max-h-40 overflow-y-auto">
      {groups.map((g) => (
        <div key={g.key} className={tc(theme, "rounded border border-zinc-800 bg-zinc-900/60 px-2 py-1", "rounded border border-zinc-200 bg-zinc-50 px-2 py-1")}>
          <div className="text-xs text-amber-300 mb-0.5">{g.count} records match on “{g.key}”</div>
          {g.members.map((m) => (
            <div key={m.id} className="text-xs text-zinc-500">
              {m.id} — {m.label}
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function DataHealthBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<DataHealthOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getDataHealthOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Data Health data."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), []);

  const im = data?.integration_monitoring;
  const dc = data?.data_completeness;
  const da = data?.data_accuracy;
  const df = data?.data_freshness;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "px-4 py-3 border-b border-zinc-800", "px-4 py-3 border-b border-zinc-200")}>
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-brand font-semibold">Data Health</div>
            <div className="text-xs text-zinc-500 mt-0.5">
              &quot;This is where trust in the AI begins.&quot; Integration Monitoring, Data Completeness, Data Accuracy, and
              Data Freshness — every number below is a real, live scan of the current graph.
            </div>
          </div>
          <WorkButton type="submit" onClick={refresh} className="ml-3 shrink-0 px-2.5 py-1 rounded text-xs bg-zinc-800 text-zinc-200 hover:bg-zinc-700">
            Refresh
          </WorkButton>
        </div>
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4 space-y-3">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-3">
            {/* Integration Monitoring */}
            <SectionCard theme={theme} title="Integration Monitoring" color={RIBBON[0]}>
              <div className="text-xs text-zinc-400 mb-2">{fmtNum(im?.total_connections)} total connections</div>
              {im && Object.keys(im.by_sam_category).length === 0 ? (
                <div className="text-xs text-zinc-500">No Data Connections configured yet.</div>
              ) : (
                <div className="space-y-2">
                  {im &&
                    Object.entries(im.by_sam_category).map(([category, conns]) => (
                      <div key={category}>
                        <div className="text-xs uppercase tracking-wide text-zinc-500">{category}</div>
                        {conns.map((c) => (
                          <div key={c.id} className="flex items-center justify-between text-xs py-0.5">
                            <span className="text-zinc-300">{c.name}</span>
                            <span className={c.status === "error" ? "text-red-400" : c.status === "connected" ? "text-emerald-300" : "text-zinc-500"}>
                              {c.status}
                            </span>
                          </div>
                        ))}
                      </div>
                    ))}
                </div>
              )}
              <div className="text-xs text-zinc-600 mt-2 italic">{im?.category_mapping_note}</div>
            </SectionCard>

            {/* Data Completeness */}
            <SectionCard theme={theme} title="Data Completeness" color={RIBBON[1]}>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Missing VIN Data</div>
                  <FieldGapRow label="Vehicles" gap={dc?.missing_vin_data.vehicles} />
                  <FieldGapRow label="Repair Orders" gap={dc?.missing_vin_data.repair_orders} />
                  <FieldGapRow label="Finance Contracts" gap={dc?.missing_vin_data.finance_contracts} />
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Missing Customer Data</div>
                  <FieldGapRow label="Email" gap={dc?.missing_customer_data.email} />
                  <FieldGapRow label="Phone" gap={dc?.missing_customer_data.phone} />
                  <FieldGapRow label="First Name" gap={dc?.missing_customer_data.first_name} />
                  <FieldGapRow label="Last Name" gap={dc?.missing_customer_data.last_name} />
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Missing RO Data</div>
                  <FieldGapRow label="Technician" gap={dc?.missing_ro_data.technician} />
                  <FieldGapRow label="Description" gap={dc?.missing_ro_data.description} />
                  <FieldGapRow label="Service Date" gap={dc?.missing_ro_data.service_date} />
                  <FieldGapRow label="Customer ID" gap={dc?.missing_ro_data.customer_id} />
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Missing Contract Data</div>
                  <FieldGapRow label="APR" gap={dc?.missing_contract_data.apr} />
                  <FieldGapRow label="Amount Financed" gap={dc?.missing_contract_data.amount_financed} />
                  <FieldGapRow label="Lender Name" gap={dc?.missing_contract_data.lender_name} />
                  <FieldGapRow label="Term (Months)" gap={dc?.missing_contract_data.term_months} />
                </div>
              </div>
            </SectionCard>

            {/* Data Accuracy */}
            <SectionCard theme={theme} title="Data Accuracy" color={RIBBON[2]}>
              <div className="space-y-3">
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1 flex items-center">
                    Duplicate Customers <RealBadge />
                  </div>
                  <DuplicateGroupList groups={da?.duplicate_customers.duplicate_groups_by_email ?? []} theme={theme} />
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1 flex items-center">
                    Duplicate Vehicles <RealBadge />
                  </div>
                  <DuplicateGroupList groups={da?.duplicate_vehicles.duplicate_groups_by_vin ?? []} theme={theme} />
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1 flex items-center">
                    Pricing Discrepancies <GapBadge />
                  </div>
                  <div className="text-xs text-zinc-500">{da?.pricing_discrepancies.note}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1 flex items-center">
                    Inventory Mismatches <RealBadge />
                  </div>
                  <div className="text-xs text-zinc-300">
                    {fmtNum(da?.inventory_mismatches.sold_without_purchase_relationship)} sold vehicles with no PURCHASED relationship on file
                  </div>
                  <div className="text-xs text-zinc-600 mt-0.5">{da?.inventory_mismatches.note}</div>
                </div>
              </div>
            </SectionCard>

            {/* Data Freshness */}
            <SectionCard theme={theme} title="Data Freshness" color={RIBBON[3]}>
              <div className="space-y-3">
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Last Sync</div>
                  {df && df.last_sync.connections.length === 0 ? (
                    <div className="text-xs text-zinc-500">No connections to report sync status for.</div>
                  ) : (
                    <div className="space-y-0.5 max-h-24 overflow-y-auto">
                      {df?.last_sync.connections.map((c) => (
                        <div key={c.id} className="flex items-center justify-between text-xs">
                          <span className="text-zinc-300">{c.name}</span>
                          <span className="text-zinc-500">{fmtDate(c.last_synced_at ?? c.last_test_at)}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Records Updated (last 24h)</div>
                  <div className="text-lg font-semibold">{fmtNum(df?.records_updated_last_24h.total)}</div>
                  <div className="text-xs text-zinc-500">
                    {fmtNum(df?.records_updated_last_24h.by_entity_type.deals)} deals ·{" "}
                    {fmtNum(df?.records_updated_last_24h.by_entity_type.vehicles)} vehicles ·{" "}
                    {fmtNum(df?.records_updated_last_24h.by_entity_type.repair_orders)} repair orders
                  </div>
                  <div className="text-xs text-zinc-600 mt-0.5 italic">
                    Customers and Finance Contracts have no update-timestamp field in this data model — not included.
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-wide text-zinc-500 mb-1">Pending Changes</div>
                  <div className="grid grid-cols-2 gap-1">
                    <div className="text-xs text-zinc-300">Campaigns: {fmtNum(df?.pending_changes.campaigns.count)}</div>
                    <div className="text-xs text-zinc-300">Assets: {fmtNum(df?.pending_changes.assets.count)}</div>
                    <div className="text-xs text-zinc-300">Websites: {fmtNum(df?.pending_changes.websites.count)}</div>
                    <div className="text-xs text-zinc-300">Financing: {fmtNum(df?.pending_changes.financing.count)}</div>
                  </div>
                </div>
              </div>
            </SectionCard>
          </div>
        )}
      </div>
    </div>
  );
}
