"use client";
import { WorkButton, WorkSelect, WorkInput, WorkTextarea } from "./WorkspaceUi";

import { useEffect, useState } from "react";
import library from "@/lib/websiteStudioCatalogue.json";
import { getWebsiteStudioInventory, saveWebsiteStudio, type Website, type WebsiteStudioConfig, type WebsiteStudioEvent, type WebsiteStudioRenderedEvent } from "@/lib/websites";
import styles from "./WebsiteDesignSettings.module.css";
import { WebsiteLocationsSettings } from "./WebsiteLocationsSettings";
import { WebsiteArtworkPicker } from "./WebsiteArtworkPicker";
import { WebsiteDesignPicker } from "./WebsiteDesignPicker";

const socialPlatforms = ["facebook", "instagram", "youtube", "tiktok", "x", "linkedin", "threads", "pinterest", "whatsapp", "yelp", "snapchat"];
const initialConfig = (website: Website): WebsiteStudioConfig => website.studio_config || {
  version: 1, theme_id: "lone-star", language: "en", social_links: {}, backgrounds: {}, events: [],
};

/** Draft-only controls; mounted by website/revision to prevent crossing site state. */
export function WebsiteDesignSettings({ website, onChange, onDirtyChange }: { website: Website; onChange: (site: Website) => void; onDirtyChange?: (dirty: boolean) => void }) {
  const [config, setConfig] = useState(() => initialConfig(website));
  const [category, setCategory] = useState("All");
  const [backgroundSection, setBackgroundSection] = useState("about");
  const [eventId, setEventId] = useState(config.events[0]?.template_id || "spring");
  const [language, setLanguage] = useState<"en" | "es">("en");
  const [busy, setBusy] = useState(false);
  const [dirty, setDirty] = useState(false);
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty, onDirtyChange]);
  const [message, setMessage] = useState("");
  const [inventory, setInventory] = useState<WebsiteStudioRenderedEvent["vehicles"]>([]);
  const [inventoryError, setInventoryError] = useState("");
  useEffect(() => {
    let active = true;
    getWebsiteStudioInventory(website.id).then(vehicles => { if (active) setInventory(vehicles); }).catch(error => { if (active) setInventoryError(error.message || "Inventory could not be loaded."); });
    return () => { active = false; };
  }, [website.id]);
  const editable = website.status === "draft" || website.status === "rejected";
  const template = library.events.find(e => e.id === eventId)!;
  const event = config.events.find(e => e.template_id === eventId);
  const update = (patch: Partial<WebsiteStudioConfig>) => {
    setConfig(current => ({ ...current, ...patch }));
    setDirty(true);
    setMessage("");
  };
  function updateEvent(patch: Partial<WebsiteStudioEvent>) {
    const next: WebsiteStudioEvent = { template_id: eventId, enabled: false, vehicle_ids: [], ...event, ...patch };
    update({ events: [...config.events.filter(e => e.template_id !== eventId), next] });
  }
  async function save() {
    setBusy(true);
    setMessage("");
    try {
      const saved = await saveWebsiteStudio(website.id, config, website.studio_revision || 0);
      setDirty(false);
      setMessage("Draft design saved.");
      onChange(saved);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to save the draft.");
    } finally { setBusy(false); }
  }
  const title = language === "es" ? event?.title_es ?? template.titleEs : event?.title ?? template.title;
  const summary = language === "es" ? event?.summary_es ?? template.summaryEs : event?.summary ?? template.summary;
  return <section className={styles.root} data-nxt-glass>
    <header className={styles.header}>
      <div><span className={styles.eyebrow}>Website / Design settings</span><h2>Make it your dealership.</h2><p>Approved designs, seasonal artwork and your social channels.</p></div>
      <div className={styles.actions}><span>{dirty ? "Unsaved changes" : website.status.replace("_", " ")}</span><WorkButton type="submit" disabled={!editable || busy || !dirty} onClick={save}>{busy ? "Saving…" : "Save draft"}</WorkButton><WorkButton type="submit" disabled={!dirty || busy} onClick={() => { setConfig(initialConfig(website)); setDirty(false); setMessage(""); }}>Discard changes</WorkButton></div>
    </header>
    {!editable && <p role="status">This site is {website.status.replace("_", " ")}. Design editing is locked to protect its reviewed version.</p>}
    {message && <p role="status">{message}</p>}
    <WebsiteDesignPicker value={config.theme_id} disabled={!editable || busy} onSelect={theme_id => update({ theme_id })} />
    <fieldset disabled={!editable || busy} className={styles.settings}>
      <label>Default language<WorkSelect value={config.language} onChange={e => update({ language: e.target.value as "en" | "es" })}><option value="en">English</option><option value="es">Español</option></WorkSelect></label>
    </fieldset>
    <div className={styles.sectionHeading}><div><h3>Events & seasons</h3><p>46 reviewed themes. Edit each language independently.</p></div><label>Collection<WorkSelect value={category} onChange={e => setCategory(e.target.value)}>{["All", ...new Set(library.events.map(e => e.category))].map(c => <option key={c}>{c}</option>)}</WorkSelect></label></div>
    <div className={styles.gallery} aria-label="Event artwork">
      {library.events.filter(e => category === "All" || e.category === category).map(item => <WorkButton key={item.id} type="button" aria-pressed={eventId === item.id} onClick={() => setEventId(item.id)}>
        {/* Reviewed first-party static catalogue assets, no remote image optimizer. */}
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={item.banner} alt="" loading="lazy" /><span>{item.name}</span>
        {config.events.some(e => e.template_id === item.id && e.enabled) && <small>Enabled</small>}
      </WorkButton>)}
    </div>
    <div className={styles.editor}>
      <div><div className={styles.actions}><h3>{template.name}</h3><WorkButton type="button" aria-pressed={language === "en"} onClick={() => setLanguage("en")}>EN</WorkButton><WorkButton type="button" aria-pressed={language === "es"} onClick={() => setLanguage("es")}>ES</WorkButton></div>
        <p>{template.context}</p>
        <div className={styles.artwork} style={{ backgroundImage: `linear-gradient(90deg,rgba(0,0,0,.65),rgba(0,0,0,.12)),url("${event?.banner_url || template.banner}")` }}><strong>{title}</strong><span>{summary}</span></div>
        <small>Artwork preview · Event dates and eligibility are saved with the draft.</small>
      </div>
      <fieldset disabled={!editable || busy} className={styles.fields}>
        <label className={styles.check}><WorkInput type="checkbox" checked={event?.enabled || false} onChange={e => updateEvent({ enabled: e.target.checked })} />Enable this event</label>
        <label>{language === "es" ? "Spanish headline" : "English headline"}<WorkInput value={title} onChange={e => updateEvent(language === "es" ? { title_es: e.target.value } : { title: e.target.value })} /></label>
        <label>{language === "es" ? "Spanish description" : "English description"}<WorkTextarea value={summary} onChange={e => updateEvent(language === "es" ? { summary_es: e.target.value } : { summary: e.target.value })} /></label>
        <label>{language === "es" ? "Spanish offer details" : "English offer details"}<WorkTextarea value={language === "es" ? event?.terms_es ?? template.termsEs : event?.terms ?? template.terms} onChange={e => updateEvent(language === "es" ? { terms_es: e.target.value } : { terms: e.target.value })} /></label>
        <div className={styles.settings}><label>Starts<WorkInput type="date" value={event?.starts_on || ""} onChange={e => updateEvent({ starts_on: e.target.value })} /></label><label>Ends<WorkInput type="date" value={event?.ends_on || ""} onChange={e => updateEvent({ ends_on: e.target.value })} /></label></div>
        <WebsiteArtworkPicker label="Event banner artwork" value={event?.banner_url || ""} disabled={!editable || busy} onChange={banner_url => updateEvent({ banner_url })} />
        <WebsiteArtworkPicker label="Event feature image" value={event?.image_url || ""} disabled={!editable || busy} onChange={image_url => updateEvent({ image_url })} />
        <div><h3>Vehicles in this event</h3><p>Select available inventory. Sold vehicles leave the event automatically.</p>
          {inventoryError && <p role="alert">{inventoryError}</p>}
          <div className={styles.eligibility}>{inventory.map(vehicle => <label key={vehicle.id} className={styles.check}><WorkInput type="checkbox" checked={event?.vehicle_ids.includes(vehicle.id) || false} onChange={e => updateEvent({ vehicle_ids: e.target.checked ? [...(event?.vehicle_ids || []), vehicle.id] : (event?.vehicle_ids || []).filter(id => id !== vehicle.id) })} /><span>{[vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(" ")} <small>{vehicle.id}</small></span></label>)}</div>
          {!inventory.length && !inventoryError && <p>No available vehicles to select.</p>}
        </div>
      </fieldset>
    </div>
    <h3>Section imagery</h3><p>Add a photographic break before a section. Each image is separated by content so photos never stack together.</p>
    <label>Section<WorkSelect value={backgroundSection} onChange={e => setBackgroundSection(e.target.value)}>{["about", "financing", "trade", "contact"].map(key => <option key={key} value={key}>{key === "trade" ? "Trade-in" : key[0].toUpperCase() + key.slice(1)}</option>)}</WorkSelect></label>
    <WebsiteArtworkPicker label="Section image" value={config.backgrounds[backgroundSection] || ""} disabled={!editable || busy} onChange={url => update({ backgrounds: { ...config.backgrounds, [backgroundSection]: url } })} />
    <WebsiteLocationsSettings />
    <h3>Social channels</h3><p>Add your dealership profile links. Empty channels stay hidden.</p>
    <fieldset disabled={!editable || busy} className={styles.socials}>{socialPlatforms.map(platform => <label key={platform}>{platform}<WorkInput type="url" placeholder="https://" value={config.social_links[platform] || ""} onChange={e => update({ social_links: { ...config.social_links, [platform]: e.target.value } })} /></label>)}</fieldset>
  </section>;
}
