"use client";

import { publicWebsiteInventory, type PublicInventoryPage } from "@/lib/websites";
import { mediaImageUrl } from "@/lib/mediaLibrary";
import { SafeHtmlPreview } from "@/components/SafeHtmlPreview";
import { WebsiteSocialLinks } from "./WebsiteSocialLinks";
import { ApprovedWebsiteHero } from "@/components/ApprovedWebsiteHero";

// Real, VISUAL rendering of a WebsiteSection -- built 2026-07-16 (Cowork, interactive)
// as the missing piece behind Sam's "why isn't the traditional/DriveFinder toggle
// coming through" question. The backend (core/websites.py's get_website_rendered())
// has always genuinely computed both variants; what never existed was anything that
// rendered a section as an actual styled page element rather than a raw field-name/
// field-value list. This is that renderer -- shared by the real public visitor page
// (app/site/[id]/page.tsx) and the authenticated Builder tab's live preview
// (components/WebsiteBuilderBoard.tsx), so "what the dealer sees while editing" and
// "what a real visitor sees" are the same rendering code, not two divergent ones.
//
// Deliberately light/neutral styling (NOT NXTDeal's own dark brand-ink chrome) --
// this represents an actual dealership's own public website, which has nothing to do
// with NXTDeal's internal look. OEM branding mode swaps in the OEM's name/logo per
// core/websites.py's oem_branding_banner section.
import { useEffect, useState, type ReactNode, type FocusEvent } from "react";
import Link from "next/link";
import type { WebsiteSection, Website } from "@/lib/websites";
import { DigitalRetailFlow } from "@/components/DigitalRetailFlow";

// Optional inline-edit mode (2026-07-23) -- the Wix/Webflow-style Builder canvas
// (components/WebsiteBuilderCanvas.tsx) renders these exact same section components
// but wants each visible text bit to be directly click-to-edit on the canvas. When an
// `ed` context is threaded in, the renderer emits its text nodes as contentEditable
// elements carrying data-field={key} and reports edits (on blur, only when changed)
// back through onFieldEdit. When `ed` is absent -- every existing caller (the public
// visitor page, the structured-mode live preview, the freeform canvas editor) -- the
// output is byte-for-byte the read-only markup it has always been.
type EditCtx = { editable: boolean; onFieldEdit: (key: string, value: string) => void };

const EDIT_CLS =
  "outline-none rounded-sm cursor-text transition hover:bg-teal-400/5 focus:bg-teal-400/10 focus:ring-2 focus:ring-teal-400";

function ecProps(ed: EditCtx | undefined, field: string, value: string) {
  if (!ed?.editable) return {};
  return {
    "data-field": field,
    contentEditable: true,
    suppressContentEditableWarning: true,
    spellCheck: false,
    onBlur: (e: FocusEvent<HTMLElement>) => {
      const next = (e.currentTarget.innerText ?? "").replace(/\n$/, "");
      if (next !== value) ed.onFieldEdit(field, next);
    },
  };
}

type LiveVehicle = Record<string, unknown>;
type CarBuilderTrim = { trim: string; count: number; price_min: number | null; price_max: number | null };
type CarBuilderModel = { model: string; trims: CarBuilderTrim[] };
type CarBuilderMake = { make: string; models: CarBuilderModel[] };

function fmtPrice(v: unknown): string {
  const n = typeof v === "number" ? v : Number(v);
  if (!n || Number.isNaN(n)) return "";
  return `$${n.toLocaleString()}`;
}

function SectionShell({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <section className={`site-section w-full ${className}`}>{children}</section>;
}

// Raw HTML drop-in (2026-07-23) -- renders the section's `html` field verbatim.
// Edited via the inspector textarea (markup, not inline-editable prose), same trust
// model as the email builder's Custom HTML block.
function CustomHtml({ fields }: { fields: Record<string, unknown> }) {
  const html = String(fields.html ?? "");
  if (!html.trim()) {
    return (
      <SectionShell className="py-10 px-6 bg-zinc-50 text-center text-sm text-zinc-400">
        {"</>"} Paste your HTML in the inspector.
      </SectionShell>
    );
  }
  return <SectionShell className="w-full" ><SafeHtmlPreview html={html} /></SectionShell>;
}

function HeroBanner({ fields, ed }: { fields: Record<string, unknown>; ed?: EditCtx }) {
  const headline = String(fields.headline ?? "");
  const subheadline = String(fields.subheadline ?? "");
  const imageUrl = fields.image_url ? mediaImageUrl(String(fields.image_url)) : "";
  const cta = fields.cta_text ? String(fields.cta_text) : "";

  return (
    <SectionShell>
      <div
        className="relative flex flex-col items-center justify-center text-center px-6 py-24 text-white"
        style={{
          backgroundImage: imageUrl
            ? `linear-gradient(rgba(15,15,20,0.55), rgba(15,15,20,0.55)), url(${imageUrl})`
            : "linear-gradient(135deg, #1f2937, #374151)",
          backgroundSize: "cover",
          backgroundPosition: "center",
        }}
      >
        <h1 {...ecProps(ed, "headline", headline)} className={`text-4xl md:text-5xl font-bold max-w-3xl min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{headline || (ed?.editable ? "" : "Welcome")}</h1>
        {(subheadline || ed?.editable) && (
          <p {...ecProps(ed, "subheadline", subheadline)} className={`mt-4 text-lg text-zinc-200 max-w-2xl min-h-[1.5em] ${ed?.editable ? EDIT_CLS : ""}`}>{subheadline}</p>
        )}
        {(cta || ed?.editable) && (
          <button {...ecProps(ed, "cta_text", cta)} className={`mt-8 px-6 py-3 rounded-full bg-white text-zinc-900 font-semibold hover:bg-zinc-200 transition min-w-[4em] ${ed?.editable ? EDIT_CLS : ""}`}>
            {cta}
          </button>
        )}
      </div>
    </SectionShell>
  );
}

function TextBlock({ fields, ed }: { fields: Record<string, unknown>; ed?: EditCtx }) {
  const heading = fields.heading ? String(fields.heading) : "";
  const body = String(fields.body ?? "");
  return (
    <SectionShell className="py-14 px-6 bg-white">
      <div className="max-w-3xl mx-auto text-center">
        {(heading || ed?.editable) && <h2 {...ecProps(ed, "heading", heading)} className={`text-2xl font-bold text-zinc-900 mb-4 min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>}
        <p {...ecProps(ed, "body", body)} className={`text-zinc-600 leading-relaxed whitespace-pre-wrap min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{body}</p>
      </div>
    </SectionShell>
  );
}

function ImageGallery({ fields }: { fields: Record<string, unknown> }) {
  const urls = String(fields.image_urls ?? "")
    .split(",")
    .map((u) => u.trim())
    .filter(Boolean);
  return (
    <SectionShell className="py-14 px-6 bg-zinc-50">
      <div className="max-w-5xl mx-auto grid grid-cols-2 md:grid-cols-4 gap-3">
        {urls.length === 0 && <div className="col-span-4 text-center text-sm text-zinc-400">No photos added yet.</div>}
        {urls.map((u, i) => (
          <div key={i} className="site-gallery-image aspect-[4/3] rounded-lg overflow-hidden bg-zinc-200">
            <img src={mediaImageUrl(u)} alt="" className="w-full h-full object-cover" />
          </div>
        ))}
      </div>
    </SectionShell>
  );
}

function VehicleCard({ vehicle, websiteId }: { vehicle: LiveVehicle; websiteId?: string }) {
  const year = String(vehicle.Year ?? vehicle.year ?? "");
  const make = String(vehicle.Make ?? vehicle.make ?? "");
  const model = String(vehicle.Model ?? vehicle.model ?? "");
  const trim = vehicle.Trim ?? vehicle.trim ?? "";
  const price = vehicle.Price ?? vehicle.price;
  const image = vehicle.image_url ? String(vehicle.image_url) : "";
  const id = vehicle.id ? String(vehicle.id) : "";

  const card = (
    <div className="site-vehicle-card rounded-lg border border-zinc-200 bg-white overflow-hidden hover:shadow-md transition">
      <div className="aspect-[4/3] bg-zinc-100 flex items-center justify-center text-zinc-300 text-3xl overflow-hidden">
        {image ? <img src={mediaImageUrl(image)} alt={`${year} ${make} ${model}`} className="w-full h-full object-cover" /> : "🚗"}
      </div>
      <div className="p-3">
        <div className="text-sm font-semibold text-zinc-900 truncate">
          {year} {make} {model}
        </div>
        {trim ? <div className="text-xs text-zinc-500 truncate">{String(trim)}</div> : null}
        {price ? <div className="mt-1 text-sm font-bold text-zinc-900">{fmtPrice(price)}</div> : null}
        {vehicle.location_name ? <div className="mt-2 text-xs text-zinc-600">{String(vehicle.location_name)}</div> : null}
      </div>
    </div>
  );

  // Real Vehicle Detail Page link (session 113 follow-up) -- only active on the real
  // public visitor page (which passes websiteId down through SitePageRenderer). The
  // authenticated Builder tab's own live preview renders this same component WITHOUT
  // websiteId, so a card stays a plain inert display card there rather than navigating
  // the whole builder app away when clicked.
  if (websiteId && id) {
    return (
      <Link href={`/site/${websiteId}/vehicle/${id}`} className="block">
        {card}
      </Link>
    );
  }

  return card;
}

function InventoryGrid({ section, websiteId }: { section: WebsiteSection; websiteId?: string }) {
  const vehicles = section.live_vehicles ?? [];
  const [location, setLocation] = useState("");
  const locations = Array.from(new Map(vehicles.filter(v => v.location_id && v.location_name).map(v => [String(v.location_id), String(v.location_name)])).entries());
  const selectedLocation = locations.some(([id]) => id === location) || location === "unassigned" ? location : "";
  const filtered = vehicles.filter(v => !selectedLocation || (selectedLocation === "unassigned" ? !v.location_id : v.location_id === selectedLocation));
  return (
    <SectionShell className="py-14 px-6 bg-white">
      <div className="max-w-6xl mx-auto">
        <h2 className="text-2xl font-bold text-zinc-900 mb-6 text-center">Current Inventory</h2>
        {locations.length > 0 && <div className="flex flex-wrap items-center justify-between gap-3 mb-6">
          <label className="text-sm text-zinc-700">Location
            <select aria-label="Filter inventory by location" value={selectedLocation} onChange={e => setLocation(e.target.value)} className="ml-3 rounded-lg border border-zinc-300 bg-white px-3 py-2 text-zinc-900">
              <option value="">All locations</option>
              {locations.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
              {vehicles.some(v => !v.location_id) && <option value="unassigned">Confirm location with dealer</option>}
            </select>
          </label>
          <span className="text-sm text-zinc-500">{filtered.length} of {vehicles.length} shown vehicles</span>
        </div>}
        {filtered.length === 0 ? (
          <div className="text-center text-sm text-zinc-400">No vehicles match right now -- check back soon.</div>
        ) : (
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            {filtered.map((v, i) => (
              <VehicleCard key={String(v.id || i)} vehicle={v} websiteId={websiteId} />
            ))}
          </div>
        )}
      </div>
    </SectionShell>
  );
}

function PublicInventoryGrid({ section, websiteId }: { section: WebsiteSection; websiteId: string }) {
  const [query, setQuery] = useState("");
  const [location, setLocation] = useState(String(section.fields.location_id || ""));
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<PublicInventoryPage | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(true);
  const [retry, setRetry] = useState(0);
  const make = String(section.fields.make || "");
  const maxPrice = String(section.fields.max_price || "");
  useEffect(() => {
    const controller = new AbortController();
    setBusy(true); setError("");
    const timer = setTimeout(() => {
      const params = new URLSearchParams({ page: String(page), page_size: "12", q: query });
      if (location) params.set("location_id", location);
      if (make) params.set("make", make);
      if (maxPrice) params.set("max_price", maxPrice);
      publicWebsiteInventory(websiteId, params, controller.signal).then(data => {
        if (!controller.signal.aborted) setResult(data);
      }).catch(reason => {
        if (!controller.signal.aborted) setError(reason instanceof Error ? reason.message : "Unable to load inventory.");
      }).finally(() => { if (!controller.signal.aborted) setBusy(false); });
    }, 200);
    return () => { clearTimeout(timer); controller.abort(); };
  }, [websiteId, page, query, location, make, maxPrice, retry]);
  return <SectionShell className="py-14 px-6 bg-white"><div className="max-w-6xl mx-auto">
    <h2 className="text-2xl font-bold text-zinc-900 mb-6 text-center">Current inventory</h2>
    <div className="mb-6 flex flex-wrap items-end gap-4">
      <label className="flex-1 min-w-48 text-sm">Search vehicles<input type="search" aria-label="Search all inventory" value={query} maxLength={100} onChange={event => { setQuery(event.target.value); setPage(1); }} placeholder="Make, model or year" className="mt-2 block w-full rounded-lg border px-3 py-2" /></label>
      <label className="text-sm">Location<select aria-label="Filter all inventory by location" value={location} onChange={event => { setLocation(event.target.value); setPage(1); }} className="mt-2 block rounded-lg border px-3 py-2">
        <option value="">All locations</option>
        {result?.locations.map(item => <option key={item.id} value={item.id}>{item.name} ({item.count})</option>)}
        {location && !result?.locations.some(item => item.id === location) && <option value={location}>Selected location</option>}
      </select></label>
      <button className="rounded-lg border px-4 py-2" onClick={() => { setQuery(""); setLocation(""); setPage(1); }}>Reset filters</button>
    </div>
    <p aria-live="polite" className="mb-4 text-sm text-zinc-500">{busy ? "Finding available vehicles…" : error ? "" : `${result?.total || 0} available vehicles`}</p>
    {error ? <div role="alert">{error} <button onClick={() => setRetry(value => value + 1)}>Try again</button></div> : <>
      <div aria-busy={busy} className="grid grid-cols-2 md:grid-cols-4 gap-4" style={{ opacity: busy ? .5 : 1 }}>
        {(result?.vehicles || []).map(vehicle => <VehicleCard key={String(vehicle.id)} vehicle={vehicle} websiteId={websiteId} />)}
      </div>
      {!busy && !result?.vehicles.length && <p className="py-8 text-center">No vehicles match these filters. Try another location or search.</p>}
      {result && result.pages > 1 && <nav aria-label="Inventory pages" className="mt-6 flex items-center justify-center gap-4">
        <button className="rounded-lg border px-4 py-2" disabled={busy || result.page <= 1} onClick={() => setPage(result.page - 1)}>Previous</button>
        <span>Page {result.page} of {result.pages}</span>
        <button className="rounded-lg border px-4 py-2" disabled={busy || result.page >= result.pages} onClick={() => setPage(result.page + 1)}>Next</button>
      </nav>}
    </>}
  </div></SectionShell>;
}

function ContactForm({
  fields,
  socialLinks,
  onSubmit,
  ed,
}: {
  fields: Record<string, unknown>;
  socialLinks?: Record<string, string>;
  onSubmit?: (input: { name: string; email?: string; phone?: string; message?: string }) => Promise<void>;
  ed?: EditCtx;
}) {
  const heading = fields.heading ? String(fields.heading) : "Contact Us";
  const phone = fields.phone ? String(fields.phone) : "";
  const address = fields.address ? String(fields.address) : "";

  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [msgPhone, setMsgPhone] = useState("");
  const [message, setMessage] = useState("");
  const [sent, setSent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [submitError, setSubmitError] = useState("");

  async function handleSubmit() {
    if (!onSubmit || busy || !name.trim() || !(email.trim() || msgPhone.trim())) return;
    setBusy(true);
    setSubmitError("");
    try {
      await onSubmit({ name: name.trim(), email: email.trim() || undefined, phone: msgPhone.trim() || undefined, message: message.trim() || undefined });
      setSent(true);
    } catch (error) {
      setSubmitError(error instanceof Error ? error.message : "Your request could not be sent. Please try again.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <SectionShell className="py-14 px-6 bg-zinc-50">
      <div className="max-w-5xl mx-auto">
        <h2 {...ecProps(ed, "heading", heading)} className={`text-2xl font-bold text-zinc-900 mb-2 text-center ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>
        <div className="text-center text-sm text-zinc-500 mb-6">
          {phone && <span className="mr-4">📞 {phone}</span>}
          {address && <span>📍 {address}</span>}
        </div>

        <div className={socialLinks && Object.values(socialLinks).some(Boolean) ? "grid gap-8 md:grid-cols-[.65fr_1fr]" : "max-w-2xl mx-auto"}>
        {socialLinks && Object.values(socialLinks).some(Boolean) && <div className="order-2 md:order-1"><WebsiteSocialLinks links={socialLinks} /></div>}
        <div className="order-1 md:order-2">
        {sent ? (
          <div className="text-center text-sm text-green-700 bg-green-50 border border-green-200 rounded-lg p-4">
            Thanks -- someone from our team will reach out shortly.
          </div>
        ) : (
          <form className="space-y-3" onSubmit={event => { event.preventDefault(); void handleSubmit(); }}>
            <input aria-label="Your name" required autoComplete="name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" className="w-full h-10 px-3 rounded border border-zinc-300 text-sm" />
            <input aria-label="Email" type="email" autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" className="w-full h-10 px-3 rounded border border-zinc-300 text-sm" />
            <input aria-label="Phone" type="tel" autoComplete="tel" value={msgPhone} onChange={(e) => setMsgPhone(e.target.value)} placeholder="Phone" className="w-full h-10 px-3 rounded border border-zinc-300 text-sm" />
            <textarea aria-label="Questions or message" value={message} onChange={(e) => setMessage(e.target.value)} placeholder="How can we help?" rows={3} className="w-full px-3 py-2 rounded border border-zinc-300 text-sm resize-none" />
            <p className="text-xs text-zinc-500">Please include an email address or phone number so we can reply.</p>
            {submitError && <p role="alert" className="text-sm text-red-600">{submitError}</p>}
            <button
              type="submit"
              disabled={busy || !name.trim() || !(email.trim() || msgPhone.trim()) || !onSubmit}
              className="w-full h-10 rounded bg-zinc-900 text-white text-sm font-semibold hover:bg-zinc-700 transition disabled:opacity-40"
            >
              {busy ? "Sending…" : "Send request"}
            </button>
          </form>
        )}
        </div></div>
      </div>
    </SectionShell>
  );
}

function TestimonialsCarousel({ fields, ed }: { fields: Record<string, unknown>; ed?: EditCtx }) {
  const heading = fields.heading ? String(fields.heading) : "What Our Customers Say";
  const lines = String(fields.testimonials ?? "")
    .split("\n")
    .map((l) => l.trim())
    .filter(Boolean);

  return (
    <SectionShell className="py-14 px-6 bg-white">
      <div className="max-w-5xl mx-auto">
        <h2 {...ecProps(ed, "heading", heading)} className={`text-2xl font-bold text-zinc-900 mb-6 text-center ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {lines.map((line, i) => {
            const [n, q] = line.split("|").map((s) => s.trim());
            return (
              <div key={i} className="rounded-lg border border-zinc-200 p-4 bg-zinc-50">
                <div className="text-zinc-500 text-lg mb-2">&ldquo;</div>
                <p className="text-sm text-zinc-700 italic">{q || line}</p>
                {n && <div className="mt-3 text-xs font-semibold text-zinc-900">— {n}</div>}
              </div>
            );
          })}
          {lines.length === 0 && <div className="text-center text-sm text-zinc-400 col-span-3">No testimonials yet.</div>}
        </div>
      </div>
    </SectionShell>
  );
}

function GoogleRatingBadge({ fields, ed }: { fields: Record<string, unknown>; ed?: EditCtx }) {
  const ratingText = String(fields.rating_text ?? "");
  return (
    <SectionShell className="py-8 px-6 bg-zinc-50 text-center">
      <div className="inline-flex items-center gap-2 rounded-full bg-white border border-zinc-200 px-5 py-2 shadow-sm">
        <span className="text-amber-500">★★★★★</span>
        <span {...ecProps(ed, "rating_text", ratingText)} className={`text-sm font-medium text-zinc-700 min-w-[2em] ${ed?.editable ? EDIT_CLS : ""}`}>{ratingText}</span>
      </div>
    </SectionShell>
  );
}

function SocialLinks({ fields }: { fields: Record<string, unknown> }) {
  const links: { label: string; url?: string }[] = [
    { label: "Facebook", url: fields.facebook_url ? String(fields.facebook_url) : undefined },
    { label: "Instagram", url: fields.instagram_url ? String(fields.instagram_url) : undefined },
    { label: "TikTok", url: fields.tiktok_url ? String(fields.tiktok_url) : undefined },
    { label: "X", url: fields.x_url ? String(fields.x_url) : undefined },
  ].filter((l) => l.url);

  if (links.length === 0) return null;

  return (
    <SectionShell className="py-6 px-6 bg-white text-center">
      <div className="flex items-center justify-center gap-4 text-sm">
        {links.map((l) => (
          <a key={l.label} href={l.url} target="_blank" rel="noreferrer" className="text-zinc-600 hover:text-zinc-900 underline">
            {l.label}
          </a>
        ))}
      </div>
    </SectionShell>
  );
}

function FinancingInfo({ fields, ed }: { fields: Record<string, unknown>; ed?: EditCtx }) {
  const heading = fields.heading ? String(fields.heading) : "Get Pre-Approved";
  const body = String(fields.body ?? "");
  const applyUrl = fields.apply_url ? String(fields.apply_url) : "";
  return (
    <SectionShell className="py-14 px-6 bg-zinc-900 text-white">
      <div className="max-w-2xl mx-auto text-center">
        <h2 {...ecProps(ed, "heading", heading)} className={`text-2xl font-bold mb-3 ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>
        <p {...ecProps(ed, "body", body)} className={`text-zinc-300 mb-6 whitespace-pre-wrap min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{body}</p>
        {applyUrl && (
          <a href={applyUrl} target="_blank" rel="noreferrer" className="inline-block px-6 py-3 rounded-full bg-white text-zinc-900 font-semibold hover:bg-zinc-200 transition">
            Apply Now
          </a>
        )}
      </div>
    </SectionShell>
  );
}

function OemBrandingBanner({ fields, ed }: { fields: Record<string, unknown>; ed?: EditCtx }) {
  const oemName = String(fields.oem_name ?? "");
  const logoUrl = fields.oem_logo_url ? String(fields.oem_logo_url) : "";
  const disclaimer = fields.disclaimer ? String(fields.disclaimer) : "";
  return (
    <SectionShell className="py-4 px-6 bg-zinc-100 border-y border-zinc-200">
      <div className="max-w-5xl mx-auto flex items-center justify-center gap-3 text-sm text-zinc-600">
        {logoUrl && <img src={mediaImageUrl(logoUrl)} alt={oemName} className="h-6" />}
        <span {...ecProps(ed, "oem_name", oemName)} className={`font-medium text-zinc-800 min-w-[2em] ${ed?.editable ? EDIT_CLS : ""}`}>{oemName}</span>
        {(disclaimer || ed?.editable) && (
          <span className="text-xs text-zinc-400">
            · <span {...ecProps(ed, "disclaimer", disclaimer)} className={ed?.editable ? EDIT_CLS : ""}>{disclaimer}</span>
          </span>
        )}
      </div>
    </SectionShell>
  );
}

function CarBuilder({ fields, section, ed }: { fields: Record<string, unknown>; section: WebsiteSection; ed?: EditCtx }) {
  const heading = fields.heading ? String(fields.heading) : "Build Your Car";
  const introText = fields.intro_text ? String(fields.intro_text) : "";
  const options = (section.live_options ?? []) as unknown as CarBuilderMake[];

  const [make, setMake] = useState<string | null>(null);
  const [model, setModel] = useState<string | null>(null);

  const selectedMake = options.find((m) => m.make === make);
  const selectedModel = selectedMake?.models.find((m) => m.model === model);

  return (
    <SectionShell className="py-16 px-6 bg-gradient-to-b from-zinc-900 to-zinc-800 text-white min-h-[70vh]">
      <div className="max-w-4xl mx-auto text-center">
        <div className="inline-block text-[11px] uppercase tracking-[0.3em] text-brand-teal mb-3">AI-Powered Configurator</div>
        <h2 {...ecProps(ed, "heading", heading)} className={`text-3xl font-bold mb-2 ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>
        {(introText || ed?.editable) && <p {...ecProps(ed, "intro_text", introText)} className={`text-zinc-300 mb-8 max-w-xl mx-auto min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{introText}</p>}

        {options.length === 0 ? (
          <div className="text-sm text-zinc-400">No inventory available to configure right now.</div>
        ) : (
          <div className="space-y-6">
            {!make && (
              <div>
                <div className="text-sm text-zinc-400 mb-3">Step 1 — Choose a Make</div>
                <div className="flex flex-wrap justify-center gap-2">
                  {options.map((m) => (
                    <button key={m.make} onClick={() => setMake(m.make)} className="px-4 py-2 rounded-full bg-white/10 hover:bg-white/20 border border-white/20 text-sm transition">
                      {m.make}
                    </button>
                  ))}
                </div>
              </div>
            )}

            {make && !model && selectedMake && (
              <div>
                <div className="text-sm text-zinc-400 mb-3">Step 2 — Choose a Model</div>
                <div className="flex flex-wrap justify-center gap-2">
                  {selectedMake.models.map((m) => (
                    <button key={m.model} onClick={() => setModel(m.model)} className="px-4 py-2 rounded-full bg-white/10 hover:bg-white/20 border border-white/20 text-sm transition">
                      {m.model}
                    </button>
                  ))}
                </div>
                <button onClick={() => setMake(null)} className="mt-4 text-xs text-zinc-500 hover:text-white">← Back</button>
              </div>
            )}

            {make && model && selectedModel && (
              <div>
                <div className="text-sm text-zinc-400 mb-3">Step 3 — Choose a Trim</div>
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 max-w-2xl mx-auto">
                  {selectedModel.trims.map((t) => (
                    <div key={t.trim} className="rounded-lg border border-white/20 bg-white/5 p-4 text-left">
                      <div className="font-semibold">{t.trim}</div>
                      <div className="text-xs text-zinc-400 mt-1">{t.count} available</div>
                      {t.price_min && (
                        <div className="text-sm font-bold mt-2">
                          {fmtPrice(t.price_min)}
                          {t.price_max && t.price_max !== t.price_min ? ` – ${fmtPrice(t.price_max)}` : ""}
                        </div>
                      )}
                    </div>
                  ))}
                </div>
                <button onClick={() => setModel(null)} className="mt-4 text-xs text-zinc-500 hover:text-white">← Back</button>
              </div>
            )}
          </div>
        )}
      </div>
    </SectionShell>
  );
}

// ---------------------------------------------------------------------------
// Digital Retail widgets (2026-07-24, DR-5) -- the customer-facing self-service
// surface. Backend catalog + render resolution live in core/websites.py; these are
// the presentational renderers (shared by the public page and the builder preview).
// ---------------------------------------------------------------------------

// Ask NXTDeal -- AI shopping-assistant entry, grounded on a live inventory sample.
function AskDealeros({ fields, section, ed }: { fields: Record<string, unknown>; section: WebsiteSection; ed?: EditCtx }) {
  const heading = fields.heading ? String(fields.heading) : "Ask NXTDeal";
  const intro = fields.intro_text ? String(fields.intro_text) : "";
  const placeholder = fields.placeholder ? String(fields.placeholder) : "Ask about any vehicle, payment, or your trade...";
  const sample = (section.live_vehicles ?? []) as LiveVehicle[];
  const chips = sample
    .map((v) => [v.Year, v.Make, v.Model].filter(Boolean).join(" "))
    .filter(Boolean)
    .slice(0, 4);

  return (
    <SectionShell className="py-16 px-6 bg-gradient-to-b from-zinc-900 to-zinc-800 text-white">
      <div className="max-w-2xl mx-auto text-center">
        <div className="inline-block text-[11px] uppercase tracking-[0.3em] text-brand-teal mb-3">AI Shopping Assistant</div>
        <h2 {...ecProps(ed, "heading", heading)} className={`text-3xl font-bold mb-2 ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>
        {(intro || ed?.editable) && <p {...ecProps(ed, "intro_text", intro)} className={`text-zinc-300 mb-6 min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{intro}</p>}
        <div className="flex items-center gap-2 rounded-full bg-white/10 border border-white/20 px-4 py-3">
          <span className="text-brand-teal">✦</span>
          <input disabled className="flex-1 bg-transparent text-sm text-white placeholder-zinc-400 outline-none" placeholder={placeholder} />
          <button className="px-4 py-1.5 rounded-full bg-white text-zinc-900 text-sm font-semibold">Ask</button>
        </div>
        {chips.length > 0 && (
          <div className="mt-4 flex flex-wrap justify-center gap-2">
            {chips.map((c, i) => (
              <span key={i} className="px-3 py-1 rounded-full bg-white/5 border border-white/10 text-xs text-zinc-300">{c}</span>
            ))}
          </div>
        )}
      </div>
    </SectionShell>
  );
}

// Payment Builder -- pick a live vehicle, adjust down/term, see the monthly update in
// real time (client-side amortization against the dealer's assumed APR).
function PaymentBuilder({ fields, section, ed }: { fields: Record<string, unknown>; section: WebsiteSection; ed?: EditCtx }) {
  const heading = fields.heading ? String(fields.heading) : "Estimate Your Payment";
  const disclaimer = fields.disclaimer ? String(fields.disclaimer) : "";
  const options = (section.live_options ?? []) as unknown as CarBuilderMake[];
  const cfg = section.payment_config ?? { default_down: 3000, default_term_months: 60, assumed_apr: 6.9 };

  const prices = options.flatMap((mk) => mk.models.flatMap((md) => md.trims.map((t) => t.price_min ?? 0))).filter((p) => p > 0);
  const defaultPrice = prices.length ? Math.round(prices.reduce((a, b) => a + b, 0) / prices.length) : 30000;

  const [price, setPrice] = useState<number>(defaultPrice);
  const [down, setDown] = useState<number>(cfg.default_down);
  const [term, setTerm] = useState<number>(cfg.default_term_months);

  const principal = Math.max(0, price - down);
  const r = cfg.assumed_apr / 100 / 12;
  const monthly = r === 0 ? principal / term : (principal * r * Math.pow(1 + r, term)) / (Math.pow(1 + r, term) - 1);

  return (
    <SectionShell className="py-16 px-6 bg-white">
      <div className="max-w-xl mx-auto">
        <div className="text-center mb-6">
          <div className="inline-block text-[11px] uppercase tracking-[0.3em] text-brand-teal mb-2">Payment Builder</div>
          <h2 {...ecProps(ed, "heading", heading)} className={`text-3xl font-bold text-zinc-900 ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>
        </div>
        <div className="rounded-2xl border border-zinc-200 bg-zinc-50 p-6">
          <div className="text-center mb-6">
            <div className="text-4xl font-bold text-zinc-900">${monthly.toFixed(0)}<span className="text-base font-normal text-zinc-500">/mo</span></div>
            <div className="text-xs text-zinc-500 mt-1">{cfg.assumed_apr}% APR · {term} months · ${principal.toLocaleString()} financed</div>
          </div>
          <label className="block text-xs font-medium text-zinc-600 mb-1">Vehicle Price: ${price.toLocaleString()}</label>
          <input type="range" min={5000} max={100000} step={500} value={price} onChange={(e) => setPrice(Number(e.target.value))} className="w-full mb-4" />
          <label className="block text-xs font-medium text-zinc-600 mb-1">Down Payment: ${down.toLocaleString()}</label>
          <input type="range" min={0} max={Math.max(down, price)} step={250} value={down} onChange={(e) => setDown(Number(e.target.value))} className="w-full mb-4" />
          <label className="block text-xs font-medium text-zinc-600 mb-1">Term: {term} months</label>
          <input type="range" min={12} max={84} step={12} value={term} onChange={(e) => setTerm(Number(e.target.value))} className="w-full" />
        </div>
        {(disclaimer || ed?.editable) && <p {...ecProps(ed, "disclaimer", disclaimer)} className={`mt-3 text-center text-[11px] text-zinc-400 min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{disclaimer}</p>}
      </div>
    </SectionShell>
  );
}

// Trade Evaluation -- VIN/mileage/condition intake (presentational; posts to the
// Digital Retail trade flow on a live site).
function TradeEvaluation({ fields, ed }: { fields: Record<string, unknown>; ed?: EditCtx }) {
  const heading = fields.heading ? String(fields.heading) : "Value Your Trade";
  const intro = fields.intro_text ? String(fields.intro_text) : "";
  const disclaimer = fields.disclaimer ? String(fields.disclaimer) : "";
  const input = "w-full rounded-md border border-zinc-300 px-3 py-2 text-sm";
  return (
    <SectionShell className="py-16 px-6 bg-zinc-50">
      <div className="max-w-lg mx-auto">
        <div className="text-center mb-6">
          <div className="inline-block text-[11px] uppercase tracking-[0.3em] text-brand-teal mb-2">Trade Evaluation</div>
          <h2 {...ecProps(ed, "heading", heading)} className={`text-3xl font-bold text-zinc-900 ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>
          {(intro || ed?.editable) && <p {...ecProps(ed, "intro_text", intro)} className={`text-zinc-500 mt-2 min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{intro}</p>}
        </div>
        <div className="space-y-3 rounded-2xl border border-zinc-200 bg-white p-6">
          <input disabled className={input} placeholder="VIN" />
          <input disabled className={input} placeholder="Mileage" />
          <select disabled className={input}><option>Condition — Excellent / Good / Fair</option></select>
          <button className="w-full rounded-full bg-zinc-900 text-white py-2.5 text-sm font-semibold">Get My Trade Estimate</button>
        </div>
        {(disclaimer || ed?.editable) && <p {...ecProps(ed, "disclaimer", disclaimer)} className={`mt-3 text-center text-[11px] text-zinc-400 min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{disclaimer}</p>}
      </div>
    </SectionShell>
  );
}

// Buy Online -- the self-service entry point; the dealer-set level names how far the
// customer can go. On the LIVE public site (websiteId present, not the builder editor) the CTA
// launches the real Verify journey (DigitalRetailFlow -> /public/verify/*); in the builder
// preview it stays an inert mockup.
function BuyOnline({ fields, section, ed, websiteId }: { fields: Record<string, unknown>; section: WebsiteSection; ed?: EditCtx; websiteId?: string }) {
  const heading = fields.heading ? String(fields.heading) : "Buy Online";
  const cta = fields.cta_text ? String(fields.cta_text) : "Start Buying Online";
  const disclaimer = fields.disclaimer ? String(fields.disclaimer) : "";
  const level = section.buy_online_level ?? "build";
  const [flowOpen, setFlowOpen] = useState(false);
  const live = Boolean(websiteId) && !ed?.editable;
  const LEVELS: { key: string; label: string; blurb: string }[] = [
    { key: "browse", label: "Browse", blurb: "Explore inventory" },
    { key: "build", label: "Build a Deal", blurb: "Structure your terms" },
    { key: "negotiate", label: "Negotiate", blurb: "Work your price & payment" },
    { key: "purchase", label: "Purchase Online", blurb: "Complete the whole deal" },
  ];
  const activeIdx = LEVELS.findIndex((l) => l.key === level);
  return (
    <SectionShell className="py-16 px-6 bg-gradient-to-br from-zinc-900 to-zinc-700 text-white">
      <div className="max-w-3xl mx-auto text-center">
        <div className="inline-block text-[11px] uppercase tracking-[0.3em] text-brand-teal mb-3">Digital Retail</div>
        <h2 {...ecProps(ed, "heading", heading)} className={`text-3xl font-bold mb-6 ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>
        <div className="flex flex-wrap justify-center gap-2 mb-8">
          {LEVELS.map((l, i) => (
            <div key={l.key} className={`rounded-lg border px-4 py-3 text-left ${i <= activeIdx ? "border-brand-teal bg-white/10" : "border-white/10 bg-white/5 opacity-50"}`}>
              <div className="text-sm font-semibold">{l.label}</div>
              <div className="text-[11px] text-zinc-300">{l.blurb}</div>
            </div>
          ))}
        </div>
        <button
          {...ecProps(ed, "cta_text", cta)}
          onClick={live ? () => setFlowOpen(true) : undefined}
          className={`px-8 py-3 rounded-full bg-white text-zinc-900 font-semibold ${ed?.editable ? EDIT_CLS : ""}`}
        >
          {cta}
        </button>
        {(disclaimer || ed?.editable) && <p {...ecProps(ed, "disclaimer", disclaimer)} className={`mt-4 text-[11px] text-zinc-400 min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{disclaimer}</p>}
      </div>
      {live && <DigitalRetailFlow open={flowOpen} onClose={() => setFlowOpen(false)} />}
    </SectionShell>
  );
}

// Delivery Scheduling -- store pickup / home delivery / try-before-you-buy, each
// dealer-toggleable.
function DeliveryScheduling({ fields, section, ed }: { fields: Record<string, unknown>; section: WebsiteSection; ed?: EditCtx }) {
  const heading = fields.heading ? String(fields.heading) : "Schedule Your Delivery";
  const disclaimer = fields.disclaimer ? String(fields.disclaimer) : "";
  const opts = section.delivery_options ?? { store_pickup: true, home_delivery: true, try_before_you_buy: false, radius_miles: 50 };
  const cards: { on: boolean; label: string; blurb: string }[] = [
    { on: opts.store_pickup, label: "Store Pickup", blurb: "Pick up at the dealership" },
    { on: opts.home_delivery, label: "Home Delivery", blurb: `Delivered within ${opts.radius_miles} miles` },
    { on: opts.try_before_you_buy, label: "Try Before You Buy", blurb: "Test it before you commit" },
  ].filter((c) => c.on);
  return (
    <SectionShell className="py-16 px-6 bg-white">
      <div className="max-w-3xl mx-auto text-center">
        <div className="inline-block text-[11px] uppercase tracking-[0.3em] text-brand-teal mb-2">Delivery</div>
        <h2 {...ecProps(ed, "heading", heading)} className={`text-3xl font-bold text-zinc-900 mb-8 ${ed?.editable ? EDIT_CLS : ""}`}>{heading}</h2>
        {cards.length === 0 ? (
          <div className="text-sm text-zinc-400">No delivery options are enabled.</div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {cards.map((c) => (
              <div key={c.label} className="rounded-xl border border-zinc-200 bg-zinc-50 p-6">
                <div className="font-semibold text-zinc-900">{c.label}</div>
                <div className="text-xs text-zinc-500 mt-1">{c.blurb}</div>
                <button className="mt-4 w-full rounded-full bg-zinc-900 text-white py-2 text-xs font-semibold">Choose</button>
              </div>
            ))}
          </div>
        )}
        {(disclaimer || ed?.editable) && <p {...ecProps(ed, "disclaimer", disclaimer)} className={`mt-4 text-[11px] text-zinc-400 min-h-[1em] ${ed?.editable ? EDIT_CLS : ""}`}>{disclaimer}</p>}
      </div>
    </SectionShell>
  );
}

export function SiteSectionRenderer({
  section,
  onContactSubmit,
  websiteId,
  editable,
  onFieldEdit,
  themeId,
  websiteName,
  publicInventory,
}: {
  section: WebsiteSection;
  onContactSubmit?: (input: { name: string; email?: string; phone?: string; message?: string }) => Promise<void>;
  websiteId?: string;
  // Optional inline-edit mode -- see EditCtx note at the top of this file. Defaults to
  // undefined, so every existing caller keeps the read-only rendering unchanged.
  editable?: boolean;
  onFieldEdit?: (fieldKey: string, value: string) => void;
  themeId?: string;
  websiteName?: string;
  publicInventory?: boolean;
}) {
  const fields = section.fields || {};
  const ed: EditCtx | undefined = editable ? { editable: true, onFieldEdit: onFieldEdit ?? (() => {}) } : undefined;

  switch (section.section_key) {
    case "hero_banner":
      if (themeId) return <ApprovedWebsiteHero themeId={themeId} fields={fields} websiteId={websiteId} websiteName={websiteName} editable={editable} onFieldEdit={onFieldEdit} />;
      return <HeroBanner fields={fields} ed={ed} />;
    case "text_block":
      return <TextBlock fields={fields} ed={ed} />;
    case "image_gallery":
      return <ImageGallery fields={fields} />;
    case "inventory_grid":
      return publicInventory && websiteId ? <PublicInventoryGrid section={section} websiteId={websiteId} /> : <InventoryGrid section={section} websiteId={websiteId} />;
    case "contact_form":
      return <ContactForm fields={fields} socialLinks={section.social_links} onSubmit={onContactSubmit} ed={ed} />;
    case "testimonials_carousel":
      return <TestimonialsCarousel fields={fields} ed={ed} />;
    case "google_rating_badge":
      return <GoogleRatingBadge fields={fields} ed={ed} />;
    case "social_links":
      return <SocialLinks fields={fields} />;
    case "financing_info":
      return <FinancingInfo fields={fields} ed={ed} />;
    case "oem_branding_banner":
      return <OemBrandingBanner fields={fields} ed={ed} />;
    case "car_builder":
      return <CarBuilder fields={fields} section={section} ed={ed} />;
    case "custom_html":
      return <CustomHtml fields={fields} />;
    case "ask_dealeros":
      return <AskDealeros fields={fields} section={section} ed={ed} />;
    case "payment_builder":
      return <PaymentBuilder fields={fields} section={section} ed={ed} />;
    case "trade_evaluation":
      return <TradeEvaluation fields={fields} ed={ed} />;
    case "buy_online":
      return <BuyOnline fields={fields} section={section} ed={ed} websiteId={websiteId} />;
    case "delivery_scheduling":
      return <DeliveryScheduling fields={fields} section={section} ed={ed} />;
    default:
      return (
        <SectionShell className="py-8 px-6 bg-zinc-50 text-center text-xs text-zinc-400">
          Unknown section type: {section.section_key}
        </SectionShell>
      );
  }
}

// Freeform drag-and-drop canvas (2026-07-18) -- keep in sync with the virtual
// canvas width backend/core/websites.py's CANVAS_WIDTH and lib/websites.ts's
// CANVAS_WIDTH constant both use. A real visitor's page is genuinely responsive,
// not a fixed-width scaled screenshot the way the authenticated builder's editor
// (components/WebsiteCanvasEditor.tsx) renders it: horizontal position/width scale
// fluidly as a percentage of the real viewport width, while vertical position/
// height stay the real, absolute pixel values a section was actually authored at
// (a "this many pixels tall" section stays that tall regardless of screen width,
// same as how Wix/Webflow-style freeform canvases behave).
const SITE_CANVAS_WIDTH = 1200;

function CanvasPageBody({
  sections,
  onContactSubmit,
  websiteId,
  themeId,
  websiteName,
}: {
  sections: WebsiteSection[];
  onContactSubmit?: (pageIndex: number, input: { name: string; email?: string; phone?: string; message?: string }) => Promise<void>;
  websiteId?: string;
  themeId?: string;
  websiteName?: string;
}) {
  const minHeight =
    40 +
    sections.reduce((max, s) => {
      const l = s.layout;
      return l ? Math.max(max, l.y + l.height) : max;
    }, 400);

  return (
    <div className="relative w-full" style={{ minHeight }}>
      {sections.map((s, i) => {
        const l = s.layout || { x: 0, y: 0, width: SITE_CANVAS_WIDTH, height: 320 };
        return (
          <div
            key={i}
            className="absolute overflow-hidden"
            style={{
              left: `${(l.x / SITE_CANVAS_WIDTH) * 100}%`,
              width: `${(l.width / SITE_CANVAS_WIDTH) * 100}%`,
              top: l.y,
              height: l.height,
            }}
          >
            <SiteSectionRenderer
              section={s}
              onContactSubmit={onContactSubmit ? (input) => onContactSubmit(i, input) : undefined}
              websiteId={websiteId}
              themeId={themeId}
              websiteName={websiteName}
            />
          </div>
        );
      })}
    </div>
  );
}

export function SitePageRenderer({
  sections,
  onContactSubmit,
  websiteId,
  layoutMode,
  themeId,
  websiteName,
  backgrounds,
  pageKey,
  publicInventory,
}: {
  sections: WebsiteSection[];
  onContactSubmit?: (pageIndex: number, input: { name: string; email?: string; phone?: string; message?: string }) => Promise<void>;
  websiteId?: string;
  layoutMode?: "structured" | "canvas";
  themeId?: string;
  websiteName?: string;
  backgrounds?: Record<string, string>;
  pageKey?: string;
  publicInventory?: boolean;
}) {
  if (layoutMode === "canvas") {
    return <CanvasPageBody sections={sections} onContactSubmit={onContactSubmit} websiteId={websiteId} themeId={themeId} websiteName={websiteName} />;
  }

  return (
    <div>
      {sections.map((s, i) => {
        const key = s.section_key === "contact_form" ? "contact" : s.section_key === "financing_info" ? "financing" : s.section_key === "trade_evaluation" ? "trade" : pageKey === "about" && i === 0 ? "about" : "";
        const photo = key ? backgrounds?.[key] : "";
        return <div key={i}>
        {photo && <div className="mx-auto my-8 max-w-6xl px-6"><img src={mediaImageUrl(photo)} alt="" loading="lazy" className="w-full rounded-2xl object-cover" style={{ height: "clamp(180px, 28vw, 360px)" }} /></div>}
        <SiteSectionRenderer
          key={i}
          section={s}
          onContactSubmit={onContactSubmit ? (input) => onContactSubmit(i, input) : undefined}
          websiteId={websiteId}
          publicInventory={publicInventory}
          themeId={themeId}
          websiteName={websiteName}
        />
        </div>;
      })}
    </div>
  );
}

export type { Website };
