"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Loyalty / VIP Rewards board -- a staff-facing visualizer + control surface over
// core/loyalty.py's graph-native points/tier/visit/referral/reward engine (loyalty
// state stored as attributes on the existing Customer entity). Four sections: a
// program-overview KPI row, a Bronze -> Platinum tier-distribution visual scaled by
// live membership, the redeemable rewards catalog, and a per-member lookup that can
// award points, record a visit, record a referral, and redeem a reward (with a
// graceful insufficient-points error). Read/act through lib/loyalty.ts -- same shape
// and styling vocabulary as OperationsCustomerJourneyBoard.tsx (RIBBON palette,
// theme-aware classes). This module is deliberately AI-free.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState } from "react";
import {
  getLoyaltyOverview,
  getRewards,
  getMember,
  awardPoints,
  recordVisit,
  recordReferral,
  redeemReward,
  LOYALTY_TIERS,
  type LoyaltyOverview,
  type Member,
  type RewardCatalogItem,
} from "@/lib/loyalty";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

// A ribbon-derived accent color per tier. Bronze -> Platinum, cycling the RIBBON
// palette so the tier ladder reads as one branded system.
const TIER_COLOR: Record<string, string> = {
  Bronze: RIBBON[0],
  Silver: RIBBON[1],
  Gold: RIBBON[2],
  Platinum: RIBBON[3],
};

function tierColor(tier: string | null | undefined): string {
  if (!tier) return "#9CA3AF";
  return TIER_COLOR[tier] ?? "#9CA3AF";
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined) return "0";
  try {
    return n.toLocaleString();
  } catch {
    return String(n);
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

// One node in the Bronze -> Platinum tier ladder. Scales its emphasis (ring +
// count size) by this tier's share of the busiest tier, so heavier tiers visually
// pop -- the "distribution visual" idea from the slice brief.
function TierNode({
  theme,
  tier,
  count,
  maxCount,
}: {
  theme: Theme;
  tier: string;
  count: number;
  maxCount: number;
}) {
  const color = TIER_COLOR[tier] ?? RIBBON[0];
  const share = maxCount > 0 ? count / maxCount : 0;
  const scale = 1 + share * 0.18;
  const active = count > 0;
  return (
    <div className="flex flex-col items-center gap-1" style={{ transform: `scale(${scale})` }}>
      <div
        className={tc(
          theme,
          "flex flex-col items-center justify-center rounded-full border bg-brand-charcoal",
          "flex flex-col items-center justify-center rounded-full border bg-zinc-50"
        )}
        style={{
          width: 64,
          height: 64,
          borderColor: color,
          borderWidth: active ? 3 : 1,
          boxShadow: active ? `0 0 0 3px ${color}33` : undefined,
        }}
      >
        <span className="text-lg font-semibold leading-none" style={{ color }}>
          {count}
        </span>
      </div>
      <span className="text-xs font-brand uppercase tracking-wide text-zinc-500 text-center">{tier}</span>
    </div>
  );
}

function TierLadder({ theme, overview }: { theme: Theme; overview: LoyaltyOverview | null }) {
  const distribution = overview?.tier_distribution ?? {};
  const maxCount = useMemo(() => {
    const values = LOYALTY_TIERS.map((t) => distribution[t] ?? 0);
    return values.reduce((a, b) => Math.max(a, b), 0);
  }, [distribution]);

  return (
    <div className="flex items-center gap-1 overflow-x-auto py-4">
      {LOYALTY_TIERS.map((tier, i) => (
        <div key={tier} className="flex items-center gap-1">
          <TierNode theme={theme} tier={tier} count={distribution[tier] ?? 0} maxCount={maxCount} />
          {i < LOYALTY_TIERS.length - 1 && <span className="text-zinc-600 text-lg select-none">→</span>}
        </div>
      ))}
    </div>
  );
}

export function LoyaltyRewardsBoard({ theme }: { theme: Theme }) {
  const [overview, setOverview] = useState<LoyaltyOverview | null>(null);
  const [rewards, setRewards] = useState<RewardCatalogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Per-member lookup state -- distinct from the overview above.
  const [lookupId, setLookupId] = useState("");
  const [member, setMember] = useState<Member | null>(null);
  const [memberLoading, setMemberLoading] = useState(false);
  const [memberError, setMemberError] = useState<string | null>(null);
  const [actionBusy, setActionBusy] = useState(false);

  // Action inputs.
  const [awardAmount, setAwardAmount] = useState("100");
  const [awardReason, setAwardReason] = useState("");
  const [awardDept, setAwardDept] = useState("");
  const [visitDept, setVisitDept] = useState("");
  const [referredName, setReferredName] = useState("");
  const [redeemRewardId, setRedeemRewardId] = useState("");

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getLoyaltyOverview(), getRewards()])
      .then(([ov, rw]) => {
        setOverview(ov);
        setRewards(rw);
        if (rw.length > 0 && !redeemRewardId) setRedeemRewardId(rw[0].reward_id);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the loyalty overview."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  function loadMember(customerId: string) {
    const id = customerId.trim();
    if (!id) {
      setMemberError("Enter a customer id to look up.");
      return;
    }
    setMemberLoading(true);
    setMemberError(null);
    getMember(id)
      .then(setMember)
      .catch((e) => {
        setMember(null);
        setMemberError(e instanceof Error ? e.message : "Unable to load this loyalty member.");
      })
      .finally(() => setMemberLoading(false));
  }

  async function handleAward() {
    if (!member) return;
    const points = parseInt(awardAmount, 10);
    if (!Number.isFinite(points) || points <= 0) {
      setMemberError("Points to award must be a positive whole number.");
      return;
    }
    setActionBusy(true);
    setMemberError(null);
    try {
      const updated = await awardPoints(member.customer_id, points, awardReason, awardDept);
      setMember(updated);
      refresh();
    } catch (e) {
      setMemberError(e instanceof Error ? e.message : "Unable to award points.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleVisit() {
    if (!member) return;
    setActionBusy(true);
    setMemberError(null);
    try {
      const updated = await recordVisit(member.customer_id, visitDept);
      setMember(updated);
      refresh();
    } catch (e) {
      setMemberError(e instanceof Error ? e.message : "Unable to record a visit.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleReferral() {
    if (!member) return;
    const name = referredName.trim();
    if (!name) {
      setMemberError("A referral must name the person referred.");
      return;
    }
    setActionBusy(true);
    setMemberError(null);
    try {
      const updated = await recordReferral(member.customer_id, name);
      setMember(updated);
      setReferredName("");
      refresh();
    } catch (e) {
      setMemberError(e instanceof Error ? e.message : "Unable to record a referral.");
    } finally {
      setActionBusy(false);
    }
  }

  async function handleRedeem() {
    if (!member || !redeemRewardId) return;
    setActionBusy(true);
    setMemberError(null);
    try {
      const updated = await redeemReward(member.customer_id, redeemRewardId);
      setMember(updated);
      refresh();
    } catch (e) {
      // Insufficient-points (and unknown-reward) errors arrive here as the
      // backend's {"error": ...} message -- surface it plainly, don't crash.
      setMemberError(e instanceof Error ? e.message : "Unable to redeem this reward.");
    } finally {
      setActionBusy(false);
    }
  }

  const distribution = overview?.tier_distribution ?? {};

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      {/* Program overview + tier ladder */}
      <div className={tc(theme, "p-4 border-b border-zinc-800", "p-4 border-b border-zinc-200")}>
        <div className="flex items-center justify-between gap-2">
          <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">🏅 VIP Rewards Program</div>
          <WorkButton type="submit" onClick={refresh} className="text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
            ↻ Refresh
          </WorkButton>
        </div>
        {loading && <div className="text-sm text-zinc-500 mt-2">Loading…</div>}
        {error && <div className="text-sm text-red-400 mt-2">{error}</div>}
        {!loading && !error && <TierLadder theme={theme} overview={overview} />}
      </div>

      {/* Overview KPIs */}
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Members Enrolled" value={fmtNum(overview?.member_count ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Outstanding Points" value={fmtNum(overview?.total_outstanding_points ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Total Redemptions" value={fmtNum(overview?.total_redemptions ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Tiers" value={String(LOYALTY_TIERS.length)} color={RIBBON[3]} />
      </div>

      {/* Per-tier counts */}
      <div className={tc(theme, "grid grid-cols-4 gap-2 px-4 py-3 border-b border-zinc-800", "grid grid-cols-4 gap-2 px-4 py-3 border-b border-zinc-200")}>
        {LOYALTY_TIERS.map((tier) => (
          <div
            key={tier}
            className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2", "rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2")}
          >
            <div className="text-lg font-semibold" style={{ color: TIER_COLOR[tier] ?? RIBBON[0] }}>
              {distribution[tier] ?? 0}
            </div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{tier}</div>
          </div>
        ))}
      </div>

      {/* Rewards catalog */}
      <div className={tc(theme, "p-4 border-b border-zinc-800 space-y-2", "p-4 border-b border-zinc-200 space-y-2")}>
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">🎁 Rewards Catalog</div>
        {rewards.length === 0 ? (
          <div className="text-xs text-zinc-500">No rewards available.</div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            {rewards.map((reward) => (
              <div
                key={reward.reward_id}
                className={tc(theme, "rounded-md border border-zinc-800 bg-brand-charcoal px-3 py-2 flex items-center justify-between gap-2", "rounded-md border border-zinc-200 bg-zinc-50 px-3 py-2 flex items-center justify-between gap-2")}
              >
                <div className="min-w-0">
                  <div className="text-xs font-medium text-zinc-200 truncate">{reward.name}</div>
                  {reward.department && (
                    <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{reward.department}</div>
                  )}
                </div>
                <div className="text-sm font-semibold whitespace-nowrap" style={{ color: RIBBON[2] }}>
                  {fmtNum(reward.point_cost)} pts
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Per-member panel */}
      <div className="p-4 space-y-3">
        <div className="text-sm font-brand uppercase tracking-wide text-zinc-400">👤 Member Lookup</div>

        <div className="flex items-center gap-2">
          <WorkField label="Record ID"><WorkInput
            value={lookupId}
            onChange={(e) => setLookupId(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") loadMember(lookupId);
            }}
            placeholder="Customer id (e.g. CUST-00123)"
            className={tc(
              theme,
              "flex-1 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1.5 text-white",
              "flex-1 text-xs rounded border border-zinc-300 bg-white px-2 py-1.5 text-black"
            )}
          /></WorkField>
          <WorkButton type="submit"
            onClick={() => loadMember(lookupId)}
            disabled={memberLoading}
            className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50 whitespace-nowrap"
          >
            {memberLoading ? "Loading…" : "Look Up"}
          </WorkButton>
        </div>

        {memberError && <div className="text-sm text-red-400">{memberError}</div>}

        {member && (
          <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-3")}>
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-medium text-zinc-200 truncate">{member.name ?? member.customer_id}</div>
                <div className="text-xs text-zinc-500">{member.customer_id}</div>
              </div>
              <div className="text-right">
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Tier</div>
                <div className="text-sm font-semibold" style={{ color: tierColor(member.tier) }}>
                  {member.tier ?? "—"}
                </div>
              </div>
            </div>

            {/* Member stat tiles */}
            <div className="grid grid-cols-4 gap-2">
              <div className={tc(theme, "rounded-md border border-zinc-800 bg-black/20 px-3 py-2", "rounded-md border border-zinc-200 bg-white px-3 py-2")}>
                <div className="text-lg font-semibold" style={{ color: RIBBON[1] }}>{fmtNum(member.points_balance)}</div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Points Balance</div>
              </div>
              <div className={tc(theme, "rounded-md border border-zinc-800 bg-black/20 px-3 py-2", "rounded-md border border-zinc-200 bg-white px-3 py-2")}>
                <div className="text-lg font-semibold" style={{ color: RIBBON[0] }}>{fmtNum(member.lifetime_points)}</div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Lifetime</div>
              </div>
              <div className={tc(theme, "rounded-md border border-zinc-800 bg-black/20 px-3 py-2", "rounded-md border border-zinc-200 bg-white px-3 py-2")}>
                <div className="text-lg font-semibold" style={{ color: RIBBON[2] }}>{fmtNum(member.visits)}</div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Visits</div>
              </div>
              <div className={tc(theme, "rounded-md border border-zinc-800 bg-black/20 px-3 py-2", "rounded-md border border-zinc-200 bg-white px-3 py-2")}>
                <div className="text-lg font-semibold" style={{ color: RIBBON[3] }}>{fmtNum(member.referrals)}</div>
                <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Referrals</div>
              </div>
            </div>

            {/* Award points */}
            <div className="flex flex-wrap items-center gap-1.5">
              <WorkField label="Points"><WorkInput
                value={awardAmount}
                onChange={(e) => setAwardAmount(e.target.value)}
                inputMode="numeric"
                placeholder="Points"
                className={tc(theme, "w-20 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white", "w-20 text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black")}
              /></WorkField>
              <WorkField label="Reason (optional)"><WorkInput
                value={awardReason}
                onChange={(e) => setAwardReason(e.target.value)}
                placeholder="Reason (optional)"
                className={tc(theme, "flex-1 min-w-[8rem] text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white", "flex-1 min-w-[8rem] text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black")}
              /></WorkField>
              <WorkField label="Dept"><WorkInput
                value={awardDept}
                onChange={(e) => setAwardDept(e.target.value)}
                placeholder="Dept"
                className={tc(theme, "w-24 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white", "w-24 text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black")}
              /></WorkField>
              <WorkButton type="submit"
                onClick={handleAward}
                disabled={actionBusy}
                className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50"
              >
                {actionBusy ? "…" : "＋ Award Points"}
              </WorkButton>
            </div>

            {/* Record visit + referral */}
            <div className="flex flex-wrap items-center gap-1.5">
              <WorkField label="Visit dept"><WorkInput
                value={visitDept}
                onChange={(e) => setVisitDept(e.target.value)}
                placeholder="Visit dept"
                className={tc(theme, "w-28 text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white", "w-28 text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black")}
              /></WorkField>
              <WorkButton type="submit"
                onClick={handleVisit}
                disabled={actionBusy}
                className="text-xs px-3 py-1.5 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50"
              >
                📍 Record Visit
              </WorkButton>
              <WorkField label="Referred person's name"><WorkInput
                value={referredName}
                onChange={(e) => setReferredName(e.target.value)}
                placeholder="Referred person's name"
                className={tc(theme, "flex-1 min-w-[8rem] text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white", "flex-1 min-w-[8rem] text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black")}
              /></WorkField>
              <WorkButton type="submit"
                onClick={handleReferral}
                disabled={actionBusy}
                className="text-xs px-3 py-1.5 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white disabled:opacity-50"
              >
                🤝 Record Referral
              </WorkButton>
            </div>

            {/* Redeem reward */}
            <div className="flex flex-wrap items-center gap-1.5">
              <WorkField label="Reward"><WorkSelect
                value={redeemRewardId}
                onChange={(e) => setRedeemRewardId(e.target.value)}
                className={tc(theme, "flex-1 min-w-[10rem] text-xs rounded border border-zinc-700 bg-black/30 px-2 py-1 text-white", "flex-1 min-w-[10rem] text-xs rounded border border-zinc-300 bg-white px-2 py-1 text-black")}
              >
                {rewards.length === 0 && <option value="">No rewards available</option>}
                {rewards.map((reward) => (
                  <option key={reward.reward_id} value={reward.reward_id}>
                    {reward.name} — {fmtNum(reward.point_cost)} pts
                  </option>
                ))}
              </WorkSelect></WorkField>
              <WorkButton type="submit"
                onClick={handleRedeem}
                disabled={actionBusy || !redeemRewardId}
                className="text-xs px-3 py-1.5 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50"
              >
                {actionBusy ? "…" : "🎟 Redeem"}
              </WorkButton>
            </div>

            {/* Ledger history timeline */}
            <div>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-1.5">Points History</div>
              {member.ledger.length === 0 ? (
                <div className="text-xs text-zinc-500">No loyalty activity recorded yet.</div>
              ) : (
                <div className="space-y-1.5">
                  {member.ledger.map((entry, i) => (
                    <div key={entry.entry_id || i} className="flex items-start gap-2">
                      <span
                        className="mt-1 h-2 w-2 rounded-full flex-shrink-0"
                        style={{ background: entry.points > 0 ? RIBBON[1] : entry.points < 0 ? RIBBON[3] : "#9CA3AF" }}
                      />
                      <div className="min-w-0 flex-1">
                        <div className="text-xs text-zinc-300 flex items-center justify-between gap-2">
                          <span className="font-medium truncate">{entry.reason || entry.entry_type}</span>
                          {entry.points !== 0 && (
                            <span className="whitespace-nowrap" style={{ color: entry.points > 0 ? RIBBON[1] : RIBBON[3] }}>
                              {entry.points > 0 ? "+" : ""}{fmtNum(entry.points)}
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-zinc-600">
                          {entry.department && <span className="mr-2">{entry.department}</span>}
                          <span>{fmt(entry.timestamp)}</span>
                          <span className="ml-2">bal {fmtNum(entry.balance_after)}</span>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
