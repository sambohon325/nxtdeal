"use client";

import { useMemo, useRef, useState } from "react";
import { WebsiteStudioEditor, type websiteStudioApi } from "./WebsiteStudioEditor";
import type { SectionTemplate, Website } from "@/lib/websites";

const templates: SectionTemplate[] = [
  { key: "hero_banner", name: "Hero", description: "", fields: [
    { key: "headline", label: "Headline", type: "textarea" },
    { key: "subheadline", label: "Introduction", type: "textarea" },
    { key: "cta_text", label: "Button label", type: "text" },
  ] },
  { key: "text_block", name: "Story", description: "", fields: [
    { key: "heading", label: "Heading", type: "text", required: true },
    { key: "body", label: "Story", type: "textarea" },
  ] },
  { key: "inventory_grid", name: "Inventory", description: "", fields: [{ key: "heading", label: "Heading", type: "text" }] },
];
const initial = {
  id: "synthetic-editor", name: "Example Motors", status: "draft", mode: "traditional",
  pages: { home: { sections: [
    { section_key: "hero_banner", locked: false, fields: { headline: "Your next truck.\nYour next chapter.", subheadline: "Local people. Open roads. A vehicle for what comes next.", cta_text: "Explore inventory" } },
    { section_key: "text_block", locked: false, fields: { heading: "Built around you.", body: "Synthetic content for testing the website editor. No real dealership records are connected." } },
  ] }, inventory: { sections: [{ section_key: "inventory_grid", locked: false, fields: { heading: "Available vehicles" } }] } },
  studio_config: { version: 1, theme_id: "lone-star", language: "en", events: [], social_links: {}, backgrounds: {} },
  owners: [], image_library: [], history: [], admin_settings: {
    custom_domain: null, meta_title: null, meta_description: null, sitemap_enabled: false,
    block_ai_crawlers: false, allow_search_engines: false, google_analytics_id: null,
    umami_site_id: null, umami_script_url: null, facebook_pixel_id: null,
    custom_head_snippet: null, custom_body_snippet: null, branding_mode: "independent",
    oem_name: null, oem_logo_url: null, page_seo: {}, ai_receptionist_enabled: false,
  }, requested_by: "synthetic-owner",
  updated_at: "2026-10-20T00:00:00Z", created_at: "2026-10-20T00:00:00Z", published_at: null,
  reviewed_by: null, review_notes: null,
} as Website;

/** All editor requests are replaced with isolated in-memory fixture operations. */
export function WebsiteStudioEditorLab() {
  const store = useRef(structuredClone(initial));
  const [website, setWebsite] = useState(store.current);
  const api = useMemo<typeof websiteStudioApi>(() => {
    const change = (operation: (site: Website) => void) => {
      const site = structuredClone(store.current);
      operation(site);
      site.updated_at = new Date().toISOString();
      store.current = site;
      return Promise.resolve(site);
    };
    return {
      listSectionTemplates: async () => templates,
      previewWebsite: async () => structuredClone(store.current),
      updateSectionFields: async (_id, page, index, fields) => change(site => { site.pages[page].sections[index].fields = fields; }),
      addSection: async (_id, page, section_key, fields) => change(site => {
        site.pages[page] ||= { sections: [] };
        site.pages[page].sections.push({ section_key, fields, locked: false });
      }),
      removeSection: async (_id, page, index) => change(site => { site.pages[page].sections.splice(index, 1); }),
      reorderSections: async (_id, page, order) => change(site => { const items = site.pages[page].sections; site.pages[page].sections = order.map(index => items[index]); }),
      startWebsiteDraft: async () => change(site => { site.status = "draft"; }),
      submitWebsite: async () => change(site => { site.status = "pending_approval"; }),
    };
  }, []);
  return <main style={{ background: "#101923", color: "#ecf4fa", minHeight: "100vh" }}>
    <p style={{ padding: "12px 22px", fontSize: 12 }}>Local editor test · Synthetic data only · Changes reset on reload. External design/media controls are disabled here.</p>
    <WebsiteStudioEditor website={website} onWebsiteChange={setWebsite} theme="dark" api={api} localHarness />
  </main>;
}
