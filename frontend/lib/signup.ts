// Self-serve signup client (NXTDeal Free Forever funnel, 2026-08-03). The marketing "Start Free"
// portal posts here; the target is the HUB's public signup endpoint (hub/core/dealer_signup.py via
// hub/app_signup_routes.py), which creates a real free Foundation dealer account and starts
// provisioning — HubSpot-style, no sales step. Public: no auth token (this is the marketing site).

// The Hub base URL (same env var the Hub client uses). On the marketing deployment this points at
// hub.dealeros.xyz's API.
const HUB_API_BASE = process.env.NEXT_PUBLIC_HUB_API_URL ?? "http://127.0.0.1:9000";

export type BusinessType = {
  key: string;
  label: string;
  suggested_modules: string[];
};

export type SignupInput = {
  name: string;
  work_email: string;
  dealership_name: string;
  business_type: string;
  contact_phone?: string;
  network_opt_in?: boolean;
};

export type SignupResult = {
  ok?: boolean;
  dealer_id?: string;
  slug?: string;
  instance_url?: string;
  plan_tier?: string;
  seat_count?: number;
  suggested_modules?: string[];
  industry_type?: string;
  business_type?: string;
  status?: string;
  warnings?: string[];
  error?: string;
  field?: string;
  reason?: string;
};

// The six business types, mirrored from hub/core/dealer_signup.py BUSINESS_TYPES so the selector
// renders instantly without waiting on the Hub (and works even if the Hub is briefly unreachable).
// getBusinessTypes() can refresh these from the Hub when available.
export const BUSINESS_TYPES: BusinessType[] = [
  { key: "franchise", label: "Franchise Dealership", suggested_modules: ["sales", "service", "marketing"] },
  { key: "independent", label: "Independent Dealership", suggested_modules: ["sales", "marketing"] },
  { key: "bhph", label: "Buy-Here-Pay-Here", suggested_modules: ["finance", "operations"] },
  { key: "finance_company", label: "Finance Company", suggested_modules: ["finance", "service"] },
  { key: "dealer_group", label: "Dealer Group", suggested_modules: ["network_premium", "sales", "service"] },
  { key: "service_only", label: "Service-Only Operation", suggested_modules: ["service"] },
];

export async function getBusinessTypes(): Promise<BusinessType[]> {
  try {
    const r = await fetch(`${HUB_API_BASE}/public/signup/business-types`);
    const d = await r.json();
    if (Array.isArray(d?.business_types) && d.business_types.length) return d.business_types;
  } catch {
    /* fall back to the built-in list */
  }
  return BUSINESS_TYPES;
}

export async function startFreeSignup(input: SignupInput): Promise<SignupResult> {
  try {
    const r = await fetch(`${HUB_API_BASE}/public/signup`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ network_opt_in: true, ...input }),
    });
    return (await r.json()) as SignupResult;
  } catch (e) {
    return { error: e instanceof Error ? e.message : "Couldn't reach the signup service." };
  }
}
