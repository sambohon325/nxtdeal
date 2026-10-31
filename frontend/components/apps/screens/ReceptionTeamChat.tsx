"use client";

// ReceptionTeamChat — in-dealership internal chat for the front desk (2026-07-24, Sam: the
// Receptionist app needs "handoffs (including in dealership chat)"). A tablet-first two-pane view
// over the same internal messaging backend the Company side of Communications uses (useMessaging →
// /messaging/*): pick a store channel or a staff member on the left, read and reply on the right.
// This is how the receptionist hands a visitor off — "your 2pm is here" straight to the rep's app.

import { useEffect, useMemo, useRef, useState } from "react";
import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import {
  useMessaging,
  channelThreadKey,
  directThreadKey,
  type ThreadKey,
} from "@/lib/useMessaging";
import { WiredScreen } from "./kit";

type Target = { kind: "channel" | "dm"; id: string; label: string } | null;

function timeLabel(ts: string): string {
  const d = new Date(ts);
  return Number.isNaN(d.getTime()) ? "" : d.toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

export function ReceptionTeamChat({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const accent = accentOf(app);
  const m = useMessaging();
  const [target, setTarget] = useState<Target>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState<string | null>(null);
  const sendInFlight = useRef(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    m.refreshDirectory();
    m.refreshConversations();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const threadKey: ThreadKey | null = target
    ? target.kind === "channel"
      ? channelThreadKey(target.id)
      : directThreadKey(target.id)
    : null;

  const thread = threadKey ? m.messages[threadKey] ?? [] : [];
  const draft = threadKey ? drafts[threadKey] ?? "" : "";
  const historyStatus = threadKey ? m.threadStatus[threadKey] ?? "loading" : "loading";

  function selectTarget(next: Target) {
    if (sendInFlight.current) return;
    setSendError(null);
    setTarget(next);
  }

  function refreshThread() {
    if (!target) return;
    if (target.kind === "channel") void m.loadChannel(target.id);
    else void m.loadDirect(target.id);
  }

  useEffect(() => {
    if (!target) return;
    if (target.kind === "channel") m.loadChannel(target.id);
    else m.loadDirect(target.id);
    m.markOpen(target.kind === "channel" ? channelThreadKey(target.id) : directThreadKey(target.id));
    return () => {
      if (target) m.markClosed(target.kind === "channel" ? channelThreadKey(target.id) : directThreadKey(target.id));
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target?.kind, target?.id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: "end" });
  }, [thread.length]);

  const directoryOthers = useMemo(
    () => m.directory.filter((d) => d.employee_id !== m.myEmployeeId),
    [m.directory, m.myEmployeeId],
  );

  async function send() {
    if (!target || !threadKey || !draft.trim() || sendInFlight.current) return;
    sendInFlight.current = true;
    setSending(true);
    setSendError(null);
    const body = draft.trim();
    try {
      if (target.kind === "channel") await m.sendChannel(target.id, body);
      else await m.sendDirect(target.id, body);
      setDrafts(prev => ({ ...prev, [threadKey]: "" }));
    } catch {
      setSendError("Message save could not be confirmed. Your draft is kept. Refresh the conversation before retrying to avoid sending it twice.");
    } finally {
      sendInFlight.current = false;
      setSending(false);
    }
  }

  return (
    <WiredScreen app={app} screen={screen} loading={false} error={null}>
      {!m.connected && <p role="status" className="text-sm text-amber-300">Live updates are disconnected. Refresh the conversation to check for new messages.</p>}
      <div className="grid gap-4 md:grid-cols-[15rem_1fr]">
        {/* Left rail — channels + staff */}
        <div className="space-y-3">
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-zinc-500">Channels</div>
            <div className="space-y-1">
              {m.channelStatus === "loading" && <p role="status" className="text-xs text-zinc-400">Loading channels…</p>}
              {m.channelStatus === "error" && <p role="alert" className="text-xs text-amber-300">Channels are unavailable. <button onClick={m.refreshChannels} className="underline">Retry channels</button></p>}
              {m.channelStatus === "ready" && m.channels.length === 0 && <div className="text-[11px] text-zinc-400">No channels.</div>}
              {m.channels.map((c) => {
                const active = target?.kind === "channel" && target.id === c.key;
                const unread = m.unread[channelThreadKey(c.key)] ?? 0;
                return (
                  <button
                    key={c.key}
                    disabled={sending}
                    onClick={() => selectTarget({ kind: "channel", id: c.key, label: c.name })}
                    className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition ${
                      active ? `${accent.soft} ${accent.softText}` : "text-zinc-300 hover:bg-white/5"
                    }`}
                  >
                    <span className="truncate"># {c.name}</span>
                    {unread > 0 && <span className="ml-2 shrink-0 rounded-full bg-[var(--app-accent)] px-1.5 text-[10px] font-bold text-[var(--app-accent-text)]">{unread}</span>}
                  </button>
                );
              })}
            </div>
          </div>
          <div>
            <div className="mb-1 text-[10px] uppercase tracking-wider text-zinc-500">Staff</div>
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {m.directoryStatus === "loading" && <p role="status" className="text-xs text-zinc-400">Loading directory…</p>}
              {m.directoryStatus === "error" && <p role="alert" className="text-xs text-amber-300">Staff directory is unavailable. <button onClick={m.refreshDirectory} className="underline">Retry directory</button></p>}
              {m.directoryStatus === "ready" && directoryOthers.length === 0 && <p className="text-xs text-zinc-400">No other staff found.</p>}
              {directoryOthers.map((d) => {
                const active = target?.kind === "dm" && target.id === d.employee_id;
                const unread = m.unread[directThreadKey(d.employee_id)] ?? 0;
                const label = d.name || d.employee_id;
                return (
                  <button
                    key={d.employee_id}
                    disabled={sending}
                    onClick={() => selectTarget({ kind: "dm", id: d.employee_id, label })}
                    className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-sm transition ${
                      active ? `${accent.soft} ${accent.softText}` : "text-zinc-300 hover:bg-white/5"
                    }`}
                  >
                    <span className="min-w-0 truncate">
                      {label}
                      <span className="ml-1 text-[10px] capitalize text-zinc-500">{d.role}</span>
                    </span>
                    {unread > 0 && <span className="ml-2 shrink-0 rounded-full bg-[var(--app-accent)] px-1.5 text-[10px] font-bold text-[var(--app-accent-text)]">{unread}</span>}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        {/* Thread */}
        <div className="flex h-[28rem] flex-col rounded-2xl border border-white/10 bg-white/[0.04] backdrop-blur-sm">
          {!target ? (
            <div className="flex flex-1 items-center justify-center px-6 text-center text-sm text-zinc-500">
              Pick a channel or a staff member to hand off a visitor.
            </div>
          ) : (
            <>
              <div className="border-b border-white/10 px-4 py-2.5 text-sm font-semibold text-white">
                {target.kind === "channel" ? `# ${target.label}` : target.label}
                <button onClick={refreshThread} disabled={historyStatus === "loading" || sending} className="ml-3 text-xs font-normal underline disabled:opacity-40">Refresh conversation</button>
              </div>
              <div className="flex-1 space-y-2 overflow-y-auto p-4">
                {historyStatus === "loading" && <p role="status" className="text-xs text-zinc-400">Loading conversation…</p>}
                {historyStatus === "error" && <p role="alert" className="text-sm text-amber-300">Conversation history is unavailable. Refresh to try again.</p>}
                {historyStatus === "ready" && thread.length === 0 && <div className="text-xs text-zinc-400">No messages yet.</div>}
                {thread.map((msg) => {
                  const mine = msg.sender_id === m.myEmployeeId;
                  return (
                    <div key={msg.id} className={mine ? "ml-auto max-w-[80%]" : "max-w-[80%]"}>
                      <div
                        className={`rounded-2xl px-3 py-2 text-sm ${
                          mine ? "bg-[var(--app-accent)] text-[var(--app-accent-text)]" : "bg-white/[0.06] text-zinc-100"
                        }`}
                      >
                        {msg.content}
                      </div>
                      <div className={`mt-0.5 text-[10px] text-zinc-500 ${mine ? "text-right" : ""}`}>
                        {mine ? "You" : msg.sender_id} · {timeLabel(msg.timestamp)}
                      </div>
                    </div>
                  );
                })}
                <div ref={bottomRef} />
              </div>
              {sendError && <p role="alert" className="px-3 py-2 text-sm text-amber-300">{sendError}</p>}
              <div className="flex items-center gap-2 border-t border-white/10 p-2.5" aria-busy={sending}>
                <input
                  value={draft}
                  aria-label={`Message ${target.label}`}
                  disabled={sending}
                  onChange={(e) => { if (threadKey) setDrafts(prev => ({ ...prev, [threadKey]: e.target.value })); }}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && !e.shiftKey) {
                      e.preventDefault();
                      send();
                    }
                  }}
                  placeholder={`Message ${target.kind === "channel" ? `#${target.label}` : target.label}…`}
                  className="flex-1 rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none"
                />
                <button
                  onClick={send}
                  disabled={!draft.trim() || sending}
                  className="rounded-full bg-[var(--app-accent)] px-4 py-2 text-sm font-semibold text-[var(--app-accent-text)] disabled:opacity-40"
                >
                  {sending ? "Saving…" : "Send"}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </WiredScreen>
  );
}
