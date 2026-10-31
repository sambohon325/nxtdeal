"use client";
import { WorkField } from "./WorkField";

// Floating knowledge base widget (2026-07-13, session 38) -- Sam: "we need to include
// a knowledge base thats accessable from each dash... obviously sections of it will be
// closed off to non admin/managers etc, role based - and there it needs to have
// Getting started guides, How to build a deal, basically the how to use NXTDeal for
// each department and everything they can use it for, and how to do it." Blue
// (#2B68AB, the one NXTDeal brand color not already claimed by the turquoise bot or
// yellow help widget) circular button, positioned left of the yellow "?" so all three
// floating/inline widgets (bot, help, knowledge) stay visually distinct. Fetches
// GET /knowledge/articles -- the backend already filters to what this role can see
// (core/knowledge_base.py's per-article visible_roles), so this component never has to
// duplicate that logic client-side.

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { angledClip } from "@/components/BrandAngles";

type Article = {
  id: string;
  title: string;
  department: string;
  category: string;
  body: string;
};

const DEPARTMENT_LABELS: Record<string, string> = {
  sales: "Sales",
  service: "Service",
  finance: "Finance",
  marketing: "Marketing",
  operations: "Operations",
  administration: "Administration",
  all: "General",
};

export function KnowledgeBaseWidget({ menuMode = false, onDismiss }: { menuMode?: boolean; onDismiss?: () => void } = {}) {
  const [open, setOpen] = useState(menuMode);
  const [articles, setArticles] = useState<Article[]>([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState("");
  const [selected, setSelected] = useState<Article | null>(null);

  useEffect(() => {
    if (!open || articles.length > 0) return;

    async function load() {
      setLoading(true);

      try {
        const response = await fetch(`${API_BASE}/knowledge/articles`, {
          headers: { ...authHeaders() },
        });
        const data = await response.json();

        if (response.ok && !data.error) {
          setArticles((data.articles ?? []) as Article[]);
        }
      } catch {
        // Best-effort.
      } finally {
        setLoading(false);
      }
    }

    load();
  }, [open, articles.length]);

  const filtered = articles.filter((a) =>
    `${a.title} ${a.department}`.toLowerCase().includes(search.toLowerCase())
  );

  const grouped = filtered.reduce<Record<string, Article[]>>((acc, article) => {
    const key = article.department || "all";
    acc[key] = acc[key] ?? [];
    acc[key].push(article);
    return acc;
  }, {});

  return (
    <>
      {!menuMode && <button
        onClick={() => setOpen(true)}
        title="Knowledge Base"
        style={angledClip(9)}
        className="fixed bottom-4 right-16 z-40 w-11 h-11 bg-brand-blue text-white text-lg shadow-lg hover:bg-[#5480c9] transition flex items-center justify-center"
      >
        📚
      </button>}

      {open && (
        <div className="fixed inset-0 z-[150] flex items-center justify-center bg-black/60 p-4">
          <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-3xl h-[32rem] flex overflow-hidden">
            <div className="w-64 border-r border-zinc-800 flex flex-col">
              <div className="p-3 border-b border-zinc-800">
                <div className="flex items-center justify-between mb-2">
                  <div className="font-medium text-sm">Knowledge Base</div>
                  <button
                    onClick={() => {
                      setOpen(false); onDismiss?.();
                      setSelected(null);
                    }}
                    className="text-zinc-500 hover:text-white text-sm"
                  >
                    ✕
                  </button>
                </div>
                <WorkField label="Search guides"><input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search guides..."
                  className="w-full h-8 px-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                /></WorkField>
              </div>

              <div className="flex-1 overflow-y-auto p-2 space-y-3">
                {loading && <div className="text-xs text-zinc-500 p-2">Loading…</div>}

                {Object.entries(grouped).map(([department, items]) => (
                  <div key={department}>
                    <div className="text-xs uppercase text-zinc-500 px-2 mb-1">
                      {DEPARTMENT_LABELS[department] ?? department}
                    </div>
                    {items.map((article) => (
                      <button
                        key={article.id}
                        onClick={() => setSelected(article)}
                        className={`w-full text-left px-2 py-1.5 text-sm rounded transition ${
                          selected?.id === article.id
                            ? "bg-[#2B68AB]/20 text-white"
                            : "text-zinc-400 hover:bg-zinc-900 hover:text-white"
                        }`}
                      >
                        {article.title}
                      </button>
                    ))}
                  </div>
                ))}

                {!loading && filtered.length === 0 && (
                  <div className="text-xs text-zinc-600 p-2">No guides match your search.</div>
                )}
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-5">
              {selected ? (
                <>
                  <div className="text-xs uppercase text-[#2B68AB] mb-1">
                    {DEPARTMENT_LABELS[selected.department] ?? selected.department} ·{" "}
                    {selected.category === "getting_started" ? "Getting Started" : "How-To"}
                  </div>
                  <h3 className="text-lg font-medium mb-3">{selected.title}</h3>
                  <div className="text-sm text-zinc-300 leading-relaxed whitespace-pre-wrap">
                    {selected.body}
                  </div>
                </>
              ) : (
                <div className="text-sm text-zinc-500">
                  Pick a guide on the left — Getting Started guides per department, plus
                  How-To guides for deals, campaigns, assets, websites, Department Intelligence, the
                  bot, readiness, compliance, and the network.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}
