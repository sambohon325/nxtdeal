"use client";

// NXTDeal Network page (2026-07-19) -- a full funnel by itself per Sam's spec. Route is
// /dealeros-network rather than /network: this same codebase's tenant deployments
// already use /network for the real, authenticated, in-app Network department dashboard
// (app/network/page.tsx) -- reusing that path here would collide with it.
//
// "Install NXTDeal Network Free" points at this page's own #install section rather
// than a Chrome Web Store listing -- the real extension (network-connect-extension/) is
// a no-build-step "Load unpacked" install today, not yet published to a store, so this
// states the real install path rather than a link that doesn't exist yet.
import {
  MarketingShell,
  Section,
  SectionHeading,
  PageHero,
  CheckItem,
  StepFlow,
  CtaLink,
  Eyebrow,
} from "@/components/marketing/MarketingChrome";
import { angledClip } from "@/components/BrandAngles";

export default function DealerOSNetworkPage() {
  return (
    <MarketingShell>
      <PageHero
        eyebrow="NXTDeal Network"
        title="The Free AI-Powered Dealer Network"
        sub="See how your dealership compares to thousands of others -- without replacing a single system you already run."
        primaryCta={{ href: "#install", label: "Install NXTDeal Network Free" }}
        secondaryCta={{ href: "/solutions", label: "Explore the Platform" }}
      />

      {/* Free / Premium / Full NXTDeal comparison */}
      <Section>
        <SectionHeading eyebrow="Three Ways In" title="Start Free. Upgrade When You're Ready." align="center" />

        <div className="mt-10 grid gap-5 lg:grid-cols-3">
          {/* Free */}
          <div className="relative bg-zinc-900/80 border border-zinc-800 p-6 flex flex-col">
            <div className="text-[11px] font-brand font-bold uppercase tracking-wider text-brand-teal mb-1">
              Free
            </div>
            <div className="text-xl font-brand font-bold mb-1">NXTDeal Network Connect</div>
            <div className="text-xs text-zinc-500 mb-5">Chrome Extension • Edge Extension</div>

            <div className="text-[10px] font-brand font-bold uppercase tracking-wider text-zinc-500 mb-2">
              Includes
            </div>
            <div className="flex flex-col gap-2 mb-5">
              <CheckItem>Benchmarking</CheckItem>
              <CheckItem>Industry Rankings</CheckItem>
              <CheckItem>AI Insights</CheckItem>
              <CheckItem>Opportunity Tracking</CheckItem>
              <CheckItem>Basic Performance Reports</CheckItem>
              <CheckItem>Peer Group Comparisons</CheckItem>
            </div>

            <div className="text-[10px] font-brand font-bold uppercase tracking-wider text-zinc-500 mb-2">
              Does Not Include
            </div>
            <div className="flex flex-col gap-2 mb-6">
              <CheckItem locked>Detailed Playbooks</CheckItem>
              <CheckItem locked>Full Forecasting</CheckItem>
              <CheckItem locked>Automation</CheckItem>
              <CheckItem locked>AI Workforce</CheckItem>
              <CheckItem locked>Operational Execution</CheckItem>
            </div>

            <div className="mt-auto">
              <CtaLink href="#install">Install Free</CtaLink>
            </div>
          </div>

          {/* Premium */}
          <div className="relative bg-zinc-900/80 border border-brand-teal/40 p-6 flex flex-col">
            <span className="absolute top-0 left-0 right-0 h-1.5 bg-brand-teal" />
            <div className="text-[11px] font-brand font-bold uppercase tracking-wider text-brand-teal mb-1 mt-1.5">
              Premium
            </div>
            <div className="text-xl font-brand font-bold mb-1">Premium Network</div>
            <div className="text-xs text-zinc-500 mb-5">Everything in Free, plus:</div>

            <div className="flex flex-col gap-2 mb-6">
              <CheckItem>Forecasting</CheckItem>
              <CheckItem>Playbooks</CheckItem>
              <CheckItem>Advanced Analytics</CheckItem>
              <CheckItem>AI Advisors</CheckItem>
              <CheckItem>Gap Analysis</CheckItem>
              <CheckItem>Opportunity Modeling</CheckItem>
            </div>

            <div className="mt-auto">
              <CtaLink href="/contact">Talk To Us</CtaLink>
            </div>
          </div>

          {/* Full NXTDeal */}
          <div className="relative bg-zinc-900/80 border border-zinc-800 p-6 flex flex-col">
            <div className="text-[11px] font-brand font-bold uppercase tracking-wider text-zinc-500 mb-1">
              Full Platform
            </div>
            <div className="text-xl font-brand font-bold mb-1">Full NXTDeal</div>
            <div className="text-xs text-zinc-500 mb-5">Network + Execution.</div>

            <div className="flex flex-col gap-2 mb-6">
              <CheckItem>Everything in Premium Network</CheckItem>
              <CheckItem>Every department module</CheckItem>
              <CheckItem>The full AI Workforce</CheckItem>
              <CheckItem>Real operational execution, not just insight</CheckItem>
            </div>

            <div className="mt-auto">
              <CtaLink href="/solutions">See Full NXTDeal</CtaLink>
            </div>
          </div>
        </div>
      </Section>

      {/* Why It's Free */}
      <Section className="bg-zinc-950/40">
        <SectionHeading eyebrow="Why It's Free" title="The Network Gets Smarter As It Grows" align="center" />
        <div className="mt-10">
          <StepFlow
            direction="horizontal"
            steps={[
              "Participating dealers contribute anonymous KPI snapshots",
              "The network learns from the data",
              "Everyone benefits",
            ]}
          />
        </div>
      </Section>

      {/* Security */}
      <Section>
        <SectionHeading eyebrow="Security" title="Blind Performance Data Only" sub="NXTDeal knows how you're performing. NXTDeal never knows whose data it is." />
        <div className="mt-8 grid gap-3 sm:grid-cols-2 max-w-2xl">
          <CheckItem>No customer information</CheckItem>
          <CheckItem>No employee identification</CheckItem>
          <CheckItem>No dealer identification</CheckItem>
          <CheckItem>Blind performance data only</CheckItem>
        </div>
      </Section>

      {/* Install */}
      <Section id="install" bleed className="border-b-0">
        <SectionHeading eyebrow="Get Started" title="Install NXTDeal Network Free" align="center" />
        <div className="mt-10 max-w-xl mx-auto">
          <StepFlow
            steps={[
              "Download the NXTDeal Network Connect extension",
              "Open chrome://extensions (or edge://extensions)",
              "Enable Developer Mode",
              "Load Unpacked",
              "Sign up with your company name and email",
            ]}
          />
        </div>
        <div className="mt-10 text-center">
          <a
            href="mailto:sambohon325@gmail.com?subject=NXTDeal%20Network%20Connect%20Extension"
            style={angledClip(12)}
            className="inline-flex items-center justify-center pl-6 pr-5 py-3 text-sm font-brand font-bold uppercase tracking-wide bg-brand-blue text-white hover:bg-[#3579c2] transition"
          >
            Request The Extension
          </a>
          <p className="mt-4 text-xs text-zinc-500">
            No credit card. No CRM integration required. Just a company name and email.
          </p>
        </div>
      </Section>
    </MarketingShell>
  );
}
