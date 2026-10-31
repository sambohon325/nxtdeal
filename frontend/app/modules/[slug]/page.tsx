"use client";

// Per-Module product page (NXTDeal Marketing Site Audit — new Modules/Product pages, 2026-08-03).
// /modules/<slug> resolves one Module (Foundation, a paid Module, or the NXTDeal AI add-on) from
// lib/marketing/modules.ts and renders it through the shared ModulePageTemplate — breaking the old
// single long /solutions page into individually linkable pages.

import { useParams } from "next/navigation";
import Link from "next/link";
import { MarketingShell, Section } from "@/components/marketing/MarketingChrome";
import { ModulePageTemplate } from "@/components/marketing/ModulePageTemplate";
import { getModule } from "@/lib/marketing/modules";

export default function ModulePage() {
  const params = useParams<{ slug: string }>();
  const slug = Array.isArray(params.slug) ? params.slug[0] : params.slug;
  const module = slug ? getModule(slug) : undefined;

  if (!module) {
    return (
      <MarketingShell>
        <Section>
          <div className="mx-auto max-w-xl py-16 text-center">
            <h1 className="text-2xl font-brand font-bold">Module not found</h1>
            <p className="mt-2 text-zinc-400">We don&apos;t have a page for “{slug}”.</p>
            <Link href="/modules" className="mt-4 inline-block text-sm font-medium text-[var(--brand-teal,#3FBCC4)]">
              ‹ See all Modules
            </Link>
          </div>
        </Section>
      </MarketingShell>
    );
  }

  return <ModulePageTemplate module={module} />;
}
