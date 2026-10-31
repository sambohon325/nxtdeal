// lib/digitalRetail.ts — client for the Digital Retail KPI dashboard (2026-07-24, DR-8).
// Talks to GET /digital-retail/dashboard (backend core/digital_retail_analytics.py), a
// read-only roll-up over everything DR-1..7 record. Same reuse-the-shared-helpers shape every
// lib/*.ts client follows.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type FunnelStage = {
  stage: string;
  label: string;
  count: number;
  conversion_from_prev: number | null;
  dropped_from_prev: number;
};

export type DigitalRetailDashboard = {
  kpis: {
    digital_deals: number;
    by_status: Record<string, number>;
    digital_closings: number;
    digital_gross: number;
    digital_deliveries: number;
    completed: number;
    verifications: number;
  };
  ai_performance: {
    deals_assisted: number;
    deals_negotiated: number;
    deals_closed: number;
    revenue_influenced: number;
    workforce: { active_workers: number; actions_executed: number; actions_drafted: number; interactions: number };
  };
  funnel: {
    stages: FunnelStage[];
    verification_by_tier: Record<string, number>;
  };
  verifications: { total: number; by_tier: Record<string, number>; verified_humans_or_above: number };
  negotiations: { total_sessions: number; by_status: Record<string, number>; open_escalations: number };
  deliveries: { total: number; by_status: Record<string, number>; by_mode: Record<string, number>; home_deliveries_without_driver: number };
  try_before_you_buy: { total: number; by_status: Record<string, number>; currently_out: number };
  note: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (
    !response.ok ||
    (data && typeof data === "object" && "error" in data && (data as { error?: string }).error)
  ) {
    throw new Error(
      (data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend."
    );
  }
  return data as T;
}

export function fetchDigitalRetailDashboard(): Promise<DigitalRetailDashboard> {
  return fetch(`${API_BASE}/digital-retail/dashboard`, { headers: { ...authHeaders() } }).then(
    handle<DigitalRetailDashboard>
  );
}
