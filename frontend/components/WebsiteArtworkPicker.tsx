"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";

import { mediaImageUrl } from "@/lib/mediaLibrary";
import { useState } from "react";
import gallery from "@/lib/websiteBackgroundGallery.json";
import ImageLibraryPicker from "./ImageLibraryPicker";

export function WebsiteArtworkPicker({ label, value, disabled, onChange }: {
  label: string; value: string; disabled?: boolean; onChange: (url: string) => void;
}) {
  const [category, setCategory] = useState("All");
  const [mediaOpen, setMediaOpen] = useState(false);
  return <fieldset disabled={disabled} className="my-4 min-w-0">
    <legend className="font-semibold">{label}</legend>
    {value && <img src={mediaImageUrl(value)} alt={`${label} preview`} className="mt-3 h-36 w-full rounded-lg object-cover" />}
    <div className="my-3 flex flex-wrap gap-2">
      <WorkButton type="button" onClick={() => setMediaOpen(true)}>Choose dealership image</WorkButton>
      <WorkButton type="button" disabled={!value || disabled} onClick={() => onChange("")}>Reset image</WorkButton>
    </div>
    <label>Image URL<WorkInput type="text" placeholder="https://" value={value} onChange={e => onChange(e.target.value)} /></label>
    <details className="mt-3">
      <summary className="cursor-pointer">Explore {gallery.length} background images</summary>
      <label className="my-3 block">Collection<WorkSelect value={category} onChange={e => setCategory(e.target.value)}>{["All", ...new Set(gallery.map(item => item.category))].map(item => <option key={item}>{item}</option>)}</WorkSelect></label>
      <div className="grid max-h-80 grid-cols-2 gap-3 overflow-auto sm:grid-cols-3" style={{ scrollbarWidth: "none" }}>
        {gallery.filter(item => category === "All" || item.category === category).map(item => <WorkButton type="button" key={item.id} aria-pressed={value === item.url} onClick={() => onChange(item.url)} className="overflow-hidden rounded-lg border border-zinc-500/30 p-0 text-left">
          <img src={item.url} alt="" loading="lazy" className="h-24 w-full object-cover" />
          <span className="block p-2 text-xs">{item.name}{value === item.url ? " · Selected" : ""}</span>
        </WorkButton>)}
      </div>
    </details>
    <ImageLibraryPicker open={mediaOpen && !disabled} onClose={() => setMediaOpen(false)} onPick={url => { onChange(url); setMediaOpen(false); }} />
  </fieldset>;
}
