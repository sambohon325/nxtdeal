"use client";

import { type PublicPersonalSite } from "@/lib/websites";
import { publicHttpsUrl } from "@/lib/personalPageLinks";

export function PersonalPage({ site }: { site: PublicPersonalSite }) {
  const photo = publicHttpsUrl(site.photo_url);
  const calendar = publicHttpsUrl(site.calendar_link);
  const review = publicHttpsUrl(site.review_link);
  const brand = site.branding?.branding_mode === "oem" ? site.branding : null;
  const brandName = typeof brand?.oem_name === "string" ? brand.oem_name.trim() : "";
  const brandLogo = typeof brand?.oem_logo_url === "string" ? publicHttpsUrl(brand.oem_logo_url) : null;
  return <section className="space-y-6 rounded-2xl border border-white/15 bg-white/[0.03] p-6 backdrop-blur-sm">
    {(brandName || brandLogo) && <div aria-label="Dealership website branding" className="flex items-center gap-3 border-b border-white/10 pb-4">
      {brandLogo && <img src={brandLogo} alt={brandName ? `${brandName} logo` : "Dealership website logo"} referrerPolicy="no-referrer" className="h-12 max-w-40 object-contain" />}
      {brandName && <p className="text-sm font-medium text-zinc-200">{brandName}</p>}
    </div>}
    {photo && <img src={photo} alt="Your representative" referrerPolicy="no-referrer" className="h-24 w-24 rounded-full object-cover" />}
    <div>
      <h1 className="text-3xl font-light text-white">{site.headline || site.slug}</h1>
      {site.subheadline && <p className="mt-2 text-lg text-sky-200">{site.subheadline}</p>}
    </div>
    {site.bio && <p className="whitespace-pre-wrap text-zinc-300">{site.bio}</p>}
    <div className="space-y-2 text-sm text-zinc-300">
      {site.phone && <p>Phone: {site.phone}</p>}
      {site.email && <p>Email: {site.email}</p>}
      {calendar && <a href={calendar} target="_blank" rel="noopener noreferrer" className="inline-block rounded-lg border border-sky-300/30 px-4 py-2 text-sky-100">Book a conversation ↗</a>}
    </div>
    {review && <div className="space-y-2 text-sm">
      <a href={review} target="_blank" rel="noopener noreferrer" className="inline-block rounded-lg border border-white/20 px-4 py-2 text-white">Leave a review ↗</a>
      <p className="text-zinc-400">Opens an external review site.</p>
    </div>}
    {site.featured_vehicles.length > 0 && <section aria-label="Featured vehicles" className="space-y-3">
      <h2 className="text-lg text-white">Featured vehicles</h2>
      {site.featured_vehicles.map((vehicle, index) => <article key={String(vehicle.id ?? index)} className="rounded-xl border border-white/10 p-4">
        <h3 className="text-zinc-100">{[vehicle.year, vehicle.make, vehicle.model, vehicle.trim].filter(Boolean).map(String).join(" ")}</h3>
        <p className="mt-1 text-sm text-zinc-400">{typeof vehicle.price === "number" && Number.isFinite(vehicle.price) ? `$${vehicle.price.toLocaleString()}` : "Contact for pricing"}</p>
      </article>)}
    </section>}
  </section>;
}
