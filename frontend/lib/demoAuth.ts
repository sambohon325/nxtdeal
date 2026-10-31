// Client for the AI-demo lead/account flow, which lives in the HUB (hub-api), not the demo
// tenant (that's non-persistent). Sign-up captures the lead + creates a login; login lets a
// prospect return without re-filling the form. After auth, the caller starts the actual demo
// sandbox session via lib/demo (demo-api). Needs NEXT_PUBLIC_HUB_API_URL on the demo frontend.

import { HUB_API_BASE } from "@/lib/hubApi";

export type DemoLeadAccount = {
  email: string;
  username?: string;
  name: string;
  persona: string;
  position?: string | null;
  dealership?: string | null;
  city?: string | null;
  region?: string | null;
  country?: string | null;
  phone?: string | null;
};

const LEAD_KEY = "dealeros_demo_lead";

async function hub<T>(path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${HUB_API_BASE}${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.detail || data?.error || "Something went wrong.");
  return data as T;
}

export function fetchDemoAuthConfig(): Promise<{ turnstile_enabled: boolean }> {
  return hub("/hub/public/demo/config");
}

export type SignupInput = {
  name: string;
  email: string;
  password: string;
  persona: string;
  position?: string;
  dealership?: string;
  city?: string;
  region?: string;
  country?: string;
  phone?: string;
  username?: string;
  turnstile_token?: string;
};

export async function demoSignup(input: SignupInput): Promise<DemoLeadAccount> {
  const data = await hub<{ account: DemoLeadAccount }>("/hub/public/demo/signup", input);
  return data.account;
}

export async function demoLogin(identifier: string, password: string): Promise<DemoLeadAccount> {
  const data = await hub<{ account: DemoLeadAccount }>("/hub/public/demo/login", { identifier, password });
  return data.account;
}

export function demoForgot(email: string): Promise<{ dev_reset_token?: string }> {
  return hub("/hub/public/demo/forgot", { email });
}

export function demoReset(email: string, token: string, new_password: string): Promise<{ ok: boolean }> {
  return hub("/hub/public/demo/reset", { email, token, new_password });
}

// Remember the signed-in prospect so a return visit can resume without re-authenticating.
export function saveDemoLead(account: DemoLeadAccount) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(LEAD_KEY, JSON.stringify(account));
  } catch {
    /* ignore */
  }
}

export function getDemoLead(): DemoLeadAccount | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(LEAD_KEY);
    return raw ? (JSON.parse(raw) as DemoLeadAccount) : null;
  } catch {
    return null;
  }
}

export function clearDemoLead() {
  if (typeof window === "undefined") return;
  try {
    localStorage.removeItem(LEAD_KEY);
  } catch {
    /* ignore */
  }
}
