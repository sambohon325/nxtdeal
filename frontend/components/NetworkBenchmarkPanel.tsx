"use client";
import { WorkSelect } from "./WorkspaceUi";

// The Network page's real cross-dealer benchmarking + AI self-audit (2026-07-13,
// session 38). Sam: "the network is a collection of other dealers... applying
// department intelligence and its kpi reports pulled from other NXTDeal dealers
// (blind labeled for anonymity) so that dealers can see area and industry trends as
// well as an ai driven audit on their dealership to see where they need to improve...
// this ties into the employee/bot data as well... This also needs to include the
// prediction scales... The entire idea of the network is to replace the twenty
// groups." Mounted directly (always-visible, not chat-gated) in /network's main
// content area, replacing the old static "Inventory Turn Opportunity 93%" mock cards.
// Reuses Department Intelligence's exact ACL tier (ADMIN/OPERATIONS/FINANCE, see
// core/network_api.py).
//
// Enriched 2026-07-18 (Intelligence Network reframe, slice 2 -- Peer Groups +
// Benchmarks, Sam: "This becomes the digital version of a dealer 20 Group"): a real
// Peer Pool selector (core/network_benchmark.py's PEER_POOLS -- Standard/OEM Peers/
// Local Market Peers/NXTDeal Elite Group/Similar Revenue Stores, every non-default
// pool a distinct SIMULATED distribution, clearly labeled, never presented as real
// cross-dealer data) re-fetches the whole benchmark board against the selected pool.
// A real new "bhph" department (Delinquency/Repo Rate/Recovery Rate/Yield/
// Charge-Offs -- 100% real current-dealer data vs. a SIMULATED industry-range peer
// pool) now appears in the same card grid automatically, no special-casing needed
// since the backend already returns it as one more entry in `departments`.

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

type NetworkKpi = {
  key: string;
  label: string;
  value: number | string;
  format: string;
  suffix?: string | null;
};

type NetworkDealerCard = {
  label: string;
  kpis: Record<string, NetworkKpi>;
  basis?: string;
};

type NetworkBenchmark = {
  department: string;
  title: string;
  primary_kpi: string;
  primary_kpi_note?: string;
  peer_pool?: string;
  peer_pool_label?: string;
  peer_pool_description?: string;
  this_dealer: NetworkDealerCard;
  peers: NetworkDealerCard[];
  percentile_rank: number | null;
  basis_notice: string;
};

type PeerPool = {
  key: string;
  label: string;
  description: string;
  peer_count: number;
  basis: string;
};

type NetworkRecommendation = {
  category: string;
  department: string | null;
  severity: "high" | "medium" | "low";
  finding: string;
  recommendation: string;
  basis: string;
};

function formatKpiValue(kpi: NetworkKpi | undefined): string {
  if (!kpi) return "—";
  const value = kpi.value;

  if (kpi.format === "currency") return `$${Number(value).toLocaleString()}`;
  if (kpi.format === "percent") return `${value}%`;

  return `${value}${kpi.suffix ?? ""}`;
}

function severityColor(severity: string) {
  if (severity === "high") return "text-[#EE3C25]";
  if (severity === "medium") return "text-[#FBCF09]";
  return "text-zinc-500";
}

export function NetworkBenchmarkPanel({ canViewNetwork, hideAssistant = false }: { canViewNetwork: boolean; hideAssistant?: boolean }) {
  const [benchmarks, setBenchmarks] = useState<NetworkBenchmark[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [recommendations, setRecommendations] = useState<NetworkRecommendation[]>([]);
  const [peerPools, setPeerPools] = useState<PeerPool[]>([]);
  const [peerPool, setPeerPool] = useState<string>("default");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!canViewNetwork) return;

    async function loadPools() {
      try {
        const res = await fetch(`${API_BASE}/network/peer-pools`, { headers: { ...authHeaders() } });
        const data = await res.json();
        if (res.ok && Array.isArray(data)) setPeerPools(data as PeerPool[]);
      } catch {
        // Non-fatal -- the selector just falls back to "default" only.
      }
    }

    loadPools();
  }, [canViewNetwork]);

  useEffect(() => {
    if (!canViewNetwork) return;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const [benchmarkResponse, auditResponse] = await Promise.all([
          fetch(`${API_BASE}/network/benchmark?peer_pool=${encodeURIComponent(peerPool)}`, {
            headers: { ...authHeaders() },
          }),
          hideAssistant ? Promise.resolve(null) : fetch(`${API_BASE}/network/audit`, { headers: { ...authHeaders() } }),
        ]);

        const benchmarkData = await benchmarkResponse.json();
        const auditData = auditResponse ? await auditResponse.json() : { recommendations: [] };

        if (!benchmarkResponse.ok || benchmarkData.error) {
          throw new Error(benchmarkData.error ?? `Backend returned ${benchmarkResponse.status}`);
        }

        setBenchmarks((benchmarkData.departments ?? []) as NetworkBenchmark[]);
        setRecommendations((auditData.recommendations ?? []) as NetworkRecommendation[]);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to reach NXTDeal backend.");
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [canViewNetwork, peerPool, hideAssistant]);

  if (!canViewNetwork) {
    return (
      <div className="bg-brand-charcoal border border-black/20 rounded-xl p-4 text-sm text-zinc-400 mb-6">
        Network benchmarks are visible to Admin, Operations, or Finance roles.
      </div>
    );
  }

  const activePool = peerPools.find((p) => p.key === peerPool);

  return (
    <div className="space-y-6 mb-8">
      <div>
        <div className="flex flex-wrap items-start justify-between gap-3 mb-3">
          <div className="text-sm text-zinc-500 max-w-2xl">
            Cross-Dealer Benchmark — how each department compares against a selected
            peer group, so you can see area and industry trends without relying on
            biased or industry-slanted reporting.
          </div>

          {peerPools.length > 0 && (
            <div className="flex flex-col items-end gap-1">
              <label className="text-xs text-zinc-500 uppercase tracking-wide">
                Peer Group
              </label>
              <WorkSelect aria-label="Peer Group"
                value={peerPool}
                onChange={(e) => setPeerPool(e.target.value)}
                className="bg-zinc-900 border border-black/30 rounded-lg text-xs px-2 py-1.5 text-white"
              >
                {peerPools.map((pool) => (
                  <option key={pool.key} value={pool.key}>
                    {pool.label} ({pool.peer_count} peers)
                  </option>
                ))}
              </WorkSelect>
            </div>
          )}
        </div>

        {activePool && (
          <div className="text-xs text-zinc-600 mb-3 max-w-3xl">
            SIMULATED — {activePool.description}
          </div>
        )}

        {loading && <div className="text-xs text-zinc-500">Loading network data…</div>}
        {error && <div className="text-xs text-[#EE3C25]">{error}</div>}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {benchmarks.map((b) => (
            <div
              key={b.department}
              className="bg-brand-charcoal border border-black/20 rounded-xl p-4 cursor-pointer"
              onClick={() => setExpanded(expanded === b.department ? null : b.department)}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="font-medium">{b.title}</div>
                {b.department === "bhph" && (
                  <span className="text-xs uppercase tracking-wide text-emerald-400 border border-emerald-800 rounded px-1.5 py-0.5">
                    Real portfolio data
                  </span>
                )}
              </div>

              <div className="text-2xl font-semibold mb-1">
                {b.percentile_rank !== null ? `${b.percentile_rank}th` : "—"}
                <span className="text-xs text-zinc-500 ml-2">percentile</span>
              </div>

              <div className="text-xs text-zinc-500 mb-1">
                {b.primary_kpi.replace(/_/g, " ")}:{" "}
                {formatKpiValue(b.this_dealer.kpis[b.primary_kpi])}
              </div>

              {expanded === b.department && (
                <div className="mt-3 pt-3 border-t border-zinc-800 space-y-2">
                  <div className="text-xs flex items-center justify-between">
                    <span className="text-cyan-400">{b.this_dealer.label}</span>
                    <span>{formatKpiValue(b.this_dealer.kpis[b.primary_kpi])}</span>
                  </div>
                  {b.peers.map((peer) => (
                    <div key={peer.label} className="text-xs flex items-center justify-between">
                      <span className="text-zinc-400">{peer.label}</span>
                      <span>{formatKpiValue(peer.kpis[b.primary_kpi])}</span>
                    </div>
                  ))}
                  {Object.values(b.this_dealer.kpis)
                    .filter((k) => k.key !== b.primary_kpi)
                    .map((k) => (
                      <div key={k.key} className="text-xs flex items-center justify-between text-zinc-500">
                        <span>{k.label}</span>
                        <span>{formatKpiValue(k)}</span>
                      </div>
                    ))}
                  {b.primary_kpi_note && (
                    <div className="text-xs text-amber-500 pt-1">{b.primary_kpi_note}</div>
                  )}
                  <div className="text-xs text-zinc-600 pt-1">{b.basis_notice}</div>
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {!hideAssistant && <div className="bg-brand-charcoal border border-black/20 rounded-xl p-4">
        <div className="font-medium mb-3">AI Dealership Audit</div>

        {recommendations.length === 0 ? (
          <div className="text-sm text-zinc-500">No recommendations right now.</div>
        ) : (
          <div className="space-y-2">
            {recommendations.map((rec, idx) => (
              <div key={idx} className="bg-brand-charcoal border border-black/20 rounded-lg p-3 text-sm">
                <div className="flex items-center justify-between mb-1">
                  <span className={`text-xs uppercase ${severityColor(rec.severity)}`}>
                    {rec.severity} · {rec.category.replace(/_/g, " ")}
                    {rec.department ? ` · ${rec.department}` : ""}
                  </span>
                  <span className="text-xs text-zinc-600">{rec.basis}</span>
                </div>
                <div className="text-zinc-300 mb-1">{rec.finding}</div>
                <div className="text-zinc-500 text-xs">{rec.recommendation}</div>
              </div>
            ))}
          </div>
        )}
      </div>}
    </div>
  );
}
