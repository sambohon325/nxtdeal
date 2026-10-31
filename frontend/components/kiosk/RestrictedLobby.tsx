"use client";

import { useEffect, useRef, useState } from "react";
import { createRestrictedKiosk, type KioskGrant } from "@/lib/restrictedKiosk";
import { startKioskPrivacyTimer } from "@/lib/kioskPrivacy";

/** Unmounted prototype: grant must come from a separately approved kiosk enrollment. */
export function RestrictedLobby({ grant }: { grant: KioskGrant }) {
  const { token, deviceId, expiresAt, apiOrigin } = grant;
  const client = useRef<ReturnType<typeof createRestrictedKiosk> | null>(null);
  const [phase, setPhase] = useState("closed");
  const [warning, setWarning] = useState(false);
  const [fields, setFields] = useState({ name: "", phone: "", reason: "" });
  const generation = useRef(0);
  useEffect(() => {
    const revision = ++generation.current;
    client.current = null;
    setWarning(false);
    setFields({ name: "", phone: "", reason: "" });
    if (document.visibilityState === "hidden" || Date.now() >= expiresAt * 1000) { setPhase("closed"); return; }
    let active: ReturnType<typeof createRestrictedKiosk>;
    try { active = createRestrictedKiosk({ token, deviceId, expiresAt, apiOrigin }); }
    catch { setPhase("closed"); return; }
    client.current = active;
    setPhase("ready");
    const clear = () => {
      if (revision !== generation.current) return;
      generation.current++;
      active.close();
      setFields({ name: "", phone: "", reason: "" });
      setPhase("closed");
    };
    const privacy = startKioskPrivacyTimer(setWarning, clear);
    const expiry = setTimeout(clear, Math.min(expiresAt * 1000 - Date.now(), 2_147_483_647));
    const visibility = () => { if (document.visibilityState === "hidden") clear(); };
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", clear);
    return () => {
      generation.current++;
      active.close();
      privacy.stop();
      clearTimeout(expiry);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", clear);
    };
  }, [token, deviceId, expiresAt, apiOrigin]);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (phase !== "ready" || !client.current || !fields.name.trim()) return;
    const revision = generation.current;
    setPhase("saving");
    const input = fields;
    setFields({ name: "", phone: "", reason: "" });
    const result = await client.current.submit(input);
    if (revision !== generation.current || result === "busy") return;
    setPhase(result);
  }
  return <main className="mx-auto max-w-lg space-y-6 p-6">
    <h1 className="text-2xl font-semibold">Welcome. Please check in.</h1>
    {warning && phase === "ready" && <p role="status">This screen will clear soon for your privacy.</p>}
    {phase === "ready" ? <form onSubmit={submit} className="space-y-4">
      {(["name", "phone", "reason"] as const).map((field) => <label key={field} className="block">
        {field === "name" ? "Name" : field === "phone" ? "Phone (optional)" : "Reason for visit (optional)"}
        <input className="block w-full rounded border p-3" value={fields[field]} required={field === "name"}
          maxLength={field === "name" ? 120 : field === "phone" ? 40 : 500}
          autoComplete="off" inputMode={field === "phone" ? "tel" : "text"}
          onChange={(event) => setFields({ ...fields, [field]: event.target.value })} />
      </label>)}
      <button type="submit" className="rounded border px-5 py-3">Check in</button>
    </form> : <div role="status">
      {phase === "saving" ? "Saving your check-in…" : phase === "confirmed" ? "Thank you. Your check-in is recorded." :
        phase === "unconfirmed" ? "We could not confirm your check-in. Please ask the front desk before trying again." :
        "Please ask the front desk to reopen this check-in screen."}
    </div>}
    {phase === "confirmed" && <button type="button" className="rounded border px-5 py-3" onClick={() => setPhase("ready")}>Next visitor</button>}
  </main>;
}
