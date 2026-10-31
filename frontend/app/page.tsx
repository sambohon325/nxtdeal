"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import showroom from "@/public/brand/nxtdeal-showroom.webp";
import { BrandLogo } from "@/components/BrandLogo";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import { ComingSoon } from "@/components/marketing/ComingSoon";

const isMarketingOnly = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "marketing";

export default function Home() {
  const router = useRouter();

  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [help, setHelp] = useState("");

  async function handleSignIn() {
    if (!employeeId.trim() || !password.trim() || loading) return;

    setError("");
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          employee_id: employeeId,
          password,
        }),
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        setError(data.error ?? "Sign in failed.");
        return;
      }

      saveSession({
        token: data.token,
        employeeId: data.employee_id,
        role: data.role,
        allowedDashboards: data.allowed_dashboards ?? [],
      });

      if (data.must_change_password) {
        router.push("/change-password");
      } else if (data.role === "BDC" || data.role === "MARKETING") {
        // Scoped roles land on the focused shell by default (they can still reach the full
        // workspace from its header).
        router.push("/focus");
      } else {
        router.push("/workspace");
      }
    } catch {
      setError("Unable to reach NXTDeal backend.");
    } finally {
      setLoading(false);
    }
  }

  if (isMarketingOnly) {
    return <ComingSoon />;
  }

  return (
    <div className="nxt-entry">
      <Image src={showroom} alt="" fill priority sizes="100vw" className="nxt-scene" />
      <div className="nxt-scene-shade" />
      <div className="nxt-entry-content">
        <header className="nxt-entry-header">
          <BrandLogo large />
          <p className="nxt-promise">Dealerships today.<br />A brighter tomorrow.</p>
        </header>
        <main className="nxt-entry-main">
          <section className="nxt-introduction" aria-labelledby="entry-heading">
            <h1 id="entry-heading">Intelligence<br /><span>in Motion.</span></h1>
            <p>The dealer operating system powered by Chrono — unifying your data, decisions, and opportunities to drive real results.</p>
            <ul className="nxt-pillars" aria-label="Our focus">
              <li>People</li><li>Process</li><li>Profit</li><li>Tomorrow</li>
            </ul>
          </section>
          <section className="nxt-login" aria-labelledby="sign-in-heading">
            <h2 id="sign-in-heading">Welcome Back</h2>
            <p className="nxt-eyebrow">Sign in to NXTDeal</p>
            <form onSubmit={(event) => { event.preventDefault(); void handleSignIn(); }}>
              {error && <p className="nxt-form-error" role="alert">{error}</p>}
              <label className="nxt-field">
                <svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="7" r="4" /><path d="M3 22v-3a9 9 0 0 1 18 0v3Z" /></svg>
                <span className="sr-only">Employee ID or Email</span>
                <input autoComplete="username" required placeholder="Employee ID or Email" value={employeeId} onChange={(e) => setEmployeeId(e.target.value)} />
              </label>
              <label className="nxt-field">
                <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="10" width="16" height="12" rx="2" /><path d="M8 10V6a4 4 0 0 1 8 0v4M12 15v3" /></svg>
                <span className="sr-only">Password</span>
                <input type={showPassword ? "text" : "password"} autoComplete="current-password" required placeholder="Password" value={password} onChange={(e) => setPassword(e.target.value)} />
                <button className="nxt-password-toggle" type="button" aria-label={showPassword ? "Hide password" : "Show password"} aria-pressed={showPassword} onClick={() => setShowPassword(!showPassword)}>
                  <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12Z" /><circle cx="12" cy="12" r="3" />{showPassword && <path d="m3 3 18 18" />}</svg>
                </button>
              </label>
              <div className="nxt-form-options"><button type="button" onClick={() => setHelp("Contact your dealership administrator to reset your password.")}>Forgot password?</button></div>
              <button type="submit" disabled={loading} className="nxt-sign-in">{loading ? "Signing In…" : "Sign In"}<span aria-hidden="true">→</span></button>
              <div className="nxt-divider"><span>Or</span></div>
              <button type="button" className="nxt-sso" disabled aria-describedby="sso-note"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 22V2h14v20M2 22h20M9 22v-5h6v5M9 5v2m6-2v2M9 9v2m6-2v2M9 13v1m6-1v1" /></svg>Sign in with SSO</button>
              <p id="sso-note" className="nxt-sso-note">SSO is not available on this sign-in page yet.</p>
              {help && <p className="nxt-help" role="status">{help}</p>}
              <p className="nxt-request">Need access? <Link href="/contact">Request Account</Link></p>
            </form>
          </section>
        </main>
        <footer className="nxt-entry-footer"><span>© 2026 Chronos. All rights reserved.</span><Link href="/contact">Support</Link></footer>
      </div>
    </div>
  );
}
