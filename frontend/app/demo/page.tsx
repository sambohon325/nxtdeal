"use client";

// AI Demo entry (2026-07-25) — a real lead-gen + account gate, styled like the NXTDeal login so
// prospects start seeing the product immediately. Sign up (captures the lead in the Hub) or log
// back in, then drop into the seeded demo sandbox as the chosen role. Forgot-password included.
// Bot-protected with Cloudflare Turnstile when configured.

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { fetchDemoPersonas, startDemo, type PersonasResponse } from "@/lib/demo";
import { startDemoSession } from "@/lib/demoSession";
import {
  fetchDemoAuthConfig,
  demoSignup,
  demoLogin,
  demoForgot,
  demoReset,
  saveDemoLead,
  getDemoLead,
  clearDemoLead,
  type DemoLeadAccount,
} from "@/lib/demoAuth";
import { Turnstile, isTurnstileConfigured } from "@/components/demo/Turnstile";
import { AngledGlow, BrandRibbon } from "@/components/BrandAngles";

type View = "signin" | "signup" | "forgot" | "reset";

export default function DemoEntryPage() {
  const router = useRouter();
  const [personas, setPersonas] = useState<PersonasResponse | null>(null);
  const [turnstileOn, setTurnstileOn] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const returning = getDemoLead();
  const [view, setView] = useState<View>(returning ? "signin" : "signup");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // form state
  const [name, setName] = useState("");
  const [email, setEmail] = useState(returning?.email ?? "");
  const [password, setPassword] = useState("");
  const [persona, setPersona] = useState("");
  const [dealership, setDealership] = useState("");
  const [city, setCity] = useState("");
  const [region, setRegion] = useState("");
  const [country, setCountry] = useState("");
  const [phone, setPhone] = useState("");
  const [identifier, setIdentifier] = useState(returning?.email ?? "");
  const [turnstileToken, setTurnstileToken] = useState("");
  // reset
  const [resetToken, setResetToken] = useState("");
  const [newPassword, setNewPassword] = useState("");

  useEffect(() => {
    fetchDemoPersonas().then(setPersonas).catch((e) => setLoadError(e instanceof Error ? e.message : "Couldn't load the demo."));
    fetchDemoAuthConfig().then((c) => setTurnstileOn(c.turnstile_enabled)).catch(() => {});
  }, []);

  async function enterDemo(personaKey: string) {
    const res = await startDemo(personaKey, "guided");
    startDemoSession({
      token: res.token,
      sessionId: res.session_id,
      persona: res.persona,
      role: res.role,
      allowed_dashboards: res.allowed_dashboards,
      mode: res.mode,
      scenarios: res.scenarios,
      watermark: res.watermark,
    });
    router.push("/workspace");
  }

  async function submitSignup() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      if (turnstileOn && isTurnstileConfigured() && !turnstileToken) {
        throw new Error("Please complete the bot check.");
      }
      const account = await demoSignup({
        name, email, password, persona,
        position: personas?.personas.find((p) => p.key === persona)?.label,
        dealership, city, region, country, phone,
        turnstile_token: turnstileToken || undefined,
      });
      saveDemoLead(account);
      await enterDemo(account.persona);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-up failed.");
      setBusy(false);
    }
  }

  async function submitLogin() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const account = await demoLogin(identifier, password);
      saveDemoLead(account);
      await enterDemo(account.persona);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Sign-in failed.");
      setBusy(false);
    }
  }

  async function submitForgot() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const res = await demoForgot(email || identifier);
      setNotice("If that email has an account, a reset link is on its way.");
      if (res.dev_reset_token) {
        // Until email delivery is wired, hand the token straight to the reset step.
        setResetToken(res.dev_reset_token);
        setView("reset");
        setNotice("Enter a new password to finish resetting.");
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't start the reset.");
    } finally {
      setBusy(false);
    }
  }

  async function submitReset() {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await demoReset(email || identifier, resetToken, newPassword);
      setNotice("Password reset — sign in with your new password.");
      setView("signin");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Reset failed.");
    } finally {
      setBusy(false);
    }
  }

  async function resume() {
    if (!returning || busy) return;
    setBusy(true);
    try {
      await enterDemo(returning.persona);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't resume.");
      setBusy(false);
    }
  }

  const input =
    "w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2.5 text-sm text-white placeholder-zinc-500 focus:outline-none focus:border-brand-teal";
  const disabled = personas ? !personas.enabled : false;

  return (
    <div className="relative flex h-full w-full items-center justify-center overflow-y-auto bg-[#0e0e10] p-4 font-brand text-white">
      <AngledGlow color="blue" className="pointer-events-none absolute -left-40 top-0 h-full w-[480px]" />
      <AngledGlow color="teal" className="pointer-events-none absolute -right-40 top-0 h-full w-[480px]" />

      <div className="relative z-10 my-6 w-full max-w-md overflow-hidden rounded-2xl border border-white/10 bg-[#141416]/85 shadow-2xl backdrop-blur-md">
        <div className="bg-brand-teal px-6 pb-7 pt-7 text-black">
          <div className="text-[11px] font-semibold uppercase tracking-[0.2em] opacity-70">NXTDeal · Product Demo</div>
          <h1 className="mt-1 text-2xl font-bold leading-tight">
            {view === "signup" ? "Experience NXTDeal" : view === "signin" ? "Welcome back" : "Reset your password"}
          </h1>
          <p className="mt-1 text-sm opacity-80">
            {view === "signup"
              ? "A fully working dealership, guided by AI. Nothing you do is saved."
              : view === "signin"
              ? "Sign in to pick up your demo where you left off."
              : "We'll get you back in."}
          </p>
        </div>
        <BrandRibbon height={3} />

        <div className="space-y-3 px-6 py-6">
          {loadError && <div className="rounded-lg bg-amber-500/10 p-2.5 text-xs text-amber-300">{loadError}</div>}
          {disabled && <div className="rounded-lg bg-white/[0.04] p-2.5 text-xs text-zinc-400">The guided demo isn&apos;t available on this environment.</div>}
          {notice && <div className="rounded-lg bg-brand-teal/10 p-2.5 text-xs text-zinc-200">{notice}</div>}
          {error && <div className="rounded-lg bg-red-500/10 p-2.5 text-xs text-red-400">{error}</div>}

          {/* Returning-user quick resume */}
          {returning && view === "signin" && (
            <div className="rounded-xl border border-white/10 bg-white/[0.04] p-3">
              <div className="text-sm text-white">Welcome back, {returning.name.split(" ")[0]}.</div>
              <button onClick={resume} disabled={busy || disabled} className="mt-2 w-full rounded-full bg-brand-teal py-2 text-sm font-semibold text-black disabled:opacity-50">
                {busy ? "Loading…" : `Resume your ${returning.persona.replace(/_/g, " ")} demo`}
              </button>
              <button onClick={() => { clearDemoLead(); setView("signin"); setIdentifier(""); }} className="mt-1.5 w-full text-center text-[11px] text-zinc-500 hover:text-white">
                Not you? Sign in as someone else
              </button>
            </div>
          )}

          {/* SIGN IN */}
          {view === "signin" && !returning && (
            <>
              <input className={input} placeholder="Email or username" value={identifier} onChange={(e) => setIdentifier(e.target.value)} autoCapitalize="none" />
              <input className={input} type="password" placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
              <button onClick={submitLogin} disabled={busy || disabled || !identifier || !password} className="w-full rounded-full bg-brand-teal py-3 text-sm font-semibold text-black disabled:opacity-50">
                {busy ? "Signing in…" : "Sign in & resume demo"}
              </button>
              <div className="flex items-center justify-between text-[11px] text-zinc-500">
                <button onClick={() => { setError(null); setView("forgot"); }} className="hover:text-white">Forgot password?</button>
                <button onClick={() => { setError(null); setView("signup"); }} className="hover:text-white">New here? Start a demo →</button>
              </div>
            </>
          )}

          {/* SIGN UP (lead form) */}
          {view === "signup" && (
            <>
              <div className="grid grid-cols-2 gap-2">
                <input className={input} placeholder="Full name" value={name} onChange={(e) => setName(e.target.value)} />
                <input className={input} placeholder="Phone" value={phone} onChange={(e) => setPhone(e.target.value)} inputMode="tel" />
              </div>
              <select className={`${input} appearance-none`} value={persona} onChange={(e) => setPersona(e.target.value)}>
                <option value="" className="bg-zinc-900">What best describes you?</option>
                {personas?.personas.map((p) => (
                  <option key={p.key} value={p.key} className="bg-zinc-900">{p.label}</option>
                ))}
              </select>
              <input className={input} placeholder="Dealership" value={dealership} onChange={(e) => setDealership(e.target.value)} />
              <div className="grid grid-cols-3 gap-2">
                <input className={input} placeholder="City" value={city} onChange={(e) => setCity(e.target.value)} />
                <input className={input} placeholder="State/Prov." value={region} onChange={(e) => setRegion(e.target.value)} />
                <input className={input} placeholder="Country" value={country} onChange={(e) => setCountry(e.target.value)} />
              </div>
              <input className={input} placeholder="Work email" value={email} onChange={(e) => setEmail(e.target.value)} autoCapitalize="none" inputMode="email" />
              <input className={input} type="password" placeholder="Create a password (8+ chars)" value={password} onChange={(e) => setPassword(e.target.value)} />
              {turnstileOn && <Turnstile onToken={setTurnstileToken} />}
              <button onClick={submitSignup} disabled={busy || disabled || !name || !email || !password || !persona} className="w-full rounded-full bg-brand-teal py-3 text-sm font-semibold text-black disabled:opacity-50">
                {busy ? "Starting your demo…" : "Start my AI demo"}
              </button>
              <div className="text-center text-[11px] text-zinc-500">
                Already did this?{" "}
                <button onClick={() => { setError(null); setView("signin"); }} className="text-brand-teal hover:underline">Sign in</button>
              </div>
              <p className="text-center text-[10px] text-zinc-600">Takes about 8 minutes · nothing you do is saved.</p>
            </>
          )}

          {/* FORGOT */}
          {view === "forgot" && (
            <>
              <input className={input} placeholder="Your email" value={email} onChange={(e) => setEmail(e.target.value)} autoCapitalize="none" inputMode="email" />
              <button onClick={submitForgot} disabled={busy || !email} className="w-full rounded-full bg-brand-teal py-3 text-sm font-semibold text-black disabled:opacity-50">
                {busy ? "Sending…" : "Send reset link"}
              </button>
              <button onClick={() => { setError(null); setNotice(null); setView("signin"); }} className="w-full text-center text-[11px] text-zinc-500 hover:text-white">‹ Back to sign in</button>
            </>
          )}

          {/* RESET */}
          {view === "reset" && (
            <>
              <input className={input} placeholder="Your email" value={email} onChange={(e) => setEmail(e.target.value)} autoCapitalize="none" inputMode="email" />
              <input className={input} placeholder="Reset code" value={resetToken} onChange={(e) => setResetToken(e.target.value)} />
              <input className={input} type="password" placeholder="New password (8+ chars)" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
              <button onClick={submitReset} disabled={busy || !email || !resetToken || !newPassword} className="w-full rounded-full bg-brand-teal py-3 text-sm font-semibold text-black disabled:opacity-50">
                {busy ? "Resetting…" : "Set new password"}
              </button>
              <button onClick={() => { setError(null); setNotice(null); setView("signin"); }} className="w-full text-center text-[11px] text-zinc-500 hover:text-white">‹ Back to sign in</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
