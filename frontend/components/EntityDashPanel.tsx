"use client";
import { WorkButton } from "./WorkspaceUi";

// The "push into the dash / sub menu area" destination for a hovered entity link
// (session 76 fifth follow-up, components/EntityHoverLink.tsx). Same charcoal-chrome
// docked-panel shape as components/MenuDashPanel.tsx's MenuDashPanel/
// components/DepartmentWorkflowButtons.tsx's WorkflowDashPanel/
// components/AccountSettings.tsx's AccountDashPanel -- a job-workflow Dash, a Top Menu
// Dash, an Account Dash, and now an arbitrary-entity Dash are all visually
// indistinguishable except for their content, matching this app's established "same
// grey UI" rule (session 72).
//
// Fetches GET /profile/{id} (the full 360 view, core/profile_api.py) and renders it
// through the same components/EntityProfile.tsx used by the standalone /profile/[id]
// permalink page and the old inline workspace-panel profile view -- including the
// Explore Connections section (components/ConnectionsExplorer.tsx). `onSelect` drills
// into a connected entity WITHOUT leaving the Dash (re-fetches in place, same "stay
// docked" behavior every other Dash in this app already has) rather than navigating
// away, matching /profile/[id]'s own "stay in the workspace panel" precedent from
// session 21.
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
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
// FallbackProfile's `entity_type` is typed as plain `string` (not a literal), so
// TypeScript can't prove it's excluded by a `=== "Customer"` check the way it could
// with a fully literal discriminated union. Same fix as app/panel/entity/page.tsx's
// identical helper (session 87 -- this duplicate is what a real `next build` caught).
function rootEntityOf(profile: Profile): EntitySummary | null {
  if (profile.entity_type === "Customer") return (profile as CustomerProfile).customer;
  if (profile.entity_type === "Employee") return (profile as EmployeeProfile).employee;
  if (profile.entity_type === "Vehicle") return (profile as VehicleProfile).vehicle;
  return (profile as { entity: EntitySummary | null }).entity ?? null;
}

export function EntityDashPanel({
  entityId,
  theme = "dark",
  onClose,
  onPopOut,
}: {
  entityId: string;
  theme?: "light" | "dark";
  onClose: () => void;
  onPopOut: () => void;
}) {
  const [currentId, setCurrentId] = useState(entityId);
  const [history, setHistory] = useState<string[]>([]);
  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumped by LeadRecordModal's onChanged (a Lead was edited/converted/etc. while
  // this Dash had it open) to force the profile fetch below to re-run against the
  // same currentId -- currentId itself wouldn't change, so it can't be the trigger.
  const [refreshKey, setRefreshKey] = useState(0);

  // A new entity pushed into an already-open Dash (re-clicking a different hover
  // link) should reset to that entity, not keep whatever was last drilled into.
  useEffect(() => {
    setCurrentId(entityId);
    setHistory([]);
  }, [entityId]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/profile/${encodeURIComponent(currentId)}`, { headers: { ...authHeaders() } })
      .then(async (r) => { const data = await r.json(); if (!r.ok) throw new Error(data.error || "This record could not be loaded."); return data; })
      .then((data) => {
        if (cancelled) return;
        if (data.error) {
          setError(data.error);
          setProfile(null);
        } else {
          setProfile(data as Profile);
        }
      })
      .catch((error) => {
        if (!cancelled) setError(error instanceof Error ? error.message : "This record could not be loaded.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [currentId, refreshKey]);

  const root = profile ? rootEntityOf(profile) : null;

  // Lead and Customer both already have a much richer, purpose-built full-record
  // view elsewhere in this app (Sales' Prospects board / the Customer 360 engine
  // multiple departments share) than EntityProfileView's thin CustomerProfile
  // branch or its generic Lead fallback -- which used to just be a flat
  // "Connected Entities" list with no identity/associations/vehicle-interest/
  // journey context at all. Route straight to those existing, already-real
  // components instead of duplicating their content here -- same data, same
  // component, no second maintenance surface. Both render as their own
  // full-screen `fixed inset-0` overlay, so this replaces the docked panel
  // chrome entirely rather than nesting inside it. `setCurrentId` re-fires this
  // same fetch/branch whenever someone drills further in from inside one of
  // these richer views, so a Lead's "Convert to Customer" flow (or any other
  // cross-entity link) correctly hands off into the Customer 360 view too.
  if (!loading && !error && profile?.entity_type === "Lead") {
    return (
      <LeadRecordModal
        inline
        theme={theme}
        leadId={currentId}
        onClose={onClose}
        onChanged={() => setRefreshKey((n) => n + 1)}
      />
    );
  }
  if (!loading && !error && profile?.entity_type === "Customer") {
    return <Customer360Panel inline theme={theme} customerId={currentId} onClose={onClose} />;
  }

  return (
    <div data-department-work="" data-record-detail="" className="flex-1 min-w-0 flex flex-col bg-brand-ink border-x border-zinc-800">
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
        <div className="flex items-center gap-3 shrink-0 ml-3">
          <WorkButton type="submit"
            onClick={onPopOut}
            aria-label="Open record in a separate view" title="Open record in a separate view"
            className="text-zinc-400 hover:text-white transition text-sm leading-none"
          >
            ⇱
          </WorkButton>
          <WorkButton type="submit" aria-label="Close record" onClick={onClose} className="text-zinc-400 hover:text-white transition text-lg leading-none">
            ×
          </WorkButton>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {history.length > 0 && <WorkButton type="submit" className="record-back" onClick={()=>{setCurrentId(history[history.length-1]);setHistory(previous=>previous.slice(0,-1));}}>← Previous record</WorkButton>}
        {loading ? (
          <div role="status" className="text-sm text-zinc-600">Loading record…</div>
        ) : error ? (
          <div role="alert" className="bg-zinc-900 border border-[#EE3C25]/30 rounded-xl p-4 text-sm text-zinc-300">
            {error}<WorkButton type="submit" className="record-back" onClick={()=>setRefreshKey(value=>value+1)}>Try again</WorkButton>
          </div>
        ) : profile ? (
          <EntityProfileView profile={profile} onSelect={id=>{setHistory(previous=>[...previous,currentId]);setCurrentId(id);}} />
        ) : null}
      </div>
    </div>
  );
}
