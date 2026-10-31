"use client";
import { WorkSelect, WorkInput, WorkTextarea, WorkButton } from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";

// Bumper-parity Bulk Import (2026-07-25): paste/upload a CSV, map columns, preview
// (new / duplicate / error counts), then commit. Backed by lib/leadImport.ts
// (backend/core/bulk_import_api.py). Mirrors Bumper's Upload -> Field Mapping ->
// Processing wizard.
import { useState } from "react";
import {
  analyzeCsv,
  previewImport,
  commitImport,
  type AnalyzeResult,
  type PreviewResult,
  type CommitResult,
} from "@/lib/leadImport";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

type Step = "input" | "map" | "done";

export function LeadImportBoard({ theme }: { theme: Theme }) {
  const [step, setStep] = useState<Step>("input");
  const [targetType, setTargetType] = useState("lead");
  const [csvText, setCsvText] = useState("");
  const [dedupe, setDedupe] = useState(true);
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);
  const [mapping, setMapping] = useState<Record<string, string>>({});
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const card = tc(theme, "rounded-md border border-zinc-800 bg-zinc-900/60 p-3", "rounded-md border border-zinc-200 bg-white p-3");
  const input = tc(theme, "w-full rounded-md bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-[12px]", "w-full rounded-md bg-white border border-zinc-300 px-2 py-1.5 text-[12px]");

  function onFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => setCsvText(String(reader.result || ""));
    reader.readAsText(file);
  }

  async function doAnalyze() {
    setBusy(true);
    setError(null);
    try {
      const a = await analyzeCsv(csvText, targetType);
      setAnalysis(a);
      setMapping(a.suggested_mapping);
      setStep("map");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't analyze CSV.");
    } finally {
      setBusy(false);
    }
  }

  async function doPreview() {
    setBusy(true);
    setError(null);
    try {
      setPreview(await previewImport(csvText, mapping, targetType, dedupe));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't preview import.");
    } finally {
      setBusy(false);
    }
  }

  async function doCommit() {
    setBusy(true);
    setError(null);
    try {
      setResult(await commitImport(csvText, mapping, targetType, dedupe));
      setStep("done");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't commit import.");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setStep("input");
    setCsvText("");
    setAnalysis(null);
    setMapping({});
    setPreview(null);
    setResult(null);
    setError(null);
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
      <div className="px-3 pt-3 shrink-0">
        <div className="text-base font-brand">Import</div>
        <div className="text-xs text-zinc-500">
          Bring in a book of leads or customers: map your columns, preview what&apos;s new vs. a duplicate, then commit.
        </div>
      </div>

      {error && (
        <div className="mx-3 mt-2 rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>
      )}

      <div className="p-3 space-y-3">
        {step === "input" && (
          <div className={card}>
            <div className="flex items-center gap-3 mb-2">
              <label className="text-xs text-zinc-500">Import into:</label>
              <WorkSelect aria-label="Import into:" value={targetType} onChange={(e) => setTargetType(e.target.value)} className={input + " max-w-[160px]"}>
                <option value="lead">Leads</option>
                <option value="customer">Customers</option>
              </WorkSelect>
              <label className="text-xs text-zinc-500 flex items-center gap-1.5 ml-auto">
                <WorkInput type="checkbox" checked={dedupe} onChange={(e) => setDedupe(e.target.checked)} />
                Skip duplicates (by email/phone)
              </label>
            </div>
            <WorkInput aria-label="Choose import file" type="file" accept=".csv,text/csv" onChange={onFile} className="text-xs mb-2 block" />
            <WorkField label="…or paste CSV here (first row = headers)"><WorkTextarea
              value={csvText}
              onChange={(e) => setCsvText(e.target.value)}
              placeholder="…or paste CSV here (first row = headers)"
              className={input + " h-40 font-mono text-xs"}
            /></WorkField>
            <WorkButton type="submit"
              onClick={doAnalyze}
              disabled={busy || !csvText.trim()}
              className="mt-2 text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50"
            >
              {busy ? "Analyzing…" : "Analyze columns →"}
            </WorkButton>
          </div>
        )}

        {step === "map" && analysis && (
          <>
            <div className={card}>
              <div className="text-xs font-semibold mb-2">Map your columns ({analysis.row_count} rows)</div>
              <div className="space-y-1.5">
                {analysis.headers.map((h) => (
                  <div key={h} className="flex items-center gap-2">
                    <div className="text-xs w-1/2 truncate text-zinc-400">{h}</div>

                    <WorkField label="→"><WorkSelect
                      value={mapping[h] || ""}
                      onChange={(e) => setMapping({ ...mapping, [h]: e.target.value })}
                      className={input + " w-1/2"}
                    >
                      <option value="">(ignore)</option>
                      {analysis.target_fields.map((f) => (
                        <option key={f} value={f}>{f}</option>
                      ))}
                    </WorkSelect></WorkField>
                  </div>
                ))}
              </div>
              <div className="flex gap-2 mt-3">
                <WorkButton type="submit" onClick={doPreview} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-zinc-700 text-white disabled:opacity-50">
                  {busy ? "…" : "Preview"}
                </WorkButton>
                <WorkButton type="submit" onClick={reset} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-400">Start over</WorkButton>
              </div>
            </div>

            {preview && (
              <div className={card}>
                <div className="flex gap-4 text-xs mb-2">
                  <span className="text-brand-teal font-semibold">{preview.will_create} new</span>
                  <span className="text-amber-400">{preview.duplicates} duplicate</span>
                  <span className="text-red-400">{preview.errors} error</span>
                </div>
                <div className="text-xs space-y-0.5">
                  <RecordCollection label="Import rows" busy={busy}>{preview.verdicts.map((v) => (
                    <div key={v.index} className="flex gap-2">
                      <span className={v.status === "create" ? "text-brand-teal" : v.status === "duplicate" ? "text-amber-400" : "text-red-400"}>
                        {v.status}
                      </span>
                      <span className="text-zinc-500 truncate">
                        {v.record.first_name} {v.record.last_name} {v.record.email || v.record.phone}
                        {v.errors ? ` — ${v.errors.join(", ")}` : ""}
                        {v.duplicate_of ? ` — matches ${v.duplicate_of.match} (${v.duplicate_of.on})` : ""}
                      </span>
                    </div>
                  ))}</RecordCollection>
                </div>
                <WorkButton type="submit"
                  onClick={doCommit}
                  disabled={busy || preview.will_create === 0}
                  className="mt-3 text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50"
                >
                  {busy ? "Importing…" : `Import ${preview.will_create} ${targetType === "lead" ? "leads" : "customers"}`}
                </WorkButton>
              </div>
            )}
          </>
        )}

        {step === "done" && result && (
          <div className={card}>
            <div className="text-sm font-semibold text-brand-teal mb-1">Import complete</div>
            <div className="text-xs text-zinc-400">
              {result.created_count} created · {result.skipped_count} skipped · {result.error_count} errored.
            </div>
            <WorkButton type="submit" onClick={reset} className="mt-3 text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold">
              Import another file
            </WorkButton>
          </div>
        )}
      </div>
    </div>
  );
}

export default LeadImportBoard;
