"use client";

// Contact page (2026-07-19) -- named on the nav bar and as the funnel's final "Contact /
// Buy" step in Sam's spec, no explicit content given. Built as a real, working contact
// path (mailto, since there's no public-facing lead-capture backend on the marketing
// site itself) rather than a fake form that goes nowhere.
import {
  MarketingShell,
  Section,
  SectionHeading,
  PageHero,
  CtaLink,
} from "@/components/marketing/MarketingChrome";
import { angledClip } from "@/components/BrandAngles";

const REASONS: { title: string; subject: string }[] = [
  { title: "Schedule A Live Demo", subject: "Schedule A NXTDeal Demo" },
  { title: "Request Pricing", subject: "NXTDeal Pricing Request" },
  { title: "Ask About NXTDeal Network", subject: "NXTDeal Network Question" },
  { title: "Something Else", subject: "NXTDeal Inquiry" },
];

export default function ContactPage() {
  return (
    <MarketingShell>
      <PageHero
        eyebrow="Contact"
        title="Let's Talk"
        sub="Whether you're ready to switch or just curious what a graph-native dealership platform actually looks like, we're happy to walk through it."
      />

      <Section>
        <SectionHeading eyebrow="Reach Us" title="Pick What You're Here For" />
        <div className="mt-10 grid gap-4 sm:grid-cols-2">
          {REASONS.map((r) => (
            <a
              key={r.title}
              href={`mailto:sambohon325@gmail.com?subject=${encodeURIComponent(r.subject)}`}
              className="relative bg-zinc-900/80 border border-zinc-800 hover:border-brand-teal/50 pl-7 pr-5 py-5 overflow-hidden transition group"
            >
              <span
                className="absolute left-0 top-0 bottom-0 w-3 bg-brand-teal opacity-70 group-hover:opacity-100"
                style={{ clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
              />
              <div className="font-brand font-bold text-sm">{r.title}</div>
              <div className="text-xs text-zinc-500 mt-1">sambohon325@gmail.com</div>
            </a>
          ))}
        </div>
      </Section>

      <Section className="bg-zinc-950/40" bleed>
        <SectionHeading
          eyebrow="Not Ready To Talk Yet?"
          title="Try It Yourself First"
          sub="Explore the platform or review NXTDeal Network Free before contacting our team."
          align="center"
        />
        <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
          <a
            href="mailto:sambohon325@gmail.com?subject=Schedule%20A%20NXTDeal%20Demo"
            style={angledClip(12)}
            className="inline-flex items-center justify-center pl-6 pr-5 py-3 text-sm font-brand font-bold uppercase tracking-wide bg-brand-blue text-white hover:bg-[#3579c2] transition"
          >
            Email Us Directly
          </a>
          <CtaLink href="/solutions" variant="ghost">Explore the Platform</CtaLink>
          <CtaLink href="/dealeros-network" variant="ghost">Install Network Free</CtaLink>
        </div>
      </Section>
    </MarketingShell>
  );
}
