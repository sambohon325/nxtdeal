"use client";

// Module product-page template (NXTDeal Marketing Site Audit — new Modules/Product pages,
// 2026-08-03). Renders Foundation, any paid Module, or the NXTDeal AI add-on from
// lib/marketing/modules.ts: hero → what it unlocks (feature list, level-tagged) → tier cards
// (Foundation free / Starter vs Pro) → close. One template, one page per Module.

import Link from "next/link";
import { MarketingShell, Section, Eyebrow, CtaLink } from "@/components/marketing/MarketingChrome";
import { BRAND_COLORS } from "@/components/BrandAngles";
import { type MarketingModule, type FeatureLevel } from "@/lib/marketing/modules";

const LEVEL_BADGE: Record<FeatureLevel, { label: string; cls: string }> = {
  free: { label: "Foundation", cls: "bg-emerald-500/15 text-emerald-400" },
  professional: { label: "Starter", cls: "bg-sky-500/15 text-sky-300" },
  enterprise: { label: "Pro", cls: "bg-violet-500/15 text-violet-300" },
};

export function ModulePageTemplate({ module: m }: { module: MarketingModule }) {
  const accent = BRAND_COLORS[m.color];
  const isFoundation = m.category === "foundation";

  return (
    <MarketingShell>
      {/* Hero */}
      <div className="relative overflow-hidden border-b border-zinc-900 px-8 py-20 md:py-24">
        <div
          className="pointer-events-none absolute -right-32 top-0 h-full w-[420px] opacity-20 blur-3xl"
          style={{ background: `radial-gradient(circle, ${accent}, transparent 70%)` }}
        />
        <div className="relative z-10 mx-auto max-w-4xl text-center">
          <Eyebrow color={m.color}>{m.eyebrow}</Eyebrow>
          <h1 className="mb-4 mt-2 text-4xl font-brand font-bold leading-tight tracking-tight md:text-5xl">{m.name}</h1>
          <p className="mx-auto mb-3 max-w-2xl text-lg text-zinc-300">{m.tagline}</p>
          <p className="mx-auto mb-8 max-w-2xl text-sm leading-relaxed text-zinc-500">{m.intro}</p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <CtaLink href="/start-free">Start Free</CtaLink>
            <CtaLink href="/pricing" variant="ghost">Compare plans</CtaLink>
          </div>
        </div>
      </div>

      {/* Features */}
      <Section>
        <Eyebrow color={m.color}>{isFoundation ? "What's free forever" : "What this Module unlocks"}</Eyebrow>
        <h2 className="mb-8 mt-2 text-2xl font-brand font-bold md:text-3xl">
          {isFoundation ? "Everything in Foundation" : `Inside the ${m.name}`}
        </h2>
        <div className="grid gap-3 md:grid-cols-2">
          {m.features.map((f) => (
            <div key={f.name} className="flex items-start justify-between gap-3 rounded-2xl border border-zinc-800 bg-white/[0.02] p-4">
              <div className="flex items-start gap-3">
                <span className="mt-1.5 h-2 w-2 shrink-0 rounded-full" style={{ background: accent }} />
                <span className="text-sm text-zinc-200">{f.name}</span>
              </div>
              <span className={`shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold ${LEVEL_BADGE[f.level].cls}`}>
                {LEVEL_BADGE[f.level].label}
              </span>
            </div>
          ))}
        </div>
      </Section>

      {/* Tiers */}
      <Section>
        <Eyebrow color={m.color}>Plans</Eyebrow>
        <h2 className="mb-8 mt-2 text-2xl font-brand font-bold md:text-3xl">
          {isFoundation ? "Free forever" : "Start free, upgrade this Module"}
        </h2>
        <div className={`grid gap-4 ${m.tiers.length > 1 ? "md:grid-cols-2" : "max-w-md"}`}>
          {m.tiers.map((t) => (
            <div key={t.name} className="flex flex-col rounded-2xl border border-zinc-800 bg-white/[0.02] p-6">
              <div className="mb-1 flex items-baseline justify-between">
                <div className="text-lg font-bold text-white">{t.name}</div>
                <div className="text-xs text-zinc-500">{t.seats}</div>
              </div>
              <p className="mb-4 text-sm text-zinc-400">{t.blurb}</p>
              <ul className="mb-5 flex-1 space-y-1.5">
                {t.includes.map((inc) => (
                  <li key={inc} className="flex items-start gap-2 text-sm text-zinc-300">
                    <span className="mt-0.5 text-emerald-400">✓</span>
                    {inc}
                  </li>
                ))}
              </ul>
              <CtaLink href={t.cta.href}>{t.cta.label}</CtaLink>
            </div>
          ))}
        </div>
        {!isFoundation && (
          <p className="mt-4 text-xs text-zinc-600">
            Foundation stays free while you run this Module. Pricing is confirmed at signup —{" "}
            <Link href="/contact" className="underline">talk to us</Link> for team and enterprise plans.
          </p>
        )}
      </Section>

      {/* Close */}
      <Section bleed className="border-b-0">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="mb-4 text-2xl font-brand font-bold md:text-3xl">Put your data in for free. Turn on {m.name} when you&apos;re ready.</h2>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <CtaLink href="/start-free">Start Free</CtaLink>
            <CtaLink href="/modules" variant="ghost">See all Modules</CtaLink>
          </div>
        </div>
      </Section>
    </MarketingShell>
  );
}
