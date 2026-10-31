// MySales adoption client (Phase 6): a rep pings their own usage so the Hub/Readiness
// function can detect rep-level buy-in (a warm dealership conversion signal). Fire-and-forget.
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";
import { getAppSession } from "@/lib/appAuth";

export async function recordMySalesActivity(action = "open"): Promise<void> {
  const session = getAppSession();
  try {
    await fetch(`${API_BASE}/mysales-adoption/activity`, {
      method: "POST",
      headers: { "Content-Type": "application/json", ...authHeaders() },
      body: JSON.stringify({
        dealership_id: session?.dealershipId ?? null,
        action,
        // On NXTDeal iff this app resolved a real NXTDeal tenant session.
        dealership_on_dealeros: Boolean(session?.token),
        rep_name: session?.employeeId ?? null,
      }),
    });
  } catch {
    // fire-and-forget — never block the app on the adoption ping
  }
}

export type ConversionSignals = {
  dealers: { dealership_id: string; on_dealeros: boolean; rep_count: number; total_activity: number }[];
  warm_conversion_targets: { dealership_id: string; rep_count: number; total_activity: number }[];
  warm_count: number;
  note: string;
};

export async function getConversionSignals(minReps = 1): Promise<ConversionSignals> {
  const res = await fetch(`${API_BASE}/mysales-adoption/conversion-signals?min_reps=${minReps}`, { headers: { ...authHeaders() } });
  const data = await res.json();
  if (!res.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as ConversionSignals;
}
