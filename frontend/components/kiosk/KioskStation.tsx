"use client";

import { useEffect, useRef, useState } from "react";
import { createKioskEnrollment } from "@/lib/kioskEnrollment";
import { createKioskSignIn } from "@/lib/kioskSignIn";
import type { KioskGrant } from "@/lib/restrictedKiosk";
import { RestrictedLobby } from "./RestrictedLobby";

type Answer = { employeeId: string; password: string } | string | null;
type Prompt = "password" | "mfa" | null;

/** Unmounted station. Origin/device are deployment inputs, never URL parameters.
 * No staff shell or staff session is restored when kiosk operation ends. */
export function KioskStation({ apiOrigin, deviceId }: { apiOrigin: string; deviceId: string }) {
  const [grant, setGrant] = useState<KioskGrant | null>(null);
  const [phase, setPhase] = useState("closed");
  const [prompt, setPrompt] = useState<Prompt>(null);
  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const manager = useRef<ReturnType<typeof createKioskEnrollment> | null>(null);
  const answer = useRef<((value: Answer) => void) | null>(null);
  const busy = useRef(false);

  function clearInputs() { setEmployeeId(""); setPassword(""); setCode(""); }

  useEffect(() => {
    let live = true;
    setGrant(null); setPrompt(null); clearInputs(); busy.current = false;
    async function ask(kind: Exclude<Prompt, null>, signal: AbortSignal): Promise<Answer> {
      if (!live || signal.aborted || document.visibilityState === "hidden") return null;
      clearInputs(); setPrompt(kind);
      return new Promise(resolve => {
        const finish = (value: Answer) => {
          signal.removeEventListener("abort", cancel);
          if (answer.current === finish) answer.current = null;
          if (live) { clearInputs(); setPrompt(null); }
          resolve(value);
        };
        const cancel = () => finish(null);
        answer.current = finish;
        signal.addEventListener("abort", cancel, { once: true });
      });
    }
    let client: ReturnType<typeof createKioskEnrollment>;
    try {
      const auth = createKioskSignIn(apiOrigin, {
        credentials: async signal => { const value = await ask("password", signal); return typeof value === "object" ? value : null; },
        mfa: async signal => { const value = await ask("mfa", signal); return typeof value === "string" ? value : null; },
      });
      client = createKioskEnrollment(apiOrigin, auth);
    } catch { setPhase("closed"); return; }
    manager.current = client;
    setPhase("ready");
    const close = () => {
      manager.current = null; client.close(); answer.current?.(null);
      setGrant(null); clearInputs(); setPrompt(null); setPhase("closed");
    };
    const visibility = () => { if (document.visibilityState === "hidden") close(); };
    document.addEventListener("visibilitychange", visibility);
    window.addEventListener("pagehide", close);
    if (document.visibilityState === "hidden") close();
    return () => {
      live = false; manager.current = null; client.close(); answer.current?.(null);
      document.removeEventListener("visibilitychange", visibility);
      window.removeEventListener("pagehide", close);
    };
  }, [apiOrigin, deviceId]);

  async function manage(revoke: boolean) {
    const active = manager.current;
    if (!active || busy.current) return;
    busy.current = true;
    // Remove the visitor form before requesting any staff credential.
    setGrant(null); setPhase("working"); clearInputs();
    const result = await (revoke ? active.revoke(deviceId) : active.enroll(deviceId));
    if (manager.current !== active) return;
    busy.current = false;
    if (result.status === "enrolled") setGrant(result.grant);
    setPhase(result.status);
  }

  function submit(event: React.FormEvent) {
    event.preventDefault();
    const finish = answer.current;
    if (!finish) return;
    const value = prompt === "password" ? { employeeId, password } : code;
    clearInputs(); finish(value);
  }
  return <section className="mx-auto max-w-lg space-y-4 p-6">
    {grant && <RestrictedLobby grant={grant} />}
    {!grant && <h1 className="text-2xl font-semibold">Reception station</h1>}
    {prompt && <form onSubmit={submit} className="space-y-3" autoComplete="off">
      <p>Administrator sign-in required.</p>
      {prompt === "password" ? <>
        <label className="block">Employee ID or email<input className="block w-full border p-2" autoComplete="off" value={employeeId} onChange={e => setEmployeeId(e.target.value)} required /></label>
        <label className="block">Password<input className="block w-full border p-2" type="password" autoComplete="off" value={password} onChange={e => setPassword(e.target.value)} required /></label>
      </> : <label className="block">Authenticator or recovery code<input className="block w-full border p-2" autoComplete="off" value={code} onChange={e => setCode(e.target.value)} required /></label>}
      <button type="submit">Continue</button>
      <button type="button" onClick={() => answer.current?.(null)}>Cancel sign-in</button>
    </form>}
    {phase === "working" && !prompt && <p role="status">Please wait…</p>}
    {phase === "denied" && <p role="alert">Sign-in could not be completed. An administrator can try again.</p>}
    {phase === "unconfirmed" && <p role="alert">We could not confirm this change. Keep this station closed and ask an administrator to review it.</p>}
    {phase === "revoked" && <p role="status">Station access was revoked. This screen remains closed.</p>}
    {phase === "closed" && <p role="status">Station closed. Ask an administrator to reopen it.</p>}
    {!["working", "closed", "unconfirmed"].includes(phase) && <div className="flex gap-4">
      {!grant && <button type="button" onClick={() => manage(false)}>Start check-in</button>}
      <button type="button" onClick={() => manage(true)}>Stop check-in and sign in</button>
    </div>}
  </section>;
}
