"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// The readiness page's new role as NXTDeal's integration platform (2026-07-13,
// session 37). Sam: "the readiness page acts as the integration platform for dealerOS
// to pull data via api, csv, etc from various dealer platforms / crms / DMS's and fill
// the knowledge ledger to a set point of prediction certainty (we'll default to 90%)
// for now for each department... so no dealer has to go full deploy across the
// dealership at one time." Two halves: (1) prediction/confidence cards -- open to any
// role, always visible, not gated behind asking chat first, since this is now the
// page's main content; (2) data-connection management (CSV upload + API connection
// config) -- ADMIN/OPERATIONS only, matching core/data_connections_api.py's ACL.

import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

type Prediction = {
  department: string;
  horizon: string;
  horizon_days: number;
  metric: string;
  unit: string;
  predicted_value: number;
  confidence_pct: number;
  basis: "ledger" | "industry_estimate" | "blended";
  sample_size: number;
  note: string;
};

type DepartmentPrediction = {
  department: string;
  readiness: { confidence_pct: number; threshold: number; ready: boolean; basis: string };
  predictions: Prediction[];
};

type Connection = {
  id: string;
  name: string;
  connection_type: "csv" | "api";
  department: string;
  status: "pending" | "connected" | "error";
  endpoint_url: string | null;
  records_ingested: number;
  last_synced_at: string | null;
  last_test_at: string | null;
  error_message: string | null;
};

const HORIZON_LABELS: Record<string, string> = {
  tomorrow: "Tomorrow",
  week: "This Week",
  month: "This Month",
  quarter: "This Quarter",
};

const BASIS_LABEL: Record<string, string> = {
  ledger: "Ledger-verified",
  blended: "Blended",
  industry_estimate: "Industry estimate",
};

const DEPARTMENTS = ["sales", "service", "finance", "parts", "marketing"];

function basisColor(basis: string) {
  if (basis === "ledger") return "text-green-400";
  if (basis === "blended") return "text-[#FBCF09]";
  return "text-zinc-500";
}

export function ReadinessIntegrationPanel({ canManageConnections }: { canManageConnections: boolean }) {
  const [departments, setDepartments] = useState<DepartmentPrediction[]>([]);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [connections, setConnections] = useState<Connection[]>([]);
  const [showAddConnection, setShowAddConnection] = useState(false);
  const [newName, setNewName] = useState("");
  const [newType, setNewType] = useState<"csv" | "api">("csv");
  const [newDepartment, setNewDepartment] = useState("sales");
  const [newEndpoint, setNewEndpoint] = useState("");
  const [connError, setConnError] = useState<string | null>(null);
  const [csvKindByConnection, setCsvKindByConnection] = useState<Record<string, string>>({});

  async function loadPredictions() {
    setLoading(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}/readiness/predictions`, {
        headers: { ...authHeaders() },
      });
      const data = await response.json();

      if (!response.ok || data.error) {
        throw new Error(data.error ?? `Backend returned ${response.status}`);
      }

      setDepartments((data.departments ?? []) as DepartmentPrediction[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Unable to reach NXTDeal backend.");
    } finally {
      setLoading(false);
    }
  }

  async function loadConnections() {
    try {
      const response = await fetch(`${API_BASE}/readiness/connections`, {
        headers: { ...authHeaders() },
      });
      const data = await response.json();
      if (!response.ok || data.error) throw new Error(data.error ?? `Unable to load connections (${response.status}).`);
      setConnections((data.connections ?? []) as Connection[]);
    } catch (err) {
      setConnError(err instanceof Error ? err.message : "Unable to load connections.");
    }
  }

  useEffect(() => {
    loadPredictions();
    if (canManageConnections) loadConnections();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [canManageConnections]);

  async function createConnection() {
    setConnError(null);

    if (!newName.trim()) {
      setConnError("Name your connection.");
      return;
    }

    try {
      const response = await fetch(`${API_BASE}/readiness/connections`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({
          name: newName,
          connection_type: newType,
          department: newDepartment,
          endpoint_url: newType === "api" ? newEndpoint : null,
        }),
      });

      const data = await response.json();

      if (!response.ok || data.error) {

        // Compliance-blocked connections (session 38, GLBA Safeguards Rule) carry
        // compliance_violations alongside the generic error -- show the real reason
        // (e.g. "unencrypted HTTP endpoint"), not just "Compliance check failed."
        if (data.compliance_violations?.length) {
          const lines = data.compliance_violations.map(
            (v: { law: string; citation: string; description: string }) =>
              `- [${v.law}, ${v.citation}] ${v.description}`
          );
          throw new Error([data.error, ...lines].join("\n"));
        }

        throw new Error(data.error ?? `Backend returned ${response.status}`);
      }

      setNewName("");
      setNewEndpoint("");
      setShowAddConnection(false);
      loadConnections();
    } catch (err) {
      setConnError(err instanceof Error ? err.message : "Unable to reach NXTDeal backend.");
    }
  }

  async function uploadCsv(connectionId: string, file: File, department: string) {
    const formData = new FormData();
    formData.append("file", file);

    if (department === "parts") {
      const kind = csvKindByConnection[connectionId] ?? "parts";
      formData.append("csv_kind", kind);
    }

    try {
      setConnError(null);
      const response = await fetch(`${API_BASE}/readiness/connections/${connectionId}/upload-csv`, {
        method: "POST",
        headers: { ...authHeaders() },
        body: formData,
      });
      const result = await response.json();
      if (!response.ok || result.error) throw new Error(result.error ?? "CSV import failed.");
      await loadConnections();
      await loadPredictions();
    } catch (err) {
      setConnError(err instanceof Error ? err.message : "CSV import failed.");
    }
  }

  async function testConnection(connectionId: string) {
    try {
      setConnError(null);
      const response = await fetch(`${API_BASE}/readiness/connections/${connectionId}/test`, {
        method: "POST",
        headers: { ...authHeaders() },
      });
      const result = await response.json();
      if (!response.ok || result.error) throw new Error(result.error ?? "Connection test failed.");
      await loadConnections();
    } catch (err) {
      setConnError(err instanceof Error ? err.message : "Connection test failed.");
    }
  }

  return (
    <div className="space-y-6 mb-8">
      <div>
        <div className="text-sm text-zinc-500 mb-3">
          Department Readiness — percentage certainty for tomorrow, this week, this
          month, and this quarter, based on real ledger history where it exists and
          honestly-labeled industry estimates where it doesn&apos;t.
        </div>

        {loading && <div className="text-xs text-zinc-500">Loading predictions…</div>}
        {error && <div className="text-xs text-[#EE3C25]">{error}</div>}

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
          {departments.map((dept) => (
            <div
              key={dept.department}
              className="bg-brand-charcoal border border-black/20 rounded-xl p-4 cursor-pointer"
              onClick={() => setExpanded(expanded === dept.department ? null : dept.department)}
            >
              <div className="flex items-center justify-between mb-2">
                <div className="font-brand font-medium uppercase tracking-wide capitalize">{dept.department}</div>
                <div
                  className={
                    dept.readiness.ready ? "text-xs text-green-400" : "text-xs text-[#FBCF09]"
                  }
                >
                  {dept.readiness.ready ? "Ready to go live" : "Not yet at threshold"}
                </div>
              </div>

              <div className="text-2xl font-semibold mb-1">
                {dept.readiness.confidence_pct}%
                <span className="text-xs text-zinc-500 ml-2">
                  vs {dept.readiness.threshold}% target
                </span>
              </div>

              <div className={`text-xs ${basisColor(dept.readiness.basis)}`}>
                {BASIS_LABEL[dept.readiness.basis] ?? dept.readiness.basis}
              </div>

              {expanded === dept.department && (
                <div className="mt-3 pt-3 border-t border-zinc-800 space-y-2">
                  {dept.predictions.map((p) => (
                    <div key={p.horizon} className="text-xs">
                      <div className="flex items-center justify-between">
                        <span className="text-zinc-400">{HORIZON_LABELS[p.horizon]}</span>
                        <span>
                          {p.predicted_value} {p.unit} · {p.confidence_pct}%
                        </span>
                      </div>
                      <div className="text-zinc-600">{p.note}</div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {canManageConnections && (
        <div className="bg-brand-charcoal border border-black/20 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="font-brand font-medium">Data Connections</div>
            <WorkButton type="submit"
              onClick={() => setShowAddConnection((v) => !v)}
              className="text-sm text-[#3FBCC4] hover:text-white transition"
            >
              {showAddConnection ? "Cancel" : "+ Add connection"}
            </WorkButton>
          </div>

          {connError && <p role="alert">{connError}</p>}
          {showAddConnection && (
            <div className="space-y-2 mb-4 bg-brand-charcoal border border-black/20 rounded-lg p-3">
              <WorkField label="Connection name"><WorkInput
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                placeholder="Connection name (e.g. DealerSocket DMS)"
                className="w-full h-9 px-2 text-sm rounded bg-zinc-900 border border-zinc-800"
              /></WorkField>
              <div className="flex gap-2">
                <WorkField label="Connection type"><WorkSelect
                  value={newType}
                  onChange={(e) => setNewType(e.target.value as "csv" | "api")}
                  className="flex-1 h-9 px-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                >
                  <option value="csv">CSV upload</option>
                  <option value="api">API connection</option>
                </WorkSelect></WorkField>
                <WorkField label="Department"><WorkSelect
                  value={newDepartment}
                  onChange={(e) => setNewDepartment(e.target.value)}
                  className="flex-1 h-9 px-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                >
                  {DEPARTMENTS.map((d) => (
                    <option key={d} value={d}>
                      {d}
                    </option>
                  ))}
                </WorkSelect></WorkField>
              </div>
              {newType === "api" && (
                <WorkField label="New Endpoint"><WorkInput
                  value={newEndpoint}
                  onChange={(e) => setNewEndpoint(e.target.value)}
                  placeholder="https://api.example.com/inventory"
                  className="w-full h-9 px-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                /></WorkField>
              )}

              <WorkButton type="submit"
                onClick={createConnection}
                className="w-full py-2 rounded-lg bg-[#3FBCC4] text-black text-sm hover:bg-[#5cd0d8]"
              >
                Create connection
              </WorkButton>
            </div>
          )}

          {connections.length === 0 ? (
            <div className="text-sm text-zinc-500">No connections configured yet.</div>
          ) : (
            <div className="space-y-2">
              {connections.map((c) => (
                <div key={c.id} className="bg-brand-charcoal border border-black/20 rounded-lg p-3 text-sm">
                  <div className="flex items-center justify-between">
                    <div>
                      <span className="font-medium">{c.name}</span>
                      <span className="text-zinc-500 text-xs ml-2">
                        {c.connection_type} · {c.department}
                      </span>
                    </div>
                    <span
                      className={
                        c.status === "connected"
                          ? "text-xs text-green-400"
                          : c.status === "error"
                          ? "text-xs text-[#EE3C25]"
                          : "text-xs text-zinc-500"
                      }
                    >
                      {c.status}
                    </span>
                  </div>

                  {c.error_message && (
                    <div className="text-xs text-[#EE3C25] mt-1">{c.error_message}</div>
                  )}

                  <div className="text-xs text-zinc-500 mt-1">
                    {c.records_ingested} record(s) ingested
                    {c.last_synced_at ? ` · last synced ${new Date(c.last_synced_at).toLocaleString()}` : ""}
                  </div>

                  {c.connection_type === "csv" ? (
                    <div className="mt-2 flex items-center gap-2">
                      {c.department === "parts" && (
                        <WorkField label="Parts catalog"><WorkSelect
                          value={csvKindByConnection[c.id] ?? "parts"}
                          onChange={(e) =>
                            setCsvKindByConnection((prev) => ({ ...prev, [c.id]: e.target.value }))
                          }
                          className="h-8 px-2 text-xs rounded bg-zinc-900 border border-zinc-800"
                        >
                          <option value="parts">Parts catalog</option>
                          <option value="sales">Parts sales</option>
                        </WorkSelect></WorkField>
                      )}
                      <WorkInput
                        aria-label="Choose CSV file" type="file"
                        accept=".csv"
                        onChange={(e) => {
                          const file = e.target.files?.[0];
                          if (file) uploadCsv(c.id, file, c.department);
                        }}
                        className="text-xs"
                      />
                    </div>
                  ) : (
                    <WorkButton type="submit"
                      onClick={() => testConnection(c.id)}
                      className="mt-2 text-xs text-[#3FBCC4] hover:text-white transition"
                    >
                      Test connection →
                    </WorkButton>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
