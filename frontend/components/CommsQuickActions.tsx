"use client";
import { WorkButton } from "./WorkspaceUi";

// CommsQuickActions — a drop-in Call / Text button pair for any dashboard (2026-07-24). Clicking
// opens the Communications call/text workspace (mounted globally in CommunicationsPanel) with the
// customer preloaded, via the lib/commsStore global store. This is the "click Call from various
// dashes and it loads in Communications where you carry out the task" wiring (Sam's spec) — drop
// <CommsQuickActions customerId=... phone=... name=... /> anywhere a customer is shown.

import { startCommsSession } from "@/lib/commsStore";

export function CommsQuickActions({
  customerId,
  phone,
  name,
  size = "sm",
}: {
  customerId?: string;
  phone?: string | null;
  name?: string;
  size?: "sm" | "xs";
}) {
  // Nothing to act on without at least a number or a customer record.
  if (!phone && !customerId) return null;

  const pad = size === "xs" ? "px-1.5 py-0.5 text-[10px]" : "px-2 py-1 text-[11px]";
  const base = `font-semibold rounded-md transition ${pad}`;

  return (
    <span className="inline-flex gap-1 align-middle">
      <WorkButton type="submit"
        onClick={(e) => {
          e.stopPropagation();
          startCommsSession({ mode: "call", customerId, number: phone || undefined, name });
        }}
        className={`${base} bg-brand-teal text-black hover:opacity-90`}
        title={phone ? `Call ${phone}` : "Call"}
      >
        📞 Call
      </WorkButton>
      <WorkButton type="submit"
        onClick={(e) => {
          e.stopPropagation();
          startCommsSession({ mode: "text", customerId, number: phone || undefined, name });
        }}
        className={`${base} border border-zinc-600 text-zinc-300 hover:bg-zinc-800`}
        title={phone ? `Text ${phone}` : "Text"}
      >
        💬 Text
      </WorkButton>
    </span>
  );
}
