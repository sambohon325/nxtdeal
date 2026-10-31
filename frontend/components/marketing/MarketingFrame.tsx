"use client";
import { useState } from "react";
import Link from "next/link";
import { BrandLogo } from "@/components/BrandLogo";
import styles from "./MarketingHome.module.css";

const navigation = [
  ["Product", "/#platform"],
  ["Solutions", "/solutions"],
  ["Industries", "/#industries"],
  ["Pricing", "/#pricing"],
  ["Resources", "#resources"],
  ["Company", "/company"],
];

export function Icon({ name }: { name: string }) {
  const paths: Record<string, React.ReactNode> = {
    car: (
      <>
        <path d="m4 10 2-6h12l2 6M3 10h18v9H3zM6 19v2m12-2v2M6 14h2m8 0h2M3 10l-2-1m20 1 2-1" />
      </>
    ),
    chart: (
      <>
        <path d="M3 13h4v8H3zM10 8h4v13h-4zM17 3h4v18h-4z" />
      </>
    ),
    marketing: (
      <>
        <path d="m3 10 17-6v14L3 13zM6 14l2 7h4l-2-6M20 9h2v4h-2" />
      </>
    ),
    operations: (
      <>
        <path d="m9 2 6 0 1 4 4 1 2 5-3 3 0 4-5 3-3-3-4 0-3-5 3-3 0-4z" />
        <circle cx="12" cy="12" r="3" />
      </>
    ),
    service: (
      <>
        <path d="m14 3 1 5 5 1 2-4a6 6 0 0 1-8 8L6 21l-3-3 8-8a6 6 0 0 1 3-7ZM3 3l5 5m-5-5 3 1-2 2z" />
      </>
    ),
    finance: (
      <>
        <rect x="4" y="6" width="16" height="16" rx="2" />
        <path d="M9 6V2h6v4m-3 4v9m3-8h-5a2 2 0 0 0 0 4h3a2 2 0 0 1 0 4H9" />
      </>
    ),
    people: (
      <>
        <circle cx="9" cy="7" r="4" />
        <path d="M1 21v-3a8 8 0 0 1 16 0v3ZM16 3a4 4 0 0 1 0 8m3 3a7 7 0 0 1 4 7" />
      </>
    ),
    shield: (
      <>
        <path d="m12 2 9 4v6c0 5-9 10-9 10S3 17 3 12V6zM8 12l3 3 5-6" />
      </>
    ),
    infinity: <path d="M12 12C8 3 1 5 1 12s7 9 11 0 11-7 11 0-7 9-11 0Z" />,
    cube: (
      <>
        <path d="m12 2 10 5v10l-10 5-10-5V7zM2 7l10 5 10-5M12 12v10" />
      </>
    ),
  };
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.4"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {paths[name] || paths.car}
    </svg>
  );
}
export function Cta({
  children = "Get Started Free",
  href = "/contact",
  outline = false,
}: {
  children?: React.ReactNode;
  href?: string;
  outline?: boolean;
}) {
  return (
    <Link className={outline ? styles.outline : styles.cta} href={href}>
      {children}
      <span aria-hidden="true">→</span>
    </Link>
  );
}

export function MarketingHeader({ active }: { active?: string }) {
  const [menuOpen, setMenuOpen] = useState(false);
  return (
    <header className={styles.header}>
      <Link href="/" aria-label="NXTDeal home" className={styles.logo}>
        <BrandLogo />
      </Link>
      <nav aria-label="Main navigation" className={styles.desktopNav}>
        {navigation.map(([label, href]) => (
          <Link
            href={href}
            key={label}
            aria-current={active === label ? "page" : undefined}
          >
            {label}
          </Link>
        ))}
      </nav>
      <div className={styles.headerActions}>
        <Link href="https://app.nxtdeal.app">Sign In</Link>
        <Cta />
      </div>
      <button
        className={styles.menuToggle}
        aria-expanded={menuOpen}
        aria-controls="mobile-navigation"
        onClick={() => setMenuOpen(!menuOpen)}
      >
        {menuOpen ? "Close" : "Menu"}
        <span aria-hidden="true">{menuOpen ? "×" : "☰"}</span>
      </button>
      {menuOpen && (
        <nav
          id="mobile-navigation"
          className={styles.mobileNav}
          aria-label="Mobile navigation"
        >
          {navigation.map(([label, href]) => (
            <Link key={label} href={href} onClick={() => setMenuOpen(false)}>
              {label}
            </Link>
          ))}
          <Link href="https://app.nxtdeal.app">Sign In</Link>
          <Cta />
        </nav>
      )}
    </header>
  );
}

export function MarketingFooter() {
  return (
    <footer id="resources" className={styles.footer}>
      <div className={styles.footerTop}>
        <div>
          <Link href="/" aria-label="NXTDeal home">
            <BrandLogo />
          </Link>
          <p>Dealerships today. A brighter tomorrow.</p>
        </div>
        <div>
          <h3>Product</h3>
          <Link href="/#departments">Features</Link>
          <Link href="/#ai">AI & Connections</Link>
          <Link href="/#pricing">Pricing</Link>
        </div>
        <div>
          <h3>Resources</h3>
          <Link href="https://app.nxtdeal.app">Sign In</Link>
          <Link href="/contact">Help & Support</Link>
          <Link href="/#platform">Platform Overview</Link>
        </div>
        <div>
          <h3>Company</h3>
          <Link href="/company">About</Link>
          <Link href="/contact">Contact</Link>
          <Link href="/industries">Industries</Link>
        </div>
        <div className={styles.stayAhead}>
          <h3>Let’s Build What’s Next.</h3>
          <p>See what NXTDeal can bring to your dealership.</p>
          <Cta href="/contact" outline>
            Talk to Us
          </Cta>
        </div>
      </div>
      <div className={styles.footerBottom}>
        <span>© {new Date().getFullYear()} Chronos. All rights reserved.</span>
        <span>NXTDeal | Powered by Chrono</span>
      </div>
    </footer>
  );
}
