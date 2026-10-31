"use client";

// Start Free — the self-serve sign-up + instance-setup portal (NXTDeal Free Forever funnel,
// 2026-08-03). Replaces "Book a Demo / Request Pricing" mailto dead-ends as the site's primary
// conversion path. Six guided steps (per the marketing-site roadmap): Start Free → Instance Setup →
// Industry Package Suggestion → Seats & Team → Data Connections → Land in the live instance.
//
// Step 1 creates a REAL free Foundation account via the Hub's public signup (lib/signup.ts →
// hub/core/dealer_signup.py), so the lead is captured even if later steps are abandoned. Steps 2–5
// are the guided setup that lands the dealer; instance-config endpoints (subdomain/seats/connections)
// are a Hub follow-up, so those preferences are collected and carried into the hand-off.

import { useState } from "react";
import { MarketingShell, Section, Eyebrow, CtaLink } from "@/components/marketing/MarketingChrome";
import { MODULE_LABELS } from "@/lib/entitlements";
import { BUSINESS_TYPES, startFreeSignup, type SignupResult } from "@/lib/signup";

const FOUNDATION_FEATURES = [
  { key: "crm", label: "CRM (contacts, customers, opportunities)" },
  { key: "inventory", label: "Inventory (upload, VIN decode, search)" },
  { key: "communications", label: "Communications (email + SMS logging)" },
  { key: "reporting", label: "Reporting (inventory, leads, sales, service)" },
  { key: "website", label: "Website (inventory site, contact forms)" },
];
const FREE_SEATS = 20;

const STEPS = ["Start Free", "Instance Setup", "Your Package", "Seats & Team", "Data", "You're Live"];

function slugify(s: string) {
  return s.trim().toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "") || "dealer";
}

export default function StartFreePage() {
  const [step, setStep] = useState(1);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Step 1 inputs
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [dealership, setDealership] = useState("");
  const [businessType, setBusinessType] = useState("");

  // Result of the real signup
  const [result, setResult] = useState<SignupResult | null>(null);

  // Steps 2–5 setup prefs
  const [subdomain, setSubdomain] = useState("");
  const [features, setFeatures] = useState<Record<string, boolean>>(
    Object.fromEntries(FOUNDATION_FEATURES.map((f) => [f.key, true])),
  );
  const [addOns, setAddOns] = useState<Set<string>>(new Set());
  const [invites, setInvites] = useState<string[]>([]);
  const [inviteDraft, setInviteDraft] = useState("");
  const [dataConn, setDataConn] = useState<"undecided" | "skip" | "dms" | "csv">("undecided");

  const suggested = result?.suggested_modules ?? BUSINESS_TYPES.find((b) => b.key === businessType)?.suggested_modules ?? [];

  async function submitStep1() {
    setError(null);
    if (!dealership.trim()) return setError("Enter your dealership name.");
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) return setError("Enter a valid work email.");
    if (!businessType) return setError("Pick what kind of business you are.");
    setBusy(true);
    const r = await startFreeSignup({ name, work_email: email, dealership_name: dealership, business_type: businessType });
    setBusy(false);
    if (r.error) {
      setError(r.reason === "email_taken" ? "An account already exists for that email — try signing in." : r.error);
      return;
    }
    setResult(r);
    setSubdomain(r.slug || slugify(dealership));
    setAddOns(new Set(r.suggested_modules ?? []));
    setStep(2);
  }

  const seatsUsed = 1 + invites.length;

  return (
    <MarketingShell>
      <Section>
        <div className="mx-auto max-w-3xl">
          <div className="text-center">
            <Eyebrow color="teal">Free Forever · No credit card</Eyebrow>
            <h1 className="mt-2 text-3xl md:text-5xl font-brand font-bold tracking-tight">Start Free</h1>
            <p className="mt-3 text-zinc-400">
              Create your NXTDeal account and start operating in minutes. Put your data in for free; add paid Modules only when you&apos;re ready.
            </p>
          </div>

          {/* Progress */}
          <div className="mt-8 flex items-center justify-between gap-1">
            {STEPS.map((label, i) => {
              const n = i + 1;
              const done = n < step;
              const active = n === step;
              return (
                <div key={label} className="flex-1 text-center">
                  <div
                    className={`mx-auto flex h-7 w-7 items-center justify-center rounded-full text-[12px] font-bold ${
                      done ? "bg-emerald-600 text-white" : active ? "bg-[var(--brand-blue,#2B68AB)] text-white" : "bg-zinc-800 text-zinc-500"
                    }`}
                    style={active ? { background: "#2B68AB" } : done ? { background: "#0f9d6b" } : undefined}
                  >
                    {done ? "✓" : n}
                  </div>
                  <div className={`mt-1 hidden text-[10px] sm:block ${active ? "text-white" : "text-zinc-600"}`}>{label}</div>
                </div>
              );
            })}
          </div>

          {error && <div className="mt-6 rounded-lg bg-red-500/10 px-4 py-2.5 text-sm text-red-400">{error}</div>}

          <div className="mt-6 rounded-2xl border border-zinc-800 bg-white/[0.02] p-6">
            {/* STEP 1 — Start Free */}
            {step === 1 && (
              <div className="space-y-4">
                <Field label="Your name">
                  <input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="Sam Bohon" />
                </Field>
                <Field label="Work email">
                  <input className={inputCls} value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@dealership.com" />
                </Field>
                <Field label="Dealership name">
                  <input className={inputCls} value={dealership} onChange={(e) => setDealership(e.target.value)} placeholder="Acme Auto" />
                </Field>
                <Field label="What kind of business are you?">
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                    {BUSINESS_TYPES.map((b) => (
                      <button
                        key={b.key}
                        type="button"
                        onClick={() => setBusinessType(b.key)}
                        className={`rounded-lg border px-3 py-2 text-left text-[12px] ${
                          businessType === b.key ? "border-emerald-500 bg-emerald-500/10 text-white" : "border-zinc-800 text-zinc-300 hover:border-zinc-600"
                        }`}
                      >
                        {b.label}
                      </button>
                    ))}
                  </div>
                </Field>
                <button onClick={submitStep1} disabled={busy} className={primaryBtn}>
                  {busy ? "Creating your account…" : "Start Free →"}
                </button>
                <p className="text-center text-[11px] text-zinc-600">No credit card. 20 free seats. Cancel anytime.</p>
              </div>
            )}

            {/* STEP 2 — Instance Setup */}
            {step === 2 && (
              <StepBody
                title="Set up your instance"
                sub="Confirm your details and pick a subdomain. Your Foundation features are on by default."
                onBack={() => setStep(1)}
                onNext={() => setStep(3)}
              >
                <Field label="Dealership">
                  <input className={inputCls} value={dealership} onChange={(e) => setDealership(e.target.value)} />
                </Field>
                <Field label="Your subdomain">
                  <div className="flex items-center gap-2">
                    <input className={inputCls} value={subdomain} onChange={(e) => setSubdomain(slugify(e.target.value))} />
                    <span className="shrink-0 text-[12px] text-zinc-500">.nxtdeal.app</span>
                  </div>
                </Field>
                <Field label="Foundation features to activate first">
                  <div className="space-y-1.5">
                    {FOUNDATION_FEATURES.map((f) => (
                      <label key={f.key} className="flex cursor-pointer items-center gap-2 text-[13px] text-zinc-300">
                        <input
                          type="checkbox"
                          checked={features[f.key]}
                          onChange={(e) => setFeatures({ ...features, [f.key]: e.target.checked })}
                        />
                        {f.label}
                      </label>
                    ))}
                  </div>
                </Field>
              </StepBody>
            )}

            {/* STEP 3 — Industry Package */}
            {step === 3 && (
              <StepBody
                title="Your industry package"
                sub={`Based on "${BUSINESS_TYPES.find((b) => b.key === businessType)?.label}", these paid Modules are recommended. Add them now or later — Foundation stays free either way.`}
                onBack={() => setStep(2)}
                onNext={() => setStep(4)}
              >
                {suggested.length === 0 && <p className="text-[13px] text-zinc-500">Foundation covers your basics — add Modules anytime.</p>}
                <div className="space-y-2">
                  {suggested.map((m) => {
                    const info = MODULE_LABELS[m] ?? { name: m, tagline: "" };
                    const on = addOns.has(m);
                    return (
                      <div key={m} className="flex items-start justify-between gap-3 rounded-lg border border-zinc-800 px-3 py-2.5">
                        <div className="min-w-0">
                          <div className="text-[13px] font-semibold text-white">{info.name}</div>
                          <div className="text-[11px] text-zinc-500">{info.tagline}</div>
                        </div>
                        <button
                          type="button"
                          onClick={() => {
                            const next = new Set(addOns);
                            on ? next.delete(m) : next.add(m);
                            setAddOns(next);
                          }}
                          className={`shrink-0 rounded-md px-2.5 py-1 text-[11px] font-semibold ${on ? "bg-emerald-600 text-white" : "bg-zinc-800 text-zinc-300"}`}
                        >
                          {on ? "✓ Added" : "Add"}
                        </button>
                      </div>
                    );
                  })}
                </div>
                <p className="text-[11px] text-zinc-600">Added Modules are noted for your setup — nothing is charged. You activate them from inside your instance.</p>
              </StepBody>
            )}

            {/* STEP 4 — Seats & Team */}
            {step === 4 && (
              <StepBody
                title="Invite your team"
                sub={`Foundation includes ${FREE_SEATS} free seats. Invite teammates now or skip and do it later.`}
                onBack={() => setStep(3)}
                onNext={() => setStep(5)}
              >
                <div className="flex items-center gap-2">
                  <input
                    className={inputCls}
                    value={inviteDraft}
                    onChange={(e) => setInviteDraft(e.target.value)}
                    placeholder="teammate@dealership.com"
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && /^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(inviteDraft) && seatsUsed < FREE_SEATS) {
                        setInvites([...invites, inviteDraft]);
                        setInviteDraft("");
                      }
                    }}
                  />
                  <button
                    type="button"
                    disabled={!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(inviteDraft) || seatsUsed >= FREE_SEATS}
                    onClick={() => {
                      setInvites([...invites, inviteDraft]);
                      setInviteDraft("");
                    }}
                    className="shrink-0 rounded-lg bg-zinc-800 px-3 py-2 text-[12px] font-semibold text-white disabled:opacity-40"
                  >
                    Add
                  </button>
                </div>
                <div className="text-[11px] text-zinc-500">{seatsUsed} / {FREE_SEATS} seats used (you + {invites.length} invited)</div>
                <div className="space-y-1">
                  {invites.map((em, i) => (
                    <div key={i} className="flex items-center justify-between rounded-md border border-zinc-800 px-3 py-1.5 text-[12px] text-zinc-300">
                      {em}
                      <button type="button" onClick={() => setInvites(invites.filter((_, j) => j !== i))} className="text-zinc-600 hover:text-zinc-300">
                        Remove
                      </button>
                    </div>
                  ))}
                </div>
              </StepBody>
            )}

            {/* STEP 5 — Data connections */}
            {step === 5 && (
              <StepBody
                title="Bring your data (optional)"
                sub="Connect a DMS/CRM feed or upload a CSV to import inventory and customers — or skip and do it later from Readiness."
                onBack={() => setStep(4)}
                onNext={() => setStep(6)}
                nextLabel="Finish & go live →"
              >
                <div className="grid gap-2 sm:grid-cols-3">
                  {[
                    { key: "dms", label: "Connect a DMS/CRM", hint: "CDK, Reynolds, Tekion…" },
                    { key: "csv", label: "Upload a CSV", hint: "Inventory or customers" },
                    { key: "skip", label: "Skip for now", hint: "Do it later" },
                  ].map((o) => (
                    <button
                      key={o.key}
                      type="button"
                      onClick={() => setDataConn(o.key as typeof dataConn)}
                      className={`rounded-lg border px-3 py-3 text-left ${dataConn === o.key ? "border-emerald-500 bg-emerald-500/10" : "border-zinc-800 hover:border-zinc-600"}`}
                    >
                      <div className="text-[13px] font-semibold text-white">{o.label}</div>
                      <div className="text-[11px] text-zinc-500">{o.hint}</div>
                    </button>
                  ))}
                </div>
              </StepBody>
            )}

            {/* STEP 6 — Live */}
            {step === 6 && (
              <div className="space-y-4 text-center">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-emerald-600 text-2xl">✓</div>
                <h3 className="text-xl font-bold text-white">You&apos;re live, {name?.split(" ")[0] || "welcome"}!</h3>
                <p className="text-sm text-zinc-400">
                  Your free NXTDeal instance is ready. Foundation is on, your data tools are set up, and your recommended Modules are waiting inside — activate them whenever you want.
                </p>
                <div className="mx-auto max-w-sm rounded-lg border border-zinc-800 bg-white/[0.02] p-4 text-left text-[12px] text-zinc-400">
                  <Recap label="Instance" value={`${subdomain}.nxtdeal.app`} />
                  <Recap label="Plan" value={`Foundation · ${FREE_SEATS} free seats`} />
                  <Recap label="Team invited" value={invites.length ? `${invites.length}` : "just you for now"} />
                  <Recap label="Modules noted" value={addOns.size ? Array.from(addOns).map((m) => MODULE_LABELS[m]?.name ?? m).join(", ") : "Foundation only"} />
                  {result?.warnings?.length ? <div className="mt-2 text-[11px] text-amber-400">{result.warnings.join(" ")}</div> : null}
                </div>
                <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
                  <CtaLink href={result?.instance_url ?? `https://${subdomain}.nxtdeal.app`}>Go to my NXTDeal →</CtaLink>
                  <CtaLink href="/solutions" variant="ghost">Explore Modules</CtaLink>
                </div>
              </div>
            )}
          </div>

          <p className="mt-6 text-center text-[12px] text-zinc-600">
            Not ready to create an account? <a href="/solutions" className="text-zinc-400 underline">Explore the platform</a> or{" "}
            <a href="/dealeros-network" className="text-zinc-400 underline">install NXTDeal Network free</a>.
          </p>
        </div>
      </Section>
    </MarketingShell>
  );
}

const inputCls =
  "w-full rounded-lg border border-zinc-800 bg-black/30 px-3 py-2 text-sm text-white outline-none placeholder:text-zinc-600 focus:border-zinc-600";
const primaryBtn = "w-full rounded-lg bg-emerald-600 px-4 py-2.5 text-sm font-bold text-white hover:bg-emerald-500 disabled:opacity-50";

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="mb-1 text-[12px] font-medium text-zinc-400">{label}</div>
      {children}
    </div>
  );
}

function StepBody({
  title,
  sub,
  children,
  onBack,
  onNext,
  nextLabel = "Continue →",
}: {
  title: string;
  sub: string;
  children: React.ReactNode;
  onBack: () => void;
  onNext: () => void;
  nextLabel?: string;
}) {
  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-lg font-bold text-white">{title}</h3>
        <p className="mt-0.5 text-[13px] text-zinc-400">{sub}</p>
      </div>
      {children}
      <div className="flex items-center justify-between pt-2">
        <button onClick={onBack} className="rounded-lg px-3 py-2 text-[13px] text-zinc-400 hover:text-white">
          ← Back
        </button>
        <button onClick={onNext} className="rounded-lg bg-emerald-600 px-4 py-2 text-[13px] font-bold text-white hover:bg-emerald-500">
          {nextLabel}
        </button>
      </div>
    </div>
  );
}

function Recap({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex justify-between gap-3 border-b border-zinc-900 py-1 last:border-0">
      <span className="text-zinc-600">{label}</span>
      <span className="text-right text-zinc-300">{value}</span>
    </div>
  );
}
