"use client";

// Session 76 fifth follow-up. Sam, on the entity-ID links added the previous pass
// (any real NXTDeal ID -- VEH-00042, CUST-00001, ... -- surfaced inside a Top Menu
// Dash or a job-workflow window): "instead of clicking the link and it opening in a
// new tab - can it pop up in a modal when you hover over it, with the option to pop it
// out into a new window or to push into the dash / sub menu area."
//
// Replaces the plain `<a href="/profile/{id}" target="_blank">` this component's two
// call sites (components/MenuDashPanel.tsx's JsonValue, components/
// DepartmentWorkflowButtons.tsx's ValuePreview) used previously. Hovering shows a small
// floating preview card (fetched from GET /entity/{id} -- the same lightweight
// {id, entity_type, attributes} shape used throughout this app, not the heavier
// /profile/{id} 360 view) with two real actions:
//   - "Open in Dash" -- pushes the entity into the current page's own docked Dash
//     takeover (components/EntityDashPanel.tsx) via lib/entityLinkContext.tsx's
//     openInDash(), reusing the exact same charcoal panel the Top Menu / job-workflow /
//     account Dashes already share. Only available where a page has wired the
//     EntityLinkActionsProvider (all four department pages do).
//   - "Pop out" -- opens a real, independent OS window
//     (app/panel/entity/page.tsx) keyed by this specific entity's ID
//     (`dealeros_entity_${id}`), NOT routed through `menuDash.popOut()`. Deliberately
//     independent of any Dash-takeover state: popping out an entity shouldn't disturb
//     whatever Dash (if any) is currently open on the page behind it, and keying the
//     window name per-entity (rather than the single shared "dealeros_dash" slot every
//     other Dash pop-out uses) lets someone pop out a Customer and a Vehicle into two
//     separate windows at once, which a hover-preview workflow makes much more likely
//     than the deliberate one-Dash-at-a-time job-workflow/Top-Menu flows.
import { useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { displayName, type EntitySummary } from "@/components/EntityProfile";
import { useEntityLinkActions } from "@/lib/entityLinkContext";
import { searchVehicleByVin } from "@/lib/vinDecoder";

// Module-level cache -- a hovered ID very often gets hovered more than once in a
// session (re-opening the same workflow window, scrolling past it again), and this is
// a lightweight single-entity fetch with no reason to hit the backend twice for the
// same ID. Deliberately unbounded (this app's entity IDs are a small, session-scale
// working set) -- matches components/DepartmentWorkflowButtons.tsx's cachedCatalog
// pattern.
const previewCache = new Map<string, EntitySummary | { error: string } | "loading">();
const listeners = new Map<string, Set<() => void>>();

function notify(id: string) {
  listeners.get(id)?.forEach((fn) => fn());
}

function fetchPreview(id: string) {
  if (previewCache.has(id)) return;
  previewCache.set(id, "loading");

  fetch(`${API_BASE}/entity/${encodeURIComponent(id)}`, { headers: { ...authHeaders() } })
    .then((r) => r.json())
    .then((d) => {
      previewCache.set(id, d.error ? { error: d.error } : (d as EntitySummary));
      notify(id);
    })
    .catch(() => {
      previewCache.set(id, { error: "Unable to reach NXTDeal backend." });
      notify(id);
    });
}

function usePreview(id: string, enabled: boolean) {
  const [, forceRender] = useState(0);

  useEffect(() => {
    if (!enabled) return;

    fetchPreview(id);

    const fn = () => forceRender((n) => n + 1);
    if (!listeners.has(id)) listeners.set(id, new Set());
    listeners.get(id)!.add(fn);

    return () => {
      listeners.get(id)?.delete(fn);
    };
  }, [id, enabled]);

  return previewCache.get(id);
}

function popOutEntity(id: string) {
  window.open(
    `/panel/entity?id=${encodeURIComponent(id)}`,
    `dealeros_entity_${id}`,
    "width=900,height=760"
  );
}

function PreviewCard({ id, onNavigate }: { id: string; onNavigate: () => void }) {
  const preview = usePreview(id, true);
  const actions = useEntityLinkActions();

  const entity: EntitySummary | null =
    preview && preview !== "loading" && !("error" in preview) ? preview : null;

  const attrs = entity ? Object.entries(entity.attributes ?? {}).slice(0, 4) : [];

  function handleOpenInDash() {
    actions?.openInDash(id);
    onNavigate();
  }

  function handlePopOut() {
    popOutEntity(id);
    onNavigate();
  }

  return (
    <div
      className="absolute z-50 top-full left-0 mt-1 w-64 rounded-lg border border-zinc-700 bg-zinc-900 shadow-xl text-left"
      // Stop the hover-out timer on the parent from firing while the pointer is
      // inside the card itself (moving from the trigger text down into the buttons).
      onMouseEnter={(e) => e.stopPropagation()}
    >
      <div className="p-3 border-b border-zinc-800">
        {preview === "loading" || preview === undefined ? (
          <div className="text-xs text-zinc-500">Loading…</div>
        ) : preview && "error" in preview ? (
          <div className="text-xs text-zinc-500">{preview.error}</div>
        ) : (
          <>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-zinc-100 truncate">
                {entity ? displayName(entity) : id}
              </span>
              <span className="text-[10px] uppercase tracking-wider text-zinc-500 shrink-0 ml-2">
                {entity?.entity_type}
              </span>
            </div>
            {attrs.length > 0 && (
              <div className="text-[11px] text-zinc-500 space-y-0.5">
                {attrs.map(([k, v]) => (
                  <div key={k} className="truncate">
                    {k}: {String(v)}
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>

      <div className="flex items-center gap-1.5 p-2">
        <button
          onClick={handlePopOut}
          title="Open in a separate window"
          className="flex-1 text-[11px] px-2 py-1.5 rounded border border-zinc-700 text-zinc-300 hover:text-white hover:border-zinc-500 transition"
        >
          ⇱ Pop out
        </button>
        {actions && (
          <button
            onClick={handleOpenInDash}
            title="Open in this page's Dash / sub-menu area"
            className="flex-1 text-[11px] px-2 py-1.5 rounded bg-[#3FBCC4] text-black font-medium hover:bg-white transition"
          >
            📥 Open in Dash
          </button>
        )}
      </div>
    </div>
  );
}

export function EntityHoverLink({
  id,
  displayText,
  className,
}: {
  id: string;
  // Session 76 sixth follow-up (VIN clickability): what to SHOW isn't always what to
  // FETCH/act on -- VinHoverLink below resolves a raw VIN string to its real Vehicle
  // id and hands that id to this component, but the visible/clickable text should stay
  // the VIN itself, not the resolved VEH-00042. Defaults to `id` so every existing call
  // site (which only ever passed a real NXTDeal id and expected it as the label) is
  // completely unaffected.
  displayText?: string;
  className?: string;
}) {
  const [hovering, setHovering] = useState(false);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const actions = useEntityLinkActions();

  function open() {
    if (closeTimer.current) {
      clearTimeout(closeTimer.current);
      closeTimer.current = null;
    }
    setHovering(true);
  }

  function scheduleClose() {
    closeTimer.current = setTimeout(() => setHovering(false), 150);
  }

  useEffect(() => {
    return () => {
      if (closeTimer.current) clearTimeout(closeTimer.current);
    };
  }, []);

  return (
    <span
      className="relative inline-block"
      onMouseEnter={open}
      onMouseLeave={scheduleClose}
    >
      <button
        type="button"
        onClick={() => (actions ? actions.openInDash(id) : popOutEntity(id))}
        className={`${className ?? ""} text-[#3FBCC4] underline decoration-dotted hover:text-white transition cursor-pointer bg-transparent border-0 p-0 font-inherit`}
      >
        {displayText ?? id}
      </button>

      {hovering && <PreviewCard id={id} onNavigate={() => setHovering(false)} />}
    </span>
  );
}

// --- VIN resolution -----------------------------------------------------------
// Session 76 sixth follow-up. Sam: "i can't click on a vin number thats attached to a
// car to start a process, or to pull up that cars information." A VIN isn't itself a
// NXTDeal entity id -- it has to be resolved to the real Vehicle it belongs to first
// (via lib/vinDecoder.ts's searchVehicleByVin, which reuses the existing, already
// role-filtered GET /search?q= endpoint -- no new backend route needed) before any of
// the id-keyed machinery above (preview fetch, pop-out, open-in-Dash) can act on it.
// Shares the same "module-level cache + listener set, one fetch per distinct value"
// shape as the entity-id preview cache above, so a VIN repeated many times on one
// screen (a long inventory list) or in one chat thread only ever resolves once.
type VinResolution = "loading" | "not_found" | { vehicleId: string };

const vinResolveCache = new Map<string, VinResolution>();
const vinListeners = new Map<string, Set<() => void>>();

function notifyVin(vin: string) {
  vinListeners.get(vin)?.forEach((fn) => fn());
}

function resolveVin(vin: string) {
  if (vinResolveCache.has(vin)) return;
  vinResolveCache.set(vin, "loading");

  searchVehicleByVin(vin)
    .then((matches) => {
      const hit = matches[0];
      vinResolveCache.set(vin, hit ? { vehicleId: hit.id } : "not_found");
      notifyVin(vin);
    })
    .catch(() => {
      vinResolveCache.set(vin, "not_found");
      notifyVin(vin);
    });
}

function useVinResolution(vin: string): VinResolution {
  const [, forceRender] = useState(0);

  useEffect(() => {
    resolveVin(vin);

    const fn = () => forceRender((n) => n + 1);
    if (!vinListeners.has(vin)) vinListeners.set(vin, new Set());
    vinListeners.get(vin)!.add(fn);

    return () => {
      vinListeners.get(vin)?.delete(fn);
    };
  }, [vin]);

  return vinResolveCache.get(vin) ?? "loading";
}

// Resolves a raw VIN string to its real Vehicle, then delegates to EntityHoverLink's
// full hover-preview/pop-out/open-in-Dash behavior with the VIN itself kept as the
// visible label. Degrades gracefully rather than ever showing a dead link: still
// loading -> plain (non-clickable) text; no matching vehicle on file -> plain text
// with an explanatory title, never a fabricated match.
export function VinHoverLink({ vin, className }: { vin: string; className?: string }) {
  const resolution = useVinResolution(vin);

  if (resolution === "loading") {
    return <span className={className}>{vin}</span>;
  }
  if (resolution === "not_found") {
    return (
      <span className={className} title="No matching vehicle on file for this VIN">
        {vin}
      </span>
    );
  }
  return <EntityHoverLink id={resolution.vehicleId} displayText={vin} className={className} />;
}

// The bare async resolve/cache primitives above, exported for a lighter-weight
// consumer that doesn't want the full hover-preview card -- components/
// MessageContent.tsx's inline chat-message VIN links, which only need a click
// action, not a hover card (chat bubbles are transient and narrow).
export function resolveVinToVehicleId(vin: string): Promise<string | null> {
  return searchVehicleByVin(vin).then((matches) => matches[0]?.id ?? null);
}
