"use client";

// The real visitor-facing chat widget for a published NXTDeal site (session 113
// follow-up, closing the Live Chat "omnichannel" slice's own final gap: the backend
// chat API and the authenticated employee inbox have both existed since session 85,
// but nothing on the actual public /site/[id] page ever consumed it -- a visitor had
// no way to actually start a conversation. Deliberately a small, self-contained
// floating widget rather than folded into SiteSectionRenderer, since it's chrome
// (persistent across every page of the site), not a page section.
//
// Session id is kept in sessionStorage, scoped per site, so a page navigation within
// the same visit keeps the same conversation without leaking across different sites
// a visitor might browse in the same browser tab.
import themeTokens from "@/lib/websiteThemeTokens.json";
import type { CSSProperties } from "react";
import styles from "./PublicChatWidget.module.css";
import { useEffect, useRef, useState, useCallback } from "react";
import {
  publicStartChat,
  publicListChatDepartments,
  publicSendChatMessage,
  publicListChatMessages,
  publicGetChatSession,
  type ChatDepartment,
  type ChatMessage,
  type ChatSession,
} from "@/lib/websites";

const DEPT_LABELS: Record<ChatDepartment, string> = {
  sales: "Sales",
  service: "Service",
  finance: "Finance",
  general: "General Question",
};

function storageKey(websiteId: string) {
  return `dealeros_chat_session_${websiteId}`;
}

export function PublicChatWidget({ websiteId, siteName, theme }: { websiteId: string; siteName: string; theme?: string }) {
  const tokens=themeTokens[theme as keyof typeof themeTokens];
  const themeStyle=tokens?Object.fromEntries(Object.entries(tokens).map(([key,value])=>[`--chat-${key}`,value])) as CSSProperties:undefined;
  const [open, setOpen] = useState(false);
  const [departments, setDepartments] = useState<ChatDepartment[]>([]);
  const [session, setSession] = useState<ChatSession | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [starting, setStarting] = useState(false);
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");

  // Pre-chat form state
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [dept, setDept] = useState<ChatDepartment>("general");
  const [firstMessage, setFirstMessage] = useState("");

  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    publicListChatDepartments().then(setDepartments).catch(() => setDepartments(["sales", "service", "finance", "general"]));
  }, []);

  // Resume an existing session for this site, if one exists in this tab already.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const savedId = window.sessionStorage.getItem(storageKey(websiteId));
    if (!savedId) return;
    publicGetChatSession(savedId)
      .then((s) => setSession(s))
      .catch(() => window.sessionStorage.removeItem(storageKey(websiteId)));
  }, [websiteId]);

  const refreshMessages = useCallback(() => {
    if (!session) return;
    publicListChatMessages(session.id)
      .then(setMessages)
      .catch(() => {});
  }, [session]);

  useEffect(() => {
    if (!session) return;
    refreshMessages();
    const t = setInterval(refreshMessages, 4000);
    return () => clearInterval(t);
  }, [session, refreshMessages]);

  useEffect(() => {
    // Also poll the session itself so "claimed"/"closed" status updates live.
    if (!session) return;
    const t = setInterval(() => {
      publicGetChatSession(session.id).then(setSession).catch(() => {});
    }, 8000);
    return () => clearInterval(t);
  }, [session?.id]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  async function handleStart() {
    setStarting(true);
    setError("");
    try {
      const s = await publicStartChat(websiteId, name || undefined, email || undefined, firstMessage || undefined, dept);
      window.sessionStorage.setItem(storageKey(websiteId), s.id);
      setSession(s);
    } catch {
      setError("Unable to start the conversation. Your message is still here; please try again.");
    } finally {
      setStarting(false);
    }
  }

  async function handleSend() {
    if (!session || !draft.trim() || sending) return;
    const body = draft.trim();
    setSending(true); setError("");
    try {
      await publicSendChatMessage(session.id, body);
      setDraft("");
      refreshMessages();
    } catch {
      setError("Message could not be confirmed. Your text is preserved; check the conversation before retrying.");
    } finally { setSending(false); }
  }

  function endChat() {
    window.sessionStorage.removeItem(storageKey(websiteId));
    setSession(null);
    setMessages([]);
    setName("");
    setEmail("");
    setFirstMessage("");
  }

  return (
    <div style={themeStyle} className={`fixed bottom-5 right-5 z-40 font-sans ${tokens ? styles.loneStar : ""}`} onKeyDown={(e) => { if (e.key === "Escape") setOpen(false); }}>
      {open && (
        <div role="dialog" aria-label="Your dealership assistant" data-chat-panel className="w-80 sm:w-96 h-[28rem] bg-white border border-zinc-200 rounded-xl shadow-2xl flex flex-col overflow-hidden mb-3">
          {error && <p role="alert" className="p-3 text-xs text-red-700 bg-red-50">{error}</p>}
          <div data-chat-header className="bg-zinc-900 text-white px-4 py-3 flex items-center justify-between">
            <div>
              <div className="text-sm font-semibold truncate max-w-[14rem]">{siteName}</div>
              <div className="text-[11px] text-zinc-400">
                {session ? (session.status === "closed" ? "Conversation ended" : session.status === "claimed" ? "A team member has joined" : "Waiting for a reply…") : "Chat with us"}
              </div>
            </div>
            <button aria-label="Close chat" onClick={() => setOpen(false)} className="text-zinc-400 hover:text-white text-lg leading-none">
              ×
            </button>
          </div>

          {!session ? (
            <div className="flex-1 overflow-y-auto p-4 space-y-3 text-sm">
              <div className="text-zinc-600">Tell us a bit about what you need and we'll connect you with the right team.</div>
              <div className="flex flex-wrap gap-1.5">
                {departments.map((d) => (
                  <button
                    key={d}
                    aria-pressed={dept === d}
                    onClick={() => setDept(d)}
                    className={`text-xs px-2.5 py-1 rounded-full border ${
                      dept === d ? "bg-zinc-900 text-white border-zinc-900" : "border-zinc-300 text-zinc-600 hover:border-zinc-500"
                    }`}
                  >
                    {DEPT_LABELS[d]}
                  </button>
                ))}
              </div>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Your name (optional)"
                className="w-full border border-zinc-300 rounded px-3 py-2 text-sm"
              />
              <input
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email (optional)"
                className="w-full border border-zinc-300 rounded px-3 py-2 text-sm"
              />
              <textarea
                value={firstMessage}
                onChange={(e) => setFirstMessage(e.target.value)}
                placeholder="What can we help with?"
                rows={3}
                className="w-full border border-zinc-300 rounded px-3 py-2 text-sm resize-none"
              />
              <button
                onClick={handleStart}
                disabled={starting}
                className="w-full bg-brand-teal text-black font-medium text-sm rounded py-2 disabled:opacity-50"
              >
                {starting ? "Starting…" : "Start Chat"}
              </button>
            </div>
          ) : (
            <>
              <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-2 bg-zinc-50">
                {messages.length === 0 && <div className="text-xs text-zinc-400 text-center pt-6">Say hello — a real person (or our AI receptionist) will be right with you.</div>}
                {messages.map((m) => (
                  <div
                    key={m.id}
                    className={`text-xs max-w-[80%] p-2 rounded-lg ${
                      m.sender === "visitor"
                        ? "ml-auto bg-brand-teal text-black"
                        : m.sender === "ai"
                        ? "bg-white border border-zinc-200 text-zinc-800"
                        : "bg-zinc-900 text-white"
                    }`}
                  >
                    {m.sender === "ai" && <div className="text-[9px] uppercase tracking-wide text-zinc-400 mb-0.5">✨ Assistant</div>}
                    {m.body}
                  </div>
                ))}
              </div>
              <div className="p-2.5 border-t border-zinc-200 flex gap-2">
                {session.status === "closed" ? (
                  <button onClick={endChat} className="w-full text-xs text-zinc-500 py-2">
                    Conversation ended — start a new chat
                  </button>
                ) : (
                  <>
                    <input
                      disabled={sending}
                      value={draft}
                      onChange={(e) => setDraft(e.target.value)}
                      onKeyDown={(e) => e.key === "Enter" && handleSend()}
                      placeholder="Type a message…"
                      className="flex-1 border border-zinc-300 rounded px-3 py-2 text-sm"
                    />
                    <button disabled={sending||!draft.trim()} onClick={handleSend} className="bg-zinc-900 text-white text-xs font-medium rounded px-3">
                      Send
                    </button>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      )}

      <button
        onClick={() => setOpen((v) => !v)}
        className="w-14 h-14 rounded-full bg-brand-teal text-black shadow-xl flex items-center justify-center text-2xl hover:scale-105 transition"
        data-chat-launcher
        aria-expanded={open}
        aria-label={open ? "Close chat" : "Open chat"}
      >
        {tokens ? <><span className={styles.dot} aria-hidden="true" />{open ? "Close assistant" : "Your dealership assistant"}</> : (open ? "\u00d7" : "\u{1f4ac}")}
      </button>
    </div>
  );
}
