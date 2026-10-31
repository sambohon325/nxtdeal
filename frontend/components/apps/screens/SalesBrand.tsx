"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { createPersonalSite, getMyPersonalSite, getPersonalSite, setPersonalSiteStatus, updatePersonalSite, type PersonalSite, type PersonalSiteRendered } from "@/lib/websites";
import { PersonalPage } from "@/components/PersonalPage";
import { WiredScreen } from "./kit";
import { FeaturedVehiclePicker } from "./FeaturedVehiclePicker";
import { ParentWebsitePicker } from "./ParentWebsitePicker";
import { PersonalPageShare } from "./PersonalPageShare";
import { setPersonalSiteParent } from "@/lib/websites";

const fields = ["headline", "subheadline", "bio", "phone", "email", "cta_text", "photo_url", "calendar_link", "review_link"] as const;
const labels = ["Headline", "Subheadline", "Bio", "Phone", "Email", "Contact button text", "Photo URL (HTTPS)", "Booking URL (HTTPS)", "Review URL (HTTPS, optional)"];

export function SalesBrand({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const [site, setSite] = useState<PersonalSite | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [slug, setSlug] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [dirty, setDirty] = useState(false);
  const [confirmStatus, setConfirmStatus] = useState(false);
  const [preview, setPreview] = useState<PersonalSiteRendered | null>(null);
  const lock = useRef(false);

  useEffect(() => {
    let alive = true;
    setLoading(true); setLoadError(null);
    getMyPersonalSite().then(value => { if (alive) { setSite(value); setDirty(false); setConfirmStatus(false); setPreview(null); setMessage(null); setFailed(false); } })
      .catch(() => { if (alive) setLoadError("Unable to load your page."); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [retry]);

  async function save(event: FormEvent) {
    event.preventDefault();
    if (lock.current) return;
    lock.current = true; setBusy(true); setMessage(null); setFailed(false);
    try {
      const updated = site
        ? await updatePersonalSite(site.id, { ...Object.fromEntries(fields.map(key => [key, site[key]])), featured_vehicle_ids: site.featured_vehicle_ids || [] })
        : await createPersonalSite(slug.trim().toLowerCase());
      setSite(updated);
      setDirty(false); setPreview(null); setConfirmStatus(false);
      setMessage(site ? "Page changes saved." : "Draft created. It has not been published.");
    } catch {
      setFailed(true);
      setMessage("We couldn't confirm the save. Your entries are still here. Check your connection and reload your page before retrying creation.");
    } finally { lock.current = false; setBusy(false); }
  }

  async function loadPreview() {
    if (!site || lock.current || dirty) return;
    lock.current = true; setBusy(true); setMessage(null); setFailed(false);
    try { setPreview(await getPersonalSite(site.id)); }
    catch { setFailed(true); setMessage("Preview couldn't load. Please try again."); }
    finally { lock.current = false; setBusy(false); }
  }

  async function changeParent(parentId: string | null) {
    if (!site || lock.current || dirty) return;
    lock.current = true; setBusy(true); setMessage(null); setFailed(false);
    try {
      const updated = await setPersonalSiteParent(site.id, parentId);
      setSite(updated); setPreview(null); setConfirmStatus(false);
      setMessage("Branding source updated.");
    } catch {
      setFailed(true); setMessage("Branding change could not be confirmed. Reload your page before retrying.");
    } finally { lock.current = false; setBusy(false); }
  }

  async function changeStatus() {
    if (!site || lock.current || dirty || !confirmStatus) return;
    lock.current = true; setBusy(true); setMessage(null); setFailed(false);
    try {
      const updated = await setPersonalSiteStatus(site.id, site.status === "active" ? "inactive" : "active");
      setSite(updated); setConfirmStatus(false); setPreview(null);
      setMessage(updated.status === "active" ? "Your page is published." : "Your page is no longer public.");
    } catch { setFailed(true); setMessage("Publication status couldn't be confirmed. Reload your page before trying again."); }
    finally { lock.current = false; setBusy(false); }
  }

  return <WiredScreen app={app} screen={screen} loading={loading} error={loadError} onRetry={() => setRetry(value => value + 1)}>
    <form onSubmit={save} className="space-y-4 rounded-xl border border-white/10 bg-white/[0.03] p-4" aria-label="Personal page editor">
      {site ? <>
        <p className="text-sm text-zinc-300">Page: {site.slug} · Status: {site.status}</p>
        {fields.map((key, index) => <label key={key} className="block text-sm text-zinc-300">{labels[index]}
          <input className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none" disabled={busy} type={key === "email" ? "email" : key === "photo_url" || key === "calendar_link" || key === "review_link" ? "url" : "text"} pattern={key === "photo_url" || key === "calendar_link" || key === "review_link" ? "https://.*" : undefined} value={site[key] || ""} onChange={event => { setSite({ ...site, [key]: event.target.value }); setDirty(true); setPreview(null); setConfirmStatus(false); }} />
        </label>)}
        <FeaturedVehiclePicker selected={site.featured_vehicle_ids || []} disabled={busy} onChange={ids => { setSite({ ...site, featured_vehicle_ids: ids }); setDirty(true); setPreview(null); setConfirmStatus(false); }} />
        <ParentWebsitePicker current={site.parent_website_id || null} disabled={busy || dirty} onApply={changeParent} />
        <p className="text-xs text-zinc-400">Saving changes to an active page updates its public content.</p>
      </> : <label className="block text-sm text-zinc-300">Page name
        <input className="mt-1 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none" required minLength={2} maxLength={50} pattern="[a-z0-9]+(-[a-z0-9]+)*" disabled={busy} value={slug} onChange={event => setSlug(event.target.value)} placeholder="your-name" />
        <span className="mt-1 block text-xs text-zinc-400">Use lowercase letters, numbers and hyphens. Starts as a private draft.</span>
      </label>}
      <button disabled={busy} className="rounded-lg border border-sky-300/30 px-4 py-2 text-sm text-sky-100" type="submit">{busy ? "Saving…" : site ? "Save page" : "Create draft"}</button>
      {message && <p role={failed ? "alert" : "status"} className="text-sm text-zinc-300">{message}</p>}
      {failed && !dirty && <button type="button" disabled={busy} onClick={() => setRetry(value => value + 1)} className="text-sm text-[var(--app-accent)]">Reload my page</button>}
      {site && <div className="space-y-3 border-t border-white/10 pt-4">
        {dirty && <p className="text-sm text-zinc-300">Save your changes before previewing or changing publication status.</p>}
        <button type="button" disabled={busy || dirty} onClick={loadPreview} className="mr-4 text-sm text-[var(--app-accent)]">Preview saved page</button>
        <button type="button" disabled={busy || dirty} onClick={() => setConfirmStatus(true)} className="text-sm text-[var(--app-accent)]">{site.status === "active" ? "Unpublish page" : "Publish page"}</button>
        {confirmStatus && <div className="space-y-2 rounded-lg border border-white/20 p-3">
          <p className="text-sm">{site.status === "active" ? "Remove public access to this page?" : "Make your saved bio, contact details and featured vehicles publicly visible?"}</p>
          <button type="button" disabled={busy} onClick={changeStatus} className="mr-4 text-sm text-[var(--app-accent)]">Confirm {site.status === "active" ? "unpublish" : "publish"}</button>
          <button type="button" disabled={busy} onClick={() => setConfirmStatus(false)} className="text-sm text-zinc-300">Cancel</button>
        </div>}
        {site.status === "active" && <p className="text-sm"><a className="text-[var(--app-accent)] underline" href={`/rep/${encodeURIComponent(site.slug)}`} target="_blank" rel="noopener noreferrer">Open public page to view or share ↗</a></p>}
        {site.status === "active" && <PersonalPageShare key={site.slug} slug={site.slug} />}
        {preview && <section aria-label="Saved page preview"><p className="mb-3 text-xs text-zinc-400">Saved page preview — contact submission is available on the published page.</p><PersonalPage site={preview} /></section>}
      </div>}
    </form>
  </WiredScreen>;
}
