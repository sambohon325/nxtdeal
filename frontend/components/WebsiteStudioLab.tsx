"use client";
import { WorkSelect, WorkTextarea, WorkButton } from "./WorkspaceUi";

import { useState } from "react";
import { WebsiteDesignPicker } from "./WebsiteDesignPicker";
import { WebsiteStudioEvents } from "./WebsiteStudioEvents";
import library from "@/lib/websiteStudioCatalogue.json";
import styles from "./WebsiteDesignSettings.module.css";
import { WebsiteTheme } from "./WebsiteTheme";
import { SitePageRenderer } from "./SiteSectionRenderer";
import { ApprovedWebsiteHero } from "./ApprovedWebsiteHero";

/** Development-only visual harness. No customer reads, writes or credentials. */
export function WebsiteStudioLab() {
  const [selected, setSelected] = useState("tempo");
  const [language, setLanguage] = useState<"en" | "es">("en");
  const [headline, setHeadline] = useState("");
  const [mobile, setMobile] = useState(false);
  const event = library.events.find(item => item.id === "halloween")!;
  return <main className="p-6" style={{ background: "#101923", color: "#ecf4fa", minHeight: "100vh" }}>
    <span className={styles.eyebrow}>NXTDeal / Marketing / Content / Website</span>
    <h2>Website studio · Local component review</h2>
    <p>Synthetic visual test. No customer records are accessed or changed.</p>
    <section id="live-hero"><h3>Live approved hero · Real content bindings</h3><div className={styles.settings}>
      <label>Design<WorkSelect value={selected} onChange={event => setSelected(event.target.value)}>{library.themes.map(theme => <option value={theme.id} key={theme.id}>{theme.name}</option>)}</WorkSelect></label>
      <label>Headline override<WorkTextarea value={headline} onChange={event => setHeadline(event.target.value)} placeholder="Leave blank to use the approved headline" /></label>
    </div><WorkButton type="submit" onClick={() => setMobile(!mobile)}>{mobile ? "Show desktop hero" : "Show mobile hero"}</WorkButton><div style={{ maxWidth: mobile ? 390 : undefined, margin: "20px auto" }}><WebsiteTheme themeId={selected}><header className="site-header p-5 flex justify-between"><strong>Example Motors</strong><span>Inventory · About us · Contact</span></header><ApprovedWebsiteHero themeId={selected} fields={{ headline }} websiteName="Example Motors" editable onFieldEdit={(key, value) => { if (key === "headline") setHeadline(value); }} /><SitePageRenderer themeId={selected} sections={[
      {section_key:"inventory_grid",fields:{},locked:false,live_vehicles:[
        {id:"synthetic-1",year:2025,make:"Example",model:"Truck",price:32000,location_id:"north",location_name:"North",image_url:"/website-studio/assets/lone-star-truck-hero.png"},
        {id:"synthetic-2",year:2024,make:"Example",model:"Touring",price:28000,location_id:"south",location_name:"South",image_url:"/website-studio/assets/tempo-luxury-hero.png"},
        {id:"synthetic-3",year:2025,make:"Example",model:"Crossover",price:26000,location_id:"north",location_name:"North",image_url:"/website-studio/assets/fieldwork-hero.png"},
      ]},
      {section_key:"contact_form",social_links:{facebook:"https://example.test/facebook",instagram:"https://example.test/instagram",youtube:"https://example.test/youtube",tiktok:"https://example.test/tiktok",x:"https://example.test/x",snapchat:"https://example.test/snapchat"},fields:{heading:"Your next chapter starts here."},locked:false},
      {section_key:"image_gallery",fields:{image_urls:"/website-studio/assets/scene-forest.png,/website-studio/assets/scene-coast.png"},locked:false},
    ]} /><footer className="site-footer text-center">Example Motors · Synthetic preview</footer></WebsiteTheme></div></section>
    <WebsiteDesignPicker value={selected} onSelect={setSelected} disabled={false} />
    <div className={styles.actions}><h3>Shared event renderer</h3><WorkButton type="submit" onClick={() => setLanguage(language === "en" ? "es" : "en")}>{language === "en" ? "View Spanish" : "View English"}</WorkButton></div>
    <WebsiteStudioEvents websiteId="synthetic-only" language={language} events={[{
      id: event.id, title: event.title, title_es: event.titleEs, summary: event.summary,
      summary_es: event.summaryEs, terms: event.terms, terms_es: event.termsEs,
      starts_on: "2026-10-20", ends_on: "2026-10-31", image_url: event.image, banner_url: event.banner,
      image_alt: event.imageAlt, image_alt_es: event.imageAltEs, background: event.bg, accent: event.accent, vehicles: [],
    }]} />
  </main>;
}
