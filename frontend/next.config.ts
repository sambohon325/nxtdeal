import type { NextConfig } from "next";

// Multi-tenant routing (session 51, REVISED session 87). Session 51's original plan was
// path-based -- dealeros.xyz/dealer1, /dealer2, etc, each its own Coolify deployment of
// this same frontend with DEALEROS_BASE_PATH set at build time. Session 87 (Sam, after
// hitting Coolify's Strip Prefixes bugs for backends in practice) switched the whole
// scheme to subdomains instead: dealeros.xyz is the marketing site, dealer1.dealeros.xyz/
// dealer2.dealeros.xyz/... are the dealers, hub.dealeros.xyz is the Hub -- see
// docs/DEPLOYMENT.md. Subdomains route on Host(), not PathPrefix()+strip, so every
// deployment now serves from its domain's root and DEALEROS_BASE_PATH should be left
// unset everywhere, including dealer1. The basePath mechanism itself is left in place
// (harmless when unset, and Next.js's basePath is still the right build-time tool if a
// path-based deployment is ever needed again) rather than ripped out.
const basePath = process.env.DEALEROS_BASE_PATH || "";

const nextConfig: NextConfig = {
  /* config options here */

  basePath,

  async headers() {
    return [{ source: "/:path*", headers: [
      { key: "X-Content-Type-Options", value: "nosniff" },
      { key: "Strict-Transport-Security", value: "max-age=31536000" },
      { key: "X-Frame-Options", value: "SAMEORIGIN" },
      { key: "Content-Security-Policy", value: "object-src 'none'; base-uri 'self'; frame-ancestors 'self'" },
      { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    ] }, { source: "/agents/connections", headers: [
      { key: "X-Frame-Options", value: "DENY" },
      { key: "Content-Security-Policy", value: "frame-ancestors 'none'" },
      { key: "Referrer-Policy", value: "no-referrer" },
      { key: "Cache-Control", value: "no-store" },
    ] }];
  },

  // Proxy programming-schedule routes to the backend API so the interactive
  // dashboard HTML (served server-side by backend/api/app.py) is reachable
  // through the same frontend domain (app.nxtdeal.app). The backend serves
  // HTML at GET /programming-schedule/dashboard-view; client-side fetches
  // still go directly to API_BASE, so this rewrite only affects direct
  // browser navigation to those paths.
  async rewrites() {
    const apiUrl = process.env.NEXT_PUBLIC_API_URL;
    if (!apiUrl) return [];
    return [
      {
        source: '/programming-schedule/:path*',
        destination: `${apiUrl}/programming-schedule/:path*`,
      },
    ];
  },

  // The floating "N" badge (Next.js Dev Tools indicator) only ever renders in `next
  // dev -- a production build (`next build && next start`) never shows it, so nothing
  // extra is needed for a deployed/production NXTDeal. Disabled here too so it's out
  // of the way during local dev as well (it was sitting in the same bottom-left corner
  // as ChatDock's launcher).
  devIndicators: false,
};

export default nextConfig;
