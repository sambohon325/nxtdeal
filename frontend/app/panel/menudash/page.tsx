"use client";

// Standalone pop-out target for a Top Menu Dash (session 60), same reasoning as
// app/panel/workflow/page.tsx (session 57): this already makes its own real,
// authenticated API calls (GET /menu/catalog, GET /menu/data) and the session token
// lives in localStorage, shared across same-origin window.open() popups -- so this
// page just signs itself in the normal way and renders the exact same MenuDashBody
// component the in-page collapsed-takeover panel uses. No BroadcastChannel relay
// needed.

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import { MenuDashBody } from "@/components/MenuDashPanel";

function PanelMenuDashContent() {
  const session = useRequireAuth();
  const params = useSearchParams();
  const department = params.get("department") ?? "";
  const initialItem = params.get("item") ?? "";
  const initialQuery = params.get("query") ?? "";

  const [itemKey, setItemKey] = useState(initialItem);

  if (!session) return null;

  if (!department || !itemKey) {
    return (
      <div className="min-h-screen bg-black text-white p-6 text-sm text-zinc-500">
        This window wasn&apos;t opened correctly — close it and use the pop-out button
        (⇱) on a Top Menu dash in the main NXTDeal workspace instead.
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-brand-ink text-white">
      <div className="relative flex items-center justify-between pl-5 pr-4 py-3 border-b border-zinc-800 shrink-0 bg-brand-charcoal overflow-hidden">
        <span className="absolute left-0 top-0 bottom-0 w-1.5 bg-brand-teal" />
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-brand font-bold uppercase tracking-wide truncate">{department}</span>
          <span className="text-xs text-zinc-500 ml-2 shrink-0 font-brand uppercase tracking-wider">— Top Menu — popped out</span>
        </div>
        <button
          onClick={() => window.close()}
          className="text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500 transition shrink-0 ml-3"
        >
          Close window
        </button>
      </div>

      <MenuDashBody department={department} itemKey={itemKey} onSelectItem={setItemKey} initialQuery={initialQuery} />
    </div>
  );
}

export default function PanelMenuDashPage() {
  return (
    <Suspense fallback={null}>
      <PanelMenuDashContent />
    </Suspense>
  );
}
