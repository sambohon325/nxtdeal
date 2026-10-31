"use client";

// Shared chrome + primitives for the dealeros.xyz marketing site (2026-07-19). Sam:
// "lets use the same look and feel of the UX (colors, fonts, etc), but build it out in
// a traditional automotive software feel." Reuses the exact same brand tokens/angled-
// shape primitives every internal NXTDeal page already uses (components/BrandAngles.tsx
// -- the NXTDeal Design Styleguide 2025 rebrand) rather than a separate marketing-site
// design language, per that file's own stated intent ("bold, throughout the app... not
// just the marketing page").
//
// "Traditional automotive software feel" is expressed here as: dense module grids with
// left-edge color-flag cards (the same visual language
// components/DepartmentWorkflowButtons.tsx's job-workflow buttons and this app's
// homepage feature cards already use), spec-sheet-style checklists, comparison tables,
// and arrowed step-flow diagrams -- a DMS main-menu look, not a soft SaaS-startup one.
//
// Every page under app/(marketing routes) composes <MarketingShell> + these primitives;
// none of this reuses the authenticated app's own chrome (BotWidget/HelpWidget/
// KnowledgeBaseWidget/DepartmentMenuBar, etc.) since a visitor here isn't signed in.
import Link from "next/link";
import { BrandLogo } from "@/components/BrandLogo";
import { usePathname } from "next/navigation";
import { Fragment, type ReactNode } from "react";
import { BrandRibbon, AngledGlow, angledClip, BRAND_COLORS, BRAND_RIBBON_ORDER } from "@/components/BrandAngles";
import { LanguageProvider, LanguageToggle } from "@/components/i18n/LanguageProvider";

type NavLink = { href: string; label: string; children?: { href: string; label: string }[] };

// Apps, Marketplace, and NXTDeal Network now live under the Solutions dropdown (Sam, 2026-07-25),
// which also keeps the top bar uncluttered.
const SOLUTIONS_SUBNAV: { href: string; label: string }[] = [
  { href: "/solutions", label: "Platform Overview" },
  { href: "/modules", label: "Modules" },
  { href: "/modules/foundation", label: "Foundation (Free)" },
  { href: "/app-suite", label: "Apps" },
  { href: "/marketplace", label: "Marketplace" },
  { href: "/dealeros-network", label: "NXTDeal Network" },
];

export const MARKETING_NAV_LINKS: NavLink[] = [
  { href: "/", label: "Home" },
  { href: "/solutions", label: "Solutions", children: SOLUTIONS_SUBNAV },
  { href: "/industries", label: "Industries" },
  { href: "/pricing", label: "Pricing" },
  { href: "/company", label: "Company" },
  { href: "/contact", label: "Contact" },
];

// Render a string with the brand word kept in normal case, even inside an uppercase-styled element,
// so "NXTDeal" never renders as "DEALEROS" (Sam: "not DEALEROS cause that just looks like spanish").
// Non-string children pass through untouched.
function brandify(children: ReactNode): ReactNode {
  if (typeof children !== "string" || !children.includes("NXTDeal")) return children;
  return children.split(/(NXTDeal)/g).map((part, i) =>
    part === "NXTDeal" ? (
      <span key={i} className="normal-case">
        NXTDeal
      </span>
    ) : (
      <Fragment key={i}>{part}</Fragment>
    )
  );
}

function CtaLink({
  href,
  children,
  variant = "primary",
  size = "md",
}: {
  href: string;
  children: ReactNode;
  variant?: "primary" | "ghost";
  size?: "sm" | "md";
}) {
  const pad = size === "sm" ? "pl-4 pr-3 py-2 text-[11px]" : "pl-6 pr-5 py-3 text-sm";
  if (variant === "primary") {
    return (
      <Link
        href={href}
        style={angledClip(size === "sm" ? 8 : 12)}
        className={`inline-flex items-center justify-center ${pad} font-brand font-medium tracking-wide brand-cta transition whitespace-nowrap`}
      >
        {brandify(children)}
      </Link>
    );
  }
  return (
    <Link
      href={href}
      style={angledClip(size === "sm" ? 8 : 12)}
      className={`inline-flex items-center justify-center ${pad} font-brand font-medium tracking-wide border border-zinc-700 text-zinc-200 hover:border-brand-teal hover:text-brand-teal transition whitespace-nowrap`}
    >
      {brandify(children)}
    </Link>
  );
}

export function MarketingNav() {
  const pathname = usePathname();

  return (
    <header className="sticky top-0 z-40 bg-brand-ink/95 backdrop-blur-sm border-b border-zinc-900">
      <div className="px-8 py-4 flex items-center gap-8">
        <Link href="/" className="flex items-center gap-3 shrink-0">
          <BrandLogo />
        </Link>

        <nav className="hidden lg:flex items-center gap-1 font-brand">
          {MARKETING_NAV_LINKS.map((link) => {
            const active = link.href === "/" ? pathname === "/" : pathname?.startsWith(link.href);
            const childActive = link.children?.some((c) => pathname?.startsWith(c.href));
            const base =
              active || childActive
                ? "px-3 py-2 text-[11px] font-bold uppercase tracking-wide text-brand-teal"
                : "px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-zinc-400 hover:text-white transition";

            if (link.children) {
              // Hover dropdown (e.g. Solutions → Platform Overview / Apps / Marketplace / NXTDeal Network).
              return (
                <div key={link.href} className="relative group">
                  <Link href={link.href} className={`${base} inline-flex items-center gap-1`}>
                    {brandify(link.label)}
                    <span aria-hidden="true" className="text-[8px] opacity-70">
                      ▾
                    </span>
                  </Link>
                  <div className="absolute left-0 top-full pt-2 hidden group-hover:block z-50">
                    <div className="min-w-[13rem] bg-brand-ink border border-zinc-800 shadow-xl py-1.5">
                      {link.children.map((child) => {
                        const cActive = pathname?.startsWith(child.href);
                        return (
                          <Link
                            key={child.href}
                            href={child.href}
                            className={
                              "block px-4 py-2 text-[11px] font-semibold uppercase tracking-wide transition " +
                              (cActive ? "text-brand-teal" : "text-zinc-400 hover:text-white hover:bg-white/5")
                            }
                          >
                            {brandify(child.label)}
                          </Link>
                        );
                      })}
                    </div>
                  </div>
                </div>
              );
            }

            return (
              <Link key={link.href} href={link.href} className={base}>
                {brandify(link.label)}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-2 shrink-0">
          <LanguageToggle className="hidden sm:inline-flex" />
          <CtaLink href="/start-free" variant="primary" size="sm">
            Start Free
          </CtaLink>
        </div>
      </div>

      <BrandRibbon height={3} />
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer className="border-t border-zinc-900 bg-black/40">
      <div className="px-8 py-12 grid gap-10 md:grid-cols-4">
        <div>
          <div className="flex items-center gap-2 mb-3">
            <BrandLogo />
          </div>
          <p className="text-xs text-zinc-500 leading-relaxed">
            The AI operating system for modern dealerships. One graph. One platform.
            Powered by Chrono.
          </p>
        </div>

        <div>
          <div className="text-[10px] font-brand font-medium tracking-wider text-zinc-500 mb-3">
            Platform
          </div>
          <div className="flex flex-col gap-2 text-xs">
            <Link href="/solutions" className="text-zinc-400 hover:text-white transition">Solutions</Link>
            <Link href="/app-suite" className="text-zinc-400 hover:text-white transition">Apps</Link>
            <Link href="/marketplace" className="text-zinc-400 hover:text-white transition">Marketplace</Link>
            <Link href="/industries" className="text-zinc-400 hover:text-white transition">Industries</Link>
            <Link href="/dealeros-network" className="text-zinc-400 hover:text-white transition">NXTDeal Network</Link>
          </div>
        </div>

        <div>
          <div className="text-[10px] font-brand font-medium tracking-wider text-zinc-500 mb-3">
            Company
          </div>
          <div className="flex flex-col gap-2 text-xs">
            <Link href="/company" className="text-zinc-400 hover:text-white transition">About NXTDeal</Link>
            <Link href="/contact" className="text-zinc-400 hover:text-white transition">Contact</Link>
            <a href="mailto:sambohon325@gmail.com" className="text-zinc-400 hover:text-white transition">
              sambohon325@gmail.com
            </a>
          </div>
        </div>

        <div>
          <div className="text-[10px] font-brand font-medium tracking-wider text-zinc-500 mb-3">
            Get Started
          </div>
          <div className="flex flex-col gap-2">
            <CtaLink href="/solutions" variant="primary" size="sm">Explore the Platform</CtaLink>
            <CtaLink href="/contact" variant="ghost" size="sm">Talk To Us</CtaLink>
          </div>
        </div>
      </div>

      <div className="border-t border-zinc-900 px-8 py-5 flex flex-col sm:flex-row gap-2 items-center justify-between text-[11px] text-zinc-600">
        <div>© 2026 Chronos. All rights reserved.</div>
        <div>Historical Analytics • Predictive Intelligence • Compliance Automation • Industry Benchmarks</div>
      </div>
    </footer>
  );
}

export function MarketingShell({ children }: { children: ReactNode }) {
  return (
    <LanguageProvider>
      <div className="h-full overflow-y-auto bg-brand-ink text-white flex flex-col">
        <MarketingNav />
        <main className="flex-1">{children}</main>
        <MarketingFooter />
      </div>
    </LanguageProvider>
  );
}

// ---------------------------------------------------------------------------
// Shared page primitives
// ---------------------------------------------------------------------------

export function Eyebrow({ children, color = "teal" }: { children: ReactNode; color?: keyof typeof BRAND_COLORS }) {
  return (
    <div className="flex items-center gap-2 mb-4">
      <span className="w-2.5 h-2.5 inline-block" style={{ background: BRAND_COLORS[color], ...angledClip(1) }} />
      <span className="text-[11px] font-brand font-bold uppercase tracking-[0.25em] text-zinc-500">
        {brandify(children)}
      </span>
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  eyebrowColor = "teal",
  title,
  sub,
  align = "left",
}: {
  eyebrow?: string;
  eyebrowColor?: keyof typeof BRAND_COLORS;
  title: ReactNode;
  sub?: ReactNode;
  align?: "left" | "center";
}) {
  return (
    <div className={align === "center" ? "text-center max-w-3xl mx-auto" : "max-w-3xl"}>
      {eyebrow && (
        <div className={align === "center" ? "flex justify-center" : ""}>
          <Eyebrow color={eyebrowColor}>{eyebrow}</Eyebrow>
        </div>
      )}
      <h2 className="text-3xl md:text-4xl font-brand font-bold tracking-tight leading-tight mb-4">
        {title}
      </h2>
      {sub && <p className="text-base text-zinc-400 leading-relaxed">{sub}</p>}
    </div>
  );
}

export function Section({
  children,
  className = "",
  bleed = false,
  id,
}: {
  children: ReactNode;
  className?: string;
  bleed?: boolean;
  id?: string;
}) {
  return (
    <section id={id} className={`relative px-8 py-16 md:py-20 ${bleed ? "" : "border-b border-zinc-900"} ${className}`}>
      <div className="max-w-6xl mx-auto">{children}</div>
    </section>
  );
}

// The left-edge angled color-flag card -- the exact visual language this app's own
// homepage feature cards + DepartmentWorkflowButtons already use, reused here as the
// primary "module tile" building block for a DMS-style feature grid.
export function FlagCard({
  color,
  title,
  children,
  className = "",
}: {
  color: keyof typeof BRAND_COLORS;
  title: ReactNode;
  children?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`relative chrono-surface pl-7 pr-5 py-5 overflow-hidden ${className}`}>
      <span className="nxt-accent absolute left-0 top-0 bottom-0 w-3"
        style={{ background: BRAND_COLORS[color], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
      />
      <div className="font-brand font-medium tracking-wide text-sm mb-1.5">{brandify(title)}</div>
      {children && <div className="text-sm text-zinc-500 leading-relaxed">{children}</div>}
    </div>
  );
}

// A dense DMS-style module grid -- each entry auto-assigned the next color in the
// standard brand ribbon rotation (blue/teal/yellow/red), matching how every internal
// department screen's own 4-button ribbon rotates through the same 4 colors.
export function ModuleGrid({
  items,
  columns = 4,
}: {
  items: { title: string; sub?: string }[];
  columns?: 3 | 4;
}) {
  return (
    <div className={`grid gap-3 ${columns === 3 ? "sm:grid-cols-2 lg:grid-cols-3" : "sm:grid-cols-2 lg:grid-cols-4"}`}>
      {items.map((item, i) => (
        <FlagCard key={item.title} color={BRAND_RIBBON_ORDER[i % BRAND_RIBBON_ORDER.length]} title={item.title}>
          {item.sub}
        </FlagCard>
      ))}
    </div>
  );
}

// A vertical arrowed step-flow -- Sam's own "User opens screen ↓ AI analyzes ↓ ..."
// diagram shorthand, built as a real component so it's reused identically across every
// page's own step diagrams (the Home page funnel, Help Me With This Screen, the AI Demo
// funnel strategy, etc.) rather than re-typed per page.
export function StepFlow({ steps, direction = "vertical" }: { steps: ReactNode[]; direction?: "vertical" | "horizontal" }) {
  if (direction === "horizontal") {
    return (
      <div className="flex flex-wrap items-center justify-center gap-3">
        {steps.map((step, i) => (
          <div key={i} className="flex items-center gap-3">
            <div
              style={angledClip(8)}
              className="bg-zinc-900 border border-zinc-800 px-5 py-3 text-sm font-brand font-semibold text-center"
            >
              {step}
            </div>
            {i < steps.length - 1 && <span className="text-brand-teal text-lg">→</span>}
          </div>
        ))}
      </div>
    );
  }
  return (
    <div className="flex flex-col items-center gap-2 max-w-md mx-auto">
      {steps.map((step, i) => (
        <div key={i} className="w-full flex flex-col items-center gap-2">
          <div
            style={angledClip(8)}
            className="w-full bg-zinc-900 border border-zinc-800 px-5 py-3 text-sm font-brand font-semibold text-center"
          >
            {step}
          </div>
          {i < steps.length - 1 && <span className="text-brand-teal text-lg leading-none">↓</span>}
        </div>
      ))}
    </div>
  );
}

export function CheckItem({ children, locked = false }: { children: ReactNode; locked?: boolean }) {
  return (
    <div className="flex items-start gap-2.5 text-sm">
      <span
        className={
          locked
            ? "shrink-0 mt-0.5 w-4 h-4 flex items-center justify-center text-[10px] font-bold text-zinc-600 border border-zinc-700"
            : "shrink-0 mt-0.5 w-4 h-4 flex items-center justify-center text-[10px] font-bold text-black bg-brand-teal"
        }
        style={angledClip(1.5)}
        aria-hidden="true"
      >
        {locked ? "–" : "✓"}
      </span>
      <span className={locked ? "text-zinc-500" : "text-zinc-200"}>{children}</span>
    </div>
  );
}

export function PageHero({
  eyebrow,
  title,
  sub,
  primaryCta,
  secondaryCta,
}: {
  eyebrow: string;
  title: ReactNode;
  sub: ReactNode;
  primaryCta?: { href: string; label: string };
  secondaryCta?: { href: string; label: string };
}) {
  return (
    <div className="relative overflow-hidden border-b border-zinc-900 px-8 py-20 md:py-28">
      <AngledGlow color="blue" className="absolute -left-32 top-0 w-[420px] h-full" />
      <AngledGlow color="teal" className="absolute right-0 bottom-0 w-[320px] h-2/3" />
      <div className="relative z-10 max-w-4xl mx-auto text-center">
        <Eyebrow color="teal">{eyebrow}</Eyebrow>
        <h1 className="text-4xl md:text-6xl font-brand font-bold tracking-tight leading-tight mb-6">
          {title}
        </h1>
        <p className="text-lg text-zinc-400 mb-10 max-w-2xl mx-auto leading-relaxed">{sub}</p>
        {(primaryCta || secondaryCta) && (
          <div className="flex flex-wrap items-center justify-center gap-3">
            {primaryCta && <CtaLink href={primaryCta.href}>{primaryCta.label}</CtaLink>}
            {secondaryCta && (
              <CtaLink href={secondaryCta.href} variant="ghost">
                {secondaryCta.label}
              </CtaLink>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export { CtaLink };
