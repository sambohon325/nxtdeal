"use client";
import { useEffect, useState, type FormEvent } from "react";
import { personalRequest, setPersonalToken } from "@/lib/mysalesPersonal";
import styles from "./MySalesPersonal.module.css";

export function MySalesEmail({ verification = false, verified = false, onVerified }: {
  verification?: boolean; verified?: boolean; onVerified?: () => void;
}) {
  const [available, setAvailable] = useState(false);
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    personalRequest<{available: boolean}>("/email/status")
      .then((result) => { if (active) setAvailable(result.available); })
      .catch(() => {});
    return () => { active = false; };
  }, []);
  async function run(action: () => Promise<void>) {
    setBusy(true); setError(""); setMessage("");
    try { await action(); } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  function request(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      const result = await personalRequest<{message: string}>(
        verification ? "/email/request" : "/password/request", "POST", verification ? {} : {email});
      setMessage(result.message);
    });
  }
  function confirm(event: FormEvent) {
    event.preventDefault();
    void run(async () => {
      await personalRequest(verification ? "/email/verify" : "/password/reset", "POST",
        verification ? {code: code.trim()} : {code: code.trim(), password});
      setCode(""); setPassword("");
      if (verification) { setMessage("Email verified."); onVerified?.(); }
      else { setPersonalToken(""); setMessage("Password updated. Sign in above. All sessions and assistant connections have been revoked."); }
    });
  }
  if (verified) return <p>Email verified</p>;
  return <details className={styles.card}>
    <summary>{verification ? "Verify your email" : "Forgot your password?"}</summary>
    {!available && <p>Email delivery is not available yet. You can still use a previously received code until it expires.</p>}
    <form onSubmit={request}>
      {!verification && <label>Recovery email<input type="email" autoComplete="email" required maxLength={254} value={email} onChange={e => setEmail(e.target.value)} /></label>}
      <button disabled={busy || !available}>Send {verification ? "verification" : "recovery"} code</button>
    </form>
    <form onSubmit={confirm}>
      <label>Email code<input required autoComplete="one-time-code" minLength={20} maxLength={100} value={code} onChange={e => setCode(e.target.value)} /></label>
      {!verification && <label>New password<input type="password" required autoComplete="new-password" minLength={12} maxLength={256} value={password} onChange={e => setPassword(e.target.value)} /></label>}
      <button disabled={busy}>{verification ? "Verify email" : "Reset password"}</button>
    </form>
    {message && <p role="status">{message}</p>}
    {error && <p role="alert" className={styles.error}>{error}</p>}
  </details>;
}
