// Entitlements client + App Suite gating map (Freemium Platform roadmap, Phase 1, 2026-08-03).
//
// The tenant backend now enforces a Foundation-plus-Modules model: Tier 0 Foundation is free,
// and eight paid Modules (Sales, Service, Marketing, Finance, Operations, AI Workforce, Connect,
// Network Premium) gate the rest. This module lets the App Suite gate its own screens against
// that enforcement:
//   * getPublicEntitlements() reads GET /public/entitlements (no auth — a customer app has no
//     staff session) for the active-module set + owned levels.
//   * SCREEN_MODULE_REQUIREMENTS maps "<slug>:<screenKey>" -> the paid Module a screen requires,
//     following the same central-map pattern as components/apps/screens/index.tsx's WIRED map.
//     Screens NOT in the map are Foundation (free) and never gate.
//
// Under the default "reference" profile every Module is active, so nothing gates today — the
// machinery is real and testable by moving the dealer to the Foundation profile.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type PublicEntitlements = {
  active_modules: string[];
  module_levels: Record<string, string>;
};

// --- Authed admin surface (the in-product Add-Modules / entitlement management board) ---

export type ModuleState = { enabled: boolean; level: string };

export type EntitlementRecord = {
  id: string;
  profile: string;
  modules: Record<string, ModuleState>;
  caps: Record<string, number | null>;
  active_modules: string[];
  module_levels: Record<string, string>;
  updated_by: string | null;
  updated_at: string | null;
};

export type CatalogFeature = { key: string; name: string; level: string };
export type CatalogModule = {
  key: string;
  name: string;
  category: "foundation" | "module";
  tagline: string;
  features: CatalogFeature[];
};
export type EntitlementCatalog = {
  foundation_key: string;
  paid_modules: string[];
  levels: string[];
  modules: Record<string, CatalogModule>;
  usage_caps: Record<string, { name: string; unit: string; foundation_default: number; description: string }>;
  industry_launch_paths: Record<string, { label: string; recommended_modules: string[]; spoken: string[] }>;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function aget<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}
function apost<T>(path: string, body?: unknown): Promise<T> {
  return fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: body ? JSON.stringify(body) : undefined,
  }).then(handle<T>);
}

export function getEntitlements(): Promise<EntitlementRecord> {
  return aget<EntitlementRecord>("/entitlements");
}
export function getEntitlementCatalog(): Promise<EntitlementCatalog> {
  return aget<EntitlementCatalog>("/entitlements/catalog");
}
export function setEntitlementProfile(profile: "reference" | "foundation"): Promise<EntitlementRecord> {
  return apost<EntitlementRecord>("/entitlements/profile", { profile });
}
export function setEntitlementModule(module: string, enabled: boolean, level?: string): Promise<EntitlementRecord> {
  return apost<EntitlementRecord>("/entitlements/module", { module, enabled, level });
}
export function setEntitlementCap(cap: string, value: number | null): Promise<EntitlementRecord> {
  return apost<EntitlementRecord>("/entitlements/cap", { cap, value });
}

// Which paid Module each gated App Suite screen requires. Derived from the roadmap's
// "How the App Suite Maps to Foundation and Modules" section:
//   * MySales — free at every tier (personal-account-scoped); never listed here.
//   * Sales — pipeline/inventory/messages are the free CRM; desking + up-rotation are Sales.
//   * Receptionist — check-in/directory/team are free; the phone dialer is Connect; booking an
//     appointment is Sales (front-desk sales/showroom visits).
//   * Showroom — browsing/saved/messages are the free Foundation website; start-your-deal-online
//     (mydeal) is Digital Retail = Sales.
//   * My Garage — the consumer hook (vehicles/equity/service-history/recall lookup, showroom,
//     messages) is free; booking work + approvals/status of active ROs + service alerts are
//     Service.
//   * Service Kiosk + Service Operations — shop-floor execution, entirely Service.
export const SCREEN_MODULE_REQUIREMENTS: Record<string, string> = {
  // Sales (dealer)
  "salesapp:ups": "sales",
  "salesapp:desking": "sales",
  // Receptionist
  "reception:appointments": "sales",
  "reception:desk": "connect",
  // Showroom (customer)
  "showroom:mydeal": "sales",
  // My Garage (customer)
  "mygarage:book": "service",
  "mygarage:approvals": "service",
  "mygarage:status": "service",
  "mygarage:alerts": "service",
  // Service Kiosk (customer, shop floor)
  "kiosk:checkin": "service",
  "kiosk:queue": "service",
  "kiosk:amenities": "service",
  // Service Operations (staff, shop floor)
  "serviceops:roboard": "service",
  "serviceops:inspections": "service",
  "serviceops:techs": "service",
  "serviceops:manager": "service",
};

// Display copy for the locked-state UI, mirroring core/entitlements.py's MODULE_CATALOG so a
// customer app doesn't need an authenticated catalog fetch to render a nice upgrade prompt.
export const MODULE_LABELS: Record<string, { name: string; tagline: string }> = {
  sales: { name: "Sales Module", tagline: "Turn the free CRM pipeline into a closing machine." },
  service: { name: "Service Module", tagline: "Run the shop: repair orders, inspections, parts, and the floor." },
  marketing: { name: "Marketing Module", tagline: "From the free inventory site to a full marketing engine." },
  finance: { name: "Finance Module", tagline: "Contracting through funding — plus BHPH, collections, and payments." },
  operations: { name: "Operations Module", tagline: "Recon, compliance, delivery, and task management." },
  ai_workforce: { name: "AI Workforce Module", tagline: "Let the Workforce AI Viewer's recommendations actually execute." },
  connect: { name: "Connect Module", tagline: "Phone, SMS, chat, recording, and conversation intelligence." },
  network_premium: { name: "Network Premium Module", tagline: "Upgrade the free Network hook into forecasting and advisory intelligence." },
};

export function requiredModuleFor(slug: string, screenKey: string): string | undefined {
  return SCREEN_MODULE_REQUIREMENTS[`${slug}:${screenKey}`];
}

// Single in-flight fetch shared across every screen on the page (the active-module set is the
// same for the whole app), so switching tabs doesn't re-hit the endpoint.
let _cache: Promise<PublicEntitlements> | null = null;

export function getPublicEntitlements(): Promise<PublicEntitlements> {
  if (!_cache) {
    _cache = fetch(`${API_BASE}/public/entitlements`)
      .then((r) => r.json())
      .then((d) => ({
        active_modules: Array.isArray(d?.active_modules) ? d.active_modules : [],
        module_levels: d?.module_levels ?? {},
      }))
      .catch(() => {
        // On any error, fail OPEN in the UI: treat everything as active so a transient fetch
        // failure never hides a screen the dealer is entitled to. The backend remains the real
        // gate for any write.
        _cache = null;
        return { active_modules: ["__all__"], active: true } as unknown as PublicEntitlements;
      });
  }
  return _cache;
}

// A screen is allowed if it requires no module, or the required module is active (or the
// fail-open sentinel is present).
export function screenAllowed(ent: PublicEntitlements | null, requiredModule?: string): boolean {
  if (!requiredModule) return true;
  if (!ent) return true; // still loading — don't flash a lock
  if (ent.active_modules.includes("__all__")) return true;
  return ent.active_modules.includes(requiredModule);
}
