"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { publicGetPersonalSite, type PublicPersonalSite } from "@/lib/websites";
import { PersonalPage } from "@/components/PersonalPage";
import { BrandLogo } from "@/components/BrandLogo";
import { PersonalPageContact } from "@/components/PersonalPageContact";

export default function RepresentativePage() {
  const { slug } = useParams<{ slug: string }>();
  const [result, setResult] = useState<{ slug: string; site: PublicPersonalSite | null; error: boolean } | null>(null);
  const [retry, setRetry] = useState(0);
  useEffect(() => {
    let alive = true;
    setResult(null);
    publicGetPersonalSite(slug).then(site => { if (alive) setResult({ slug, site, error: false }); })
      .catch(() => { if (alive) setResult({ slug, site: null, error: true }); });
    return () => { alive = false; };
  }, [slug, retry]);
  const current = result?.slug === slug ? result : null;
  return <div className="min-h-screen bg-[#080f16] px-5 py-8 text-zinc-200">
    <div className="mx-auto max-w-2xl space-y-8">
      <header><BrandLogo /></header>
      <main>
        {!current ? <p role="status">Loading page…</p> : current.error || !current.site ? <div role="alert" className="space-y-3">
          <h1 className="text-2xl font-light">This page isn’t available.</h1>
          <p>It may not be published, or we couldn’t connect. Please try again.</p>
          <button onClick={() => setRetry(value => value + 1)} className="rounded-lg border border-white/20 px-4 py-2">Try again</button>
        </div> : <div className="space-y-6"><PersonalPage site={current.site} /><PersonalPageContact key={slug} slug={slug} label={current.site.cta_text} /></div>}
      </main>
      <footer className="text-xs text-zinc-500">© {new Date().getFullYear()} Chronos. All rights reserved.</footer>
    </div>
  </div>;
}
