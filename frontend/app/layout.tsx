import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import "./product-ui.css";
import { ApplicationAppearance } from "@/components/ApplicationAppearance";
import { DemoOverlay } from "@/components/demo/DemoOverlay";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

// Sam (2026-07-16): keep every deployment of this codebase out of search results by
// default while it's still test infrastructure on *.dealeros.xyz -- see app/robots.ts
// for the matching robots.txt half of this (a robots.txt disallow is a request search
// engines can choose to honor for crawling; a page-level noindex meta tag is the
// stronger de-indexing signal, so both are set together). Same
// NEXT_PUBLIC_ALLOW_INDEXING env var flips both at once, per-deployment.
const ALLOW_INDEXING = process.env.NEXT_PUBLIC_ALLOW_INDEXING === "true";

export const metadata: Metadata = {
  title: "NXTDeal | Powered by Chrono",
  description: "NXTDeal | Powered by Chrono — one connected operating system for your dealership.",
  robots: ALLOW_INDEXING
    ? undefined
    : { index: false, follow: false, nocache: true },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      {/* h-full + overflow-hidden (not min-h-full) so the page can never grow past the
          viewport and produce a page-level scrollbar — every route is designed to fit a
          single 16:9 screen, with scrolling (where genuinely needed) handled by internal
          regions inside each page instead. See BUILD_QUEUE.md's "Viewport Fit / No
          Scrollbars" entry. */}
      <body className="h-full overflow-hidden flex flex-col">
        <ApplicationAppearance>{children}</ApplicationAppearance>
        {/* AI Demo Platform overlay — renders nothing unless a demo session is active
            (isDemoActive), so it's inert on every normal page and every real tenant. */}
        <DemoOverlay />
      </body>
    </html>
  );
}
