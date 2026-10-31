"use client";

// Graph-native Communications (session 28 -- Sam: "communications will work off the
// same graph knowledge... it needs to be able to reference data from the graph...
// as well as be able to break out into the central chat box... share knowledge pins
// with other users"). One shared hook, used by the Communications sidebar block and
// ChatDock on every authenticated page, matching every other cross-page piece built
// this session (useArtifactPanel, pins.ts, KnowledgeSidebar).
//
// Real-time via a single websocket per session (Sam picked real-time over polling when
// asked) -- backend/core/ws_manager.py pushes a payload the instant someone else posts
// a channel or direct message; this hook is purely the client side of that, plus the
// REST calls for history/sending (api/app.py's /messaging/* routes).

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders, getSession, isAuthError, clearSession } from "@/lib/auth";

export type Channel = { key: string; name: string; roles: string[] };

export type DirectoryEntry = { employee_id: string; role: string; name: string | null };

export type RecentConversation = { employee_id: string; timestamp: string; preview: string };

export type AttachedPinRef = { kind: string; label: string; refId?: string };

export type Message = {
  id: string;
  kind: "channel" | "direct";
  channel_key?: string;
  sender_id: string;
  recipient_id?: string;
  content: string;
  attached_pin: AttachedPinRef | null;
  timestamp: string;
};

// "channel:sales" | "dm:EMP-00042" -- one key format both channels and DM threads share,
// so ChatDock/Communications can treat every open thread uniformly.
export type ThreadKey = string;

export function channelThreadKey(channelKey: string): ThreadKey {
  return `channel:${channelKey}`;
}

export function directThreadKey(employeeId: string): ThreadKey {
  return `dm:${employeeId}`;
}

export type OpenThread = { key: ThreadKey; label: string; kind: "channel" | "dm"; target: string };

function wsUrl(token: string): string {
  const httpBase = API_BASE.replace(/\/$/, "");
  const wsBase = httpBase.replace(/^http/, "ws");
  return `${wsBase}/ws/messaging?token=${encodeURIComponent(token)}`;
}

export function useMessaging() {
  const session = getSession();
  const myEmployeeId = session?.employeeId ?? "";

  const [connected, setConnected] = useState(false);
  const [channels, setChannels] = useState<Channel[]>([]);
  const [directory, setDirectory] = useState<DirectoryEntry[]>([]);
  const [conversations, setConversations] = useState<RecentConversation[]>([]);
  const [messages, setMessages] = useState<Record<ThreadKey, Message[]>>({});
  const [unread, setUnread] = useState<Record<ThreadKey, number>>({});
  const [channelStatus, setChannelStatus] = useState<"loading" | "ready" | "error">("loading");
  const [directoryStatus, setDirectoryStatus] = useState<"loading" | "ready" | "error">("loading");
  const [threadStatus, setThreadStatus] = useState<Record<ThreadKey, "loading" | "ready" | "error">>({});

  // ChatDock/Communications dock state -- lives here (not in ChatDock itself) so both
  // the collapsible Communications sidebar block and the floating ChatDock windows
  // share one notion of "what's open" instead of drifting out of sync, and so a page
  // only ever opens one websocket connection regardless of how many components
  // consume this hook's return value (call useMessaging() once per page, pass the
  // result down).
  const [openThreads, setOpenThreads] = useState<OpenThread[]>([]);
  const [expandedKeys, setExpandedKeys] = useState<Record<ThreadKey, boolean>>({});

  // Lifted up from ChatDock (session 72) so components outside ChatDock itself --
  // components/CommunicationsPanel.tsx's drag-a-pin-onto-a-channel/DM flow -- can open
  // a thread with a pin already attached to the compose box, not just ChatDock's own
  // in-window drop target.
  const [pendingAttachments, setPendingAttachments] = useState<Record<ThreadKey, AttachedPinRef | undefined>>({});

  const setPendingAttachment = useCallback((threadKey: ThreadKey, pin: AttachedPinRef | undefined) => {
    setPendingAttachments((prev) => ({ ...prev, [threadKey]: pin }));
  }, []);

  const socketRef = useRef<WebSocket | null>(null);
  // Tracks which threads are "currently open" (a ChatDock window or the Communications
  // panel is actively showing them) so an incoming push can skip incrementing unread —
  // a ref, not state, since the websocket's onmessage closure needs the latest value
  // without re-subscribing every render.
  const openThreadsRef = useRef<Set<ThreadKey>>(new Set());

  async function guardedFetch(url: string, init?: RequestInit): Promise<unknown | null> {
    const requestToken = getSession()?.token;
    const response = await fetch(url, {
      ...init,
      headers: { ...(init?.headers ?? {}), ...authHeaders() },
    });

    const data = await response.json();

    if (response.status === 401 || isAuthError(data)) {
      if (requestToken && getSession()?.token === requestToken) clearSession();
      throw new Error("Sign in again to use messaging.");
    }

    if (!requestToken || getSession()?.token !== requestToken) throw new Error("Messaging session changed.");

    if (!response.ok || data.error) {
      throw new Error(data.error ?? `Backend returned ${response.status}`);
    }

    return data;
  }

  const refreshChannels = useCallback(async () => {
    setChannelStatus("loading");
    try {
      const data = await guardedFetch(`${API_BASE}/messaging/channels`);
      if (!Array.isArray(data)) throw new Error("Invalid channels response");
      setChannels(data as Channel[]);
      setChannelStatus("ready");
    } catch {
      setChannelStatus("error");
    }
  }, []);

  const refreshDirectory = useCallback(async () => {
    setDirectoryStatus("loading");
    try {
      const data = await guardedFetch(`${API_BASE}/messaging/directory`);
      if (!Array.isArray(data)) throw new Error("Invalid directory response");
      setDirectory(data as DirectoryEntry[]);
      setDirectoryStatus("ready");
    } catch {
      setDirectoryStatus("error");
    }
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      const data = await guardedFetch(`${API_BASE}/messaging/conversations`);
      if (data) setConversations(data as RecentConversation[]);
    } catch {
      // ignore
    }
  }, []);

  const loadChannel = useCallback(async (channelKey: string) => {
    const key = channelThreadKey(channelKey);
    setThreadStatus(prev => ({ ...prev, [key]: "loading" }));
    try {
      const data = await guardedFetch(`${API_BASE}/messaging/channels/${channelKey}/messages`);
      if (!Array.isArray(data)) throw new Error("Invalid history response");
      setMessages((prev) => ({ ...prev, [key]: data as Message[] }));
      setThreadStatus(prev => ({ ...prev, [key]: "ready" }));
    } catch {
      setThreadStatus(prev => ({ ...prev, [key]: "error" }));
    }
  }, []);

  const loadDirect = useCallback(async (otherEmployeeId: string) => {
    const key = directThreadKey(otherEmployeeId);
    setThreadStatus(prev => ({ ...prev, [key]: "loading" }));
    try {
      const data = await guardedFetch(`${API_BASE}/messaging/direct/${otherEmployeeId}`);
      if (!Array.isArray(data)) throw new Error("Invalid history response");
      setMessages((prev) => ({ ...prev, [key]: data as Message[] }));
      setThreadStatus(prev => ({ ...prev, [key]: "ready" }));
    } catch {
      setThreadStatus(prev => ({ ...prev, [key]: "error" }));
    }
  }, []);

  function appendMessage(key: ThreadKey, message: Message) {
    setMessages(prev => ({ ...prev, [key]: (prev[key] ?? []).some(item => item.id === message.id)
      ? prev[key] : [...(prev[key] ?? []), message] }));
  }

  function acceptSentMessage(key: ThreadKey, data: unknown) {
    if (!data || typeof data !== "object" || !("id" in data) || typeof data.id !== "string" || !data.id) {
      throw new Error("Message save could not be confirmed.");
    }
    // The REST acknowledgement proves persistence even when the live socket is down.
    // Deduplication also handles the socket arriving before or after this response.
    appendMessage(key, data as Message);
  }

  const sendChannel = useCallback(
    async (channelKey: string, content: string, attachedPin?: AttachedPinRef) => {
      const data = await guardedFetch(`${API_BASE}/messaging/channels/${channelKey}/messages`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, attached_pin: attachedPin ?? null }),
      });
      acceptSentMessage(channelThreadKey(channelKey), data);
    },
    []
  );

  const sendDirect = useCallback(
    async (otherEmployeeId: string, content: string, attachedPin?: AttachedPinRef) => {
      const data = await guardedFetch(`${API_BASE}/messaging/direct/${otherEmployeeId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content, attached_pin: attachedPin ?? null }),
      });
      acceptSentMessage(directThreadKey(otherEmployeeId), data);
    },
    []
  );

  function markOpen(threadKey: ThreadKey) {
    openThreadsRef.current.add(threadKey);
    setUnread((prev) => {
      if (!prev[threadKey]) return prev;
      const next = { ...prev };
      delete next[threadKey];
      return next;
    });
  }

  function markClosed(threadKey: ThreadKey) {
    openThreadsRef.current.delete(threadKey);
  }

  function openThread(kind: "channel" | "dm", target: string, label: string, attachPin?: AttachedPinRef) {
    const key = kind === "channel" ? channelThreadKey(target) : directThreadKey(target);

    setOpenThreads((prev) => {
      if (prev.some((t) => t.key === key)) return prev;
      return [...prev, { key, label, kind, target }];
    });

    setExpandedKeys((prev) => ({ ...prev, [key]: true }));
    markOpen(key);

    if (attachPin) {
      setPendingAttachment(key, attachPin);
    }

    if (!messages[key]) {
      if (kind === "channel") loadChannel(target);
      else loadDirect(target);
    }
  }

  function closeThread(threadKey: ThreadKey) {
    setOpenThreads((prev) => prev.filter((t) => t.key !== threadKey));
    setExpandedKeys((prev) => {
      const next = { ...prev };
      delete next[threadKey];
      return next;
    });
    markClosed(threadKey);
  }

  function toggleExpand(threadKey: ThreadKey) {
    setExpandedKeys((prev) => {
      const next = { ...prev, [threadKey]: !prev[threadKey] };
      if (next[threadKey]) markOpen(threadKey);
      return next;
    });
  }

  useEffect(() => {
    if (!session) return;

    refreshChannels();
    refreshDirectory();
    refreshConversations();

    const socket = new WebSocket(wsUrl(session.token));
    socketRef.current = socket;

    socket.onopen = () => setConnected(true);
    socket.onclose = () => setConnected(false);

    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(event.data) as
          | { event: "channel_message"; channel_key: string; message: Message }
          | { event: "direct_message"; message: Message };

        if (payload.event === "channel_message") {
          const threadKey = channelThreadKey(payload.channel_key);

          appendMessage(threadKey, payload.message);

          if (!openThreadsRef.current.has(threadKey)) {
            setUnread((prev) => ({ ...prev, [threadKey]: (prev[threadKey] ?? 0) + 1 }));
          }
        } else if (payload.event === "direct_message") {
          const partner =
            payload.message.sender_id === myEmployeeId
              ? payload.message.recipient_id!
              : payload.message.sender_id;
          const threadKey = directThreadKey(partner);

          appendMessage(threadKey, payload.message);

          if (!openThreadsRef.current.has(threadKey)) {
            setUnread((prev) => ({ ...prev, [threadKey]: (prev[threadKey] ?? 0) + 1 }));
          }

          refreshConversations();
        }
      } catch {
        // Malformed/unknown payload -- ignore rather than crash the socket handler.
      }
    };

    return () => {
      socket.close();
      socketRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return {
    connected,
    channelStatus,
    directoryStatus,
    threadStatus,
    channels,
    directory,
    conversations,
    messages,
    unread,
    myEmployeeId,
    loadChannel,
    loadDirect,
    sendChannel,
    sendDirect,
    markOpen,
    markClosed,
    refreshDirectory,
    refreshChannels,
    refreshConversations,
    openThreads,
    expandedKeys,
    openThread,
    closeThread,
    toggleExpand,
    pendingAttachments,
    setPendingAttachment,
  };
}

export type Messaging = ReturnType<typeof useMessaging>;
