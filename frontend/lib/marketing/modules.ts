// Module / product marketing content (NXTDeal Marketing Site Audit — new Modules/Product pages,
// 2026-08-03). The audit calls for breaking the single long /solutions page into one page per
// Module, mirroring the Freemium Feature List's Foundation + paid Modules + NXTDeal AI add-on. This
// is the content behind each page. It mirrors core/entitlements.py's MODULE_CATALOG (same features,
// same free/professional/enterprise levels) so the marketing site and the product's real entitlement
// enforcement never tell different stories.
//
// Pricing note: no dollar amounts are invented. NXTDeal's own principle is "real data or an honest
// gap, never a fabricated precise number." Tiers show what's included + seat counts; the actual price
// is set at signup / by conversation, surfaced as "Start Free" + "Talk to us" rather than a fake $.

import { type BrandColor } from "@/lib/marketing/industries";

export type FeatureLevel = "free" | "professional" | "enterprise";

export type ModuleTier = {
  name: string;         // Foundation | Starter | Pro
  seats: string;        // "20 seats" | "1 seat" | "5+ seats"
  blurb: string;
  includes: string[];   // headline features at this tier
  cta: { label: string; href: string };
};

export type MarketingModule = {
  slug: string;
  name: string;
  category: "foundation" | "module" | "add_on";
  color: BrandColor;
  eyebrow: string;
  tagline: string;
  intro: string;
  features: { name: string; level: FeatureLevel }[];
  tiers: ModuleTier[];
};

const START_FREE = { label: "Start Free", href: "/start-free" };
const UPGRADE = (name: string) => ({ label: `Start Free, upgrade to ${name}`, href: "/start-free" });

export const FOUNDATION: MarketingModule = {
  slug: "foundation",
  name: "NXTDeal Foundation",
  category: "foundation",
  color: "teal",
  eyebrow: "Free Forever",
  tagline: "Your dealership's data, live in NXTDeal from day one — free forever, up to 20 seats.",
  intro:
    "Foundation is the free base every dealer starts on. Put your contacts, inventory, and reporting in for free, run the business, and add paid Modules only when you're ready. No credit card, no sales call.",
  features: [
    { name: "Basic CRM — contacts, customers, vehicles, opportunities, tasks, activity tracking", level: "free" },
    { name: "Basic Inventory — upload, VIN decode, search, vehicle storage", level: "free" },
    { name: "Basic Communications — email + SMS logging, contact history", level: "free" },
    { name: "Basic Reporting — inventory, leads, sales activity, service activity", level: "free" },
    { name: "NXTDeal Network — benchmarking, peer comparison, performance scores, opportunity highlights", level: "free" },
    { name: "Basic Website — inventory site, contact forms, basic SEO, mobile responsive", level: "free" },
    { name: "Workforce AI Viewer — see AI recommendations (execution unlocks with a Module)", level: "free" },
  ],
  tiers: [
    {
      name: "Foundation",
      seats: "Up to 20 seats",
      blurb: "Free forever. Everything above, for your whole team.",
      includes: ["Everything listed above", "20 free seats", "No credit card"],
      cta: START_FREE,
    },
  ],
};

// The eight paid Modules. Professional-level features map to the Starter tier; enterprise-level
// features map to the Pro tier (Pro includes everything in Starter).
export const MODULES: MarketingModule[] = [
  {
    slug: "sales",
    name: "Sales Module",
    category: "module",
    color: "blue",
    eyebrow: "Sales",
    tagline: "Turn the free CRM pipeline into a closing machine.",
    intro: "Foundation gives you the pipeline; the Sales Module gives you the desk. Build and price deals, evaluate trades, route manager T.O.s, run your up-rotation, and take the whole thing online with Digital Retail.",
    features: [
      { name: "Appointments", level: "professional" },
      { name: "Desking (deal builder + scenarios)", level: "professional" },
      { name: "Trade Evaluation", level: "professional" },
      { name: "Manager approval routing", level: "professional" },
      { name: "Up-rotation system", level: "professional" },
      { name: "Digital Retail (Start Your Deal Online)", level: "professional" },
      { name: "AI Sales Agents", level: "enterprise" },
    ],
    tiers: [],
  },
  {
    slug: "service",
    name: "Service Module",
    category: "module",
    color: "teal",
    eyebrow: "Service",
    tagline: "Run the shop: repair orders, inspections, parts, and the floor.",
    intro: "Everything the service drive needs on the same graph as sales and inventory — so a repair order can become a trade, and a delinquency can inform recon.",
    features: [
      { name: "Repair Orders", level: "professional" },
      { name: "Digital Vehicle Inspections", level: "professional" },
      { name: "Parts", level: "professional" },
      { name: "Warranty", level: "professional" },
      { name: "Shop Control", level: "enterprise" },
    ],
    tiers: [],
  },
  {
    slug: "marketing",
    name: "Marketing Module",
    category: "module",
    color: "yellow",
    eyebrow: "Marketing",
    tagline: "From the free inventory site to a full marketing engine.",
    intro: "Foundation ships a basic website; the Marketing Module adds the Website Studio builder, email/SMS campaigns, PURLs, events, advertising, and an AI Marketing Agent.",
    features: [
      { name: "Website Studio (builder)", level: "professional" },
      { name: "Email Marketing", level: "professional" },
      { name: "SMS Marketing", level: "professional" },
      { name: "PURLs", level: "professional" },
      { name: "Events", level: "enterprise" },
      { name: "Advertising", level: "enterprise" },
      { name: "AI Marketing Agent", level: "enterprise" },
    ],
    tiers: [],
  },
  {
    slug: "finance",
    name: "Finance Module",
    category: "module",
    color: "red",
    eyebrow: "Finance & F&I",
    tagline: "Contracting through funding — plus BHPH, collections, and payments.",
    intro: "The full F&I engine: structure deals, submit to lenders, fund, and — for stores carrying their own paper — run the portfolio, collections, GPS/starter-interrupt, and BHPH on the same graph.",
    features: [
      { name: "Contracting", level: "professional" },
      { name: "Funding", level: "professional" },
      { name: "Lenders", level: "professional" },
      { name: "F&I Products", level: "professional" },
      { name: "Payments", level: "professional" },
      { name: "Collections", level: "professional" },
      { name: "GPS / Starter Interrupt", level: "enterprise" },
      { name: "Buy-Here-Pay-Here", level: "enterprise" },
    ],
    tiers: [],
  },
  {
    slug: "operations",
    name: "Operations Module",
    category: "module",
    color: "blue",
    eyebrow: "Operations",
    tagline: "Recon, compliance, delivery, and task management.",
    intro: "The day-to-day command center — reconditioning, compliance scanning, delivery coordination, and cross-department task management.",
    features: [
      { name: "Recon", level: "professional" },
      { name: "Compliance", level: "professional" },
      { name: "Delivery", level: "professional" },
      { name: "Task Management", level: "professional" },
    ],
    tiers: [],
  },
  {
    slug: "ai-workforce",
    name: "AI Workforce Module",
    category: "module",
    color: "teal",
    eyebrow: "AI Workforce",
    tagline: "Let the Workforce AI Viewer's recommendations actually execute.",
    intro: "Foundation shows you what the AI recommends; the AI Workforce Module lets it act — coaching, coverage, screen assistance, and autonomous AI workers, with your choice of AI provider.",
    features: [
      { name: "AI Coaching", level: "professional" },
      { name: "AI Coverage", level: "professional" },
      { name: "AI Screen Assistance", level: "professional" },
      { name: "AI Workers", level: "enterprise" },
    ],
    tiers: [],
  },
  {
    slug: "connect",
    name: "Connect Module",
    category: "module",
    color: "yellow",
    eyebrow: "Connect",
    tagline: "Phone, SMS, chat, recording, and conversation intelligence.",
    intro: "The unified customer-engagement layer — one inbox across phone, SMS, and chat, with recording, transcripts, and conversation intelligence.",
    features: [
      { name: "Phone", level: "professional" },
      { name: "SMS", level: "professional" },
      { name: "Chat", level: "professional" },
      { name: "Recording", level: "professional" },
      { name: "Transcripts", level: "enterprise" },
      { name: "Conversation Intelligence", level: "enterprise" },
    ],
    tiers: [],
  },
  {
    slug: "network-premium",
    name: "Network Premium Module",
    category: "module",
    color: "red",
    eyebrow: "Network Premium",
    tagline: "Upgrade the free Network hook into forecasting and advisory intelligence.",
    intro: "Foundation's Network gives you benchmarking; Network Premium adds forecasting, AI advisors, playbooks, gap analysis, and executive insights — the enterprise layer for groups.",
    features: [
      { name: "Forecasting", level: "professional" },
      { name: "AI Advisors", level: "professional" },
      { name: "Playbooks", level: "professional" },
      { name: "Gap Analysis", level: "enterprise" },
      { name: "Executive Insights", level: "enterprise" },
    ],
    tiers: [],
  },
];

// The NXTDeal AI add-on — usage-billed managed inference, separate from the feature Modules.
export const DEALEROS_AI: MarketingModule = {
  slug: "dealeros-ai",
  name: "NXTDeal AI",
  category: "add_on",
  color: "teal",
  eyebrow: "AI Add-On",
  tagline: "Our hosted AI, billed by usage — zero setup, no key to manage.",
  intro:
    "NXTDeal is model-agnostic. Bring your own OpenAI, Anthropic, or Gemini key at any tier for free, point us at your own homegrown endpoint, or turn on NXTDeal AI — our hosted inference, billed by usage, with nothing to configure. Not available on the free tier.",
  features: [
    { name: "Managed AI inference (no key to manage)", level: "professional" },
    { name: "Usage-based billing — pay for what you use", level: "professional" },
    { name: "Per-user consumption limits set by your admin", level: "professional" },
    { name: "Bring-your-own-key alternative (free at any tier)", level: "free" },
    { name: "Homegrown / any-API endpoint alternative (free at any tier)", level: "free" },
    { name: "Turn AI off entirely — dealer-wide or per user", level: "free" },
  ],
  tiers: [],
};

// Fill Starter/Pro tiers for every paid Module from its feature levels (professional -> Starter,
// enterprise -> Pro; Pro includes Starter).
function withTiers(m: MarketingModule): MarketingModule {
  if (m.category !== "module") return m;
  const pro = m.features.filter((f) => f.level === "professional").map((f) => f.name);
  const ent = m.features.filter((f) => f.level === "enterprise").map((f) => f.name);
  return {
    ...m,
    tiers: [
      {
        name: "Starter",
        seats: "1 seat",
        blurb: "Everything the Module does, for a single power user.",
        includes: pro.length ? pro : m.features.map((f) => f.name),
        cta: UPGRADE(`${m.name} Starter`),
      },
      {
        name: "Pro",
        seats: "5+ seats",
        blurb: "The full Module for your team, including the enterprise features.",
        includes: ["Everything in Starter", ...(ent.length ? ent : ["Team seats + admin controls"])],
        cta: UPGRADE(`${m.name} Pro`),
      },
    ],
  };
}

export const ALL_MODULES: MarketingModule[] = [FOUNDATION, ...MODULES.map(withTiers), withTiers(DEALEROS_AI)];

export function getModule(slug: string): MarketingModule | undefined {
  return ALL_MODULES.find((m) => m.slug === slug);
}

// The paid Modules (+ add-on) for the index + pricing grid, Foundation handled separately.
export const PAID_FOR_PRICING: MarketingModule[] = MODULES.map(withTiers);
export const AI_ADDON = withTiers(DEALEROS_AI);
