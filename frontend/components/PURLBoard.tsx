"use client";
import { WorkInput, WorkButton, WorkSelect , WorkStat, WorkOverlay} from "./WorkspaceUi";
import {RecordCollection} from "./RecordCollection";
import { WorkField } from "./WorkField";

// Marketing's "PURLs" item -- the Personalized URL Platform (Marketing Growth
// Platform, session 113 follow-up). Sam's own "one of NXTDeal' strongest
// differentiators" example: dealer.com/john-smith. A real Generate/List/Revoke
// workspace plus a real Mail Piece + client-side QR code (the npm `qrcode`
// package, pure JS -- no native backend dependency) for direct mail, and real
// per-PURL analytics. The visitor-facing landing page itself is
// app/purl/[token]/page.tsx, genuinely public/unauthenticated.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import QRCode from "qrcode";
import {
  generatePurl,
  listPurls,
  getPurlDashboard,
  revokePurl,
  createMailPiece,
  getPurlAnalytics,
  bulkGeneratePurls,
  OFFER_TYPES,
  type Purl,
  type PurlDashboard,
  type PurlAnalytics,
  type OfferType,
  type BulkSourceType,
  type BulkGenerateResult,
} from "@/lib/purls";
import { searchCrm, type CrmSearchResult } from "@/lib/marketingCrm";
import { listAllLists, type MarketingList } from "@/lib/marketingLists";
import { listSavedAudiences, type SavedAudience } from "@/lib/smartAudiences";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const OFFER_LABELS: Record<OfferType, string> = {
  current_vehicle: "Current Vehicle",
  trade_equity: "Trade Equity",
  inventory_matches: "Inventory Matches",
  payment_reduction: "Payment Reduction",
  general: "General",
};

function fmtDate(s: string | null | undefined): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
  } catch {
    return s;
  }
}

function siteOrigin(): string {
  if (typeof window !== "undefined") return window.location.origin;
  return "";
}

function Kpi({ theme, label, value, color }: { theme: Theme; label: string; value: string; color: string }) { return <WorkStat label={label} value={value}/>; }

function StatusPill({ theme, status }: { theme: Theme; status: string }) {
  const active = status === "active";
  return (
    <span
      className={
        active
          ? "text-xs px-1.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-medium"
          : tc(theme, "text-xs px-1.5 py-0.5 rounded-full bg-zinc-700 text-zinc-300 font-medium", "text-xs px-1.5 py-0.5 rounded-full bg-zinc-200 text-zinc-600 font-medium")
      }
    >
      {active ? "Active" : "Revoked"}
    </span>
  );
}

function GeneratePurlForm({ theme, onGenerated }: { theme: Theme; onGenerated: () => void }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<CrmSearchResult[]>([]);
  const [selected, setSelected] = useState<CrmSearchResult | null>(null);
  const [offerType, setOfferType] = useState<OfferType>("general");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<{ purl: Purl; public_path: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const inputClass = tc(
    theme,
    "w-full rounded-md border border-black/20 bg-brand-ink px-2 py-1.5 text-sm text-white placeholder:text-zinc-500",
    "w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-black placeholder:text-zinc-400"
  );

  async function handleSearch(q: string) {
    setQuery(q);
    setSelected(null);
    if (q.trim().length < 2) {
      setResults([]);
      return;
    }
    try {
      const r = await searchCrm(q);
      setResults(r.results.filter((x) => x.entity_type === "Customer" || x.entity_type === "Lead"));
    } catch {
      setResults([]);
    }
  }

  async function handleGenerate() {
    if (!selected) return;
    setSubmitting(true);
    setError(null);
    try {
      const isCustomer = selected.entity_type === "Customer";
      const r = await generatePurl(offerType, isCustomer ? selected.id : undefined, isCustomer ? undefined : selected.id, notes);
      setResult(r);
      setSelected(null);
      setQuery("");
      setResults([]);
      setNotes("");
      onGenerated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to generate PURL.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-4 space-y-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-4 space-y-3")}>
      <div className="text-sm font-medium">Generate a Personalized URL</div>

      <div className="space-y-1">
        <label className="text-xs font-brand uppercase tracking-wide text-zinc-500">Customer or Lead</label>
        <WorkInput aria-label="Customer or Lead" className={inputClass} placeholder="Search by name, email, phone…" value={query} onChange={(e) => handleSearch(e.target.value)} />
        {results.length > 0 && !selected && (
          <div className={tc(theme, "border border-black/20 rounded-md max-h-40 overflow-y-auto", "border border-zinc-200 rounded-md max-h-40 overflow-y-auto")}>
            <RecordCollection>{results.map((r) => (
              <WorkButton type="submit"
                key={r.id}
                onClick={() => {
                  setSelected(r);
                  setResults([]);
                  setQuery(`${r.name ?? r.id} (${r.entity_type})`);
                }}
                className={tc(theme, "w-full text-left px-2 py-1.5 text-xs hover:bg-zinc-800", "w-full text-left px-2 py-1.5 text-xs hover:bg-zinc-100")}
              >
                {r.name ?? r.id} <span className="text-zinc-500">— {r.entity_type} · {r.id}</span>
              </WorkButton>
            ))}</RecordCollection>
          </div>
        )}
      </div>

      <div className="space-y-1">
        <label className="text-xs font-brand uppercase tracking-wide text-zinc-500">Offer Type</label>
        <WorkSelect aria-label="Offer Type" className={inputClass} value={offerType} onChange={(e) => setOfferType(e.target.value as OfferType)}>
          {OFFER_TYPES.map((o) => (
            <option key={o} value={o}>
              {OFFER_LABELS[o]}
            </option>
          ))}
        </WorkSelect>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-brand uppercase tracking-wide text-zinc-500">Notes (optional)</label>
        <WorkInput aria-label="Notes (optional)" className={inputClass} placeholder="e.g. July trade-in mailer" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>

      {error && <div className="text-xs text-red-400">{error}</div>}

      <WorkButton type="submit"
        disabled={!selected || submitting}
        onClick={handleGenerate}
        className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-40"
      >
        {submitting ? "Generating…" : "Generate PURL"}
      </WorkButton>

      {result && (
        <div className={tc(theme, "rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 space-y-1", "rounded-md border border-emerald-400 bg-emerald-50 p-3 space-y-1")}>
          <div className="text-xs font-medium">PURL generated: {result.purl.id}</div>
          <div className="text-xs font-mono break-all">{siteOrigin()}{result.public_path}</div>
        </div>
      )}
    </div>
  );
}

function BulkGenerateForm({ theme, onGenerated }: { theme: Theme; onGenerated: () => void }) {
  const [sourceType, setSourceType] = useState<BulkSourceType>("marketing_list");
  const [lists, setLists] = useState<MarketingList[]>([]);
  const [audiences, setAudiences] = useState<SavedAudience[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [offerType, setOfferType] = useState<OfferType>("general");
  const [notes, setNotes] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<BulkGenerateResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const inputClass = tc(
    theme,
    "w-full rounded-md border border-black/20 bg-brand-ink px-2 py-1.5 text-sm text-white",
    "w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-black"
  );

  useEffect(() => {
    listAllLists().then(setLists).catch(() => setLists([]));
    listSavedAudiences().then((r) => setAudiences(r.audiences)).catch(() => setAudiences([]));
  }, []);

  useEffect(() => {
    setSourceId("");
  }, [sourceType]);

  const options = sourceType === "marketing_list" ? lists : audiences;

  async function handleGenerate() {
    if (!sourceId) return;
    setSubmitting(true);
    setError(null);
    setResult(null);
    try {
      const r = await bulkGeneratePurls(sourceType, sourceId, offerType, notes || undefined);
      setResult(r);
      onGenerated();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to bulk-generate PURLs.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-4 space-y-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-4 space-y-3")}>
      <div className="text-sm font-medium">Bulk Generate for a Direct Mail Campaign</div>
      <div className="text-xs text-zinc-500">
        Generate one real PURL per person in a saved Marketing List or Smart Audience — for mailing a whole
        campaign audience at once instead of one link at a time.
      </div>

      <div className="flex gap-1">
        {(["marketing_list", "smart_audience"] as const).map((t) => (
          <WorkButton type="submit"
            key={t}
            onClick={() => setSourceType(t)}
            className={
              sourceType === t
                ? "text-xs px-2 py-1 rounded-md bg-zinc-200 text-black font-medium"
                : tc(theme, "text-xs px-2 py-1 rounded-md text-zinc-400 hover:bg-zinc-800", "text-xs px-2 py-1 rounded-md text-zinc-500 hover:bg-zinc-100")
            }
          >
            {t === "marketing_list" ? "Marketing List" : "Smart Audience"}
          </WorkButton>
        ))}
      </div>

      <div className="space-y-1">
        <label className="text-xs font-brand uppercase tracking-wide text-zinc-500">
          {sourceType === "marketing_list" ? "Marketing List" : "Smart Audience"}
        </label>
        <WorkSelect aria-label={sourceType === "marketing_list" ? "Marketing List" : "Smart Audience"} className={inputClass} value={sourceId} onChange={(e) => setSourceId(e.target.value)}>
          <option value="">Select…</option>
          {options.map((o) => (
            <option key={o.id} value={o.id}>
              {o.name} ({o.id})
            </option>
          ))}
        </WorkSelect>
        {options.length === 0 && (
          <div className="text-xs text-zinc-500">
            No {sourceType === "marketing_list" ? "marketing lists" : "smart audiences"} saved yet.
          </div>
        )}
      </div>

      <div className="space-y-1">
        <label className="text-xs font-brand uppercase tracking-wide text-zinc-500">Offer Type</label>
        <WorkSelect aria-label="Offer Type" className={inputClass} value={offerType} onChange={(e) => setOfferType(e.target.value as OfferType)}>
          {OFFER_TYPES.map((o) => (
            <option key={o} value={o}>
              {OFFER_LABELS[o]}
            </option>
          ))}
        </WorkSelect>
      </div>

      <div className="space-y-1">
        <label className="text-xs font-brand uppercase tracking-wide text-zinc-500">Notes (optional)</label>
        <WorkInput aria-label="Notes (optional)" className={inputClass} placeholder="e.g. Q3 conquest mailer" value={notes} onChange={(e) => setNotes(e.target.value)} />
      </div>

      {error && <div className="text-xs text-red-400">{error}</div>}

      <WorkButton type="submit"
        disabled={!sourceId || submitting}
        onClick={handleGenerate}
        className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-40"
      >
        {submitting ? "Generating…" : "Bulk Generate PURLs"}
      </WorkButton>

      {result && (
        <div className={tc(theme, "rounded-md border border-emerald-500/30 bg-emerald-500/10 p-3 space-y-1", "rounded-md border border-emerald-400 bg-emerald-50 p-3 space-y-1")}>
          <div className="text-xs font-medium">
            {result.created_count} of {result.requested} PURLs generated for &quot;{result.source_name ?? result.source_id}&quot;
          </div>
          {result.skipped_count > 0 && (
            <div className="text-xs text-zinc-500">
              {result.skipped_count} skipped — {result.skipped.slice(0, 3).map((s) => s.reason).join("; ")}
              {result.skipped_count > 3 ? "…" : ""}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function PurlDetailModal({ theme, purl, onClose, onChanged }: { theme: Theme; purl: Purl; onClose: () => void; onChanged: () => void }) {
  const [analytics, setAnalytics] = useState<PurlAnalytics | null>(null);
  const [qr, setQr] = useState<string | null>(null);
  const [pieceName, setPieceName] = useState("");
  const [pieceType, setPieceType] = useState("postcard");
  const [mailDate, setMailDate] = useState("");
  const [busy, setBusy] = useState(false);

  const publicUrl = `${siteOrigin()}/purl/${purl.token}`;

  useEffect(() => {
    getPurlAnalytics(purl.id).then(setAnalytics).catch(() => {});
    QRCode.toDataURL(publicUrl, { width: 180, margin: 1 })
      .then(setQr)
      .catch(() => setQr(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [purl.id]);

  const inputClass = tc(
    theme,
    "w-full rounded-md border border-black/20 bg-brand-ink px-2 py-1.5 text-sm text-white",
    "w-full rounded-md border border-zinc-300 bg-white px-2 py-1.5 text-sm text-black"
  );

  async function handleRevoke() {
    setBusy(true);
    try {
      await revokePurl(purl.id);
      onChanged();
      onClose();
    } finally {
      setBusy(false);
    }
  }

  async function handleMailPiece() {
    if (!pieceName.trim()) return;
    setBusy(true);
    try {
      await createMailPiece(purl.id, pieceName, pieceType, mailDate || undefined);
      onChanged();
    } finally {
      setBusy(false);
    }
  }

  return (
    <WorkOverlay className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4" onClick={onClose}>
      <div
        className={tc(theme, "bg-brand-charcoal border border-black/20 rounded-lg max-w-lg w-full max-h-[85vh] overflow-y-auto p-4 space-y-4", "bg-white border border-zinc-200 rounded-lg max-w-lg w-full max-h-[85vh] overflow-y-auto p-4 space-y-4")}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between">
          <div>
            <div className="text-sm font-medium">{purl.id}</div>
            <div className="text-xs text-zinc-500">{OFFER_LABELS[purl.offer_type]} · created {fmtDate(purl.created_at)}</div>
          </div>
          <StatusPill theme={theme} status={purl.status} />
        </div>

        <div className="flex gap-4 items-start">
          {qr && (
            <div className="shrink-0">
              <img src={qr} alt="PURL QR code" className="rounded-md border border-black/10" width={140} height={140} />
            </div>
          )}
          <div className="flex-1 space-y-1">
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Public Link</div>
            <div className="text-xs font-mono break-all">{publicUrl}</div>
            <WorkButton type="submit"
              onClick={() => navigator.clipboard?.writeText(publicUrl)}
              className={tc(theme, "text-xs px-2 py-1 rounded-md bg-zinc-800 hover:bg-zinc-700", "text-xs px-2 py-1 rounded-md bg-zinc-200 hover:bg-zinc-300")}
            >
              Copy Link
            </WorkButton>
          </div>
        </div>

        {analytics && (
          <div className="grid grid-cols-2 gap-2">
            <Kpi theme={theme} label="Visits" value={String(analytics.visits)} color={RIBBON[0]} />
            <Kpi theme={theme} label="Lead Generated" value={analytics.lead_generated ? "Yes" : "No"} color={RIBBON[1]} />
            <Kpi theme={theme} label="Appointments Since" value={String(analytics.correlated_since_creation.appointments_count)} color={RIBBON[2]} />
            <Kpi theme={theme} label="Revenue Since" value={`$${analytics.correlated_since_creation.revenue.toLocaleString()}`} color={RIBBON[3]} />
          </div>
        )}
        {analytics && (
          <div className="text-xs text-zinc-500 italic">{analytics.correlated_since_creation.disclaimer}</div>
        )}

        <div className={tc(theme, "border-t border-black/20 pt-3 space-y-2", "border-t border-zinc-200 pt-3 space-y-2")}>
          <div className="text-xs font-medium">Mail Piece {purl.mail_piece && "(on file)"}</div>
          {purl.mail_piece ? (
            <div className="text-xs text-zinc-500">
              {purl.mail_piece.piece_name} — {purl.mail_piece.piece_type}
              {purl.mail_piece.mail_date && ` — mailed ${purl.mail_piece.mail_date}`}
            </div>
          ) : (
            <div className="space-y-2">
              <WorkField label="Piece name"><WorkInput className={inputClass} placeholder="Piece name (e.g. July Trade-In Postcard)" value={pieceName} onChange={(e) => setPieceName(e.target.value)} /></WorkField>
              <div className="flex gap-2">
                <WorkField label="Piece Type"><WorkSelect className={inputClass} value={pieceType} onChange={(e) => setPieceType(e.target.value)}>
                  <option value="postcard">Postcard</option>
                  <option value="letter">Letter</option>
                  <option value="flyer">Flyer</option>
                  <option value="other">Other</option>
                </WorkSelect></WorkField>
                <WorkField label="Mail Date"><WorkInput type="date" className={inputClass} value={mailDate} onChange={(e) => setMailDate(e.target.value)} /></WorkField>
              </div>
              <WorkButton type="submit" disabled={busy} onClick={handleMailPiece} className="text-xs px-3 py-1.5 rounded-md bg-zinc-200 text-black font-medium disabled:opacity-40">
                Save Mail Piece
              </WorkButton>
            </div>
          )}
        </div>

        <div className="flex justify-between items-center pt-2">
          {purl.status === "active" ? (
            <WorkButton type="submit" variant="danger" disabled={busy} onClick={handleRevoke} className="text-xs px-3 py-1.5 rounded-md bg-red-500/20 text-red-400 font-medium disabled:opacity-40">
              Revoke Link
            </WorkButton>
          ) : (
            <div />
          )}
          <WorkButton type="submit" onClick={onClose} className={tc(theme, "text-xs px-3 py-1.5 rounded-md bg-zinc-800", "text-xs px-3 py-1.5 rounded-md bg-zinc-200")}>
            Close
          </WorkButton>
        </div>
      </div>
    </WorkOverlay>
  );
}

export function PURLBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<PurlDashboard | null>(null);
  const [purls, setPurls] = useState<Purl[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Purl | null>(null);
  const [statusFilter, setStatusFilter] = useState<"" | "active" | "revoked">("");

  function refresh() {
    setLoading(true);
    Promise.all([getPurlDashboard(), listPurls(undefined, statusFilter || undefined)])
      .then(([d, p]) => {
        setDashboard(d);
        setPurls(p.purls);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [statusFilter]);

  if (loading && !dashboard) {
    return <div className="p-4 text-sm text-zinc-500">Loading PURLs…</div>;
  }

  return (
    <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
      <div>
        <div className="text-base font-brand">Personalized URLs</div>
        <div className="text-xs text-zinc-500">
          dealer.com/john-smith — a real, per-person landing page with Current Vehicle, Trade Equity, Inventory
          Matches, and Payment Reduction offers, tracked end to end.
        </div>
      </div>

      {dashboard && (
        <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
          <Kpi theme={theme} label="Total PURLs" value={String(dashboard.kpis.total_purls)} color={RIBBON[0]} />
          <Kpi theme={theme} label="Active" value={String(dashboard.kpis.active_purls)} color={RIBBON[1]} />
          <Kpi theme={theme} label="Total Visits" value={String(dashboard.kpis.total_visits)} color={RIBBON[2]} />
          <Kpi theme={theme} label="Leads Generated" value={String(dashboard.kpis.leads_generated)} color={RIBBON[3]} />
          <Kpi theme={theme} label="Conversion Rate" value={`${dashboard.kpis.conversion_rate}%`} color={RIBBON[0]} />
        </div>
      )}

      <GeneratePurlForm theme={theme} onGenerated={refresh} />
      <BulkGenerateForm theme={theme} onGenerated={refresh} />

      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <div className="text-sm font-medium">All PURLs</div>
          <div className="flex gap-1">
            {(["", "active", "revoked"] as const).map((s) => (
              <WorkButton type="submit"
                key={s || "all"}
                onClick={() => setStatusFilter(s)}
                className={
                  statusFilter === s
                    ? "text-xs px-2 py-1 rounded-md bg-zinc-200 text-black font-medium"
                    : tc(theme, "text-xs px-2 py-1 rounded-md text-zinc-400 hover:bg-zinc-800", "text-xs px-2 py-1 rounded-md text-zinc-500 hover:bg-zinc-100")
                }
              >
                {s === "" ? "All" : s === "active" ? "Active" : "Revoked"}
              </WorkButton>
            ))}
          </div>
        </div>

        {purls.length === 0 ? (
          <div className="text-xs text-zinc-500">No PURLs yet — generate one above.</div>
        ) : (
          <div className={tc(theme, "border border-black/20 rounded-lg divide-y divide-black/10", "border border-zinc-200 rounded-lg divide-y divide-zinc-200")}>
            {purls.map((p) => (
              <button
                key={p.id}
                onClick={() => setSelected(p)}
                className={tc(theme, "w-full text-left px-3 py-2 flex items-center justify-between hover:bg-zinc-900/40", "w-full text-left px-3 py-2 flex items-center justify-between hover:bg-zinc-50")}
              >
                <div>
                  <div className="text-xs font-medium">
                    {p.id} <span className="text-zinc-500">— {OFFER_LABELS[p.offer_type]}</span>
                  </div>
                  <div className="text-xs text-zinc-500">
                    {p.customer_id ?? p.lead_id} · {p.visit_count} visit{p.visit_count === 1 ? "" : "s"}
                    {p.generated_lead_id && ` · lead generated: ${p.generated_lead_id}`}
                  </div>
                </div>
                <StatusPill theme={theme} status={p.status} />
              </button>
            ))}
          </div>
        )}
      </div>

      {selected && <PurlDetailModal theme={theme} purl={selected} onClose={() => setSelected(null)} onChanged={refresh} />}
    </div>
  );
}
