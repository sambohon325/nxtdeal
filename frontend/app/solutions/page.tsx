"use client";

import Image from "next/image";
import Link from "next/link";
import {
  Cta,
  Icon,
  MarketingHeader,
  MarketingFooter,
} from "@/components/marketing/MarketingFrame";
import base from "@/components/marketing/MarketingHome.module.css";
import styles from "./solutions.module.css";
import departmentPhotos from "@/public/brand/nxtdeal-departments.png";
import businessPhotos from "@/public/brand/nxtdeal-business-departments.png";
import showroom from "@/public/brand/nxtdeal-command-showroom.webp";

const departments = [
  {
    name: "Operations",
    icon: "operations",
    copy: "Keep your dealership running at peak performance.",
    items: [
      "Daily overview & tasks",
      "Scheduling & workforce",
      "Delivery readiness",
      "Workflows & reporting",
    ],
  },
  {
    name: "Sales",
    icon: "chart",
    copy: "Turn more opportunities into customers.",
    items: [
      "Prospects & customers",
      "Deals & desking",
      "Appointments & follow-up",
      "Sales reporting",
    ],
  },
  {
    name: "Marketing",
    icon: "marketing",
    copy: "Reach the right buyers at the right time.",
    items: [
      "Audiences & campaigns",
      "Email, SMS & PURLs",
      "Websites & shared media",
      "Campaign analytics",
    ],
  },
  {
    name: "Inventory",
    icon: "car",
    copy: "Maximize every vehicle’s potential.",
    items: [
      "Acquisition & intake",
      "Pricing & merchandising",
      "Aging & lot management",
      "Inventory reporting",
    ],
  },
  {
    name: "Service",
    icon: "service",
    copy: "Drive retention and lifetime value.",
    items: [
      "Appointments & repair orders",
      "Shop control & parts",
      "Customer history",
      "Service reporting",
    ],
  },
  {
    name: "Finance",
    icon: "finance",
    copy: "Simplify deals and keep funding in focus.",
    items: [
      "Deals & funding",
      "F&I workflows",
      "BHPH portfolio",
      "Collections & payments",
    ],
  },
  {
    name: "Accounting",
    icon: "finance",
    copy: "Gain clarity and control across your financials.",
    items: [
      "General ledger",
      "Bank reconciliation",
      "Floorplan tracking",
      "Commissions",
    ],
  },
  {
    name: "HR",
    icon: "people",
    copy: "Empower your people to do their best work.",
    items: [
      "Employee records",
      "Team scheduling",
      "Workload visibility",
      "Roles & responsibilities",
    ],
  },
  {
    name: "Administration",
    icon: "shield",
    copy: "Keep your dealership secure, organized, and scalable.",
    items: [
      "Users & permissions",
      "Organization settings",
      "Integration configuration",
      "Data management",
    ],
  },
  {
    name: "Reports",
    icon: "chart",
    copy: "Turn data into actionable insights.",
    items: [
      "Department dashboards",
      "Performance reporting",
      "Inventory trends",
      "Shared business context",
    ],
  },
];
const foundations = [
  [
    "cube",
    "Connected Data Core",
    "A shared view of your business across every department.",
  ],
  [
    "operations",
    "Customizable Workflows",
    "Adapt to your processes, not the other way around.",
  ],
  [
    "people",
    "Role-Based Access",
    "Give the right people the right level of access.",
  ],
  [
    "infinity",
    "Integrations & APIs",
    "Bring your tools and dealership data together.",
  ],
  [
    "chart",
    "Business Insights",
    "Make informed decisions with context from your data.",
  ],
  ["shield", "Built to Grow", "Support the way your dealership evolves."],
];
const models = [
  [
    "operations",
    "Single Rooftop",
    "Everything you need to run one store.",
    "independent",
  ],
  [
    "people",
    "Multi-Store Groups",
    "Shared visibility with local flexibility.",
    "dealer-groups",
  ],
  [
    "car",
    "Franchise Dealer Networks",
    "Consistent processes across rooftops.",
    "franchise",
  ],
  [
    "car",
    "Independent Dealerships",
    "Tools for the independent dealer.",
    "independent",
  ],
  [
    "people",
    "Enterprise Dealers",
    "Bring your organization together.",
    "dealer-groups",
  ],
  [
    "finance",
    "Buy Here Pay Here",
    "Connected in-house finance operations.",
    "bhph",
  ],
];
const websites: Record<string, string> = {
  "Website Builder":
    "Create a web presence that reflects your dealership, with pages built around your inventory and customer journey.",
  Inventory:
    "Connect vehicle merchandising with your dealership’s inventory information.",
  SEO: "Manage search-friendly page content and metadata as part of your dealership website.",
  Blog: "Share dealership news, buying guides and helpful ownership content.",
  "Pixels & Tracking":
    "Discuss the analytics and advertising connections your dealership needs.",
  "Lead Capture":
    "Bring website inquiries into your dealership’s follow-up process.",
};

export default function SolutionsPage() {
  return (
    <div className={`${base.page} ${styles.page}`}>
      <Link className={base.skip} href="#solutions-main">
        Skip to content
      </Link>
      <div className={styles.header}>
        <MarketingHeader active="Solutions" />
      </div>
      <main id="solutions-main">
        <section className={`${styles.section} ${styles.hero}`}>
          <div>
            <p className={base.eyebrow}>
              Solutions <span aria-hidden="true">—</span>
            </p>
            <h1>
              One Platform.
              <br />
              <span>Every Department.</span>
            </h1>
            <p>
              NXTDeal is built on a single, connected platform — every module,
              data point, and workflow working together so your dealership can
              move faster, operate smarter, and deliver a better experience at
              every touchpoint.
            </p>
            <Cta />
          </div>
          <p className={styles.manifesto}>
            People
            <br />
            Process
            <br />
            Profit
            <br />
            Tomorrow
          </p>
        </section>
        <section className={styles.section} aria-labelledby="overview-heading">
          <div className={styles.overview}>
            <div>
              <p className={base.eyebrow}>Platform overview</p>
              <h2 id="overview-heading">
                Every Department. One Connected View.
              </h2>
              <p>
                Connect your teams around a shared data foundation. Break down
                silos, streamline workflows, and give your team the visibility
                to deliver a seamless customer experience from first touch to
                long-term loyalty.
              </p>
            </div>
            <div className={styles.source}>
              <Icon name="cube" />
              <p>
                A shared source of truth
                <br />
                across your entire dealership.
              </p>
            </div>
          </div>
          <div className={styles.departments}>
            {departments.map((d, i) => (
              <details className={styles.card} key={d.name}>
                <summary>
                  <div
                    className={styles.photo}
                    style={{
                      backgroundImage: `url(${i < 6 ? departmentPhotos.src : businessPhotos.src})`,
                      backgroundSize: i < 6 ? "600% auto" : "400% auto",
                      backgroundPosition: `${i < 6 ? i * 20 : ((i - 6) * 100) / 3}% center`,
                    }}
                  />
                  <div className={styles.cardCopy}>
                    <Icon name={d.icon} />
                    <div>
                      <h3>{d.name}</h3>
                      <p>{d.copy}</p>
                    </div>
                    <span className={styles.arrow} aria-hidden="true">
                      →
                    </span>
                  </div>
                </summary>
                <div className={styles.cardDetails}>
                  <p>Explore {d.name.toLowerCase()}</p>
                  <ul>
                    {d.items.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                  <Link href="/contact">Discuss your setup →</Link>
                </div>
              </details>
            ))}
            <div className={styles.gridNote}>
              Different departments.
              <br />
              One connected system.
              <br />
              Less friction. More results.
            </div>
          </div>
        </section>
        <section
          className={styles.section}
          aria-labelledby="foundation-heading"
        >
          <p className={base.eyebrow}>More than the sum of its screens</p>
          <h2 id="foundation-heading">
            A Connected Platform
            <br />
            Built to Perform.
          </h2>
          <p className={styles.intro}>
            NXTDeal brings your work together — helping you work smarter, reduce
            manual effort, and move your business forward.
          </p>
          <div className={styles.foundation}>
            {foundations.map(([icon, title, copy]) => (
              <div className={styles.feature} key={title}>
                <span className={styles.iconBox}>
                  <Icon name={icon} />
                </span>
                <div>
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </div>
              </div>
            ))}
          </div>
        </section>
        <section
          className={`${styles.section} ${styles.ai}`}
          aria-labelledby="ai-heading"
        >
          <div>
            <p className={base.eyebrow}>AI agnostic by design</p>
            <h2 id="ai-heading">Your Dealership. Your AI. Your Way.</h2>
            <p>
              Your tools should work on your terms. Our direction is an open
              platform built around the AI you choose. Ask us about supported
              connections for your setup.
            </p>
            <div className={styles.providers}>
              {[
                ["◎", "ChatGPT"],
                ["✳", "Claude"],
                ["✦", "Gemini"],
                ["▧", "Microsoft Copilot"],
                ["◇", "Your AI Platform"],
              ].map(([symbol, name], i) => (
                <Link
                  href="/contact"
                  key={name}
                  aria-label={`Ask about ${name}`}
                >
                  <span
                    aria-hidden="true"
                    style={{
                      color: [
                        "#eefaff",
                        "#e98458",
                        "#87a4ff",
                        "#60ded6",
                        "#bbdff2",
                      ][i],
                    }}
                  >
                    {symbol}
                  </span>
                  <span>{name}</span>
                </Link>
              ))}
            </div>
          </div>
          <p className={styles.manifesto}>
            Open.
            <br />
            Flexible.
            <br />
            Ready for
            <br />
            what’s next.
          </p>
        </section>
        <section className={styles.section}>
          <p className={base.eyebrow}>Designed for every type of dealership</p>
          <h2>Leadership. Grounded in the Business.</h2>
          <p className={styles.intro}>
            From single rooftops to multi-store groups, NXTDeal gives leaders
            visibility and tools to work across the organization.
          </p>
          <div className={styles.models}>
            {models.map(([icon, title, copy, slug]) => (
              <Link href={`/industries/${slug}`} key={title}>
                <Icon name={icon} />
                <div>
                  <h3>{title}</h3>
                  <p>{copy}</p>
                </div>
              </Link>
            ))}
          </div>
        </section>
        <section className={`${styles.section} ${styles.websites}`}>
          <p className={base.eyebrow}>Built to integrate</p>
          <h2>Websites</h2>
          <p>
            A modern, connected web presence that works hand-in-hand with your
            dealership.
          </p>
          <div className={styles.websiteFeatures}>
            {Object.entries(websites).map(([title, copy]) => (
              <details key={title}>
                <summary>{title}</summary>
                <p>{copy}</p>
                <Link href="/contact">Learn more →</Link>
              </details>
            ))}
          </div>
        </section>
        <section className={`${styles.section} ${styles.ctaBand}`}>
          <Image src={showroom} alt="" fill sizes="100vw" />
          <div>
            <p className={base.eyebrow}>Ready to see it in action?</p>
            <h2>See How It Fits Your Business.</h2>
            <p>Explore the platform and discover what’s possible.</p>
            <Cta />
          </div>
          <p className={styles.manifesto}>
            Same
            <br />
            dealerships.
            <br />A brighter
            <br />
            tomorrow.
          </p>
        </section>
      </main>
      <MarketingFooter />
    </div>
  );
}
