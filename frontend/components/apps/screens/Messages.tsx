"use client";

// Sales "Messages" — the unified customer conversation feed off GET /connect/inbox
// (core/connect.py): every channel in one list, each touch flagged AI-handled with a rules-based
// sentiment badge. Read-only here (composing a reply lives in the full Connect board).

import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { fetchInbox, type Inbox, type Sentiment } from "@/lib/connect";
import { useAsync, WiredScreen, ListCard, Row, EmptyNote } from "./kit";

const SENTIMENT_STYLE: Record<Sentiment, string> = {
  positive: "bg-emerald-50 text-emerald-700",
  neutral: "bg-white/10 text-zinc-400",
  at_risk: "bg-amber-50 text-amber-700",
  escalation: "bg-red-50 text-red-700",
};

export function Messages({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data } = useAsync<Inbox>(() => fetchInbox({ limit: 40 }), []);
  const items = data?.items ?? [];

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={!data}>
      <ListCard title="Conversations" count={data?.total_matching ?? items.length}>
        {items.map((it) => (
          <Row
            key={it.id}
            primary={it.ai_summary || it.body || `${it.channel ?? "message"} · ${it.direction ?? ""}`}
            secondary={[it.channel, it.direction, it.handled_by_ai ? `AI: ${it.ai_worker_role ?? "worker"}` : null]
              .filter(Boolean)
              .join(" · ") || undefined}
            meta={
              <span className={`rounded-full px-2 py-0.5 text-[9px] font-medium ${SENTIMENT_STYLE[it.intelligence.sentiment]}`}>
                {it.intelligence.sentiment.replace(/_/g, " ")}
              </span>
            }
          />
        ))}
        {items.length === 0 && <EmptyNote>No conversations logged yet.</EmptyNote>}
      </ListCard>
    </WiredScreen>
  );
}
