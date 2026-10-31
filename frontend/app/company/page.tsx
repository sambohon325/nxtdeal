"use client";

// Company page (2026-07-19) -- named on the nav bar in Sam's spec, no explicit content
// given. Built as a short "about the platform / who's behind it" page, consistent in
// tone with the rest of the marketing site rather than left unbuilt.
import {
  MarketingShell,
  Section,
  SectionHeading,
  PageHero,
  FlagCard,
  CtaLink,
} from "@/components/marketing/MarketingChrome";

const PRINCIPLES: { title: string; body: string }[] = [
  {
    title: "One Graph, Not Fifteen Systems",
    body: "Every entity -- customer, vehicle, lead, deal, document -- lives once, in one shared graph. Departments read and write the same source of truth instead of syncing copies between disconnected modules.",
  },
  {
    title: "Real Data Or An Honest Gap",
    body: "When a figure can't be computed from real data, NXTDeal says so plainly rather than fabricating a number that looks precise. Simulated figures are always labeled as simulated.",
  },
  {
    title: "AI That Does Work, Not Just Chat",
    body: "The AI Workforce doesn't just answer questions -- it analyzes screens, suggests actions, automates the safe ones, and covers for absent employees under real, reviewable guardrails.",
  },
];

export default function CompanyPage() {
  return (
    <MarketingShell>
      <PageHero
        eyebrow="Company"
        title="NXTDeal | Powered by Chrono"
        sub="NXTDeal is a connected dealership operating system -- built to replace a stack of disconnected CRM, DMS, Finance, and Marketing tools with one shared platform."
      />

      <Section>
        <SectionHeading eyebrow="What We Believe" title="A Different Foundation" />
        <div className="mt-10 grid gap-4 md:grid-cols-3">
          {PRINCIPLES.map((p, i) => (
            <FlagCard key={p.title} color={(["blue", "teal", "yellow"] as const)[i % 3]} title={p.title}>
              {p.body}
            </FlagCard>
          ))}
        </div>
      </Section>

      <Section className="bg-zinc-950/40">
        <SectionHeading eyebrow="The Product Family" title="One Ecosystem, Three Doors In" />
        <div className="mt-10 grid gap-4 sm:grid-cols-3 text-sm">
          <div className="bg-zinc-900/80 border border-zinc-800 p-6">
            <div className="font-brand font-bold text-base mb-2">NXTDeal Network</div>
            <div className="text-zinc-500">Free, anonymous benchmarking. The on-ramp for any dealership.</div>
          </div>
          <div className="bg-zinc-900/80 border border-zinc-800 p-6">
            <div className="font-brand font-bold text-base mb-2">NXTDeal</div>
            <div className="text-zinc-500">The full operating platform -- Sales, Service, Inventory, Marketing, Finance, Operations, and the AI Workforce.</div>
          </div>
          <div className="bg-zinc-900/80 border border-zinc-800 p-6">
            <div className="font-brand font-bold text-base mb-2">NXTDeal Hub</div>
            <div className="text-zinc-500">The internal control center NXTDeal uses to provision, monitor, and support every dealer on the platform.</div>
          </div>
        </div>
      </Section>

      <Section bleed className="border-b-0">
        <SectionHeading eyebrow="Get In Touch" title="Let's Talk About Your Dealership" align="center" />
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <CtaLink href="/solutions">Explore the Platform</CtaLink>
          <CtaLink href="/contact" variant="ghost">Contact Us</CtaLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
