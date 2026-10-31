"use client";
import { WorkField } from "./WorkField";

// The single "pin your whole Workspace to Knowledge" action (session 76 third follow-
// up). Sam: "we need to move the pin to knowledge out of the reports and notes
// windows and put it into the workspace as a whole -- the idea being they pin
// everything in their workspace as one knowledge point. when they do that, they need
// to be able to title it what they want and set viewing permissions."
//
// Modeled directly on components/PinShareButton.tsx's "Only me" / "Share with
// department(s)..." popover (same createSharedPin/lib/pins.ts split), with one
// addition: a title input, since a whole-board pin needs a name the owner picks
// (unlike a per-entity pin, which can derive a reasonable label from context).
// refId is always the pinning employee's own employee_id -- see lib/pins.ts's
// "workspace_board" PinKind comment for how that doubles as the lookup key for
// core/workspace_board_api.py's get_shared_workspace_board_api.

import { useEffect, useState } from "react";
import { PinIcon } from "@/components/Icons";
import { fetchShareRoles, createSharedPin, ROLE_LABELS } from "@/lib/sharedKnowledge";

export function PinWorkspaceButton({
  refId,
  disabled,
  isPinned,
  defaultTitle,
  onPinLocal,
}: {
  refId: string;
  disabled?: boolean;
  isPinned: boolean;
  defaultTitle: string;
  onPinLocal: (title: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<"menu" | "share">("menu");
  const [title, setTitle] = useState(defaultTitle);
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
    if (open) {
      setTitle(defaultTitle);
    } else {
      setMode("menu");
      setError(null);
    }
  }, [open, defaultTitle]);

  function handlePinLocal() {
    const trimmed = title.trim();

    if (!trimmed) {
      setError("Give your Workspace a title first.");
      return;
    }

    onPinLocal(trimmed);
    setOpen(false);
  }

  async function handleShare() {
    const trimmed = title.trim();

    if (!trimmed) {
      setError("Give your Workspace a title first.");
      return;
    }

    if (!shareAll && selectedRoles.length === 0) {
      setError("Pick at least one department, or choose Everyone.");
      return;
    }

    setSharing(true);
    setError(null);

    try {
      await createSharedPin({
        kind: "workspace_board",
        ref_id: refId,
        label: trimmed,
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

  if (disabled) {
    return (
      <span className="text-sm text-zinc-700 cursor-default" title="Add something to your Workspace first">
        📌 Pin Workspace
      </span>
    );
  }

  return (
    <div className="relative">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1.5 text-sm text-[#FBCF09] hover:text-white transition"
      >
        <PinIcon size={13} filled={isPinned || shared} />
        {isPinned || shared ? "Workspace Pinned" : "Pin Workspace"}
      </button>

      {open && (
        <>
          {/* Click-outside catcher */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />

          <div className="absolute right-0 top-full mt-1 w-72 bg-zinc-900 border border-zinc-700 rounded-lg shadow-xl z-50 p-3 text-sm space-y-2">


            <WorkField label="Pin your whole Workspace"><input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Title this Knowledge point…"
              className="w-full text-xs bg-zinc-950 border border-zinc-700 rounded px-2 py-1.5 focus:outline-none focus:border-[#3FBCC4] placeholder:text-zinc-600"
            /></WorkField>

            {mode === "menu" ? (
              <div className="space-y-1">
                <button
                  onClick={handlePinLocal}
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

            {error && <div className="text-[11px] text-[#EE3C25]">{error}</div>}
          </div>
        </>
      )}
    </div>
  );
}
