"use client";

// Standalone pop-out target for the OneNote-style Workspace board (session 76 follow-
// up, Sam: "make workspace removable (pop out in another window) for multiscreens").
// Same reasoning as app/panel/menudash/page.tsx and app/panel/workflow/page.tsx: this
// already makes its own real, authenticated API calls (GET/POST /workspace-board) and
// the session token lives in localStorage, shared across same-origin window.open()
// popups -- so this page just signs itself in the normal way and renders the exact
// same WorkspaceBoardBody component + useWorkspaceBoard hook the in-page Workspace
// column uses. No BroadcastChannel relay needed -- each window has its own live hook
// instance and its own debounced autosave, both reading/writing the same per-employee
// board on the backend.

import { useRequireAuth } from "@/lib/auth";
import { useWorkspaceBoard } from "@/lib/useWorkspaceBoard";
import { WorkspaceBoardBody } from "@/components/WorkspaceBoardBody";

export default function PanelWorkspaceBoardPage() {
  const session = useRequireAuth();
  const board = useWorkspaceBoard();

  if (!session) return null;

  function handlePrint() {
    requestAnimationFrame(() => requestAnimationFrame(() => window.print()));
  }

  return (
    <div className="h-screen flex flex-col bg-brand-ink text-white">
      <div className="relative flex items-center justify-between pl-5 pr-4 py-3 border-b border-zinc-800 shrink-0 bg-brand-charcoal overflow-hidden">
        <span className="absolute left-0 top-0 bottom-0 w-1.5 bg-[#EE3C25]" />
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-brand font-bold uppercase tracking-wide truncate">Notes &amp; Knowledge</span>
          <span className="text-xs text-zinc-500 ml-2 shrink-0 font-brand uppercase tracking-wider">— Workspace — popped out</span>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-3">
          {board.items.length > 0 && (
            <button
              onClick={handlePrint}
              title="Print your Workspace"
              className="text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500 transition"
            >
              🖨 Print
            </button>
          )}
          <button
            onClick={() => window.close()}
            className="text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500 transition"
          >
            Close window
          </button>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        <WorkspaceBoardBody board={board} />
      </div>
    </div>
  );
}
