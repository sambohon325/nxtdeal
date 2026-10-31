"use client";

// Standalone pop-out target for the workspace panel (session 29). Deliberately has no
// auth of its own and makes no API calls -- it's a pure renderer, fed entirely by
// BroadcastChannel messages from whichever main-window tab opened it (see
// lib/usePanelPopout.ts). That's what makes "pull this out onto a second screen" or
// "show a customer this screen" safe and simple: no second login, and the two windows
// can never show different data since the popped window only ever displays what the
// main window just pushed to it.

import { Suspense, useEffect, useRef, useState } from "react";
import { useSearchParams } from "next/navigation";
import { ArtifactView } from "@/components/ArtifactView";
import type { Artifact } from "@/lib/useArtifactPanel";

function PanelContent() {
  const params = useSearchParams();
  const channelName = params.get("channel") ?? "";

  const [artifact, setArtifact] = useState<Artifact | null>(null);
  const [connected, setConnected] = useState(false);
  const channelRef = useRef<BroadcastChannel | null>(null);

  useEffect(() => {
    if (!channelName) return;

    const channel = new BroadcastChannel(channelName);
    channelRef.current = channel;
    setConnected(true);

    channel.onmessage = (event: MessageEvent<{ type: string; artifact?: Artifact | null }>) => {
      if (event.data.type === "artifact") {
        setArtifact(event.data.artifact ?? null);
      }
    };

    channel.postMessage({ type: "ready" });

    function handleUnload() {
      channel.postMessage({ type: "closed" });
    }

    window.addEventListener("beforeunload", handleUnload);

    return () => {
      window.removeEventListener("beforeunload", handleUnload);
      channel.close();
    };
  }, [channelName]);

  function send(message: object) {
    channelRef.current?.postMessage(message);
  }

  function closeAndReturn() {
    send({ type: "closed" });
    window.close();
  }

  return (
    <div className="min-h-screen bg-[#111111] text-white p-6">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <div className="w-2 h-2 rounded-full bg-[#FBCF09]" />
          <span className="text-sm text-zinc-400">NXTDeal — Workspace (popped out)</span>
        </div>
        <button
          onClick={closeAndReturn}
          className="text-xs text-zinc-500 hover:text-white transition"
        >
          Close &amp; return to main window
        </button>
      </div>

      {!channelName ? (
        <div className="text-sm text-zinc-500">
          This window wasn't opened correctly — go back to NXTDeal and use the pop-out
          button on the workspace panel.
        </div>
      ) : !connected || !artifact ? (
        <div className="text-sm text-zinc-500">Waiting for content from the main window…</div>
      ) : (
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-6 max-w-4xl">
          <ArtifactView
            artifact={artifact}
            onSelectProfile={(entityId) => send({ type: "selectProfile", entityId })}
            onConfirmReset={(employeeId) => send({ type: "confirmReset", employeeId })}
            onCancelReset={() => send({ type: "cancelReset" })}
            resetLoading={false}
          />
        </div>
      )}
    </div>
  );
}

export default function PanelPage() {
  return (
    <Suspense fallback={null}>
      <PanelContent />
    </Suspense>
  );
}
