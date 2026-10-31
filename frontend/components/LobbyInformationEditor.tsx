"use client";
import { WorkButton, WorkTextarea } from "./WorkspaceUi";

import { useEffect, useRef, useState } from "react";
import { getLobbySettings, saveLobbySettings, LOBBY_FIELDS, type LobbyContent, type LobbySettings } from "@/lib/lobbyInformation";

export function LobbyInformationEditor() {
  const [saved, setSaved] = useState<LobbySettings | null>(null);
  const [content, setContent] = useState<LobbyContent>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [confirm, setConfirm] = useState<boolean | null>(null);
  const lock = useRef(false);
  async function load() {
    if (lock.current) return;
    lock.current = true;
    setLoading(true); setError("");
    try {
      const data = await getLobbySettings();
      setSaved(data); setContent(data.content);
    } catch {
      setError("Lobby settings could not be loaded. Admin or Operations access is required. You can retry if your connection was interrupted.");
    } finally { lock.current = false; setLoading(false); }
  }
  useEffect(() => { void load(); }, []);
  async function save(published: boolean) {
    if (lock.current) return;
    lock.current = true; setBusy(true); setError(""); setMessage("");
    try {
      const data = await saveLobbySettings(content, published);
      setSaved(data); setContent(data.content); setConfirm(null);
      setMessage(data.published ? "Lobby information published." : "Draft saved. Lobby information is not public.");
    } catch {
      setError("The save could not be confirmed. Your edits are still here. Retry to confirm the saved state.");
    } finally { lock.current = false; setBusy(false); }
  }
  const buttonClass = "rounded border border-zinc-500 px-3 py-2 text-sm disabled:opacity-40";
  if (loading) return <p role="status">Loading lobby settings…</p>;
  if (!saved) return <div><p role="alert">{error}</p><WorkButton type="submit" className={buttonClass} onClick={load}>Try again</WorkButton></div>;
  return <section className="max-w-2xl space-y-4" aria-label="Lobby information editor">
    <h2 className="text-lg font-semibold">Lobby information</h2>
    <p className="text-sm">Published content is public on the kiosk. Add only guest-facing information. Never include internal passwords, employee details or private customer information.</p>
    <p role="status">Last confirmed state: {saved.published ? "Published" : "Not public"}</p>
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
    <fieldset disabled={busy || confirm !== null} className="space-y-3">
      {Object.entries(LOBBY_FIELDS).map(([key, label]) => <label key={key} className="block text-sm">
        {label}
        <WorkTextarea className="mt-1 block w-full rounded border border-zinc-600 bg-transparent p-2" rows={3} maxLength={1000}
          value={content[key as keyof LobbyContent] || ""}
          onChange={e => { setContent({ ...content, [key]: e.target.value }); setMessage(""); }} />
      </label>)}
    </fieldset>
    {confirm === null ? <div className="flex flex-wrap gap-2">
      <WorkButton type="submit" className={buttonClass} disabled={busy} onClick={() => saved.published ? setConfirm(false) : void save(false)}>{saved.published ? "Unpublish and save draft" : "Save draft"}</WorkButton>
      <WorkButton type="submit" className={buttonClass} disabled={busy || !Object.values(content).some(v => v?.trim())} onClick={() => setConfirm(true)}>Publish information</WorkButton>
    </div> : <div className="space-y-2 rounded border border-zinc-600 p-3">
      <p>{confirm ? "Publish these edits for anyone using the kiosk to read?" : "Remove public lobby information and save these edits as a private draft?"}</p>
      <div className="flex gap-2">
        <WorkButton type="submit" className={buttonClass} disabled={busy} onClick={() => save(confirm)}>{confirm ? "Confirm publish" : "Confirm unpublish"}</WorkButton>
        <WorkButton type="submit" className={buttonClass} disabled={busy} onClick={() => setConfirm(null)}>Cancel</WorkButton>
      </div>
    </div>}
  </section>;
}
