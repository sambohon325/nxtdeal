"use client";

// Real, public, unauthenticated Vehicle Detail Page (session 113 follow-up) --
// closes the "AI-generated location/vehicle pages" item from Website's remaining
// "Wix-level asks" list (CLAUDE.md, flagged open since session 90). Until this page
// existed, a vehicle had no indexable URL of its own anywhere in this codebase --
// the Inventory page's `inventory_grid` section only ever rendered a flat grid list
// (core/websites.py's get_live_inventory(), real but shallow). Now every real unsold
// vehicle in a published site's inventory has its own page here, linked from the
// inventory grid (see SiteSectionRenderer.tsx's VehicleCard) and listed in
// core/website_seo.py's real sitemap.xml.
//
// Same no-NXTDeal-chrome convention as the parent /site/[id] page -- this is meant
// to look like a real independent dealership's own website.
import { useEffect, useState, useCallback } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { publicGetVehiclePage, type VehicleLandingPage } from "@/lib/websites";
import { WebsiteTheme } from "@/components/WebsiteTheme";
import { WebsiteSocialLinks } from "@/components/WebsiteSocialLinks";
import { PublicChatWidget } from "@/components/PublicChatWidget";

function fmtPrice(v: unknown): string {
  const n = typeof v === "number" ? v : Number(v);
  if (!n || Number.isNaN(n)) return "";
  return `$${n.toLocaleString()}`;
}

function fmtMileage(v: unknown): string {
  const n = typeof v === "number" ? v : Number(v);
  if (!n || Number.isNaN(n)) return String(v ?? "");
  return `${n.toLocaleString()} mi`;
}

export default function VehicleDetailPage() {
  const params = useParams();
  const websiteId = String(params?.id ?? "");
  const vehicleId = String(params?.vehicleId ?? "");

  const [vehicle, setVehicle] = useState<VehicleLandingPage | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeImage, setActiveImage] = useState(0);

  const load = useCallback(() => {
    if (!websiteId || !vehicleId) return;
    setLoading(true);
    setError(null);
    publicGetVehiclePage(websiteId, vehicleId)
      .then((v) => {
        setVehicle(v);
        setActiveImage(0);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "This vehicle isn't available."))
      .finally(() => setLoading(false));
  }, [websiteId, vehicleId]);

  useEffect(() => {
    load();
  }, [load]);

  if (loading && !vehicle) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white text-zinc-400 text-sm">
        Loading…
      </div>
    );
  }

  if (error || !vehicle) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-white text-center px-6">
        <div>
          <div className="text-lg font-semibold text-zinc-800 mb-2">This vehicle isn&apos;t available</div>
          <div className="text-sm text-zinc-500 mb-4">{error ?? "It may have sold or the listing may have been removed."}</div>
          <Link href={`/site/${websiteId}?page=inventory`} className="text-sm text-zinc-700 underline">
            ← Back to inventory
          </Link>
        </div>
      </div>
    );
  }

  const title = [vehicle.year, vehicle.make, vehicle.model].filter(Boolean).join(" ");
  const images = vehicle.images ?? [];

  return (
    <WebsiteTheme themeId={vehicle.theme_id}><div className={vehicle.theme_id ? "min-h-screen" : "min-h-screen bg-white text-zinc-900"}>
      <header className="site-header sticky top-0 z-20 bg-white border-b border-zinc-200">
        <div className="max-w-6xl mx-auto px-6 py-3 flex items-center justify-between gap-4">
          <div className="font-bold text-lg truncate">{vehicle.website_name}</div>
          <Link href={`/site/${websiteId}?page=inventory`} className="text-sm text-zinc-600 hover:text-zinc-900 transition">
            ← Back to Inventory
          </Link>
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-6 py-10">
        {!vehicle.available && (
          <div className="mb-6 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-800">
            This vehicle is no longer available -- it may have already sold.
          </div>
        )}

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-10">
          <div>
            <div className="site-gallery-image aspect-[4/3] rounded-lg overflow-hidden bg-zinc-100 flex items-center justify-center text-zinc-300 text-6xl">
              {images.length > 0 ? (
                <img src={images[activeImage]} alt={title} className="w-full h-full object-cover" />
              ) : (
                "🚗"
              )}
            </div>
            {images.length > 1 && (
              <div className="mt-3 grid grid-cols-5 gap-2">
                {images.map((url, i) => (
                  <button
                    key={i}
                    onClick={() => setActiveImage(i)}
                    aria-label={`View vehicle photo ${i + 1}`}
                    aria-pressed={i === activeImage}
                    className={`site-gallery-image aspect-[4/3] rounded overflow-hidden border-2 ${i === activeImage ? "border-zinc-900" : "border-transparent"}`}
                  >
                    <img src={url} alt="" className="w-full h-full object-cover" />
                  </button>
                ))}
              </div>
            )}
          </div>

          <div>
            <h1 className="text-3xl font-bold text-zinc-900">{title || "Vehicle"}</h1>
            {vehicle.trim && <div className="text-lg text-zinc-500 mt-1">{vehicle.trim}</div>}

            {vehicle.price ? (
              <div className="mt-4 text-3xl font-bold text-zinc-900">{fmtPrice(vehicle.price)}</div>
            ) : null}

            {vehicle.location_name && <div className="mt-5 rounded-lg bg-zinc-100 p-4 text-sm text-zinc-800"><strong>{vehicle.location_name}</strong>{vehicle.location_address && <p className="mt-1 text-zinc-600">{vehicle.location_address}</p>}</div>}
            <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
              {vehicle.mileage ? (
                <div>
                  <div className="text-zinc-400">Mileage</div>
                  <div className="font-medium text-zinc-800">{fmtMileage(vehicle.mileage)}</div>
                </div>
              ) : null}
              {vehicle.color ? (
                <div>
                  <div className="text-zinc-400">Exterior Color</div>
                  <div className="font-medium text-zinc-800">{vehicle.color}</div>
                </div>
              ) : null}
              {vehicle.condition ? (
                <div>
                  <div className="text-zinc-400">Condition</div>
                  <div className="font-medium text-zinc-800">{vehicle.condition}</div>
                </div>
              ) : null}
              {vehicle.stock_number ? (
                <div>
                  <div className="text-zinc-400">Stock #</div>
                  <div className="font-medium text-zinc-800">{vehicle.stock_number}</div>
                </div>
              ) : null}
              {vehicle.vin ? (
                <div className="col-span-2">
                  <div className="text-zinc-400">VIN</div>
                  <div className="font-medium text-zinc-800">{vehicle.vin}</div>
                </div>
              ) : null}
            </div>

            {vehicle.description && (
              <div className="mt-8">
                <div className="text-sm font-semibold text-zinc-900 mb-2 flex items-center gap-2">
                  About This Vehicle
                  {vehicle.description_ai_generated && (
                    <span className="text-[10px] font-normal uppercase tracking-wide text-zinc-400 border border-zinc-200 rounded-full px-2 py-0.5">
                      AI-drafted
                    </span>
                  )}
                </div>
                <p className="text-sm text-zinc-600 leading-relaxed whitespace-pre-wrap">{vehicle.description}</p>
              </div>
            )}

            <div className="mt-8 flex flex-wrap gap-3">
              <Link
                href={`/site/${websiteId}?page=contact&vehicle=${encodeURIComponent(vehicleId)}&intent=information`}
                className="inline-block px-6 py-3 rounded-full bg-zinc-900 text-white font-semibold hover:bg-zinc-700 transition"
              >
                More information
              </Link>
              <Link
                href={`/site/${websiteId}?page=contact&vehicle=${encodeURIComponent(vehicleId)}&intent=purchase`}
                className="inline-block px-6 py-3 rounded-full border border-zinc-300 text-zinc-700 font-semibold hover:bg-zinc-50 transition"
              >
                Let’s get started
              </Link>
            </div>
          </div>
        </div>
      </main>

      <footer className="site-footer bg-zinc-900 text-zinc-400 text-xs text-center py-8">
        <div className="mb-6 flex justify-center"><WebsiteSocialLinks links={vehicle.social_links} /></div>
        © {new Date().getFullYear()} {vehicle.website_name}. <a href="https://nxtdeal.app" target="_blank" rel="noopener noreferrer">Powered by NXTDeal.</a>
      </footer>

      <PublicChatWidget websiteId={websiteId} siteName={vehicle.website_name ?? ""} />
    </div></WebsiteTheme>
  );
}
