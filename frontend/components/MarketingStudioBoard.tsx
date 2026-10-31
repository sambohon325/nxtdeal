"use client";
import { WorkButton, WorkTextarea, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Marketing's new "AI Studio" Top Menu item (2026-07-19). One real content
// generation form dispatching to 7 already-real AI wizard functions across this
// codebase, plus a real Content Library feed with Apply/Discard actions.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState } from "react";
import {
  getStudioOverview,
  listContentDrafts,
  generateContent,
  applyDraft,
  discardDraft,
  type StudioOverview,
  type ContentDraft,
  type ContentType,
  type ContentTypeCatalogEntry,
} from "@/lib/marketingStudio";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

// Params whose value is a JSON object/array rather than a plain string --
// rendered as a JSON textarea instead of a single-line input.
const JSON_PARAMS = new Set(["text_fields", "vehicle_attrs", "vehicle"]);

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function Pill({ children, tone }: { children: React.ReactNode; tone?: string }) {
  return (
    <span
      className="text-xs px-2 py-0.5 rounded-full font-brand uppercase tracking-wide"
      style={{ background: tone ? `${tone}22` : "rgba(255,255,255,0.08)", color: tone ?? "#a1a1aa" }}
    >
      {children}
    </span>
  );
}

const STATUS_TONE: Record<string, string> = {
  drafted: "#FBCF09",
  applied: "#22c55e",
  discarded: "#71717a",
};

const TABS = [
  ["generate", "Generate"],
  ["library", "Content Library"],
] as const;

export function MarketingStudioBoard({ theme }: { theme: Theme }) {
  const [tab, setTab] = useState<(typeof TABS)[number][0]>("generate");
  const [overview, setOverview] = useState<StudioOverview | null>(null);
  const [drafts, setDrafts] = useState<ContentDraft[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [contentType, setContentType] = useState<ContentType>("email_copy");
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [generating, setGenerating] = useState(false);
  const [lastDraft, setLastDraft] = useState<ContentDraft | null>(null);

  const [typeFilter, setTypeFilter] = useState<string>("");
  const [statusFilter, setStatusFilter] = useState<string>("");

  function refreshOverview() {
    setLoading(true);
    setError(null);
    getStudioOverview()
      .then((data) => {
        setOverview(data);
        if (!contentType && data.content_type_catalog.length > 0) {
          setContentType(data.content_type_catalog[0].key);
        }
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the AI Marketing Studio."))
      .finally(() => setLoading(false));
  }

  useEffect(refreshOverview, []); // eslint-disable-line react-hooks/exhaustive-deps

  function refreshLibrary() {
    listContentDrafts({
      content_type: typeFilter || undefined,
      status: statusFilter || undefined,
    })
      .then((r) => setDrafts(r.drafts))
      .catch(() => setDrafts([]));
  }

  useEffect(() => {
    if (tab === "library") refreshLibrary();
  }, [tab, typeFilter, statusFilter]); // eslint-disable-line react-hooks/exhaustive-deps

  const catalogEntry: ContentTypeCatalogEntry | undefined = useMemo(
    () => overview?.content_type_catalog.find((c) => c.key === contentType),
    [overview, contentType]
  );

  useEffect(() => {
    // Reset the form's field values whenever the selected content type changes.
    setParamValues({});
    setLastDraft(null);
  }, [contentType]);

  async function submitGenerate() {
    if (!catalogEntry) return;
    setGenerating(true);
    setActionError(null);
    setLastDraft(null);
    try {
      const params: Record<string, unknown> = {};
      for (const key of catalogEntry.params) {
        const raw = paramValues[key];
        if (raw === undefined || raw === "") continue;
        if (JSON_PARAMS.has(key)) {
          try {
            params[key] = JSON.parse(raw);
          } catch {
            throw new Error(`"${key}" must be valid JSON (e.g. an object or array).`);
          }
        } else {
          params[key] = raw;
        }
      }
      const draft = await generateContent(contentType, params);
      setLastDraft(draft);
      refreshOverview();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Unable to generate content.");
    } finally {
      setGenerating(false);
    }
  }

  async function act(fn: () => Promise<unknown>) {
    setActionError(null);
    try {
      await fn();
      refreshLibrary();
      refreshOverview();
    } catch (e) {
      setActionError(e instanceof Error ? e.message : "Action failed.");
    }
  }

  function renderContent(content: Record<string, unknown>) {
    return (
      <div className="space-y-1">
        {Object.entries(content).map(([k, v]) => (
          <div key={k}>
            <span className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k}: </span>
            <span className="text-xs">{typeof v === "string" ? v : JSON.stringify(v)}</span>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Drafts" value={String(overview?.total_drafts ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Applied" value={String(overview?.by_status.applied ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Discarded" value={String(overview?.by_status.discarded ?? 0)} color={RIBBON[3]} />
        <Kpi theme={theme} label="Used Fallback (no AI)" value={String(overview?.fallback_count ?? 0)} color={RIBBON[2]} />
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {TABS.map(([key, label]) => (
          <WorkButton data-work-view aria-pressed={tab === key} type="submit"
            key={key}
            onClick={() => setTab(key)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${tab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {label}
          </WorkButton>
        ))}
        <WorkButton type="submit" onClick={refreshOverview} className="ml-auto text-xs px-2.5 py-1 rounded-full bg-zinc-200/10 text-zinc-400 hover:text-white">
          ↻ Refresh
        </WorkButton>
      </div>

      {actionError && <div className="mx-4 mt-2 text-xs text-red-400">{actionError}</div>}

      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        {loading && <div className="text-sm text-zinc-500">Loading…</div>}
        {error && <div className="text-sm text-red-400">{error}</div>}

        {!loading && !error && tab === "generate" && overview && (
          <div className="space-y-4">
            <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2")}>
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Content Type</div>
              <div className="flex flex-wrap gap-1.5">
                {overview.content_type_catalog.map((c) => (
                  <WorkButton type="submit"
                    key={c.key}
                    onClick={() => setContentType(c.key)}
                    className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${contentType === c.key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
                  >
                    {c.label}
                  </WorkButton>
                ))}
              </div>

              {catalogEntry && (
                <div className="space-y-2 pt-2">
                  <div className="text-xs text-zinc-500">
                    Channel: {catalogEntry.channel} -- gated by the real &quot;{catalogEntry.kill_switch_feature}&quot; AI Management kill switch.
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {catalogEntry.params.map((key) =>
                      JSON_PARAMS.has(key) ? (
                        <WorkTextarea
                          key={key}
                          aria-label={`${key.replaceAll("_", " ")} (JSON)`} placeholder={`${key} (JSON)`}
                          value={paramValues[key] ?? ""}
                          onChange={(e) => setParamValues({ ...paramValues, [key]: e.target.value })}
                          className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1 col-span-2 font-mono"
                          rows={3}
                        />
                      ) : (
                        <WorkInput
                          key={key}
                          aria-label={key.replaceAll("_", " ")} placeholder={key}
                          value={paramValues[key] ?? ""}
                          onChange={(e) => setParamValues({ ...paramValues, [key]: e.target.value })}
                          className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1"
                        />
                      )
                    )}
                  </div>
                  <WorkButton type="submit"
                    onClick={submitGenerate}
                    disabled={generating}
                    className="text-xs px-2.5 py-1 rounded-full bg-zinc-200 text-black font-medium disabled:opacity-50"
                  >
                    {generating ? "Generating…" : "✨ Generate"}
                  </WorkButton>
                </div>
              )}
            </div>

            {lastDraft && (
              <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Result -- {lastDraft.id}</div>
                  <div className="flex items-center gap-2">
                    <Pill tone={STATUS_TONE[lastDraft.status]}>{lastDraft.status}</Pill>
                    {lastDraft.used_fallback && <Pill tone="#71717a">Fallback (no AI)</Pill>}
                  </div>
                </div>
                {renderContent(lastDraft.content)}
                {lastDraft.used_fallback && lastDraft.fallback_reason && (
                  <div className="text-xs text-zinc-600 mt-2">AI call unavailable: {lastDraft.fallback_reason}</div>
                )}
                {lastDraft.status === "drafted" && (
                  <div className="flex gap-2 mt-2">
                    <WorkButton type="submit" onClick={() => act(() => applyDraft(lastDraft.id).then((d) => setLastDraft(d)))} className="text-xs text-zinc-400 hover:text-white">
                      ✓ Apply
                    </WorkButton>
                    <WorkButton type="submit" onClick={() => act(() => discardDraft(lastDraft.id).then((d) => setLastDraft(d)))} className="text-xs text-zinc-400 hover:text-white">
                      ✕ Discard
                    </WorkButton>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {!loading && tab === "library" && (
          <div className="space-y-3">
            <div className="flex gap-2">
              <WorkField label="Type Filter"><WorkSelect value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1">
                <option value="">All content types</option>
                {overview?.content_type_catalog.map((c) => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
              </WorkSelect></WorkField>
              <WorkField label="Status"><WorkSelect value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="text-xs bg-transparent border border-zinc-700 rounded px-2 py-1">
                <option value="">All statuses</option>
                <option value="drafted">Drafted</option>
                <option value="applied">Applied</option>
                <option value="discarded">Discarded</option>
              </WorkSelect></WorkField>
            </div>

            {drafts.length === 0 && <div className="text-xs text-zinc-500">No content drafts yet -- generate one from the Generate tab.</div>}

            {drafts.map((d) => (
              <div key={d.id} className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3")}>
                <div className="flex items-center justify-between mb-1">
                  <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">
                    {d.content_type} -- {d.id}
                  </div>
                  <div className="flex items-center gap-2">
                    {d.used_fallback && <Pill tone="#71717a">Fallback</Pill>}
                    <Pill tone={STATUS_TONE[d.status]}>{d.status}</Pill>
                  </div>
                </div>
                {renderContent(d.content)}
                <div className="text-xs text-zinc-600 mt-2">
                  Created by {d.created_by} at {d.created_at}
                  {d.decided_by && <> -- decided by {d.decided_by} at {d.decided_at}</>}
                </div>
                {d.status === "drafted" && (
                  <div className="flex gap-2 mt-2">
                    <WorkButton type="submit" onClick={() => act(() => applyDraft(d.id))} className="text-xs text-zinc-400 hover:text-white">✓ Apply</WorkButton>
                    <WorkButton type="submit" onClick={() => act(() => discardDraft(d.id))} className="text-xs text-zinc-400 hover:text-white">✕ Discard</WorkButton>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
