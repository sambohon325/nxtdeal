"use client";

// ReceptionDesk — the front-desk phone screen (2026-07-24, Sam: the Receptionist app needs "all
// calls / texting functionality and handoffs"). A tablet-first dialpad + CRM search so the front
// desk can call or text any customer, or a free number, without leaving the app. Every call/text
// routes through startCommsSession → the CommsWorkspaceMount already mounted in AppShell, so it
// opens the same shared customer communications window used throughout NXTDeal.

import { useEffect, useRef, useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import {
  fetchProviderStatus,
  searchCustomers,
  saveContact,
  fetchRecent,
  type ProviderStatus,
  type ContactBrief,
  type RecentActivity,
} from "@/lib/customerComms";
import { startCommsSession, useCommsSession } from "@/lib/commsStore";
import { WiredScreen } from "./kit";

const KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"];

export function ReceptionDesk({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  const [provider, setProvider] = useState<ProviderStatus | null>(null);
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<ContactBrief[]>([]);
  const [searching, setSearching] = useState(false);
  const [searchError, setSearchError] = useState(false);
  const [searchRetry, setSearchRetry] = useState(0);
  const [providerError, setProviderError] = useState(false);
  const [providerRetry, setProviderRetry] = useState(0);
  const [recentError, setRecentError] = useState(false);
  const [recentRetry, setRecentRetry] = useState(0);
  const [dial, setDial] = useState("");
  const [contactDraft, setContactDraft] = useState<{ number: string; name: string } | null>(null);
  const [savingContact, setSavingContact] = useState(false);
  const [contactError, setContactError] = useState<string | null>(null);
  const contactInFlight = useRef(false);
  const [recent, setRecent] = useState<RecentActivity["items"]>([]);
  const activeSession = useCommsSession();

  async function createContact() {
    if (!contactDraft || contactInFlight.current) return;
    contactInFlight.current = true;
    setSavingContact(true);
    setContactError(null);
    try {
      const c = await saveContact(contactDraft.number, contactDraft.name.trim() || contactDraft.number);
      setQuery(c.name);
      setDial(current => current === contactDraft.number ? "" : current);
      setContactDraft(null);
    } catch {
      setContactError("Contact save could not be confirmed. Check the CRM before retrying.");
    } finally {
      contactInFlight.current = false;
      setSavingContact(false);
    }
  }

  useEffect(() => {
    let alive = true;
    setProviderError(false);
    setProvider(null);
    fetchProviderStatus().then(value => { if (alive) setProvider(value); })
      .catch(() => { if (alive) setProviderError(true); });
    return () => { alive = false; };
  }, [providerRetry]);

  // Recent calls/texts, refreshed whenever a session finishes.
  useEffect(() => {
    let alive = true;
    setRecentError(false);
    setRecent([]);
    fetchRecent(10)
      .then((r) => alive && setRecent(r.items))
      .catch(() => { if (alive) setRecentError(true); });
    return () => {
      alive = false;
    };
  }, [activeSession, recentRetry]);

  // Debounced CRM search.
  useEffect(() => {
    const q = query.trim();
    setResults([]);
    setSearchError(false);
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

  return (
    <WiredScreen app={app} screen={screen} loading={false} error={null}>
      {!provider && <div role="status" className="text-sm text-zinc-300">
        {providerError ? <>Phone provider status is unavailable. Live delivery has not been verified. <button onClick={() => setProviderRetry(n => n + 1)} className="underline">Retry provider status</button></> : "Checking phone provider status…"}
      </div>}
      {provider && !provider.live && (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-[11px] text-amber-300">
          📞 Calls &amp; texts are simulated — connect a phone provider in the Marketplace to go live.
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Search the CRM */}
        <div className="space-y-3">
          <input
            aria-label="Search customers"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search customers to call or text…"
            className="w-full rounded-lg border border-white/10 bg-white/5 px-4 py-2.5 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none"
          />
          {query.trim() && (
            <div className="space-y-2">
              {searching && <div className="text-xs text-zinc-500">Searching…</div>}
              {searchError && <p role="alert" className="text-sm text-zinc-300">Customer search is unavailable. <button onClick={() => setSearchRetry(n => n + 1)} className="underline">Retry search</button></p>}
              {!searching && !searchError && results.length === 0 && (
                <div className="text-xs text-zinc-500">No customers match “{query}”.</div>
              )}
              {results.map((c) => (
                <div key={c.id} className="rounded-xl border border-white/10 bg-white/[0.05] px-3.5 py-2.5 backdrop-blur-sm">
                  <div className="flex items-center justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate text-sm font-semibold text-white">{c.name}</div>
                      <div className="truncate text-[11px] text-zinc-500">
                        {c.phone || "no phone"}
                        {c.pipeline_state ? ` · ${c.pipeline_state}` : ""}
                      </div>
                    </div>
                    <div className="flex shrink-0 gap-1.5">
                      <button
                        disabled={!c.phone}
                        onClick={() => startCommsSession({ mode: "call", customerId: c.id, name: c.name, number: c.phone || undefined })}
                        className="rounded-full bg-[var(--app-accent)] px-3 py-1.5 text-xs font-semibold text-[var(--app-accent-text)] disabled:opacity-40"
                      >
                        Call
                      </button>
                      <button
                        disabled={!c.phone}
                        onClick={() => startCommsSession({ mode: "text", customerId: c.id, name: c.name, number: c.phone || undefined })}
                        className="rounded-full border border-white/15 px-3 py-1.5 text-xs text-zinc-200 disabled:opacity-40"
                      >
                        Text
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}

          {/* Recent conversations */}
          {recentError && <p role="alert" className="text-sm text-zinc-300">Recent conversations are unavailable. <button onClick={() => setRecentRetry(n => n + 1)} className="underline">Retry recent conversations</button></p>}
          {recent.length > 0 && (
            <div className="space-y-1.5 pt-1">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">Recent</div>
              {recent.map((r) => {
                const label = r.summary || r.number || (r.linked_entity_id ?? "Conversation");
                const icon = r.kind === "text" ? "💬" : "📞";
                return (
                  <div key={`${r.kind}-${r.id}`} className="flex items-center justify-between gap-2 rounded-lg border border-white/5 bg-white/[0.03] px-3 py-2">
                    <div className="min-w-0 text-[11px] text-zinc-300">
                      <span className="mr-1">{icon}</span>
                      <span className="truncate">{label}</span>
                    </div>
                    {r.number && (
                      <button
                        onClick={() => startCommsSession({ mode: "call", customerId: r.linked_entity_id ?? undefined, number: r.number ?? undefined, name: r.number ?? undefined })}
                        className={`shrink-0 rounded-full px-2.5 py-1 text-[10px] font-semibold ${accent.soft} ${accent.softText}`}
                      >
                        Call back
                      </button>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Dial pad */}
        <div className="rounded-2xl border border-white/10 bg-white/[0.05] p-4 backdrop-blur-sm">
          <input
            aria-label="Phone number"
            value={dial}
            onChange={(e) => setDial(e.target.value)}
            placeholder="Enter a number"
            inputMode="tel"
            className="mb-3 w-full rounded-lg border border-white/10 bg-white/5 px-4 py-3 text-center text-lg tracking-widest text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none"
          />
          <div className="grid grid-cols-3 gap-2">
            {KEYS.map((k) => (
              <button
                key={k}
                onClick={() => setDial((d) => d + k)}
                className="rounded-xl border border-white/10 bg-white/[0.04] py-3.5 text-lg font-semibold text-white transition hover:bg-white/10 active:scale-95"
              >
                {k}
              </button>
            ))}
          </div>
          <div className="mt-3 flex gap-2">
            <button
              disabled={!dial.trim()}
              onClick={() => startCommsSession({ mode: "call", number: dial.trim(), name: dial.trim() })}
              className="flex-1 rounded-full bg-[var(--app-accent)] py-2.5 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-40"
            >
              Call
            </button>
            <button
              disabled={!dial.trim()}
              onClick={() => startCommsSession({ mode: "text", number: dial.trim(), name: dial.trim() })}
              className="flex-1 rounded-full border border-white/15 py-2.5 text-sm text-zinc-200 disabled:opacity-40"
            >
              Text
            </button>
            <button
              disabled={!dial.trim() || savingContact}
              onClick={() => { if (contactInFlight.current) return; setContactError(null); setContactDraft({ number: dial.trim(), name: "" }); }}
              className="rounded-full border border-white/15 px-3 py-2.5 text-sm text-zinc-200 disabled:opacity-40"
              title="Save to CRM"
            >
              + CRM
            </button>
            {dial && (
              <button
                onClick={() => setDial((d) => d.slice(0, -1))}
                className="rounded-full border border-white/15 px-3 py-2.5 text-sm text-zinc-400"
                title="Delete"
              >
                ⌫
              </button>
            )}
          </div>
          {contactDraft && <form className="mt-3 space-y-2" aria-label="Save contact to CRM" aria-busy={savingContact} onSubmit={e => { e.preventDefault(); void createContact(); }}>
            <p className="text-sm text-zinc-300">Save {contactDraft.number} to the CRM</p>
            <input aria-label="Contact name (optional)" value={contactDraft.name} disabled={savingContact} onChange={e => setContactDraft({ ...contactDraft, name: e.target.value })} className="w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500" />
            {contactError && <p role="alert" className="text-sm text-red-300">{contactError}</p>}
            <div className="flex gap-3">
              <button type="submit" disabled={savingContact} className="text-sm text-[var(--app-accent)]">{savingContact ? "Saving…" : "Save contact"}</button>
              <button type="button" disabled={savingContact} onClick={() => { setContactDraft(null); setContactError(null); }} className="text-sm text-zinc-300">Cancel</button>
            </div>
          </form>}
        </div>
      </div>
    </WiredScreen>
  );
}
