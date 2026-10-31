"use client";

// Extracted verbatim (unchanged behavior) out of app/hub-console/page.tsx's old
// inline CreateDealerForm as part of the 2026-07-19 Dealer Management rebuild's
// file split -- see components/hub/DealerManagementSection.tsx's own docstring.

import { useState } from "react";
import { HubApiError, createDealer } from "@/lib/hubApi";

function errorMessage(error: unknown): string {
  return error instanceof HubApiError ? error.message : "Unable to reach the Hub.";
}

function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-4 text-sm text-red-400 bg-red-950/30 border border-red-900 rounded-lg px-4 py-3">
      {message}
    </div>
  );
}

export default function CreateDealerForm({ onCreated }: { onCreated: () => void }) {
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [contactName, setContactName] = useState("");
  const [error, setError] = useState("");
  const [result, setResult] = useState<{
    admin_employee_id: string;
    admin_temp_password: string;
    note: string;
  } | null>(null);
  const [saving, setSaving] = useState(false);

  async function submit() {
    if (!name.trim() || !email.trim() || saving) return;
    setSaving(true);
    setError("");
    try {
      const res = await createDealer({
        name: name.trim(),
        contact_email: email.trim(),
        contact_name: contactName.trim() || undefined,
      });
      setResult(res);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving(false);
    }
  }

  if (result) {
    return (
      <div className="bg-zinc-900 border border-brand-teal rounded-lg p-5 mb-6">
        <div className="text-sm font-bold text-brand-teal mb-2">
          Dealer scaffolded -- store this password now, it is never shown again:
        </div>
        <div className="font-mono text-sm bg-zinc-950 rounded px-3 py-2 mb-3">
          {result.admin_employee_id} / {result.admin_temp_password}
        </div>
        <p className="text-xs text-zinc-400 mb-3">{result.note}</p>
        <p className="text-xs text-zinc-500 mb-4">
          Next: create the matching Coolify apps (frontend + backend) per
          docs/DEPLOYMENT.md, then come back and set this dealer&apos;s API base URL
          from the Dealer Record once it&apos;s deployed.
        </p>
        <button
          onClick={onCreated}
          className="bg-zinc-200 text-black font-medium px-4 py-2 rounded text-xs uppercase tracking-wide"
        >
          Done
        </button>
      </div>
    );
  }

  return (
    <div className="bg-zinc-900 rounded-lg p-5 mb-6">
      {error && <ErrorBanner message={error} />}
      <div className="grid grid-cols-2 gap-3 mb-3">
        <input
          placeholder="Dealership name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          className="h-10 px-3 rounded bg-zinc-950 border border-zinc-800 focus:outline-none text-sm"
        />
        <input
          placeholder="Contact email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          className="h-10 px-3 rounded bg-zinc-950 border border-zinc-800 focus:outline-none text-sm"
        />
        <input
          placeholder="Contact name (optional)"
          value={contactName}
          onChange={(e) => setContactName(e.target.value)}
          className="h-10 px-3 rounded bg-zinc-950 border border-zinc-800 focus:outline-none text-sm col-span-2"
        />
      </div>
      <button
        onClick={submit}
        disabled={saving}
        className="brand-cta font-brand font-bold uppercase tracking-wide text-xs px-5 py-2.5 disabled:opacity-50"
      >
        {saving ? "Creating..." : "Scaffold Dealer"}
      </button>
    </div>
  );
}
