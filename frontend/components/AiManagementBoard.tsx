"use client";
import { WorkButton, WorkSelect, WorkTextarea, WorkInput , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Administration's "AI Management" item (Administration Control Center rebuild,
// continuing 2026-07-18/19). A real catalog of every OpenAI-backed feature in this
// codebase (core/ai_management.py -- built off a full grep for OpenAI usage across
// core/*.py), each with a real per-feature kill switch actually wired into that
// feature's own consumer function (not just a stored-and-ignored setting) and
// honest, in-memory call-attempt counters (attempted/succeeded/fell back/blocked).
//
// This sandbox has no outbound network path to the real OpenAI API at all -- every
// AI call attempted here falls back to its template fallback. That means no
// real usage/cost/token metrics from an OpenAI dashboard can be shown; the
// sandbox_network_note banner below states this plainly rather than fabricating
// numbers. This board is Administration-only.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getAiManagementOverview,
  setAiFeatureEnabled,
  type AiManagementOverview,
  type AiFeature,
} from "@/lib/aiManagement";
import {
  getBrandSettings,
  updateBrandSettings,
  listPromptTemplates,
  addPromptTemplate,
  removePromptTemplate,
  type BrandSettings,
  type PromptTemplate,
} from "@/lib/aiSettings";

type Theme = "dark" | "light";
type Tab = "features" | "brand" | "templates";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function Toggle({ on, onClick, busy }: { on: boolean; onClick: () => void; busy?: boolean }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={busy}
      className={`relative inline-flex h-5 w-9 items-center rounded-full transition disabled:opacity-40 ${on ? "bg-emerald-600" : "bg-zinc-700"}`}
      title={on ? "Enabled -- click to disable" : "Disabled -- click to enable"}
    >
      <span className="inline-block h-3.5 w-3.5 rounded-full bg-white transition" style={{ transform: on ? "translateX(18px)" : "translateX(4px)" }} />
    </WorkButton>
  );
}

function StatChip({ label, value, tone }: { label: string; value: number; tone: "neutral" | "good" | "warn" | "bad" }) {
  const toneClass =
    tone === "good" ? "bg-emerald-950/40 text-emerald-300" :
    tone === "warn" ? "bg-amber-950/40 text-amber-300" :
    tone === "bad" ? "bg-red-950/40 text-red-300" :
    "bg-zinc-800 text-zinc-400";
  return (
    <span className={`px-1.5 py-0.5 rounded text-xs ${toneClass}`}>
      {label}: {value}
    </span>
  );
}

function FeatureCard({
  theme,
  feature,
  onToggle,
  busy,
}: {
  theme: Theme;
  feature: AiFeature;
  onToggle: (key: string, enabled: boolean) => void;
  busy: boolean;
}) {
  return (
    <div className={tc(theme, "text-xs px-3 py-2.5 rounded border border-zinc-800", "text-xs px-3 py-2.5 rounded border border-zinc-200")}>
      <div className="flex items-center justify-between gap-2">
        <div className="min-w-0">
          <span className="text-zinc-200 font-medium">{feature.name}</span>
          <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${feature.enabled ? "bg-emerald-950/40 text-emerald-300" : "bg-zinc-800 text-zinc-500"}`}>
            {feature.enabled ? "enabled" : "disabled"}
          </span>
          {!feature.wired_route && (
            <span className="ml-2 px-1.5 py-0.5 rounded text-xs bg-amber-950/40 text-amber-300">no real route yet</span>
          )}
          {feature.has_tool_calling_access && (
            <span className="ml-2 px-1.5 py-0.5 rounded text-xs bg-sky-950/40 text-sky-300">graph tool access</span>
          )}
        </div>
        <Toggle on={feature.enabled} busy={busy} onClick={() => onToggle(feature.key, !feature.enabled)} />
      </div>
      <div className="text-xs text-zinc-500 mt-1">{feature.description}</div>
      <div className="text-xs text-zinc-600 mt-1">
        {feature.module} · {feature.functions.join(", ")}
      </div>
      <div className="text-xs text-zinc-600 mt-0.5">{feature.route_note}</div>
      <div className="flex flex-wrap items-center gap-1.5 mt-2">
        <StatChip label="attempted" value={feature.stats.attempted} tone="neutral" />
        <StatChip label="succeeded" value={feature.stats.succeeded} tone="good" />
        <StatChip label="fell back" value={feature.stats.fell_back} tone="warn" />
        <StatChip label="blocked" value={feature.stats.blocked} tone="bad" />
      </div>
      {feature.stats.last_at && (
        <div className="text-xs text-zinc-600 mt-1">
          last call: {feature.stats.last_outcome} at {fmt(feature.stats.last_at)}
          {feature.stats.last_detail ? ` — ${feature.stats.last_detail}` : ""}
        </div>
      )}
    </div>
  );
}

// Brand Voice -- the dealer's own tone/voice/style, injected into every inline
// AI assist (core/ai_assist.py) so all generated copy is on-brand. Editing is
// ADMIN/OPERATIONS-only server-side; a non-admin viewer just sees a save error.
function BrandVoicePanel({ theme }: { theme: Theme }) {
  const [settings, setSettings] = useState<BrandSettings | null>(null);
  const [tones, setTones] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    getBrandSettings()
      .then((r) => {
        setSettings(r.brand_settings);
        setTones(r.tones);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load brand settings."))
      .finally(() => setLoading(false));
  }, []);

  function save() {
    if (!settings) return;
    setSaving(true);
    setError(null);
    setSaved(false);
    updateBrandSettings(settings)
      .then((r) => {
        setSettings(r.brand_settings);
        setSaved(true);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to save brand settings."))
      .finally(() => setSaving(false));
  }

  const inputCls = tc(
    theme,
    "w-full text-xs rounded px-2 py-1.5 bg-zinc-900 border border-zinc-700 text-white",
    "w-full text-xs rounded px-2 py-1.5 bg-white border border-zinc-300 text-black"
  );

  if (loading) return <div className="text-sm text-zinc-500">Loading…</div>;
  if (!settings) return <div className="text-xs text-red-400">{error ?? "No brand settings."}</div>;

  return (
    <div className="max-w-2xl space-y-4">
      <div className={tc(theme, "text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
        This is your dealership&apos;s voice. It&apos;s injected into every inline &quot;✨ AI Assist&quot; across
        NXTDeal, so generated and rewritten copy sounds like you by default.
      </div>

      <div className="space-y-1">

        <WorkField label="Default tone"><WorkSelect
          value={settings.brand_tone}
          onChange={(e) => setSettings({ ...settings, brand_tone: e.target.value })}
          className={inputCls}
        >
          {tones.map((t) => (
            <option key={t} value={t}>
              {t}
            </option>
          ))}
        </WorkSelect></WorkField>
      </div>

      <div className="space-y-1">

        <WorkField label="Brand voice"><WorkTextarea
          value={settings.brand_voice}
          onChange={(e) => setSettings({ ...settings, brand_voice: e.target.value })}
          rows={3}
          placeholder="e.g. Warm and confident. We're the neighborhood dealer who treats people like family, never pushy."
          className={inputCls}
        /></WorkField>
      </div>

      <div className="space-y-1">

        <WorkField label="Style guidelines"><WorkTextarea
          value={settings.style_guidelines}
          onChange={(e) => setSettings({ ...settings, style_guidelines: e.target.value })}
          rows={3}
          placeholder="e.g. Short sentences. No jargon. Always mention financing options. Avoid exclamation points."
          className={inputCls}
        /></WorkField>
      </div>

      {error && <div className="text-xs text-red-400">{error}</div>}
      <div className="flex items-center gap-3">
        <WorkButton type="submit"
          onClick={save}
          disabled={saving}
          className="text-xs font-medium px-3 py-1.5 rounded bg-brand-teal text-black hover:brightness-110 disabled:opacity-40"
        >
          {saving ? "Saving…" : "Save brand voice"}
        </WorkButton>
        {saved && <span className="text-xs text-emerald-400">Saved.</span>}
      </div>
    </div>
  );
}

// Prompt Templates -- reusable named prompts an admin saves once and re-runs.
function PromptTemplatesPanel({ theme }: { theme: Theme }) {
  const [templates, setTemplates] = useState<PromptTemplate[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [body, setBody] = useState("");
  const [saving, setSaving] = useState(false);
  const [removingId, setRemovingId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    listPromptTemplates()
      .then((r) => setTemplates(r.prompt_templates))
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load prompt templates."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  function add() {
    if (!name.trim() || !body.trim()) return;
    setSaving(true);
    setError(null);
    addPromptTemplate(name.trim(), body.trim())
      .then(() => {
        setName("");
        setBody("");
        refresh();
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to save template."))
      .finally(() => setSaving(false));
  }

  function remove(id: string) {
    setRemovingId(id);
    removePromptTemplate(id)
      .then(() => refresh())
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to delete template."))
      .finally(() => setRemovingId(null));
  }

  const inputCls = tc(
    theme,
    "w-full text-xs rounded px-2 py-1.5 bg-zinc-900 border border-zinc-700 text-white",
    "w-full text-xs rounded px-2 py-1.5 bg-white border border-zinc-300 text-black"
  );

  return (
    <div className="max-w-2xl space-y-4">
      <div className={tc(theme, "text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
        Save prompts your team reuses -- a follow-up template, a service-reminder opener, a trade-in
        pitch -- so anyone can pull them up instead of rewriting from scratch.
      </div>

      <div className={tc(theme, "space-y-2 rounded border border-zinc-800 p-3", "space-y-2 rounded border border-zinc-200 p-3")}>

        <WorkField label="New template"><WorkInput
          value={name}
          onChange={(e) => setName(e.target.value)}
          placeholder="Template name (e.g. 30-day service reminder)"
          className={inputCls}
        /></WorkField>
        <WorkField label="The prompt body"><WorkTextarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={3}
          placeholder="The prompt body…"
          className={inputCls}
        /></WorkField>
        {error && <div className="text-xs text-red-400">{error}</div>}
        <WorkButton type="submit"
          onClick={add}
          disabled={saving || !name.trim() || !body.trim()}
          className="text-xs font-medium px-3 py-1.5 rounded bg-brand-teal text-black hover:brightness-110 disabled:opacity-40"
        >
          {saving ? "Saving…" : "Add template"}
        </WorkButton>
      </div>

      {loading ? (
        <div className="text-sm text-zinc-500">Loading…</div>
      ) : templates.length === 0 ? (
        <div className="text-xs text-zinc-500">No prompt templates saved yet.</div>
      ) : (
        <div className="space-y-2">
          {templates.map((t) => (
            <div key={t.id} className={tc(theme, "rounded border border-zinc-800 p-3", "rounded border border-zinc-200 p-3")}>
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-zinc-200">{t.name}</span>
                <WorkButton type="submit" variant="danger"
                  onClick={() => remove(t.id)}
                  disabled={removingId === t.id}
                  className="text-xs px-2 py-0.5 rounded bg-red-950/40 text-red-300 hover:bg-red-950/60 disabled:opacity-40"
                >
                  {removingId === t.id ? "…" : "Delete"}
                </WorkButton>
              </div>
              <div className="text-xs text-zinc-400 mt-1 whitespace-pre-wrap">{t.body}</div>
              <div className="text-xs text-zinc-600 mt-1">
                {t.created_by ? `by ${t.created_by} · ` : ""}
                {fmt(t.created_at)}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function AiManagementBoard({ theme }: { theme: Theme }) {
  const [tab, setTab] = useState<Tab>("features");
  const [overview, setOverview] = useState<AiManagementOverview | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [togglingKey, setTogglingKey] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getAiManagementOverview()
      .then(setOverview)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load AI Management data."))
      .finally(() => setLoading(false));
  }

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => refresh(), []);

  function handleToggle(key: string, enabled: boolean) {
    setTogglingKey(key);
    setAiFeatureEnabled(key, enabled)
      .then(() => refresh())
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to update this AI feature."))
      .finally(() => setTogglingKey(null));
  }

  const features = overview?.features ?? [];
  const summary = overview?.summary;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total AI Features" value={String(summary?.total_features ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Enabled" value={String(summary?.enabled_count ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Disabled" value={String(summary?.disabled_count ?? 0)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Features With Recorded Activity" value={String(summary?.features_with_recorded_activity ?? 0)} color={RIBBON[3]} />
      </div>

      <div className={tc(theme, "flex gap-1 px-4 pt-3 border-b border-zinc-800", "flex gap-1 px-4 pt-3 border-b border-zinc-200")}>
        {(
          [
            ["features", "Features & Usage"],
            ["brand", "Brand Voice"],
            ["templates", "Prompt Templates"],
          ] as [Tab, string][]
        ).map(([k, label]) => (
          <WorkButton data-work-view aria-pressed={tab === k} type="submit"
            key={k}
            onClick={() => setTab(k)}
            className={`text-xs px-3 py-1.5 rounded-t border-b-2 -mb-px ${
              tab === k
                ? "border-brand-teal text-white font-semibold"
                : tc(theme, "border-transparent text-zinc-400 hover:text-zinc-200", "border-transparent text-zinc-500 hover:text-zinc-800")
            }`}
          >
            {label}
          </WorkButton>
        ))}
      </div>

      <div className="flex-1 p-4 space-y-4">
        {tab === "brand" && <BrandVoicePanel theme={theme} />}
        {tab === "templates" && <PromptTemplatesPanel theme={theme} />}
        {tab === "features" && (
          <>
        {error && <div className="text-xs text-red-400">{error}</div>}
        {overview?.sandbox_network_note && (
          <div className={tc(theme, "text-xs text-amber-300 bg-amber-950/30 border border-amber-900/50 rounded px-3 py-2", "text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2")}>
            {overview.sandbox_network_note}
          </div>
        )}

        {summary && summary.features_missing_a_real_route > 0 && (
          <div className={tc(theme, "text-xs text-zinc-400 bg-zinc-900/60 border border-zinc-800 rounded px-3 py-2", "text-xs text-zinc-600 bg-zinc-50 border border-zinc-200 rounded px-3 py-2")}>
            {summary.features_missing_a_real_route} feature{summary.features_missing_a_real_route === 1 ? "" : "s"} below
            {" "}{summary.features_missing_a_real_route === 1 ? "has" : "have"} no real HTTP route wired to it yet -- see
            the &quot;no real route yet&quot; badge. Toggling it here still works (the flag is real), it just isn&apos;t
            reachable by any UI surface until that gap is closed separately.
          </div>
        )}

        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <div className="space-y-2">
            {features.map((f) => (
              <FeatureCard key={f.key} theme={theme} feature={f} onToggle={handleToggle} busy={togglingKey === f.key} />
            ))}
            {features.length === 0 && <div className="text-xs text-zinc-500">No AI features catalogued.</div>}
          </div>
        )}
          </>
        )}
      </div>
    </div>
  );
}
