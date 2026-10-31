"use client";

// NXTDeal Marketplace — marketing page (2026-07-25, Sam: "add in the marketplace, and all that
// that involves"). The Marketplace is NXTDeal's certified app store: apps, integrations, and
// connectors a dealer installs with one click while NXTDeal stays the system of record. Copy is
// drawn from the real product (components/MarketplaceBoard.tsx + core/marketplace.py) — a closed,
// NXTDeal-reviewed catalog with Day-1 integration categories, OEM Programs, and Phase-2 shelves.

import {
  MarketingShell,
  Section,
  SectionHeading,
  PageHero,
  CtaLink,
} from "@/components/marketing/MarketingChrome";
import { AngledGlow, BRAND_COLORS, BRAND_RIBBON_ORDER, angledClip } from "@/components/BrandAngles";

type Cat = { icon: string; name: string; blurb: string };

// The Day-1 integration categories that ship installable now.
const DAY_ONE: Cat[] = [
  { icon: "📞", name: "Communications", blurb: "Voice, SMS, MMS, and video — plus phone migration — powering NXTDeal Connect." },
  { icon: "🪪", name: "Identity & Fraud", blurb: "ID verification, license scanning, and fraud prevention for Digital Retail." },
  { icon: "💳", name: "Finance & Credit", blurb: "Credit aggregation and bureau pulls — required to finance a deal." },
  { icon: "✍️", name: "Electronic Signatures", blurb: "Legally-binding e-sign on any NXTDeal document." },
  { icon: "🗄️", name: "DMS Integrations", blurb: "Connect the DMS you already run for migration and hybrid operation." },
  { icon: "📇", name: "CRM Integrations", blurb: "Bring your existing CRM in — key for Dealer Network adoption." },
  { icon: "🔧", name: "Service Integrations", blurb: "Scheduling, inspection, and shop tools wired to the RO." },
  { icon: "🚗", name: "Inventory & Valuation", blurb: "Market pricing, appraisal, and book values." },
  { icon: "📡", name: "GPS & Starter Interrupt", blurb: "Device integration — critical for BHPH secured lending." },
  { icon: "💵", name: "Payments", blurb: "Deposits, down payments, service, and recurring BHPH collections." },
  { icon: "📣", name: "Advertising", blurb: "Push live inventory and campaigns to the ad platforms." },
  { icon: "⭐", name: "Reputation", blurb: "Reviews and reputation management." },
  { icon: "📊", name: "Accounting", blurb: "General-ledger sync to your accounting system." },
];

// Phase-2 shelves — coming soon, not yet installable.
const COMING_SOON: Cat[] = [
  { icon: "🧠", name: "AI Skills", blurb: "Installable AI modules that plug into the AI Workforce — Sales Coach, Service Coach, F&I Coach, and more." },
  { icon: "🧩", name: "Workflow Packs", blurb: "Process packs by store type and OEM — Ford Service, Toyota Delivery, Luxury, BHPH." },
  { icon: "🎯", name: "Marketing Packs", blurb: "Seasonal campaigns — Truck Month, Tax Season, Lease Pull-Ahead, Private Sale." },
  { icon: "🎨", name: "Website Themes", blurb: "Themes for the built-in NXTDeal website builder." },
  { icon: "🤝", name: "Network Partners", blurb: "“Powered By Dealers” — playbooks, campaigns, and workflows top stores publish anonymously." },
];

function CatCard({ cat, color, soon = false }: { cat: Cat; color: keyof typeof BRAND_COLORS; soon?: boolean }) {
  return (
    <div className="relative bg-zinc-900/70 border border-zinc-800 pl-6 pr-4 py-4 overflow-hidden">
      <span
        className="absolute left-0 top-0 bottom-0 w-2.5"
        style={{ background: BRAND_COLORS[color], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
      />
      <div className="flex items-center gap-2">
        <span className="text-lg" aria-hidden="true">
          {cat.icon}
        </span>
        <span className="font-brand font-bold uppercase tracking-wide text-sm">{cat.name}</span>
        {soon && (
          <span className="ml-auto shrink-0 px-2 py-0.5 text-[9px] font-brand font-bold uppercase tracking-wide bg-white/10 text-zinc-400">
            Soon
          </span>
        )}
      </div>
      <div className="mt-1.5 text-xs text-zinc-500 leading-relaxed">{cat.blurb}</div>
    </div>
  );
}

export default function MarketplaceMarketingPage() {
  return (
    <MarketingShell>
      <PageHero
        eyebrow="NXTDeal Marketplace"
        title="One Click To Connect Everything"
        sub="A certified catalog of apps, integrations, and connectors your dealership installs with one click — while NXTDeal stays the system of record. Every listing is NXTDeal-reviewed, so you're never wiring together a patchwork of vendors on your own."
        primaryCta={{ href: "/solutions", label: "Explore the Platform" }}
        secondaryCta={{ href: "/contact", label: "Talk To Us" }}
      />

      {/* What it is */}
      <Section>
        <div className="grid gap-4 md:grid-cols-3">
          {[
            {
              t: "Certified, not a free-for-all",
              b: "A closed, reviewed catalog — no public plugin dumps, no community uploads. Every listing is reviewed and certified by NXTDeal before it reaches your store.",
            },
            {
              t: "NXTDeal stays the system of record",
              b: "Installing a connector never moves your source of truth. Every record still flows through the single NXTDeal ledger — the connector just feeds it.",
            },
            {
              t: "One click to install",
              b: "Browse the catalog, install what you need, and remove it just as fast. Admins manage installs; every install and removal is written to the audit log.",
            },
          ].map((c, i) => (
            <div key={c.t} className="relative bg-zinc-900/70 border border-zinc-800 p-6 overflow-hidden">
              <span className="absolute left-0 top-0 right-0 h-1.5" style={{ background: Object.values(BRAND_COLORS)[i % 4] }} />
              <div className="font-brand font-bold tracking-tight text-base mb-2">{c.t}</div>
              <p className="text-sm text-zinc-500 leading-relaxed">{c.b}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Day-1 categories */}
      <Section className="bg-zinc-950/40">
        <SectionHeading
          eyebrow="Install Today"
          title="Integration Categories"
          sub="The connectors that ship installable now — the tools that power communications, financing, digital retail, BHPH, and the back office."
        />
        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {DAY_ONE.map((c, i) => (
            <CatCard key={c.name} cat={c} color={BRAND_RIBBON_ORDER[i % BRAND_RIBBON_ORDER.length]} />
          ))}
        </div>
      </Section>

      {/* OEM Programs */}
      <Section>
        <div className="relative overflow-hidden border border-zinc-800 bg-gradient-to-br from-zinc-900/80 to-black/40">
          <AngledGlow color="blue" className="absolute -right-24 top-0 h-full w-[340px]" />
          <div className="relative z-10 p-7 md:p-9">
            <SectionHeading
              eyebrow="OEM Programs"
              title="Built For The Manufacturer Relationship"
              sub="A dedicated area for manufacturer compliance, OEM programs, co-op advertising, and certified data feeds — for Ford, GM, Toyota, Honda, Stellantis, Hyundai, Kia, Nissan, BMW, and Mercedes-Benz."
            />
            <div className="mt-6 flex flex-wrap gap-2.5">
              {["Compliance", "OEM programs", "Co-op advertising", "Certified data feeds"].map((f) => (
                <span
                  key={f}
                  style={angledClip(6)}
                  className="px-4 py-2 bg-zinc-900/80 border border-zinc-800 text-xs font-brand font-semibold"
                >
                  {f}
                </span>
              ))}
            </div>
          </div>
        </div>
      </Section>

      {/* Coming soon / Phase 2 */}
      <Section className="bg-zinc-950/40">
        <SectionHeading
          eyebrow="Coming Soon"
          title="Skills, Packs, Themes & Network Partners"
          sub="The next shelves: installable AI Skills that plug into the AI Workforce, ready-made workflow and marketing packs, website themes, and dealer-published “Powered By Dealers” network partner content."
        />
        <div className="mt-8 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {COMING_SOON.map((c, i) => (
            <CatCard key={c.name} cat={c} color={BRAND_RIBBON_ORDER[i % BRAND_RIBBON_ORDER.length]} soon />
          ))}
        </div>
      </Section>

      <Section bleed className="border-b-0">
        <SectionHeading eyebrow="Ready When You Are" title="Connect Your Whole Stack" align="center" />
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <CtaLink href="/solutions">Explore the Platform</CtaLink>
          <CtaLink href="/solutions" variant="ghost">
            See The Full Platform
          </CtaLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
