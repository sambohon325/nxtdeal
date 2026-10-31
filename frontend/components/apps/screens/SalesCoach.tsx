"use client";

// Keep the historical screen key and communications API compatible with external
// clients while replacing the dedicated coaching panel with conversation history.
import { type AppDef, type AppScreen } from "@/lib/apps/registry";
import { fetchRecent, type RecentActivity } from "@/lib/customerComms";
import { useAsync, WiredScreen, ListCard, Row, EmptyNote } from "./kit";

export function SalesCoach({ app, screen }: { app: AppDef; screen: AppScreen }) {
  const { loading, error, data, reload } = useAsync<RecentActivity>(() => fetchRecent(15), []);
  const items = data?.items ?? [];

  return (
    <WiredScreen app={app} screen={screen} loading={loading} error={error} empty={false} onRetry={reload}>
      <ListCard title="Recent conversations" count={items.length}>
        {items.map((r) => (
          <Row
            key={`${r.kind}-${r.id}`}
            primary={`${r.kind === "text" ? "💬" : "📞"} ${r.summary || r.number || "Conversation"}`}
            secondary={[r.direction, r.status].filter(Boolean).join(" · ") || undefined}
          />
        ))}
        {items.length === 0 && <EmptyNote>No conversations yet. Your calls and texts will appear here.</EmptyNote>}
      </ListCard>
    </WiredScreen>
  );
}
