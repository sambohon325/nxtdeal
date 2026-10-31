"use client";

import { useState } from "react";
import Link from "next/link";
import Image from "next/image";
import showroom from "@/public/brand/nxtdeal-showroom.webp";
import { BrandLogo } from "@/components/BrandLogo";
import { useRouter } from "next/navigation";
import { API_BASE } from "@/lib/api";
import { saveSession } from "@/lib/auth";
import handoffStyles from "./handoff.module.css";

const isMarketingOnly = process.env.NEXT_PUBLIC_DEPLOYMENT_MODE === "marketing";
const repository = "https://github.com/sambohon325/nxtdeal";

function CommunityHandoff() {
  return (
    <main className={handoffStyles.page}>
      <div className={handoffStyles.glow} aria-hidden="true" />
      <div className={handoffStyles.shell}>
        <header className={handoffStyles.header}>
          <BrandLogo />
          <span className={handoffStyles.status}><span aria-hidden="true" /> Community handoff</span>
        </header>

        <section className={handoffStyles.hero} aria-labelledby="handoff-heading">
          <p className={handoffStyles.eyebrow}>An open-source project</p>
          <h1 id="handoff-heading">The next chapter<br /><span>belongs to the community.</span></h1>
          <p className={handoffStyles.summary}>
            We’ve concluded our active development of NXTDeal to focus on other projects.
            The source is now public, and we’re excited to see what the community builds with it.
          </p>
          <div className={handoffStyles.actions}>
            <a className={handoffStyles.primary} href={repository}>
              Explore NXTDeal on GitHub <span aria-hidden="true">↗</span>
            </a>
            <a className={handoffStyles.secondary} href={`${repository}/blob/main/COMMUNITY-HANDOFF.md`}>
              Read the project handoff
            </a>
          </div>
        </section>

        <section className={handoffStyles.details} aria-label="Project information">
          <article>
            <span className={handoffStyles.number}>01</span>
            <h2>Open source</h2>
            <p>Browse the code and project notes in the public repository.</p>
          </article>
          <article>
            <span className={handoffStyles.number}>02</span>
            <h2>Community led</h2>
            <p>Development and support are now in the hands of community maintainers.</p>
          </article>
          <article>
            <span className={handoffStyles.number}>03</span>
            <h2>Early stage</h2>
            <p>The project is unfinished and has not been validated as production-ready.</p>
          </article>
        </section>

        <section className={handoffStyles.overview} aria-labelledby="nxtapp-heading">
          <p className={handoffStyles.eyebrow}>The product</p>
          <h2 id="nxtapp-heading">What is NXTapp?</h2>
          <p>NXTapp (NXTDeal) is an open-source dealership operations workspace: a shared place for teams to work across customer relationships, sales, inventory, service, marketing, finance and day-to-day operations. The project combines a web app, Python API and dealer administration Hub, with Chrono decision-support capabilities.</p>
          <p>The source snapshot includes substantial product work across these areas. It is an unfinished project, and feature presence does not mean every workflow is complete, connected to a live provider, or ready for production.</p>
          <div className={handoffStyles.capabilities}>
            <article><h3>Customer and sales workflows</h3><p>CRM and BDC lead records, follow-up queues, appointments, customer journeys, deals and delivery workflows.</p></article>
            <article><h3>Department workspaces</h3><p>Shared application surfaces for marketing, inventory, service and parts, finance, operations and administration.</p></article>
            <article><h3>Planning and decision support</h3><p>Dealership Lab scenarios, reporting and forecasting concepts, plus Chrono components for structured analysis.</p></article>
            <article><h3>Platform foundations</h3><p>FastAPI services, a Next.js interface, workflow and audit infrastructure, access controls, dealer Hub and integration scaffolding.</p></article>
          </div>
        </section>

        <section className={handoffStyles.gallery} aria-labelledby="screenshots-heading">
          <p className={handoffStyles.eyebrow}>A look inside</p>
          <h2 id="screenshots-heading">Screens from the NXTapp</h2>
          <p className={handoffStyles.galleryNote}>These captures show interface work and examples from the project. Some are sample-data demos; they do not establish that a live dealership deployment or integration is available.</p>
          <div className={handoffStyles.shots}>
            <figure><a href="/handoff/nxtdeal-home-real-product.jpg"><Image src="/handoff/nxtdeal-home-real-product.jpg" alt="NXTDeal sales workspace interface shown beside its daily overview and dealership workflow navigation" width={1280} height={720} loading="lazy" /></a><figcaption><strong>Sales workspace</strong><span>Follow-ups, appointments, vehicles and next actions in a shared workspace.</span></figcaption></figure>
            <figure><a href="/handoff/nxtdeal-crm-report-demo.jpg"><Image src="/handoff/nxtdeal-crm-report-demo.jpg" alt="NXTDeal sample CRM workflow demo showing leads, appointments and appointment reporting" width={1280} height={720} loading="lazy" /></a><figcaption><strong>CRM workflow example</strong><span>A sample lead-to-appointment flow with a simple performance view.</span></figcaption></figure>
            <figure><a href="/handoff/nxtdeal-lab-dashboard.jpg"><Image src="/handoff/nxtdeal-lab-dashboard.jpg" alt="Dealership Lab scenario screen with editable assumptions and modeled outcome comparison" width={1280} height={720} loading="lazy" /></a><figcaption><strong>Dealership Lab</strong><span>Scenario assumptions and modeled outcomes for planning conversations.</span></figcaption></figure>
          </div>
        </section>

        <footer className={handoffStyles.footer}>
          <span>NXTDeal · Community handoff</span>
          <a href={`${repository}/blob/main/CONTRIBUTING.md`}>Contributing on GitHub <span aria-hidden="true">↗</span></a>
        </footer>
      </div>
    </main>
  );
}

export default function Home() {
  const router = useRouter();

  const [employeeId, setEmployeeId] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [help, setHelp] = useState("");

  if (isMarketingOnly) {
    return <CommunityHandoff />;
  }

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
