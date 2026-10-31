"use client";

import { useEffect, useState } from "react";
import { listMyWebsites, type Website } from "@/lib/websites";

export function ParentWebsitePicker({ current, disabled, onApply }: {
  current: string | null; disabled: boolean; onApply: (id: string | null) => Promise<void>;
}) {
  const [choices, setChoices] = useState<Website[]>([]);
  const [selected, setSelected] = useState(current || "");
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const [confirm, setConfirm] = useState(false);
  useEffect(() => { setSelected(current || ""); setConfirm(false); }, [current]);
  useEffect(() => {
    let alive = true;
    setLoading(true); setFailed(false);
    listMyWebsites().then(data => { if (alive) setChoices(data); })
      .catch(() => { if (alive) setFailed(true); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [retry]);
  return <fieldset disabled={disabled} className="space-y-2 rounded-lg border border-white/15 p-3">
    <legend className="px-1 text-sm">Website branding</legend>
    <p className="text-xs text-zinc-400">Use a website you created, or choose independent branding. Applying changes updates an active page immediately. Save page edits first.</p>
    {loading ? <p role="status">Loading your websites…</p> : failed ? <div><p role="alert">Website choices could not load. Your current link is unchanged.</p><button type="button" onClick={() => setRetry(v => v + 1)}>Retry websites</button></div> : <>
      <label className="block text-sm">Branding source
        <select disabled={confirm} value={selected} onChange={e => setSelected(e.target.value)} className="mt-1 block w-full rounded bg-zinc-900 p-2 text-white">
          <option value="">Independent branding</option>
          {current && !choices.some(w => w.id === current) && <option value={current}>Current linked website ({current})</option>}
          {choices.map(w => <option key={w.id} value={w.id}>{w.name}</option>)}
        </select>
      </label>
      {!choices.length && <p className="text-xs text-zinc-400">No websites you created are available.</p>}
      {confirm ? <div><p className="text-sm">Apply this branding source to your page?</p>
        <button type="button" onClick={async () => { await onApply(selected || null); setConfirm(false); }} className="mr-4 text-[var(--app-accent)]">Confirm branding change</button>
        <button type="button" onClick={() => setConfirm(false)}>Cancel branding change</button>
      </div> : <button type="button" disabled={selected === (current || "")} onClick={() => setConfirm(true)} className="text-[var(--app-accent)] disabled:opacity-40">Apply branding source</button>}
    </>}
  </fieldset>;
}
