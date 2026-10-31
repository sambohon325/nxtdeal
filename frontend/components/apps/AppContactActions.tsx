"use client";

// AppContactActions — Call / Text / My-phone actions for a customer inside a suite app (2026-07-24,
// Sam: the sales apps "need to call/text from inside the app, or send it to their phone to call/
// text and transcribe the call / add it to the crm").
//
//  • Call / Text  → open the in-app call/text workspace (the bottom-docked chat window mounted in
//    AppShell) via the shared commsStore — same experience as the back office.
//  • My phone     → hand off to the rep's actual phone (tel:/sms:) AND log a real Communication to
//    the CRM in the background (with the simulated transcript + AI analysis), so a call taken on
//    the phone still lands in NXTDeal with a record and coaching. Simulated until a telephony
//    provider is connected.

import { startCommsSession } from "@/lib/commsStore";
import { placeCall, endCall } from "@/lib/customerComms";

export function AppContactActions({
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
  if (!phone && !customerId) return null;

  async function toPhone(mode: "call" | "text") {
    if (!phone) return;
    if (mode === "text") {
      window.location.href = `sms:${phone}`;
      return;
    }
    // Open the device dialer, and log a tracked (simulated-transcribed) call to the CRM so the
    // conversation is on record even though the talking happens on the rep's phone.
    window.location.href = `tel:${phone}`;
    try {
      const r = await placeCall({ customer_id: customerId, number: phone });
      if (!("error" in r)) {
        await endCall(r.call.id, "Call handled on the rep's phone.");
      }
    } catch {
      /* best-effort logging */
    }
  }

  const pad = size === "xs" ? "px-2 py-1 text-[10px]" : "px-2.5 py-1.5 text-[11px]";
  const base = `rounded-lg font-semibold transition ${pad}`;

  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <button
        onClick={(e) => {
          e.stopPropagation();
          startCommsSession({ mode: "call", customerId, number: phone || undefined, name });
        }}
        className={`${base} bg-[var(--app-accent)] text-[var(--app-accent-text)]`}
        title="Call in-app"
      >
        📞 Call
      </button>
      <button
        onClick={(e) => {
          e.stopPropagation();
          startCommsSession({ mode: "text", customerId, number: phone || undefined, name });
        }}
        className={`${base} border border-white/15 text-zinc-200 hover:bg-white/5`}
        title="Text in-app"
      >
        💬 Text
      </button>
      {phone && (
        <button
          onClick={(e) => {
            e.stopPropagation();
            toPhone("call");
          }}
          className={`${base} border border-white/15 text-zinc-300 hover:bg-white/5`}
          title="Dial on my phone — still logs to the CRM"
        >
          📱 My phone
        </button>
      )}
    </div>
  );
}
