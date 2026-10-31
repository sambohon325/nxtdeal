"use client";
import { WorkButton, WorkTextarea, WorkInput } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Wix/Webflow-style interactive Website Builder canvas (2026-07-23). Replaces the old
// Builder-tab body (the split Structured/Canvas field-form + static live preview) with
// a single unified WYSIWYG surface: a left insert drawer, a center canvas of real
// rendered sections (components/SiteSectionRenderer.tsx, the same renderer the public
// visitor page uses) with click-to-edit inline text, and a right inspector for the
// full set of a section's content fields.
//
// Everything here rides on the EXISTING websites API -- every mutating call
// (addSection/updateSectionFields/reorderSections/...) already persists per-action on
// the backend and returns the fresh Website, which we hand straight to onWebsiteChange.
// Undo/Redo is a purely client-side snapshot stack of those returned Website objects
// (the backend has no per-edit revision endpoint), so it visually reverts the surface;
// Save force-refetches the canonical Website via getWebsite() and pulses "Saved".
//
// There are deliberately NO style/padding/color fields surfaced -- the data model has
// none (see lib/websites.ts's WebsiteSection). The inspector exposes only the real,
// persisted content fields, with a clearly-marked "Style (coming soon)" placeholder
// where a future style system will live.
import { useEffect, useMemo, useState } from "react";
import {
  listSectionTemplates,
  listPageKeys,
  addSection,
  updateSectionFields,
  removeSection,
  setSectionLocked,
  reorderSections,
  regenerateSection,
  submitWebsite,
  getWebsite,
  addLibraryImage,
  type Website,
  type WebsiteSection,
  type SectionTemplate,
  type SectionField,
} from "@/lib/websites";
import { SiteSectionRenderer } from "@/components/SiteSectionRenderer";
import AiAssistButton from "@/components/AiAssistButton";
import ImageLibraryPicker from "@/components/ImageLibraryPicker";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const HISTORY_CAP = 30;
const DESKTOP_WIDTH = 1200;
const MOBILE_WIDTH = 390;

const isImageField = (k: string) => /image|logo|photo/i.test(k);

function Btn({
  theme,
  onClick,
  children,
  kind = "default",
  disabled,
  small,
  title,
  active,
}: {
  theme: Theme;
  onClick?: () => void;
  children: React.ReactNode;
  kind?: "default" | "primary" | "danger";
  disabled?: boolean;
  small?: boolean;
  title?: string;
  active?: boolean;
}) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      title={title}
      variant={kind === "default" ? "secondary" : kind}
      aria-pressed={active}
    >
      {children}
    </WorkButton>
  );
}

// A tiny icon-button for the per-section floating toolbar.
function IconBtn({
  onClick,
  disabled,
  title,
  danger,
  children,
}: {
  onClick: () => void;
  disabled?: boolean;
  title: string;
  danger?: boolean;
  children: React.ReactNode;
}) {
  return (
    <WorkButton type="submit"
      onClick={(e) => {
        e.stopPropagation();
        onClick();
      }}
      disabled={disabled}
      title={title}
      className={`w-7 h-7 flex items-center justify-center rounded text-xs shadow-sm transition disabled:opacity-30 disabled:cursor-not-allowed ${
        danger ? "bg-red-900/90 text-red-200 hover:bg-red-800" : "bg-zinc-900/90 text-zinc-200 hover:bg-zinc-700 border border-white/10"
      }`}
    >
      {children}
    </WorkButton>
  );
}

export function WebsiteBuilderCanvas({
  theme = "dark",
  website,
  pageKey,
  onWebsiteChange,
  fullScreen,
  onToggleFullScreen,
}: {
  theme?: Theme;
  website: Website;
  pageKey: string;
  onWebsiteChange: (w: Website) => void;
  fullScreen?: boolean;
  onToggleFullScreen?: () => void;
}) {
  const [templates, setTemplates] = useState<SectionTemplate[]>([]);
  const [pageLabels, setPageLabels] = useState<Record<string, string>>({});
  const [activePage, setActivePage] = useState<string>(() =>
    website.pages[pageKey] ? pageKey : Object.keys(website.pages)[0] ?? pageKey
  );
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [inspectorOpen, setInspectorOpen] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Client-side history stack of returned Website snapshots (see file header).
  const [past, setPast] = useState<Website[]>([]);
  const [future, setFuture] = useState<Website[]>([]);

  // Drag-to-insert state (progressive enhancement over click-to-insert).
  const [draggingKey, setDraggingKey] = useState<string | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);

  // Inspector working copy of the selected section's fields (committed on blur).
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [newImg, setNewImg] = useState("");
  const [pickerField, setPickerField] = useState<string | null>(null);
  // Shared (dealership-wide) media library picker -- the field key we're picking for.
  const [sharedLibFor, setSharedLibFor] = useState<string | null>(null);

  const canEdit = website.status === "draft" || website.status === "rejected";
  const templateByKey = useMemo(() => Object.fromEntries(templates.map((t) => [t.key, t])), [templates]);
  const sections = website.pages[activePage]?.sections ?? [];
  const pages = Object.keys(website.pages).map((k) => ({ key: k, label: pageLabels[k] ?? k }));
  const selected = selectedIndex != null ? sections[selectedIndex] ?? null : null;
  const selectedTemplate = selected ? templateByKey[selected.section_key] : undefined;

  useEffect(() => {
    listSectionTemplates().then(setTemplates).catch(() => {});
    listPageKeys()
      .then((keys) => setPageLabels(Object.fromEntries(keys.map((p) => [p.key, p.label]))))
      .catch(() => {});
  }, []);

  // Keep the active page valid and the selection in range as the site changes.
  useEffect(() => {
    if (!website.pages[activePage]) {
      setActivePage(Object.keys(website.pages)[0] ?? activePage);
      setSelectedIndex(null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [website]);

  useEffect(() => {
    setSelectedIndex(null);
  }, [activePage]);

  // Re-seed the inspector draft whenever the selection or persisted content changes.
  useEffect(() => {
    if (selected && selectedTemplate) {
      setDraft(Object.fromEntries(selectedTemplate.fields.map((f) => [f.key, String(selected.fields[f.key] ?? "")])));
    } else {
      setDraft({});
    }
    setPickerField(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedIndex, activePage, website]);

  // --- Mutation core: run an API call, snapshot into history, propagate result -------
  async function commit(fn: () => Promise<Website>): Promise<Website | null> {
    const snapshot = website;
    setBusy(true);
    setError(null);
    try {
      const updated = await fn();
      setPast((p) => [...p, snapshot].slice(-HISTORY_CAP));
      setFuture([]);
      onWebsiteChange(updated);
      return updated;
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      return null;
    } finally {
      setBusy(false);
    }
  }

  async function insertSection(sectionKey: string, at?: number) {
    if (!canEdit) return;
    const t = templateByKey[sectionKey];
    const fields: Record<string, unknown> = {};
    (t?.fields ?? []).forEach((f) => {
      if (f.default !== undefined) fields[f.key] = f.default;
    });
    const target = at ?? (selectedIndex != null ? selectedIndex + 1 : sections.length);
    const updated = await commit(async () => {
      let w = await addSection(website.id, activePage, sectionKey, fields);
      const from = w.pages[activePage].sections.length - 1;
      if (target < from) {
        const order = w.pages[activePage].sections.map((_, i) => i);
        order.splice(from, 1);
        order.splice(target, 0, from);
        w = await reorderSections(website.id, activePage, order);
      }
      return w;
    });
    if (updated) setSelectedIndex(Math.min(target, updated.pages[activePage].sections.length - 1));
  }

  async function duplicateSection(index: number) {
    if (!canEdit) return;
    const s = sections[index];
    if (!s) return;
    const target = index + 1;
    const updated = await commit(async () => {
      let w = await addSection(website.id, activePage, s.section_key, { ...s.fields });
      const from = w.pages[activePage].sections.length - 1;
      if (target < from) {
        const order = w.pages[activePage].sections.map((_, i) => i);
        order.splice(from, 1);
        order.splice(target, 0, from);
        w = await reorderSections(website.id, activePage, order);
      }
      return w;
    });
    if (updated) setSelectedIndex(target);
  }

  async function moveSection(index: number, dir: -1 | 1) {
    if (!canEdit) return;
    const target = index + dir;
    if (target < 0 || target >= sections.length) return;
    const order = sections.map((_, i) => i);
    const tmp = order[index];
    order[index] = order[target];
    order[target] = tmp;
    const updated = await commit(() => reorderSections(website.id, activePage, order));
    if (updated) setSelectedIndex(target);
  }

  async function deleteSection(index: number) {
    if (!canEdit) return;
    const updated = await commit(() => removeSection(website.id, activePage, index));
    if (updated) setSelectedIndex(null);
  }

  async function toggleLock(index: number) {
    const s = sections[index];
    if (!s) return;
    await commit(() => setSectionLocked(website.id, activePage, index, !s.locked));
  }

  async function regen(index: number) {
    if (!canEdit) return;
    await commit(async () => {
      const r = await regenerateSection(website.id, activePage, index);
      if (r.error) setError(r.error);
      return r;
    });
  }

  async function editField(index: number, key: string, value: string) {
    if (!canEdit) return;
    const s = sections[index];
    if (!s || s.locked) return;
    await commit(() => updateSectionFields(website.id, activePage, index, { ...s.fields, [key]: value }));
  }

  async function addImg() {
    if (!newImg.trim()) return;
    await commit(() => addLibraryImage(website.id, newImg.trim()));
    setNewImg("");
  }

  function undo() {
    if (past.length === 0) return;
    const prev = past[past.length - 1];
    setPast((p) => p.slice(0, -1));
    setFuture((f) => [website, ...f].slice(0, HISTORY_CAP));
    setSelectedIndex(null);
    onWebsiteChange(prev);
  }

  function redo() {
    if (future.length === 0) return;
    const next = future[0];
    setFuture((f) => f.slice(1));
    setPast((p) => [...p, website].slice(-HISTORY_CAP));
    setSelectedIndex(null);
    onWebsiteChange(next);
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      const w = await getWebsite(website.id);
      onWebsiteChange(w);
      setSaved(true);
      setTimeout(() => setSaved(false), 1600);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to refresh");
    } finally {
      setBusy(false);
    }
  }

  async function publish() {
    await commit(() => submitWebsite(website.id));
  }

  // Keyboard undo/redo -- but never hijack native undo while typing in a field.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || el.tagName === "INPUT" || el.tagName === "TEXTAREA")) return;
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
        e.preventDefault();
        if (e.shiftKey) redo();
        else undo();
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [past, future, website]);

  const panelBorder = tc(theme, "border-zinc-800", "border-zinc-200");
  const panelBg = tc(theme, "bg-brand-charcoal", "bg-white");

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      {/* ---- Top toolbar --------------------------------------------------------- */}
      <div className={`flex items-center gap-3 px-4 py-2 border-b shrink-0 flex-wrap ${panelBorder}`}>
        {/* Page selector */}
        <div className={`flex rounded-md border overflow-hidden ${tc(theme, "border-zinc-700", "border-zinc-300")}`}>
          {pages.map((p) => (
            <WorkButton aria-pressed={activePage === p.key} type="submit"
              key={p.key}
              onClick={() => setActivePage(p.key)}
              className={`text-xs px-2.5 py-1 transition ${
                activePage === p.key ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-400 hover:text-white", "bg-white text-zinc-600 hover:text-black")
              }`}
            >
              {p.label}
              <span className="ml-1 text-xs opacity-60">({website.pages[p.key]?.sections.length ?? 0})</span>
            </WorkButton>
          ))}
        </div>

        {/* Device toggle */}
        <div className={`flex rounded-md border overflow-hidden ${tc(theme, "border-zinc-700", "border-zinc-300")}`}>
          {(["desktop", "mobile"] as const).map((d) => (
            <WorkButton type="submit"
              key={d}
              onClick={() => setDevice(d)}
              title={d === "desktop" ? "Desktop preview" : "Mobile preview"}
              className={`text-xs px-2.5 py-1 transition ${
                device === d ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-400 hover:text-white", "bg-white text-zinc-600 hover:text-black")
              }`}
            >
              {d === "desktop" ? "🖥 Desktop" : "📱 Mobile"}
            </WorkButton>
          ))}
        </div>

        <div className="flex items-center gap-1.5">
          <Btn theme={theme} small onClick={undo} disabled={past.length === 0} title="Undo (⌘Z)">
            ↶ Undo
          </Btn>
          <Btn theme={theme} small onClick={redo} disabled={future.length === 0} title="Redo (⇧⌘Z)">
            ↷ Redo
          </Btn>
        </div>

        <div className="flex items-center gap-2 ml-auto">
          {error && <span className="text-xs text-red-400 max-w-[240px] truncate" title={error}>{error}</span>}
          {busy && <span className="text-xs text-zinc-500">Working…</span>}
          {saved && <span className="text-xs text-green-400 font-medium animate-pulse">Saved ✓</span>}
          <span className="text-xs px-2 py-0.5 rounded uppercase tracking-wide bg-zinc-800 text-zinc-400">{website.status.replace(/_/g, " ")}</span>
          <Btn theme={theme} small onClick={save} disabled={busy}>
            💾 Save
          </Btn>
          {canEdit && (
            <Btn theme={theme} small kind="primary" onClick={publish} disabled={busy}>
              🚀 Publish
            </Btn>
          )}
          {onToggleFullScreen && (
            <Btn theme={theme} small onClick={onToggleFullScreen}>
              {fullScreen ? "⤡ Exit" : "⤢ Full Screen"}
            </Btn>
          )}
        </div>
      </div>

      {/* ---- 3-column shell ------------------------------------------------------ */}
      <div className="flex-1 flex min-h-0">
        {/* Left: insert drawer */}
        <div className={`w-56 shrink-0 border-r flex flex-col ${panelBorder}`}>
          <div className={`px-3 py-2 text-xs font-semibold uppercase tracking-wide text-zinc-500 border-b ${panelBorder}`}>Add Section</div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
            {!canEdit && (
              <div className="text-xs text-zinc-500 px-1 py-2">This site is {website.status.replace(/_/g, " ")} — editing is locked until it&apos;s back in draft.</div>
            )}
            {templates.map((t) => (
              <div
                key={t.key}
                draggable={canEdit}
                onDragStart={(e) => {
                  setDraggingKey(t.key);
                  e.dataTransfer.setData("text/plain", t.key);
                  e.dataTransfer.effectAllowed = "copy";
                }}
                onDragEnd={() => {
                  setDraggingKey(null);
                  setDropIndex(null);
                }}
                onClick={() => insertSection(t.key)}
                className={`rounded-lg border p-2 transition ${canEdit ? "cursor-grab hover:border-brand-teal active:cursor-grabbing" : "opacity-50 cursor-not-allowed"} ${panelBorder} ${panelBg}`}
                title={canEdit ? "Click to append, or drag onto the canvas" : undefined}
              >
                <div className="text-xs font-semibold flex items-center gap-1">
                  <span className="text-zinc-500">⠿</span>
                  {t.name}
                </div>
                {t.description && <div className="text-xs text-zinc-500 mt-0.5 leading-snug">{t.description}</div>}
              </div>
            ))}
            {templates.length === 0 && <div className="text-xs text-zinc-500 px-1">Loading sections…</div>}
          </div>
        </div>

        {/* Center: canvas */}
        <div
          className={`flex-1 overflow-auto ${tc(theme, "bg-zinc-950/60", "bg-zinc-100")} flex justify-center py-6 px-4`}
          onClick={() => setSelectedIndex(null)}
        >
          <div
            className="bg-white shadow-2xl transition-all self-start"
            style={{ width: device === "desktop" ? DESKTOP_WIDTH : MOBILE_WIDTH, maxWidth: "100%" }}
          >
            {sections.length === 0 ? (
              <div
                onDragOver={(e) => {
                  if (draggingKey && canEdit) {
                    e.preventDefault();
                    setDropIndex(0);
                  }
                }}
                onDrop={(e) => {
                  if (!draggingKey || !canEdit) return;
                  e.preventDefault();
                  const key = draggingKey;
                  setDraggingKey(null);
                  setDropIndex(null);
                  insertSection(key, 0);
                }}
                className="py-24 px-6 text-center text-sm text-zinc-400"
              >
                This page is empty. Click a section on the left to add one — or drag it here.
              </div>
            ) : (
              sections.map((s, i) => {
                const isSel = selectedIndex === i;
                const editable = canEdit && !s.locked;
                return (
                  <div
                    key={i}
                    className={`group relative ${isSel ? "ring-2 ring-brand-teal ring-inset z-10" : "hover:ring-2 hover:ring-brand-teal/40 hover:ring-inset"}`}
                    onClick={(e) => {
                      e.stopPropagation();
                      setSelectedIndex(i);
                    }}
                    onDragOver={(e) => {
                      if (!draggingKey || !canEdit) return;
                      e.preventDefault();
                      const rect = e.currentTarget.getBoundingClientRect();
                      const before = e.clientY < rect.top + rect.height / 2;
                      setDropIndex(before ? i : i + 1);
                    }}
                    onDrop={(e) => {
                      if (!draggingKey || !canEdit) return;
                      e.preventDefault();
                      const at = dropIndex ?? i;
                      const key = draggingKey;
                      setDraggingKey(null);
                      setDropIndex(null);
                      insertSection(key, at);
                    }}
                  >
                    {/* drop indicators */}
                    {dropIndex === i && <div className="absolute left-0 right-0 top-0 h-1 bg-brand-teal z-30" />}
                    {dropIndex === i + 1 && <div className="absolute left-0 right-0 bottom-0 h-1 bg-brand-teal z-30" />}

                    {/* section label + lock badge */}
                    <div className={`absolute top-2 left-2 z-20 flex items-center gap-1 ${isSel ? "opacity-100" : "opacity-0 group-hover:opacity-100"} transition`}>
                      <span className="text-xs px-1.5 py-0.5 rounded bg-zinc-900/90 text-zinc-300 border border-white/10">
                        {templateByKey[s.section_key]?.name ?? s.section_key}
                      </span>
                      {s.locked && <span className="text-xs px-1.5 py-0.5 rounded bg-amber-950/90 text-amber-300">🔒</span>}
                    </div>

                    {/* floating per-section toolbar */}
                    {canEdit && (
                      <div className={`absolute top-2 right-2 z-20 flex items-center gap-1 ${isSel ? "opacity-100" : "opacity-0 group-hover:opacity-100"} transition`}>
                        <IconBtn onClick={() => moveSection(i, -1)} disabled={busy || s.locked || i === 0} title="Move up">↑</IconBtn>
                        <IconBtn onClick={() => moveSection(i, 1)} disabled={busy || s.locked || i === sections.length - 1} title="Move down">↓</IconBtn>
                        <IconBtn onClick={() => duplicateSection(i)} disabled={busy || s.locked} title="Duplicate">⧉</IconBtn>
                        <IconBtn onClick={() => regen(i)} disabled={busy || s.locked} title="AI Rewrite">✨</IconBtn>
                        <IconBtn onClick={() => toggleLock(i)} disabled={busy} title={s.locked ? "Unlock" : "Lock"}>{s.locked ? "🔓" : "🔒"}</IconBtn>
                        <IconBtn onClick={() => deleteSection(i)} disabled={busy || s.locked} title="Delete" danger>✕</IconBtn>
                      </div>
                    )}

                    <SiteSectionRenderer
                      section={s}
                      themeId={website.studio_config?.theme_id}
                      websiteName={website.name}
                      editable={editable}
                      onFieldEdit={(key, value) => editField(i, key, value)}
                    />
                  </div>
                );
              })
            )}
            {/* trailing append drop zone */}
            {sections.length > 0 && (
              <div
                onDragOver={(e) => {
                  if (draggingKey && canEdit) {
                    e.preventDefault();
                    setDropIndex(sections.length);
                  }
                }}
                onDrop={(e) => {
                  if (!draggingKey || !canEdit) return;
                  e.preventDefault();
                  const key = draggingKey;
                  setDraggingKey(null);
                  setDropIndex(null);
                  insertSection(key, sections.length);
                }}
                className={`h-8 ${dropIndex === sections.length ? "bg-brand-teal/30" : ""}`}
              />
            )}
          </div>
        </div>

        {/* Right: inspector */}
        {inspectorOpen ? (
          <div className={`w-80 shrink-0 border-l flex flex-col ${panelBorder}`}>
            <div className={`flex items-center justify-between px-3 py-2 border-b ${panelBorder}`}>
              <div className="text-xs font-semibold uppercase tracking-wide text-zinc-500">Inspector</div>
              <WorkButton type="submit" onClick={() => setInspectorOpen(false)} title="Collapse" className="text-zinc-500 hover:text-white text-xs">→│</WorkButton>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-3">
              {!selected || !selectedTemplate ? (
                <div className="text-center text-zinc-500 pt-10 px-4 space-y-2">
                  <div className="text-3xl">🎯</div>
                  <div className="text-sm font-medium">Nothing selected</div>
                  <div className="text-xs">Click any section on the canvas to edit its content here, or add one from the left.</div>
                </div>
              ) : (
                <>
                  <div className="flex items-center justify-between">
                    <div className="text-sm font-semibold">{selectedTemplate.name}</div>
                    {selected.locked && <span className="text-xs px-1.5 py-0.5 rounded bg-amber-950 text-amber-300">🔒 locked</span>}
                  </div>

                  {selected.locked && (
                    <div className="text-xs text-amber-300/80 bg-amber-950/40 border border-amber-900/50 rounded px-2 py-1.5">
                      This section is locked. Unlock it to edit its fields.
                    </div>
                  )}

                  {selectedTemplate.fields.map((f: SectionField) => (
                    <div key={f.key} className="space-y-1">
                      <div className="flex items-center justify-between gap-2">
                        <div className="text-xs text-zinc-500 flex items-center gap-1">
                          {f.label}
                          {f.ai_writable && <span className="text-brand-teal">· AI-writable</span>}
                        </div>
                        {(f.type === "textarea" || f.ai_writable) && canEdit && !selected.locked && (
                          <AiAssistButton
                            theme={theme}
                            aria-label={f.label} value={draft[f.key] ?? ""}
                            context={f.label}
                            fieldLabel={f.label}
                            onApply={(text, mode) => {
                              const next = mode === "insert" ? `${draft[f.key] ?? ""}${text}` : text;
                              setDraft((d) => ({ ...d, [f.key]: next }));
                              if (selectedIndex != null) editField(selectedIndex, f.key, next);
                            }}
                          />
                        )}
                      </div>
                      {f.type === "textarea" ? (
                        <WorkTextarea
                          aria-label={f.label} value={draft[f.key] ?? ""}
                          disabled={selected.locked || !canEdit}
                          onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                          onBlur={() => {
                            if (selectedIndex == null) return;
                            const persisted = String(selected.fields[f.key] ?? "");
                            if ((draft[f.key] ?? "") !== persisted) editField(selectedIndex, f.key, draft[f.key] ?? "");
                          }}
                          rows={3}
                          className={tc(theme, "w-full text-xs rounded px-2 py-1.5 bg-zinc-900 border border-zinc-700 text-white disabled:opacity-50", "w-full text-xs rounded px-2 py-1.5 bg-white border border-zinc-300 text-black disabled:opacity-50")}
                        />
                      ) : (
                        <WorkInput
                          aria-label={f.label} value={draft[f.key] ?? ""}
                          disabled={selected.locked || !canEdit}
                          onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
                          onBlur={() => {
                            if (selectedIndex == null) return;
                            const persisted = String(selected.fields[f.key] ?? "");
                            if ((draft[f.key] ?? "") !== persisted) editField(selectedIndex, f.key, draft[f.key] ?? "");
                          }}
                          className={tc(theme, "w-full text-xs rounded px-2 py-1.5 bg-zinc-900 border border-zinc-700 text-white disabled:opacity-50", "w-full text-xs rounded px-2 py-1.5 bg-white border border-zinc-300 text-black disabled:opacity-50")}
                        />
                      )}

                      {/* Image field: quick-pick from the site's image library */}
                      {isImageField(f.key) && canEdit && !selected.locked && (
                        <div className="space-y-1">
                          <div className="flex items-center gap-3">
                          <WorkButton type="submit"
                            onClick={() => setPickerField((p) => (p === f.key ? null : f.key))}
                            className="text-xs text-brand-teal hover:underline"
                          >
                            {pickerField === f.key ? "Close library" : "🖼 This site's images"}
                          </WorkButton>
                          <WorkButton type="submit"
                            onClick={() => setSharedLibFor(f.key)}
                            className="text-xs text-brand-teal hover:underline"
                          >
                            🖼 Shared media library
                          </WorkButton>
                          </div>
                          {pickerField === f.key && (
                            <div className="space-y-2 rounded border border-zinc-700 p-2">
                              <div className="flex flex-wrap gap-1.5">
                                {website.image_library.map((img) => (
                                  <WorkButton type="submit"
                                    key={img.id}
                                    onClick={() => {
                                      setDraft((d) => ({ ...d, [f.key]: img.url }));
                                      if (selectedIndex != null) editField(selectedIndex, f.key, img.url);
                                    }}
                                    title={img.label || img.url}
                                    className="w-12 h-12 rounded overflow-hidden border border-zinc-700 hover:border-brand-teal"
                                  >
                                    {/* eslint-disable-next-line @next/next/no-img-element */}
                                    <img src={img.url} alt={img.label || ""} className="w-full h-full object-cover" onError={(e) => ((e.target as HTMLImageElement).style.display = "none")} />
                                  </WorkButton>
                                ))}
                                {website.image_library.length === 0 && <div className="text-xs text-zinc-500">No images yet.</div>}
                              </div>
                              <div className="flex gap-1">
                                <WorkField label="Add image URL"><WorkInput
                                  value={newImg}
                                  onChange={(e) => setNewImg(e.target.value)}
                                  placeholder="Add image URL…"
                                  className={tc(theme, "flex-1 text-xs rounded px-2 py-1 bg-zinc-900 border border-zinc-700 text-white", "flex-1 text-xs rounded px-2 py-1 bg-white border border-zinc-300 text-black")}
                                /></WorkField>
                                <Btn theme={theme} small onClick={addImg} disabled={busy || !newImg.trim()}>Add</Btn>
                              </div>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  ))}

                  {canEdit && (
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {selectedTemplate.fields.some((f) => f.ai_writable) && (
                        <Btn theme={theme} small onClick={() => selectedIndex != null && regen(selectedIndex)} disabled={busy || selected.locked}>
                          ✨ AI Rewrite
                        </Btn>
                      )}
                      <Btn theme={theme} small onClick={() => selectedIndex != null && toggleLock(selectedIndex)} disabled={busy}>
                        {selected.locked ? "🔓 Unlock" : "🔒 Lock"}
                      </Btn>
                      <Btn theme={theme} small kind="danger" onClick={() => selectedIndex != null && deleteSection(selectedIndex)} disabled={busy || selected.locked}>
                        Delete
                      </Btn>
                    </div>
                  )}

                  {/* Style (coming soon) -------------------------------------------------
                      Placeholder home for a future style system (padding / colors /
                      typography). The data model (lib/websites.ts WebsiteSection) has NO
                      style fields today, so there is deliberately nothing persisted here
                      yet -- surfacing fake style controls would silently drop edits. */}
                  <div className={`mt-3 pt-3 border-t ${panelBorder}`}>
                    <div className="text-xs uppercase tracking-wide text-zinc-600 mb-1">Style (coming soon)</div>
                    <div className="text-xs text-zinc-500 rounded border border-dashed border-zinc-700 px-2 py-3 text-center">
                      Padding, colors & typography controls will live here once the model supports them.
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        ) : (
          <WorkButton type="submit"
            onClick={() => setInspectorOpen(true)}
            title="Open inspector"
            className={`w-8 shrink-0 border-l flex items-center justify-center text-zinc-500 hover:text-white ${panelBorder}`}
          >
            │←
          </WorkButton>
        )}
      </div>

      <ImageLibraryPicker
        open={sharedLibFor !== null}
        onClose={() => setSharedLibFor(null)}
        theme={theme}
        onPick={(url) => {
          const key = sharedLibFor;
          if (key) {
            setDraft((d) => ({ ...d, [key]: url }));
            if (selectedIndex != null) editField(selectedIndex, key, url);
          }
          setSharedLibFor(null);
        }}
      />
    </div>
  );
}
