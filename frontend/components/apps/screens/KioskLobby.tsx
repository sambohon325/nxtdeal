"use client";

import type { AppDef, AppScreen } from "@/lib/apps/registry";
import { getPublicLobby, LOBBY_FIELDS } from "@/lib/lobbyInformation";
import { useAsync } from "./kit";

export function KioskLobby({ screen }: { app: AppDef; screen: AppScreen }) {
  const request = useAsync(getPublicLobby, []);
  const visible = request.data?.published === true
    ? Object.entries(LOBBY_FIELDS).flatMap(([key, label]) => {
        const value = request.data?.content[key as keyof typeof LOBBY_FIELDS];
        return typeof value === "string" && value.trim() ? [{ key, label, value }] : [];
      }) : [];
  return <section className="space-y-4">
    <h2 className="text-xl font-semibold text-white">{screen.heading}</h2>
    {request.loading ? <p role="status">Loading lobby information…</p>
      : request.error ? <p role="alert">Lobby information is unavailable right now. Please ask the service desk.</p>
      : visible.length ? <div className="grid gap-4 sm:grid-cols-2">{visible.map(({ key, label, value }) =>
          <article key={key} className="rounded-xl border border-white/10 bg-white/[0.03] p-4">
            <h3 className="font-medium text-white">{label}</h3>
            <p className="mt-2 whitespace-pre-wrap text-sm text-zinc-300">{value}</p>
          </article>)}</div>
      : <p role="status">The dealership has not published lobby information yet. Please ask the service desk about available amenities.</p>}
    <button type="button" onClick={request.reload} disabled={request.loading}
      className="rounded-lg border border-white/20 px-4 py-3 text-sm text-white disabled:opacity-40">
      {request.error ? "Try again" : "Refresh lobby information"}
    </button>
  </section>;
}
