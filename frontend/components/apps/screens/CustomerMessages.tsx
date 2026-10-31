"use client";

// Customer message thread — the verified customer's one conversation with the dealership
// across text/call/appointments (App Suite roadmap Phase 4, customer side). Reads the
// token-scoped /public/garage/messages endpoint (core/garage.py → customer_comms unified
// timeline) behind the identity gate. Used by My Garage messages (and Showroom messages).

import { type AppDef, type AppScreen, accentOf } from "@/lib/apps/registry";
import { getMyMessages, type GarageMessagesView } from "@/lib/garage";
import { CustomerVerifyGate } from "@/components/apps/CustomerVerifyGate";
import { useAsync, ListCard, Row, EmptyNote, CustomerLoadError } from "./kit";

function Inner({ app }: { app: AppDef }) {
  const accent = accentOf(app);
  const { loading, error, data, reload } = useAsync<GarageMessagesView>(() => getMyMessages(), []);

  if (loading) {
    return <div className="flex justify-center py-12"><div className={`h-6 w-6 animate-spin rounded-full border-2 border-white/15 ${accent.text} border-t-current`} /></div>;
  }
  if (error) {
    return <CustomerLoadError subject="your conversation" onRetry={reload} />;
  }
  if (!data) return null;

  const events = data.timeline?.events ?? [];
  return (
    <ListCard title="Your conversation" count={events.length}>
      {events.length === 0 && <EmptyNote>No messages yet — your texts, calls, and appointment updates will show up here as one thread.</EmptyNote>}
      {events.map((e, i) => (
        <Row
          key={i}
          primary={String(e.summary ?? e.body ?? e.description ?? e.type ?? "Update")}
          secondary={String(e.channel ?? e.category ?? "")}
          meta={String(e.at ?? e.date ?? e.timestamp ?? "")}
        />
      ))}
    </ListCard>
  );
}

export function CustomerMessages({ app, screen }: { app: AppDef; screen: AppScreen }) {
  return (
    <div className="space-y-4">
      <div>
        <h2 className="text-xl font-bold text-white">{screen.heading}</h2>
        <p className="mt-0.5 text-sm text-zinc-400">{screen.intro}</p>
      </div>
      <CustomerVerifyGate what="your conversation with the dealership">
        <Inner app={app} />
      </CustomerVerifyGate>
    </div>
  );
}
