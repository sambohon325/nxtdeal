"use client";

// Sales Pro "Customers" — the rep's real action center off GET /sales/my-day. Merges the
// leads-to-contact and missing-follow-up queues into one customer worklist with tap-to-call/email.

import { useState } from "react";
import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { getMyDay, type MyDay, type ActionItem } from "@/lib/salesOverview";
import { useAsync, WiredScreen, ListCard, EmptyNote } from "./kit";
import { AppContactActions } from "@/components/apps/AppContactActions";

export function SalesCustomers({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const [visibleCount, setVisibleCount] = useState(25);
  const [query, setQuery] = useState("");
  const { loading, error, data, reload } = useAsync<MyDay>(() => getMyDay(), []);

  const t = data?.my_tasks;
  const seen = new Set<string>();
  const merged: ActionItem[] = [];
  for (const bucket of [t?.action_center, t?.leads_requiring_contact_today, t?.missing_follow_ups, t?.unsold_showroom_visits]) {
    for (const it of bucket?.items ?? []) {
      if (!seen.has(it.id)) {
        seen.add(it.id);
        merged.push(it);
      }
    }
  }

  const matching = merged.filter(item => [item.name, item.phone, item.email, item.source, item.pipeline_state].join(" ").toLowerCase().includes(query.trim().toLowerCase()));
  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data} onRetry={reload}>
      <label className="block text-sm text-slate-200">Find a customer or lead<input type="search" value={query} onChange={event => { setQuery(event.target.value); setVisibleCount(25); }} placeholder="Name, phone, email or sales stage"            className="mt-2 w-full rounded-lg border border-white/10 bg-white/5 px-3 py-2 text-sm text-white placeholder-zinc-500 focus:border-[var(--app-accent)] focus:outline-none" /></label>
      <ListCard title="My customers & leads" count={matching.length}>
        {matching.slice(0, visibleCount).map((it) => (
          <div key={it.id} className="rounded-lg border border-white/5 px-3 py-2">
            <div className="min-w-0">
              <div className="truncate text-sm text-zinc-100">{it.name || "Customer"}</div>
              <div className="truncate text-[11px] text-zinc-500">
                {[it.source, it.pipeline_state].filter(Boolean).join(" · ") || it.phone || it.email || ""}
              </div>
            </div>
            <div className="mt-1.5">
              <AppContactActions customerId={it.id} phone={it.phone} name={it.name || undefined} size="xs" />
            </div>
          </div>
        ))}
        {merged.length === 0 && <EmptyNote>No open customers or leads assigned right now.</EmptyNote>}
        {merged.length > 0 && matching.length === 0 && <div role="status"><p>No customers match your search.</p><button className="mt-2 min-h-11 text-[var(--app-accent)] underline" onClick={() => setQuery("")}>Show all customers</button></div>}
        {matching.length > visibleCount && (
          <button type="button" onClick={() => setVisibleCount((count) => count + 25)} className="min-h-11 w-full rounded-lg border border-white/20 px-4 py-2 text-sm text-white focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-sky-400">
            Show more customers ({visibleCount} of {matching.length} shown)
          </button>
        )}
      </ListCard>
    </WiredScreen>
  );
}
