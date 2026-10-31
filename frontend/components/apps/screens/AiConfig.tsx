"use client";

// Shared AI model-selector for all companion apps (2026-10-24).
//
// Generalizes the MySales personal AI setup (MySalesAiConfig.tsx + MySalesAssistants.tsx)
// so that any authenticated staff user can choose how AI runs in their app:
//   * off          -> turn AI off for themselves
//   * byok         -> bring their own provider key (raw key never stored on the server)
//   * on_device    -> prefer the native on-device model (routine tasks only)
//   * dealer       -> use the dealership's managed AI provider
//
// Staff apps (salesapp, reception, serviceops) render this full config screen.
// Customer apps (showroom, mygarage, kiosk) render a read-only notice instead,
// since AI is dealer-managed for customer-facing surfaces.
// MySales (personal) keeps its own MySalesAiConfig.tsx that links to the Hub-based
// personal assistant connection flow.

import { useEffect, useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import { useAsync, WiredScreen } from "./kit";
import {
  getAiConfig,
  setAiEnabled,
  setAiByok,
  clearAiByok,
  setAiRouting,
  resolveAiModel,
  type AiConfigResponse,
  type RoutingDecision,
  BYOK_PROVIDERS,
} from "@/lib/aiConfig";

// Staff companion apps that get the full per-user AI model selector.
const STAFF_AI_APPS = new Set(["salesapp", "reception", "serviceops"]);

// Customer-facing apps that show read-only dealer-managed AI info.
const CUSTOMER_AI_APPS = new Set(["showroom", "mygarage", "kiosk"]);

export function AiConfig({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const slug = app.slug;
  const accent = accentOf(app);

  const { loading, error, data: config, reload } = useAsync<AiConfigResponse>(
    () => getAiConfig(slug),
    [slug],
  );

  const [routing, setRouting] = useState<RoutingDecision | null>(null);
  const [routingLoading, setRoutingLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);

  // Resolve the current routing decision (which model provider will be used).
  useEffect(() => {
    if (!config || !config.ai_enabled) return;
    setRoutingLoading(true);
    resolveAiModel(slug, "routine")
      .then((r) => { setRouting(r); setRoutingLoading(false); })
      .catch(() => setRoutingLoading(false));
  }, [config, slug]);

  if (!STAFF_AI_APPS.has(slug)) {
    // Customer-facing apps: read-only informational.
    return (
      <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!config} onRetry={reload}>
        <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
          <h3 className="text-sm font-semibold text-white">AI Assistance</h3>
          <p className="mt-2 text-sm text-zinc-300">
            AI assistance in this app is managed by your dealership. An administrator
            configures the AI provider and spend controls in the Administration panel.
          </p>
          {config && config.ai_enabled && (
            <p className="mt-2 text-xs text-zinc-400">
              Currently active: dealer-managed AI with routing preferences you can
              review in your personal settings.
            </p>
          )}
        </div>
      </WiredScreen>
    );
  }

  // Staff apps: full per-user AI model selector.
  async function toggleAi(enabled: boolean) {
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      await setAiEnabled(slug, enabled);
      setSaveSuccess(`AI ${enabled ? "enabled" : "disabled"} for this app.`);
      await reload();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Unable to save.");
    } finally {
      setSaving(false);
    }
  }

  async function submitByok(provider: string, apiKey: string) {
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      await setAiByok(slug, provider, apiKey);
      setSaveSuccess("Your API key has been saved and masked on the server.");
      await reload();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Unable to save.");
    } finally {
      setSaving(false);
    }
  }

  async function clearByok() {
    setSaving(true);
    setSaveError(null);
    setSaveSuccess(null);
    try {
      await clearAiByok(slug);
      setSaveSuccess("BYOK connection cleared.");
      await reload();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Unable to save.");
    } finally {
      setSaving(false);
    }
  }

  function renderContent() {
    if (!config) return null;

    return (
      <>
        {/* Current routing decision */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
          <h3 className={`text-sm font-semibold ${accent.text}`}>
            {routing ? `AI is: ${routing.source}` : "Routing status"}
          </h3>
          {routingLoading && <p className="mt-1 text-xs text-zinc-500">Checking…</p>}
          {routing && (
            <p className="mt-1 text-xs text-zinc-400">
              {routing.reason}
              {routing.provider && <> • provider: {routing.provider}</>}
              {routing.model && <> • model: {routing.model}</>}
            </p>
          )}
        </div>

        {/* AI on/off */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
          <h3 className="text-sm font-semibold text-white">AI for this app</h3>
          <p className="mt-1 text-xs text-zinc-400">
            {config.ai_enabled
              ? "AI is on. You'll see suggested actions and draft replies."
              : "AI is off. You won't see AI suggestions or draft assistance."}
          </p>
          <div className="mt-3 flex gap-2">
            <button
              disabled={saving}
              onClick={() => toggleAi(true)}
              className="flex-1 rounded-lg border border-white/20 px-3 py-2 text-sm text-white hover:bg-white/5"
            >
              Turn ON
            </button>
            <button
              disabled={saving}
              onClick={() => toggleAi(false)}
              className="flex-1 rounded-lg border border-white/20 px-3 py-2 text-sm text-white hover:bg-white/5"
            >
              Turn OFF
            </button>
          </div>
        </div>

        {/* BYOK */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
          <h3 className="text-sm font-semibold text-white">Bring your own AI key</h3>
          {config.byok.configured ? (
            <div className="mt-2 space-y-2">
              <p className="text-xs text-zinc-400">
                Connected to <strong>{config.byok.provider}</strong>
                {" "}• key ends in {config.byok.key_masked}
              </p>
              <button
                disabled={saving}
                onClick={clearByok}
                className="rounded-lg border border-white/20 px-3 py-2 text-sm text-white hover:bg-white/5"
              >
                Clear connection
              </button>
            </div>
          ) : (
            <div className="mt-2 space-y-3">
              <p className="text-xs text-zinc-400">
                Bring your own OpenAI, Anthropic, Gemini, or Azure key to power AI
                on your own dime. Your dealership will not be billed.
              </p>
              <ByokForm onSubmit={submitByok} saving={saving} />
            </div>
          )}
        </div>

        {/* On-device preference */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
          <h3 className="text-sm font-semibold text-white">On-device model</h3>
          <p className="mt-1 text-xs text-zinc-400">
            {config.routing.on_device_when_available
              ? "Routine tasks use your phone's native on-device model when available."
              : "AI tasks always go to the cloud provider."}
          </p>
          <button
            disabled={saving}
            onClick={async () => {
              setSaving(true);
              try {
                await setAiRouting(slug, {
                  on_device_when_available: !config.routing.on_device_when_available,
                });
                await reload();
              } catch (e) {
                setSaveError(e instanceof Error ? e.message : "Unable to save.");
              } finally {
                setSaving(false);
              }
            }}
            className={`mt-2 rounded-lg px-3 py-2 text-sm ${
              config.routing.on_device_when_available
                ? `${accent.soft} ${accent.softText}`
                : "border border-white/20 text-white hover:bg-white/5"
            }`}
          >
            {config.routing.on_device_when_available ? "On" : "Off"}
          </button>
        </div>
      </>
    );
  }

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!config} onRetry={reload}>
      {saveSuccess && (
        <div role="status" className="rounded-xl border border-green-500/30 bg-green-500/10 p-3">
          <p className="text-xs text-green-300">{saveSuccess}</p>
        </div>
      )}
      {saveError && (
        <div role="alert" className="rounded-xl border border-red-500/30 bg-red-500/10 p-3">
          <p className="text-xs text-red-300">{saveError}</p>
        </div>
      )}
      {renderContent()}
    </WiredScreen>
  );
}

function ByokForm({
  onSubmit,
  saving,
}: {
  onSubmit: (provider: string, apiKey: string) => void;
  saving: boolean;
}) {
  const [provider, setProvider] = useState<string>(BYOK_PROVIDERS[0]);
  const [apiKey, setApiKey] = useState("");

  return (
    <div className="space-y-3">
      <select
        value={provider}
        onChange={(e) => setProvider(e.target.value)}
        className="w-full rounded-lg border border-white/20 bg-white/[0.05] px-3 py-2 text-sm text-white"
      >
        {BYOK_PROVIDERS.map((p) => (
          <option key={p} value={p}>
            {p.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase())}
          </option>
        ))}
      </select>
      <input
        type="password"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        placeholder="Your provider API key"
        className="w-full rounded-lg border border-white/20 bg-white/[0.05] px-3 py-2 text-sm text-white placeholder-zinc-500"
      />
      <button
        disabled={saving || !apiKey.trim()}
        onClick={() => {
          onSubmit(provider, apiKey);
          setApiKey("");
        }}
        className="w-full rounded-lg border border-sky-300/30 px-3 py-2 text-sm text-sky-100 hover:bg-sky-300/10"
      >
        {saving ? "Saving…" : "Save key"}
      </button>
    </div>
  );
}
