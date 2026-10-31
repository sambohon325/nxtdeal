"use client";

// DealerProvisionControl (2026-07-24) — the Hub-console button that spins a dealer's whole stack
// up in Coolify (hub_core/infra_provisioning.py). Shows whether auto-provisioning is configured,
// a "Provision in Coolify" action, a live status chip, and any warnings/errors — so onboarding a
// dealer's infrastructure is one click instead of a Coolify checklist.

import { useCallback, useEffect, useState } from "react";
import {
  getProvisioningConfig,
  provisionDealer,
  getProvisionStatus,
  HubApiError,
  type ProvisioningConfig,
  type ProvisionStatus,
} from "@/lib/hubApi";

const STATUS_STYLE: Record<string, string> = {
  none: "bg-zinc-800 text-zinc-400 border-zinc-700",
  provisioning: "bg-sky-500/15 text-sky-300 border-sky-500/30",
  deploying: "bg-amber-500/15 text-amber-300 border-amber-500/30",
  failed: "bg-red-500/15 text-red-300 border-red-500/30",
};

export default function DealerProvisionControl({
  dealerId,
  hasApiBaseUrl,
  onProvisioned,
}: {
  dealerId: string;
  hasApiBaseUrl: boolean;
  onProvisioned: (apiUrl: string) => void;
}) {
  const [config, setConfig] = useState<ProvisioningConfig | null>(null);
  const [status, setStatus] = useState<ProvisionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(
    async (live = false) => {
      try {
        setStatus(await getProvisionStatus(dealerId, live));
      } catch {
        /* no record yet is fine */
      }
    },
    [dealerId],
  );

  useEffect(() => {
    getProvisioningConfig().then(setConfig).catch(() => setConfig({ configured: false, missing: [] }));
    refresh(false);
  }, [dealerId, refresh]);

  async function provision() {
    setBusy(true);
    setError("");
    try {
      const res = await provisionDealer(dealerId);
      if (res.api?.url) onProvisioned(res.api.url);
      await refresh(true);
    } catch (e) {
      setError(e instanceof HubApiError ? e.message : e instanceof Error ? e.message : "Provisioning failed.");
      await refresh(false);
    } finally {
      setBusy(false);
    }
  }

  const st = status?.status ?? "none";
  const configured = config?.configured ?? false;

  return (
    <div className="mt-3 rounded-lg border border-zinc-800 bg-zinc-950/60 p-3">
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] uppercase tracking-wide text-zinc-400">Auto-provision</span>
          {st !== "none" && (
            <span className={`rounded-full border px-2 py-0.5 text-[10px] font-semibold capitalize ${STATUS_STYLE[st] ?? STATUS_STYLE.none}`}>
              {st}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          {st !== "none" && (
            <button onClick={() => refresh(true)} className="text-[10px] text-zinc-500 hover:text-white" title="Refresh live status">
              ↻ status
            </button>
          )}
          <button
            onClick={provision}
            disabled={busy || !configured}
            title={configured ? "" : "Set the COOLIFY_* env vars on hub-api to enable this."}
            className="rounded bg-brand-teal px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-black disabled:opacity-40"
          >
            {busy ? "Provisioning…" : hasApiBaseUrl || st === "deploying" ? "Re-provision" : "Provision in Coolify"}
          </button>
        </div>
      </div>

      {config && !configured && (
        <p className="mt-2 text-[11px] text-amber-300">
          Coolify auto-provisioning isn&apos;t set up on hub-api{config.missing.length ? ` (missing: ${config.missing.join(", ")})` : ""}. Add the COOLIFY_* env vars to enable one-click provisioning.
        </p>
      )}

      {status?.live && (
        <p className="mt-2 text-[11px] text-zinc-400">
          Coolify: API <span className="text-zinc-200">{status.live.api ?? "—"}</span> · Frontend <span className="text-zinc-200">{status.live.frontend ?? "—"}</span>
        </p>
      )}

      {status?.warnings?.map((w, i) => (
        <p key={i} className="mt-2 text-[11px] text-amber-300">⚠ {w}</p>
      ))}

      {(error || status?.error) && <p className="mt-2 text-[11px] text-red-400">{error || status?.error}</p>}

      {configured && st === "none" && (
        <p className="mt-2 text-[11px] text-zinc-500">
          Creates {`{slug}`}-api + {`{slug}`}-frontend in Coolify, deploys both, and records this dealer&apos;s API URL automatically.
        </p>
      )}
    </div>
  );
}
