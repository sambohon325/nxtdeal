"use client";
import { WorkButton, WorkSelect, WorkInput } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Track B Connections (2026-07-25): see which external capabilities are live vs simulated,
// and connect a provider. For notifications, the built-in "http_webhook" provider works
// today with any endpoint you control (your own webhook, Zapier/Make) — no paid account.
// Named providers (Twilio, Stripe, Meta…) show as slots that need a builder + credentials.
// Backed by lib/connections.ts (backend/api/routers/connections.py). ADMIN to configure.
import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";
import {
  getConnections,
  configureCredential,
  removeCredential,
  type ConnectionsView,
} from "@/lib/connections";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

export function ConnectionsBoard({ theme }: { theme: Theme }) {
  const [data, setData] = useState<ConnectionsView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [openCap, setOpenCap] = useState<string | null>(null);
  const [provider, setProvider] = useState("");
  const [url, setUrl] = useState("");
  const [auth, setAuth] = useState("");
  const [busy, setBusy] = useState(false);

  const session = getSession();
  const isAdmin = session?.role === "ADMIN";

  const card = tc(theme, "rounded-md border border-zinc-800 bg-zinc-900/60 p-3", "rounded-md border border-zinc-200 bg-white p-3");
  const input = tc(theme, "rounded-md bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-[12px]", "rounded-md bg-white border border-zinc-300 px-2 py-1.5 text-[12px]");

  function refresh() {
    getConnections()
      .then((d) => { setData(d); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load connections."));
  }

  useEffect(refresh, []);

  function openConfig(capability: string) {
    setOpenCap(capability);
    setProvider(data?.slots[capability]?.[0]?.provider || "");
    setUrl(""); setAuth(""); setFlash(null);
  }

  async function save(capability: string) {
    setBusy(true); setError(null);
    try {
      const config: Record<string, string> = provider === "http_webhook" ? { url } : {};
      const secrets: Record<string, string> = provider === "http_webhook" && auth ? { auth_header: auth } : {};
      const r = await configureCredential(capability, provider, config, secrets);
      setFlash(r.note);
      setOpenCap(null);
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't save."); } finally { setBusy(false); }
  }

  async function disconnect(capability: string) {
    setError(null);
    try { await removeCredential(capability); refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't disconnect."); }
  }

  if (!data) return <div className="p-4 text-sm text-zinc-500">Loading connections…</div>;

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
      <div className="px-3 pt-3 shrink-0">
        <div className="text-base font-brand">Connections</div>
        <div className="text-xs text-zinc-500">
          {data.status.live_count} live · {data.status.simulated_count} simulated. Connect a provider to take a capability live.
        </div>
      </div>

      {flash && <div className="mx-3 mt-2 rounded-md bg-brand-teal/15 border border-brand-teal/40 px-3 py-2 text-xs text-brand-teal">{flash}</div>}
      {error && <div className="mx-3 mt-2 rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>}

      <div className="p-3 space-y-2">
        {data.status.providers.map((p) => {
          const cred = data.credentials.find((c) => c.capability === p.capability);
          const slots = data.slots[p.capability] || [];
          return (
            <div key={p.capability} className={card}>
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="text-sm font-semibold flex items-center gap-2 flex-wrap">
                    {p.name}
                    <span className={p.mode === "live" ? "text-xs px-1.5 py-0.5 rounded-full bg-brand-teal text-black" : "text-xs px-1.5 py-0.5 rounded-full bg-zinc-700 text-zinc-200"}>
                      {p.mode}
                    </span>
                    <span className={p.scope === "personal" ? "text-xs px-1.5 py-0.5 rounded-full bg-brand-yellow/20 text-brand-yellow" : "text-xs px-1.5 py-0.5 rounded-full bg-zinc-800 text-zinc-400"}>
                      {p.layer}
                    </span>
                  </div>
                  <div className="text-xs text-zinc-500">{p.description}</div>
                  {cred && <div className="text-xs text-zinc-500 mt-0.5">Provider: {cred.provider}{Object.entries(cred.secrets).length ? ` · ${Object.entries(cred.secrets).map(([k, v]) => `${k}=${v}`).join(", ")}` : ""}</div>}
                </div>
                {isAdmin && (
                  <div className="flex gap-1.5 shrink-0">
                    <WorkButton type="submit" onClick={() => openConfig(p.capability)} className="text-xs px-2.5 py-1 rounded-md bg-zinc-700 text-white">
                      {cred ? "Reconfigure" : "Connect"}
                    </WorkButton>
                    {cred && <WorkButton type="submit" onClick={() => disconnect(p.capability)} className="text-xs px-2 py-1 rounded-md border border-zinc-700 text-zinc-400">Disconnect</WorkButton>}
                  </div>
                )}
              </div>

              {openCap === p.capability && isAdmin && (
                <div className="mt-2 pt-2 border-t border-zinc-800/60 space-y-2">
                  <div className="flex flex-wrap gap-2 items-center">
                    <WorkField label="Provider"><WorkSelect value={provider} onChange={(e) => setProvider(e.target.value)} className={input}>
                      {slots.map((s) => <option key={s.provider} value={s.provider}>{s.provider}{s.has_builder ? "" : " (needs builder)"}</option>)}
                    </WorkSelect></WorkField>
                    {provider === "http_webhook" && (
                      <>
                        <WorkField label="Webhook URL (https://…)"><WorkInput className={input + " flex-1 min-w-[180px]"} placeholder="Webhook URL (https://…)" value={url} onChange={(e) => setUrl(e.target.value)} /></WorkField>
                        <WorkField label="Auth header (optional)"><WorkInput className={input} placeholder="Auth header (optional)" value={auth} onChange={(e) => setAuth(e.target.value)} /></WorkField>
                      </>
                    )}
                    <WorkButton type="submit" onClick={() => save(p.capability)} disabled={busy || (provider === "http_webhook" && !url)} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">Save</WorkButton>
                  </div>
                  {provider !== "http_webhook" && (
                    <div className="text-xs text-zinc-500">
                      {slots.find((s) => s.provider === provider)?.has_builder
                        ? "This provider has a builder — saving credentials takes it live."
                        : "No shippable adapter builder exists for this provider yet, so it stays simulated until one is added. For notifications, use http_webhook to go live today with any endpoint you control."}
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
        {!isAdmin && <div className="text-xs text-zinc-500 px-1">You can view status; connecting a provider needs an Admin role.</div>}
        <div className="text-xs text-zinc-600 px-1">{data.status.disclaimer}</div>
      </div>
    </div>
  );
}

export default ConnectionsBoard;
