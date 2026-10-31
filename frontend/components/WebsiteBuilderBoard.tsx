"use client";
import { WorkButton, WorkTextarea, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Marketing's "Website" Top Menu item, rebuilt session 85 into a real in-Dash builder.
// Sam: "the last bit is the website. I think we've built this out, just haven't put it
// fully in the dashboard. it needs to be a full website builder, with drag and drop
// functionality, layout templates to choose from for independent dealers, OEM
// compliant templates for franchise, image slection, inventory control, about us,
// contact forms that feed into the crm, live chat functionality (wired into the crm).
// each template section should have ai writing abilities, and each website should have
// a toggle for customers between a traiditonal website and a drivefinder.xyz ai
// powered car builder but branded for the dealership. in the admin section, you should
// be able to adjust the seo per page, control the DNS, and preview the site. it needs
// to have personal url functionality that takes the look and feel of the website and
// can be deployed by the sales rep or markeeting / events, and the admin side should
// have google analytics / umami style reporting... lastly, there should be a ai setup
// wizard to walk dealers through this if they don't want to build it themselves."
//
// This is the authenticated, in-Dash builder/admin surface. The backend also exposes a
// fully PUBLIC set of routes (see lib/websites.ts's "PUBLIC" section) for a real
// dealership-visitor-facing page and personal-URL page -- deliberately NOT built as a
// second Next.js frontend in this pass (that's a separate customer storefront surface,
// not "the dashboard" this request was scoped around); the API is ready for one, see
// BUILD_QUEUE.md's session-85 entry.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useRef, useState, type DragEvent } from "react";
import {
  listSectionTemplates,
  listSiteTemplates,
  listPageKeys,
  createWebsite,
  createStudioWebsite,
  createWebsiteWizard,
  listMyWebsites,
  listPendingWebsites,
  getWebsite,
  submitWebsite,
  approveWebsite,
  rejectWebsite,
  addSection,
  updateSectionFields,
  removeSection,
  setSectionLocked,
  reorderSections,
  regenerateSection,
  applySiteTemplate,
  addLibraryImage,
  removeLibraryImage,
  updateAdminSettings,
  updatePageSeo,
  getDnsInstructions,
  getRobotsTxt,
  previewWebsite,
  getWebsiteAnalytics,
  getMyPersonalSite,
  createPersonalSite,
  checkPersonalSiteSlug,
  updatePersonalSite,
  setPersonalSiteStatus,
  getPersonalSiteAnalytics,
  listChatInbox,
  listChatMessages,
  sendChatReply,
  claimChatSession,
  closeChatSession,
  promoteChatSession,
  listUnifiedChatInbox,
  generateAiChatReply,
  getSitemapXml,
  getSeoHealth,
  getStructuredData,
  generatePageSeoCopy,
  setPageLayoutMode,
  listPersonalizationVariants,
  addPersonalizationVariant,
  removePersonalizationVariant,
  type Website,
  type SectionTemplate,
  type SiteTemplate,
  type WebsiteSection,
  type WebsiteAnalytics,
  type PersonalSite,
  type ChatSession,
  type ChatMessage,
  type ChatDepartment,
  type SeoHealth,
  type PersonalizationVariant,
} from "@/lib/websites";
import { getSession } from "@/lib/auth";
import { VISUALIZATION_DRAG_TYPE, type VisualizationDropPayload } from "@/lib/useVisualizationWorkspace";
import { SitePageRenderer } from "@/components/SiteSectionRenderer";
import { WebsiteCanvasEditor } from "@/components/WebsiteCanvasEditor";
import { WebsiteDesignPicker } from "@/components/WebsiteDesignPicker";
import { WebsiteDealerAssistant } from "./WebsiteDealerAssistant";
import { WebsiteDomainSetup } from "./WebsiteDomainSetup";
import { WebsiteTraffic } from "./WebsiteTraffic";
import websiteNav from "./WebsiteBoardNav.module.css";
import { LoneStarCustomizer } from "@/components/LoneStarCustomizer";
import { WebsiteStudioEditor } from "@/components/WebsiteStudioEditor";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";

type Theme = "dark" | "light";
type Section = "sites" | "builder" | "seo" | "analytics" | "chat" | "personal" | "approvals";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

// Same brand-ribbon order as components/DepartmentWorkflowButtons.tsx's RIBBON_COLORS.
const KPI_RIBBON = PRODUCT_ACCENT_COLORS;

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-zinc-800 text-zinc-400",
  pending_approval: "bg-amber-950 text-amber-300",
  published: "bg-green-900 text-green-300",
  rejected: "bg-red-950 text-red-300",
  open: "bg-blue-900 text-blue-300",
  claimed: "bg-amber-950 text-amber-300",
  closed: "bg-zinc-800 text-zinc-500",
  active: "bg-green-900 text-green-300",
  inactive: "bg-zinc-800 text-zinc-500",
};

function Badge({ theme, label }: { theme: Theme; label: string }) {
  const cls = STATUS_COLORS[label] || "bg-zinc-800 text-zinc-400";
  return <span className={`text-xs px-2 py-0.5 rounded uppercase tracking-wide ${cls}`}>{label.replace(/_/g, " ")}</span>;
}

function Btn({
  theme,
  onClick,
  children,
  kind = "default",
  disabled,
  small,
}: {
  theme: Theme;
  onClick?: () => void;
  children: React.ReactNode;
  kind?: "default" | "primary" | "danger";
  disabled?: boolean;
  small?: boolean;
}) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      variant={kind === "default" ? "secondary" : kind}
    >
      {children}
    </WorkButton>
  );
}

function Input({
  theme,
  value,
  onChange,
  placeholder,
  textarea,
}: {
  theme: Theme;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  textarea?: boolean;
}) {
  const cls = tc(
    theme,
    "bg-zinc-900 border border-zinc-700 text-white placeholder-zinc-600",
    "bg-white border border-zinc-300 text-black placeholder-zinc-400"
  );
  if (textarea) {
    return (
      <WorkField label={placeholder || "Value"}><WorkTextarea
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        rows={3}
        className={`w-full text-xs rounded px-2 py-1.5 ${cls}`}
      /></WorkField>
    );
  }
  return (
    <WorkField label={placeholder || "Value"}><WorkInput
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className={`w-full text-xs rounded px-2 py-1.5 ${cls}`}
    /></WorkField>
  );
}

function DragHandle({ theme, itemKey, fieldPath, sourceLabel, rows, numericColumns, labelColumn }: {
  theme: Theme; itemKey: string; fieldPath: string[]; sourceLabel: string;
  rows: Record<string, unknown>[]; numericColumns: string[]; labelColumn: string;
}) {
  if (rows.length === 0 || numericColumns.length === 0) return null;
  function handleDragStart(event: DragEvent<HTMLButtonElement>) {
    const payload: VisualizationDropPayload = { department: "Marketing", itemKey, fieldPath, sourceLabel, rows, numericColumns, labelColumn };
    event.dataTransfer.setData(VISUALIZATION_DRAG_TYPE, JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "copy";
  }
  return (
    <WorkButton type="submit"
      draggable
      onDragStart={handleDragStart}
      title="Drag into the Workspace to build a chart, then pin it"
      className={tc(theme, "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-700 text-zinc-500 hover:text-white hover:border-zinc-500 transition cursor-grab", "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-400 text-zinc-600 hover:text-black hover:border-zinc-600 transition cursor-grab")}
    >
      ⠿ Drag to Workspace
    </WorkButton>
  );
}

// --- Sites tab -----------------------------------------------------------------------

function SitesTab({
  theme, sites, onRefresh, onSelect, onEditWebsite, siteTemplates,
}: {
  theme: Theme; sites: Website[]; onRefresh: () => void; onSelect: (id: string) => void; onEditWebsite: (id: string) => void; siteTemplates: SiteTemplate[];
}) {
  const [name, setName] = useState("");
  const [designId, setDesignId] = useState("lone-star");
  const creationRequest = useRef<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleCreate() {
    setBusy(true);
    setError(null);
    try {
      if (!name.trim()) throw new Error("A site name is required");
      creationRequest.current ||= crypto.randomUUID();
      const site = await createStudioWebsite(name.trim(), designId, creationRequest.current, "traditional");
      creationRequest.current = null;
      onRefresh();
      onEditWebsite(site.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create site");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      <div className={tc(theme, "border border-zinc-800 rounded-lg p-4 space-y-3", "border border-zinc-200 rounded-lg p-4 space-y-3")}>
        <div className="text-sm font-semibold">Start a new site</div>
        <Input theme={theme} value={name} onChange={setName} placeholder="Site name (e.g. Sam's Motors)" />
        <WebsiteDesignPicker value={designId} disabled={busy} onSelect={setDesignId} />

        {error && <div className="text-xs text-red-400">{error}</div>}
        <Btn theme={theme} kind="primary" onClick={handleCreate} disabled={busy}>{busy ? "Creating…" : "Create Site"}</Btn>
      </div>

      <div>
        <div className="text-sm font-semibold mb-2">My Sites ({sites.length})</div>
        <div className="space-y-2">
          {sites.map((s) => {
            const liveUrl = typeof window !== "undefined" ? `${window.location.origin}/site/${s.id}` : `/site/${s.id}`;
            return (
              <div
                key={s.id}
                className={tc(theme, "flex items-center justify-between gap-3 px-4 py-3 rounded-lg border border-zinc-800 bg-brand-charcoal", "flex items-center justify-between gap-3 px-4 py-3 rounded-lg border border-zinc-200 bg-white")}
              >
                <div className="min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-semibold truncate">{s.name}</span>
                    <Badge theme={theme} label={s.status} />
                  </div>
                  <div className="text-xs text-zinc-500 mt-0.5 flex items-center gap-3">

                    {s.status === "published" && (
                      <a href={liveUrl} target="_blank" rel="noreferrer" className="text-brand-teal hover:underline">
                        View live site ↗
                      </a>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  <WorkButton type="submit"
                    onClick={() => onSelect(s.id)}
                    className={tc(theme, "text-xs px-3 py-1.5 rounded border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 transition", "text-xs px-3 py-1.5 rounded border border-zinc-300 text-zinc-600 hover:text-black transition")}
                  >
                    Details
                  </WorkButton>
                  <WorkButton type="submit"
                    onClick={() => onEditWebsite(s.id)}
                    className="text-xs px-3 py-1.5 rounded bg-brand-teal text-black font-semibold hover:brightness-110 transition"
                  >
                    ✎ Edit Website
                  </WorkButton>
                </div>
              </div>
            );
          })}
          {sites.length === 0 && <div className="text-xs text-zinc-500">No sites yet -- create one above.</div>}
        </div>
      </div>
    </div>
  );
}

// --- Builder tab: pages, drag-drop sections, image library, mode/preview -------------

function SectionCard({
  theme, website, pageKey, index, section, template, onChanged,
}: {
  theme: Theme; website: Website; pageKey: string; index: number; section: WebsiteSection;
  template?: SectionTemplate; onChanged: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [fields, setFields] = useState<Record<string, string>>(
    Object.fromEntries(Object.entries(section.fields || {}).map(([k, v]) => [k, String(v ?? "")]))
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const canEdit = website.status === "draft" || website.status === "rejected";
  const writableFields = (template?.fields || []).filter((f) => f.ai_writable);

  // Website Personalization (2026-07-19) -- a real utm_source/referrer-matched
  // per-section overlay, distinct from the section's own base fields above.
  const [personalizing, setPersonalizing] = useState(false);
  const [variants, setVariants] = useState<PersonalizationVariant[] | null>(null);
  const [variantsBusy, setVariantsBusy] = useState(false);
  const [variantsError, setVariantsError] = useState<string | null>(null);
  const [newUtmSource, setNewUtmSource] = useState("");
  const [newReferrerContains, setNewReferrerContains] = useState("");
  const [newOverrides, setNewOverrides] = useState<Record<string, string>>({});

  async function loadVariants() {
    setVariantsBusy(true);
    setVariantsError(null);
    try {
      const res = await listPersonalizationVariants(website.id, pageKey, index);
      setVariants(res.variants || []);
    } catch (e) {
      setVariantsError(e instanceof Error ? e.message : "Failed to load variants");
    } finally {
      setVariantsBusy(false);
    }
  }

  function togglePersonalize() {
    const next = !personalizing;
    setPersonalizing(next);
    if (next && variants === null) loadVariants();
  }

  async function addVariant() {
    const overrides = Object.fromEntries(Object.entries(newOverrides).filter(([, v]) => v.trim() !== ""));
    setVariantsBusy(true);
    setVariantsError(null);
    try {
      const result = await addPersonalizationVariant(
        website.id, pageKey, index,
        { utm_source: newUtmSource.trim() || undefined, referrer_contains: newReferrerContains.trim() || undefined },
        overrides
      );
      if (result.error) {
        setVariantsError(result.error);
      } else {
        setNewUtmSource("");
        setNewReferrerContains("");
        setNewOverrides({});
        await loadVariants();
        onChanged();
      }
    } catch (e) {
      setVariantsError(e instanceof Error ? e.message : "Failed to add variant");
    } finally {
      setVariantsBusy(false);
    }
  }

  async function removeVariant(variantId: string) {
    setVariantsBusy(true);
    setVariantsError(null);
    try {
      await removePersonalizationVariant(website.id, pageKey, index, variantId);
      await loadVariants();
      onChanged();
    } catch (e) {
      setVariantsError(e instanceof Error ? e.message : "Failed to remove variant");
    } finally {
      setVariantsBusy(false);
    }
  }

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await updateSectionFields(website.id, pageKey, index, fields);
      onChanged();
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to save");
    } finally {
      setBusy(false);
    }
  }

  async function regen() {
    setBusy(true);
    setError(null);
    try {
      const result = await regenerateSection(website.id, pageKey, index);
      if (result.error) setError(result.error);
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "AI regeneration failed");
    } finally {
      setBusy(false);
    }
  }

  async function toggleLock() {
    setBusy(true);
    try {
      await setSectionLocked(website.id, pageKey, index, !section.locked);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function remove() {
    setBusy(true);
    try {
      await removeSection(website.id, pageKey, index);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <div
      draggable={canEdit}
      onDragStart={(e) => e.dataTransfer.setData("text/website-section-index", String(index))}
      onDragOver={(e) => canEdit && e.preventDefault()}
      onDrop={(e) => {
        if (!canEdit) return;
        e.preventDefault();
        const from = Number(e.dataTransfer.getData("text/website-section-index"));
        if (Number.isNaN(from) || from === index) return;
        const order = website.pages[pageKey].sections.map((_, i) => i);
        order.splice(order.indexOf(from), 1);
        order.splice(order.indexOf(index) >= 0 ? order.indexOf(index) : index, 0, from);
        reorderSections(website.id, pageKey, order).then(onChanged);
      }}
      className={tc(theme, `border rounded-lg p-3 space-y-2 ${canEdit ? "cursor-move" : ""} border-zinc-800 bg-brand-charcoal`, `border rounded-lg p-3 space-y-2 ${canEdit ? "cursor-move" : ""} border-zinc-200 bg-white`)}
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-zinc-500 text-xs">⠿</span>
          <span className="text-sm font-semibold">{template?.name || section.section_key}</span>
          {section.locked && <span className="text-xs px-1.5 py-0.5 rounded bg-amber-950 text-amber-300">🔒 locked</span>}
        </div>
        {canEdit && (
          <div className="flex gap-1.5">
            {writableFields.length > 0 && <Btn theme={theme} small onClick={regen} disabled={busy || section.locked}>✨ AI Rewrite</Btn>}
            <Btn theme={theme} small onClick={() => setEditing((v) => !v)} disabled={section.locked}>{editing ? "Close" : "Edit"}</Btn>
            <Btn theme={theme} small onClick={togglePersonalize} disabled={section.locked}>
              {personalizing ? "Close" : "🎯 Personalize"}
              {(section.personalization_variants?.length ?? 0) > 0 && ` (${section.personalization_variants?.length})`}
            </Btn>
            <Btn theme={theme} small onClick={toggleLock}>{section.locked ? "Unlock" : "Lock"}</Btn>
            <Btn theme={theme} small kind="danger" onClick={remove} disabled={section.locked || busy}>Remove</Btn>
          </div>
        )}
      </div>

      {editing && template && (
        <div className="space-y-2 pt-2 border-t border-zinc-800">
          {template.fields.map((f) => (
            <div key={f.key}>
              <div className="text-xs text-zinc-500 mb-0.5">{f.label} {f.ai_writable && <span className="text-brand-teal">· AI-writable</span>}</div>
              <Input theme={theme} value={fields[f.key] ?? ""} onChange={(v) => setFields((s) => ({ ...s, [f.key]: v }))} textarea={f.type === "textarea"} />
            </div>
          ))}
          {error && <div className="text-xs text-red-400">{error}</div>}
          <Btn theme={theme} kind="primary" small onClick={save} disabled={busy}>Save</Btn>
        </div>
      )}

      {personalizing && (
        <div className="space-y-3 pt-2 border-t border-zinc-800">
          <div className="text-xs text-zinc-500">
            Shown to a real visitor whenever their ?utm_source= or the page they came
            from (Referer) matches -- otherwise the section's base fields render as-is.
          </div>
          {variantsError && <div className="text-xs text-red-400">{variantsError}</div>}
          {variantsBusy && variants === null ? (
            <div className="text-xs text-zinc-500">Loading…</div>
          ) : (
            <div className="space-y-1.5">
              {(variants ?? section.personalization_variants ?? []).map((v) => (
                <div key={v.id} className={tc(theme, "flex items-center justify-between gap-2 text-xs bg-zinc-900 border border-zinc-800 rounded px-2 py-1.5", "flex items-center justify-between gap-2 text-xs bg-zinc-50 border border-zinc-200 rounded px-2 py-1.5")}>
                  <div className="truncate">
                    <span className="text-zinc-500">match:</span>{" "}
                    {v.match.utm_source && <span className="text-brand-teal">utm_source={v.match.utm_source} </span>}
                    {v.match.referrer_contains && <span className="text-brand-teal">referrer~{v.match.referrer_contains}</span>}
                    <span className="text-zinc-600"> · {Object.keys(v.field_overrides).length} field override(s)</span>
                  </div>
                  <WorkButton type="submit" variant="danger"
                    onClick={() => removeVariant(v.id)}
                    disabled={variantsBusy}
                    className="text-red-400 hover:text-red-300 text-xs shrink-0"
                  >
                    remove
                  </WorkButton>
                </div>
              ))}
              {(variants ?? []).length === 0 && !variantsBusy && (
                <div className="text-xs text-zinc-600">No personalization variants yet.</div>
              )}
            </div>
          )}

          <div className="space-y-1.5 pt-1">
            <div className="text-xs text-zinc-500">+ New variant</div>
            <div className="grid grid-cols-2 gap-1.5">
              <Input theme={theme} value={newUtmSource} onChange={setNewUtmSource} placeholder="utm_source (e.g. facebook_ad)" />
              <Input theme={theme} value={newReferrerContains} onChange={setNewReferrerContains} placeholder="referrer contains (e.g. google.com)" />
            </div>
            {(template?.fields || []).map((f) => (
              <div key={f.key}>
                <div className="text-xs text-zinc-500 mb-0.5">Override {f.label}</div>
                <Input
                  theme={theme}
                  value={newOverrides[f.key] ?? ""}
                  onChange={(v) => setNewOverrides((s) => ({ ...s, [f.key]: v }))}
                  textarea={f.type === "textarea"}
                />
              </div>
            ))}
            <Btn theme={theme} kind="primary" small onClick={addVariant} disabled={variantsBusy}>+ Add Variant</Btn>
          </div>
        </div>
      )}

      {!editing && !personalizing && (
        <div className="text-xs text-zinc-500 space-y-0.5">
          {Object.entries(section.fields || {}).slice(0, 3).map(([k, v]) => (
            <div key={k} className="truncate">
              <span className="text-zinc-600">{k}:</span> {String(v ?? "").slice(0, 80) || "—"}
            </div>
          ))}
          {section.live_vehicles && <div className="text-xs text-brand-teal">{section.live_vehicles.length} live vehicles</div>}
          {section.live_options && <div className="text-xs text-brand-teal">{section.live_options.length} makes in DealerGPT builder</div>}
        </div>
      )}
    </div>
  );
}

function BuilderTab({
  theme, website, onChanged, sectionTemplates, pageKeys, fullScreen, onToggleFullScreen,
}: {
  theme: Theme; website: Website; onChanged: () => void; sectionTemplates: SectionTemplate[]; pageKeys: { key: string; label: string }[];
  fullScreen?: boolean; onToggleFullScreen?: () => void;
}) {
  const [activePage, setActivePage] = useState(pageKeys[0]?.key || "home");
  const [addingKey, setAddingKey] = useState("");
  const [previewMode, setPreviewMode] = useState<string>(website.mode);
  const [preview, setPreview] = useState<Website | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const [imgUrl, setImgUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const canEdit = website.status === "draft" || website.status === "rejected";
  const templateByKey = useMemo(() => Object.fromEntries(sectionTemplates.map((t) => [t.key, t])), [sectionTemplates]);
  const page = website.pages[activePage] || { sections: [] };

  // Freeform drag-and-drop canvas (2026-07-18) -- Sam: "have a button that says edit
  // website where you can open it up fully into a wix drag and drop, fully editable
  // website builder." The real, deferred version of the Full Screen overlay's own
  // "much larger build" note. A per-page view toggle, defaulting to whatever the
  // page's own real stored layout_mode already is -- switching TO canvas for the
  // first time calls the real backend auto-backfill (setPageLayoutMode) so existing
  // sections land exactly where they already appeared in structured mode.
  const [viewMode, setViewMode] = useState<"structured" | "canvas">(page.layout_mode || "structured");
  const [canvasSwitchBusy, setCanvasSwitchBusy] = useState(false);

  useEffect(() => {
    setViewMode(website.pages[activePage]?.layout_mode || "structured");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activePage]);

  async function switchViewMode(next: "structured" | "canvas") {
    const stored = website.pages[activePage]?.layout_mode || "structured";
    setViewMode(next);
    if (next === stored) return;
    setCanvasSwitchBusy(true);
    try {
      await setPageLayoutMode(website.id, activePage, next);
      onChanged();
    } finally {
      setCanvasSwitchBusy(false);
    }
  }

  // Real, VISUAL live preview -- re-fetches automatically whenever the active page,
  // the mode being previewed, or the site's own content changes, and renders through
  // components/SiteSectionRenderer.tsx (the same renderer the real public
  // app/site/[id]/page.tsx uses) instead of the old raw section-key bullet list. This
  // is what makes "what does this actually look like" answerable without leaving the
  // Dash, and what the full-screen Edit Website view below is built around.
  useEffect(() => {
    let cancelled = false;
    setPreviewBusy(true);
    previewWebsite(website.id, previewMode)
      .then((w) => { if (!cancelled) setPreview(w); })
      .catch(() => { if (!cancelled) setPreview(null); })
      .finally(() => { if (!cancelled) setPreviewBusy(false); });
    return () => { cancelled = true; };
  }, [website, previewMode]);

  async function handleAddSection() {
    if (!addingKey) return;
    const template = templateByKey[addingKey];
    const fields: Record<string, unknown> = {};
    (template?.fields || []).forEach((f) => { if (f.default !== undefined) fields[f.key] = f.default; });
    setBusy(true);
    try {
      await addSection(website.id, activePage, addingKey, fields);
      onChanged();
      setAddingKey("");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddImage() {
    if (!imgUrl.trim()) return;
    setBusy(true);
    try {
      await addLibraryImage(website.id, imgUrl.trim());
      setImgUrl("");
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  async function handleSubmit() {
    setBusy(true);
    try {
      await submitWebsite(website.id);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  const previewPage = preview?.pages?.[activePage]?.sections ?? page.sections;
  const liveUrl = typeof window !== "undefined" ? `${window.location.origin}/site/${website.id}` : `/site/${website.id}`;

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className={tc(theme, "flex items-center justify-between gap-2 px-4 py-2 border-b border-zinc-800 shrink-0", "flex items-center justify-between gap-2 px-4 py-2 border-b border-zinc-200 shrink-0")}>
        <div className="text-sm font-semibold truncate">✎ Editing: {website.name}</div>
        <div className="flex items-center gap-2 shrink-0">
          {/* Freeform drag-and-drop canvas (2026-07-18) -- Sam's "wix drag and drop"
              ask. Structured = today's stacked-flow field editor + live preview,
              unchanged. Canvas = every section gets a real, draggable/resizable x/y
              position on a true freeform Wix-style canvas instead. */}
          <div className={tc(theme, "flex rounded-md border border-zinc-700 overflow-hidden", "flex rounded-md border border-zinc-300 overflow-hidden")}>
            {(["structured", "canvas"] as const).map((m) => (
              <WorkButton type="submit"
                key={m}
                onClick={() => switchViewMode(m)}
                disabled={canvasSwitchBusy}
                className={`text-xs px-2.5 py-1 disabled:opacity-50 ${viewMode === m ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-400 hover:text-white", "bg-white text-zinc-600 hover:text-black")}`}
              >
                {m === "structured" ? "☰ Structured" : "⛶ Canvas"}
              </WorkButton>
            ))}
          </div>
          <a href={liveUrl} target="_blank" rel="noreferrer" className="text-xs text-brand-teal hover:underline">
            Open live site ↗
          </a>
          {onToggleFullScreen && (
            <WorkButton type="submit"
              onClick={onToggleFullScreen}
              className={tc(theme, "text-xs px-3 py-1.5 rounded border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 transition", "text-xs px-3 py-1.5 rounded border border-zinc-300 text-zinc-700 hover:text-black hover:border-zinc-500 transition")}
            >
              {fullScreen ? "⤡ Exit Full Screen" : "⤢ Full Screen"}
            </WorkButton>
          )}
        </div>
      </div>

      <div className="px-4 pt-4">
        <div className="flex items-center gap-2 flex-wrap">
          {pageKeys.map((p) => (
            <WorkButton aria-pressed={activePage === p.key} type="submit"
              key={p.key}
              onClick={() => setActivePage(p.key)}
              className={`text-xs px-3 py-1.5 rounded ${activePage === p.key ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-400 border border-zinc-700 hover:text-white", "bg-zinc-100 text-zinc-600 border border-zinc-300 hover:text-black")}`}
            >
              {p.label} <span className="text-xs opacity-60">({(website.pages[p.key]?.sections || []).length})</span>
              {website.pages[p.key]?.layout_mode === "canvas" && <span className="ml-1 text-xs text-brand-teal">⛶</span>}
            </WorkButton>
          ))}
        </div>
      </div>

      {viewMode === "canvas" ? (
        <WebsiteCanvasEditor
          theme={theme}
          website={website}
          pageKey={activePage}
          sectionTemplates={sectionTemplates}
          canEdit={canEdit}
          onChanged={onChanged}
        />
      ) : (
      <div className="flex-1 flex min-h-0">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {canEdit && (
          <div className="flex items-center gap-2">
            <WorkField label="Section to add"><WorkSelect
              value={addingKey}
              onChange={(e) => setAddingKey(e.target.value)}
              className={tc(theme, "text-xs bg-zinc-900 border border-zinc-700 text-white rounded px-2 py-1.5", "text-xs bg-white border border-zinc-300 text-black rounded px-2 py-1.5")}
            >
              <option value="">+ Add section…</option>
              {sectionTemplates.map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
            </WorkSelect></WorkField>
            <Btn theme={theme} onClick={handleAddSection} disabled={!addingKey || busy}>Add to {pageKeys.find((p) => p.key === activePage)?.label}</Btn>
          </div>
        )}

        <div className="space-y-2">
          {page.sections.map((s, i) => (
            <SectionCard key={i} theme={theme} website={website} pageKey={activePage} index={i} section={s} template={templateByKey[s.section_key]} onChanged={onChanged} />
          ))}
          {page.sections.length === 0 && <div className="text-xs text-zinc-500">No sections on this page yet.</div>}
        </div>

        <div className={tc(theme, "border border-zinc-800 rounded-lg p-3 space-y-2", "border border-zinc-200 rounded-lg p-3 space-y-2")}>
          <div className="text-sm font-semibold">Image Library</div>
          <div className="flex gap-2">
            <Input theme={theme} value={imgUrl} onChange={setImgUrl} placeholder="Image URL" />
            <Btn theme={theme} onClick={handleAddImage} disabled={busy}>Add</Btn>
          </div>
          <div className="flex flex-wrap gap-2">
            {website.image_library.map((img) => (
              <div key={img.id} className="relative group">
                <img src={img.url} alt={img.label || ""} className="w-16 h-16 object-cover rounded border border-zinc-700" onError={(e) => ((e.target as HTMLImageElement).style.display = "none")} />
                <WorkButton type="submit" variant="danger"
                  onClick={() => removeLibraryImage(website.id, img.id).then(onChanged)}
                  className="absolute -top-1 -right-1 bg-red-900 text-white text-xs rounded-full w-4 h-4 opacity-0 group-hover:opacity-100"
                >×</WorkButton>
              </div>
            ))}
            {website.image_library.length === 0 && <div className="text-xs text-zinc-500">No images yet -- paste a URL above.</div>}
          </div>
        </div>

        {canEdit && (
          <Btn theme={theme} kind="primary" onClick={handleSubmit} disabled={busy}>Submit for Approval</Btn>
        )}
      </div>

      <div className={tc(theme, "w-[420px] shrink-0 border-l border-zinc-800 flex flex-col", "w-[420px] shrink-0 border-l border-zinc-200 flex flex-col")}>
        <div className={tc(theme, "p-3 space-y-2 border-b border-zinc-800", "p-3 space-y-2 border-b border-zinc-200")}>
          <div className="text-sm font-semibold">Live Preview</div>
          <div className="text-xs text-zinc-500">
            This is the actual rendered page a visitor sees -- not a field list. Every site
            has both views built in; toggle below to check either one.
          </div>
          <div className="flex gap-2">
            {(["traditional", "dealer_gpt"] as const).map((m) => (
              <WorkButton type="submit"
                key={m}
                onClick={() => setPreviewMode(m)}
                className={`text-xs px-2 py-1 rounded flex-1 ${previewMode === m ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-500 border border-zinc-700 hover:text-white", "bg-zinc-100 text-zinc-500 border border-zinc-300 hover:text-black")}`}
              >
                {m === "traditional" ? "Traditional" : "DriveFinder"}
              </WorkButton>
            ))}
          </div>
        </div>

        <div className="flex-1 overflow-y-auto bg-zinc-950 flex justify-center py-4">
          <div
            className="bg-white shadow-xl origin-top"
            style={{ width: 1100, transform: "scale(0.34)" }}
          >
            {previewBusy && !preview ? (
              <div className="p-10 text-center text-xs text-zinc-400">Loading preview…</div>
            ) : previewPage.length === 0 ? (
              <div className="p-10 text-center text-xs text-zinc-400">Nothing on this page yet.</div>
            ) : (
              <SitePageRenderer sections={previewPage} />
            )}
          </div>
        </div>
      </div>
      </div>
      )}
    </div>
  );
}

// --- SEO & Admin tab -------------------------------------------------------------------

function SeoAdminTab({ theme, website, onChanged, pageKeys }: { theme: Theme; website: Website; onChanged: () => void; pageKeys: { key: string; label: string }[] }) {
  const [activePage, setActivePage] = useState(pageKeys[0]?.key || "home");
  const [seo, setSeo] = useState(website.admin_settings.page_seo[activePage] || { meta_title: "", meta_description: "", og_image_url: "" });
  const [admin, setAdmin] = useState(website.admin_settings);
  const [dns, setDns] = useState<Record<string, unknown> | null>(null);
  const [robots, setRobots] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [aiBusy, setAiBusy] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);
  const [health, setHealth] = useState<SeoHealth | null>(null);
  const [healthLoading, setHealthLoading] = useState(true);
  const [sitemap, setSitemap] = useState<string | null>(null);
  const [structuredData, setStructuredData] = useState<Record<string, unknown> | null>(null);

  useEffect(() => {
    setSeo(website.admin_settings.page_seo[activePage] || { meta_title: "", meta_description: "", og_image_url: "" });
    setAiNote(null);
  }, [activePage, website]);

  function refreshHealth() {
    setHealthLoading(true);
    getSeoHealth(website.id).then(setHealth).finally(() => setHealthLoading(false));
  }

  useEffect(() => {
    refreshHealth();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [website.id]);

  async function saveSeo() {
    setBusy(true);
    try {
      await updatePageSeo(website.id, activePage, seo);
      onChanged();
      refreshHealth();
    } finally {
      setBusy(false);
    }
  }

  async function saveAdmin() {
    setBusy(true);
    try {
      await updateAdminSettings(website.id, admin);
      onChanged();
      refreshHealth();
    } finally {
      setBusy(false);
    }
  }

  // AI meta-copy generation (session 113 follow-up) -- grounded in the page's own
  // real content, a draft the dealer reviews/edits before Save, never auto-applied.
  async function handleAiGenerate() {
    setAiBusy(true);
    setAiNote(null);
    try {
      const result = await generatePageSeoCopy(website.id, activePage);
      setSeo((s) => ({ ...s, meta_title: result.meta_title, meta_description: result.meta_description }));
      setAiNote(result.ai_generated ? "✨ AI-drafted -- review, then Save." : "Drafted from a template (AI unavailable) -- review, then Save.");
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setAiBusy(false);
    }
  }

  const pageHealth = health?.pages.find((p) => p.page_key === activePage);
  const scoreColor = (pct: number) => (pct >= 75 ? "text-green-400" : pct >= 50 ? "text-amber-400" : "text-red-400");

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-6">
      <div className={tc(theme, "border border-zinc-800 rounded-lg p-4 space-y-3", "border border-zinc-200 rounded-lg p-4 space-y-3")}>
        <div className="flex items-center justify-between">
          <div className="text-sm font-semibold">SEO Health Score</div>
          <div className="flex items-center gap-2">
            {!healthLoading && health && (
              <span className={`text-lg font-semibold ${scoreColor(health.overall_score_pct)}`}>{health.overall_score_pct}%</span>
            )}
            <Btn theme={theme} small onClick={refreshHealth} disabled={healthLoading}>{healthLoading ? "…" : "Refresh"}</Btn>
          </div>
        </div>
        {health && (
          <div className="space-y-1.5">
            {health.site_checks.map((c) => (
              <div key={c.check} className="flex items-start gap-1.5 text-xs">
                <span className={c.pass ? "text-green-400" : "text-amber-400"}>{c.pass ? "✓" : "!"}</span>
                <span className="text-zinc-400">{c.detail}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div className={tc(theme, "border border-zinc-800 rounded-lg p-4 space-y-3", "border border-zinc-200 rounded-lg p-4 space-y-3")}>
        <div className="text-sm font-semibold">Per-Page SEO</div>
        <div className="flex gap-1.5 flex-wrap">
          {pageKeys.map((p) => {
            const ph = health?.pages.find((h) => h.page_key === p.key);
            return (
              <WorkButton aria-pressed={activePage === p.key} type="submit" key={p.key} onClick={() => setActivePage(p.key)} className={`text-xs px-2 py-1 rounded flex items-center gap-1 ${activePage === p.key ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-500 border border-zinc-700 hover:text-white", "bg-zinc-100 text-zinc-500 border border-zinc-300 hover:text-black")}`}>
                {p.label}
                {ph && <span className={activePage === p.key ? "text-zinc-600" : scoreColor(ph.score_pct)}>{Math.round(ph.score_pct)}%</span>}
              </WorkButton>
            );
          })}
        </div>
        {pageHealth && (
          <div className="space-y-1">
            {pageHealth.checks.map((c) => (
              <div key={c.check} className="flex items-start gap-1.5 text-xs">
                <span className={c.pass ? "text-green-400" : "text-amber-400"}>{c.pass ? "✓" : "!"}</span>
                <span className="text-zinc-500">{c.detail}</span>
              </div>
            ))}
          </div>
        )}
        <div className="flex items-center gap-2">
          <Input theme={theme} value={seo.meta_title || ""} onChange={(v) => setSeo((s) => ({ ...s, meta_title: v }))} placeholder="Meta title" />
          <Btn theme={theme} small onClick={handleAiGenerate} disabled={aiBusy}>{aiBusy ? "…" : "✨ AI Generate"}</Btn>
        </div>
        <Input theme={theme} value={seo.meta_description || ""} onChange={(v) => setSeo((s) => ({ ...s, meta_description: v }))} placeholder="Meta description" textarea />
        <Input theme={theme} value={seo.og_image_url || ""} onChange={(v) => setSeo((s) => ({ ...s, og_image_url: v }))} placeholder="Social preview image URL" />
        {aiNote && <div className="text-xs text-brand-teal">{aiNote}</div>}
        <Btn theme={theme} kind="primary" onClick={saveSeo} disabled={busy}>Save SEO for {pageKeys.find((p) => p.key === activePage)?.label}</Btn>
      </div>

      <div className={tc(theme, "border border-zinc-800 rounded-lg p-4 space-y-3", "border border-zinc-200 rounded-lg p-4 space-y-3")}>
        <div className="text-sm font-semibold">Admin Settings</div>
        <p className="text-xs">Manage your website address in Domain &amp; publish.</p>
        <Input theme={theme} value={admin.google_analytics_id || ""} onChange={(v) => setAdmin((s) => ({ ...s, google_analytics_id: v }))} placeholder="Google Analytics ID" />
        <Input theme={theme} value={admin.umami_site_id || ""} onChange={(v) => setAdmin((s) => ({ ...s, umami_site_id: v }))} placeholder="Umami site ID" />
        <Input theme={theme} value={admin.facebook_pixel_id || ""} onChange={(v) => setAdmin((s) => ({ ...s, facebook_pixel_id: v }))} placeholder="Facebook Pixel ID" />
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          <WorkInput type="checkbox" checked={admin.block_ai_crawlers} onChange={(e) => setAdmin((s) => ({ ...s, block_ai_crawlers: e.target.checked }))} />
          Block AI crawlers (GPTBot, CCBot, ClaudeBot, …)
        </label>
        <label className="flex items-center gap-2 text-xs text-zinc-400">
          <WorkInput type="checkbox" checked={!!admin.ai_receptionist_enabled} onChange={(e) => setAdmin((s) => ({ ...s, ai_receptionist_enabled: e.target.checked }))} />
          AI Receptionist — auto-reply to new visitors until a team member joins the chat
        </label>
        <div className="flex items-center gap-2">
          <span className="text-xs text-zinc-500">Branding</span>
          {(["independent", "oem"] as const).map((m) => (
            <WorkButton type="submit" key={m} onClick={() => setAdmin((s) => ({ ...s, branding_mode: m }))} className={`text-xs px-2 py-1 rounded ${admin.branding_mode === m ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-500 border border-zinc-700 hover:text-white", "bg-zinc-100 text-zinc-500 border border-zinc-300 hover:text-black")}`}>{m}</WorkButton>
          ))}
        </div>
        <Btn theme={theme} kind="primary" onClick={saveAdmin} disabled={busy}>Save Admin Settings</Btn>
      </div>

      <div className={tc(theme, "border border-zinc-800 rounded-lg p-4 space-y-2", "border border-zinc-200 rounded-lg p-4 space-y-2")}>
        <div className="text-sm font-semibold">Search engine access</div>
        <div className="flex gap-2 flex-wrap">

          <Btn theme={theme} small onClick={() => getRobotsTxt(website.id).then((r) => setRobots(r.robots_txt))}>Preview robots.txt</Btn>
        </div>

        {robots && <pre className="text-xs text-zinc-400 whitespace-pre-wrap">{robots}</pre>}
      </div>

      <div className={tc(theme, "border border-zinc-800 rounded-lg p-4 space-y-2", "border border-zinc-200 rounded-lg p-4 space-y-2")}>
        <div className="text-sm font-semibold">Sitemap & Structured Data</div>
        <div className="text-xs text-zinc-500">
          Real, live-generated -- publicly served (once this site is published) at
          <code className="mx-1 px-1 py-0.5 rounded bg-black/30">/public/websites/{website.id}/sitemap.xml</code>
          and
          <code className="mx-1 px-1 py-0.5 rounded bg-black/30">/robots.txt</code>.
        </div>
        <div className="flex gap-2 flex-wrap">
          <Btn theme={theme} small onClick={() => getSitemapXml(website.id).then((r) => setSitemap(r.sitemap_xml)).catch((e) => alert((e as Error).message))}>Preview sitemap.xml</Btn>
          <Btn theme={theme} small onClick={() => getStructuredData(website.id).then((r) => setStructuredData(r.json_ld))}>Preview Structured Data (JSON-LD)</Btn>
        </div>
        {sitemap && <pre className="text-xs text-zinc-400 whitespace-pre-wrap">{sitemap}</pre>}
        {structuredData && <pre className="text-xs text-zinc-400 whitespace-pre-wrap">{JSON.stringify(structuredData, null, 2)}</pre>}
      </div>
    </div>
  );
}

// --- Analytics & Bot Traffic tab -------------------------------------------------------

// --- Chat tab -------------------------------------------------------------------------

const DEPARTMENT_LABELS: Record<ChatDepartment, string> = {
  sales: "Sales",
  service: "Service",
  finance: "Finance",
  general: "General",
};

function ChatTab({ theme, websiteId }: { theme: Theme; websiteId: string }) {
  // "This Site" keeps the original single-site inbox scope; "All Sites" is the real
  // omnichannel upgrade (session 113 follow-up) -- every chat session across every
  // site this employee manages, in one list.
  const [scope, setScope] = useState<"site" | "all">("site");
  const [deptFilter, setDeptFilter] = useState<ChatDepartment | "">("");
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [reply, setReply] = useState("");
  const [aiBusy, setAiBusy] = useState(false);
  const me = getSession()?.employeeId;

  function refreshSessions() {
    const load = scope === "all" ? listUnifiedChatInbox(undefined, deptFilter || undefined) : listChatInbox(websiteId);
    return load.then(setSessions).catch(() => setSessions([]));
  }

  useEffect(() => {
    refreshSessions();
    const t = setInterval(refreshSessions, 8000);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [websiteId, scope, deptFilter]);

  useEffect(() => {
    if (!selected) return;
    function poll() {
      listChatMessages(selected!).then(setMessages).catch(() => {});
    }
    poll();
    const t = setInterval(poll, 4000);
    return () => clearInterval(t);
  }, [selected]);

  async function handleReply() {
    if (!selected || !reply.trim()) return;
    await sendChatReply(selected, reply.trim());
    setReply("");
    setMessages(await listChatMessages(selected));
  }

  async function handleAiReply() {
    if (!selected) return;
    setAiBusy(true);
    try {
      await generateAiChatReply(selected);
      setMessages(await listChatMessages(selected));
    } finally {
      setAiBusy(false);
    }
  }

  const activeSession = sessions.find((s) => s.id === selected);

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="flex items-center gap-3 px-3 py-2 border-b border-zinc-800 flex-wrap">
        <div className="flex gap-1">
          {(["site", "all"] as const).map((s) => (
            <WorkButton type="submit"
              key={s}
              onClick={() => setScope(s)}
              className={`text-xs px-2 py-1 rounded ${scope === s ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-500 border border-zinc-700 hover:text-white", "bg-zinc-100 text-zinc-500 border border-zinc-300 hover:text-black")}`}
            >
              {s === "site" ? "This Site" : "All Sites"}
            </WorkButton>
          ))}
        </div>
        {scope === "all" && (
          <div className="flex gap-1">
            <WorkButton type="submit" onClick={() => setDeptFilter("")} className={`text-xs px-2 py-1 rounded ${deptFilter === "" ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-500 border border-zinc-700", "bg-zinc-100 text-zinc-500 border border-zinc-300")}`}>All Depts</WorkButton>
            {(Object.keys(DEPARTMENT_LABELS) as ChatDepartment[]).map((d) => (
              <WorkButton type="submit" key={d} onClick={() => setDeptFilter(d)} className={`text-xs px-2 py-1 rounded ${deptFilter === d ? "bg-zinc-200 text-black font-medium" : tc(theme, "bg-zinc-900 text-zinc-500 border border-zinc-700", "bg-zinc-100 text-zinc-500 border border-zinc-300")}`}>{DEPARTMENT_LABELS[d]}</WorkButton>
            ))}
          </div>
        )}
      </div>
      <div className="flex-1 flex min-h-0">
        <div className={tc(theme, "w-64 border-r border-zinc-800 overflow-y-auto", "w-64 border-r border-zinc-200 overflow-y-auto")}>
          {sessions.map((s) => (
            <button key={s.id} onClick={() => setSelected(s.id)} className={`w-full text-left px-3 py-2 border-b border-zinc-900 text-xs ${selected === s.id ? "bg-zinc-900" : ""}`}>
              <div className="flex items-center justify-between">
                <span>{s.visitor_name || "Anonymous visitor"}</span>
                <Badge theme={theme} label={s.status} />
              </div>
              <div className="text-zinc-500 text-xs">{s.visitor_email || "no email"}</div>
              <div className="flex items-center gap-1.5 mt-0.5">
                {s.department && <span className="text-xs uppercase tracking-wide text-brand-teal">{DEPARTMENT_LABELS[s.department]}</span>}
                {scope === "all" && s.website_name && <span className="text-xs text-zinc-600">· {s.website_name}</span>}
              </div>
              {s.lead_id && <div className="text-xs text-brand-teal">→ {s.lead_id}</div>}
            </button>
          ))}
          {sessions.length === 0 && <div className="p-3 text-xs text-zinc-500">No chat sessions yet.</div>}
        </div>
        <div className="flex-1 flex flex-col min-h-0">
          {activeSession ? (
            <>
              <div className="flex items-center justify-between p-3 border-b border-zinc-800">
                <div className="text-sm flex items-center gap-2">
                  {activeSession.visitor_name || "Anonymous visitor"} <Badge theme={theme} label={activeSession.status} />
                  {activeSession.department && <span className="text-xs uppercase tracking-wide text-brand-teal">{DEPARTMENT_LABELS[activeSession.department]}</span>}
                </div>
                <div className="flex gap-1.5">
                  <Btn theme={theme} small onClick={() => claimChatSession(activeSession.id).then(refreshSessions)}>Claim</Btn>
                  <Btn theme={theme} small onClick={() => closeChatSession(activeSession.id).then(refreshSessions)}>Close</Btn>
                  <Btn theme={theme} small onClick={handleAiReply} disabled={aiBusy}>{aiBusy ? "Thinking…" : "✨ AI Reply"}</Btn>
                  {!activeSession.lead_id && (
                    <Btn theme={theme} small kind="primary" onClick={() => promoteChatSession(activeSession.id).then(refreshSessions)}>
                      Promote to Lead
                    </Btn>
                  )}
                </div>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-2">
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`text-xs max-w-[70%] p-2 rounded ${
                      m.sender === "employee" ? "ml-auto bg-brand-teal text-black" : m.sender === "ai" ? "bg-zinc-800 text-zinc-100 border border-brand-teal/50" : "bg-zinc-900 text-white"
                    }`}
                  >
                    {m.sender === "ai" && <div className="text-xs uppercase tracking-wide text-brand-teal mb-0.5">✨ AI Receptionist</div>}
                    {m.body}
                  </div>
                ))}
              </div>
              <div className="p-3 border-t border-zinc-800 flex gap-2">
                <Input theme={theme} value={reply} onChange={setReply} placeholder="Reply…" />
                <Btn theme={theme} kind="primary" onClick={handleReply}>Send</Btn>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center text-xs text-zinc-500">Select a conversation</div>
          )}
        </div>
      </div>
    </div>
  );
}

// --- Personal URL tab ------------------------------------------------------------------

function PersonalTab({ theme, websites }: { theme: Theme; websites: Website[] }) {
  const [site, setSite] = useState<PersonalSite | null>(null);
  const [loading, setLoading] = useState(true);
  const [slug, setSlug] = useState("");
  const [slugStatus, setSlugStatus] = useState<string | null>(null);
  const [analytics, setAnalytics] = useState<{ total_views: number; by_day: Record<string, number> } | null>(null);

  useEffect(() => {
    getMyPersonalSite().then((s) => { setSite(s); setLoading(false); }).catch(() => setLoading(false));
  }, []);

  async function handleCreate() {
    if (!slug.trim()) return;
    const created = await createPersonalSite(slug.trim(), websites[0]?.id);
    setSite(created);
  }

  async function checkSlug() {
    const res = await checkPersonalSiteSlug(slug);
    setSlugStatus(res.available ? "Available" : "Taken");
  }

  async function save(patch: Partial<PersonalSite>) {
    if (!site) return;
    const updated = await updatePersonalSite(site.id, patch);
    setSite(updated);
  }

  async function toggleStatus() {
    if (!site) return;
    const next = site.status === "active" ? "inactive" : "active";
    setSite(await setPersonalSiteStatus(site.id, next));
  }

  if (loading) return <div className="p-4 text-xs text-zinc-500">Loading…</div>;

  if (!site) {
    return (
      <div className="p-4 space-y-3 max-w-md">
        <div className="text-sm font-semibold">Create your personal URL</div>
        <div className="text-xs text-zinc-500">A single personal landing page you can share -- borrows your dealership site's branding live. Contact-form leads captured here assign directly to you.</div>
        <div className="flex gap-2">
          <Input theme={theme} value={slug} onChange={setSlug} placeholder="your-name" />
          <Btn theme={theme} onClick={checkSlug}>Check</Btn>
        </div>
        {slugStatus && <div className="text-xs">{slugStatus}</div>}
        <Btn theme={theme} kind="primary" onClick={handleCreate}>Create Page</Btn>
      </div>
    );
  }

  return (
    <div className="p-4 space-y-4 max-w-md">
      <div className="flex items-center justify-between">
        <div className="text-sm font-semibold">/{site.slug}</div>
        <div className="flex items-center gap-2">
          <Badge theme={theme} label={site.status} />
          <Btn theme={theme} small onClick={toggleStatus}>{site.status === "active" ? "Deactivate" : "Activate"}</Btn>
        </div>
      </div>
      <Input theme={theme} value={site.headline || ""} onChange={(v) => setSite((s) => s && { ...s, headline: v })} placeholder="Headline" />
      <Input theme={theme} value={site.bio || ""} onChange={(v) => setSite((s) => s && { ...s, bio: v })} placeholder="Bio" textarea />
      <Input theme={theme} value={site.photo_url || ""} onChange={(v) => setSite((s) => s && { ...s, photo_url: v })} placeholder="Photo URL" />
      <Input theme={theme} value={site.phone || ""} onChange={(v) => setSite((s) => s && { ...s, phone: v })} placeholder="Phone" />
      <Input theme={theme} value={site.email || ""} onChange={(v) => setSite((s) => s && { ...s, email: v })} placeholder="Email" />
      <Input theme={theme} value={site.cta_text || ""} onChange={(v) => setSite((s) => s && { ...s, cta_text: v })} placeholder="CTA text" />
      <Btn theme={theme} kind="primary" onClick={() => site && save(site)}>Save</Btn>

      <div className="pt-3 border-t border-zinc-800 space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-xs font-semibold">Analytics</div>
          <Btn theme={theme} small onClick={() => getPersonalSiteAnalytics(site.id).then(setAnalytics)}>Refresh</Btn>
        </div>
        {analytics && <div className="text-xs text-zinc-500">{analytics.total_views} total views</div>}
      </div>
    </div>
  );
}

// --- Approvals tab ----------------------------------------------------------------------

function ApprovalsTab({ theme, onDecision }: { theme: Theme; onDecision: (site:Website)=>void }) {
  const [busy, setBusy] = useState(false);
  const [pending, setPending] = useState<Website[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listPendingWebsites().then((r) => Array.isArray(r) ? setPending(r) : setError("You don't have access to the approval queue")).catch((e) => setError(e.message));
  }, []);

  async function refresh() {
    try { setPending(await listPendingWebsites()); } catch { /* keep prior */ }
  }

  async function decide(id:string, approve:boolean) {
    if(busy)return;setBusy(true);setError(null);
    try { const site=await (approve?approveWebsite(id):rejectWebsite(id)); onDecision(site); await refresh(); }
    catch(e){setError(e instanceof Error?e.message:"Unable to complete review. Please try again.");}
    finally{setBusy(false);}
  }

  return (
    <div className="flex-1 overflow-y-auto p-4 space-y-2">
      <h3>Review before publishing</h3><p className="text-xs">Saved changes stay in draft until submitted and approved by an authorized reviewer. Approving a website makes that reviewed version public.</p>
      {error&&<p role="alert">{error}</p>}
      {pending.map((w) => (
        <div key={w.id} className={tc(theme, "border border-zinc-800 rounded-lg p-3 flex items-center justify-between", "border border-zinc-200 rounded-lg p-3 flex items-center justify-between")}>
          <div>
            <div className="text-sm font-semibold">{w.name}</div>
            <div className="text-xs text-zinc-500">requested by {w.requested_by}</div>
          </div>
          <div className="flex gap-2">
            <Btn theme={theme} kind="primary" small disabled={busy} onClick={() => void decide(w.id,true)}>Approve & publish</Btn>
            <Btn theme={theme} kind="danger" small disabled={busy} onClick={() => void decide(w.id,false)}>Reject</Btn>
          </div>
        </div>
      ))}
      {pending.length === 0 && <div className="text-xs text-zinc-500">Nothing pending approval.</div>}
    </div>
  );
}

// --- Main -------------------------------------------------------------------------------

export function WebsiteBuilderBoard({ theme, initialSection = "sites" }: { theme: Theme; initialSection?: Section }) {
  const [section, setSection] = useState<Section>(initialSection);
  useEffect(()=>setSection(initialSection),[initialSection]);
  const [sites, setSites] = useState<Website[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Website | null>(null);
  const [sectionTemplates, setSectionTemplates] = useState<SectionTemplate[]>([]);
  const [siteTemplates, setSiteTemplates] = useState<SiteTemplate[]>([]);
  const [pageKeys, setPageKeys] = useState<{ key: string; label: string }[]>([]);
  // Sam: "have a button that says edit website where you can open it up fully into a
  // wix drag and drop, fully editable website builder." A true pixel-freeform WYSIWYG
  // canvas is a much larger build (scoped explicitly with Sam); this is the agreed
  // near-term version -- a maximized, full-bleed overlay (no KPI strip/tab chrome)
  // around BuilderTab's real visual preview + side-panel editor.
  const [fullScreenBuilder, setFullScreenBuilder] = useState(false);
  const [editorDirty, setEditorDirty] = useState(false);
  const [editorNotice, setEditorNotice] = useState("");

  useEffect(() => {
    listMyWebsites().then(setSites).catch(() => {});
    listSectionTemplates().then(setSectionTemplates).catch(() => {});
    listSiteTemplates().then(setSiteTemplates).catch(() => {});
    listPageKeys().then(setPageKeys).catch(() => {});
  }, []);

  async function refreshSites() {
    listMyWebsites().then(setSites).catch(() => {});
  }

  async function refreshSelected() {
    if (!selectedId) return;
    setSelected(await getWebsite(selectedId));
    refreshSites();
  }

  function handleSelect(id: string) {
    setSelectedId(id);
    setSection("builder");
    getWebsite(id).then(setSelected);
  }

  function handleEditWebsite(id: string) {
    setSelectedId(id);
    setSection("builder");
    getWebsite(id).then(site => { setSelected(site); setFullScreenBuilder(false); });
  }

  useEffect(() => {
    if (selectedId) getWebsite(selectedId).then(setSelected).catch(() => setSelected(null));
  }, [selectedId]);

  const tabs: { key: Section; label: string }[] = [
    { key: "sites", label: "My Sites" },
    { key: "builder", label: "Customize" },
    { key: "seo", label: "SEO & Admin" },
    { key: "analytics", label: "Analytics" },
    { key: "chat", label: "Dealer assistant" },
    { key: "approvals", label: "Domain & publish" },
  ];

  const kpis = useMemo(() => ({
    total: sites.length,
    published: sites.filter((s) => s.status === "published").length,
    draft: sites.filter((s) => s.status === "draft" || s.status === "rejected").length,
    pending: sites.filter((s) => s.status === "pending_approval").length,
  }), [sites]);

  // Full-screen "Edit Website" overlay: BuilderTab only, no KPI strip/tab chrome,
  // covering the whole viewport (same fixed inset-0 z-50 pattern
  // components/ReportDashboardBuilder.tsx's Full Screen already established).
  // Every website-mutating call in WebsiteBuilderCanvas already persists per-action and
  // returns the fresh Website; hand it straight to state instead of re-fetching, and
  // mirror it into the My Sites list so status/section counts stay in sync.
  const applyWebsite = (w: Website) => {
    setSelected(w);
    setSites((prev) => prev.map((s) => (s.id === w.id ? w : s)));
  };

  if (fullScreenBuilder && selected) {
    return (
      <div className="fixed inset-0 z-50 bg-brand-ink text-white flex flex-col">
        {!!selected.studio_config ? <LoneStarCustomizer key={selected.id} website={selected} onWebsiteChange={applyWebsite} onDirtyChange={setEditorDirty}/> : <WebsiteStudioEditor
          key={selected.id}
          onDirtyChange={setEditorDirty}
          theme={theme}
          website={selected}
          onWebsiteChange={applyWebsite}
          fullScreen
          onToggleFullScreen={() => setFullScreenBuilder(false)}
        />}
      </div>
    );
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      {/* Quick-stats row -- matches the reference look (SocialReputationBoard/
          AdvertisingBoard/EventsBoard): a grid of dark KPI cards up top, before the
          app-function tab row. */}
      <div style={{display:(section === "approvals" || section === "analytics" || section === "chat" || (!!selected?.studio_config && section === "builder")) ? "none" : undefined}} className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-black/20", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        {[
          { label: "Total Sites", value: kpis.total },
          { label: "Published", value: kpis.published },
          { label: "Draft", value: kpis.draft },
          { label: "Pending Approval", value: kpis.pending },
        ].map((k, i) => (
          <div key={k.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
              style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
            />
            <div className="text-2xl font-semibold">{k.value}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k.label}</div>
          </div>
        ))}
      </div>

      <nav aria-label="Website management" className={websiteNav.navigation} data-theme={theme}>
        {tabs.map((t) => (
          <WorkButton type="submit"
            key={t.key}
            aria-current={section === t.key ? "page" : undefined}
            onClick={() => {
              if (editorDirty) { setEditorNotice("Save or discard your website changes before leaving the editor."); return; }
              setEditorNotice("");
              setSection(t.key);
            }}
            disabled={(t.key === "builder" || t.key === "seo" || t.key === "analytics" || t.key === "chat") && !selected}
            className={`text-xs px-3 py-1.5 rounded transition disabled:opacity-30 ${section === t.key ? "bg-zinc-200 text-black font-medium" : tc(theme, "text-zinc-400 hover:text-white hover:bg-zinc-900", "text-zinc-600 hover:text-black hover:bg-zinc-100")}`}
          >
            {t.label}
          </WorkButton>
        ))}
        {selected && <span className={websiteNav.siteName} title={selected.name}>{selected.name}</span>}
      </nav>

      {editorNotice && <p role="status" className="px-4 py-2 text-xs">{editorNotice}</p>}
      {section === "sites" && <details className="p-4"><summary>Optional tools · salesperson pages</summary><p className="text-xs p-3">Give a salesperson a shareable page that routes inquiries to them. This is separate from your dealership website.</p><PersonalTab theme={theme} websites={sites}/></details>}
      {section === "sites" && <SitesTab theme={theme} sites={sites} onRefresh={refreshSites} onSelect={handleSelect} onEditWebsite={handleEditWebsite} siteTemplates={siteTemplates} />}
      {section === "builder" && selected && (
        !!selected.studio_config ? <LoneStarCustomizer key={selected.id} website={selected} onWebsiteChange={applyWebsite} onDirtyChange={setEditorDirty}/> : <WebsiteStudioEditor
          key={selected.id}
          onDirtyChange={setEditorDirty}
          theme={theme}
          website={selected}
          onWebsiteChange={applyWebsite}
          onToggleFullScreen={() => setFullScreenBuilder(true)}
        />
      )}
      {section === "seo" && selected && <SeoAdminTab theme={theme} website={selected} onChanged={refreshSelected} pageKeys={pageKeys} />}
      {section === "analytics" && selected && <WebsiteTraffic key={selected.id} website={selected} onChange={applyWebsite} />}
      {section === "chat" && selected && <WebsiteDealerAssistant key={selected.id} website={selected} onChange={applyWebsite}><ChatTab theme={theme} websiteId={selected.id} /></WebsiteDealerAssistant>}

      {section === "approvals" && <><WebsiteDomainSetup key={selected?.id || "none"} website={selected} onChange={applyWebsite} /><details className="p-4"><summary>Publishing review</summary><ApprovalsTab key={`${selected?.id}-${selected?.status}-${selected?.studio_revision}`} theme={theme} onDecision={site=>{if(site.id===selectedId)applyWebsite(site);else void refreshSites();}} /></details></>}
    </div>
  );
}
