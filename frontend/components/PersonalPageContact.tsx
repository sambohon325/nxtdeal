"use client";

import { useRef, useState, type FormEvent } from "react";
import { publicSubmitPersonalSiteContactForm } from "@/lib/websites";

export function PersonalPageContact({ slug, label }: { slug: string; label?: string | null }) {
  const [draft, setDraft] = useState({ name: "", email: "", phone: "", message: "" });
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const lock = useRef(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (lock.current || sent) return;
    const input = Object.fromEntries(Object.entries(draft).map(([key, value]) => [key, value.trim()])) as typeof draft;
    if (!input.name || (!input.email && !input.phone)) {
      setError("Enter your name and an email address or phone number."); return;
    }
    lock.current = true; setBusy(true); setError(null);
    try {
      const result = await publicSubmitPersonalSiteContactForm(slug, input);
      if (!result.lead_id) throw new Error("Unconfirmed response");
      setSent(true); setDraft({ name: "", email: "", phone: "", message: "" });
    } catch {
      setError("We couldn't confirm your request. Your entries are still here. Please contact the representative before sending again to avoid a duplicate.");
    } finally { lock.current = false; setBusy(false); }
  }
  if (sent) return <p role="status" className="rounded-xl border border-sky-300/20 p-5 text-sky-100">Your request was received. The representative can follow up using the contact details you provided.</p>;
  return <form onSubmit={submit} aria-label="Contact representative" className="space-y-4 rounded-xl border border-white/15 p-6">
    <h2 className="text-xl font-light">{label || "Get in touch"}</h2>
    {(["name", "email", "phone", "message"] as const).map(key => <label key={key} className="block text-sm text-zinc-300">
      {{ name: "Name", email: "Email", phone: "Phone", message: "Message" }[key]}
      {key === "message" ? <textarea disabled={busy} maxLength={4000} value={draft.message} onChange={event => setDraft({ ...draft, message: event.target.value })} className="mt-1 w-full rounded-lg border border-white/15 bg-black/20 p-3" /> :
        <input disabled={busy} required={key === "name"} maxLength={key === "phone" ? 40 : 254} autoComplete={key === "phone" ? "tel" : key} type={key === "email" ? "email" : key === "phone" ? "tel" : "text"} value={draft[key]} onChange={event => setDraft({ ...draft, [key]: event.target.value })} className="mt-1 w-full rounded-lg border border-white/15 bg-black/20 p-3" />}
    </label>)}
    <p className="text-xs text-zinc-400">Your details and message will be shared with this representative to respond to your request.</p>
    {error && <p role="alert" className="text-sm text-amber-100">{error}</p>}
    <button type="submit" disabled={busy} className="rounded-lg border border-sky-300/30 px-4 py-2 text-sky-100">{busy ? "Sending…" : "Send request"}</button>
  </form>;
}
