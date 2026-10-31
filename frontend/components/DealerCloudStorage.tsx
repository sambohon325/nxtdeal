"use client";
import { WorkButton, WorkSelect, WorkInput, WorkTextarea } from "./WorkspaceUi";

import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

type Settings = {
  photo_connection: string;
  backup_connection: string;
  interval_hours: number;
  retention_days: number;
  enabled: boolean;
  public_key: string;
};
type Status = {
  settings: Settings;
  worker_enabled: boolean;
  scope: string;
  connections: {
    id: string;
    label: string;
    provider: string;
    status: string;
  }[];
  runs: {
    id: string;
    state: string;
    started: number;
    error?: string;
    verified_at?: number;
  }[];
};
async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
): Promise<T> {
  const r = await fetch(`${API_BASE}/data-management/cloud${path}`, {
    method,
    headers: { ...authHeaders(), "Content-Type": "application/json" },
    cache: "no-store",
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await r.json();
  if (!r.ok)
    throw new Error(
      typeof data.detail === "string"
        ? data.detail
        : "Storage request could not be completed.",
    );
  return data;
}

export function DealerCloudStorage() {
  const [data, setData] = useState<Status | null>(null),
    [draft, setDraft] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [notice, setNotice] = useState("");
  async function refresh() {
    const value = await api<Status>("");
    setData(value);
    setDraft(value.settings);
  }
  useEffect(() => {
    void refresh().catch((e) => setError(e.message));
  }, []);
  async function action(run: boolean) {
    setBusy(true);
    setError("");
    setNotice("");
    try {
      if (run) {
        const result = await api<{ state: string }>("/backups", "POST");
        setNotice(
          result.state === "verified_transfer"
            ? "Encrypted backup uploaded and downloaded again: bytes match. A restore drill is still required."
            : "Backup did not verify. Review the run below before retrying.",
        );
      } else if (draft) {
        if (draft.public_key.includes("PRIVATE KEY")) {
          throw new Error("Keep the private recovery key on your trusted recovery device. Paste only the public key; nothing was submitted.");
        }
        const {
          photo_connection,
          backup_connection,
          interval_hours,
          retention_days,
          enabled,
          public_key,
        } = draft;
        await api("", "PUT", {
          photo_connection,
          backup_connection,
          interval_hours,
          retention_days,
          enabled,
          public_key,
        });
        setNotice(
          "Storage preferences saved. This does not verify a provider connection or a restore.",
        );
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Storage request failed.");
    } finally {
      setBusy(false);
    }
  }
  const field =
    "block w-full rounded border border-zinc-600 bg-transparent p-2 text-sm";
  return (
    <section className="space-y-4 max-w-3xl" aria-label="Dealer-owned storage">
      <h2 className="text-lg font-semibold">Dealer-owned storage</h2>
      <p>
        Use existing inventory-feed photo links. Photos uploaded in NXTDeal go
        to your dealership’s storage; the app keeps vehicle associations and
        references.
      </p>
      {error && (
        <p role="alert" className="text-red-400">
          {error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {!data || !draft ? (
        <WorkButton type="submit"
          onClick={() => void refresh().catch((e) => setError(e.message))}
        >
          Reload storage settings
        </WorkButton>
      ) : (
        <>
          {!data.connections.length && (
            <p className="rounded border border-amber-500/40 p-3">
              No dealer cloud accounts connected. Google Drive, OneDrive,
              Dropbox and S3 connections must first be authorized and
              provisioned for this dealership. No files are being backed up to
              those services yet.
            </p>
          )}
          <fieldset disabled={busy} className="grid gap-4 sm:grid-cols-2">
            {(["photo_connection", "backup_connection"] as const).map((key) => (
              <label key={key}>
                {key === "photo_connection"
                  ? "Uploaded vehicle photos"
                  : "Encrypted dealership backups"}
                <WorkSelect
                  className={field}
                  value={draft[key]}
                  onChange={(e) =>
                    setDraft({ ...draft, [key]: e.target.value })
                  }
                >
                  <option value="">Not selected</option>
                  {data.connections.map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.label} · {c.provider}
                    </option>
                  ))}
                </WorkSelect>
              </label>
            ))}
            <label>
              Backup frequency
              <WorkSelect
                className={field}
                value={draft.interval_hours}
                onChange={(e) =>
                  setDraft({ ...draft, interval_hours: Number(e.target.value) })
                }
              >
                {[1, 6, 12, 24, 168].map((n) => (
                  <option key={n} value={n}>
                    {n === 168
                      ? "Weekly"
                      : n === 24
                        ? "Daily"
                        : `Every ${n} hour${n === 1 ? "" : "s"}`}
                  </option>
                ))}
              </WorkSelect>
            </label>
            <label>
              Retention review after (days)
              <WorkInput
                className={field}
                type="number"
                min={1}
                max={3650}
                value={draft.retention_days}
                onChange={(e) =>
                  setDraft({ ...draft, retention_days: Number(e.target.value) })
                }
              />
            </label>
            <label className="sm:col-span-2">
              Public recovery key
              <WorkTextarea
                className={`${field} font-mono`}
                rows={5}
                placeholder="-----BEGIN PUBLIC KEY-----"
                value={draft.public_key}
                onChange={(e) =>
                  setDraft({ ...draft, public_key: e.target.value })
                }
              />
              <span className="text-sm">
                Your RSA public key encrypts backups. Keep its private recovery
                key outside NXTDeal; without it, backups cannot be recovered.
                Never paste a private key here.
              </span>
            </label>
            <label className="sm:col-span-2">
              <WorkInput
                type="checkbox"
                checked={draft.enabled}
                onChange={(e) =>
                  setDraft({ ...draft, enabled: e.target.checked })
                }
              />{" "}
              Schedule backups to the selected dealer-owned destination
            </label>
          </fieldset>
          <p>
            {data.worker_enabled
              ? "Backup worker activated. Saved schedules run while the service is online."
              : "Backup worker is not activated on this deployment. Saving a schedule will not start uploads."}
          </p>
          <p className="text-sm">
            {data.scope} Capture requires stable files. A verified transfer is
            not a verified restore. Retention dates flag backups for review;
            this release does not automatically delete cloud files.
          </p>
          <div className="flex flex-wrap gap-3">
            <WorkButton type="submit"
              className="rounded border px-4 py-2"
              disabled={busy}
              onClick={() => void action(false)}
            >
              Save settings
            </WorkButton>
            <WorkButton type="submit"
              className="rounded border px-4 py-2"
              disabled={
                busy ||
                !data.worker_enabled ||
                !data.settings.backup_connection ||
                !data.settings.public_key
              }
              onClick={() => void action(true)}
            >
              Back up now using saved settings
            </WorkButton>
          </div>
          <h3 className="font-semibold">Recent backup runs</h3>
          {!data.runs.length && <p>No cloud backup runs recorded.</p>}
          {data.runs.map((r) => (
            <article className="rounded border border-zinc-600 p-3" key={r.id}>
              <p>
                {new Date(r.started * 1000).toLocaleString()} ·{" "}
                {r.state.replaceAll("_", " ")}
              </p>
              {r.error && <p>{r.error}</p>}
              {r.verified_at && (
                <p>
                  Readback matched at{" "}
                  {new Date(r.verified_at * 1000).toLocaleString()}. Restore not
                  yet verified.
                </p>
              )}
            </article>
          ))}
        </>
      )}
    </section>
  );
}

export function DealerPhotoUpload({
  vehicleId,
  onUploaded,
  onBusyChange,
  onDraftChange,
  disabled = false,
}: {
  vehicleId: string;
  onUploaded: () => void;
  onBusyChange?: (busy: boolean) => void;
  onDraftChange?: (dirty: boolean) => void;
  disabled?: boolean;
}) {
  const [file, setFile] = useState<File | null>(null),
    [publish, setPublish] = useState(false),
    [busy, setBusy] = useState(false),
    [message, setMessage] = useState("");
  const pending = useRef(false);
  useEffect(() => { onBusyChange?.(busy); return () => onBusyChange?.(false); }, [busy, onBusyChange]);
  useEffect(() => { onDraftChange?.(!!file); return () => onDraftChange?.(false); }, [file, onDraftChange]);
  async function upload() {
    if (!file || !publish || disabled || pending.current) return;
    pending.current = true;
    setBusy(true);
    setMessage("");
    try {
      const r = await fetch(
        `${API_BASE}/merchandising/vehicles/${encodeURIComponent(vehicleId)}/cloud-photo?publish=true`,
        {
          method: "POST",
          headers: {
            ...authHeaders(),
            "Content-Type": "application/octet-stream",
          },
          body: file,
        },
      );
      const result = await r.json();
      if (!r.ok)
        throw new Error(
          typeof result.detail === "string"
            ? result.detail
            : "Photo upload failed; check inventory before retrying.",
        );
      setMessage(
        "Photo verified in dealer-owned storage and linked to this vehicle.",
      );
      setFile(null);
      setPublish(false);
      onUploaded();
    } catch (e) {
      setMessage(e instanceof Error ? e.message : "Photo upload failed.");
    } finally {
      pending.current = false;
      setBusy(false);
    }
  }
  return (
    <fieldset
      disabled={busy || disabled}
      className="mt-3 space-y-2 border-t border-zinc-600 pt-3"
    >
      <legend className="text-sm">Upload to dealer-owned storage</legend>
      <p className="text-xs">
        For vehicles managed in NXTDeal. Existing feed URLs above are used
        directly without copying their images.
      </p>
      <label className="block text-xs">
        Vehicle photo (JPEG, PNG or WebP; up to 10 MB)
        <WorkInput
          className="block max-w-full"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          onChange={(e) => {
            const f = e.target.files?.[0] ?? null;
            setFile(f && f.size <= 10 * 1024 * 1024 ? f : null);
            setMessage(
              f && f.size > 10 * 1024 * 1024 ? "Photo exceeds 10 MB." : "",
            );
          }}
        />
      </label>
      <label className="block text-xs">
        <WorkInput
          type="checkbox"
          checked={publish}
          onChange={(e) => setPublish(e.target.checked)}
        />{" "}
        This photo may appear publicly in vehicle listings.
      </label>
      <WorkButton type="submit"
        className="rounded border px-3 py-2 text-xs"
        disabled={!file || !publish || busy}
        onClick={() => void upload()}
      >
        Upload photo
      </WorkButton>
      {message && (
        <p role="status" className="text-xs">
          {message}
        </p>
      )}
    </fieldset>
  );
}
