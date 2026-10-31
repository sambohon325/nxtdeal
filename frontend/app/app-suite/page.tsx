"use client";

// NXTDeal Apps — the marketing page for the mobile app suite (2026-07-25, Sam: "add in the apps —
// everything that they do, and feature the MySales app (free)"). Lives at /app-suite so it doesn't
// collide with /apps (the live launcher). Data is pulled from lib/apps/registry.ts so the marketing
// copy stays in lockstep with the actual app shells — one source of truth for names, audiences, and
// every screen each app ships.

import {
  MarketingShell,
  Section,
  SectionHeading,
  PageHero,
  CtaLink,
} from "@/components/marketing/MarketingChrome";
import { APP_SUITE, getApp, type AppDef } from "@/lib/apps/registry";
import { AngledGlow, BRAND_COLORS, BRAND_RIBBON_ORDER, angledClip } from "@/components/BrandAngles";

const mysales = getApp("mysales");
const salesApps = APP_SUITE.filter((a) => a.platform === "sales" && a.slug !== "mysales");
const serviceApps = APP_SUITE.filter((a) => a.platform === "service");

function AudienceBadge({ app }: { app: AppDef }) {
  const staff = app.audience === "staff";
  return (
    <span
      className={
        "shrink-0 px-2 py-0.5 text-[9px] font-brand font-bold uppercase tracking-wide " +
        (staff ? "bg-brand-blue/20 text-brand-blue" : "bg-brand-teal/20 text-brand-teal")
      }
      style={angledClip(2)}
    >
      {staff ? "Staff" : "Customer"}
    </span>
  );
}

// One app rendered with everything it does — its summary plus every screen it ships.
function AppBlock({ app, color }: { app: AppDef; color: keyof typeof BRAND_COLORS }) {
  return (
    <div className="relative bg-zinc-900/70 border border-zinc-800 overflow-hidden">
      <span className="absolute left-0 top-0 bottom-0 w-1.5" style={{ background: BRAND_COLORS[color] }} />
      <div className="pl-7 pr-5 py-5">
        <div className="flex items-center gap-2.5">
          <span className="text-2xl" aria-hidden="true">
            {app.icon}
          </span>
          <h3 className="text-lg font-brand font-bold tracking-tight">{app.name}</h3>
          <AudienceBadge app={app} />
        </div>
        <div className="mt-0.5 text-[11px] font-brand font-semibold uppercase tracking-wide text-zinc-500">
          {app.tagline}
        </div>
        <p className="mt-2 text-sm text-zinc-400 leading-relaxed">{app.summary}</p>

        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          {app.screens.map((s) => (
            <div key={s.key} className="border border-zinc-800/80 bg-black/20 px-3 py-2">
              <div className="flex items-center gap-1.5 text-[13px] font-brand font-semibold text-zinc-200">
                <span aria-hidden="true">{s.icon}</span>
                {s.label}
              </div>
              <div className="mt-0.5 text-[11px] text-zinc-500 leading-snug">{s.intro}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default function AppSuiteMarketingPage() {
  return (
    <MarketingShell>
      <PageHero
        eyebrow="NXTDeal Apps"
        title="An App For Every Role"
        sub="A suite of tablet-first apps — for salespeople, the front desk, service advisors, technicians, and your customers — all synced to your dealership's single NXTDeal ledger. Installable to iOS and Google Play as native wrappers over the same code."
        primaryCta={{ href: "/solutions", label: "Explore the Platform" }}
        secondaryCta={{ href: "/contact", label: "Talk To Us" }}
      />

      {/* Featured: MySales — the free rep app */}
      {mysales && (
        <Section>
          <div className="relative overflow-hidden border border-brand-teal/30 bg-gradient-to-br from-zinc-900/80 to-black/40">
            <AngledGlow color="teal" className="absolute -right-24 top-0 h-full w-[360px]" />
            <div className="relative z-10 p-7 md:p-9">
              <div className="flex flex-wrap items-center gap-3">
                <span className="text-3xl" aria-hidden="true">
                  {mysales.icon}
                </span>
                <h2 className="text-2xl md:text-3xl font-brand font-bold tracking-tight">MySales</h2>
                <span
                  className="px-2.5 py-1 text-[11px] font-brand font-bold uppercase tracking-wide bg-brand-teal text-black"
                  style={angledClip(3)}
                >
                  Free
                </span>
              </div>
              <p className="mt-3 max-w-2xl text-base text-zinc-300 leading-relaxed">
                The free app every salesperson can carry from store to store. A personal brand page, ranked
                lead follow-up, live inventory to build a deal from anywhere, and an AI coach that travels
                with the rep — plus referral rewards and a light money app with budgets and an AI advisor.
              </p>

              <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {mysales.screens.map((s, i) => (
                  <div
                    key={s.key}
                    className="relative bg-zinc-900/80 border border-zinc-800 pl-6 pr-4 py-4 overflow-hidden"
                  >
                    <span
                      className="absolute left-0 top-0 bottom-0 w-2.5"
                      style={{
                        background: BRAND_COLORS[BRAND_RIBBON_ORDER[i % BRAND_RIBBON_ORDER.length]],
                        clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)",
                      }}
                    />
                    <div className="flex items-center gap-1.5 text-sm font-brand font-bold">
                      <span aria-hidden="true">{s.icon}</span>
                      {s.heading}
                    </div>
                    <div className="mt-1 text-xs text-zinc-500 leading-relaxed">{s.intro}</div>
                  </div>
                ))}
              </div>

              <div className="mt-7">
                <CtaLink href="/contact">Get MySales Free</CtaLink>
              </div>
            </div>
          </div>
        </Section>
      )}

      {/* Sales Platform */}
      <Section className="bg-zinc-950/40">
        <SectionHeading
          eyebrow="Sales Platform"
          title="The Sales Floor, Mobile"
          sub="The dealer-managed sales apps — shared pipeline and the up system, the front desk, and a customer showroom — every one writing to the same deal room."
        />
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          {salesApps.map((app, i) => (
            <AppBlock key={app.slug} app={app} color={BRAND_RIBBON_ORDER[i % BRAND_RIBBON_ORDER.length]} />
          ))}
        </div>
      </Section>

      {/* Service Experience Platform */}
      <Section>
        <SectionHeading
          eyebrow="Service Experience Platform"
          title="From The Service Drive To The Couch"
          sub="Your customers request service and track their car live, and your advisors, technicians, and managers run the shop from a tablet — all on one ledger."
        />
        <div className="mt-8 grid gap-4 lg:grid-cols-2">
          {serviceApps.map((app, i) => (
            <AppBlock key={app.slug} app={app} color={BRAND_RIBBON_ORDER[(i + 1) % BRAND_RIBBON_ORDER.length]} />
          ))}
        </div>
      </Section>

      <Section bleed className="border-b-0">
        <SectionHeading eyebrow="Ready When You Are" title="Put The Whole Store In Their Pocket" align="center" />
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
