"use client";
import {RecordTable} from "./RecordTable";
import { WorkButton, WorkInput, WorkTextarea , WorkStat} from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import { WorkField } from "./WorkField";

// Inventory department's "Merchandising" item -- digital inventory
// presentation (Inventory rebuild, sixth slice). Real photo upload,
// description, and featured flag; SIMULATED VDP Health Score (blended with
// real inputs) and Feed Sync Status -- every simulated figure carries a
// visible "Simulated" badge + disclaimer, never presented as real.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { DealerPhotoUpload } from "@/components/DealerCloudStorage";
import { useEffect, useState } from "react";
import {
  getMerchandisingQueue,
  getMerchandisingView,
  addVehicleImage,
  updateDescription,
  setFeatured,
  publishToFeed,
  type MerchandisingQueue,
  type MerchandisingView,
} from "@/lib/merchandising";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

function money(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === "") return "—";
  const n = typeof v === "string" ? parseFloat(v) : v;
  if (Number.isNaN(n)) return String(v);
  return `$${n.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function scoreColor(score: number): string {
  if (score >= 70) return "text-green-400";
  if (score >= 40) return "text-amber-400";
  return "text-red-400";
}

function SimulatedBadge({ disclaimer }: { disclaimer: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="relative inline-block">
      <WorkButton type="submit"
        onClick={() => setOpen((o) => !o)}
        className="text-xs px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 font-brand uppercase tracking-wide cursor-help"
        title={disclaimer}
      >
        Simulated
      </WorkButton>
      {open && (
        <div className="absolute z-10 top-full left-0 mt-1 w-64 text-xs leading-snug p-2 rounded-lg bg-zinc-950 border border-amber-900/50 text-amber-200 shadow-xl">
          {disclaimer}
        </div>
      )}
    </span>
  );
}

type WorkState = { onDraftOpenChange?: (open:boolean)=>void; onSavingChange?: (saving:boolean)=>void };
function VehicleDetailModal({ theme, vehicleId, onClose, onChanged, onDraftOpenChange, onSavingChange }: WorkState & { theme: Theme; vehicleId: string; onClose: () => void; onChanged: () => void }) {
  const [data, setData] = useState<MerchandisingView | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  const [photoDraft, setPhotoDraft] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [imageUrl, setImageUrl] = useState("");
  const [caption, setCaption] = useState("");
  const [descriptionDraft, setDescriptionDraft] = useState<string|null>(null);
  const description = descriptionDraft ?? data?.description ?? "";
  const [confirmClose,setConfirmClose]=useState(false);
  const unfinished = photoDraft || !!imageUrl || !!caption || (descriptionDraft!==null && descriptionDraft!==data?.description);
  const saving = busy || photoBusy;
  useEffect(()=>{onDraftOpenChange?.(unfinished);return ()=>onDraftOpenChange?.(false);},[unfinished,onDraftOpenChange]);
  useEffect(()=>{onSavingChange?.(saving);return ()=>onSavingChange?.(false);},[saving,onSavingChange]);
  function requestClose() {
    if(busy || photoBusy)return;
    if(photoDraft || imageUrl || caption || (descriptionDraft!==null && descriptionDraft!==data?.description))setConfirmClose(true);
    else onClose();
  }

  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  function refresh() {
    setLoading(true);
    return getMerchandisingView(vehicleId)
      .then((v) => {
        setData(v);
        return true;
      })
      .catch((e) => {setError((e as Error).message); return false;})
      .finally(() => setLoading(false));
  }

  useEffect(()=>{void refresh();}, [vehicleId]);

  async function withBusy(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      const refreshed = await refresh();
      onChanged();
      return refreshed;
    } catch (e) {
      setError((e as Error).message);
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (!data) return <section role="region" aria-label="Vehicle listing editor" className="workspace-editor-surface p-4"><WorkButton type="submit" className="min-h-11 underline" onClick={requestClose}>Back to merchandising</WorkButton><p role={error?"alert":"status"}>{error || "Loading listing…"}</p>{error && <WorkButton type="submit" onClick={()=>void refresh()} className="min-h-11 underline">Retry listing</WorkButton>}</section>;

  const { vehicle, images, featured, vdp_health, feed_status } = data;

  return (
    <div data-department-work="" className="workspace-inline-editor">
      <div role="region" aria-label="Vehicle listing editor" className="workspace-editor-surface p-5 space-y-3">
        <WorkButton type="submit" disabled={busy || photoBusy} onClick={requestClose} className="min-h-11 underline">Back to merchandising</WorkButton>
        {confirmClose && <section role="alert"><p>You have unsaved listing changes.</p><WorkButton type="submit" onClick={()=>setConfirmClose(false)} className="min-h-11 rounded border px-3">Keep editing</WorkButton><WorkButton type="submit" disabled={busy || photoBusy} onClick={onClose} className="min-h-11 underline px-3">Discard draft and return</WorkButton></section>}
        {(busy || photoBusy || loading) && <p role="status">Saving or refreshing listing…</p>}
        <div className="flex items-start justify-between gap-3">
          <div>
            <div className="text-sm font-brand uppercase tracking-wide">
              {vehicle.year} {vehicle.make} {vehicle.model}
            </div>
            <div className="text-xs text-zinc-500 mt-0.5">{vehicle.vehicle_id} · {money(vehicle.price)}{featured ? " · ★ Featured" : ""}</div>
          </div>
          <WorkButton type="submit" disabled={busy || photoBusy} onClick={requestClose} className="min-h-11 underline">Close listing</WorkButton>
        </div>

        {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}

        <details className={cardClass}><summary className="min-h-11 cursor-pointer">Simulated listing performance</summary>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
            VDP Health Score <SimulatedBadge disclaimer={vdp_health.disclaimer} />
          </div>
          <div className={`text-2xl font-semibold mb-1 ${scoreColor(vdp_health.health_score)}`}>{vdp_health.health_score} / {vdp_health.health_score_max}</div>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div><span className="text-zinc-500">Photos</span><div>{vdp_health.has_photos ? "✓ Real" : "✗ Missing"}</div></div>
            <div><span className="text-zinc-500">Description</span><div>{vdp_health.has_description ? "✓ Real" : "✗ Missing"}</div></div>
            <div><span className="text-zinc-500">Est. Views</span><div>{vdp_health.simulated_page_views}</div></div>
          </div>
        </details>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Photos ({images.length})</div>
          <div className="space-y-1 mb-2">
            {images.map((img) => (
              <div key={img.id} className="text-xs text-zinc-400 truncate">{img.caption || "Untitled"} — {img.url}</div>
            ))}
            {images.length === 0 && <div className="text-xs text-zinc-500">No photos on file.</div>}
          </div>
          <WorkField label="Image URL"><WorkInput disabled={busy || photoBusy} value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder="Image URL" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-1.5 ${textClass}`} /></WorkField>
          <WorkField label="Caption (optional)"><WorkInput disabled={busy || photoBusy} value={caption} onChange={(e) => setCaption(e.target.value)} placeholder="Caption (optional)" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`} /></WorkField>
          <WorkButton type="submit" variant="primary" disabled={busy || photoBusy || !imageUrl.trim()} onClick={() => withBusy(() => addVehicleImage(vehicleId, imageUrl, caption)).then(saved=>{if(saved){setImageUrl("");setCaption("");}})} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Add Photo</WorkButton>
          <DealerPhotoUpload disabled={busy} onBusyChange={setPhotoBusy} onDraftChange={setPhotoDraft} vehicleId={vehicleId} onUploaded={() => { void withBusy(async () => undefined); }} />
        </div>

        <div className={cardClass}>

          <WorkField label="Description"><WorkTextarea value={description} disabled={busy || photoBusy} onChange={(e) => setDescriptionDraft(e.target.value)} rows={3} placeholder="Vehicle description / comments…" className={`w-full rounded-md border px-2 py-1.5 text-xs mb-2 ${textClass}`} /></WorkField>
          <WorkButton type="submit" variant="primary" disabled={busy || photoBusy} onClick={() => withBusy(() => updateDescription(vehicleId, description)).then(saved=>{if(saved)setDescriptionDraft(null);})} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Save Description</WorkButton>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2">Featured</div>
          <WorkButton type="submit"
            disabled={busy || photoBusy}
            onClick={() => withBusy(() => setFeatured(vehicleId, !featured))}
            className={`text-xs px-2.5 py-1.5 rounded font-medium transition disabled:opacity-50 ${featured ? "bg-red-600 text-white hover:opacity-90" : "bg-brand-blue text-white hover:opacity-90"}`}
          >
            {featured ? "Remove from Featured" : "Mark as Featured"}
          </WorkButton>
        </div>

        <div className={cardClass}>
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500 mb-2 flex items-center gap-2">
            Feed simulation — no live publishing <SimulatedBadge disclaimer={feed_status.disclaimer} />
          </div>
          <div className="space-y-1.5">
            {feed_status.feeds.map((f) => (
              <div key={f.platform} className="flex items-center justify-between text-xs">
                <span>{f.platform}</span>
                <div className="flex items-center gap-2">
                  <span className={`capitalize ${f.status === "synced" ? "text-green-400" : f.status === "pending" ? "text-amber-400" : "text-red-400"}`}>{f.status}</span>
                  <WorkButton type="submit" disabled={busy || photoBusy} onClick={() => withBusy(() => publishToFeed(vehicleId, f.platform))} className="text-xs px-2 py-0.5 rounded bg-zinc-700 text-white hover:opacity-90 transition disabled:opacity-50">Simulate republish</WorkButton>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function MerchandisingBoard({ theme, onDraftOpenChange, onSavingChange }: WorkState & { theme: Theme }) {
  const [queue, setQueue] = useState<MerchandisingQueue | null>(null);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<string | null>(null);
  const [pageSize,setPageSize]=useState(25);

  const [page,setPage] = useState(0);
  const [error,setError] = useState("");
  function refresh() {
    setError("");
    setLoading(true);
    getMerchandisingQueue(pageSize,page*pageSize)
      .then(setQueue)
      .catch(e=>setError(e instanceof Error?e.message:"Unable to load vehicles"))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [page,pageSize]);

  const noPhotosCount = queue?.vehicles.filter((v) => !v.vdp_health.has_photos).length || 0;
  const noDescriptionCount = queue?.vehicles.filter((v) => !v.vdp_health.has_description).length || 0;
  const featuredCount = queue?.vehicles.filter((v) => v.vdp_health.is_featured).length || 0;

  if(selected)return <VehicleDetailModal onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} key={selected} theme={theme} vehicleId={selected} onClose={()=>setSelected(null)} onChanged={refresh}/>;

  return (
    <div className={tc(theme, "work-inventory-board", "work-inventory-board")}>
      <div className={tc(theme, "work-inventory-stats", "work-inventory-stats")}>
        <Kpi theme={theme} label="In Queue" value={String(queue?.total || 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Missing Photos (this page)" value={String(noPhotosCount)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Missing Description (this page)" value={String(noDescriptionCount)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Featured (this page)" value={String(featuredCount)} color={RIBBON[3]} />
      </div>

      <div className="px-4 py-2 border-b border-zinc-800">
        <span className="text-xs px-2 py-1 rounded bg-amber-950/30 border border-amber-900/50 text-amber-300">
          VDP Health Score and Feed Sync Status below are SIMULATED (blended with real photo/description inputs) -- no real VDP-analytics platform or listing feed is connected yet. Click any &quot;Simulated&quot; badge for details.
        </span>
      </div>

      <div className="flex-1 p-4">
        {error ? <div role="alert">{error}<WorkButton type="submit" className="min-h-11 underline px-3" onClick={refresh}>Retry queue</WorkButton></div> : loading || !queue ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <RecordTable label="Merchandising vehicles" paginate={false}><thead><tr><th>Vehicle</th><th>Photos</th><th>Description</th><th>Simulated health</th><th>Next step</th></tr></thead><tbody>{queue.vehicles.map(v=><tr key={v.vehicle_id}><td><strong>{v.year} {v.make} {v.model}</strong><span className="work-record-meta">{v.vehicle_id}</span></td><td>{v.vdp_health.has_photos?"Ready":"Needed"}</td><td>{v.vdp_health.has_description?"Ready":"Needed"}</td><td>{v.vdp_health.health_score}/100</td><td><WorkButton onClick={()=>setSelected(v.vehicle_id)}>Open listing</WorkButton></td></tr>)}</tbody></RecordTable>
        )}
      </div>

      <CollectionPagination label="Vehicles" total={queue?.total??0} page={page} pageSize={pageSize} onPageSizeChange={size=>{setPageSize(size);setPage(0);}} onPageChange={setPage} busy={loading||!!error}/>

    </div>
  );
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }
