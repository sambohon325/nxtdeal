"use client";

// Standalone pop-out target for a department workflow window (session 57). Sam: "i'd
// also like the ability to pull the modals out of the browser and move to a second
// screen like we did for the workspace, so people can have more than 1 screen and use
// that functionality."
//
// Deliberately NOT the same BroadcastChannel-relay pattern as app/panel/page.tsx (the
// main workspace panel's pop-out) -- that pattern was chosen there specifically to stay
// auth-free for a customer-facing "show them the screen" use case. A workflow window is
// different: it already makes its own real, authenticated API calls (start/advance/
// tab-data, all in components/DepartmentWorkflowButtons.tsx's WorkflowWindowBody), and
// the session token lives in localStorage, which is shared across same-origin windows
// including window.open() popups. So this page just signs itself in the normal way
// (useRequireAuth, same guard /workspace and friends use) and renders the exact same
// WorkflowWindowBody component the in-page floating window uses -- no relay, no parent
// round-trip, and no state to sync back on close since every field it shows is live off
// the graph regardless of which window is displaying it.

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import {
  fetchCatalog,
  WorkflowWindowBody,
  DASH_ACCENT,
  type Catalog,
} from "@/components/DepartmentWorkflowButtons";

function PanelWorkflowContent() {
  const session = useRequireAuth();
  const params = useSearchParams();
  const department = params.get("department") ?? "";
  const key = params.get("key") ?? "";

  const [catalog, setCatalog] = useState<Catalog | null>(null);

  useEffect(() => {
    fetchCatalog().then(setCatalog);
  }, []);

  if (!session) return null;

  if (!catalog) {
    return <div className="min-h-screen bg-zinc-950 text-white p-6 text-sm text-zinc-500">Loading…</div>;
  }

  const workflows = catalog[department] ?? [];
  const workflow = workflows.find((w) => w.key === key);

  if (!workflow) {
    return (
      <div className="min-h-screen bg-zinc-950 text-white p-6 text-sm text-zinc-500">
        This window wasn&apos;t opened correctly — close it and use the pop-out button
        (⇱) on a workflow window in the main NXTDeal workspace instead.
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-brand-ink text-white">
      <div className="relative flex items-center justify-between pl-5 pr-4 py-3 border-b border-zinc-800 shrink-0 bg-brand-charcoal overflow-hidden">
        <span className="absolute left-0 top-0 bottom-0 w-1.5 bg-brand-teal" />
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-brand font-bold uppercase tracking-wide truncate">{department}</span>
          <span className="text-xs text-zinc-500 shrink-0 font-brand uppercase tracking-wider">
            — {workflow.title}
          </span>
        </div>
        <button
          onClick={() => window.close()}
          className="text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500 transition shrink-0 ml-3"
        >
          Close window
        </button>
      </div>

      <WorkflowWindowBody workflow={workflow} color={DASH_ACCENT} onRequestClose={() => window.close()} />
    </div>
  );
}

export default function PanelWorkflowPage() {
  return (
    <Suspense fallback={null}>
      <PanelWorkflowContent />
    </Suspense>
  );
}
