"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";
import { BrandLogo } from "@/components/BrandLogo";
import hero from "@/public/brand/nxtdeal-dealership-hero.png";
import departmentPhotos from "@/public/brand/nxtdeal-departments.png";
import showroom from "@/public/brand/nxtdeal-command-showroom.webp";
import styles from "./MarketingHome.module.css";
import { Icon, Cta, MarketingHeader, MarketingFooter } from "./MarketingFrame";

const departments = [
  {
    name: "Operations",
    icon: "operations",
    copy: "Streamline workflows across your dealership.",
    detail:
      "Keep daily execution, deliveries, titles and compliance in view. Bring the next action into focus for every team.",
  },
  {
    name: "Sales",
    icon: "chart",
    copy: "Turn more opportunities into customers.",
    detail:
      "Follow opportunities from first conversation to delivery, with customer context and the next step in one place.",
  },
  {
    name: "Marketing",
    icon: "marketing",
    copy: "Reach the right buyers with the right message.",
    detail:
      "Connect campaigns, customer audiences and dealership activity so your marketing works with the rest of the business.",
  },
  {
    name: "Inventory",
    icon: "car",
    copy: "Maximize every vehicle’s potential.",
    detail:
      "See inventory, aging and vehicle readiness together. Give sales and operations a shared view of the lot.",
  },
  {
    name: "Service",
    icon: "service",
    copy: "Drive retention and lifetime value.",
    detail:
      "Bring service activity, customer follow-up and vehicle information into the same dealership experience.",
  },
  {
    name: "Finance",
    icon: "finance",
    copy: "Simplify deals and keep finance connected.",
    detail:
      "Keep deal structure, documents and finance activity connected to the customer journey, from the desk to delivery.",
  },
];
function Preview({ mobile = false }: { mobile?: boolean }) {
  return (
    <div
      className={mobile ? styles.phone : styles.tablet}
      aria-label={
        mobile ? "Mobile platform illustration" : "Platform illustration"
      }
    >
      <div className={styles.deviceHeader}>
        <BrandLogo />
        <span>YOUR DEALERSHIP, CONNECTED.</span>
      </div>
      <div className={styles.deviceBody}>
        {!mobile && (
          <aside>
            {["Home", ...departments.map((d) => d.name), "Reports"].map(
              (name, i) => (
                <span key={name} className={i === 0 ? styles.deviceActive : ""}>
                  ⌑ &nbsp; {name}
                </span>
              ),
            )}
          </aside>
        )}
        <div className={styles.deviceMain}>
          <div className={styles.deviceWelcome}>
            <Image src={showroom} alt="" fill sizes="600px" />
            <strong>Welcome to NXTDeal</strong>
            <p>Your dealership. One connected platform.</p>
          </div>
          <div className={styles.deviceTiles}>
            {departments.map((d) => (
              <div key={d.name}>
                <Icon name={d.icon} />
                <span>{d.name}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

export function MarketingHome() {
  const [selected, setSelected] = useState<number | null>(null);
  return (
    <div className={styles.page}>
      <Link className={styles.skip} href="#main">
        Skip to content
      </Link>
      <div className={styles.heroWrap}>
        <Image
          src={hero}
          alt="NXTDeal dealership at dusk with vehicles on a reflective forecourt"
          fill
          preload
          sizes="100vw"
          className={styles.heroImage}
        />
        <MarketingHeader />
        <main id="main" className={styles.hero}>
          <p className={styles.eyebrow}>
            Dealerships today.
            <br />A brighter tomorrow.
          </p>
          <h1>
            The Complete
            <br />
            Dealer Operating
            <br />
            <em>System.</em>
          </h1>
          <p className={styles.heroCopy}>
            Run your entire dealership — sales, service, inventory, marketing,
            finance, and more — in one connected platform.
            <br />
            Built for modern dealerships. Powered by your data.
            <br />
            Ready for what’s next.
          </p>
          <div className={styles.actions}>
            <Cta />
            <Link href="#platform" className={styles.overview}>
              <span aria-hidden="true">↗</span>Explore the platform
            </Link>
          </div>
        </main>
      </div>
      <div className={styles.benefits}>
        {[
          ["operations", "Unify", "Your Operations"],
          ["chart", "Work Smarter", "With Your Data"],
          ["people", "Adapt to", "Your Way of Working"],
          ["shield", "Built for", "Modern Dealerships"],
          ["infinity", "Free Forever", "To Get Started"],
        ].map(([icon, first, second]) => (
          <div key={first}>
            <Icon name={icon} />
            <p>
              {first}
              <br />
              {second}
            </p>
          </div>
        ))}
      </div>
      <section id="platform" className={`${styles.section} ${styles.platform}`}>
        <div className={styles.platformCopy}>
          <p className={styles.eyebrow}>Built for what’s next</p>
          <h2>
            One Platform.
            <br />
            Total Control.
          </h2>
          <p>
            NXTDeal connects every part of your dealership so you can operate
            more effectively, deliver a better customer experience, and unlock
            new opportunities — today and in the future.
          </p>
          <Cta href="#departments">Explore the Platform</Cta>
        </div>
        <div className={styles.devices}>
          <Preview />
          <Preview mobile />
          <span className={styles.previewCaption}>Platform illustration</span>
        </div>
      </section>
      <section id="departments" className={styles.section}>
        <div className={styles.sectionHeading}>
          <div>
            <p className={styles.eyebrow}>Every department. Fully connected.</p>
            <h2>
              Everything Your Dealership Needs.
              <br />
              In One Place.
            </h2>
            <p>
              From inventory to marketing to the service drive, NXTDeal gives
              your team
              <br className={styles.desktopBreak} /> the tools, data, and
              workflows to move faster and achieve more.
            </p>
          </div>
          <Cta href="/solutions" outline>
            Explore All Features
          </Cta>
        </div>
        <div className={styles.departments}>
          {departments.map((d, i) => (
            <button
              type="button"
              key={d.name}
              className={styles.department}
              aria-expanded={selected === i}
              aria-controls="department-details"
              onClick={() => setSelected(selected === i ? null : i)}
            >
              <div
                className={styles.departmentPhoto}
                style={{
                  backgroundImage: `url(${departmentPhotos.src})`,
                  backgroundPosition: `${i * 20}% center`,
                }}
              />
              <div className={styles.departmentCopy}>
                <Icon name={d.icon} />
                <h3>
                  {d.name}
                  <span aria-hidden="true">{selected === i ? "−" : "↗"}</span>
                </h3>
                <p>{d.copy}</p>
              </div>
            </button>
          ))}
        </div>
        <div
          id="department-details"
          hidden={selected === null}
          className={styles.departmentDetails}
        >
          {selected !== null && (
            <>
              <h3>{departments[selected].name}, connected.</h3>
              <p>{departments[selected].detail}</p>
              <Link href="/contact">
                Talk to us about {departments[selected].name.toLowerCase()}{" "}
                <span aria-hidden="true">→</span>
              </Link>
            </>
          )}
        </div>
      </section>
      <section id="ai" className={`${styles.section} ${styles.ai}`}>
        <div>
          <p className={styles.eyebrow}>AI agnostic by design</p>
          <h2>
            Your Dealership.
            <br />
            Your AI. Your Way.
          </h2>
          <p>
            Your tools should work on your terms. NXTDeal’s direction is an open
            platform that connects your dealership with the AI you choose. Talk
            to us about supported connections for your setup.
          </p>
          <Cta href="/contact">Learn More</Cta>
        </div>
        <div>
          <div className={styles.aiCards}>
            {[
              ["◎", "ChatGPT"],
              ["✳", "Claude"],
              ["✦", "Gemini"],
              ["▧", "Microsoft Copilot"],
              ["◇", "Your AI Platform"],
            ].map(([symbol, name], i) => (
              <div
                key={name}
                style={
                  {
                    "--card-color": [
                      "#ecf8ff",
                      "#ec8b64",
                      "#89a6ff",
                      "#65d9d6",
                      "#a8e8ff",
                    ][i],
                  } as React.CSSProperties
                }
              >
                <span aria-hidden="true">{symbol}</span>
                <p>{name}</p>
              </div>
            ))}
          </div>
          <p className={styles.aiCaption}>
            Open. Flexible. Ready for what’s next.
          </p>
        </div>
      </section>
      <section
        id="industries"
        className={`${styles.section} ${styles.industries}`}
      >
        <div>
          <p className={styles.eyebrow}>Built for every type of dealership</p>
          <h2>One Platform. Every Business Model.</h2>
          <p>
            Whether you’re franchise, independent, BHPH, or part of a group,
            NXTDeal delivers the flexibility and tools to fit your business —
            now and as you grow.
          </p>
        </div>
        <div className={styles.industryCards}>
          {[
            ["car", "Franchise Dealerships", "franchise"],
            ["car", "Independent Dealerships", "independent"],
            ["finance", "Buy Here Pay Here", "bhph"],
            ["people", "Groups & Enterprise", "dealer-groups"],
          ].map(([icon, name, slug]) => (
            <Link href={`/industries/${slug}`} key={name}>
              <Icon name={icon} />
              <span>{name}</span>
            </Link>
          ))}
        </div>
      </section>
      <section id="pricing" className={styles.pricing}>
        <Image src={showroom} alt="" fill sizes="100vw" />
        <div>
          <p className={styles.eyebrow}>Get started today</p>
          <h2>It’s Free. Forever.</h2>
          <p>
            Explore core features at no cost. Upgrade as your dealership grows.
          </p>
        </div>
        <Cta />
        <p className={styles.eyebrow}>
          Same dealerships.
          <br />A brighter tomorrow.
        </p>
      </section>
      <MarketingFooter />
    </div>
  );
}
