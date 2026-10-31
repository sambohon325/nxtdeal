"use client";

// Entity 360 profile page — backs onto GET /profile/{entity_id} (core/profile_api.py,
// see BUILD_QUEUE.md's "Employee/Customer 360 profile view" entry). Rendering is shared
// with the workspace panel's inline profile view via components/EntityProfile.tsx —
// see that file's docstring. This standalone page is the permalink/deep-link form
// (reachable by clicking a connected entity from within a rendered profile); the entry
// point for looking a profile up in the first place is chat, in /workspace, as of
// session 21.

import { BrandLogo } from "@/components/BrandLogo";
import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { API_BASE } from "@/lib/api";
import {
  getSession,
  clearSession,
  authHeaders,
  isAuthError,
  type Session,
} from "@/lib/auth";
import { EntityProfileView, type Profile } from "@/components/EntityProfile";
import { BrandRibbon } from "@/components/BrandAngles";
import { LeadRecordModal } from "@/components/ProspectsBoard";
import { Customer360Panel } from "@/components/Customer360Panel";

export default function ProfilePage() {
  const router = useRouter();
  const params = useParams<{ id: string }>();

  const [session, setSession] = useState<Session | null | undefined>(
    undefined
  );

  const [profile, setProfile] = useState<Profile | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  // Bumped by LeadRecordModal's onChanged (a Lead was edited/converted/etc. while
  // this permalink page had it open) to force the profile fetch below to re-run
  // against the same params.id -- params.id itself wouldn't change, so it can't be
  // the trigger. Same fix as components/EntityDashPanel.tsx / app/panel/entity/
  // page.tsx's identical smart-route branches.
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    const existing = getSession();

    if (!existing) {
      router.push("/");
      return;
    }

    setSession(existing);
  }, [router]);

  useEffect(() => {
    if (!session || !params.id) return;

    let cancelled = false;

    async function load() {
      setLoading(true);
      setError(null);

      try {
        const response = await fetch(
          `${API_BASE}/profile/${encodeURIComponent(params.id)}`,
          { headers: authHeaders() }
        );

        const data = await response.json();

        if (isAuthError(data)) {
          clearSession();
          router.push("/");
          return;
        }

        if (cancelled) return;

        if (!response.ok || data.error) {
          setError(data.error ?? `Backend returned ${response.status}`);
          setProfile(null);
        } else {
          setProfile(data as Profile);
        }
      } catch (err) {
        if (cancelled) return;

        setError(
          err instanceof Error
            ? err.message
            : "Unable to reach NXTDeal backend."
        );
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    load();

    return () => {
      cancelled = true;
    };
  }, [session, params.id, router, refreshKey]);

  function handleSignOut() {
    clearSession();
    router.push("/");
  }

  if (!session) {
    return null;
  }

  // Lead and Customer both already have a much richer, purpose-built full-record
  // view elsewhere in this app (Sales' Prospects board / the Customer 360 engine
  // multiple departments share) than EntityProfileView's thin CustomerProfile
  // branch or its generic Lead fallback -- which used to just be a flat "Connected
  // Entities" list with no identity/associations/vehicle-interest/journey context
  // at all. Route straight to those existing, already-real components instead of
  // duplicating their content here, matching components/EntityDashPanel.tsx's and
  // app/panel/entity/page.tsx's identical smart-route branches. `onClose` goes
  // back to wherever this permalink was reached from, matching this page's own
  // existing "← Back" button behavior.
  if (!loading && !error && profile?.entity_type === "Lead") {
    return (
      <LeadRecordModal
        theme="dark"
        leadId={params.id}
        onClose={() => router.back()}
        onChanged={() => setRefreshKey((n) => n + 1)}
      />
    );
  }
  if (!loading && !error && profile?.entity_type === "Customer") {
    return <Customer360Panel theme="dark" customerId={params.id} onClose={() => router.back()} />;
  }

  return (
    <div className="h-screen overflow-hidden bg-[#111111] text-white flex flex-col">
      <header className="border-b border-zinc-900 px-8 py-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <BrandLogo />
          </div>

          <div className="flex items-center gap-6 text-sm">
            <span className="text-zinc-500">
              {session.employeeId} · {session.role}
            </span>
            <Link href="/workspace" className="text-zinc-500 hover:text-white">
              Workspace
            </Link>
            <button
              onClick={handleSignOut}
              className="text-zinc-500 hover:text-white transition"
            >
              Sign Out
            </button>
          </div>
        </div>
      </header>

      <BrandRibbon />

      <main className="flex-1 overflow-y-auto max-w-4xl w-full mx-auto p-8">
        <button
          onClick={() => router.back()}
          className="text-sm text-zinc-500 hover:text-white mb-6"
        >
          ← Back
        </button>

        {loading && <div className="text-zinc-500">Loading profile…</div>}

        {error && (
          <div className="bg-zinc-900 border border-[#EE3C25]/30 rounded-xl p-4 text-sm text-zinc-300">
            {error}
          </div>
        )}

        {!loading && !error && profile && (
          <EntityProfileView
            profile={profile}
            onSelect={(entityId) => router.push(`/profile/${entityId}`)}
          />
        )}
      </main>
    </div>
  );
}
