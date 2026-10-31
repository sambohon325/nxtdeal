"use client";
import { WorkButton, WorkSelect, WorkTextarea, WorkInput } from "./WorkspaceUi";
import { WebsiteTheme } from "./WebsiteTheme";

import { useEffect, useState } from "react";
import {
  addSection, listSectionTemplates, previewWebsite, removeSection, reorderSections,
  startWebsiteDraft, submitWebsite, updateSectionFields, type SectionTemplate, type Website,
} from "@/lib/websites";
import { SitePageRenderer } from "./SiteSectionRenderer";
import { WebsiteDesignSettings } from "./WebsiteDesignSettings";
import { WebsiteStudioEvents } from "./WebsiteStudioEvents";
import ImageLibraryPicker from "./ImageLibraryPicker";
import styles from "./WebsiteStudioEditor.module.css";
import { WebsitePreviewFrame } from "./WebsitePreviewFrame";

export const websiteStudioApi = { addSection, listSectionTemplates, previewWebsite, removeSection, reorderSections, startWebsiteDraft, submitWebsite, updateSectionFields };
const pages = ["home", "inventory", "about", "testimonials", "financing", "contact"];
const label = (text: string) => text.replaceAll("_", " ").replace(/\b\w/g, letter => letter.toUpperCase());

export function WebsiteStudioEditor({ website, theme, onWebsiteChange, onToggleFullScreen, fullScreen, api = websiteStudioApi, localHarness = false, onDirtyChange }: {
  website: Website; theme: "dark" | "light"; onWebsiteChange: (website: Website) => void;
  onToggleFullScreen?: () => void; fullScreen?: boolean; api?: typeof websiteStudioApi;
  localHarness?: boolean;
  onDirtyChange?: (dirty: boolean) => void;
}) {
  const [tab, setTab] = useState<"content" | "design">("content");
  const [page, setPage] = useState("home");
  const [selected, setSelected] = useState(0);
  const [templates, setTemplates] = useState<SectionTemplate[]>([]);
  const [preview, setPreview] = useState<Website | null>(null);
  const [fields, setFields] = useState<Record<string, unknown> | null>(null);
  const [designDirty, setDesignDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [device, setDevice] = useState<"desktop" | "mobile">("desktop");
  const [addType, setAddType] = useState("text_block");
  const [imageField, setImageField] = useState<string | null>(null);
  const editable = website.status === "draft" || website.status === "rejected";
  const sections = website.pages[page]?.sections || [];
  const section = sections[selected];
  const definition = templates.find(template => template.key === section?.section_key);
  const currentFields = fields || section?.fields || {};
  const dirty = fields !== null;
  useEffect(() => { onDirtyChange?.(dirty || designDirty); }, [dirty, designDirty, onDirtyChange]);
  useEffect(() => {
    if (!dirty && !designDirty) return;
    const warn = (event: BeforeUnloadEvent) => { event.preventDefault(); event.returnValue = ""; };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [dirty, designDirty]);

  useEffect(() => {
    let active = true;
    api.listSectionTemplates().then(result => { if (active) setTemplates(result); }).catch(error => { if (active) setMessage(error.message); });
    return () => { active = false; };
  }, [api]);
  useEffect(() => {
    let active = true;
    api.previewWebsite(website.id, "traditional").then(result => { if (active) setPreview(result); }).catch(error => { if (active) setMessage(error.message); });
    return () => { active = false; };
  }, [api, website.id, website.updated_at, website.studio_revision]);

  function navigate(action: () => void) {
    if (busy) return;
    if (dirty || designDirty) { setMessage("Save or discard your changes before moving on."); return; }
    setMessage("");
    action();
  }
  async function perform(action: () => Promise<Website>, after?: () => void) {
    setBusy(true); setMessage("");
    try {
      const updated = await action();
      onWebsiteChange(updated);
      setFields(null);
      after?.();
      setMessage(updated.status === "pending_approval" ? "Sent for review. This version is now read-only." : "Draft saved.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Unable to save."); }
    finally { setBusy(false); }
  }
  function move(delta: number) {
    const target = selected + delta;
    if (target < 0 || target >= sections.length) return;
    const order = sections.map((_, index) => index);
    [order[selected], order[target]] = [order[target], order[selected]];
    void perform(() => api.reorderSections(website.id, page, order), () => setSelected(target));
  }
  const rendered = preview?.pages[page]?.sections || [];
  // The canonical traditional render removes the home car-builder alternative.
  const visible = sections.map((item, index) => ({ item, index })).filter(({ item }) => page !== "home" || item.section_key !== "car_builder");
  const previewSections = visible.map(({ item, index }, renderIndex) => ({
    ...item, ...rendered[renderIndex], fields: index === selected && fields ? fields : item.fields,
  }));
  const editorFields = definition?.fields || Object.keys(currentFields).map(key => ({ key, label: label(key), type: "text" as const }));

  return <section className={styles.root} data-nxt-glass data-theme={theme}>
    <header className={styles.header}>
      <div><span className={styles.eyebrow}>Marketing / Content / Website</span><h2>{website.name}</h2></div>
      <div className={styles.actions}><span className={styles.status}>{dirty ? "Unsaved section changes" : label(website.status)}</span>
        {onToggleFullScreen && <WorkButton type="submit" onClick={() => navigate(onToggleFullScreen)}>{fullScreen ? "Close full screen" : "Full screen"}</WorkButton>}
        {website.status === "published" && <WorkButton type="submit" disabled={busy || dirty || designDirty} onClick={() => perform(() => api.startWebsiteDraft(website.id))}>Edit a new draft</WorkButton>}
        <WorkButton type="submit" disabled={!editable || busy || dirty || designDirty} onClick={() => perform(() => api.submitWebsite(website.id))}>Send for review</WorkButton>
      </div>
    </header>
    <nav className={styles.tabs} aria-label="Website editor">
      <WorkButton data-work-view type="submit" aria-pressed={tab === "content"} onClick={() => navigate(() => setTab("content"))}>Pages & content</WorkButton>
      <WorkButton data-work-view type="submit" disabled={localHarness} aria-pressed={tab === "design"} onClick={() => navigate(() => setTab("design"))}>Design, events & socials</WorkButton>
      <span>{website.published_at && website.status !== "published" ? "The approved version stays live while you prepare these changes." : "Changes stay in draft until approved."}</span>
    </nav>
    {message && <div className={styles.message} role="status">{message}</div>}
    {!editable && <div className={styles.message}>This {label(website.status).toLowerCase()} version is read-only. Review and publishing stay in Approvals.</div>}
    {tab === "design" ? <WebsiteDesignSettings key={website.id} website={website} onChange={onWebsiteChange} onDirtyChange={setDesignDirty} /> : <div className={styles.workspace}>
      <aside className={styles.outline}>
        <label>Page<WorkSelect value={page} onChange={event => navigate(() => { setPage(event.target.value); setSelected(0); })}>{pages.map(key => <option key={key} value={key}>{label(key)}</option>)}</WorkSelect></label>
        <h3>Sections</h3>
        <div className={styles.sectionList}>{sections.map((item, index) => <WorkButton type="submit" key={`${item.section_key}-${index}`} aria-pressed={selected === index} onClick={() => navigate(() => setSelected(index))}><span>{String(index + 1).padStart(2, "0")}</span>{label(item.section_key)}{item.locked && <small>Locked</small>}</WorkButton>)}</div>
        {!sections.length && <p>This page is empty. Add a section to begin.</p>}
        <label>Add a section<WorkSelect value={addType} onChange={event => setAddType(event.target.value)}>{templates.map(item => <option key={item.key} value={item.key}>{item.name}</option>)}</WorkSelect></label>
        <WorkButton type="submit" disabled={!editable || busy || dirty || !templates.length} onClick={() => {
          const template = templates.find(item => item.key === addType);
          const defaults = Object.fromEntries((template?.fields || []).map(field => [field.key, field.default ?? (field.required ? field.label : "")]));
          void perform(() => api.addSection(website.id, page, addType, defaults), () => setSelected(sections.length));
        }}>Add section</WorkButton>
      </aside>
      <div className={styles.previewColumn}>
        <div className={styles.previewToolbar}><strong>{label(page)} preview</strong><div className={styles.actions}><WorkButton type="submit" aria-pressed={device === "desktop"} onClick={() => setDevice("desktop")}>Desktop</WorkButton><WorkButton type="submit" aria-pressed={device === "mobile"} onClick={() => setDevice("mobile")}>Mobile</WorkButton></div></div>
        <div className={styles.previewStage}><WebsitePreviewFrame device={device}><div className={styles.website}><WebsiteTheme themeId={website.studio_config?.theme_id}>
          <div className={styles.previewIdentity}>{website.name}</div>
          {page === "home" && <WebsiteStudioEvents events={preview?.studio_events || []} websiteId={website.id} language={website.studio_config?.language} bannerOnly />}
          {!preview ? <p className={styles.empty}>Loading saved content…</p> : !sections.length ? <p className={styles.empty}>Your page starts here.</p> : <div inert>
            <SitePageRenderer sections={previewSections} websiteId={website.id} themeId={website.studio_config?.theme_id} websiteName={website.name} backgrounds={website.studio_config?.backgrounds} pageKey={page} />
            {page === "home" && <WebsiteStudioEvents events={preview.studio_events || []} websiteId={website.id} language={website.studio_config?.language} />}
          </div>}
        </WebsiteTheme></div></WebsitePreviewFrame></div>
        <p className={styles.previewNote}>Live content preview · Customer forms and links are inactive here.</p>
      </div>
      <aside className={styles.inspector}>
        {section ? <><h3>{label(section.section_key)}</h3><p>{section.locked ? "This section is locked." : "Edit the content below. See changes before saving."}</p>
          <fieldset disabled={!editable || busy || section.locked}>
            {editorFields.map(field => <label key={field.key}>{field.label}{field.key === "location_id" ? <WorkSelect value={String(currentFields[field.key] || "")} onChange={event => setFields({ ...currentFields, [field.key]: event.target.value })}><option value="">All locations</option>{(preview?.studio_locations || []).map(location => <option key={location.id} value={location.id}>{location.name}</option>)}</WorkSelect> : field.type === "textarea" || /headline|body|description|text|html/i.test(field.key) ? <WorkTextarea rows={4} value={String(currentFields[field.key] ?? "")} onChange={event => setFields({ ...currentFields, [field.key]: event.target.value })} /> : <WorkInput value={String(currentFields[field.key] ?? "")} onChange={event => setFields({ ...currentFields, [field.key]: event.target.value })} />}
              {/image_url|logo_url/.test(field.key) && <WorkButton type="button" disabled={localHarness} onClick={() => setImageField(field.key)}>Choose from media library</WorkButton>}
            </label>)}
            <div className={styles.actions}><WorkButton type="submit" disabled={!dirty} onClick={() => perform(() => api.updateSectionFields(website.id, page, selected, currentFields))}>Save section</WorkButton><WorkButton type="submit" disabled={!dirty} onClick={() => { setFields(null); setMessage(""); }}>Discard</WorkButton></div>
            <div className={styles.actions}><WorkButton type="submit" disabled={dirty || selected === 0} onClick={() => move(-1)}>Move up</WorkButton><WorkButton type="submit" disabled={dirty || selected === sections.length - 1} onClick={() => move(1)}>Move down</WorkButton></div>
            <WorkButton type="submit" className={styles.remove} disabled={dirty} onClick={() => perform(() => api.removeSection(website.id, page, selected), () => setSelected(Math.max(0, selected - 1)))}>Remove section</WorkButton>
          </fieldset>
        </> : <p>Select or add a section to edit its content.</p>}
      </aside>
    </div>}
    <ImageLibraryPicker open={imageField !== null} theme={theme} onClose={() => setImageField(null)} onPick={url => { if (imageField) setFields({ ...currentFields, [imageField]: url }); setImageField(null); }} />
  </section>;
}
