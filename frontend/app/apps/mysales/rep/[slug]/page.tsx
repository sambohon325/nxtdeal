"use client";
import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { PersonalPage } from "@/components/PersonalPage";
import { HUB_API_BASE } from "@/lib/hubApi";
import { type PublicPersonalSite } from "@/lib/websites";
export default function PublicRepPage() {
  const { slug } = useParams<{ slug: string }>();
  const [site, setSite] = useState<PublicPersonalSite | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setSite(null);
    setError("");
    fetch(`${HUB_API_BASE}/mysales/public/pages/${encodeURIComponent(slug)}`, {
      credentials: "omit",
      cache: "no-store",
    })
      .then(async (r) => {
        if (!r.ok)
          throw Error(
            r.status === 404
              ? "This page is not published."
              : "This page is temporarily unavailable.",
          );
        return r.json();
      })
      .then((s) => {
        if (active) setSite(s);
      })
      .catch((e) => {
        if (active) setError(e.message);
      });
    return () => {
      active = false;
    };
  }, [slug]);
  return (
    <main className="min-h-screen bg-[#07121e] p-5 text-white">
      <div className="mx-auto max-w-xl py-8">
        {site ? (
          <PersonalPage site={site} />
        ) : (
          <p role={error ? "alert" : "status"}>{error || "Loading page…"}</p>
        )}
        <p className="mt-8 text-xs text-slate-400">
          Powered by NXTDeal · © 2026 Chronos.
        </p>
      </div>
    </main>
  );
}
