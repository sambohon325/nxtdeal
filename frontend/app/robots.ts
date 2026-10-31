import type { MetadataRoute } from "next";

// Sam (2026-07-16): "make sure that this website doesn't get indexed. this is just a
// test url, so we don't need google indexing this if we can avoid it." Applies to every
// deployment of this codebase (marketing, every dealer, the Hub console) since they're
// all the same repo right now, mid-testing on *.dealeros.xyz subdomains -- default is
// noindex everywhere. Flip NEXT_PUBLIC_ALLOW_INDEXING=true on a SPECIFIC Coolify app's
// env vars (e.g. the real production dealeros.xyz marketing deployment, once it's ready
// to actually go live) to allow indexing on just that one app -- every other deployment
// stays blocked with no further code changes.
const ALLOW_INDEXING = process.env.NEXT_PUBLIC_ALLOW_INDEXING === "true";

export default function robots(): MetadataRoute.Robots {
  return {
    rules: {
      userAgent: "*",
      allow: ALLOW_INDEXING ? "/" : undefined,
      disallow: ALLOW_INDEXING ? undefined : "/",
    },
  };
}
