"use client";
import { WorkButton, WorkInput , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Administration's "Data Management" item (Administration Control Center
// rebuild, continued) -- real per-entity-type CSV export
// (core/data_backup.py) and a real graph.json backup/restore action.
// ADMIN/OPERATIONS for export + backup; RESTORE IS ADMIN-ONLY and is the
// single most consequential real action in this whole rebuild -- it
// overwrites the live graph.json and reloads it in-process. Gated behind a
// typed confirmation phrase, not just a plain "are you sure" click-through.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { DealerCloudStorage } from "@/components/DealerCloudStorage";
import { useEffect, useState } from "react";
import {
  getExportableTypes,
  downloadEntityTypeExport,
  createBackup,
  listBackups,
  restoreBackup,
  type DataBackup,
} from "@/lib/dataManagement";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;
const RESTORE_PHRASE = "RESTORE";

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function Btn({ onClick, children, disabled, tone }: { onClick: () => void; children: React.ReactNode; disabled?: boolean; tone?: "primary" | "danger" }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      className={`text-xs px-2.5 py-1 rounded font-medium disabled:opacity-40 ${
        tone === "danger" ? "bg-red-900/60 text-red-200 hover:bg-red-900" : tone === "primary" ? "bg-zinc-200 text-black hover:bg-white" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
      }`}
    >
      {children}
    </WorkButton>
  );
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

export function DataManagementBoard({ theme, initialTab = "export" }: { theme: Theme; initialTab?: "export" | "backups" | "cloud" }) {
  const [tab, setTab] = useState<"export" | "backups" | "cloud">(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);
  const [types, setTypes] = useState<Record<string, number>>({});
  const [backups, setBackups] = useState<DataBackup[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [exporting, setExporting] = useState<string | null>(null);
  const [backupLabel, setBackupLabel] = useState("");
  const [restoreTarget, setRestoreTarget] = useState<DataBackup | null>(null);
  const [confirmText, setConfirmText] = useState("");

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getExportableTypes(), listBackups()])
      .then(([t, b]) => {
        setTypes(t.entity_types);
        setBackups(b.backups);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Data Management data."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleExport(entityType: string) {
    setExporting(entityType);
    setError(null);
    try {
      await downloadEntityTypeExport(entityType);
      setMessage(`Exported ${entityType}.csv`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to export this entity type.");
    } finally {
      setExporting(null);
    }
  }

  async function handleCreateBackup() {
    try {
      await createBackup(backupLabel);
      setBackupLabel("");
      setMessage("Backup created.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create backup.");
    }
  }

  async function handleRestore() {
    if (!restoreTarget || confirmText !== RESTORE_PHRASE) return;
    try {
      await restoreBackup(restoreTarget.id);
      setMessage(`Restored from ${restoreTarget.filename}. The live graph has been reloaded.`);
      setRestoreTarget(null);
      setConfirmText("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to restore this backup.");
    }
  }

  const sortedTypes = Object.entries(types).sort((a, b) => b[1] - a[1]);

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-3 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-3 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Exportable Types" value={String(sortedTypes.length)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Total Entities" value={String(sortedTypes.reduce((n, [, c]) => n + c, 0))} color={RIBBON[1]} />
        <Kpi theme={theme} label="Backups on File" value={String(backups.length)} color={RIBBON[2]} />
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {([
          ["export", "Export"],
          ["backups", "Backups & Restore"],
          ["cloud", "Cloud storage"],
        ] as const).map(([key, label]) => (
          <WorkButton data-work-view aria-pressed={tab === key} type="submit"
            key={key}
            onClick={() => setTab(key)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${tab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {label}
          </WorkButton>
        ))}
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}
      {message && <div className="mx-4 mt-2 text-xs text-emerald-400">{message}</div>}

      <div className="flex-1 p-4">
        {tab === "cloud" ? <DealerCloudStorage /> : loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "export" ? (
          <div className="space-y-1">
            <div className="text-xs text-zinc-500 mb-2">
              A real CSV of every entity of the selected type currently on the graph -- every attribute becomes a
              column, missing values render as empty cells. Formula-like text is prefixed with [text] in the download
              for spreadsheet viewing. Stored records are unchanged; this download is not a lossless import file.
            </div>
            {sortedTypes.length === 0 && <div className="text-xs text-zinc-600">No entity types found.</div>}
            {sortedTypes.map(([type, count]) => (
              <div key={type} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                <div>
                  <span className="text-zinc-200">{type}</span>
                  <span className="text-zinc-600 ml-2">{count} records</span>
                </div>
                <Btn tone="primary" onClick={() => handleExport(type)} disabled={exporting === type}>
                  {exporting === type ? "Exporting…" : "Export CSV"}
                </Btn>
              </div>
            ))}
          </div>
        ) : (
          <div className="space-y-4">
            <div className="rounded border border-zinc-800 p-3 space-y-2 max-w-md">

              <WorkField label="Create Backup"><WorkInput
                value={backupLabel}
                onChange={(e) => setBackupLabel(e.target.value)}
                placeholder="Label (optional)"
                className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 w-full"
              /></WorkField>
              <Btn tone="primary" onClick={handleCreateBackup}>Create Backup Now</Btn>
              <div className="text-xs text-zinc-600">
                Local graph-only recovery copy. Use Cloud storage for scheduled encrypted tenant-file backups.
              </div>
            </div>

            <div className="space-y-1">
              {backups.length === 0 && <div className="text-xs text-zinc-600">No backups on file.</div>}
              {backups.map((b) => (
                <div key={b.id} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div>
                    <span className="text-zinc-200">{b.filename}</span>
                    {b.label && <span className="text-zinc-600 ml-2">{b.label}</span>}
                    <span className="text-zinc-600 ml-2">{fmtBytes(b.size_bytes)}</span>
                    <span className="text-zinc-600 ml-2">{fmt(b.created_at)}</span>
                    {b.restored_at && <span className="text-amber-400 ml-2">restored {fmt(b.restored_at)}</span>}
                  </div>
                  <Btn tone="danger" onClick={() => { setRestoreTarget(b); setConfirmText(""); }}>Restore…</Btn>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {restoreTarget && (
        <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setRestoreTarget(null)}>
          <div className="bg-brand-charcoal border border-red-900 rounded-xl p-5 w-[26rem] text-white space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="text-sm font-brand font-medium text-red-300">⚠ Restore Backup — Admin Only</div>
            <div className="text-xs text-zinc-400">
              This overwrites the LIVE graph.json with <span className="text-zinc-200">{restoreTarget.filename}</span> and
              reloads it in-process immediately. Any data created or changed after this backup was taken will be
              PERMANENTLY LOST. This cannot be undone from this screen.
            </div>
            <div className="text-xs text-zinc-400">
              Type <span className="text-red-300 font-medium">{RESTORE_PHRASE}</span> to confirm.
            </div>
            <WorkField label="Confirm Text"><WorkInput
              value={confirmText}
              onChange={(e) => setConfirmText(e.target.value)}
              placeholder={RESTORE_PHRASE}
              className="text-xs px-2 py-1.5 rounded bg-zinc-900 border border-red-900 text-zinc-200 w-full"
            /></WorkField>
            <div className="flex gap-1.5">
              <Btn tone="danger" onClick={handleRestore} disabled={confirmText !== RESTORE_PHRASE}>Restore Now</Btn>
              <Btn onClick={() => setRestoreTarget(null)}>Cancel</Btn>
            </div>
          </div>
        </WorkOverlay>
      )}
    </div>
  );
}
