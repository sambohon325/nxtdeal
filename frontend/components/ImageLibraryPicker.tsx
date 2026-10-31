"use client";
import { WorkButton, WorkInput, WorkSelect , WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Reusable shared-media-library picker (2026-07-23) -- Sam: "a shared image asset file
// system that's accessible from all marketing related tools... OEM approved images,
// logos, dealership logos and branding, as well as inventory." One modal any tool drops
// in: category tabs (OEM Approved / Logos / Dealership Branding / Inventory / General),
// a search box, an add-by-URL affordance for the dealership-wide categories, and click-
// to-pick. Inventory images are the live vehicle photos merged in by the backend and are
// read-only here. Talks to lib/mediaLibrary.ts.
//
// Presentational + self-contained: the host controls `open`/`onClose` and receives the
// chosen image URL via `onPick`. Same drop-in ergonomics as AiAssistButton.

import { useEffect, useState } from "react";
import {
  listMedia,
  listMediaCategories,
  addMedia,
  uploadMedia,
  mediaImageUrl,
  removeMedia,
  type MediaImage,
  type MediaCategory,
} from "@/lib/mediaLibrary";

type Theme = "dark" | "light";

type Props = {
  open: boolean;
  onClose: () => void;
  onPick: (url: string) => void;
  theme?: Theme;
};

// Categories a user can upload into (backend's UPLOADABLE_CATEGORIES; inventory is
// live/read-only). Kept here so the "Add" form's select matches the backend.
const UPLOADABLE = [
  { key: "oem_approved", label: "OEM Approved" },
  { key: "logos", label: "Logos" },
  { key: "dealership_branding", label: "Dealership Branding" },
  { key: "general", label: "General" },
];

function cx(theme: Theme, dark: string, light: string) {
  return theme === "dark" ? dark : light;
}

export default function ImageLibraryPicker({ open, onClose, onPick, theme = "dark" }: Props) {
  const [categories, setCategories] = useState<MediaCategory[]>([]);
  const [activeCat, setActiveCat] = useState<string>("");
  const [query, setQuery] = useState("");
  const [images, setImages] = useState<MediaImage[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [showAdd, setShowAdd] = useState(false);
  const [addFile, setAddFile] = useState<File | null>(null);
  const [addUrl, setAddUrl] = useState("");
  const [addName, setAddName] = useState("");
  const [addCat, setAddCat] = useState("logos");
  const [saving, setSaving] = useState(false);

  function refresh(cat: string, q: string) {
    setLoading(true);
    setError(null);
    listMedia(cat || undefined, q || undefined)
      .then((r) => setImages(r.images))
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the media library."))
      .finally(() => setLoading(false));
  }

  // Load categories + the first page when the modal opens.
  useEffect(() => {
    if (!open) return;
    listMediaCategories()
      .then((r) => setCategories(r.categories))
      .catch(() => setCategories([]));
    refresh(activeCat, query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (!open) return;
    refresh(activeCat, query);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [activeCat]);

  if (!open) return null;

  function submitSearch(e: React.FormEvent) {
    e.preventDefault();
    refresh(activeCat, query);
  }

  function submitAdd() {
    if (saving || (!addFile && !addUrl.trim())) return;
    if (addFile && addFile.size > 12 * 1024 * 1024) { setError("Choose an image of 12 MB or less."); return; }
    setSaving(true);
    setError(null);
    (addFile ? uploadMedia(addFile, addName.trim(), addCat) : addMedia(addUrl.trim(), addName.trim(), addCat))
      .then(() => {
        setAddFile(null);
        setAddUrl("");
        setAddName("");
        setShowAdd(false);
        listMediaCategories().then((r) => setCategories(r.categories)).catch(() => {});
        refresh(activeCat, query);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to add this image."))
      .finally(() => setSaving(false));
  }

  function handleRemove(img: MediaImage) {
    removeMedia(img.id)
      .then(() => refresh(activeCat, query))
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to remove this image."));
  }

  const panelCls = cx(theme, "bg-brand-charcoal text-zinc-200 border-zinc-700", "bg-white text-zinc-800 border-zinc-200");
  const inputCls = cx(theme, "bg-zinc-900 border-zinc-700 text-zinc-100 placeholder-zinc-500", "bg-white border-zinc-300 text-zinc-900 placeholder-zinc-400");
  const chipCls = cx(theme, "bg-zinc-800 text-zinc-200 hover:bg-zinc-700 border-zinc-700", "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 border-zinc-200");

  return (
    <WorkOverlay className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 p-4" onMouseDown={onClose}>
      <div
        className={`w-full max-w-3xl max-h-[80vh] flex flex-col rounded-xl border shadow-2xl ${panelCls}`}
        onMouseDown={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-700/50">
          <div className="text-sm font-semibold">🖼 Shared Media Library</div>
          <div className="flex items-center gap-2">
            <WorkButton type="submit" onClick={() => setShowAdd((s) => !s)} className={`text-xs px-2 py-1 rounded border ${chipCls}`}>
              {showAdd ? "Cancel" : "+ Add image"}
            </WorkButton>
            <WorkButton type="submit" onClick={onClose} className="text-zinc-500 hover:text-white text-lg leading-none px-1">×</WorkButton>
          </div>
        </div>

        {/* Shared marketing image upload or existing URL */}
        {showAdd && (
          <div className="px-4 py-3 border-b border-zinc-700/50 space-y-2">
            <label className="block text-xs">Upload your image
              <WorkInput aria-label="Upload marketing image" type="file" accept="image/jpeg,image/png,image/webp" disabled={saving} onChange={e => { setAddFile(e.target.files?.[0] || null); setAddUrl(""); }} className="mt-2 block w-full text-xs" />
            </label>
            <p className="text-xs opacity-70">JPG, PNG or WebP, up to 12 MB. These are public marketing images. Do not upload customer documents.</p>
            <div className="grid grid-cols-1 sm:grid-cols-[1fr_1fr_auto] gap-2">
              <WorkInput disabled={!!addFile || saving} aria-label="Existing image URL" value={addUrl} onChange={(e) => setAddUrl(e.target.value)} placeholder="Image URL" className={`h-8 px-2 text-xs rounded border ${inputCls}`} />
              <WorkField label="Name (optional)"><WorkInput value={addName} onChange={(e) => setAddName(e.target.value)} placeholder="Name (optional)" className={`h-8 px-2 text-xs rounded border ${inputCls}`} /></WorkField>
              <WorkField label="Add Cat"><WorkSelect value={addCat} onChange={(e) => setAddCat(e.target.value)} className={`h-8 px-2 text-xs rounded border ${inputCls}`}>
                {UPLOADABLE.map((c) => (
                  <option key={c.key} value={c.key}>{c.label}</option>
                ))}
              </WorkSelect></WorkField>
            </div>
            <WorkButton type="submit" onClick={submitAdd} disabled={saving || (!addFile && !addUrl.trim())} className={`text-xs px-3 py-1 rounded border disabled:opacity-40 ${chipCls}`}>
              {saving ? "Adding…" : "Add to library"}
            </WorkButton>
          </div>
        )}

        {/* Category tabs + search */}
        <div className="px-4 py-2 border-b border-zinc-700/50 flex flex-wrap items-center gap-1.5">
          <WorkButton aria-pressed={activeCat === ""} type="submit"
            onClick={() => setActiveCat("")}
            className={`text-xs px-2 py-1 rounded border ${activeCat === "" ? "bg-brand-teal text-black border-brand-teal" : chipCls}`}
          >
            All
          </WorkButton>
          {categories.map((c) => (
            <WorkButton aria-pressed={activeCat === c.key} type="submit"
              key={c.key}
              onClick={() => setActiveCat(c.key)}
              className={`text-xs px-2 py-1 rounded border ${activeCat === c.key ? "bg-brand-teal text-black border-brand-teal" : chipCls}`}
            >
              {c.label} <span className="opacity-60">{c.count}</span>
            </WorkButton>
          ))}
          <form onSubmit={submitSearch} className="ml-auto">
            <WorkField label="Search"><WorkInput value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search…" className={`h-7 px-2 text-xs rounded border ${inputCls}`} /></WorkField>
          </form>
        </div>

        {error && <div className="px-4 pt-2 text-xs text-red-400">{error}</div>}

        {/* Grid */}
        <div className="flex-1 overflow-y-auto p-4">
          {loading ? (
            <div className="text-sm text-zinc-500">Loading…</div>
          ) : images.length === 0 ? (
            <div className="text-xs text-zinc-500 text-center py-10">
              No images here yet. Use &quot;+ Add image&quot; to add OEM art, logos, or branding.
            </div>
          ) : (
            <div className="grid grid-cols-3 sm:grid-cols-4 gap-3">
              {images.map((img) => (
                <div key={img.id} className={`group relative rounded-lg border overflow-hidden ${cx(theme, "border-zinc-700 bg-zinc-900", "border-zinc-200 bg-zinc-50")}`}>
                  <WorkButton type="submit" onClick={() => { onPick(img.url); onClose(); }} className="block w-full" title={`Use ${img.name || "image"}`}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img src={mediaImageUrl(img.url)} alt={img.name} className="w-full h-24 object-cover" onError={(e) => ((e.target as HTMLImageElement).style.opacity = "0.3")} />
                  </WorkButton>
                  <div className="px-1.5 py-1">
                    <div className="text-xs truncate">{img.name || (img.scope === "inventory" ? img.vehicle : "Untitled")}</div>
                    <div className="text-xs text-zinc-500 truncate">{img.scope === "inventory" ? "Inventory" : img.category.replace(/_/g, " ")}</div>
                  </div>
                  {img.removable && (
                    <WorkButton type="submit" variant="danger"
                      onClick={() => handleRemove(img)}
                      className="absolute top-1 right-1 opacity-0 group-hover:opacity-100 text-xs px-1 rounded bg-red-950/70 text-red-200"
                      title="Remove from library"
                    >
                      ×
                    </WorkButton>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </WorkOverlay>
  );
}
