"use client";

// Drop-in replacement for the plain "Pin"/"Pinned" button every chat-first page's
// Workspace panel renders (session 72 -- Sam: "when you pin something from the
// workplace, it should have an option (simular to google docs) for only you to
// access, or if you want to share, you can select a department, multiple
// departments, or all, and it goes into 'Shared Knowledge'"). A small popover with two
// paths: "Only me" (unchanged existing behavior -- lib/pins.ts's local, browser-only
// pin) or "Share..." (a role/department picker that POSTs a new backend
// core/knowledge_pins.py KnowledgePin via lib/sharedKnowledge.ts).

import { useEffect, useState } from "react";
import { PinIcon } from "@/components/Icons";
import { fetchShareRoles, createSharedPin, ROLE_LABELS } from "@/lib/sharedKnowledge";
import type { Pin } from "@/lib/pins";

export function PinShareButton({
  candidate,
  isPinned,
  onPinLocal,
}: {
  candidate: (Omit<Pin, "id" | "pinnedAt" | "tag"> & { tag?: string }) | null;
  isPinned: boolean;
  onPinLocal: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"menu" | "share">("menu");
  const [roles, setRoles] = useState<string[]>([]);
  const [selectedRoles, setSelectedRoles] = useState<string[]>([]);
  const [shareAll, setShareAll] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [shared, setShared] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (mode === "share" && roles.length === 0) {
      fetchShareRoles()
        .then(setRoles)
        .catch(() => setRoles([]));
    }
  }, [mode, roles.length]);

  useEffect(() => {
    if (!open) {
      setMode("menu");
      setError(null);
    }
  }, [open]);

  if (!candidate) return null;

  async function handleShare() {
    if (!candidate) return;

    if (!shareAll && selectedRoles.length === 0) {
      setError("Pick at least one department, or choose Everyone.");
      return;
    }

    setSharing(true);
    setError(null);

    try {
      await createSharedPin({
        kind: candidate.kind,
        ref_id: candidate.refId ?? null,
        label: candidate.label,
        visibility: shareAll ? "all" : "roles",
        roles: shareAll ? undefined : selectedRoles,
      });
      setShared(true);
      setOpen(false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to share.");
    } finally {
      setSharing(false);
    }
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        disabled={isPinned}
        className="flex items-center gap-1.5 text-sm text-brand-teal hover:text-white transition disabled:opacity-40 disabled:cursor-default"
      >
        <PinIcon size={13} filled={isPinned || shared} />
        {isPinned ? "Pinned" : "Pin"}
      </button>

      {open && (
        <>
          {/* Click-outside catcher */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />

          <div className="absolute right-0 top-full mt-1 w-64 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl z-50 p-3 text-sm">
            {mode === "menu" ? (
              <div className="space-y-1">
                <button
                  onClick={() => {
                    onPinLocal();
                    setOpen(false);
                  }}
                  className="w-full text-left px-2 py-1.5 rounded hover:bg-zinc-800 transition"
                >
                  Only me
                </button>
                <button
                  onClick={() => setMode("share")}
                  className="w-full text-left px-2 py-1.5 rounded hover:bg-zinc-800 transition"
                >
                  Share with department(s)...
                </button>
              </div>
            ) : (
              <div className="space-y-2">
                <div className="font-brand text-[11px] font-bold uppercase tracking-wide text-zinc-500">
                  Share with
                </div>

                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    checked={shareAll}
                    onChange={(e) => setShareAll(e.target.checked)}
                  />
                  Everyone
                </label>

                {!shareAll && (
                  <div className="grid grid-cols-2 gap-1 pt-1">
                    {roles.map((r) => (
                      <label key={r} className="flex items-center gap-1.5 text-xs">
                        <input
                          type="checkbox"
                          checked={selectedRoles.includes(r)}
                          onChange={(e) =>
                            setSelectedRoles((prev) =>
                              e.target.checked ? [...prev, r] : prev.filter((x) => x !== r)
                            )
                          }
                        />
                        {ROLE_LABELS[r] ?? r}
                      </label>
                    ))}
                  </div>
                )}

                {error && <div className="text-[11px] text-[#EE3C25]">{error}</div>}

                <div className="flex items-center gap-3 pt-1">
                  <button
                    onClick={() => setMode("menu")}
                    className="text-xs text-zinc-500 hover:text-white transition"
                  >
                    Back
                  </button>
                  <button
                    onClick={handleShare}
                    disabled={sharing}
                    className="ml-auto text-xs px-3 py-1.5 brand-cta disabled:opacity-50"
                  >
                    {sharing ? "Sharing..." : "Share"}
                  </button>
                </div>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
