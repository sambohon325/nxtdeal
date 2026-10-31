"use client";

// Gmail/Google Chat-style floating messenger (session 28 -- Sam: "a text chat option
// similar to gchat in gmail where its on the left side at the bottom"). Fixed to the
// bottom-left of the viewport on every authenticated page, on top of everything else.
// Threads are opened from the Communications sidebar block (components/
// CommunicationsPanel.tsx) or from the "+" launcher here; each open thread renders as
// a small floating window (or collapses to just a head chip) using the single shared
// lib/useMessaging.ts hook instance the page passes in, so unread counts / open state
// never drift between the sidebar and the dock.
//
// Also carries the two other pieces of Sam's session 28 ask that live "in the
// conversation" rather than in the sidebar: pin sharing (drag a pin from Knowledge onto
// a thread's compose box, or use the paperclip attach picker) and "break out into the
// central chat box" (the ↗ button hands the thread's recent messages to the page's main
// AI chat).

import { useState, type DragEvent } from "react";
import type { Messaging, ThreadKey, AttachedPinRef } from "@/lib/useMessaging";
import type { Pin, PinKind } from "@/lib/pins";
import { MessageContent } from "@/components/MessageContent";
import { PinIcon } from "@/components/Icons";
import { EmojiPicker, GifPicker } from "@/components/EmojiGifPicker";

// Which popover (if any) is open, and for which thread -- generalized from the old
// pin-only `pickerOpenFor` (session 75, Sam: "on the direct messages, can we add in
// emoji selector and gif selector?") to also cover the new emoji and GIF pickers, all
// three sharing the same "one popover open at a time, anchored above the compose bar"
// pattern.
type PickerType = "pin" | "emoji" | "gif";

const PIN_KIND_ICONS: Record<string, string> = {
  roster: "\u{1F465}",
  audit: "\u{1F4CB}",
  compliance: "⚖️",
  readiness_score: "\u{1F3AF}",
  performance_rank: "\u{1F3C6}",
  growth_opportunities: "\u{1F4C8}",
  profile: "\u{1F464}",
  dashboard: "\u{1F4CA}",
  asset: "\u{1F5BC}\u{FE0F}",
  campaign: "\u{1F4E3}",
  website: "\u{1F310}",
  deal: "\u{1F4B0}",
};

function formatClock(timestamp: string): string {
  try {
    return new Date(timestamp).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
  } catch {
    return "";
  }
}

export function ChatDock({
  messaging,
  pins,
  onOpenEntity,
  onOpenPin,
  onSavePin,
  onHandoff,
  simple = false,
}: {
  simple?: boolean;
  messaging: Messaging;
  pins: Pin[];
  onOpenEntity: (entityId: string) => void;
  onOpenPin: (pin: { kind: PinKind; refId?: string }) => void;
  onSavePin: (pin: { label: string; kind: PinKind; refId?: string }) => void;
  onHandoff: (text: string) => void;
}) {
  const [launcherOpen, setLauncherOpen] = useState(false);
  const [draftByThread, setDraftByThread] = useState<Record<ThreadKey, string>>({});
  const [activePicker, setActivePicker] = useState<{ thread: ThreadKey; type: PickerType } | null>(null);
  const [dragOverThread, setDragOverThread] = useState<ThreadKey | null>(null);

  function togglePicker(thread: ThreadKey, type: PickerType) {
    setActivePicker((prev) => (prev && prev.thread === thread && prev.type === type ? null : { thread, type }));
  }

  function insertEmoji(thread: Messaging["openThreads"][number], emoji: string) {
    setDraftByThread((prev) => ({ ...prev, [thread.key]: (prev[thread.key] ?? "") + emoji }));
  }

  async function sendGif(thread: Messaging["openThreads"][number], gifUrl: string) {
    setActivePicker(null);

    if (thread.kind === "channel") {
      await messaging.sendChannel(thread.target, gifUrl);
    } else {
      await messaging.sendDirect(thread.target, gifUrl);
    }
  }

  // Lifted into lib/useMessaging.ts (session 72) so CommunicationsPanel's
  // drag-a-pin-onto-a-channel/DM flow can pre-attach a pin when it opens a thread, not
  // just this window's own in-place drop target below.
  const attachedByThread = messaging.pendingAttachments;
  const setAttachedByThread = messaging.setPendingAttachment;

  function labelFor(employeeId: string): string {
    const entry = messaging.directory.find((d) => d.employee_id === employeeId);
    return entry?.name || employeeId;
  }

  async function send(thread: Messaging["openThreads"][number]) {
    const content = (draftByThread[thread.key] ?? "").trim();
    const attached = attachedByThread[thread.key];

    if (!content && !attached) return;

    if (thread.kind === "channel") {
      await messaging.sendChannel(thread.target, content || "(shared a pin)", attached);
    } else {
      await messaging.sendDirect(thread.target, content || "(shared a pin)", attached);
    }

    setDraftByThread((prev) => ({ ...prev, [thread.key]: "" }));
    setAttachedByThread(thread.key, undefined);
  }

  function handleDrop(e: DragEvent, threadKey: ThreadKey) {
    e.preventDefault();
    setDragOverThread(null);

    const raw = e.dataTransfer.getData("application/json");
    if (!raw) return;

    try {
      const pin = JSON.parse(raw) as AttachedPinRef;
      setAttachedByThread(threadKey, pin);
    } catch {
      // ignore malformed drag payloads
    }
  }

  function handoffThread(thread: Messaging["openThreads"][number]) {
    const recent = (messaging.messages[thread.key] ?? []).slice(-10);

    const transcript = recent
      .map((m) => `${labelFor(m.sender_id)}: ${m.content}`)
      .join("\n");

    onHandoff(
      `Here's the recent conversation in ${thread.kind === "channel" ? `#${thread.target}` : labelFor(thread.target)}:\n\n${transcript}\n\nCan you summarize this and suggest next steps?`
    );
  }

  const launchable = [
    ...messaging.channels.map((c) => ({ kind: "channel" as const, target: c.key, label: `#${c.name}` })),
    ...messaging.directory
      .filter((d) => d.employee_id !== messaging.myEmployeeId)
      .map((d) => ({ kind: "dm" as const, target: d.employee_id, label: d.name || d.employee_id })),
  ];

  return (
    <div data-tour-id="tour-chat-dock" className="fixed bottom-0 left-4 z-40 flex items-end gap-3">
      {/* Floating windows -- rendered left to right in open order */}
      {messaging.openThreads
        .filter((t) => messaging.expandedKeys[t.key])
        .map((thread) => (
          <div
            key={thread.key}
            className="w-[26rem] h-96 bg-zinc-950 border border-zinc-800 rounded-t-xl flex flex-col shadow-2xl"
          >
            <div className="flex items-center justify-between px-3 py-2 border-b border-zinc-800 bg-zinc-900 rounded-t-xl">
              <span className="text-sm font-medium truncate">{thread.label}</span>
              <div className="flex items-center gap-2 text-zinc-500">
                {!simple && <button
                  onClick={() => handoffThread(thread)}
                  title="Ask NXTDeal about this"
                  className="hover:text-[#3FBCC4] transition text-xs"
                >
                  ↗
                </button>}
                <button
                  onClick={() => messaging.toggleExpand(thread.key)}
                  title="Minimize"
                  className="hover:text-white transition text-xs"
                >
                  −
                </button>
                <button
                  onClick={() => messaging.closeThread(thread.key)}
                  title="Close"
                  className="hover:text-[#EE3C25] transition text-xs"
                >
                  ✕
                </button>
              </div>
            </div>

            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {(messaging.messages[thread.key] ?? []).length === 0 && (
                <div className="text-xs text-zinc-600">No messages yet -- say hello.</div>
              )}

              {(messaging.messages[thread.key] ?? []).map((message) => {
                const mine = message.sender_id === messaging.myEmployeeId;

                return (
                  <div key={message.id} className={mine ? "ml-auto max-w-[85%]" : "max-w-[85%]"}>
                    {!mine && (
                      <div className="text-[10px] text-zinc-500 mb-0.5">{labelFor(message.sender_id)}</div>
                    )}
                    <div
                      className={
                        mine
                          ? "bg-blue-600 rounded-lg px-3 py-2 text-sm"
                          : "bg-zinc-900 border border-zinc-800 rounded-lg px-3 py-2 text-sm"
                      }
                    >
                      <MessageContent text={message.content} onOpenEntity={onOpenEntity} />

                      {message.attached_pin && (
                        <div className="mt-2 bg-zinc-950/60 border border-zinc-700 rounded-lg p-2">
                          <div className="text-xs flex items-center gap-1 mb-1">
                            <span>{PIN_KIND_ICONS[message.attached_pin.kind] ?? "\u{1F4CC}"}</span>
                            <span className="truncate">{message.attached_pin.label}</span>
                          </div>
                          <div className="flex gap-2">
                            <button
                              onClick={() =>
                                onOpenPin({
                                  kind: message.attached_pin!.kind as PinKind,
                                  refId: message.attached_pin!.refId,
                                })
                              }
                              className="text-[11px] text-[#3FBCC4] hover:text-white transition"
                            >
                              View
                            </button>
                            {!simple && <button
                              onClick={() =>
                                onSavePin({
                                  label: message.attached_pin!.label,
                                  kind: message.attached_pin!.kind as PinKind,
                                  refId: message.attached_pin!.refId,
                                })
                              }
                              className="text-[11px] text-[#FBCF09] hover:text-white transition"
                            >
                              Save to my Knowledge
                            </button>}
                          </div>
                        </div>
                      )}
                    </div>
                    <div className="text-[10px] text-zinc-600 mt-0.5">{formatClock(message.timestamp)}</div>
                  </div>
                );
              })}
            </div>

            {attachedByThread[thread.key] && (
              <div className="mx-3 mb-1 flex items-center justify-between bg-zinc-900 border border-[#3FBCC4]/40 rounded-lg px-2 py-1 text-xs">
                <span className="flex items-center gap-1.5 truncate">
                  <PinIcon size={12} filled className="text-[#3FBCC4] shrink-0" />
                  {attachedByThread[thread.key]!.label}
                </span>
                <button
                  onClick={() => setAttachedByThread(thread.key, undefined)}
                  className="text-zinc-500 hover:text-white transition"
                >
                  ✕
                </button>
              </div>
            )}

            <div
              onDragOver={(e) => {
                e.preventDefault();
                setDragOverThread(thread.key);
              }}
              onDragLeave={() => setDragOverThread(null)}
              onDrop={(e) => handleDrop(e, thread.key)}
              className={
                "relative flex items-center gap-1 p-2 border-t border-zinc-800" +
                (dragOverThread === thread.key ? " bg-[#3FBCC4]/10" : "")
              }
            >
              {activePicker?.thread === thread.key && activePicker.type === "pin" && (
                <div className="absolute bottom-12 left-2 right-2 bg-zinc-900 border border-zinc-800 rounded-lg max-h-40 overflow-y-auto z-10">
                  {pins.length === 0 ? (
                    <div className="p-2 text-xs text-zinc-600">Nothing pinned yet.</div>
                  ) : (
                    pins.map((pin) => (
                      <button
                        key={pin.id}
                        onClick={() => {
                          setAttachedByThread(thread.key, { kind: pin.kind, label: pin.label, refId: pin.refId });
                          setActivePicker(null);
                        }}
                        className="block w-full text-left px-3 py-2 text-xs hover:bg-zinc-800 transition truncate"
                      >
                        {PIN_KIND_ICONS[pin.kind] ?? "\u{1F4CC}"} {pin.label}
                      </button>
                    ))
                  )}
                </div>
              )}

              {activePicker?.thread === thread.key && activePicker.type === "emoji" && (
                <div className="absolute bottom-12 left-2 bg-zinc-900 border border-zinc-800 rounded-lg z-10 shadow-xl">
                  <EmojiPicker onSelect={(emoji) => insertEmoji(thread, emoji)} />
                </div>
              )}

              {activePicker?.thread === thread.key && activePicker.type === "gif" && (
                <div className="absolute bottom-12 left-2 bg-zinc-900 border border-zinc-800 rounded-lg z-10 shadow-xl">
                  <GifPicker onSelect={(gifUrl) => sendGif(thread, gifUrl)} />
                </div>
              )}

              {!simple && <button
                onClick={() => togglePicker(thread.key, "pin")}
                title="Attach a pin"
                className="shrink-0 text-zinc-500 hover:text-white transition px-1"
              >
                📎
              </button>}

              <button
                onClick={() => togglePicker(thread.key, "emoji")}
                title="Emoji"
                className="shrink-0 text-zinc-500 hover:text-white transition px-1"
              >
                😊
              </button>

              <button
                onClick={() => togglePicker(thread.key, "gif")}
                title="GIF"
                className="shrink-0 text-zinc-500 hover:text-white transition px-1 text-[10px] font-bold border border-zinc-700 rounded"
              >
                GIF
              </button>

              <input
                value={draftByThread[thread.key] ?? ""}
                onChange={(e) => setDraftByThread((prev) => ({ ...prev, [thread.key]: e.target.value }))}
                onKeyDown={(e) => {
                  if (e.key === "Enter") send(thread);
                }}
                placeholder="Message..."
                className="flex-1 min-w-0 h-8 px-2 text-sm rounded bg-zinc-900 border border-zinc-800"
              />

              <button
                onClick={() => send(thread)}
                className="shrink-0 text-xs px-2.5 py-1 rounded brand-cta transition"
              >
                Send
              </button>
            </div>
          </div>
        ))}

      {/* Collapsed head chips + launcher, gchat-style row along the very bottom */}
      <div className="flex items-center gap-2 pb-0">
        <div className="flex items-center gap-1 bg-zinc-950 border border-zinc-800 border-b-0 rounded-t-lg px-2 py-2">
          {messaging.openThreads
            .filter((t) => !messaging.expandedKeys[t.key])
            .map((thread) => (
              <button
                key={thread.key}
                onClick={() => messaging.toggleExpand(thread.key)}
                className="relative text-xs bg-zinc-900 border border-zinc-800 rounded-full px-3 py-1 hover:border-[#3FBCC4] transition"
              >
                {thread.label}
                {messaging.unread[thread.key] ? (
                  <span className="ml-1 text-[#EE3C25]">({messaging.unread[thread.key]})</span>
                ) : null}
              </button>
            ))}

          <div className="relative">
            <button
              onClick={() => setLauncherOpen(!launcherOpen)}
              className="text-xs bg-zinc-900 border border-zinc-800 rounded-full w-6 h-6 flex items-center justify-center hover:border-[#3FBCC4] transition"
              title="Start a conversation"
            >
              +
            </button>

            {launcherOpen && (
              <div className="absolute bottom-8 left-0 w-56 bg-zinc-900 border border-zinc-800 rounded-lg max-h-64 overflow-y-auto z-10">
                {launchable.length === 0 && (
                  <div className="p-2 text-xs text-zinc-600">Nothing to open yet.</div>
                )}
                {launchable.map((item) => (
                  <button
                    key={`${item.kind}-${item.target}`}
                    onClick={() => {
                      messaging.openThread(item.kind, item.target, item.label);
                      setLauncherOpen(false);
                    }}
                    className="block w-full text-left px-3 py-2 text-xs hover:bg-zinc-800 transition truncate"
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
