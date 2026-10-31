"use client";

// AppSettings — the dealer "Appearance" panel (2026-07-24). Lets a dealership brand the app suite
// within the NXTDeal framework: their name, a brand color, and a logo. Writes to the shared
// appTheme store (localStorage-backed), so every app updates live via the --app-accent variable.

import { useState } from "react";
import { useAppTheme, setAppTheme, resetAppTheme } from "@/lib/apps/appTheme";

const PRESETS = ["#2b68ab", "#3fbcc4", "#ee3c25", "#fbcf09", "#7c3aed", "#059669", "#0ea5e9", "#e11d48"];

export function AppSettings({ onClose }: { onClose: () => void }) {
  const theme = useAppTheme();
  const [name, setName] = useState(theme.dealershipName);
  const [accent, setAccent] = useState(theme.accent);
  const [logo, setLogo] = useState(theme.logoUrl ?? "");

  function save() {
    setAppTheme({
      dealershipName: name.trim() || "NXTDeal",
      accent,
      logoUrl: logo.trim() || null,
    });
    onClose();
  }

  const field = "w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-[var(--app-accent)]";
  const label = "mb-1 block text-[11px] uppercase tracking-wide text-zinc-500";

  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/70 p-4 font-brand" onClick={onClose}>
      <div
        className="w-full max-w-sm rounded-2xl border border-white/10 bg-[#141416] p-5 text-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        style={{ ["--app-accent" as string]: accent }}
      >
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-lg font-bold">Appearance</h3>
          <button onClick={onClose} className="text-zinc-500 hover:text-white" aria-label="Close">✕</button>
        </div>
        <p className="mb-4 text-xs text-zinc-400">Brand the apps to your dealership — within the NXTDeal framework.</p>

        <label className={label}>Dealership name</label>
        <input value={name} onChange={(e) => setName(e.target.value)} className={`${field} mb-4`} placeholder="Your dealership" />

        <label className={label}>Brand color</label>
        <div className="mb-2 flex flex-wrap gap-2">
          {PRESETS.map((c) => (
            <button
              key={c}
              onClick={() => setAccent(c)}
              style={{ background: c }}
              className={`h-7 w-7 rounded-full border-2 transition ${accent.toLowerCase() === c ? "border-white" : "border-transparent"}`}
              title={c}
            />
          ))}
        </div>
        <input type="color" value={accent} onChange={(e) => setAccent(e.target.value)} className="mb-4 h-9 w-full cursor-pointer rounded-lg bg-white/5" />

        <label className={label}>Logo URL (optional)</label>
        <input value={logo} onChange={(e) => setLogo(e.target.value)} className={`${field} mb-5`} placeholder="https://…/logo.png" />

        <div className="flex items-center justify-between">
          <button onClick={() => { resetAppTheme(); onClose(); }} className="text-xs text-zinc-500 transition hover:text-white">
            Reset to NXTDeal
          </button>
          <button onClick={save} className="rounded-full bg-[var(--app-accent)] px-5 py-2 text-sm font-semibold text-[var(--app-accent-text)]">
            Save
          </button>
        </div>
      </div>
    </div>
  );
}
