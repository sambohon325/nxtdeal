// Network's "AI Advisors" item -- 5 real, department-specific Q&A advisors
// (Sales/Service/Parts/F&I/BHPH), Intelligence Network reframe, slice 6.
// Backend: core/network_advisors.py + 2 dedicated routes (a question needs a
// POST, so this bypasses the generic GET /menu/data path other Network items
// use). An isolated OpenAI call may only phrase an answer from a real,
// pre-computed per-department FACTS block (this dealer's own real benchmark
// comparison, gap analysis, and curated playbook data -- all already-real
// Intelligence Network modules); its fallback (used whenever OpenAI is
// unreachable, which is every call in this sandbox) is a real topic-matching
// formatter over that same FACTS block, not a generic "AI unavailable"
// message.

import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type AdvisorDepartment = "sales" | "service" | "parts" | "fi" | "bhph";

export type AdvisorCatalogEntry = {
  department: AdvisorDepartment;
  title: string;
};

export type AdvisorAnswer = {
  department: AdvisorDepartment;
  question: string;
  answer: string;
  ai_generated: boolean;
  note?: string;
  fallback_answer?: string;
  error?: string;
};

async function handle<T>(response: Response): Promise<T> {
  const data = await response.json();
  if (!response.ok || (data && typeof data === "object" && "error" in data)) {
    throw new Error((data && (data as { error?: string }).error) || "Unable to reach NXTDeal backend.");
  }
  return data as T;
}

export function getNetworkAdvisorsCatalog(): Promise<{ advisors: AdvisorCatalogEntry[] }> {
  return fetch(`${API_BASE}/network-advisors/catalog`, { headers: { ...authHeaders() } }).then(
    handle<{ advisors: AdvisorCatalogEntry[] }>
  );
}

export function askNetworkAdvisor(department: AdvisorDepartment, question: string): Promise<AdvisorAnswer> {
  return fetch(`${API_BASE}/network-advisors/ask`, {
    method: "POST",
    headers: { "Content-Type": "application/json", ...authHeaders() },
    body: JSON.stringify({ department, question }),
  }).then(handle<AdvisorAnswer>);
}
