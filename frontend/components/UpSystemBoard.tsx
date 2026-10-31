"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// The Up System (session 100 follow-up) -- rendered inside Sales' "Up System"
// workflow modal (core/workflow_catalog.py's sales.up_system), alongside the generic
// LiveDataPanel's read-only rotation view. This component is where the actual real
// actions live: log a walk-in/phone-up, see who's next in the floor rotation, toggle
// reps in/out of today's board, work an open Up through to an outcome, and the
// Be-Back Board for customers expected to return.
//
// Session 102 follow-up (Sam: "it doesn't look like the tabs are working... it needs
// to be a working process, not just a list") -- this used to render its ENTIRE board
// identically on every one of Up System's 5 named tabs, which is exactly why the tabs
// looked broken: switching tabs changed nothing. Now takes a `section` prop and shows
// only the piece of the board that matches whichever tab is selected -- Floor Rotation
// / Log an Up / Working Ups / Be-Back Board / Outcome Tracking (new: real resolved
// sold/no_sale history, not fabricated).
import { useEffect, useState } from "react";
import {
  getRotation,
  setBoardActive,
  logUp,
  updateUpStatus,
  listUps,
  getBeBackBoard,
  type Rotation,
  type Up,
  type UpType,
  type UpStatus,
} from "@/lib/upSystem";
import { requestTO, type ToReason } from "@/lib/managerTo";

export type UpSystemSection = "rotation" | "log" | "working" | "beback" | "outcomes";

const REASON_LABELS: Record<ToReason, string> = {
  price: "Price",
  payment: "Payment",
  trade_value: "Trade Value",
  financing: "Financing",
  just_looking: "Just Looking",
  spouse_approval: "Spouse Approval",
  product_objection: "Product Objection",
  other: "Other",
};

const STATUS_LABELS: Record<UpStatus, string> = {
  working: "Working",
  demo: "Demo",
  worksheet: "Worksheet",
  be_back: "Be-Back",
  sold: "Sold",
  no_sale: "No Sale",
};

const NEXT_STATUS: Partial<Record<UpStatus, UpStatus[]>> = {
  working: ["demo", "worksheet", "be_back", "no_sale"],
  demo: ["worksheet", "be_back", "no_sale"],
  worksheet: ["sold", "be_back", "no_sale"],
  be_back: ["working", "no_sale"],
};

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

export function UpSystemBoard({ section = "working" }: { section?: UpSystemSection }) {
  const [rotation, setRotation] = useState<Rotation | null>(null);
  const [openUps, setOpenUps] = useState<Up[]>([]);
  const [beBacks, setBeBacks] = useState<Up[]>([]);
  const [resolved, setResolved] = useState<Up[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const [upType, setUpType] = useState<UpType>("walk_in");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phone, setPhone] = useState("");
  const [logged, setLogged] = useState<string | null>(null);

  const [toFormFor, setToFormFor] = useState<string | null>(null);
  const [toReason, setToReason] = useState<ToReason>("price");
  const [toSentFor, setToSentFor] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    Promise.all([getRotation(), listUps({ status: "working" }), getBeBackBoard(), listUps({})])
      .then(([rot, working, bb, all]) => {
        setRotation(rot);
        setOpenUps(working);
        setBeBacks(bb);
        setResolved(all.filter((u) => u.up_status === "sold" || u.up_status === "no_sale"));
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load the Up System"))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleToggleActive(employeeId: string, active: boolean) {
    setBusy(true);
    try {
      const rot = await setBoardActive(employeeId, active);
      setRotation(rot);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update the board");
    } finally {
      setBusy(false);
    }
  }

  async function handleLogUp() {
    if (!firstName.trim()) {
      setError("A first name is required to log an Up.");
      return;
    }
    setBusy(true);
    try {
      const up = await logUp({ up_type: upType, first_name: firstName.trim(), last_name: lastName.trim(), phone: phone.trim() || null });
      setFirstName("");
      setLastName("");
      setPhone("");
      setLogged(`${up.first_name || ""} ${up.last_name || ""}`.trim() + (up.assigned_to_name ? ` assigned to ${up.assigned_to_name}` : ""));
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to log the Up");
    } finally {
      setBusy(false);
    }
  }

  async function handleStatus(leadId: string, status: UpStatus) {
    setBusy(true);
    try {
      await updateUpStatus(leadId, status);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update status");
    } finally {
      setBusy(false);
    }
  }

  async function handleRequestTO(leadId: string) {
    setBusy(true);
    try {
      await requestTO(leadId, toReason);
      setToFormFor(null);
      setToSentFor(leadId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to request a TO");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="mb-5 text-xs text-zinc-600">Loading…</div>;
  }

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}

      {section === "rotation" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Floor Rotation</div>
          {rotation?.next_up && (
            <div className="text-xs text-zinc-500 mb-2">
              Next up: <span style={{ color: "#3FBCC4" }}>{rotation.next_up.name}</span>
            </div>
          )}
          <div className="grid grid-cols-2 gap-1.5">
            {(rotation?.board || []).map((slot) => (
              <div key={slot.employee_id} className="flex items-center justify-between text-xs px-2 py-1 rounded border border-zinc-800">
                <span className={slot.active ? "text-zinc-200" : "text-zinc-600 line-through"}>{slot.name}</span>
                <WorkButton type="submit" onClick={() => handleToggleActive(slot.employee_id, !slot.active)} disabled={busy} className="text-zinc-500 hover:text-white transition">
                  {slot.active ? "On" : "Off"}
                </WorkButton>
              </div>
            ))}
            {(rotation?.board || []).length === 0 && (
              <div className="text-xs text-zinc-600">No one is on the board yet.</div>
            )}
          </div>
        </div>
      )}

      {section === "log" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 space-y-2">
          <div className="text-xs font-medium text-zinc-200 mb-1">Log an Up</div>
          <div className="flex gap-2">
            <WorkButton type="submit"
              onClick={() => setUpType("walk_in")}
              className={upType === "walk_in" ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium" : "text-xs px-2.5 py-1 rounded-md text-zinc-400 border border-zinc-700"}
            >
              Walk-In
            </WorkButton>
            <WorkButton type="submit"
              onClick={() => setUpType("phone_up")}
              className={upType === "phone_up" ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium" : "text-xs px-2.5 py-1 rounded-md text-zinc-400 border border-zinc-700"}
            >
              Phone-Up
            </WorkButton>
          </div>
          <div className="flex gap-2">
            <WorkField label="First name"><WorkInput
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              placeholder="First name"
              className="flex-1 text-xs rounded-md border border-zinc-700 bg-black px-2.5 py-1.5 text-white placeholder:text-zinc-600"
            /></WorkField>
            <WorkField label="Last name (optional)"><WorkInput
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              placeholder="Last name (optional)"
              className="flex-1 text-xs rounded-md border border-zinc-700 bg-black px-2.5 py-1.5 text-white placeholder:text-zinc-600"
            /></WorkField>
            <WorkField label="Phone (optional)"><WorkInput
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="Phone (optional)"
              className="flex-1 text-xs rounded-md border border-zinc-700 bg-black px-2.5 py-1.5 text-white placeholder:text-zinc-600"
            /></WorkField>
          </div>
          {rotation?.next_up && (
            <div className="text-xs text-zinc-500">
              Will be assigned to next in rotation: <span className="text-zinc-300">{rotation.next_up.name}</span>
            </div>
          )}
          <WorkButton type="submit" variant="primary" onClick={handleLogUp} disabled={busy} className="text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium transition disabled:opacity-50">
            {busy ? "Logging…" : "Log Up"}
          </WorkButton>
          {logged && <div className="text-xs text-emerald-400">Logged — {logged}.</div>}
        </div>
      )}

      {section === "working" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Working Ups ({openUps.length})</div>
          {openUps.length === 0 ? (
            <div className="text-xs text-zinc-600">No open Ups right now.</div>
          ) : (
            <div className="space-y-1.5">
              {openUps.map((u) => (
                <div key={u.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-zinc-200 truncate">
                        {u.first_name} {u.last_name} · {u.up_type === "walk_in" ? "Walk-In" : "Phone-Up"} · {STATUS_LABELS[u.up_status]}
                      </div>
                      <div className="text-zinc-500">{u.assigned_to_name} · {fmt(u.up_logged_at)}</div>
                    </div>
                    <div className="flex gap-1 shrink-0">
                      {(NEXT_STATUS[u.up_status] || []).map((s) => (
                        <WorkButton type="submit"
                          key={s}
                          onClick={() => handleStatus(u.id, s)}
                          disabled={busy}
                          className="text-xs px-1.5 py-0.5 rounded bg-zinc-200 text-black font-medium"
                        >
                          {STATUS_LABELS[s]}
                        </WorkButton>
                      ))}
                      <WorkButton type="submit"
                        onClick={() => setToFormFor(toFormFor === u.id ? null : u.id)}
                        disabled={busy}
                        className="text-xs px-1.5 py-0.5 rounded border border-amber-800 text-amber-400"
                      >
                        Request TO
                      </WorkButton>
                    </div>
                  </div>

                  {toFormFor === u.id && (
                    <div className="flex items-center gap-1.5 mt-1.5 pt-1.5 border-t border-zinc-800">
                      <WorkField label="Turnover reason"><WorkSelect
                        value={toReason}
                        onChange={(e) => setToReason(e.target.value as ToReason)}
                        className="text-xs rounded border border-zinc-700 bg-black px-1.5 py-1 text-white"
                      >
                        {(Object.keys(REASON_LABELS) as ToReason[]).map((r) => (
                          <option key={r} value={r}>{REASON_LABELS[r]}</option>
                        ))}
                      </WorkSelect></WorkField>
                      <WorkButton type="submit" variant="primary" onClick={() => handleRequestTO(u.id)} disabled={busy} className="text-xs px-2 py-1 rounded bg-brand-blue text-white font-medium">
                        Send to Manager
                      </WorkButton>
                    </div>
                  )}

                  {toSentFor === u.id && (
                    <div className="text-xs text-emerald-400 mt-1">TO requested — a manager will pick this up.</div>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {section === "beback" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Be-Back Board ({beBacks.length})</div>
          {beBacks.length === 0 ? (
            <div className="text-xs text-zinc-600">Nobody's expected back right now.</div>
          ) : (
            <div className="space-y-1.5">
              {beBacks.map((u) => (
                <div key={u.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800 flex items-center justify-between gap-2">
                  <div className="text-zinc-200">{u.first_name} {u.last_name} · {u.assigned_to_name}</div>
                  <WorkButton type="submit" onClick={() => handleStatus(u.id, "working")} disabled={busy} className="text-xs px-1.5 py-0.5 rounded bg-zinc-200 text-black font-medium">
                    Returned
                  </WorkButton>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {section === "outcomes" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="flex items-center gap-3 mb-1.5">
            <span className="text-xs font-medium text-zinc-200">Outcome Tracking</span>
            <span className="text-xs text-zinc-500">
              {resolved.filter((u) => u.up_status === "sold").length} sold · {resolved.filter((u) => u.up_status === "no_sale").length} no sale
            </span>
          </div>
          {resolved.length === 0 ? (
            <div className="text-xs text-zinc-600">No Ups have reached a final outcome yet.</div>
          ) : (
            <div className="space-y-1.5">
              {resolved.map((u) => (
                <div key={u.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800 flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <div className="text-zinc-200 truncate">{u.first_name} {u.last_name} · {u.assigned_to_name}</div>
                    <div className="text-zinc-500">{u.up_type === "walk_in" ? "Walk-In" : "Phone-Up"} · logged {fmt(u.up_logged_at)}</div>
                  </div>
                  <span className={u.up_status === "sold" ? "text-xs px-1.5 py-0.5 rounded border border-emerald-800 text-emerald-400" : "text-xs px-1.5 py-0.5 rounded border border-zinc-700 text-zinc-500"}>
                    {STATUS_LABELS[u.up_status]}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
