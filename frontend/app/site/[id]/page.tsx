"use client";

// The real, public, unauthenticated dealership-visitor-facing page -- built 2026-07-16
// (Cowork, interactive), Sam's direct follow-up after the Website Builder overhaul:
// "im not sure why this isn't coming through. The customer should be able to choose
// between a traditional website and a drivefinder ChatGPT style. its a toggle on the
// car purchasing / dealers customer facing (not dealersOS) side... All websites will
// have a choice." The backend has genuinely computed both variants since session 86
// (core/websites.py's get_website_rendered()) -- what never existed anywhere in this
// codebase was an actual page a visitor could load. This is that page.
//
// Deliberately a path-based route (dealeros.xyz/site/{id}) rather than a per-dealer
// subdomain -- real custom-domain routing per site is DNS/deploy infrastructure
// (core/websites.py's get_dns_instructions(), an honest non-integration -- see that
// file's docstring) that's a separate topic from "does the toggle actually render
// anywhere." Swapping to a real subdomain later doesn't change this rendering code.
//
// No NXTDeal chrome here at all (no BrandRibbon, no font-brand, no dark charcoal) --
// this is meant to look like an actual independent dealership's own website, not an
// internal NXTDeal screen.
import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useParams, useSearchParams, useRouter, usePathname } from "next/navigation";
import { publicGetWebsite, publicGetVehiclePage, publicSubmitContactForm, type VehicleLandingPage, type Website } from "@/lib/websites";
import { WebsiteSocialLinks } from "@/components/WebsiteSocialLinks";
import { WebsiteVisitorAnalytics } from "@/components/WebsiteVisitorAnalytics";
import { LoneStarPublicSite } from "@/components/LoneStarPublicSite";
import { WebsiteTheme } from "@/components/WebsiteTheme";
import { SitePageRenderer } from "@/components/SiteSectionRenderer";
import { PublicChatWidget } from "@/components/PublicChatWidget";
import { WebsiteStudioEvents } from "@/components/WebsiteStudioEvents";

const PAGE_KEYS = ["home", "inventory", "about", "testimonials", "financing", "contact"];
const PAGE_LABELS: Record<string, string> = {
  home: "Home",
  inventory: "Inventory",
  about: "About",
  testimonials: "Testimonials",
  financing: "Financing",
  contact: "Contact",
};

type ModeT = "traditional" | "dealer_gpt";

// useSearchParams() (added session 113 follow-up, for the ?page= deep link below)
// requires a Suspense boundary around any usage, same convention this codebase's own
// app/panel/workflow/page.tsx etc. already established.
export default function PublicSitePage() {
  return (
    <Suspense fallback={<div className="min-h-screen flex items-center justify-center bg-white text-zinc-400 text-sm">Loading…</div>}>
      <PublicSitePageContent />
    </Suspense>
  );
}

function PublicSitePageContent() {
  const params = useParams();
  const websiteId = String(params?.id ?? "");
  const searchParams = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();

  const inquiryVehicleId = searchParams?.get("vehicle") || "";
  const inquiryIntent = searchParams?.get("intent") || "information";
  const [inquiryVehicle, setInquiryVehicle] = useState<VehicleLandingPage | null>(null);
  useEffect(() => {
    let active = true;
    setInquiryVehicle(null);
    if (inquiryVehicleId) publicGetVehiclePage(websiteId, inquiryVehicleId).then(vehicle => { if (active) setInquiryVehicle(vehicle); }).catch(() => {});
    return () => { active = false; };
  }, [websiteId, inquiryVehicleId]);
  const [site, setSite] = useState<Website | null>(null);
  const [mode, setMode] = useState<ModeT>("traditional");
  // Deep-linkable per-page URLs (?page=inventory, etc.) -- session 113 follow-up's
  // enterprise SEO automation slice. The initial value honors a real `?page=` query
  // param (what core/website_seo.py's get_sitemap_xml() now links to) instead of
  // always landing on "home", so sitemap/shared/bookmarked page links actually work.
  const initialPage = searchParams?.get("page") || "home";
  const [activePage, setActivePageState] = useState(PAGE_KEYS.includes(initialPage) ? initialPage : "home");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function setActivePage(key: string) {
    setActivePageState(key);
    const qs = key === "home" ? "" : `?page=${encodeURIComponent(key)}`;
    router.replace(`${pathname}${qs}`, { scroll: false });
  }

  const load = useCallback((m: ModeT) => {
    if (!websiteId) return;
    setLoading(true);
    setError(null);
    // Website Personalization (2026-07-19) -- a real ?utm_source= on this page's own
    // URL (e.g. from a mail piece or an ad's landing-page link) rides straight through
    // to the backend, which overlays any matching section's personalization_variants.
    // The Referer header is sent by the browser automatically, read server-side.
    const utmSource = searchParams?.get("utm_source") || undefined;
    publicGetWebsite(websiteId, m, utmSource)
      .then((w) => {
        setSite(w);
        setMode((w.effective_mode as ModeT) ?? m);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "This site isn't available."))
      .finally(() => setLoading(false));
  }, [websiteId, searchParams]);

  useEffect(() => {
    load("traditional");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [websiteId]);

  function handleToggle(next: ModeT) {
    setMode(next);
    load(next);
    setActivePage("home");
  }

  const inquiryRequests = useRef(new Map<string, string>());

  async function handleContactSubmit(pageIndex: number, input: { name: string; email?: string; phone?: string; message?: string }) {
    const payload = { page_key: activePage, section_index: pageIndex, ...input, vehicle_id: inquiryVehicleId || undefined, intent: ["information", "purchase", "test_drive", "financing", "trade"].includes(inquiryIntent) ? inquiryIntent : "information" };
    const key = JSON.stringify([websiteId, payload]);
    const requestId = inquiryRequests.current.get(key) || crypto.randomUUID();
    inquiryRequests.current.set(key, requestId);
    await publicSubmitContactForm(websiteId, { ...payload, request_id: requestId });
    inquiryRequests.current.delete(key);
  }

  if (loading && !site) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white text-zinc-400 text-sm">
        Loading…
      </div>
    );
  }

  if (error || !site) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white text-center px-6">
        <div>
          <div className="text-lg font-semibold text-zinc-800 mb-2">This site isn&apos;t available</div>
          <div className="text-sm text-zinc-500">{error ?? "It may not be published yet."}</div>
        </div>
      </div>
    );
  }

  if ((site.studio_config?.approved_template || site.studio_config?.lone_star) && mode === "traditional") return <><WebsiteVisitorAnalytics site={site}/><LoneStarPublicSite site={site}/></>;

  const oemBanner = site.admin_settings?.branding_mode === "oem";
  const pageSections = site.pages?.[activePage]?.sections ?? [];
  const pageLayoutMode = site.pages?.[activePage]?.layout_mode;

  return (
    <> <WebsiteVisitorAnalytics site={site} page={activePage}/>
    <WebsiteTheme themeId={site.studio_config?.theme_id}><div className={site.studio_config ? "min-h-screen" : "min-h-screen bg-white text-zinc-900"}>
      {activePage === "home" && <WebsiteStudioEvents events={site.studio_events || []} websiteId={websiteId} language={site.studio_config?.language} bannerOnly />}
      <header className="site-header sticky top-0 z-20 bg-white border-b border-zinc-200">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
          <div className="font-bold text-lg truncate">{site.name}</div>

          <nav className="hidden md:flex items-center gap-5 text-sm text-zinc-600">
            {PAGE_KEYS.map((k) => (
              <button
                key={k}
                onClick={() => setActivePage(k)}
                aria-current={activePage === k ? "page" : undefined}
                className={activePage === k ? "text-zinc-900 font-semibold" : "hover:text-zinc-900 transition"}
              >
                {PAGE_LABELS[k]}
              </button>
            ))}
          </nav>

          {site.both_modes_available !== false && (
            <div className="flex items-center gap-1 rounded-full border border-zinc-300 p-0.5 text-xs shrink-0">
              <button
                onClick={() => handleToggle("traditional")}
                className={mode === "traditional" ? "px-3 py-1.5 rounded-full bg-zinc-900 text-white font-medium" : "px-3 py-1.5 rounded-full text-zinc-500 hover:text-zinc-900 transition"}
              >
                Website
              </button>
              <button
                onClick={() => handleToggle("dealer_gpt")}
                className={mode === "dealer_gpt" ? "px-3 py-1.5 rounded-full bg-brand-teal text-black font-medium" : "px-3 py-1.5 rounded-full text-zinc-500 hover:text-zinc-900 transition"}
              >
                ✨ AI Build
              </button>
            </div>
          )}
        </div>

        <nav className="md:hidden flex items-center gap-4 overflow-x-auto px-6 pb-3 text-xs text-zinc-600">
          {PAGE_KEYS.map((k) => (
            <button
              key={k}
              onClick={() => setActivePage(k)}
                aria-current={activePage === k ? "page" : undefined}
              className={activePage === k ? "text-zinc-900 font-semibold whitespace-nowrap" : "whitespace-nowrap"}
            >
              {PAGE_LABELS[k]}
            </button>
          ))}
        </nav>
      </header>

      {oemBanner && site.admin_settings?.oem_name && (
        <div className="bg-zinc-100 border-b border-zinc-200 py-2 text-center text-xs text-zinc-500">
          {site.admin_settings.oem_name}
          {site.admin_settings.branding_mode === "oem" ? " · Independently owned and operated" : ""}
        </div>
      )}

      <main>
        {activePage === "contact" && inquiryVehicleId && <div className="max-w-5xl mx-auto px-6 pt-8" role="status">
          <strong>{inquiryIntent === "purchase" ? "Let's get started" : "Vehicle inquiry"}</strong>
          <p>{inquiryVehicle ? [inquiryVehicle.year, inquiryVehicle.make, inquiryVehicle.model].filter(Boolean).join(" ") : "Your selected vehicle will be checked when you send your request."}</p>
          {inquiryVehicle && !inquiryVehicle.available && <p>This vehicle is no longer available. Our team can discuss alternatives.</p>}
        </div>}
        {loading ? (
          <div className="py-24 text-center text-sm text-zinc-400">Switching view…</div>
        ) : pageSections.length === 0 ? (
          <div className="py-24 text-center text-sm text-zinc-400">Nothing here yet.</div>
        ) : (
          <SitePageRenderer sections={pageSections} onContactSubmit={handleContactSubmit} websiteId={websiteId} layoutMode={pageLayoutMode} themeId={site.studio_config?.theme_id} websiteName={site.name} backgrounds={site.studio_config?.backgrounds} pageKey={activePage} publicInventory={activePage === "inventory"} />
        )}
      </main>
      {activePage === "home" && <WebsiteStudioEvents events={site.studio_events || []} websiteId={websiteId} language={site.studio_config?.language} />}

      <footer className="site-footer bg-zinc-900 text-zinc-400 text-xs text-center py-8">
        <div className="mb-6 flex justify-center"><WebsiteSocialLinks links={site.studio_config?.social_links} /></div>
        © {new Date().getFullYear()} {site.name}. <a href="https://nxtdeal.app" target="_blank" rel="noopener noreferrer">Powered by NXTDeal.</a>
      </footer>

      <PublicChatWidget websiteId={websiteId} siteName={site.name} />
    </div></WebsiteTheme>
    </>
  );
}
