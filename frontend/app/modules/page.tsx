"use client";

// Modules index (NXTDeal Marketing Site Audit — new Modules/Product pages, 2026-08-03). Replaces the
// single long /solutions mega-page as the way to browse the product: Foundation (free) up top, then a
// grid of the eight paid Modules, then the NXTDeal AI add-on — each linking to its own page.

import Link from "next/link";
import { MarketingShell, Section, SectionHeading, PageHero, CtaLink } from "@/components/marketing/MarketingChrome";
import { BRAND_COLORS } from "@/components/BrandAngles";
import { FOUNDATION, MODULES, AI_ADDON } from "@/lib/marketing/modules";

function ModuleCard({ slug, name, tagline, color }: { slug: string; name: string; tagline: string; color: keyof typeof BRAND_COLORS }) {
  return (
    <Link
      href={`/modules/${slug}`}
      className="group relative overflow-hidden rounded-2xl border border-zinc-800 bg-white/[0.02] p-5 transition hover:border-zinc-600"
    >
      <div className="mb-2 h-1 w-10 rounded-full" style={{ background: BRAND_COLORS[color] }} />
      <div className="mb-1 text-[16px] font-semibold text-white group-hover:underline">{name}</div>
      <p className="text-[13px] leading-relaxed text-zinc-400">{tagline}</p>
      <div className="mt-3 text-[12px] font-semibold" style={{ color: BRAND_COLORS[color] }}>Explore →</div>
    </Link>
  );
}

export default function ModulesPage() {
  return (
    <MarketingShell>
      <PageHero
        eyebrow="Product"
        title="One Platform. Foundation Free, Modules When You're Ready."
        sub="Start on the free Foundation tier, then turn on the paid Modules built for your operation. Every Module runs on the same graph — no integration, no migration, no re-implementation."
        primaryCta={{ href: "/start-free", label: "Start Free" }}
        secondaryCta={{ href: "/pricing", label: "Compare plans" }}
      />

      {/* Foundation */}
      <Section>
        <Link
          href="/modules/foundation"
          className="group block overflow-hidden rounded-2xl border border-emerald-500/30 bg-emerald-500/[0.04] p-6 transition hover:border-emerald-500/60"
        >
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-full bg-emerald-500/15 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">FREE FOREVER · 20 SEATS</span>
            <span className="text-lg font-bold text-white group-hover:underline">{FOUNDATION.name}</span>
          </div>
          <p className="mt-2 max-w-2xl text-[14px] text-zinc-300">{FOUNDATION.tagline}</p>
          <div className="mt-3 text-[12px] font-semibold text-emerald-400">See what&apos;s free →</div>
        </Link>
      </Section>

      {/* Paid Modules */}
      <Section>
        <SectionHeading eyebrow="Paid Modules" title="Add what your operation needs" />
        <div className="mt-8 grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {MODULES.map((m) => (
            <ModuleCard key={m.slug} slug={m.slug} name={m.name} tagline={m.tagline} color={m.color} />
          ))}
        </div>
      </Section>

      {/* AI add-on */}
      <Section>
        <SectionHeading eyebrow="AI, your way" title="Bring your own key, or let us host it" />
        <div className="mt-6 max-w-xl">
          <ModuleCard slug={AI_ADDON.slug} name={AI_ADDON.name} tagline={AI_ADDON.tagline} color={AI_ADDON.color} />
        </div>
      </Section>

      <Section bleed className="border-b-0">
        <div className="text-center">
          <div className="flex flex-wrap items-center justify-center gap-3">
            <CtaLink href="/start-free">Start Free</CtaLink>
            <CtaLink href="/pricing" variant="ghost">See pricing</CtaLink>
            <CtaLink href="/industries" variant="ghost">Find your industry</CtaLink>
          </div>
        </div>
      </Section>
    </MarketingShell>
  );
}
