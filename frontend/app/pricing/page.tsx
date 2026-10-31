"use client";

// Pricing / comparison page (NXTDeal Marketing Site Audit — new pricing page, 2026-08-03). A
// HubSpot-style grid: the free Foundation tier, each paid Module's Starter (1 seat) vs Pro (5+ seats)
// with what unlocks, and the managed-NXTDeal-AI-vs-bring-your-own-key add-on. No dollar amounts are
// invented (NXTDeal's "real data or an honest gap" principle) — the price is confirmed at signup;
// every path starts with "Start Free".

import Link from "next/link";
import { MarketingShell, Section, SectionHeading, PageHero, CtaLink } from "@/components/marketing/MarketingChrome";
import { BRAND_COLORS } from "@/components/BrandAngles";
import { FOUNDATION, PAID_FOR_PRICING } from "@/lib/marketing/modules";

export default function PricingPage() {
  return (
    <MarketingShell>
      <PageHero
        eyebrow="Pricing"
        title="Free To Start. Pay For The Modules You Turn On."
        sub="NXTDeal Foundation is free forever, up to 20 seats. Add paid Modules — each with a Starter and a Pro tier — only when you're ready. No credit card to begin."
        primaryCta={{ href: "/start-free", label: "Start Free" }}
        secondaryCta={{ href: "/contact", label: "Talk to us" }}
      />

      {/* Foundation */}
      <Section>
        <div className="mx-auto max-w-3xl rounded-2xl border border-emerald-500/30 bg-emerald-500/[0.04] p-6 md:p-8">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">FREE FOREVER · 20 SEATS</span>
              <h2 className="mt-2 text-2xl font-brand font-bold">{FOUNDATION.name}</h2>
              <p className="mt-1 max-w-xl text-[14px] text-zinc-300">{FOUNDATION.tagline}</p>
            </div>
            <CtaLink href="/start-free">Start Free</CtaLink>
          </div>
          <div className="mt-5 grid gap-2 sm:grid-cols-2">
            {FOUNDATION.features.map((f) => (
              <div key={f.name} className="flex items-start gap-2 text-[13px] text-zinc-300">
                <span className="mt-0.5 text-emerald-400">✓</span>
                {f.name}
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* Module Starter vs Pro grid */}
      <Section>
        <SectionHeading
          eyebrow="Paid Modules"
          title="Every Module: Starter vs Pro"
          sub="Starter is one power user; Pro is your team, with the enterprise features. Foundation stays free underneath either one."
        />
        <div className="mt-8 overflow-x-auto rounded-2xl border border-zinc-800">
          <table className="w-full min-w-[720px] border-collapse text-left">
            <thead>
              <tr className="border-b border-zinc-800 bg-white/[0.03] text-[12px] text-zinc-400">
                <th className="px-4 py-3 font-semibold">Module</th>
                <th className="px-4 py-3 font-semibold">Starter <span className="font-normal text-zinc-600">· 1 seat</span></th>
                <th className="px-4 py-3 font-semibold">Pro <span className="font-normal text-zinc-600">· 5+ seats</span></th>
              </tr>
            </thead>
            <tbody>
              {PAID_FOR_PRICING.map((m) => {
                const starter = m.tiers.find((t) => t.name === "Starter");
                const pro = m.tiers.find((t) => t.name === "Pro");
                return (
                  <tr key={m.slug} className="border-b border-zinc-900 align-top last:border-0">
                    <td className="px-4 py-4">
                      <Link href={`/modules/${m.slug}`} className="group inline-flex items-center gap-2">
                        <span className="h-2 w-2 rounded-full" style={{ background: BRAND_COLORS[m.color] }} />
                        <span className="text-[14px] font-semibold text-white group-hover:underline">{m.name}</span>
                      </Link>
                      <p className="mt-1 max-w-[220px] text-[11px] text-zinc-500">{m.tagline}</p>
                    </td>
                    <td className="px-4 py-4">
                      <ul className="space-y-1">
                        {(starter?.includes ?? []).map((f) => (
                          <li key={f} className="flex items-start gap-1.5 text-[12px] text-zinc-300">
                            <span className="mt-0.5 text-sky-300">✓</span>
                            {f}
                          </li>
                        ))}
                      </ul>
                    </td>
                    <td className="px-4 py-4">
                      <ul className="space-y-1">
                        {(pro?.includes ?? []).map((f) => (
                          <li key={f} className="flex items-start gap-1.5 text-[12px] text-zinc-300">
                            <span className="mt-0.5 text-violet-300">✓</span>
                            {f}
                          </li>
                        ))}
                      </ul>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-3 text-[12px] text-zinc-600">
          Per-Module pricing is confirmed at signup based on seats and tier. Every Module starts on a{" "}
          <Link href="/start-free" className="underline">Start Free</Link> flow — you upgrade from inside your instance.
        </p>
      </Section>

      {/* AI add-on */}
      <Section>
        <SectionHeading eyebrow="AI, your way" title="Managed, bring-your-own, or off" sub="NXTDeal is model-agnostic. Metering is by AI action; the cost of a bring-your-own key sits with you." />
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {[
            { t: "NXTDeal AI", tag: "Paid add-on · usage-billed", d: "Our hosted inference — zero setup, no key to manage. Billed by usage, with per-user limits your admin sets. Not on the free tier.", color: "teal" as const, href: "/modules/dealeros-ai" },
            { t: "Bring your own key", tag: "Free at any tier", d: "Use your own OpenAI, Anthropic, or Gemini key — or a homegrown endpoint. The cost of consumption sits with your own account.", color: "blue" as const, href: "/modules/dealeros-ai" },
            { t: "Turn AI off", tag: "Free · your choice", d: "Some people just don't want AI. Switch it off dealer-wide or per user — the AI chat and bot disappear; everything else works the same.", color: "yellow" as const, href: "/modules/dealeros-ai" },
          ].map((o) => (
            <Link key={o.t} href={o.href} className="group rounded-2xl border border-zinc-800 bg-white/[0.02] p-5 transition hover:border-zinc-600">
              <div className="mb-2 h-1 w-10 rounded-full" style={{ background: BRAND_COLORS[o.color] }} />
              <div className="text-[15px] font-semibold text-white group-hover:underline">{o.t}</div>
              <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-wide text-zinc-500">{o.tag}</div>
              <p className="text-[12px] leading-relaxed text-zinc-400">{o.d}</p>
            </Link>
          ))}
        </div>
      </Section>

      <Section bleed className="border-b-0">
        <div className="text-center">
          <h2 className="mb-6 text-2xl font-brand font-bold md:text-3xl">Start free. Upgrade only what you use.</h2>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <CtaLink href="/start-free">Start Free</CtaLink>
            <CtaLink href="/modules" variant="ghost">Browse Modules</CtaLink>
            <CtaLink href="/contact" variant="ghost">Talk to us</CtaLink>
          </div>
        </div>
      </Section>
    </MarketingShell>
  );
}
