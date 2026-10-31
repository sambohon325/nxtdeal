"use client";

import { dealerDisplayName } from "@/lib/brandDisplay";

// NXTDeal Hub -- AI Kill Switch emergency-response console. Security-hardening
// pass, Task #6 ("Expand AI kill switch to dealer/department/bot/workflow
// scope"). Lets a NXTDeal staffer see one dealer's real, LIVE 4-scope AI
// kill-switch state and push a real emergency stop to that dealer's own
// tenant process directly from the Hub console -- without needing that
// dealer's own employee credentials. See hub/hub_core/dealer_ai_kill_switch.py's
// own module docstring for the full design; two things worth restating here
// since they shape this UI directly:
//
//   1. STATUS IS ALWAYS A LIVE FETCH, NEVER CACHED. Unlike every other Hub
//      panel's own "recheck and persist a snapshot" pattern (AI Management,
//      Storage, Services), showing a stale kill-switch state during a real
//      incident would be actively dangerous -- so there's no "last checked"
//      snapshot to fall back on here, only a real-time re-fetch on demand.
//
//   2. EVERY PUSH -- SUCCESS OR FAILURE -- IS A PERMANENT RECORD. The
//      history table below is append-only by design; a failed push (e.g. an
//      unreachable dealer) still shows up, since a real incident review
//      needs to see every attempt that was made, not just the current
//      state.
//
// A dealer-wide or department-wide push is a genuinely destructive action
// (it can silence real AI capability for an entire dealer or department), so
// the push form uses the same two-step "click to arm, click again to
// confirm" pattern components/hub/NetworkConnectSection.tsx's own Convert To
// Dealer action already established, rather than firing on the first click.

import { useEffect, useState } from "react";
import {
  HubApiError,
  listDealers,
  getDealerKillSwitchStatus,
  pushDealerKillSwitch,
  getDealerKillSwitchHistory,
  getAllKillSwitchHistory,
  KILL_SWITCH_SCOPES,
  KILL_SWITCH_DEPARTMENTS,
  type Dealer,
  type DealerKillSwitchStatus,
  type DealerKillSwitchHistory,
  type AllKillSwitchHistory,
  type KillSwitchAction,
  type KillSwitchScope,
  type AiKillSwitchScopeState,
} from "@/lib/hubApi";

function errorMessage(error: unknown): string {
  return error instanceof HubApiError ? error.message : "Unable to reach the Hub.";
}

function KpiCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-4">
      <div className="text-2xl font-semibold">{value}</div>
      <div className="text-[11px] uppercase tracking-wide text-zinc-500 mt-1">{label}</div>
    </div>
  );
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 text-sm text-red-400 bg-red-950/30 border border-red-900 rounded-lg px-4 py-3">
      {message}
    </div>
  );
}

function EnforcementNotice({ text }: { text: string }) {
  return (
    <div className="mb-4 text-[11px] text-yellow-500 bg-yellow-950/20 border border-yellow-900 rounded-lg px-4 py-3">
      {text}
    </div>
  );
}

function DealerPicker({
  dealers,
  selected,
  onSelect,
}: {
  dealers: Dealer[] | null;
  selected: string;
  onSelect: (dealerId: string) => void;
}) {
  return (
    <select
      value={selected}
      onChange={(e) => onSelect(e.target.value)}
      className="h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm min-w-[220px]"
    >
      <option value="">Select a dealer…</option>
      {(dealers ?? []).map((d) => (
        <option key={d.dealer_id} value={d.dealer_id}>
          {dealerDisplayName(d.name)} ({d.dealer_id})
        </option>
      ))}
    </select>
  );
}

const SCOPE_LABELS: Record<KillSwitchScope, string> = {
  dealer_wide: "Dealer-Wide (kill everything)",
  department: "Department",
  bot: "Bot (autonomous actions)",
  workflow_automation: "Workflow Automation",
};

function ScopeBadge({ scope }: { scope: KillSwitchScope }) {
  return (
    <span className="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded bg-zinc-800 text-zinc-300">
      {SCOPE_LABELS[scope] ?? scope}
    </span>
  );
}

function ActiveBadge({ active }: { active: boolean }) {
  return (
    <span
      className={
        active
          ? "text-[10px] uppercase tracking-wide px-2 py-0.5 rounded text-red-400 bg-red-950/40"
          : "text-[10px] uppercase tracking-wide px-2 py-0.5 rounded text-green-400 bg-green-950/40"
      }
    >
      {active ? "AI Killed" : "Enabled"}
    </span>
  );
}

function ScopeStateRow({
  label,
  state,
  footnote,
}: {
  label: string;
  state: AiKillSwitchScopeState;
  footnote?: string;
}) {
  return (
    <div className="bg-zinc-900 rounded-lg p-3">
      <div className="flex items-center justify-between mb-1">
        <span className="text-sm font-medium">{label}</span>
        <ActiveBadge active={state.active} />
      </div>
      {state.active && (
        <div className="text-[11px] text-zinc-500 leading-relaxed">
          {state.activated_by && <div>by {state.activated_by}</div>}
          {state.activated_at && <div>{new Date(state.activated_at).toLocaleString()}</div>}
          {state.reason && <div className="text-zinc-400 mt-1">"{state.reason}"</div>}
        </div>
      )}
      {footnote && <div className="text-[10px] text-zinc-600 mt-1">{footnote}</div>}
    </div>
  );
}

function ActionRow({ action, showDealer }: { action: KillSwitchAction; showDealer?: boolean }) {
  return (
    <tr className="border-t border-zinc-800">
      <td className="px-3 py-2 text-xs">
        {new Date(action.pushed_at).toLocaleString()}
      </td>
      {showDealer && (
        <td className="px-3 py-2 text-xs text-zinc-400">
          {action.dealer_name ?? action.dealer_id} ({action.dealer_id})
        </td>
      )}
      <td className="px-3 py-2">
        <ScopeBadge scope={action.scope} />
        {action.department && (
          <span className="text-[10px] text-zinc-500 ml-1">{action.department}</span>
        )}
      </td>
      <td className="px-3 py-2">
        <ActiveBadge active={action.active} />
      </td>
      <td className="px-3 py-2 text-xs text-zinc-400">{action.pushed_by}</td>
      <td className="px-3 py-2 text-xs">
        {action.success ? (
          <span className="text-green-400">succeeded</span>
        ) : (
          <span className="text-red-400" title={action.push_error ?? undefined}>
            failed{action.push_error ? `: ${action.push_error}` : ""}
          </span>
        )}
      </td>
      <td className="px-3 py-2 text-xs text-zinc-500">{action.reason ?? "—"}</td>
    </tr>
  );
}

export default function AiKillSwitchSection() {
  const [dealers, setDealers] = useState<Dealer[] | null>(null);
  const [dealerId, setDealerId] = useState("");
  const [status, setStatus] = useState<DealerKillSwitchStatus | null>(null);
  const [history, setHistory] = useState<DealerKillSwitchHistory | null>(null);
  const [allHistory, setAllHistory] = useState<AllKillSwitchHistory | null>(null);
  const [view, setView] = useState<"dealer" | "all">("dealer");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState("");

  const [pushedBy, setPushedBy] = useState("");
  const [scope, setScope] = useState<KillSwitchScope>("dealer_wide");
  const [active, setActive] = useState(true);
  const [department, setDepartment] = useState<string>(KILL_SWITCH_DEPARTMENTS[0]);
  const [reason, setReason] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [lastAction, setLastAction] = useState<KillSwitchAction | null>(null);

  useEffect(() => {
    listDealers()
      .then(setDealers)
      .catch((e) => setError(errorMessage(e)));
  }, []);

  async function loadStatus(id: string) {
    if (!id) {
      setStatus(null);
      setHistory(null);
      return;
    }
    setBusy("status");
    setError("");
    try {
      const [s, h] = await Promise.all([
        getDealerKillSwitchStatus(id),
        getDealerKillSwitchHistory(id),
      ]);
      setStatus(s);
      setHistory(h);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    loadStatus(dealerId);
    setConfirming(false);
    setLastAction(null);
  }, [dealerId]);

  useEffect(() => {
    if (view === "all") {
      getAllKillSwitchHistory()
        .then(setAllHistory)
        .catch((e) => setError(errorMessage(e)));
    }
  }, [view]);

  async function runPush() {
    if (!dealerId || !pushedBy.trim()) return;
    setBusy("push");
    setError("");
    try {
      const result = await pushDealerKillSwitch(dealerId, {
        pushed_by: pushedBy.trim(),
        scope,
        active,
        reason: reason.trim() || undefined,
        department: scope === "department" ? department : undefined,
      });
      setLastAction(result);
      setConfirming(false);
      await loadStatus(dealerId);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy("");
    }
  }

  const canPush = Boolean(dealerId) && pushedBy.trim().length > 0;

  return (
    <div>
      {error && <ErrorBanner message={error} />}
      <EnforcementNotice
        text="Status shown below is always a real, live round trip to the dealer's own tenant process -- it never comes from a cache, unlike every other Hub panel's own recheck-and-persist pattern. Pushing a switch reaches that dealer's real running backend immediately (if it's currently reachable) -- there is no undo beyond pushing the opposite state back."
      />

      <div className="flex items-center gap-3 mb-6">
        <h3 className="font-brand font-bold uppercase tracking-wide text-sm">AI Kill Switch</h3>
        <DealerPicker dealers={dealers} selected={dealerId} onSelect={setDealerId} />
        <button
          disabled={!dealerId || busy === "status"}
          onClick={() => loadStatus(dealerId)}
          className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
        >
          {busy === "status" ? "Checking…" : "↻ Refresh Live Status"}
        </button>
        <div className="flex-1" />
        <div className="flex gap-1">
          <button
            onClick={() => setView("dealer")}
            className={
              view === "dealer"
                ? "bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide"
                : "bg-zinc-900 text-zinc-400 hover:text-white px-3 py-1.5 rounded text-xs uppercase tracking-wide transition"
            }
          >
            This Dealer
          </button>
          <button
            onClick={() => setView("all")}
            className={
              view === "all"
                ? "bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide"
                : "bg-zinc-900 text-zinc-400 hover:text-white px-3 py-1.5 rounded text-xs uppercase tracking-wide transition"
            }
          >
            All Dealers History
          </button>
        </div>
      </div>

      {view === "all" && (
        <div>
          {allHistory ? (
            <>
              <div className="grid grid-cols-3 gap-3 mb-6">
                <KpiCard label="Total Pushes" value={allHistory.summary.total_actions} />
                <KpiCard label="Succeeded" value={allHistory.summary.successful_pushes} />
                <KpiCard label="Failed" value={allHistory.summary.failed_pushes} />
              </div>
              <div className="bg-zinc-900 rounded-lg overflow-hidden mb-3">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wide text-zinc-500">
                      <th className="px-3 py-2">Pushed At</th>
                      <th className="px-3 py-2">Dealer</th>
                      <th className="px-3 py-2">Scope</th>
                      <th className="px-3 py-2">Set To</th>
                      <th className="px-3 py-2">Pushed By</th>
                      <th className="px-3 py-2">Result</th>
                      <th className="px-3 py-2">Reason</th>
                    </tr>
                  </thead>
                  <tbody>
                    {allHistory.actions.map((a) => (
                      <ActionRow key={a.action_id} action={a} showDealer />
                    ))}
                    {allHistory.actions.length === 0 && (
                      <tr>
                        <td colSpan={7} className="px-3 py-6 text-center text-zinc-500">
                          No kill-switch pushes have ever been made from this Hub.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
              <p className="text-[11px] text-zinc-500">{allHistory.note}</p>
            </>
          ) : (
            <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
              Loading…
            </div>
          )}
        </div>
      )}

      {view === "dealer" && !dealerId && (
        <div className="bg-zinc-900 rounded-lg p-8 text-center text-sm text-zinc-500">
          Select a dealer above to view their live AI kill-switch state and push an emergency stop.
        </div>
      )}

      {view === "dealer" && dealerId && status && (
        <>
          <div className="flex items-center gap-2 mb-4">
            <span
              className={
                status.reachable
                  ? "text-[10px] uppercase tracking-wide px-2 py-1 rounded text-green-400 bg-green-950/40"
                  : "text-[10px] uppercase tracking-wide px-2 py-1 rounded text-red-400 bg-red-950/40"
              }
            >
              {status.reachable ? "Reachable" : "Unreachable"}
            </span>
            <span className="text-[11px] text-zinc-600">
              live as of {new Date(status.fetched_at).toLocaleString()}
            </span>
            {status.fetch_error && (
              <span className="text-[11px] text-red-400">{status.fetch_error}</span>
            )}
          </div>

          {status.reachable && status.state && (
            <div className="mb-6">
              <h4 className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
                Current Live State
              </h4>
              <div className="grid grid-cols-3 gap-2 mb-2">
                <ScopeStateRow
                  label="Dealer-Wide"
                  state={status.state.dealer_wide}
                  footnote="Overrides every narrower switch below when active."
                />
                <ScopeStateRow label="Bot" state={status.state.bot} />
                <ScopeStateRow label="Workflow Automation" state={status.state.workflow_automation} />
              </div>
              <h4 className="text-[11px] uppercase tracking-wide text-zinc-500 mt-4 mb-2">
                Departments
              </h4>
              <div className="grid grid-cols-3 gap-2">
                {status.state.departments.map((d) => (
                  <ScopeStateRow
                    key={d.department}
                    label={d.department}
                    state={d}
                    footnote={
                      d.governed_features.length > 0
                        ? `governs: ${d.governed_features.map((f) => f.name).join(", ")}`
                        : "no AI feature mapped to this department yet"
                    }
                  />
                ))}
              </div>
              {status.state.cross_department_features.length > 0 && (
                <p className="text-[11px] text-zinc-600 mt-3">
                  Cross-department (no single department switch governs these):{" "}
                  {status.state.cross_department_features.map((f) => f.name).join(", ")}
                </p>
              )}
            </div>
          )}

          <div className="bg-zinc-900 rounded-lg p-4 mb-6">
            <h4 className="text-[11px] uppercase tracking-wide text-zinc-500 mb-3">
              Push An Emergency Toggle
            </h4>
            <div className="grid grid-cols-2 gap-3 mb-3">
              <div>
                <label className="text-[10px] uppercase tracking-wide text-zinc-500 block mb-1">
                  Your Name (recorded as pushed_by)
                </label>
                <input
                  value={pushedBy}
                  onChange={(e) => setPushedBy(e.target.value)}
                  placeholder="e.g. Sam Bohon"
                  className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
                />
              </div>
              <div>
                <label className="text-[10px] uppercase tracking-wide text-zinc-500 block mb-1">
                  Scope
                </label>
                <select
                  value={scope}
                  onChange={(e) => setScope(e.target.value as KillSwitchScope)}
                  className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
                >
                  {KILL_SWITCH_SCOPES.map((s) => (
                    <option key={s} value={s}>
                      {SCOPE_LABELS[s]}
                    </option>
                  ))}
                </select>
              </div>
              {scope === "department" && (
                <div>
                  <label className="text-[10px] uppercase tracking-wide text-zinc-500 block mb-1">
                    Department
                  </label>
                  <select
                    value={department}
                    onChange={(e) => setDepartment(e.target.value)}
                    className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
                  >
                    {KILL_SWITCH_DEPARTMENTS.map((d) => (
                      <option key={d} value={d}>
                        {d}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <div>
                <label className="text-[10px] uppercase tracking-wide text-zinc-500 block mb-1">
                  Set To
                </label>
                <select
                  value={active ? "kill" : "enable"}
                  onChange={(e) => setActive(e.target.value === "kill")}
                  className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
                >
                  <option value="kill">Kill AI (activate the switch)</option>
                  <option value="enable">Re-Enable AI (deactivate the switch)</option>
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-[10px] uppercase tracking-wide text-zinc-500 block mb-1">
                  Reason (recommended, especially when killing)
                </label>
                <input
                  value={reason}
                  onChange={(e) => setReason(e.target.value)}
                  placeholder="e.g. Suspected prompt-injection incident on the Sales AI assistant"
                  className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 text-sm"
                />
              </div>
            </div>

            {!confirming ? (
              <button
                disabled={!canPush}
                onClick={() => setConfirming(true)}
                className={
                  active
                    ? "bg-red-700 hover:bg-red-600 text-white font-brand font-bold uppercase tracking-wide text-xs px-5 py-2.5 rounded disabled:opacity-50"
                    : "brand-cta font-brand font-bold uppercase tracking-wide text-xs px-5 py-2.5 disabled:opacity-50"
                }
              >
                {active ? "Kill AI…" : "Push…"}
              </button>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs text-yellow-500">
                  {active
                    ? `Confirm: this pushes a real, live stop to ${status.dealer_name}'s own backend right now.`
                    : `Confirm: this re-enables AI on ${status.dealer_name}'s own backend right now.`}
                </span>
                <button
                  onClick={runPush}
                  disabled={busy === "push"}
                  className="bg-red-700 hover:bg-red-600 text-white font-brand font-bold uppercase tracking-wide text-xs px-4 py-2 rounded disabled:opacity-50"
                >
                  {busy === "push" ? "Pushing…" : "Confirm Push"}
                </button>
                <button
                  onClick={() => setConfirming(false)}
                  disabled={busy === "push"}
                  className="bg-zinc-800 text-zinc-400 hover:text-white px-4 py-2 rounded text-xs transition"
                >
                  Cancel
                </button>
              </div>
            )}

            {lastAction && (
              <div
                className={
                  lastAction.success
                    ? "mt-3 text-xs text-green-400"
                    : "mt-3 text-xs text-red-400"
                }
              >
                {lastAction.success
                  ? `Push succeeded (${lastAction.action_id}).`
                  : `Push FAILED (${lastAction.action_id}): ${lastAction.push_error} -- recorded anyway, see history below.`}
              </div>
            )}
          </div>

          <h4 className="text-[11px] uppercase tracking-wide text-zinc-500 mb-2">
            This Dealer's Push History
          </h4>
          <div className="bg-zinc-900 rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-zinc-500">
                  <th className="px-3 py-2">Pushed At</th>
                  <th className="px-3 py-2">Scope</th>
                  <th className="px-3 py-2">Set To</th>
                  <th className="px-3 py-2">Pushed By</th>
                  <th className="px-3 py-2">Result</th>
                  <th className="px-3 py-2">Reason</th>
                </tr>
              </thead>
              <tbody>
                {(history?.actions ?? []).map((a) => (
                  <ActionRow key={a.action_id} action={a} />
                ))}
                {(history?.actions ?? []).length === 0 && (
                  <tr>
                    <td colSpan={6} className="px-3 py-6 text-center text-zinc-500">
                      No kill-switch pushes have been made to this dealer yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
