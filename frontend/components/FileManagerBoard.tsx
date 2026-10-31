"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Bumper-parity File Manager / DAM (2026-07-25): a general digital-asset catalog across
// image/video/audio/document, with categories, tags, and search. Backed by
// lib/fileManager.ts (backend/api/routers/content_library.py).
import { useEffect, useState } from "react";
import {
  getStorageSummary,
  listFiles,
  addFile,
  removeFile,
  type FileAsset,
  type MediaType,
  type StorageSummary,
} from "@/lib/fileManager";

type Theme = "dark" | "light";

const MEDIA_TYPES: MediaType[] = ["image", "video", "audio", "document", "other"];

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

export function FileManagerBoard({ theme }: { theme: Theme }) {
  const [files, setFiles] = useState<FileAsset[]>([]);
  const [summary, setSummary] = useState<StorageSummary | null>(null);
  const [filter, setFilter] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [showForm, setShowForm] = useState(false);

  const [name, setName] = useState("");
  const [mediaType, setMediaType] = useState<MediaType>("image");
  const [url, setUrl] = useState("");
  const [category, setCategory] = useState("general");

  const card = tc(theme, "rounded-md border border-zinc-800 bg-zinc-900/60 p-3", "rounded-md border border-zinc-200 bg-white p-3");
  const input = tc(theme, "rounded-md bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-[12px]", "rounded-md bg-white border border-zinc-300 px-2 py-1.5 text-[12px]");

  function refresh() {
    Promise.all([
      listFiles({ media_type: filter || undefined, query: query || undefined }),
      getStorageSummary(),
    ])
      .then(([f, s]) => { setFiles(f.files); setSummary(s); setError(null); })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load files."));
  }

  useEffect(refresh, [filter]);

  async function add() {
    setBusy(true); setError(null);
    try {
      await addFile({ name, media_type: mediaType, url, category });
      setName(""); setUrl(""); setShowForm(false);
      refresh();
    } catch (e) { setError(e instanceof Error ? e.message : "Couldn't add file."); } finally { setBusy(false); }
  }

  async function remove(id: string) {
    try { await removeFile(id); refresh(); }
    catch (e) { setError(e instanceof Error ? e.message : "Couldn't remove file."); }
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
      <div className="px-3 pt-3 shrink-0 flex items-center justify-between">
        <div>
          <div className="text-base font-brand">File Manager</div>
          <div className="text-xs text-zinc-500">Your dealership&apos;s shared library of images, video, audio, and documents.</div>
        </div>
        <WorkButton type="submit" onClick={() => setShowForm((s) => !s)} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold">
          {showForm ? "Close" : "+ Add file"}
        </WorkButton>
      </div>

      {error && <div className="mx-3 mt-2 rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>}

      {summary && (
        <div className="flex flex-wrap gap-1.5 px-3 pt-3">
          <WorkButton aria-pressed={filter === null} type="submit" onClick={() => setFilter(null)} className={filter === null ? "text-xs px-2.5 py-1 rounded-full bg-brand-teal text-black" : tc(theme, "text-xs px-2.5 py-1 rounded-full bg-zinc-900 text-zinc-300", "text-xs px-2.5 py-1 rounded-full bg-zinc-100 text-zinc-600")}>
            All ({summary.total})
          </WorkButton>
          {MEDIA_TYPES.map((mt) => (
            <WorkButton aria-pressed={filter === mt} type="submit" key={mt} onClick={() => setFilter(mt)} className={filter === mt ? "text-xs px-2.5 py-1 rounded-full bg-brand-teal text-black capitalize" : tc(theme, "text-xs px-2.5 py-1 rounded-full bg-zinc-900 text-zinc-300 capitalize", "text-xs px-2.5 py-1 rounded-full bg-zinc-100 text-zinc-600 capitalize")}>
              {mt} ({summary.by_media_type[mt]?.count ?? 0})
            </WorkButton>
          ))}
        </div>
      )}

      <div className="p-3 space-y-2">
        {showForm && (
          <div className={card + " flex flex-wrap gap-2 items-center"}>
            <WorkField label="File name"><WorkInput className={input + " flex-1 min-w-[140px]"} placeholder="File name" value={name} onChange={(e) => setName(e.target.value)} /></WorkField>
            <WorkField label="File type"><WorkSelect className={input} value={mediaType} onChange={(e) => setMediaType(e.target.value as MediaType)}>
              {MEDIA_TYPES.map((mt) => <option key={mt} value={mt} className="capitalize">{mt}</option>)}
            </WorkSelect></WorkField>
            <WorkField label="URL or storage reference"><WorkInput className={input + " flex-1 min-w-[160px]"} placeholder="URL or storage reference" value={url} onChange={(e) => setUrl(e.target.value)} /></WorkField>
            <WorkField label="Category"><WorkInput className={input} placeholder="Category" value={category} onChange={(e) => setCategory(e.target.value)} /></WorkField>
            <WorkButton type="submit" onClick={add} disabled={busy || !name || !url} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">Add</WorkButton>
          </div>
        )}

        <div className="flex gap-2">
          <WorkField label="Search name, tags, description"><WorkInput className={input + " flex-1"} placeholder="Search name, tags, description…" value={query} onChange={(e) => setQuery(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") refresh(); }} /></WorkField>
          <WorkButton type="submit" onClick={refresh} className="text-xs px-3 py-1.5 rounded-md bg-zinc-700 text-white">Search</WorkButton>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          {files.map((f) => (
            <div key={f.id} className={card + " flex items-start justify-between gap-2"}>
              <div className="min-w-0">
                <div className="text-xs font-semibold truncate">{f.name}</div>
                <div className="text-xs uppercase tracking-wide text-zinc-500">{f.media_type} · {f.category}</div>
                <a href={f.url} target="_blank" rel="noreferrer" className="text-xs text-brand-teal truncate block max-w-[220px]">{f.url}</a>
              </div>
              <WorkButton type="submit" onClick={() => remove(f.id)} className="text-xs px-1.5 text-zinc-500 shrink-0">✕</WorkButton>
            </div>
          ))}
          {files.length === 0 && <div className="text-xs text-zinc-500 p-2">No files yet.</div>}
        </div>
      </div>
    </div>
  );
}

export default FileManagerBoard;
