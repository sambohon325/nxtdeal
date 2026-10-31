"use client";

// Workspace-panel pop-out (session 29 -- Sam: "can we make it so that entire panel can
// be broken out in its own window / browser/tab? the idea being if your working in the
// system and you have two screens you can pull that out and move it to the other
// screen - also, if your a sales rep and you want to show inventory to a customer, same
// with managers wanting to show data internally. It also needs to be able to be placed
// back, or closed and reloaded into the original screen").
//
// Deliberately does NOT give the popped-out window its own login/API calls -- it has no
// token, makes no requests, and exists purely as a second renderer driven by
// BroadcastChannel messages from the window that opened it (same-origin, same tab
// group, no auth surface added). This keeps a customer-facing "show them the screen"
// use case from ever needing a second sign-in, and keeps the two windows trivially in
// sync: whatever artifact the main window is showing gets pushed to the popped window
// the instant it changes, and clicking something inside the popped window (a related
// entity, a reset-password confirm) sends a request back to the main window, which
// runs the exact same loader function it already had and pushes the result back out.
//
// One BroadcastChannel per pop-out "session" (a fresh random channel name each time
// popOut() is called) rather than one fixed channel for the whole app -- so multiple
// tabs/pages each popping out their own panel don't cross-talk.

import { useEffect, useRef, useState } from "react";
import type { Artifact } from "@/lib/useArtifactPanel";

type OutboundMessage =
  | { type: "artifact"; artifact: Artifact | null }
  | { type: "closed" };

type InboundMessage =
  | { type: "ready" }
  | { type: "selectProfile"; entityId: string }
  | { type: "selectDashboard"; key: string }
  | { type: "confirmReset"; employeeId: string }
  | { type: "cancelReset" }
  | { type: "closed" };

export function usePanelPopout({
  artifact,
  onSelectProfile,
  onSelectDashboard,
  onConfirmReset,
  onCancelReset,
}: {
  artifact: Artifact | null;
  onSelectProfile: (entityId: string) => void;
  onSelectDashboard: (key: string) => void;
  onConfirmReset: (employeeId: string) => void;
  onCancelReset: () => void;
}) {
  const [poppedOut, setPoppedOut] = useState(false);

  const channelRef = useRef<BroadcastChannel | null>(null);
  const popupRef = useRef<Window | null>(null);
  const closeWatcherRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function teardown() {
    if (closeWatcherRef.current) {
      clearInterval(closeWatcherRef.current);
      closeWatcherRef.current = null;
    }

    channelRef.current?.close();
    channelRef.current = null;
    popupRef.current = null;
    setPoppedOut(false);
  }

  // Push the latest artifact out any time it changes while a window is popped --
  // otherwise "pull it to a second screen" would just be a frozen snapshot instead of
  // the same live panel.
  useEffect(() => {
    if (poppedOut && channelRef.current) {
      channelRef.current.postMessage({ type: "artifact", artifact } as OutboundMessage);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [artifact, poppedOut]);

  useEffect(() => {
    return () => {
      if (closeWatcherRef.current) clearInterval(closeWatcherRef.current);
      channelRef.current?.close();
    };
  }, []);

  function popOut() {
    if (poppedOut) {
      popupRef.current?.focus();
      return;
    }

    const channelName = `dealeros-panel-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const channel = new BroadcastChannel(channelName);
    channelRef.current = channel;

    channel.onmessage = (event: MessageEvent<InboundMessage>) => {
      const message = event.data;

      if (message.type === "ready") {
        channel.postMessage({ type: "artifact", artifact } as OutboundMessage);
      } else if (message.type === "selectProfile") {
        onSelectProfile(message.entityId);
      } else if (message.type === "selectDashboard") {
        onSelectDashboard(message.key);
      } else if (message.type === "confirmReset") {
        onConfirmReset(message.employeeId);
      } else if (message.type === "cancelReset") {
        onCancelReset();
      } else if (message.type === "closed") {
        teardown();
      }
    };

    const popup = window.open(
      `/panel?channel=${encodeURIComponent(channelName)}`,
      "dealeros_panel",
      "width=820,height=880"
    );

    if (!popup) {
      // Popup blocked -- stay inline rather than claiming success.
      channel.close();
      channelRef.current = null;
      return;
    }

    popupRef.current = popup;
    setPoppedOut(true);

    // Belt-and-suspenders close detection: the popped page posts "closed" on
    // beforeunload, but that can race a hard-crash/force-close, so also poll
    // window.closed directly.
    closeWatcherRef.current = setInterval(() => {
      if (popup.closed) {
        teardown();
      }
    }, 1000);
  }

  function bringBack() {
    popupRef.current?.close();
    teardown();
  }

  return { poppedOut, popOut, bringBack };
}
