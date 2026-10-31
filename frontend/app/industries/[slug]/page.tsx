"use client";

// Per-industry marketing page (NXTDeal Marketing Site Audit — Industry-First Structure, 2026-08-03).
// /industries/<slug> resolves one industry from lib/marketing/industries.ts and renders it through the
// shared IndustryPageTemplate. Each industry now has its own URL — independently linkable in a sales
// email, an ad, or a search result the way a flat /industries page never could be.

import { useParams } from "next/navigation";
import Link from "next/link";
import { MarketingShell, Section } from "@/components/marketing/MarketingChrome";
import { IndustryPageTemplate } from "@/components/marketing/IndustryPageTemplate";
import { getIndustry } from "@/lib/marketing/industries";

export default function IndustryPage() {
  const params = useParams<{ slug: string }>();
  const slug = Array.isArray(params.slug) ? params.slug[0] : params.slug;
  const industry = slug ? getIndustry(slug) : undefined;

  if (!industry) {
    return (
      <MarketingShell>
        <Section>
          <div className="mx-auto max-w-xl py-16 text-center">
            <h1 className="text-2xl font-brand font-bold">Industry not found</h1>
            <p className="mt-2 text-zinc-400">We don&apos;t have a page for “{slug}”.</p>
            <Link href="/industries" className="mt-4 inline-block text-sm font-medium text-[var(--brand-teal,#3FBCC4)]">
              ‹ See all industries
            </Link>
          </div>
        </Section>
      </MarketingShell>
    );
  }

  return <IndustryPageTemplate industry={industry} />;
}
