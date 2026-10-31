"use client";
import { WorkInput, WorkButton } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// CustomerCommsPanel — the CUSTOMER side of Communications (2026-07-24, Sam's spec). The sidebar
// half where phone calls and texts with real customers happen: search the CRM, dial a number,
// place a call or send a text, and carry out the conversation in a bottom-docked chat window that
// retains the call/text record and transcript. Backend: core/customer_comms.py
// via /comms/*.
//
// Telephony is simulated until a provider is connected (honest, same as the rest of NXTDeal) —
// so when no provider is live this surfaces a "Connect a phone provider" prompt into the
// Marketplace Communications category.
//
// The workspace (CommsWorkspaceModal) is a bottom-docked instant-message window matching the
// Company side's ChatDock, opened from the global commsStore so any dashboard's Call/Text button
// routes into the same window.

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import {
  fetchProviderStatus,
  searchCustomers,
  saveContact,
  placeCall,
  endCall,
  sendText,
  fetchRecent,
  type ProviderStatus,
  type ContactBrief,
  type CallView,
  type RecentActivity,
} from "@/lib/customerComms";
import { startCommsSession, closeCommsSession, useCommsSession, type CommsSession } from "@/lib/commsStore";
import { CommsQuickActions } from "@/components/CommsQuickActions";

export type { CommsSession };



export function CustomerCommsPanel() {
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ContactBrief[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [recentError, setRecentError] = useState(false);
  const [searchRetry, setSearchRetry] = useState(0);
  const [recentRetry, setRecentRetry] = useState(0);
  const [dial, setDial] = useState("");
  const [recent, setRecent] = useState<RecentActivity["items"]>([]);
  // Watch the global comms session so the recent list refreshes when a call/text finishes.
  const activeSession = useCommsSession();

  useEffect(() => {
    fetchProviderStatus().then(setProvider).catch(() => {});
  }, []);

  useEffect(() => {
    let alive = true;
    setRecentError(false);
    setRecent([]);
    fetchRecent(12)
      .then((r) => alive && setRecent(r.items))
      .catch(() => { if (alive) setRecentError(true); });
    return () => {
      alive = false;
    };
  }, [activeSession, recentRetry]);

  useEffect(() => {
    const q = query.trim();
    setSearchError(false);
    setResults([]);
    if (!q) {
      setSearching(false);
      return;
    }
    let alive = true;
    setSearching(true);
    const t = setTimeout(() => {
      searchCustomers(q)
        .then((r) => alive && setResults(r.results))
        .catch(() => { if (alive) setSearchError(true); })
        .finally(() => alive && setSearching(false));
    }, 250);
    return () => {
      alive = false;
      clearTimeout(t);
    };
  }, [query, searchRetry]);

  const btn = "text-[11px] font-brand font-semibold uppercase tracking-wide px-2 py-1.5 rounded-md transition";

  return (
    <div className="space-y-3 text-sm">
      {provider && !provider.live && (
        <Link
          href="/apps"
          onClick={(e) => {
            e.preventDefault();
            alert("Open Settings (gear) → Marketplace → Communications to connect Twilio, Bandwidth, or another phone provider.");
          }}
          className="block rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300"
        >
          📞 Calls & texts are simulated — connect a phone provider in the Marketplace to go live.
        </Link>
      )}

      {/* Search the CRM */}
      <WorkInput
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        aria-label="Search customers to call or text"
        placeholder="Search customers to call or text…"
        className="w-full h-8 px-3 text-xs rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none focus:border-brand-teal"
      />

      {query.trim() && (
        <div className="space-y-1.5">
          {searching && <div className="text-xs text-zinc-600">Searching…</div>}
          {searchError && <div role="alert" className="text-xs text-amber-200">Customer search is unavailable. <WorkButton type="submit" className="underline" onClick={() => setSearchRetry((value) => value + 1)}>Retry search</WorkButton></div>}
          {!searching && !searchError && results.length === 0 && (
            <div className="text-xs text-zinc-600">No customers match “{query}”.</div>
          )}
          {results.map((c) => (
            <div key={c.id} className="rounded-lg bg-zinc-900 border border-transparent hover:border-brand-teal/50 px-3 py-2">
              <div className="flex items-center justify-between gap-2">
                <div className="min-w-0">
                  <div className="truncate font-brand font-semibold uppercase tracking-wide text-xs">{c.name}</div>
                  <div className="truncate text-xs text-zinc-500">{c.phone || "no phone"}{c.pipeline_state ? ` · ${c.pipeline_state}` : ""}</div>
                </div>
                <div className="flex shrink-0 gap-1">
                  <WorkButton type="submit"
                    disabled={!c.phone}
                    onClick={() => startCommsSession({ mode: "call", customerId: c.id, name: c.name, number: c.phone || undefined })}
                    className={`${btn} bg-brand-teal text-black disabled:opacity-40`}
                  >
                    Call
                  </WorkButton>
                  <WorkButton type="submit"
                    disabled={!c.phone}
                    onClick={() => startCommsSession({ mode: "text", customerId: c.id, name: c.name, number: c.phone || undefined })}
                    className={`${btn} text-zinc-300 hover:bg-zinc-800 disabled:opacity-40`}
                  >
                    Text
                  </WorkButton>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Dial pad — a free number */}
      <div className="rounded-lg bg-zinc-900 p-3 space-y-2">

        <WorkField label="Dial a number"><WorkInput
          value={dial}
          onChange={(e) => setDial(e.target.value)}
          placeholder="e.g. 555-0100"
          inputMode="tel"
          className="w-full h-8 px-3 text-xs rounded-lg bg-zinc-950 border border-zinc-800 focus:outline-none focus:border-brand-teal"
        /></WorkField>
        <div className="flex gap-1.5">
          <WorkButton type="submit"
            disabled={!dial.trim()}
            onClick={() => startCommsSession({ mode: "call", number: dial.trim(), name: dial.trim() })}
            className={`${btn} flex-1 bg-brand-teal text-black disabled:opacity-40`}
          >
            Call
          </WorkButton>
          <WorkButton type="submit"
            disabled={!dial.trim()}
            onClick={() => startCommsSession({ mode: "text", number: dial.trim(), name: dial.trim() })}
            className={`${btn} flex-1 text-zinc-300 hover:bg-zinc-800 disabled:opacity-40`}
          >
            Text
          </WorkButton>
          <WorkButton type="submit"
            disabled={!dial.trim()}
            onClick={async () => {
              const name = prompt("Save this number to the CRM as — name?") || dial.trim();
              try {
                const c = await saveContact(dial.trim(), name);
                setQuery(c.name);
                setDial("");
              } catch {
                /* ignore */
              }
            }}
            className={`${btn} text-zinc-300 hover:bg-zinc-800 disabled:opacity-40`}
            title="Save to CRM"
          >
            + CRM
          </WorkButton>
        </div>
      </div>

      {recentError && <div role="alert" className="text-xs text-amber-200">Recent conversations are unavailable. <WorkButton type="submit" className="underline" onClick={() => setRecentRetry((value) => value + 1)}>Retry recent conversations</WorkButton></div>}
      {/* Recent conversations — the store's calls + texts, newest first. */}
      {recent.length > 0 && (
        <div className="space-y-1.5">
          <div className="text-xs uppercase tracking-wider text-zinc-500">Recent conversations</div>
          {recent.map((r) => {
            const label = r.summary || r.number || (r.linked_entity_id ?? "Conversation");
            const icon = r.kind === "text" ? "💬" : "📞";
            return (
              <div key={`${r.kind}-${r.id}`} className="flex items-center justify-between gap-2 rounded-lg bg-zinc-900 px-3 py-2">
                <div className="min-w-0">
                  <div className="truncate text-xs text-zinc-300">
                    <span className="mr-1">{icon}</span>
                    {label}
                  </div>
                  <div className="text-xs text-zinc-600">
                    {r.direction ?? ""}{r.status ? ` · ${r.status}` : ""}
                  </div>
                </div>
                {r.number && (
                  <div className="shrink-0">
                    <CommsQuickActions
                      customerId={r.linked_entity_id ?? undefined}
                      phone={r.number}
                      name={r.number ?? undefined}
                      size="xs"
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// The call/text workspace — a bottom-docked chat window (2026-07-24, Sam: route customer calls/
// texts through the SAME instant-message windows the Company side uses, for consistency). Matches
// ChatDock's look: fixed bottom, chat bubbles, a message input. Calls render their live status +
// transcript in the same window; texts remain a conversation thread. Driven by the global
// commsStore so any dashboard's Call/Text button opens it.
export function CommsWorkspaceModal({ session, onClose }: { session: CommsSession | null; onClose: () => void }) {
  const [call, setCall] = useState<CallView | null>(null);
  const [phase, setPhase] = useState<"idle" | "connecting" | "live" | "ended" | "text" | "error">("idle");
  const [transcript, setTranscript] = useState<string | null>(null);
  const [messages, setMessages] = useState<{ body: string; delivery: string }[]>([]);
  const [textBody, setTextBody] = useState("");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const generation = useRef(0);
  const inFlight = useRef(false);

  useEffect(() => {
    const current = ++generation.current;
    inFlight.current = false;
    setBusy(false);
    if (!session) return;
    setCall(null);
    setTranscript(null);
    setErrorMsg(null);
    setTextBody("");
    setMessages([]);
    if (session.mode === "call") {
      setPhase("connecting");
      placeCall({ customer_id: session.customerId, number: session.number })
        .then((r) => {
          if (generation.current !== current) return;
          if ("error" in r) {
            setErrorMsg(r.error);
            setPhase("error");
          } else {
            setCall(r.call);
            setPhase("live");
          }
        })
        .catch(() => {
          if (generation.current !== current) return;
          setErrorMsg("The call could not be confirmed. Check recent activity before trying again.");
          setPhase("error");
        });
    } else {
      setPhase("text");
    }
    return () => { generation.current++; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  async function hangUp() {
    if (!call || inFlight.current) return;
    const current = generation.current;
    inFlight.current = true;
    setBusy(true);
    setErrorMsg(null);
    try {
      const r = await endCall(call.id, "Call completed from Communications.");
      if (generation.current !== current) return;
      if ("error" in r) throw new Error("Call completion unconfirmed");
      setTranscript(r.communication?.recording?.transcript ?? r.communication?.body ?? null);
      setPhase("ended");
    } catch {
      if (generation.current === current) setErrorMsg("Call completion could not be confirmed. Check recent activity before trying again.");
    } finally {
      if (generation.current === current) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  }

  async function submitText() {
    if (!session || !textBody.trim() || inFlight.current) return;
    const current = generation.current;
    const body = textBody.trim();
    inFlight.current = true;
    setBusy(true);
    setErrorMsg(null);
    try {
      const r = await sendText({ body, customer_id: session.customerId, number: session.number });
      if (generation.current !== current) return;
      if ("error" in r) throw new Error("Message submission unconfirmed");
      const delivery = r.dispatch?.simulated === true
        ? "Demo only — no SMS sent"
        : "Recorded — delivery not confirmed";
      setMessages((m) => [...m, { body, delivery }]);
      if (r.dispatch?.error) {
        setErrorMsg("The message was recorded, but dispatch reported a problem. Your draft is kept. Check recent activity before retrying.");
      } else {
        setTextBody("");
      }
    } catch {
      if (generation.current === current) setErrorMsg("Message submission could not be confirmed. Your draft is kept. Check recent activity before retrying to avoid sending twice.");
    } finally {
      if (generation.current === current) {
        inFlight.current = false;
        setBusy(false);
      }
    }
  }

  if (!session) return null;

  return (
    <div className="fixed bottom-0 left-4 z-50 flex items-end">
      <div className="flex h-[30rem] w-[26rem] flex-col rounded-t-xl border border-zinc-800 bg-zinc-950 shadow-2xl">
        {/* header — matches ChatDock */}
        <div className="flex items-center justify-between rounded-t-xl border-b border-zinc-800 bg-zinc-900 px-3 py-2">
          <div className="min-w-0">
            <div className="truncate text-sm font-medium text-white">{session.name || session.number}</div>
            <div className="text-xs uppercase tracking-wider text-brand-teal">
              {session.mode === "call" ? "Call" : "Text"}{session.number ? ` · ${session.number}` : ""}
            </div>
          </div>
          <WorkButton type="submit" aria-label="Close customer conversation" onClick={onClose} className="text-xs text-zinc-500 transition hover:text-[#EE3C25]" title="Close">✕</WorkButton>
        </div>

        {/* body — chat area */}
        <div className="flex-1 space-y-2 overflow-y-auto p-3 text-sm text-zinc-200">
          {errorMsg && <div role="alert" className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{errorMsg}</div>}

          {session.mode === "call" && (
            <>
              {phase === "connecting" && <div className="py-6 text-center text-zinc-400">Connecting…</div>}
              {(phase === "live" || phase === "ended") && (
                <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 px-3 py-2 text-center">
                  <div className={phase === "live" ? "font-semibold text-emerald-400" : "text-zinc-400"}>
                    {phase === "live" ? "Call record open" : "Call ended"}
                  </div>
                  <div className="mt-1 text-xs text-zinc-400">
                    Call records are retained here. Phone delivery requires a connected provider; demo calls do not reach a customer.
                  </div>
                </div>
              )}
              {phase === "ended" && transcript && (
                <div>
                  <div className="mb-1 text-xs uppercase tracking-wider text-zinc-500">Transcript (simulated)</div>
                  <div className="rounded-lg border border-zinc-800 bg-zinc-950 p-3 text-xs whitespace-pre-wrap text-zinc-300">
                    {transcript}
                  </div>
                </div>
              )}
            </>
          )}

          {session.mode === "text" && (
            <>
              {messages.length === 0 && <div className="text-xs text-zinc-600">No messages yet — say hello.</div>}
              {messages.map((m, i) => (
                <div key={i} className="ml-auto max-w-[85%]">
                  <div className="rounded-lg bg-brand-teal px-3 py-2 text-sm text-black">{m.body}</div>
                  <div className="mt-1 text-right text-xs text-zinc-400">{m.delivery}</div>

                </div>
              ))}
              {busy && <div className="ml-auto text-xs text-zinc-600">sending…</div>}
            </>
          )}
        </div>

        {/* footer — IM input for text; call controls for call */}
        {session.mode === "text" ? (
          <div className="flex items-center gap-2 border-t border-zinc-800 p-2">
            <WorkInput
              value={textBody}
              onChange={(e) => setTextBody(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  submitText();
                }
              }}
              disabled={busy}
              aria-label="Customer text message"
              placeholder="Type a message…"
              className="flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-3 py-1.5 text-sm focus:border-brand-teal focus:outline-none"
            />
            <WorkButton type="submit"
              onClick={submitText}
              disabled={busy || !textBody.trim()}
              className="rounded-lg bg-brand-teal px-3 py-1.5 text-sm font-semibold text-black disabled:opacity-40"
            >
              Send
            </WorkButton>
          </div>
        ) : (
          <div className="border-t border-zinc-800 p-2">
            {phase === "live" ? (
              <WorkButton type="submit" variant="danger"
                onClick={hangUp}
                disabled={busy}
                className="w-full rounded-full bg-red-600 py-2 text-sm font-semibold text-white disabled:opacity-50"
              >
                {busy ? "Ending…" : "End call"}
              </WorkButton>
            ) : (
              <WorkButton type="submit" onClick={onClose} className="w-full rounded-full bg-zinc-800 py-2 text-sm text-zinc-200">
                Close
              </WorkButton>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// Mount ONCE (in CommunicationsPanel, which is present on every app page). Reads the global
// comms store, so any dashboard's Call/Text button (startCommsSession) opens this same workspace.
export function CommsWorkspaceMount() {
  const session = useCommsSession();
  return <CommsWorkspaceModal session={session} onClose={closeCommsSession} />;
}
