"use client";

// Standalone pop-out target for a hovered entity link (session 76 fifth follow-up,
// components/EntityHoverLink.tsx's "⇱ Pop out" action). Mirrors app/panel/account/
// page.tsx and app/panel/workflow/page.tsx's pattern exactly: signs itself in the
// normal way (useRequireAuth) and makes its own real, authenticated GET /profile/{id}
// call off the shared localStorage session token -- no BroadcastChannel relay needed.
// Deliberately keyed by entity ID at the window.open() call site
// (`dealeros_entity_${id}`, not the single shared "dealeros_dash" slot every other Dash
// pop-out reuses) so popping out a Customer and a Vehicle at the same time opens two
// independent windows rather than replacing one another.

import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { API_BASE } from "@/lib/api";
import { useRequireAuth, authHeaders } from "@/lib/auth";
import {
  EntityProfileView,
  displayName,
  type Profile,
  type EntitySummary,
  type CustomerProfile,
  type EmployeeProfile,
  type VehicleProfile,
} from "@/components/EntityProfile";
import { LeadRecordModal } from "@/components/ProspectsBoard";
import { Customer360Panel } from "@/components/Customer360Panel";

// Explicit casts rather than relying on entity_type-based narrowing here --
// FallbackProfile's `entity_type` is typed as plain `string` (not a literal, since it
// covers whatever unrecognized entity types the backend might send), so TypeScript
// can't prove it's excluded by a `=== "Customer"` check the way it could with a fully
// literal discriminated union. Same fallback-cast pattern the last line already used.
function rootEntityOf(profile: Profile): EntitySummary | null {
  if (profile.entity_type === "Customer") return (profile as CustomerProfile).customer;
  if (profile.entity_type === "Employee") return (profile as EmployeeProfile).employee;
  if (profile.entity_type === "Vehicle") return (profile as VehicleProfile).vehicle;
  return (profile as { entity: EntitySummary | null }).entity ?? null;
}

function PanelEntityContent() {
  const session = useRequireAuth();
  const params = useSearchParams();
  const initialId = params.get("id") ?? "";

  const [currentId, setCurrentId] = useState(initialId);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumped by LeadRecordModal's onChanged (a Lead was edited/converted/etc. while
  // this popped-out window had it open) to force a re-fetch against the same
  // currentId -- currentId itself wouldn't change, so it can't be the trigger.
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    if (!session || !currentId) return;

    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/profile/${encodeURIComponent(currentId)}`, { headers: { ...authHeaders() } })
      .then((r) => r.json())
      .then((data) => {
        if (cancelled) return;
        if (data.error) {
          setError(data.error);
          setProfile(null);
        } else {
          setProfile(data as Profile);
        }
      })
      .catch(() => {
        if (!cancelled) setError("Unable to reach NXTDeal backend.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [session, currentId, refreshKey]);

  if (!session) return null;

  const root = profile ? rootEntityOf(profile) : null;

  // Same smart-route as components/EntityDashPanel.tsx's identical fix -- a
  // popped-out Lead/Customer window should show that entity's own real,
  // purpose-built full-record view (Prospects' LeadRecordModal / the shared
  // Customer 360 engine), not EntityProfileView's thin Customer branch or its
  // generic "Connected Entities" Lead fallback. `onClose` closes the OS window
  // itself here, matching this page's own existing "Close window" behavior.
  if (!loading && !error && profile?.entity_type === "Lead") {
    return (
      <LeadRecordModal
        theme="dark"
        leadId={currentId}
        onClose={() => window.close()}
        onChanged={() => setRefreshKey((n) => n + 1)}
      />
    );
  }
  if (!loading && !error && profile?.entity_type === "Customer") {
    return <Customer360Panel theme="dark" customerId={currentId} onClose={() => window.close()} />;
  }

  return (
    <div className="h-screen flex flex-col bg-brand-ink text-white">
      <div className="relative flex items-center justify-between pl-5 pr-4 py-3 border-b border-zinc-800 shrink-0 bg-brand-charcoal overflow-hidden">
        <span className="absolute left-0 top-0 bottom-0 w-1.5 bg-brand-teal" />
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-brand font-bold uppercase tracking-wide truncate">
            {root ? displayName(root) : currentId}
          </span>
          <span className="text-xs text-zinc-500 shrink-0 font-brand uppercase tracking-wider">
            — {profile?.entity_type ?? "Entity"} Profile
          </span>
        </div>
        <button
          onClick={() => window.close()}
          className="text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500 transition shrink-0 ml-3"
        >
          Close window
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-5">
        {loading ? (
          <div className="text-sm text-zinc-600">Loading…</div>
        ) : error ? (
          <div className="bg-zinc-900 border border-[#EE3C25]/30 rounded-xl p-4 text-sm text-zinc-300">
            {error}
          </div>
        ) : profile ? (
          <EntityProfileView profile={profile} onSelect={setCurrentId} />
        ) : null}
      </div>
    </div>
  );
}

export default function PanelEntityPage() {
  return (
    <Suspense fallback={null}>
      <PanelEntityContent />
    </Suspense>
  );
}
