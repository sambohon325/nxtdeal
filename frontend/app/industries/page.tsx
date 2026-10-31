"use client";

// Industries index (rebuilt 2026-08-03 for the Industry-First structure). Was a flat page of
// "Supports" tag lists; now each tile is a real link to that industry's own page
// (/industries/<slug>) built on the competitive template. Data is the shared
// lib/marketing/industries.ts so the index and the pages never drift.

import Link from "next/link";
import { MarketingShell, Section, SectionHeading, PageHero, CtaLink } from "@/components/marketing/MarketingChrome";
import { BRAND_COLORS } from "@/components/BrandAngles";
import { industriesInOrder } from "@/lib/marketing/industries";

export default function IndustriesPage() {
  const industries = industriesInOrder();
  return (
    <MarketingShell>
      <PageHero
        eyebrow="Industries"
        title="Built For How Your Business Actually Runs"
        sub="Franchise. Independent. Buy-Here-Pay-Here. Finance companies. Dealer groups. Service-only shops. One graph-native platform — each page below shows the challenges your segment loses money on, the modules that solve them, and an honest comparison to what you use today."
        primaryCta={{ href: "/start-free", label: "Start Free" }}
        secondaryCta={{ href: "/solutions", label: "See All Solutions" }}
      />

      <Section>
        <div className="grid gap-5 md:grid-cols-2">
          {industries.map((ind) => (
            <Link
              key={ind.slug}
              href={`/industries/${ind.slug}`}
              className="group relative overflow-hidden border border-zinc-800 bg-zinc-900/80 transition hover:border-zinc-600"
            >
              <span className="absolute bottom-0 left-0 top-0 w-3" style={{ background: BRAND_COLORS[ind.color] }} />
              <div className="py-6 pl-8 pr-6">
                <div className="mb-2 text-xl font-brand font-bold tracking-tight group-hover:underline">{ind.name}</div>
                <p className="mb-4 text-[13px] leading-relaxed text-zinc-400 line-clamp-3">{ind.tagline}</p>
                <div className="flex flex-wrap gap-1.5">
                  {ind.comparison.columns.slice(1).map((c) => (
                    <span key={c} className="rounded-full bg-white/5 px-2 py-0.5 text-[10px] text-zinc-500">vs {c}</span>
                  ))}
                </div>
                <div className="mt-4 text-[12px] font-semibold" style={{ color: BRAND_COLORS[ind.color] }}>
                  See how NXTDeal fits →
                </div>
              </div>
            </Link>
          ))}
        </div>
      </Section>

      <Section bleed className="border-b-0">
        <SectionHeading
          eyebrow="Next Step"
          title="Start free, in your industry"
          sub="Every industry above runs on the same core platform — Foundation is free forever, and you add the Modules built for your operation when you're ready."
          align="center"
        />
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <CtaLink href="/start-free">Start Free</CtaLink>
          <CtaLink href="/solutions" variant="ghost">Explore the Platform</CtaLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
