"use client";
import { WorkButton } from "./WorkspaceUi";

// Bumper-parity Campaign-Template Library (2026-07-25). Browse prebuilt campaign
// templates by category and launch one into a draft campaign with a single click --
// the NXTDeal answer to Bumper's Library of ~79 ready-to-run campaigns. Backed by
// lib/campaignLibrary.ts (backend/api/routers/content_library.py).
import { useEffect, useState } from "react";
import {
  listTemplates,
  listTemplateCategories,
  instantiateTemplate,
  type CampaignTemplate,
} from "@/lib/campaignLibrary";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

export function CampaignLibraryBoard({ theme }: { theme: Theme }) {
  const [templates, setTemplates] = useState<CampaignTemplate[]>([]);
  const [categories, setCategories] = useState<{ category: string; count: number }[]>([]);
  const [activeCategory, setActiveCategory] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [flash, setFlash] = useState<string | null>(null);
  const [launching, setLaunching] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    Promise.all([
      listTemplates(activeCategory ? { category: activeCategory } : undefined),
      listTemplateCategories(),
    ])
      .then(([t, c]) => {
        setTemplates(t.templates);
        setCategories(c.categories);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load the library."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [activeCategory]);

  async function launch(t: CampaignTemplate) {
    setLaunching(t.id);
    setFlash(null);
    try {
      const campaign = await instantiateTemplate(t.id);
      setFlash(`Created draft campaign "${campaign.name ?? t.name}" (${campaign.id}). Find it under Campaigns to review and activate.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't launch template.");
    } finally {
      setLaunching(null);
    }
  }

  if (loading && templates.length === 0) {
    return <div className="p-4 text-sm text-zinc-500">Loading campaign library…</div>;
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <div className="px-3 pt-3 shrink-0">
        <div className="text-base font-brand">Campaign Library</div>
        <div className="text-xs text-zinc-500">
          Prebuilt campaigns, ready to launch. Pick one and it becomes a draft you can review, tweak, and activate.
        </div>
      </div>

      {flash && (
        <div className="mx-3 mt-2 rounded-md bg-brand-teal/15 border border-brand-teal/40 px-3 py-2 text-xs text-brand-teal">
          {flash}
        </div>
      )}
      {error && (
        <div className="mx-3 mt-2 rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">
          {error}
        </div>
      )}

      <div className="flex flex-wrap gap-1.5 px-3 pt-3 shrink-0">
        <WorkButton aria-pressed={activeCategory === null} type="submit"
          onClick={() => setActiveCategory(null)}
          className={
            activeCategory === null
              ? "text-xs px-2.5 py-1 rounded-full bg-brand-teal text-black"
              : tc(theme, "text-xs px-2.5 py-1 rounded-full bg-zinc-900 text-zinc-300", "text-xs px-2.5 py-1 rounded-full bg-zinc-100 text-zinc-600")
          }
        >
          All
        </WorkButton>
        {categories.map((c) => (
          <WorkButton aria-pressed={activeCategory === c.category} type="submit"
            key={c.category}
            onClick={() => setActiveCategory(c.category)}
            className={
              activeCategory === c.category
                ? "text-xs px-2.5 py-1 rounded-full bg-brand-teal text-black"
                : tc(theme, "text-xs px-2.5 py-1 rounded-full bg-zinc-900 text-zinc-300", "text-xs px-2.5 py-1 rounded-full bg-zinc-100 text-zinc-600")
            }
          >
            {c.category} ({c.count})
          </WorkButton>
        ))}
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto p-3 grid grid-cols-1 md:grid-cols-2 gap-2.5">
        {templates.map((t) => (
          <div
            key={t.id}
            className={tc(theme, "rounded-md border border-zinc-800 bg-zinc-900/60 p-3", "rounded-md border border-zinc-200 bg-white p-3")}
          >
            <div className="flex items-start justify-between gap-2">
              <div className="min-w-0">
                <div className="text-sm font-semibold truncate">{t.name}</div>
                <div className="text-xs uppercase tracking-wide text-zinc-500 mt-0.5">
                  {t.category} · {t.campaign_type} · {t.channel}
                </div>
              </div>
              <WorkButton type="submit"
                onClick={() => launch(t)}
                disabled={launching === t.id}
                className="shrink-0 text-xs px-2.5 py-1 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50"
              >
                {launching === t.id ? "Launching…" : "Launch"}
              </WorkButton>
            </div>
            <div className="text-xs text-zinc-500 mt-1.5">{t.description}</div>
            {t.suggested_subject && (
              <div className="text-xs text-zinc-500 mt-1.5 italic truncate">Subject: {t.suggested_subject}</div>
            )}
            {t.times_used > 0 && (
              <div className="text-xs text-zinc-600 mt-1">Used {t.times_used}×</div>
            )}
          </div>
        ))}
        {templates.length === 0 && !loading && (
          <div className="text-xs text-zinc-500 p-3">No templates in this category.</div>
        )}
      </div>
    </div>
  );
}

export default CampaignLibraryBoard;
