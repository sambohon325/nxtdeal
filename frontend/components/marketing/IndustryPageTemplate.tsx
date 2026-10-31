"use client";

// Industry page template (NXTDeal Marketing Site Audit — Industry-First Structure, 2026-08-03).
// Renders any industry from lib/marketing/industries.ts on the NXTDeal "Markets Served" pattern:
// hero → the challenges the segment loses money on → an interactive challenge picker → the NXTDeal
// modules that map to it → a side-by-side competitive comparison → the "three ways in" Network
// framing → a Start Free close. One template, six URLs.

import { useState } from "react";
import Link from "next/link";
import { MarketingShell, Section, Eyebrow, CtaLink } from "@/components/marketing/MarketingChrome";
import { BRAND_COLORS } from "@/components/BrandAngles";
import { type Industry, type Verdict } from "@/lib/marketing/industries";

function VerdictMark({ v, note }: { v: Verdict; note?: string }) {
  const map = {
    yes: { icon: "✓", cls: "text-emerald-400" },
    partial: { icon: "~", cls: "text-amber-400" },
    no: { icon: "✕", cls: "text-zinc-600" },
  }[v];
  return (
    <div>
      <span className={`text-sm font-bold ${map.cls}`}>{map.icon}</span>
      {note && <span className="ml-1.5 text-[11px] text-zinc-500">{note}</span>}
    </div>
  );
}

export function IndustryPageTemplate({ industry }: { industry: Industry }) {
  const accent = BRAND_COLORS[industry.color];
  const [picked, setPicked] = useState(0);

  return (
    <MarketingShell>
      {/* Hero */}
      <div className="relative overflow-hidden border-b border-zinc-900 px-8 py-20 md:py-24">
        <div
          className="pointer-events-none absolute -left-32 top-0 h-full w-[420px] opacity-20 blur-3xl"
          style={{ background: `radial-gradient(circle, ${accent}, transparent 70%)` }}
        />
        <div className="relative z-10 mx-auto max-w-4xl text-center">
          <Eyebrow color={industry.color}>NXTDeal for {industry.eyebrow}</Eyebrow>
          <h1 className="mb-5 mt-2 text-4xl font-brand font-bold leading-tight tracking-tight md:text-5xl">{industry.name}</h1>
          <p className="mx-auto mb-8 max-w-2xl text-lg leading-relaxed text-zinc-400">{industry.tagline}</p>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <CtaLink href="/start-free">Start Free</CtaLink>
            <CtaLink href="#comparison" variant="ghost">See the comparison</CtaLink>
          </div>
        </div>
      </div>

      {/* Challenges */}
      <Section>
        <Eyebrow color={industry.color}>What you&apos;re up against</Eyebrow>
        <h2 className="mb-8 mt-2 text-2xl font-brand font-bold md:text-3xl">The problems this segment actually loses money on</h2>
        <div className="grid gap-4 md:grid-cols-3">
          {industry.challenges.map((c) => (
            <div key={c.title} className="rounded-2xl border border-zinc-800 bg-white/[0.02] p-5">
              <div className="mb-2 h-1 w-10 rounded-full" style={{ background: accent }} />
              <div className="mb-2 text-[15px] font-semibold text-white">{c.title}</div>
              <p className="text-[13px] leading-relaxed text-zinc-400">{c.body}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* Interactive challenge picker */}
      <Section>
        <div className="mx-auto max-w-4xl">
          <Eyebrow color={industry.color}>Pick your problem</Eyebrow>
          <h2 className="mb-6 mt-2 text-2xl font-brand font-bold md:text-3xl">Which one did you come here to solve?</h2>
          <div className="grid gap-4 md:grid-cols-[1fr_1.2fr]">
            <div className="space-y-2">
              {industry.picker.map((p, i) => (
                <button
                  key={i}
                  onClick={() => setPicked(i)}
                  className={`w-full rounded-xl border px-4 py-3 text-left text-[13px] transition ${
                    picked === i ? "border-transparent text-white" : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
                  }`}
                  style={picked === i ? { background: `${accent}22`, borderColor: accent } : undefined}
                >
                  {p.problem}
                </button>
              ))}
            </div>
            <div className="rounded-2xl border border-zinc-800 bg-white/[0.02] p-6">
              <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide" style={{ color: accent }}>
                How NXTDeal solves it
              </div>
              <p className="text-[15px] leading-relaxed text-zinc-200">{industry.picker[picked].answer}</p>
            </div>
          </div>
        </div>
      </Section>

      {/* Module mapping */}
      <Section>
        <Eyebrow color={industry.color}>The modules that map to you</Eyebrow>
        <h2 className="mb-8 mt-2 text-2xl font-brand font-bold md:text-3xl">What you run, on one graph</h2>
        <div className="grid gap-3 md:grid-cols-2">
          {industry.modules.map((m) => (
            <Link
              key={m.dept}
              href={m.href}
              className="group flex items-start gap-3 rounded-2xl border border-zinc-800 bg-white/[0.02] p-4 transition hover:border-zinc-600"
            >
              <div className="mt-1 h-2 w-2 shrink-0 rounded-full" style={{ background: accent }} />
              <div>
                <div className="text-[14px] font-semibold text-white group-hover:underline">{m.dept}</div>
                <p className="mt-0.5 text-[12px] leading-relaxed text-zinc-400">{m.detail}</p>
              </div>
            </Link>
          ))}
        </div>
      </Section>

      {/* Competitive comparison */}
      <Section id="comparison">
        <Eyebrow color={industry.color}>The honest comparison</Eyebrow>
        <h2 className="mb-2 mt-2 text-2xl font-brand font-bold md:text-3xl">How dealers in your segment solve this today</h2>
        <p className="mb-6 max-w-2xl text-[13px] text-zinc-500">{industry.positioning}</p>
        <div className="overflow-x-auto rounded-2xl border border-zinc-800">
          <table className="w-full min-w-[640px] border-collapse text-left">
            <thead>
              <tr className="border-b border-zinc-800 bg-white/[0.03]">
                <th className="px-4 py-3 text-[12px] font-semibold text-zinc-400">Capability</th>
                {industry.comparison.columns.map((col, i) => (
                  <th
                    key={col}
                    className={`px-4 py-3 text-[12px] font-semibold ${i === 0 ? "text-white" : "text-zinc-400"}`}
                    style={i === 0 ? { color: accent } : undefined}
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {industry.comparison.rows.map((row) => (
                <tr key={row.capability} className="border-b border-zinc-900 last:border-0">
                  <td className="px-4 py-3 text-[13px] text-zinc-200">{row.capability}</td>
                  {row.cells.map((cell, i) => (
                    <td key={i} className={`px-4 py-3 ${i === 0 ? "bg-white/[0.02]" : ""}`}>
                      <VerdictMark v={cell.v} note={cell.note} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="mt-3 flex flex-wrap gap-4 text-[11px] text-zinc-500">
          <span><span className="font-bold text-emerald-400">✓</span> Yes</span>
          <span><span className="font-bold text-amber-400">~</span> Partial</span>
          <span><span className="font-bold text-zinc-600">✕</span> No</span>
        </div>
      </Section>

      {/* Three ways in (Network migration framing) */}
      <Section>
        <div className="mx-auto max-w-4xl rounded-2xl border border-zinc-800 bg-white/[0.02] p-6 md:p-8">
          <Eyebrow color={industry.color}>Three ways in</Eyebrow>
          <h2 className="mb-4 mt-2 text-xl font-brand font-bold md:text-2xl">Start free — and upgrading is never a fresh onboarding</h2>
          <div className="grid gap-4 md:grid-cols-3">
            {[
              { t: "NXTDeal Network (free)", d: "Install the free benchmarking extension. The same connection doing the benchmarking is already pulling the data NXTDeal needs to go live." },
              { t: "Foundation (free forever)", d: "Create a free account and start operating: CRM, inventory, communications, reporting, Network, a website — 20 seats, no credit card." },
              { t: "Add Modules", d: "Turn on the paid Modules for your segment when you're ready. Your data is already in — no migration, no re-implementation." },
            ].map((s, i) => (
              <div key={s.t} className="rounded-xl border border-zinc-800 p-4">
                <div className="mb-1 text-[11px] font-bold" style={{ color: accent }}>{i + 1}</div>
                <div className="mb-1 text-[13px] font-semibold text-white">{s.t}</div>
                <p className="text-[12px] leading-relaxed text-zinc-400">{s.d}</p>
              </div>
            ))}
          </div>
        </div>
      </Section>

      {/* Close */}
      <Section bleed className="border-b-0">
        <div className="mx-auto max-w-3xl text-center">
          <h2 className="mb-4 text-2xl font-brand font-bold md:text-3xl">{industry.outcome}</h2>
          <div className="flex flex-wrap items-center justify-center gap-3">
            <CtaLink href="/start-free">Start Free</CtaLink>
            <CtaLink href="/industries" variant="ghost">See other industries</CtaLink>
          </div>
          <p className="mt-4 text-[12px] text-zinc-600">Free forever · 20 seats · no credit card</p>
        </div>
      </Section>
    </MarketingShell>
  );
}
