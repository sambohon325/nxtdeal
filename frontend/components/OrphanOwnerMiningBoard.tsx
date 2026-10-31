"use client";
import { WorkInput, WorkButton } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Orphan Owner Mining (session 105 follow-up) -- rendered inside Sales' "Orphan
// Owner Mining" workflow modal (core/workflow_catalog.py's
// sales.orphan_owner_mining). The ninth of Sam's ~10 "completely missing"
// dealership workflows; follows the same bespoke per-tab-section pattern session
// 100-105 established -- a `section` prop matching this workflow's 5 real tabs
// (Orphan Queue, Customer Detail, Claim & Assign, Claimed Owners, Mining Stats).
//
// Real signal, not a guess: a Customer who owns a Vehicle with zero traceable
// salesperson attribution on file. Claiming one creates a real assigned Lead tied
// back to the Customer -- see lib/orphanOwners.ts's header comment for the full
// honest-scope note (no Employee departure field exists in this codebase).
import { useEffect, useState } from "react";
import {
  getOrphanOwnerDashboard,
  getOrphanOwners,
  getOrphanOwnerDetail,
  claimOrphanOwner,
  type OrphanOwnerDashboard,
  type OrphanOwnerEntry,
} from "@/lib/orphanOwners";

export type OrphanOwnerMiningSection = "queue" | "detail" | "claim" | "claimed" | "stats";

function OwnerRow({ entry, onSelect, selected }: { entry: OrphanOwnerEntry; onSelect: () => void; selected: boolean }) {
  return (
    <button
      onClick={onSelect}
      className={`w-full text-left text-xs px-2 py-1.5 rounded border ${
        selected ? "border-zinc-500 bg-zinc-800" : "border-zinc-800"
      } text-zinc-300`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="text-zinc-200">{entry.customer.name}</span>
        <span className="text-zinc-600">{entry.customer.id}</span>
      </div>
      <div className="text-xs text-zinc-500">
        {entry.vehicles_owned.count} vehicle{entry.vehicles_owned.count === 1 ? "" : "s"} owned
        {entry.service_history.most_recent_service_date && ` · last service ${entry.service_history.most_recent_service_date}`}
        {entry.claimed && ` · claimed by ${entry.claimed_by}`}
      </div>
    </button>
  );
}

export function OrphanOwnerMiningBoard({ section = "queue" }: { section?: OrphanOwnerMiningSection }) {
  const [dashboard, setDashboard] = useState<OrphanOwnerDashboard | null>(null);
  const [claimedList, setClaimedList] = useState<OrphanOwnerEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [selectedId, setSelectedId] = useState<string>("");
  const [detail, setDetail] = useState<OrphanOwnerEntry | null>(null);
  const [customerIdInput, setCustomerIdInput] = useState("");
  const [noteInput, setNoteInput] = useState("");

  function refresh() {
    setLoading(true);
    getOrphanOwnerDashboard()
      .then((d) => {
        setDashboard(d);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Orphan Owner Mining data."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  useEffect(() => {
    if (section === "claimed") {
      getOrphanOwners(200, true)
        .then((all) => setClaimedList(all.filter((o) => o.claimed)))
        .catch(() => setClaimedList([]));
    }
  }, [section]);

  function selectOwner(entry: OrphanOwnerEntry) {
    setSelectedId(entry.customer.id);
    setDetail(entry);
  }

  function loadDetail(customerId: string) {
    if (!customerId.trim()) return;
    setBusy(true);
    getOrphanOwnerDetail(customerId.trim())
      .then((d) => {
        setDetail(d);
        setSelectedId(customerId.trim());
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load this customer."))
      .finally(() => setBusy(false));
  }

  async function handleClaim() {
    if (!selectedId) return;
    setBusy(true);
    try {
      const result = await claimOrphanOwner(selectedId, noteInput.trim() || undefined);
      setMessage(`Claimed ${selectedId} -- created Lead ${result.lead_id}, assigned to you.`);
      setNoteInput("");
      refresh();
      loadDetail(selectedId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to claim this owner.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="mb-5 text-xs text-zinc-600">Loading…</div>;
  }

  const stats = dashboard?.stats;

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}

      {section === "queue" && (
        <>
          <div className="grid grid-cols-4 gap-2 mb-3">
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{stats?.total_orphan_owners ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Total Orphan Owners</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-amber-300">{stats?.unclaimed ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Unclaimed</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-emerald-300">{stats?.claimed ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Claimed</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{stats?.total_vehicles_represented ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Vehicles Represented</div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">
              Unclaimed Owners ({dashboard?.queue.length ?? 0} shown, sorted by vehicles owned + service recency)
            </div>
            {(dashboard?.queue.length ?? 0) === 0 ? (
              <div className="text-xs text-zinc-600">No unclaimed orphan owners right now.</div>
            ) : (
              <div className="space-y-1.5">
                {dashboard!.queue.map((o) => (
                  <OwnerRow key={o.customer.id} entry={o} onSelect={() => selectOwner(o)} selected={selectedId === o.customer.id} />
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {section === "detail" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Customer Detail</div>
          <div className="flex items-center gap-2 mb-3">
            <WorkField label="Customer ID (CUST-…)"><WorkInput
              value={customerIdInput}
              onChange={(e) => setCustomerIdInput(e.target.value)}
              placeholder="Customer ID (CUST-…)"
              className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
            /></WorkField>
            <WorkButton type="submit"
              onClick={() => loadDetail(customerIdInput)}
              disabled={busy || !customerIdInput.trim()}
              className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
            >
              Open
            </WorkButton>
          </div>
          {!detail ? (
            <div className="text-xs text-zinc-600">Select an owner from the Orphan Queue tab, or open one by ID above.</div>
          ) : (
            <div className="space-y-2">
              <div className="text-xs text-zinc-200">
                {detail.customer.name} <span className="text-zinc-600">({detail.customer.id})</span>
              </div>
              <div className="text-xs text-zinc-400">
                {detail.customer.email || "no email"} · {detail.customer.phone || "no phone"}
              </div>
              <div className="text-xs text-zinc-300">
                {detail.claimed ? (
                  <span className="text-emerald-300">Claimed -- Lead {detail.claimed_lead_id}, assigned to {detail.claimed_by}</span>
                ) : (
                  <span className="text-amber-300">Unclaimed -- no salesperson attribution on file</span>
                )}
              </div>
              <div className="mt-2">
                <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">
                  Vehicles Owned ({detail.vehicles_owned.count})
                </div>
                <div className="space-y-1">
                  {detail.vehicles_owned.vehicles.map((v) => (
                    <div key={v.id} className="text-xs text-zinc-300 px-2 py-1 rounded border border-zinc-800">
                      {v.description} <span className="text-zinc-600">({v.vin || v.id})</span>
                    </div>
                  ))}
                </div>
              </div>
              <div className="mt-2">
                <div className="text-xs text-zinc-500 uppercase tracking-wide mb-1">Service History</div>
                <div className="text-xs text-zinc-300">
                  {detail.service_history.visit_count} visit{detail.service_history.visit_count === 1 ? "" : "s"}
                  {detail.service_history.most_recent_service_date && ` · most recent ${detail.service_history.most_recent_service_date}`}
                </div>
              </div>
            </div>
          )}
        </div>
      )}

      {section === "claim" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Claim & Assign</div>
          <p className="text-xs text-zinc-600 mb-2">
            Claiming creates a real new Lead (Source "Orphan Owner Mining"), auto-assigned to you, tied back to this
            customer -- the same one-click promote-to-CRM mechanism used across this codebase.
          </p>
          {!selectedId ? (
            <div className="text-xs text-zinc-600">Select an owner from the Orphan Queue or Customer Detail tab first.</div>
          ) : detail?.claimed ? (
            <div className="text-xs text-emerald-300">
              {selectedId} is already claimed -- Lead {detail.claimed_lead_id}, assigned to {detail.claimed_by}.
            </div>
          ) : (
            <>
              <div className="text-xs text-zinc-300 mb-2">
                Claiming: {detail?.customer.name || selectedId} ({selectedId})
              </div>
              <WorkField label="Optional note"><WorkInput
                value={noteInput}
                onChange={(e) => setNoteInput(e.target.value)}
                placeholder="Optional note (e.g. planned outreach angle)"
                className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 mb-2"
              /></WorkField>
              <WorkButton type="submit"
                onClick={handleClaim}
                disabled={busy}
                className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
              >
                Claim This Owner
              </WorkButton>
            </>
          )}
        </div>
      )}

      {section === "claimed" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Claimed Owners ({claimedList.length})</div>
          {claimedList.length === 0 ? (
            <div className="text-xs text-zinc-600">No owners claimed yet.</div>
          ) : (
            <div className="space-y-1.5">
              {claimedList.map((o) => (
                <div key={o.customer.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800 text-zinc-300">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-zinc-200">{o.customer.name}</span>
                    <span className="text-zinc-600">{o.customer.id}</span>
                  </div>
                  <div className="text-xs text-zinc-500">
                    Lead {o.claimed_lead_id} · assigned to {o.claimed_by} · {o.vehicles_owned.count} vehicle(s)
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {section === "stats" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Mining Stats</div>
          <div className="grid grid-cols-2 gap-2">
            <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
              <div className="text-base font-semibold text-zinc-100">{stats?.total_orphan_owners ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Total Orphan Owners</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
              <div className="text-base font-semibold text-zinc-100">{stats?.total_vehicles_represented ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Vehicles Represented</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
              <div className="text-base font-semibold text-amber-300">{stats?.unclaimed ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Unclaimed</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800">
              <div className="text-base font-semibold text-emerald-300">{stats?.claimed ?? 0}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Claimed</div>
            </div>
          </div>
          <p className="text-xs text-zinc-600 mt-3">
            "Orphan" here means real ownership with zero salesperson attribution on file -- this codebase has no
            Employee departure/termination field, so a departed-rep signal can't be computed honestly; this is the
            real, buildable gap instead.
          </p>
        </div>
      )}
    </div>
  );
}
