// Industry-first marketing content (NXTDeal Marketing Site Audit — Industry-First Structure,
// 2026-08-03). One record per industry, mirroring the NXTDeal "Markets Served" template: the
// challenges the segment loses money on, an interactive challenge picker, the NXTDeal modules that
// map to it, and a side-by-side competitive comparison naming the real alternatives. Content is
// taken verbatim from the audit's six industry sections. The template component
// (components/marketing/IndustryPageTemplate.tsx) renders any of these; each has its own URL
// (/industries/<slug>) so it's independently linkable, shareable, and indexable.

// Brand accent keys (mirrors components/BrandAngles.tsx BRAND_COLORS).
export type BrandColor = "blue" | "teal" | "yellow" | "red";

export type Verdict = "yes" | "partial" | "no";

export type ComparisonRow = {
  capability: string;
  // cells align 1:1 with `columns` (column 0 is always NXTDeal).
  cells: { v: Verdict; note?: string }[];
};

export type ModuleMap = { dept: string; detail: string; href: string };

export type Industry = {
  slug: string;
  name: string;
  color: BrandColor;
  eyebrow: string;
  tagline: string; // hero sub
  // "What <segment> are up against"
  challenges: { title: string; body: string }[];
  // interactive challenge picker: pick the problem you came to solve -> the NXTDeal answer
  picker: { problem: string; answer: string }[];
  // NXTDeal modules that map to this industry
  modules: ModuleMap[];
  // competitive positioning paragraph
  positioning: string;
  // side-by-side competitive comparison
  comparison: { columns: string[]; rows: ComparisonRow[] };
  outcome: string;
};

// Map a department reference to its product page. Paid Modules get their own /modules/<slug> page;
// Foundation-level departments (inventory, administration, readiness) point at the Foundation page.
const DEPT_TO_PAGE: Record<string, string> = {
  sales: "/modules/sales",
  service: "/modules/service",
  marketing: "/modules/marketing",
  finance: "/modules/finance",
  operations: "/modules/operations",
  network: "/modules/network-premium",
  inventory: "/modules/foundation",
  administration: "/modules/foundation",
  readiness: "/modules/foundation",
};
const SOL = (key: string) => DEPT_TO_PAGE[key] ?? "/modules";

export const INDUSTRIES: Industry[] = [
  // ---------------------------------------------------------------------------
  // BHPH — built first per the audit's build order (most specific fit).
  // ---------------------------------------------------------------------------
  {
    slug: "bhph",
    name: "Buy-Here-Pay-Here Dealers",
    color: "yellow",
    eyebrow: "Buy-Here-Pay-Here",
    tagline:
      "You're running a retail lot and a loan portfolio at the same time. NXTDeal runs both on one graph — so a missed payment, a GPS ping, and a reconditioning cost are one decision, not three systems.",
    challenges: [
      {
        title: "The lot and the loan book are the same business",
        body: "A missed payment, a GPS ping, and a reconditioning cost are all part of the same decision — but most tools handle the lending side and the lot side as separate systems, which is exactly the kind of sync problem a single graph is built to remove.",
      },
      {
        title: "Delinquency should inform what you stock",
        body: "When loan performance lives in a different system than inventory and recon, a delinquency trend can never tell you which units to stock next — the data is sitting in a servicing system nobody on the lot side ever looks at.",
      },
      {
        title: "Repossessions re-enter the lot blind",
        body: "A repossessed unit comes back into inventory, but if the loan was tracked somewhere else, the lot re-lists it without the history that would price and place it correctly.",
      },
    ],
    picker: [
      { problem: "My collections are all manual and rules-based", answer: "The Collections & Repossessions module includes an AI collections assistant and delinquency tracking — not just rules, and native, not a bolt-on." },
      { problem: "My GPS/starter-interrupt hardware lives in another system", answer: "GPS & Starter-Interrupt Devices is a native module for secured-loan hardware, so a ping and a payment are on the same record." },
      { problem: "I can't see loan performance next to my inventory", answer: "Portfolio & Payments and Inventory write to one graph, so a delinquency trend directly informs recon and what to stock next." },
    ],
    modules: [
      { dept: "Finance & F&I — Portfolio & Payments", detail: "The loan book: originations, servicing, and the true payment picture.", href: SOL("finance") },
      { dept: "Finance & F&I — Collections & Repossessions", detail: "Delinquency tracking + an AI collections assistant, with repossession workflows.", href: SOL("finance") },
      { dept: "Finance & F&I — GPS & Starter-Interrupt Devices", detail: "Secured-loan hardware integration on the same record as the loan.", href: SOL("finance") },
      { dept: "Finance & F&I — Assets, Commissions & Lender Intelligence", detail: "Portfolio and asset performance reporting.", href: SOL("finance") },
      { dept: "Inventory", detail: "A repossessed unit re-enters the lot through the same graph the loan was tracked in.", href: SOL("inventory") },
    ],
    positioning:
      "DealerSocket/Solera is one of the few incumbents with real BHPH-specific tooling, alongside standalone loan-servicing systems built specifically for buy-here-pay-here books. NXTDeal's differentiation is that the loan performance data lives in the same graph as the inventory and reconditioning data, so a delinquency trend can inform which units to stock next — instead of sitting in a separate servicing system nobody on the lot side ever looks at.",
    comparison: {
      columns: ["NXTDeal", "DealerSocket / Solera", "Standalone BHPH Loan-Servicing"],
      rows: [
        { capability: "Loan servicing & portfolio management", cells: [{ v: "yes", note: "Portfolio & Payments" }, { v: "yes", note: "BHPH-capable tools" }, { v: "yes", note: "Core, purpose-built" }] },
        { capability: "Collections workflows with an AI assistant", cells: [{ v: "yes", note: "AI collections assistant" }, { v: "partial", note: "Tools exist but not AI-native" }, { v: "no", note: "Rules-based only, no AI" }] },
        { capability: "GPS & starter-interrupt hardware integration", cells: [{ v: "yes", note: "Native module" }, { v: "partial", note: "Via third-party" }, { v: "yes", note: "Often a core specialty" }] },
        { capability: "Repossession management", cells: [{ v: "yes" }, { v: "yes" }, { v: "yes" }] },
        { capability: "Inventory + loan data on one shared graph", cells: [{ v: "yes", note: "Recon informed by delinquency" }, { v: "no", note: "Separate systems" }, { v: "no", note: "Servicing-only, no lot data" }] },
        { capability: "Lender & asset performance analytics", cells: [{ v: "yes", note: "Assets & Lender Intelligence" }, { v: "partial" }, { v: "partial", note: "Servicing-focused only" }] },
        { capability: "Retail sales & desking on the same platform", cells: [{ v: "yes" }, { v: "yes" }, { v: "no", note: "Servicing-only, no sales floor" }] },
      ],
    },
    outcome: "One graph for the lot and the loan book — so delinquency, recon, and what you stock next are finally the same conversation.",
  },

  // ---------------------------------------------------------------------------
  // Franchise
  // ---------------------------------------------------------------------------
  {
    slug: "franchise",
    name: "Franchise Dealerships",
    color: "blue",
    eyebrow: "Franchise Dealerships",
    tagline:
      "OEM compliance, every department at once, and fixed-ops share slipping to independents — on a tool stack that grows more fragmented, not less. NXTDeal runs it all on one graph.",
    challenges: [
      { title: "OEM-mandated compliance no one else carries", body: "Franchise stores carry OEM-mandated reporting and compliance obligations no other segment deals with — and no tool that treats them as an afterthought will pass an audit." },
      { title: "Every department, against factory targets", body: "You run new, used, service, parts, and F&I at once against factory-set targets — a fragmented stack means every department is reconciling copies of the same records." },
      { title: "Losing fixed-ops share as the stack fragments", body: "Franchise stores are losing fixed-ops share to independents even as their own tool stack (DMS, CRM, ad vendors, phone system) grows more fragmented rather than less." },
    ],
    picker: [
      { problem: "My DMS, CRM, ad vendor and phone system don't talk", answer: "NXTDeal runs every department off one shared graph — a sale updates inventory and opens a service record with no integration in between." },
      { problem: "I can't switch DMS without a rip-and-replace", answer: "NXTDeal can sit on top of an existing DMS via Readiness before you ever replace it — start with one department, not a big-bang migration." },
      { problem: "Fixed ops is leaking to independents", answer: "Service (Appointments & Repair Orders) plus the Service-to-Sales Handoff defend fixed-ops share and turn service visits back into sales." },
    ],
    modules: [
      { dept: "Sales — Prospects & Customers, Deals & Desking", detail: "The retail engine.", href: SOL("sales") },
      { dept: "Service — Appointments & Repair Orders, Service-to-Sales Handoff", detail: "Defend fixed-ops share and convert service to sales.", href: SOL("service") },
      { dept: "Finance & F&I — Deals & Funding, Compliance & Accounting", detail: "OEM-grade compliance and lender submission.", href: SOL("finance") },
      { dept: "Marketing — CRM & Campaigns, Loyalty/VIP Rewards", detail: "Retention.", href: SOL("marketing") },
      { dept: "Administration — Vendors & Organizations, Systems & Integrations", detail: "Replace the fragmented vendor stack with one connector layer.", href: SOL("administration") },
    ],
    positioning:
      "The incumbents are Tekion, CDK Global, and Reynolds & Reynolds — each selling (or grown out of) the core DMS a franchise store is contractually tied to. NXTDeal's pitch is architectural: those systems were built module by module, often through acquisition, so departments sync copies of records to each other; NXTDeal runs every department off one shared graph, so a sale updates inventory and opens a service record with no integration in between. It can also sit on top of an existing DMS via Readiness before a dealer ever has to replace it.",
    comparison: {
      columns: ["NXTDeal", "Tekion", "CDK / Reynolds"],
      rows: [
        { capability: "Single shared data graph across departments", cells: [{ v: "yes", note: "Native, one graph" }, { v: "partial", note: "Modern DMS but depts sync" }, { v: "no", note: "Connected after acquisitions" }] },
        { capability: "AI workforce embedded per department", cells: [{ v: "yes", note: "Assistant, Automation, Coverage, Coaching" }, { v: "partial", note: "AI exists, not four-pillar" }, { v: "no", note: "Add-ons bolted on" }] },
        { capability: "OEM compliance & reporting", cells: [{ v: "yes", note: "Compliance & Accounting" }, { v: "yes", note: "Core strength" }, { v: "yes", note: "Longest track record" }] },
        { capability: "F&I deal structuring & lender submission", cells: [{ v: "yes", note: "Deals & Funding" }, { v: "yes" }, { v: "yes" }] },
        { capability: "Service-to-sales handoff automation", cells: [{ v: "yes", note: "Native, same graph" }, { v: "partial", note: "Via CRM rules" }, { v: "partial", note: "Separate CRM add-on" }] },
        { capability: "Built-in website / digital retail", cells: [{ v: "yes", note: "Website Studio + Connect" }, { v: "yes", note: "Dedicated retail tools" }, { v: "partial", note: "Separate vendor product" }] },
        { capability: "Cross-rooftop benchmarking included", cells: [{ v: "yes", note: "Network, no separate purchase" }, { v: "no", note: "Not a core feature" }, { v: "partial", note: "Separate BI at enterprise tier" }] },
        { capability: "Modular, start-with-one-department rollout", cells: [{ v: "yes", note: "Staged through Readiness" }, { v: "no", note: "Full-suite" }, { v: "no", note: "Full-suite" }] },
      ],
    },
    outcome: "One graph under every department, OEM compliance built in, and the option to start on top of your current DMS instead of replacing it on day one.",
  },

  // ---------------------------------------------------------------------------
  // Dealer Groups
  // ---------------------------------------------------------------------------
  {
    slug: "dealer-groups",
    name: "Dealer Groups",
    color: "teal",
    eyebrow: "Dealer Groups",
    tagline:
      "N stores that each need everything the other segments need — plus a layer above comparing rooftops, rolling up reporting, and deciding where to roll out first. That layer is built in, not a separate BI product.",
    challenges: [
      { title: "A platform decision, made once", body: "A group is N stores that each need everything the other five industries need, plus a layer above them comparing rooftops, rolling up reporting, and deciding where to roll out changes first. The buying decision is usually made once at the enterprise level, not store by store." },
      { title: "Cross-rooftop reporting is always a bolt-on", body: "Enterprise DMS tiers typically bundle a separate business-intelligence product on top of the core DMS just to compare rooftops — a second purchase and an integration project before you see one number." },
      { title: "Rolling out to N rooftops at once is risky", body: "Without staged rollout tooling, a platform switch means flipping every rooftop simultaneously instead of proving it on one first." },
    ],
    picker: [
      { problem: "I need to compare rooftops without buying a BI product", answer: "Network (Benchmarking & Trends, Opportunity Value & Root Cause) is the same graph every rooftop already writes to — benchmarking is available the moment a second rooftop joins." },
      { problem: "I can't risk flipping every store at once", answer: "Readiness stages the rollout rooftop by rooftop, so you prove it on one store before the group." },
      { problem: "Multi-rooftop structure is a mess to administer", answer: "Administration's Vendors & Organizations models multi-rooftop structure directly." },
    ],
    modules: [
      { dept: "Network — Benchmarking & Trends, Opportunity Value & Root Cause, Playbooks & Advisors", detail: "The centerpiece: cross-rooftop intelligence.", href: SOL("network") },
      { dept: "Administration — Vendors & Organizations", detail: "Multi-rooftop structure and administration.", href: SOL("administration") },
      { dept: "Readiness", detail: "Stage the rollout rooftop by rooftop instead of all at once.", href: SOL("readiness") },
      { dept: "Every department module", detail: "Everything the other five industries use still applies underneath — a group is built from individual stores.", href: "/industries" },
    ],
    positioning:
      "CDK Global, Reynolds & Reynolds, and Tekion all sell enterprise tiers aimed at exactly this buyer, typically bundling a separate business-intelligence product on top of the core DMS for cross-rooftop reporting. NXTDeal's argument is that Network isn't a bolted-on BI add-on purchased separately; it's the same graph every rooftop already writes to, so benchmarking and root-cause analysis are available the moment a second rooftop joins rather than after a separate integration project.",
    comparison: {
      columns: ["NXTDeal", "CDK / Reynolds", "Tekion"],
      rows: [
        { capability: "Cross-rooftop benchmarking native to the core platform", cells: [{ v: "yes", note: "Network, included" }, { v: "partial", note: "Separate BI at enterprise tier" }, { v: "partial", note: "Not a core feature" }] },
        { capability: "Multi-organization / multi-rooftop administration", cells: [{ v: "yes", note: "Vendors & Organizations" }, { v: "yes", note: "Core strength at enterprise tier" }, { v: "yes" }] },
        { capability: "Shared marketing campaigns across rooftops", cells: [{ v: "yes", note: "Shared asset library" }, { v: "yes" }, { v: "partial" }] },
        { capability: "Staged, rooftop-by-rooftop rollout tooling", cells: [{ v: "yes", note: "Readiness" }, { v: "no", note: "Full-suite per rooftop" }, { v: "no", note: "Full-suite" }] },
        { capability: "Enterprise analytics bundled at no extra integration cost", cells: [{ v: "yes" }, { v: "no", note: "Separate BI / integration project" }, { v: "partial", note: "Not native to daily workflow" }] },
      ],
    },
    outcome: "Cross-rooftop benchmarking the moment a second store joins — not a separate BI product bolted on after an integration project.",
  },

  // ---------------------------------------------------------------------------
  // Independent
  // ---------------------------------------------------------------------------
  {
    slug: "independent",
    name: "Independent Dealerships",
    color: "blue",
    eyebrow: "Independent Dealerships",
    tagline:
      "You live and die on inventory turn and acquisition cost, run leaner than a franchise store, and carry some of your own paper — without the overhead of an enterprise DMS. One graph drives inventory, pricing, advertising, and collections.",
    challenges: [
      { title: "Inventory turn and acquisition cost are everything", body: "Independents live and die on inventory turn and acquisition cost — the wrong car at the wrong price is the whole month." },
      { title: "Leaner budgets, more vendors", body: "You typically run leaner marketing budgets than a franchise store, yet end up paying for a CRM, a separate pricing tool, and a separate marketing vendor to cover it all." },
      { title: "Light collections in a used-only operation", body: "Many independents carry at least some of their own paper, which pulls light collections work into what is otherwise a used-only operation — without a franchise-scale back office to run it." },
    ],
    picker: [
      { problem: "I'm paying for a CRM, a pricing tool, and a marketing vendor", answer: "One graph drives inventory, pricing, advertising, and collections — you shouldn't need a DealerSocket-style CRM plus a vAuto-style pricing tool plus a separate marketing vendor." },
      { problem: "My listings fall out of sync across channels", answer: "The Inventory Advertising Engine keeps listings synced across channels automatically." },
      { problem: "I carry my own paper but don't have a back office", answer: "A light slice of Finance & F&I (Collections & Repossessions) is available even at independent scale." },
    ],
    modules: [
      { dept: "Inventory — Acquisitions & Lot Management, Pricing & Merchandising, Wholesale & Syndication, Aging & Overview", detail: "The core of an independent operation.", href: SOL("inventory") },
      { dept: "Marketing — Inventory Advertising Engine", detail: "Keep listings synced across channels automatically.", href: SOL("marketing") },
      { dept: "Finance & F&I — Collections & Repossessions", detail: "A light slice for stores carrying their own paper.", href: SOL("finance") },
      { dept: "Operations", detail: "The day-to-day command center a smaller store still needs without a franchise-scale back office.", href: SOL("operations") },
    ],
    positioning:
      "DealerSocket/Solera is the long-time incumbent for independents that need CRM, inventory, and light BHPH-style servicing together, and Cox Automotive's inventory-management tools (vAuto and similar) are the default for pricing and merchandising alone. NXTDeal's case is that an independent shouldn't need a DealerSocket-style CRM plus a separate vAuto-style pricing tool plus a separate marketing vendor when one graph can drive inventory, pricing, advertising, and collections together.",
    comparison: {
      columns: ["NXTDeal", "DealerSocket / Solera", "Cox Automotive (vAuto)"],
      rows: [
        { capability: "Inventory acquisition & lot workflows", cells: [{ v: "yes", note: "Acquisitions & Lot Mgmt" }, { v: "yes" }, { v: "partial", note: "Pricing focus, not acquisition" }] },
        { capability: "Automated inventory-based advertising sync", cells: [{ v: "yes", note: "Inventory Advertising Engine" }, { v: "partial", note: "Usually a marketing add-on" }, { v: "yes", note: "Core strength" }] },
        { capability: "Light in-house financing & collections", cells: [{ v: "yes", note: "Even at independent scale" }, { v: "yes", note: "BHPH-capable" }, { v: "no", note: "Inventory/pricing tool only" }] },
        { capability: "CRM lead scoring & routing", cells: [{ v: "yes", note: "Prospects & Customers" }, { v: "yes", note: "Core strength" }, { v: "no" }] },
        { capability: "Marketing website builder included", cells: [{ v: "yes", note: "Website Studio" }, { v: "partial", note: "Often separate product" }, { v: "no" }] },
        { capability: "One vendor for inventory + marketing + financing", cells: [{ v: "yes" }, { v: "partial", note: "Marketing often separate" }, { v: "no", note: "Single-purpose tool" }] },
        { capability: "AI-assisted pricing & merchandising", cells: [{ v: "yes", note: "Pricing & Merchandising + AI Workforce" }, { v: "partial" }, { v: "yes", note: "Core strength" }] },
      ],
    },
    outcome: "Inventory, pricing, advertising, and light collections on one graph — the whole used-car operation without an enterprise DMS bill or four separate vendors.",
  },

  // ---------------------------------------------------------------------------
  // Service-Only
  // ---------------------------------------------------------------------------
  {
    slug: "service-only",
    name: "Service-Only Operations",
    color: "teal",
    eyebrow: "Service-Only Operations",
    tagline:
      "An independent repair shop, quick-lube, or tire chain — no sales floor, no F&I, no inventory. Just the repair-order lifecycle, technician dispatch, and a way to keep customers coming back. And an upgrade path if the shop ever grows.",
    challenges: [
      { title: "You need shop tools, not a dealership DMS", body: "A service-only operation has no sales floor, no F&I, and no vehicle inventory to manage — but still needs a real repair-order lifecycle, technician dispatch, and customer retention. Buyers here are skeptical of anything that looks like a full dealership DMS with unused sales and F&I modules bolted on." },
      { title: "Retention is the whole business", body: "With no vehicle sale to fall back on, keeping customers coming back for the next service is the entire growth model — retention marketing isn't a nice-to-have, it's the engine." },
      { title: "Growth shouldn't mean re-platforming", body: "If the shop adds sales, F&I, or inventory later, that shouldn't mean ripping out the servicing system and starting over on a dealership platform." },
    ],
    picker: [
      { problem: "I don't want a dealership DMS with unused modules", answer: "The Service department runs almost entirely on its own — Appointments & Repair Orders, Shop Control & Parts, Customers & Warranty — the clearest proof that NXTDeal's departments are genuinely modular." },
      { problem: "Retention is my whole growth model", answer: "The Service-to-Sales Handoff is repurposed as a pure retention signal, and Marketing's Loyalty/VIP Rewards keeps customers coming back." },
      { problem: "What happens if my shop grows into sales?", answer: "Same graph — you activate additional modules (sales, F&I, inventory) without re-platforming." },
    ],
    modules: [
      { dept: "Service — Appointments & Repair Orders", detail: "The repair-order lifecycle.", href: SOL("service") },
      { dept: "Service — Shop Control & Parts", detail: "Technician dispatch and the parts desk.", href: SOL("service") },
      { dept: "Service — Customers & Warranty", detail: "Customer records and warranty tracking.", href: SOL("service") },
      { dept: "Service-to-Sales Handoff → retention", detail: "Repurposed as a pure retention signal, not a lead into a sales floor that doesn't exist here.", href: SOL("service") },
      { dept: "Marketing — Loyalty/VIP Rewards", detail: "Customer-retention marketing automation.", href: SOL("marketing") },
    ],
    positioning:
      "This segment's competitors are standalone shop-management systems built for independent repair and quick-service shops: Tekmetric, Shop-Ware, and Mitchell 1's Manager SE — a different category than the DMS/CRM players in the other industries. All three cover digital vehicle inspections, estimate building, parts and inventory, payment processing, and customer-retention marketing. NXTDeal's edge is the upgrade path: a shop that grows into sales, F&I, or inventory activates those modules on the same graph instead of re-platforming — something a servicing-only product can't offer.",
    comparison: {
      columns: ["NXTDeal", "Tekmetric / Shop-Ware", "Mitchell 1 (Manager SE)"],
      rows: [
        { capability: "Repair-order lifecycle management", cells: [{ v: "yes", note: "Appointments & Repair Orders" }, { v: "yes", note: "Core strength" }, { v: "yes", note: "Core, 100+ years" }] },
        { capability: "Digital vehicle inspections", cells: [{ v: "partial", note: "Inspections module wiring in progress" }, { v: "yes", note: "Core (DVI/DVX)" }, { v: "partial", note: "Via ProDemand" }] },
        { capability: "Technician dispatch & workflow", cells: [{ v: "yes", note: "Shop Control & Parts" }, { v: "yes" }, { v: "partial" }] },
        { capability: "Parts & inventory desk", cells: [{ v: "yes", note: "Shop Control & Parts" }, { v: "yes" }, { v: "yes" }] },
        { capability: "Payment processing / text-to-pay", cells: [{ v: "partial", note: "Platform-level, not a dedicated shop checkout" }, { v: "yes", note: "Text-to-pay, BNPL" }, { v: "partial" }] },
        { capability: "Customer retention & marketing automation", cells: [{ v: "yes", note: "Loyalty/VIP Rewards" }, { v: "yes", note: "Reminders, campaigns, two-way texting" }, { v: "yes", note: "SocialCRM, LocalSearch" }] },
        { capability: "Multi-shop management", cells: [{ v: "yes", note: "Vendors & Organizations" }, { v: "yes", note: "Multi-shop MSO tiers" }, { v: "yes" }] },
        { capability: "Upgrade path to sales / F&I / inventory if the shop grows", cells: [{ v: "yes", note: "Same graph, activate modules" }, { v: "no", note: "Servicing-only product" }, { v: "no", note: "Servicing-only product" }] },
      ],
    },
    outcome: "Real shop tools with none of the dealership overhead — and the only one on this list that grows into a full platform without a re-platform.",
  },

  // ---------------------------------------------------------------------------
  // Finance Companies
  // ---------------------------------------------------------------------------
  {
    slug: "finance-companies",
    name: "Finance Companies",
    color: "red",
    eyebrow: "Finance Companies",
    tagline:
      "You don't run a sales floor — you run originations, servicing, collections, and a portfolio. NXTDeal is the operating platform that executes all of that and benchmarks it against peers, above the targeting layer, not competing with it.",
    challenges: [
      { title: "You're an execution platform, not a targeting tool", body: "An OEM captive finance arm, a third-party subprime lender buying paper, and an in-house finance operation for a dealer group are three different buyers — but all of them need to actually run originations, servicing, collections, and recovery, not just decide who to target." },
      { title: "Portfolio performance vs peers is hard to see", body: "Without cross-lender benchmarking, you can't tell whether your delinquency, recovery, and yield are ahead of or behind comparable books." },
      { title: "No sales floor to lean on", body: "Because a finance company isn't running a sales floor, a platform built around Sales and Inventory modules is mostly dead weight — the value is in the F&I engine and the portfolio reporting." },
    ],
    picker: [
      { problem: "I have a targeting tool but nothing runs the servicing", answer: "NXTDeal competes above the targeting layer: Deals & Funding and Portfolio & Payments run the originations and servicing that come after a targeting decision." },
      { problem: "My collections and recovery are disconnected from the book", answer: "Collections & Repossessions runs delinquency and recovery workflows on the same graph as the portfolio." },
      { problem: "I can't benchmark my portfolio against peers", answer: "Network's benchmarking compares portfolio performance against peers — feeding real performance data back into future targeting." },
    ],
    modules: [
      { dept: "Finance & F&I — Deals & Funding, Portfolio & Payments", detail: "Originations and servicing.", href: SOL("finance") },
      { dept: "Finance & F&I — Collections & Repossessions", detail: "Delinquency and recovery workflows.", href: SOL("finance") },
      { dept: "Finance & F&I — Assets, Commissions & Lender Intelligence", detail: "Portfolio-level reporting.", href: SOL("finance") },
      { dept: "Network — Benchmarking", detail: "Portfolio performance against peers (this page leans on Network, not Sales/Inventory).", href: SOL("network") },
    ],
    positioning:
      "automotiveMastermind is the closest named competitor, but it's a predictive-analytics and lead-scoring layer for OEM captive finance and lease-maturity targeting rather than a full operating system. NXTDeal's honest positioning is that it competes above that layer, not directly with it: automotiveMastermind-style tools tell a lender who to target, while NXTDeal's F&I engine and Readiness function are built to run the servicing and collections operations that come after that decision — and feed real performance data back into future targeting.",
    comparison: {
      columns: ["NXTDeal", "automotiveMastermind (CDK)"],
      rows: [
        { capability: "Predictive lead scoring for captive finance / lease-maturity targeting", cells: [{ v: "partial", note: "Network + AI Consulting at platform level, not a dedicated targeting product" }, { v: "yes", note: "Core, purpose-built" }] },
        { capability: "Loan servicing & originations execution", cells: [{ v: "yes", note: "Deals & Funding, Portfolio & Payments" }, { v: "no", note: "Analytics/scoring only" }] },
        { capability: "Collections & recovery workflows", cells: [{ v: "yes", note: "Collections & Repossessions" }, { v: "no" }] },
        { capability: "Portfolio-level analytics", cells: [{ v: "yes", note: "Assets & Lender Intelligence" }, { v: "yes", note: "Core strength" }] },
        { capability: "Full operating platform (execution, not just insight)", cells: [{ v: "yes" }, { v: "no", note: "Feeds recommendations into existing DMS/CRM" }] },
        { capability: "Cross-lender / cross-portfolio benchmarking", cells: [{ v: "yes", note: "Network module" }, { v: "partial", note: "Primarily OEM-captive-focused" }] },
      ],
    },
    outcome: "The platform that runs originations, servicing, collections, and portfolio reporting — and benchmarks the book against peers — above the targeting layer, not competing with it.",
  },
];

export const INDUSTRY_ORDER = ["bhph", "franchise", "dealer-groups", "independent", "service-only", "finance-companies"];

export function getIndustry(slug: string): Industry | undefined {
  return INDUSTRIES.find((i) => i.slug === slug);
}

export function industriesInOrder(): Industry[] {
  return INDUSTRY_ORDER.map((s) => getIndustry(s)).filter(Boolean) as Industry[];
}
