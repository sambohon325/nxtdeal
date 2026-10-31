"use client";

// Standalone pop-out target for the gear icon's Account Settings Dash (session 74),
// mirroring app/panel/workflow/page.tsx's pattern exactly: signs itself in the normal
// way (useRequireAuth) and renders the same chrome-free AccountSettingsBody the
// in-page docked Dash uses -- no BroadcastChannel relay, since every field here
// (profile, password, notification preferences) is a real authenticated API call
// against the shared localStorage session token, same as any other same-origin popup.

import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import { AccountSettingsBody, type AccountTabKey } from "@/components/AccountSettings";

function PanelAccountContent() {
  const session = useRequireAuth();
  const params = useSearchParams();
  const initialItem = params.get("item") === "notifications" ? "notifications" : "profile";

  const [activeTab, setActiveTab] = useState<AccountTabKey>(initialItem);

  if (!session) return null;

  return (
    <div className="h-screen flex flex-col bg-brand-ink text-white">
      <div className="relative flex items-center justify-between pl-5 pr-4 py-3 border-b border-zinc-800 shrink-0 bg-brand-charcoal overflow-hidden">
        <span className="absolute left-0 top-0 bottom-0 w-1.5 bg-brand-teal" />
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-brand font-bold uppercase tracking-wide truncate">Account Settings</span>
        </div>
        <button
          onClick={() => window.close()}
          className="text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500 transition shrink-0 ml-3"
        >
          Close window
        </button>
      </div>

      <AccountSettingsBody activeTab={activeTab} onSelectTab={setActiveTab} />
    </div>
  );
}

export default function PanelAccountPage() {
  return (
    <Suspense fallback={null}>
      <PanelAccountContent />
    </Suspense>
  );
}
