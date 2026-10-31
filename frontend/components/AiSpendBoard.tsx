"use client";
import { WorkButton, WorkInput } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Administration → "AI Spend" (Freemium Platform roadmap, Phase 5, 2026-08-03). The AI Spend
// Governor for a bring-your-own-key model (core/ai_spend.py). ADMIN/OPERATIONS. NXTDeal is
// model-agnostic: the dealer declares their AI provider + that they've put their own key in place,
// sets a per-user monthly AI-action limit so one user can't burn the whole key's budget, overrides
// it per user, and sees the aggregate consumption view for the month. Metering is by AI ACTIONS
// (no token/dollar metering exists yet) — stated plainly, not fabricated.

import { useEffect, useState } from "react";
import {
  getAiSpendPolicy,
  getAiSpendOverview,
  setAiSpendProvider,
  setAiSpendDefaultLimit,
  setAiSpendUserLimit,
  setDealerAiEnabled,
  setCustomEndpoint,
  AI_PROVIDERS,
  MANAGED_PROVIDER,
  type AiSpendPolicy,
  type AiSpendOverview,
} from "@/lib/aiSpend";

type Theme = "dark" | "light";
function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

export function AiSpendBoard({ theme = "dark" }: { theme?: Theme }) {
  const [policy, setPolicy] = useState<AiSpendPolicy | null>(null);
  const [overview, setOverview] = useState<AiSpendOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [limitDraft, setLimitDraft] = useState<string>("");

  async function load() {
    try {
      const [p, o] = await Promise.all([getAiSpendPolicy(), getAiSpendOverview()]);
      setPolicy(p);
      setOverview(o);
      setLimitDraft(p.per_user_monthly_limit === null ? "" : String(p.per_user_monthly_limit));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't load AI spend.");
    }
  }
  useEffect(() => {
    load();
  }, []);

  async function guard(key: string, fn: () => Promise<AiSpendPolicy>) {
    setBusy(key);
    setError(null);
    try {
      setPolicy(await fn());
      setOverview(await getAiSpendOverview());
    } catch (e) {
      setError(e instanceof Error ? e.message : "That change didn't take.");
    } finally {
      setBusy(null);
    }
  }

  if (error && !policy) return <div className="rounded-lg bg-red-500/10 px-4 py-3 text-sm text-red-400">{error}</div>;
  if (!policy || !overview) return <div className="py-10 text-center text-sm text-zinc-500">Loading AI spend…</div>;

  const card = tc(theme, "rounded-xl border border-white/10 bg-white/[0.03] p-4", "rounded-xl border border-zinc-200 bg-white p-4");
  const sub = tc(theme, "text-zinc-400", "text-zinc-500");

  return (
    <div className="space-y-5">
      {error && <div className="rounded-lg bg-red-500/10 px-4 py-2 text-sm text-red-400">{error}</div>}

      {/* Dealer master AI switch */}
      <div className={card}>
        <div className="flex items-center justify-between gap-3">
          <div>
            <div className="text-sm font-semibold">AI for this dealership</div>
            <div className={`text-xs ${sub}`}>
              {policy.ai_enabled
                ? "AI is on. Turn it off to remove the AI chat, bot, and assistant for everyone — the rest of NXTDeal is unchanged."
                : "AI is OFF dealer-wide. No AI runs and the AI UI is hidden for every user."}
            </div>
          </div>
          <WorkButton type="submit"
            onClick={() => guard("aienabled", () => setDealerAiEnabled(!policy.ai_enabled))}
            disabled={!!busy}
            className={`shrink-0 rounded-lg px-4 py-2 text-xs font-semibold ${policy.ai_enabled ? "bg-emerald-600 text-white" : tc(theme, "bg-white/10 text-zinc-300", "bg-zinc-100 text-zinc-600")}`}
          >
            {policy.ai_enabled ? "AI On" : "AI Off"}
          </WorkButton>
        </div>
        {overview.ai_off_user_count > 0 && (
          <div className="mt-2 text-xs text-zinc-500">{overview.ai_off_user_count} user(s) have also turned AI off for themselves.</div>
        )}
      </div>

      <div className={tc(theme, "rounded-lg bg-amber-500/10 px-3 py-2 text-xs text-amber-300", "rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-700")}>
        NXTDeal is model-agnostic — use our hosted <span className="font-semibold">NXTDeal AI</span> (paid add-on, billed by usage),
        bring your own key, or point us at your own endpoint. Limits below meter <span className="font-semibold">AI actions</span> per user
        per month (not tokens or dollars — no token metering yet).
      </div>

      {/* Provider posture */}
      <div className={card}>
        <div className="text-sm font-semibold">Your AI provider</div>
        <div className={`mb-3 text-xs ${sub}`}>
          Pick our hosted AI, the key you&apos;re bringing, or a homegrown endpoint. NXTDeal never stores your key here.
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {AI_PROVIDERS.map((p) => {
            const isManaged = p === MANAGED_PROVIDER;
            const lockedManaged = isManaged && !policy.managed_ai_available;
            return (
              <WorkButton type="submit"
                key={p}
                onClick={() => guard(`prov:${p}`, () => setAiSpendProvider(p, policy.byo_key_configured))}
                disabled={!!busy}
                title={lockedManaged ? "NXTDeal AI is a paid add-on — add it in Modules & Plan" : undefined}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium ${policy.provider === p ? "bg-brand-blue text-white" : tc(theme, "bg-white/10 text-zinc-300", "bg-zinc-100 text-zinc-600")}`}
              >
                {isManaged ? "NXTDeal AI" : p.replace("_", " ")}
                {lockedManaged ? " 🔒" : ""}
                {isManaged && policy.managed_ai_available ? " ✦" : ""}
              </WorkButton>
            );
          })}
          {policy.provider !== MANAGED_PROVIDER && policy.provider !== "custom" && (
            <WorkButton type="submit"
              onClick={() => guard("byo", () => setAiSpendProvider(policy.provider, !policy.byo_key_configured))}
              disabled={!!busy}
              className={`ml-auto rounded-lg px-3 py-1.5 text-xs font-semibold ${policy.byo_key_configured ? "bg-emerald-600 text-white" : tc(theme, "bg-white/10 text-zinc-300", "bg-zinc-100 text-zinc-600")}`}
            >
              {policy.byo_key_configured ? "✓ Key configured" : "Mark key configured"}
            </WorkButton>
          )}
        </div>

        {/* Managed billing (only when on NXTDeal AI) */}
        {policy.provider === MANAGED_PROVIDER && overview.managed_billing && (
          <div className="mt-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-xs">
            <div className="flex items-center justify-between">
              <span className={sub}>This month · {overview.managed_billing.billable_actions} actions × ${overview.managed_billing.rate_per_action}/action</span>
              <span className="font-semibold text-white">≈ ${overview.managed_billing.estimated_charge}</span>
            </div>
            <div className="mt-0.5 text-xs text-zinc-500">{overview.managed_billing.note}</div>
          </div>
        )}

        {/* Custom / homegrown endpoint config */}
        {policy.provider === "custom" && (
          <CustomEndpointEditor
            theme={theme}
            current={policy.custom_endpoint}
            busy={!!busy}
            onSave={(cfg) => guard("custom", () => setCustomEndpoint(cfg))}
          />
        )}
      </div>

      {/* Default per-user limit */}
      <div className={card}>
        <div className="text-sm font-semibold">Per-user monthly limit</div>
        <div className={`mb-3 text-xs ${sub}`}>Caps AI actions per user each month so one user can't burn the whole key. Blank = unlimited.</div>
        <div className="flex items-center gap-2">
          <WorkField label="Spending limit"><WorkInput
            value={limitDraft}
            onChange={(e) => setLimitDraft(e.target.value.replace(/[^0-9]/g, ""))}
            placeholder="∞ unlimited"
            className={tc(theme, "w-40 rounded-md border border-white/10 bg-black/20 px-3 py-1.5 text-sm text-white outline-none", "w-40 rounded-md border border-zinc-200 bg-white px-3 py-1.5 text-sm outline-none")}
          /></WorkField>
          <WorkButton type="submit" variant="primary"
            onClick={() => guard("deflimit", () => setAiSpendDefaultLimit(limitDraft === "" ? null : Number(limitDraft)))}
            disabled={!!busy}
            className="rounded-lg bg-brand-blue px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            {busy === "deflimit" ? "…" : "Set limit"}
          </WorkButton>
        </div>
      </div>

      {/* Aggregate usage */}
      <div className={card}>
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">Consumption · {overview.period}</div>
          <div className={`text-xs ${sub}`}>{overview.total_ai_actions} AI actions · {overview.distinct_users} users</div>
        </div>
        {overview.unattributed_actions > 0 && (
          <div className="mt-1 text-xs text-zinc-500">
            {overview.unattributed_actions} action(s) not attributed to a user (the calling feature didn&apos;t tag one).
          </div>
        )}
        <div className="mt-3 space-y-1.5">
          {overview.users.length === 0 && <div className={`text-xs ${sub}`}>No attributed AI usage yet this month.</div>}
          {overview.users.map((u) => (
            <div key={u.user_id} className={tc(theme, "flex items-center justify-between gap-3 rounded-lg border border-white/5 px-3 py-2", "flex items-center justify-between gap-3 rounded-lg border border-zinc-100 px-3 py-2")}>
              <div className="min-w-0">
                <div className="truncate text-xs font-medium">{u.user_id}</div>
                <div className="text-xs text-zinc-500">
                  {u.used} used{u.limit !== null ? ` / ${u.limit}` : " · unlimited"}
                  {u.over_limit ? " · over limit" : ""}
                </div>
              </div>
              <div className="flex items-center gap-2">
                {u.limit !== null && (
                  <div className="hidden h-1.5 w-24 overflow-hidden rounded-full bg-white/10 sm:block">
                    <div
                      className={`h-full rounded-full ${u.over_limit ? "bg-red-500" : "bg-emerald-500"}`}
                      style={{ width: `${Math.min(100, u.limit ? (u.used / u.limit) * 100 : 0)}%` }}
                    />
                  </div>
                )}
                <UserLimitControl theme={theme} userId={u.user_id} current={u.limit} busy={busy === `user:${u.user_id}`} onSave={(v) => guard(`user:${u.user_id}`, () => setAiSpendUserLimit(u.user_id, v))} />
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function UserLimitControl({
  theme,
  userId,
  current,
  busy,
  onSave,
}: {
  theme: Theme;
  userId: string;
  current: number | null;
  busy: boolean;
  onSave: (v: number | null) => void;
}) {
  const [open, setOpen] = useState(false);
  const [draft, setDraft] = useState<string>(current === null ? "" : String(current));
  if (!open) {
    return (
      <WorkButton type="submit" onClick={() => setOpen(true)} className={tc(theme, "rounded-md bg-white/5 px-2 py-1 text-xs text-zinc-400", "rounded-md bg-zinc-50 px-2 py-1 text-xs text-zinc-500")}>
        Override
      </WorkButton>
    );
  }
  return (
    <div className="flex items-center gap-1">
      <WorkField label="Limit"><WorkInput
        value={draft}
        onChange={(e) => setDraft(e.target.value.replace(/[^0-9]/g, ""))}
        placeholder="∞"
        className={tc(theme, "w-14 rounded-md border border-white/10 bg-black/20 px-2 py-1 text-right text-xs text-white outline-none", "w-14 rounded-md border border-zinc-200 bg-white px-2 py-1 text-right text-xs outline-none")}
      /></WorkField>
      <WorkButton type="submit" variant="primary"
        onClick={() => {
          onSave(draft === "" ? null : Number(draft));
          setOpen(false);
        }}
        disabled={busy}
        className="rounded-md bg-brand-blue px-2 py-1 text-xs font-semibold text-white disabled:opacity-50"
      >
        {busy ? "…" : "Save"}
      </WorkButton>
    </div>
  );
}

function CustomEndpointEditor({
  theme,
  current,
  busy,
  onSave,
}: {
  theme: Theme;
  current: { base_url: string; model: string; auth_header: string; notes: string } | null;
  busy: boolean;
  onSave: (cfg: { base_url: string; model: string; auth_header: string; notes: string } | null) => void;
}) {
  const [baseUrl, setBaseUrl] = useState(current?.base_url ?? "");
  const [model, setModel] = useState(current?.model ?? "");
  const [authHeader, setAuthHeader] = useState(current?.auth_header ?? "Authorization");
  const input = tc(
    theme,
    "w-full rounded-md border border-white/10 bg-black/20 px-2.5 py-1.5 text-[12px] text-white outline-none placeholder:text-zinc-600",
    "w-full rounded-md border border-zinc-200 bg-white px-2.5 py-1.5 text-[12px] outline-none",
  );
  return (
    <div className="mt-3 space-y-2 rounded-lg border border-white/10 bg-white/[0.03] p-3">
      <div className="text-xs font-semibold">Homegrown / any-API endpoint</div>
      <div className="text-xs text-zinc-500">
        Point NXTDeal at your own model server. The API key belongs in your deployment&apos;s secret store — not here.
      </div>
      <WorkField label="Base URL (https://…)"><WorkInput value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="Base URL (https://…)" className={input} /></WorkField>
      <div className="flex gap-2">
        <WorkField label="Model name"><WorkInput value={model} onChange={(e) => setModel(e.target.value)} placeholder="Model name" className={input} /></WorkField>
        <WorkField label="Auth header"><WorkInput value={authHeader} onChange={(e) => setAuthHeader(e.target.value)} placeholder="Auth header" className={input} /></WorkField>
      </div>
      <div className="flex gap-2">
        <WorkButton type="submit" variant="primary"
          onClick={() => onSave({ base_url: baseUrl, model, auth_header: authHeader, notes: current?.notes ?? "" })}
          disabled={busy}
          className="rounded-lg bg-brand-blue px-3 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
        >
          {busy ? "…" : "Save endpoint"}
        </WorkButton>
        {current && (
          <WorkButton type="submit"
            onClick={() => onSave(null)}
            disabled={busy}
            className={tc(theme, "rounded-lg bg-white/10 px-3 py-1.5 text-xs text-zinc-300", "rounded-lg bg-zinc-100 px-3 py-1.5 text-xs text-zinc-600")}
          >
            Clear
          </WorkButton>
        )}
      </div>
    </div>
  );
}
