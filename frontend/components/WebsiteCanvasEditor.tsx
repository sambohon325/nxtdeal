"use client";
import { WorkButton, WorkTextarea, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// The real, freeform pixel-drag Wix-style canvas (2026-07-18, Cowork, interactive).
// Sam: "have a button that says edit website where you can open it up fully into a
// wix drag and drop, fully editable website builder." Session 90 shipped the
// near-term version (a maximized visual-preview + side-panel field editor,
// components/WebsiteBuilderBoard.tsx's BuilderTab); this is the deferred "much
// larger build" -- every section on a page can be dragged to any x/y position and
// resized, not just reordered top-to-bottom. Renders the exact same real
// components/SiteSectionRenderer.tsx every other real surface in this codebase uses
// (the public site, the structured-mode preview) so what a dealer arranges here is
// genuinely what a visitor sees, absolutely positioned instead of stacked.
//
// Coordinate system: sections are stored in a fixed CANVAS_WIDTH=1200 virtual pixel
// space (backend/core/websites.py). This component renders that space scaled down to
// fit whatever width its container actually has (a CSS transform, same "render at
// real size, scale the whole thing down" trick components/WebsiteBuilderBoard.tsx's
// old static preview already used at a fixed 0.34), but INTERACTIVE this time --
// mouse deltas during a drag/resize are divided by the current scale factor before
// being applied to the stored (unscaled) x/y/width/height. A drag/resize is tracked
// entirely client-side (a local, optimistic `localLayouts` override) and only
// persisted once, on mouse-up -- never on every mousemove, since a real save_graph()
// call costs real seconds on this graph's size (the same "batch the writes, not the
// gesture" discipline this codebase's other drag interactions already follow).
//
// Layering/z-order is NOT a new concept -- a section's position in the underlying
// array already determines paint order (later paints on top, same as normal HTML
// flow), so "Bring to Front"/"Send to Back" just calls the existing, already-real
// reorderSections().
import { useEffect, useMemo, useRef, useState } from "react";
import {
  type Website,
  type WebsiteSection,
  type SectionTemplate,
  type SectionLayout,
  CANVAS_WIDTH,
  addSection,
  removeSection,
  setSectionLocked,
  setSectionLayout,
  reorderSections,
  updateSectionFields,
  regenerateSection,
} from "@/lib/websites";
import { SiteSectionRenderer } from "@/components/SiteSectionRenderer";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const DEFAULT_HEIGHT = 320;
const SECTION_GAP = 24;
const MIN_SIZE = 40;
const CANVAS_HEIGHT_FLOOR = 700;
const CANVAS_BOTTOM_PAD = 160;

function fallbackLayout(index: number, sections: WebsiteSection[]): SectionLayout {
  // Same deterministic stack-from-top-down default the backend's own
  // set_page_layout_mode() auto-backfill uses, computed client-side for any section
  // that genuinely has no stored layout yet (e.g. one just added this session,
  // before its own first setSectionLayout call lands).
  let y = 0;
  for (let i = 0; i < index; i++) {
    const l = sections[i]?.layout;
    y = (l ? l.y + l.height : y + DEFAULT_HEIGHT) + SECTION_GAP;
  }
  return { x: 0, y, width: CANVAS_WIDTH, height: DEFAULT_HEIGHT };
}

function Btn({
  theme, children, onClick, small, kind, disabled,
}: {
  theme: Theme; children: React.ReactNode; onClick?: () => void; small?: boolean;
  kind?: "primary" | "danger"; disabled?: boolean;
}) {
  const base = small ? "text-[11px] px-2 py-1" : "text-xs px-3 py-1.5";
  const style =
    kind === "primary"
      ? "bg-brand-teal text-black font-semibold hover:brightness-95"
      : kind === "danger"
      ? "border border-red-500/40 text-red-400 hover:bg-red-500/10"
      : tc(theme, "border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500", "border border-zinc-300 text-zinc-700 hover:text-black hover:border-zinc-500");
  return (
    <WorkButton type="submit" onClick={onClick} disabled={disabled} className={`${base} rounded-md transition disabled:opacity-40 ${style}`}>
      {children}
    </WorkButton>
  );
}

function Input({
  theme, value, onChange, textarea, label,
}: { theme: Theme; value: string; onChange: (v: string) => void; textarea?: boolean; label:string }) {
  const cls = tc(
    theme,
    "w-full px-2 py-1.5 text-xs rounded bg-zinc-900 border border-zinc-700 text-white",
    "w-full px-2 py-1.5 text-xs rounded bg-white border border-zinc-300 text-black"
  );
  return textarea ? (
    <WorkTextarea aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} rows={3} className={cls} />
  ) : (
    <WorkInput aria-label={label} value={value} onChange={(e) => onChange(e.target.value)} className={cls} />
  );
}

type DragMode = "move" | "resize";

export function WebsiteCanvasEditor({
  theme,
  website,
  pageKey,
  sectionTemplates,
  canEdit,
  onChanged,
}: {
  theme: Theme;
  website: Website;
  pageKey: string;
  sectionTemplates: SectionTemplate[];
  canEdit: boolean;
  onChanged: () => void;
}) {
  const page = website.pages[pageKey] || { sections: [] };
  const sections = page.sections;
  const templateByKey = useMemo(() => Object.fromEntries(sectionTemplates.map((t) => [t.key, t])), [sectionTemplates]);

  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);

  useEffect(() => {
    function measure() {
      const w = containerRef.current?.clientWidth;
      if (w) setScale(Math.max(0.25, Math.min(1, (w - 32) / CANVAS_WIDTH)));
    }
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  // Local, optimistic per-section layout override -- live during a drag/resize
  // gesture, re-synced from the real server data whenever the underlying website
  // (or the active page) changes out from under it.
  const [localLayouts, setLocalLayouts] = useState<Record<number, SectionLayout>>({});
  useEffect(() => {
    setLocalLayouts({});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [website.id, pageKey, sections.length]);

  const [selected, setSelected] = useState<number | null>(null);
  const [editingFields, setEditingFields] = useState(false);
  const [fieldValues, setFieldValues] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [addingKey, setAddingKey] = useState("");
  const [error, setError] = useState<string | null>(null);

  function layoutFor(index: number): SectionLayout {
    return localLayouts[index] || sections[index]?.layout || fallbackLayout(index, sections);
  }

  const canvasHeight = Math.max(
    CANVAS_HEIGHT_FLOOR,
    ...sections.map((_, i) => layoutFor(i).y + layoutFor(i).height + CANVAS_BOTTOM_PAD)
  );

  const dragRef = useRef<{
    index: number;
    mode: DragMode;
    startClientX: number;
    startClientY: number;
    startLayout: SectionLayout;
  } | null>(null);

  function startDrag(e: React.MouseEvent, index: number, mode: DragMode) {
    if (!canEdit || sections[index]?.locked) return;
    e.preventDefault();
    e.stopPropagation();
    setSelected(index);
    setEditingFields(false);

    const startLayout = layoutFor(index);
    dragRef.current = { index, mode, startClientX: e.clientX, startClientY: e.clientY, startLayout };

    function onMouseMove(moveEvent: MouseEvent) {
      const drag = dragRef.current;
      if (!drag) return;
      const dx = (moveEvent.clientX - drag.startClientX) / scale;
      const dy = (moveEvent.clientY - drag.startClientY) / scale;

      if (drag.mode === "move") {
        setLocalLayouts((prev) => ({
          ...prev,
          [drag.index]: {
            ...drag.startLayout,
            x: Math.max(0, drag.startLayout.x + dx),
            y: Math.max(0, drag.startLayout.y + dy),
          },
        }));
      } else {
        setLocalLayouts((prev) => ({
          ...prev,
          [drag.index]: {
            ...drag.startLayout,
            width: Math.max(MIN_SIZE, drag.startLayout.width + dx),
            height: Math.max(MIN_SIZE, drag.startLayout.height + dy),
          },
        }));
      }
    }

    function onMouseUp() {
      window.removeEventListener("mousemove", onMouseMove);
      window.removeEventListener("mouseup", onMouseUp);
      const drag = dragRef.current;
      dragRef.current = null;
      if (!drag) return;

      setLocalLayouts((prev) => {
        const finalLayout = prev[drag.index];
        if (finalLayout) {
          setSectionLayout(website.id, pageKey, drag.index, finalLayout)
            .then(onChanged)
            .catch((err) => setError(err instanceof Error ? err.message : "Couldn't save that position."));
        }
        return prev;
      });
    }

    window.addEventListener("mousemove", onMouseMove);
    window.addEventListener("mouseup", onMouseUp);
  }

  async function bringToFront(index: number) {
    const order = sections.map((_, i) => i);
    order.splice(order.indexOf(index), 1);
    order.push(index);
    setBusy(true);
    try {
      await reorderSections(website.id, pageKey, order);
      onChanged();
      setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't reorder.");
    } finally {
      setBusy(false);
    }
  }

  async function sendToBack(index: number) {
    const order = sections.map((_, i) => i);
    order.splice(order.indexOf(index), 1);
    order.unshift(index);
    setBusy(true);
    try {
      await reorderSections(website.id, pageKey, order);
      onChanged();
      setSelected(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't reorder.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleLock(index: number) {
    setBusy(true);
    try {
      await setSectionLocked(website.id, pageKey, index, !sections[index].locked);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function removeSel(index: number) {
    setBusy(true);
    try {
      await removeSection(website.id, pageKey, index);
      onChanged();
      setSelected(null);
      setEditingFields(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't remove that section.");
    } finally {
      setBusy(false);
    }
  }

  function openFieldEditor(index: number) {
    const s = sections[index];
    setFieldValues(Object.fromEntries(Object.entries(s.fields || {}).map(([k, v]) => [k, String(v ?? "")])));
    setEditingFields(true);
  }

  async function saveFields(index: number) {
    setBusy(true);
    setError(null);
    try {
      await updateSectionFields(website.id, pageKey, index, fieldValues);
      onChanged();
      setEditingFields(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't save those fields.");
    } finally {
      setBusy(false);
    }
  }

  async function aiRewrite(index: number) {
    setBusy(true);
    setError(null);
    try {
      await regenerateSection(website.id, pageKey, index);
      onChanged();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't AI-rewrite this section.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddSection() {
    if (!addingKey) return;
    const template = templateByKey[addingKey];
    const fields: Record<string, unknown> = {};
    (template?.fields || []).forEach((f) => {
      if (f.default !== undefined) fields[f.key] = f.default;
    });

    // Place the new section stacked below everything currently on the canvas,
    // computed from the real current layouts (including any live-dragged, not-yet-
    // saved position) rather than the stale server copy.
    const maxBottom = sections.reduce((max, _, i) => {
      const l = layoutFor(i);
      return Math.max(max, l.y + l.height);
    }, 0);

    setBusy(true);
    setError(null);
    try {
      const updated = await addSection(website.id, pageKey, addingKey, fields);
      const newIndex = (updated.pages[pageKey]?.sections.length || 1) - 1;
      await setSectionLayout(website.id, pageKey, newIndex, {
        x: 0,
        y: sections.length === 0 ? 0 : maxBottom + SECTION_GAP,
        width: CANVAS_WIDTH,
        height: DEFAULT_HEIGHT,
      });
      onChanged();
      setAddingKey("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't add that section.");
    } finally {
      setBusy(false);
    }
  }

  const selectedSection = selected !== null ? sections[selected] : null;
  const selectedTemplate = selectedSection ? templateByKey[selectedSection.section_key] : null;
  const writableFields = (selectedTemplate?.fields || []).filter((f) => f.ai_writable);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className={tc(theme, "flex items-center gap-2 px-3 py-2 border-b border-zinc-800 shrink-0 flex-wrap", "flex items-center gap-2 px-3 py-2 border-b border-zinc-200 shrink-0 flex-wrap")}>
        <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>
          Freeform canvas -- drag any section anywhere, resize from the corner. {sections.length} section(s).
        </span>
        {canEdit && (
          <div className="flex items-center gap-2 ml-auto">
            <WorkField label="Section to add"><WorkSelect
              value={addingKey}
              onChange={(e) => setAddingKey(e.target.value)}
              className={tc(theme, "text-xs bg-zinc-900 border border-zinc-700 text-white rounded px-2 py-1.5", "text-xs bg-white border border-zinc-300 text-black rounded px-2 py-1.5")}
            >
              <option value="">+ Add section…</option>
              {sectionTemplates.map((t) => (
                <option key={t.key} value={t.key}>{t.name}</option>
              ))}
            </WorkSelect></WorkField>
            <Btn theme={theme} onClick={handleAddSection} disabled={!addingKey || busy}>Add to Canvas</Btn>
          </div>
        )}
      </div>

      {error && <div className="px-3 py-1.5 text-xs text-red-400 shrink-0">{error}</div>}

      <div className="flex-1 flex min-h-0">
        <div
          ref={containerRef}
          className={tc(theme, "flex-1 overflow-auto bg-zinc-950 p-4", "flex-1 overflow-auto bg-zinc-100 p-4")}
          onClick={() => {
            setSelected(null);
            setEditingFields(false);
          }}
        >
          <div
            className="relative bg-white shadow-2xl mx-auto origin-top"
            style={{
              width: CANVAS_WIDTH,
              height: canvasHeight,
              transform: `scale(${scale})`,
              transformOrigin: "top center",
              backgroundImage:
                "linear-gradient(#eee 1px, transparent 1px), linear-gradient(90deg, #eee 1px, transparent 1px)",
              backgroundSize: "40px 40px",
            }}
          >
            {sections.length === 0 && (
              <div className="absolute inset-0 flex items-center justify-center text-sm text-zinc-400">
                Nothing on this page yet -- add a section above, then drag it anywhere.
              </div>
            )}

            {sections.map((s, i) => {
              const l = layoutFor(i);
              const isSelected = selected === i;
              return (
                <div
                  key={i}
                  onClick={(e) => {
                    e.stopPropagation();
                    setSelected(i);
                    setEditingFields(false);
                  }}
                  className="absolute overflow-hidden"
                  style={{
                    left: l.x,
                    top: l.y,
                    width: l.width,
                    height: l.height,
                    outline: isSelected ? "3px solid #3FBCC4" : s.locked ? "2px dashed #b45309" : "1px solid #e4e4e7",
                    outlineOffset: -1,
                    cursor: canEdit && !s.locked ? "move" : "default",
                    zIndex: isSelected ? 50 : i,
                  }}
                  onMouseDown={(e) => startDrag(e, i, "move")}
                >
                  {/* The real, actual visual -- same renderer the live public site uses.
                      pointer-events-none so a drag doesn't fight with, say, a car-builder
                      dropdown or a contact-form input while editing. */}
                  <div className="pointer-events-none w-full h-full overflow-hidden">
                    <SiteSectionRenderer section={s} websiteId={undefined} />
                  </div>

                  {s.locked && (
                    <div className="absolute top-1.5 left-1.5 text-xs font-bold px-1.5 py-0.5 rounded bg-amber-800 text-amber-100 pointer-events-none">
                      🔒 locked
                    </div>
                  )}

                  {canEdit && !s.locked && (
                    <div
                      onMouseDown={(e) => startDrag(e, i, "resize")}
                      className="absolute bottom-0 right-0 w-4 h-4 cursor-se-resize bg-brand-teal/80"
                      style={{ clipPath: "polygon(100% 0, 100% 100%, 0 100%)" }}
                    />
                  )}

                  {isSelected && (
                    <div
                      className="absolute -top-9 left-0 flex items-center gap-1 bg-zinc-900 border border-zinc-700 rounded-md px-1.5 py-1 shadow-lg whitespace-nowrap"
                      onClick={(e) => e.stopPropagation()}
                      onMouseDown={(e) => e.stopPropagation()}
                    >
                      <span className="text-xs text-zinc-400 px-1">{templateByKey[s.section_key]?.name || s.section_key}</span>
                      {canEdit && (
                        <>
                          <WorkButton type="submit" onClick={() => openFieldEditor(i)} className="text-xs px-1.5 py-0.5 rounded bg-zinc-700 text-white hover:bg-zinc-600">Edit</WorkButton>
                          <WorkButton type="submit" onClick={() => bringToFront(i)} className="text-xs px-1.5 py-0.5 rounded bg-zinc-700 text-white hover:bg-zinc-600">Front</WorkButton>
                          <WorkButton type="submit" onClick={() => sendToBack(i)} className="text-xs px-1.5 py-0.5 rounded bg-zinc-700 text-white hover:bg-zinc-600">Back</WorkButton>
                          <WorkButton type="submit" onClick={() => toggleLock(i)} className="text-xs px-1.5 py-0.5 rounded bg-zinc-700 text-white hover:bg-zinc-600">{s.locked ? "Unlock" : "Lock"}</WorkButton>
                          <WorkButton type="submit" variant="danger" onClick={() => removeSel(i)} className="text-xs px-1.5 py-0.5 rounded bg-red-900 text-red-200 hover:bg-red-800">Remove</WorkButton>
                        </>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {editingFields && selectedSection && selected !== null && (
          <div className={tc(theme, "w-[340px] shrink-0 border-l border-zinc-800 flex flex-col overflow-y-auto p-3 space-y-2", "w-[340px] shrink-0 border-l border-zinc-200 flex flex-col overflow-y-auto p-3 space-y-2")}>
            <div className="flex items-center justify-between">
              <div className="text-sm font-semibold">{selectedTemplate?.name || selectedSection.section_key}</div>
              <WorkButton type="submit" onClick={() => setEditingFields(false)} className="text-xs text-zinc-500 hover:text-white">✕</WorkButton>
            </div>
            {writableFields.length > 0 && (
              <Btn theme={theme} small onClick={() => aiRewrite(selected)} disabled={busy}>✨ AI Rewrite</Btn>
            )}
            {(selectedTemplate?.fields || []).map((f) => (
              <div key={f.key}>
                <div className="text-xs text-zinc-500 mb-0.5">
                  {f.label} {f.ai_writable && <span className="text-brand-teal">· AI-writable</span>}
                </div>
                <Input label={f.label}
                  theme={theme}
                  value={fieldValues[f.key] ?? ""}
                  onChange={(v) => setFieldValues((s) => ({ ...s, [f.key]: v }))}
                  textarea={f.type === "textarea"}
                />
              </div>
            ))}
            <Btn theme={theme} kind="primary" small onClick={() => saveFields(selected)} disabled={busy}>Save</Btn>
          </div>
        )}
      </div>
    </div>
  );
}
