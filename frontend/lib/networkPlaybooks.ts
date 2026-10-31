// Network's "Playbooks" item -- a real curated best-practice library (slice 5
// of the Intelligence Network reframe, 2026-07-18). Backend: core/
// network_playbooks.py + core/network_menu.py's enriched playbooks(). Every
// playbook references a real NXTDeal screen/workflow, is tied to a real
// core/network_root_cause.py diagnostic (re-run live -- is_currently_active
// is a checked fact, not a static description), and carries a real
// automation_score against core/workflow_automation.py's actual rule engine.
// Served via the existing generic GET /menu/data route -- no dedicated
// backend route was needed for this slice.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import type { RootCause } from "@/lib/networkGapAnalysis";
import type { RecommendationEntry } from "@/lib/networkOpportunity";

export type AutomationScore = {
  tier: 0 | 1 | 2 | 3;
  label: string;
  note: string;
  active_rule_count?: number;
};

export type PlaybookEntry = {
  key: string;
  title: string;
  department: string;
  kpi_keys: string[];
  summary: string;
  steps: string[];
  is_currently_active: boolean;
  active_finding: RootCause | null;
  automation_score: AutomationScore;
};

export type NetworkPlaybooks = {
  library: PlaybookEntry[];
  playbook_count: number;
  currently_active_count: number;
  library_note: string;
  related_recommendations: RecommendationEntry[];
  note: string;
  not_yet_tracked: Record<string, string>;
  error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

function get<T>(path: string): Promise<T> {
  return fetch(`${API_BASE}${path}`, { headers: { ...authHeaders() } }).then(handle<T>);
}

export function getNetworkPlaybooks(): Promise<NetworkPlaybooks> {
  const params = new URLSearchParams({ department: "Network", item_key: "playbooks" });
  return get(`/menu/data?${params.toString()}`);
}
