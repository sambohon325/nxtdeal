"use client";
import { WorkButton, WorkInput , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Administration's "Identity & Access" item (Administration Control Center
// rebuild, continued) -- real, per-employee API keys (core/api_keys.py),
// already wired into api/app.py's _authenticate() bearer-token fallback: a
// generated key genuinely authenticates a request, it isn't a hollow CRUD
// screen. An employee can generate/revoke their own keys; managing another
// employee's requires ADMIN/OPERATIONS, who also get the all-employees view.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { getSession } from "@/lib/auth";
import {
  generateApiKey,
  listMyApiKeys,
  listAllApiKeys,
  revokeApiKey,
  type ApiKey,
  type NewApiKey,
} from "@/lib/apiKeys";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;
const ADMIN_ROLES = ["ADMIN", "OPERATIONS"];

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function Btn({ onClick, children, disabled, tone }: { onClick: () => void; children: React.ReactNode; disabled?: boolean; tone?: "primary" | "danger" }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      disabled={disabled}
      className={`text-xs px-2.5 py-1 rounded font-medium disabled:opacity-40 ${
        tone === "danger" ? "bg-red-900/60 text-red-200 hover:bg-red-900" : tone === "primary" ? "bg-zinc-200 text-black hover:bg-white" : "bg-zinc-800 text-zinc-300 hover:bg-zinc-700"
      }`}
    >
      {children}
    </WorkButton>
  );
}

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function isUnexpiredKey(k: ApiKey) {
  return k.active && !!k.expires_at && Date.parse(k.expires_at) > Date.now();
}

function KeyRow({ k, onRevoke }: { k: ApiKey; onRevoke: (id: string) => void }) {
  return (
    <div className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
      <div>
        <span className="text-zinc-200">{k.label || "(unlabeled)"}</span>
        <span className="text-zinc-600 ml-2 font-mono">dos_…{k.last4}</span>
        <span className="text-zinc-600 ml-2">{k.employee_id}</span>
        {!k.active && <span className="ml-2 px-1.5 py-0.5 rounded bg-red-950/40 text-red-300 text-xs">revoked</span>}
        {k.active && k.expires_at && !isUnexpiredKey(k) && <span className="ml-2 text-red-300">expired</span>}
        <span className="text-zinc-600 ml-2">created {fmt(k.created_at)}</span>
        <span className="text-zinc-600 ml-2">{k.expires_at ? `expires ${fmt(k.expires_at)}` : "expiry unavailable — replace key"}</span>
        {k.last_used_at && <span className="text-zinc-600 ml-2">last used {fmt(k.last_used_at)}</span>}
      </div>
      {k.active && <Btn tone="danger" onClick={() => onRevoke(k.id)}>Revoke</Btn>}
    </div>
  );
}

export function IdentityAccessBoard({ theme, initialTab = "mine" }: { theme: Theme; initialTab?: "mine" | "all" }) {
  const session = getSession();
  const isAdmin = !!session && ADMIN_ROLES.includes(session.role);

  const [tab, setTab] = useState<"mine" | "all">(initialTab);
  useEffect(()=>setTab(initialTab),[initialTab]);
  const [myKeys, setMyKeys] = useState<ApiKey[]>([]);
  const [allKeys, setAllKeys] = useState<ApiKey[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [newKey, setNewKey] = useState<NewApiKey | null>(null);
  const [copied, setCopied] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    const calls: Promise<unknown>[] = [listMyApiKeys().then((r) => setMyKeys(r.keys))];
    if (isAdmin) calls.push(listAllApiKeys().then((r) => setAllKeys(r.keys)));
    Promise.all(calls)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load API keys."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [isAdmin]);

  async function handleGenerate() {
    try {
      const key = await generateApiKey(label.trim());
      setNewKey(key);
      setLabel("");
      setCopied(false);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to generate an API key.");
    }
  }

  async function handleRevoke(keyId: string) {
    try {
      await revokeApiKey(keyId);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to revoke this key.");
    }
  }

  function handleCopy() {
    if (!newKey) return;
    navigator.clipboard?.writeText(newKey.raw_key).then(() => setCopied(true));
  }

  const activeMine = myKeys.filter(isUnexpiredKey).length;
  const activeAll = allKeys.filter(isUnexpiredKey).length;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-3 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-3 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="My Active Keys" value={String(activeMine)} color={RIBBON[0]} />
        <Kpi theme={theme} label="My Total Keys" value={String(myKeys.length)} color={RIBBON[1]} />
        <Kpi theme={theme} label={isAdmin ? "All Active Keys (Org)" : "—"} value={isAdmin ? String(activeAll) : "—"} color={RIBBON[2]} />
      </div>

      {isAdmin && (
        <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
          {([
            ["mine", "My Keys"],
            ["all", "All Employees"],
          ] as const).map(([key, lbl]) => (
            <WorkButton data-work-view aria-pressed={tab === key} type="submit"
              key={key}
              onClick={() => setTab(key)}
              className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${tab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
            >
              {lbl}
            </WorkButton>
          ))}
        </div>
      )}

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}

      <div className="flex-1 p-4">
        {(tab === "mine" || !isAdmin) && (
          <div className="rounded border border-zinc-800 p-3 space-y-2 max-w-md mb-4">
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Generate a New API Key</div>
            <p className="text-xs text-zinc-500">New keys expire after 90 days. Replace integration keys before they expire.</p>
            <WorkField label="Label"><WorkInput
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="Label (e.g. 'Reporting integration')"
              className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 w-full"
            /></WorkField>
            <Btn tone="primary" onClick={handleGenerate}>Generate Key</Btn>
          </div>
        )}

        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "mine" || !isAdmin ? (
          <div className="space-y-1">
            {myKeys.length === 0 && <div className="text-xs text-zinc-600">No API keys yet.</div>}
            {myKeys.map((k) => (
              <KeyRow key={k.id} k={k} onRevoke={handleRevoke} />
            ))}
          </div>
        ) : (
          <div className="space-y-1">
            {allKeys.length === 0 && <div className="text-xs text-zinc-600">No API keys exist for any employee.</div>}
            {allKeys.map((k) => (
              <KeyRow key={k.id} k={k} onRevoke={handleRevoke} />
            ))}
          </div>
        )}
      </div>

      {newKey && (
        <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setNewKey(null)}>
          <div className="bg-brand-charcoal border border-amber-700 rounded-xl p-5 w-[30rem] text-white space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="text-sm font-brand font-medium text-amber-300">🔑 Your New API Key</div>
            <div className="text-xs text-amber-300 font-medium">
              Copy this now — it will NOT be shown again. Only a hash is stored; if you lose it, you'll need to
              generate a new one.
            </div>
            <div className="flex items-center gap-2">
              <code className="flex-1 text-xs px-2 py-1.5 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 break-all">
                {newKey.raw_key}
              </code>
              <Btn tone="primary" onClick={handleCopy}>{copied ? "Copied ✓" : "Copy"}</Btn>
            </div>
            <Btn onClick={() => setNewKey(null)}>Done</Btn>
          </div>
        </WorkOverlay>
      )}
    </div>
  );
}
