"use client";
import { WorkButton , WorkStat} from "./WorkspaceUi";
import {RecordTable} from "./RecordTable";

// Marketing's "Analytics" Top Menu item (Marketing Growth Platform, session 113
// follow-up) -- the Attribution Engine + Marketing ROI Dashboard + Vehicle
// Attribution capstone. Sam's own framing: most valuable "once other channels
// are feeding it real event data," now true after the CRM/PURLs/Email-SMS
// slices this same rebuild arc already shipped.
//
// Three real, honestly-labeled views: Channel Mix (real, first-touch-only
// attribution off each Lead's own Source field), Campaign & PURL ROI (rolls up
// the two per-channel revenue-correlation engines those slices already built),
// and Vehicle Attribution (real Campaign/SocialPost marketing signals
// cross-referenced against real funded-Deal sales by Make/Model). See
// core/marketing_attribution.py's module docstring for the full honesty notes
// -- every number here is a real correlation, never proven multi-touch
// causation, and every disclaimer string below is surfaced verbatim from the
// backend rather than summarized away.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  fetchChannelMix,
  fetchMarketingRoiDashboard,
  fetchVehicleAttribution,
  type ChannelMix,
  type MarketingRoiDashboard,
  type VehicleAttribution,
} from "@/lib/marketingAttribution";

type Theme = "dark" | "light";
type Tab = "channel_mix" | "roi" | "vehicle";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function fmtCurrency(n: number): string {
  return n.toLocaleString(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function DisclaimerBanner({ theme, text }: { theme: Theme; text: string }) {
  return (
    <div className={tc(theme, "text-xs leading-snug px-3 py-2 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-300", "text-xs leading-snug px-3 py-2 rounded-lg bg-amber-50 border border-amber-300 text-amber-700")}>
      {text}
    </div>
  );
}

function TabButton({ theme, active, onClick, label }: { theme: Theme; active: boolean; onClick: () => void; label: string }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      className={
        active
          ? "text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium"
          : tc(theme, "text-xs px-3 py-1.5 rounded-md text-zinc-400 hover:text-white transition", "text-xs px-3 py-1.5 rounded-md text-zinc-500 hover:text-black transition")
      }
    >
      {label}
    </WorkButton>
  );
}

export function AttributionBoard({ theme }: { theme: Theme }) {
  const [tab, setTab] = useState<Tab>("channel_mix");
  const [channelMix, setChannelMix] = useState<ChannelMix | null>(null);
  const [roi, setRoi] = useState<MarketingRoiDashboard | null>(null);
  const [vehicleAttr, setVehicleAttr] = useState<VehicleAttribution | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function refreshAll() {
    setLoading(true);
    setError(null);
    Promise.all([fetchChannelMix(), fetchMarketingRoiDashboard(), fetchVehicleAttribution()])
      .then(([cm, r, va]) => {
        setChannelMix(cm);
        setRoi(r);
        setVehicleAttr(va);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Couldn't load attribution data."))
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refreshAll();
  }, []);

  const totalCampaignRevenue = roi?.campaign_roi.total_revenue ?? 0;
  const totalPurlRevenue = roi?.purl_roi.total_revenue ?? 0;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-black/20 shrink-0", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200 shrink-0")}>
        <Kpi theme={theme} label="Total Leads (all sources)" value={String(channelMix?.total_leads ?? "—")} color={RIBBON[0]} />
        <Kpi theme={theme} label="Revenue by Lead Source" value={channelMix ? fmtCurrency(channelMix.total_revenue) : "—"} color={RIBBON[1]} />
        <Kpi theme={theme} label="Campaign ROI (correlated)" value={roi ? fmtCurrency(totalCampaignRevenue) : "—"} color={RIBBON[2]} />
        <Kpi theme={theme} label="PURL ROI (correlated)" value={roi ? fmtCurrency(totalPurlRevenue) : "—"} color={RIBBON[3]} />
      </div>

      <div className={tc(theme, "flex items-center gap-1.5 px-4 py-2.5 border-b border-zinc-800 shrink-0", "flex items-center gap-1.5 px-4 py-2.5 border-b border-zinc-300 shrink-0")}>
        <TabButton theme={theme} active={tab === "channel_mix"} onClick={() => setTab("channel_mix")} label="Channel Mix & ROI" />
        <TabButton theme={theme} active={tab === "roi"} onClick={() => setTab("roi")} label="Campaign & PURL ROI" />
        <TabButton theme={theme} active={tab === "vehicle"} onClick={() => setTab("vehicle")} label="Vehicle Attribution" />
        <WorkButton type="submit" onClick={refreshAll} className={tc(theme, "ml-auto text-xs text-zinc-500 hover:text-white transition", "ml-auto text-xs text-zinc-500 hover:text-black transition")}>
          {loading ? "Loading…" : "↻ Refresh"}
        </WorkButton>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-3">
        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        {tab === "channel_mix" && channelMix && (
          <>
            <DisclaimerBanner theme={theme} text={channelMix.disclaimer} />
            <div className={tc(theme, "rounded-lg border border-zinc-800 overflow-hidden", "rounded-lg border border-zinc-300 overflow-hidden")}>
              <RecordTable className="w-full text-xs">
                <thead>
                  <tr className={tc(theme, "bg-zinc-900 text-zinc-400", "bg-zinc-100 text-zinc-600")}>
                    <th className="text-left px-3 py-2 font-semibold">Source</th>
                    <th className="text-right px-3 py-2 font-semibold">Leads</th>
                    <th className="text-right px-3 py-2 font-semibold">Sold</th>
                    <th className="text-right px-3 py-2 font-semibold">Conv. Rate</th>
                    <th className="text-right px-3 py-2 font-semibold">Funded Deals</th>
                    <th className="text-right px-3 py-2 font-semibold">Revenue</th>
                    <th className="text-right px-3 py-2 font-semibold">Rev / Lead</th>
                  </tr>
                </thead>
                <tbody>
                  {channelMix.channels.map((c) => (
                    <tr key={c.source} className={tc(theme, "border-t border-zinc-800", "border-t border-zinc-200")}>
                      <td className="px-3 py-1.5 font-medium">{c.source}</td>
                      <td className="px-3 py-1.5 text-right">{c.lead_count}</td>
                      <td className="px-3 py-1.5 text-right">{c.sold_count}</td>
                      <td className="px-3 py-1.5 text-right">{c.conversion_rate}%</td>
                      <td className="px-3 py-1.5 text-right">{c.funded_deals_count}</td>
                      <td className="px-3 py-1.5 text-right text-brand-teal font-semibold">{fmtCurrency(c.revenue)}</td>
                      <td className="px-3 py-1.5 text-right">{fmtCurrency(c.revenue_per_lead)}</td>
                    </tr>
                  ))}
                  {channelMix.channels.length === 0 && (
                    <tr>
                      <td colSpan={7} className={tc(theme, "px-3 py-6 text-center text-zinc-600", "px-3 py-6 text-center text-zinc-500")}>
                        No leads yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </RecordTable>
            </div>
          </>
        )}

        {tab === "roi" && roi && (
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-2">
              <div className={tc(theme, "text-xs font-bold uppercase tracking-wide text-zinc-400", "text-xs font-bold uppercase tracking-wide text-zinc-500")}>
                Campaign ROI
              </div>
              <DisclaimerBanner theme={theme} text={roi.campaign_roi.disclaimer} />
              <div className={tc(theme, "rounded-lg border border-zinc-800 divide-y divide-zinc-800", "rounded-lg border border-zinc-300 divide-y divide-zinc-200")}>
                {roi.campaign_roi.campaigns.map((c) => (
                  <div key={c.campaign_id} className="px-3 py-2 flex items-center justify-between text-xs">
                    <div>
                      <div className="font-medium">{c.name}</div>
                      <div className="text-xs text-zinc-500">{c.campaign_type} · {c.channel} · {c.campaign_id}</div>
                    </div>
                    <div className="text-right">
                      <div className="text-brand-teal font-semibold">{fmtCurrency(c.revenue)}</div>
                      <div className="text-xs text-zinc-500">{c.funded_deals_count} deals / {c.leads_sold_count} leads sold</div>
                    </div>
                  </div>
                ))}
                {roi.campaign_roi.campaigns.length === 0 && (
                  <div className={tc(theme, "px-3 py-6 text-center text-xs text-zinc-600", "px-3 py-6 text-center text-xs text-zinc-500")}>
                    No activated/completed campaigns yet.
                  </div>
                )}
              </div>
            </div>

            <div className="space-y-2">
              <div className={tc(theme, "text-xs font-bold uppercase tracking-wide text-zinc-400", "text-xs font-bold uppercase tracking-wide text-zinc-500")}>
                PURL ROI
              </div>
              <DisclaimerBanner theme={theme} text={roi.purl_roi.disclaimer} />
              <div className={tc(theme, "rounded-lg border border-zinc-800 divide-y divide-zinc-800", "rounded-lg border border-zinc-300 divide-y divide-zinc-200")}>
                {roi.purl_roi.purls.map((p) => (
                  <div key={p.purl_id} className="px-3 py-2 flex items-center justify-between text-xs">
                    <div>
                      <div className="font-medium">{p.purl_id}</div>
                      <div className="text-xs text-zinc-500">{p.visits} visits{p.lead_generated ? " · lead generated" : ""}</div>
                    </div>
                    <div className="text-brand-teal font-semibold">{fmtCurrency(p.revenue)}</div>
                  </div>
                ))}
                {roi.purl_roi.purls.length === 0 && (
                  <div className={tc(theme, "px-3 py-6 text-center text-xs text-zinc-600", "px-3 py-6 text-center text-xs text-zinc-500")}>
                    No PURLs generated yet.
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {tab === "vehicle" && vehicleAttr && (
          <>
            <DisclaimerBanner theme={theme} text={vehicleAttr.disclaimer} />
            <div className="grid grid-cols-3 gap-3">
              <Kpi theme={theme} label="Marketed & Sold" value={String(vehicleAttr.marketed_and_sold_count)} color={RIBBON[0]} />
              <Kpi theme={theme} label="Marketed, Not Yet Sold" value={String(vehicleAttr.marketed_not_sold_count)} color={RIBBON[1]} />
              <Kpi theme={theme} label="Sold, Not Marketed" value={String(vehicleAttr.sold_not_marketed_count)} color={RIBBON[2]} />
            </div>
            <div className={tc(theme, "rounded-lg border border-zinc-800 overflow-hidden", "rounded-lg border border-zinc-300 overflow-hidden")}>
              <RecordTable className="w-full text-xs">
                <thead>
                  <tr className={tc(theme, "bg-zinc-900 text-zinc-400", "bg-zinc-100 text-zinc-600")}>
                    <th className="text-left px-3 py-2 font-semibold">Make / Model</th>
                    <th className="text-right px-3 py-2 font-semibold">Campaign Mentions</th>
                    <th className="text-right px-3 py-2 font-semibold">Social Mentions</th>
                    <th className="text-right px-3 py-2 font-semibold">Funded Deals</th>
                    <th className="text-right px-3 py-2 font-semibold">Gross Revenue</th>
                    <th className="text-right px-3 py-2 font-semibold">Marketed?</th>
                  </tr>
                </thead>
                <tbody>
                  {vehicleAttr.rows.map((r, i) => (
                    <tr key={`${r.make}-${r.model}-${i}`} className={tc(theme, "border-t border-zinc-800", "border-t border-zinc-200")}>
                      <td className="px-3 py-1.5 font-medium">{r.make} {r.model}</td>
                      <td className="px-3 py-1.5 text-right">{r.campaign_mentions}</td>
                      <td className="px-3 py-1.5 text-right">{r.social_mentions}</td>
                      <td className="px-3 py-1.5 text-right">{r.funded_deals_count}</td>
                      <td className="px-3 py-1.5 text-right text-brand-teal font-semibold">{fmtCurrency(r.gross_revenue)}</td>
                      <td className="px-3 py-1.5 text-right">
                        {r.marketed ? (
                          <span className="text-xs px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium">Yes</span>
                        ) : (
                          <span className={tc(theme, "text-xs px-1.5 py-0.5 rounded-full bg-zinc-700 text-zinc-300 font-medium", "text-xs px-1.5 py-0.5 rounded-full bg-zinc-200 text-zinc-600 font-medium")}>No</span>
                        )}
                      </td>
                    </tr>
                  ))}
                  {vehicleAttr.rows.length === 0 && (
                    <tr>
                      <td colSpan={6} className={tc(theme, "px-3 py-6 text-center text-zinc-600", "px-3 py-6 text-center text-zinc-500")}>
                        No marketed or sold vehicles yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </RecordTable>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
