"use client";
import { WorkButton, WorkTextarea, WorkInput, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

import { SafeHtmlPreview } from "@/components/SafeHtmlPreview";

// Marketing's "Email / SMS" Top Menu item (session 79, redesigned session 82). Sam:
// "It looks pretty bad and not all with the ui that we've made. Please create a more
// user friendly method of this that uses all the space. also just like the all
// dashes, it needs to have active metrics / graphics at the top of the dash. for
// reference / please apply mailchimp app logic how the dashboard should be laid out
// but with our theme."
//
// Mailchimp's own layout logic: a KPI strip up top, then a persistent left-hand
// campaign/template library you browse and click into, with the actual editor taking
// over the full remaining width -- not a single cramped column with a tiny <select>.
// This rework keeps every real piece already built (the AI wizard, the real
// drag-and-drop block builder, real GSM-7/UCS-2 SMS segment math, the CRM-backed
// recipient picker) and gives it that shell: GET /menu/data's email_sms overview
// (core/marketing_menu.py's email_sms()) now drives a real KPI header, and the
// template list moves out of a dropdown into a proper left-hand library pane.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useRef, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders, getSession } from "@/lib/auth";
import {
  fetchEmailSmsOverview,
  fetchBlockTypes,
  createTemplate,
  updateTemplate,
  listAllTemplates,
  draftFromWizard,
  fetchMergeFields,
  previewPersonalized,
  type BlockType,
  type EmailTemplate,
  type EmailChannel,
  type TemplateBlock,
  type EmailSmsOverview,
  type MergeField,
  type PersonalizedPreview,
} from "@/lib/emailSms";
import { previewCrmAudience, createCrmCampaign, fetchCrmData, type CrmData } from "@/lib/marketingCrm";
import { setAbVariant, getCampaignRevenue, getAbTestResults, type CampaignRevenue, type AbTestResults } from "@/lib/campaignAnalytics";
import { listAllLists, type MarketingList } from "@/lib/marketingLists";
import { EmailBuilderCanvas } from "@/components/EmailBuilderCanvas";

type Theme = "dark" | "light";
type Mode = "wizard" | "builder";
type LibraryFilter = "all" | "mine" | EmailChannel;

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const PALETTE_DRAG_TYPE = "application/x-dealeros-email-block";
const REORDER_DRAG_TYPE = "application/x-dealeros-email-block-reorder";

// Mirrors core/email_templates.py's sms_segment_info() -- same real GSM-7 (160/153)
// vs UCS-2 (70/67) segmentation math, computed client-side for instant feedback while
// typing rather than round-tripping to the backend on every keystroke.
function smsSegmentInfo(body: string) {
  const length = body.length;
  const isGsm7 = [...body].every((c) => c.charCodeAt(0) < 128);
  const singleLimit = isGsm7 ? 160 : 70;
  const multiLimit = isGsm7 ? 153 : 67;
  const segments = length === 0 ? 0 : length <= singleLimit ? 1 : Math.ceil(length / multiLimit);
  return { length, encoding: isGsm7 ? "GSM-7" : "UCS-2 (Unicode)", segments, charsPerSegment: segments <= 1 ? singleLimit : multiLimit };
}

// Client-side mirror of core/email_templates.py's render_email_html() -- real,
// deterministic rendering of the same block shapes, so the preview pane updates
// instantly as blocks are edited instead of waiting on a save + fetch round trip.
function renderBlocksHtml(blocks: TemplateBlock[]): string {
  const esc = (v: unknown) => String(v ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const parts = blocks.map((b) => {
    const f = b.fields ?? {};
    switch (b.block_key) {
      case "html":
        return String(f.html ?? "");
      case "heading":
        return `<h2 style="margin:16px 0;">${esc(f.text)}</h2>`;
      case "paragraph":
        return `<p style="margin:12px 0;line-height:1.5;">${esc(f.text).replace(/\n/g, "<br/>")}</p>`;
      case "image":
        return `<img src="${esc(f.image_url)}" alt="${esc(f.alt_text)}" style="max-width:100%;display:block;margin:12px 0;"/>`;
      case "button":
        return `<div style="margin:16px 0;"><a href="${esc(f.url)}" style="background:#2B68AB;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;display:inline-block;">${esc(f.text)}</a></div>`;
      case "divider":
        return `<hr style="border:none;border-top:1px solid #ddd;margin:16px 0;"/>`;
      case "spacer":
        return `<div style="height:${esc(f.height || "24")}px;"></div>`;
      case "footer":
        return `<p style="margin-top:24px;font-size:11px;color:#888;">${esc(f.text)}</p>`;
      default:
        return "";
    }
  });
  return `<div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;">${parts.join("")}</div>`;
}

function blockSummary(block: TemplateBlock): string {
  const f = block.fields ?? {};
  if (typeof f.text === "string" && f.text) return f.text.slice(0, 60);
  if (typeof f.image_url === "string" && f.image_url) return f.image_url;
  return "(empty)";
}

function fmtDate(s: string | undefined | null): string {
  if (!s) return "—";
  try {
    return new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  } catch {
    return s;
  }
}

async function searchRecipients(query: string): Promise<Array<{ id: string; entity_type: string; name: string }>> {
  if (!query.trim()) return [];
  const res = await fetch(`${API_BASE}/search?q=${encodeURIComponent(query)}`, { headers: { ...authHeaders() } });
  const data = await res.json();
  if (!Array.isArray(data)) return [];
  return data
    .filter((e: { entity_type: string }) => e.entity_type === "Customer" || e.entity_type === "Lead")
    .map((e: { id: string; entity_type: string; attributes: Record<string, unknown> }) => ({
      id: e.id,
      entity_type: e.entity_type,
      name:
        e.entity_type === "Customer"
          ? `${e.attributes.FirstName ?? ""} ${e.attributes.LastName ?? ""}`.trim() || e.id
          : String(e.attributes.LeadID ?? e.id),
    }));
}

// Mailchimp-style top KPI strip -- Sam: "just like the all dashes, it needs to have
// active metrics / graphics at the top." Real numbers off core/marketing_menu.py's
// email_sms(), the same overview already fetched for the library pane below.
function KpiStrip({ theme, overview }: { theme: Theme; overview: EmailSmsOverview | null }) {
  if (!overview) return null;

  const cards: Array<{ label: string; value: number | string; accent?: string }> = [
    { label: "Total Messages", value: overview.total_templates },
    { label: "Email", value: overview.by_channel.email ?? 0 },
    { label: "SMS", value: overview.by_channel.sms ?? 0 },
    { label: "AI-Generated", value: overview.ai_generated_count, accent: "text-brand-teal" },
    { label: "Attached to Campaign", value: overview.attached_to_campaign_count, accent: "text-brand-blue" },
  ];

  // Same brand-ribbon order as components/DepartmentWorkflowButtons.tsx's
  // RIBBON_COLORS -- keeps this board's KPI strip on the same angled-flag language as
  // every other dash rather than a plain flat card.
  const kpiRibbon = PRODUCT_ACCENT_COLORS;

  return (
    <div className={tc(theme, "grid grid-cols-5 gap-3 p-4 border-b border-black/20 shrink-0", "grid grid-cols-5 gap-3 p-4 border-b border-zinc-200 shrink-0")}>
      {cards.map((c, i) => (
        <div key={c.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
          <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
            style={{ background: kpiRibbon[i % kpiRibbon.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
          />
          <div className={`text-2xl font-semibold ${c.accent ?? ""}`}>{c.value}</div>
          <div className={tc(theme, "text-xs font-brand uppercase tracking-wide text-zinc-500 truncate", "text-xs font-brand uppercase tracking-wide text-zinc-500 truncate")}>{c.label}</div>
        </div>
      ))}
    </div>
  );
}

function BlockCard({
  theme,
  block,
  blockType,
  onUpdateField,
  onRemove,
  dragProps,
}: {
  theme: Theme;
  block: TemplateBlock;
  blockType?: BlockType;
  onUpdateField: (key: string, value: string) => void;
  onRemove: () => void;
  dragProps: React.HTMLAttributes<HTMLDivElement>;
}) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div
      {...dragProps}
      className={tc(
        theme,
        "rounded-lg border border-zinc-800 bg-brand-charcoal overflow-hidden",
        "rounded-lg border border-zinc-300 bg-zinc-50 overflow-hidden"
      )}
    >
      <div className={tc(theme, "flex items-center gap-2 px-2.5 py-1.5 bg-zinc-900 cursor-grab active:cursor-grabbing", "flex items-center gap-2 px-2.5 py-1.5 bg-zinc-100 cursor-grab active:cursor-grabbing")}>
        <span className="text-xs">⠿</span>
        <span className={tc(theme, "text-xs font-semibold text-zinc-200 flex-1", "text-xs font-semibold text-zinc-800 flex-1")}>
          {blockType?.name ?? block.block_key}
        </span>
        <WorkButton type="submit" onClick={() => setExpanded((e) => !e)} className={tc(theme, "text-xs text-zinc-500 hover:text-white transition", "text-xs text-zinc-500 hover:text-black transition")}>
          {expanded ? "▾" : "▸"}
        </WorkButton>
        <WorkButton type="submit" variant="danger" onClick={onRemove} className="text-xs text-zinc-500 hover:text-red-400 transition">✕</WorkButton>
      </div>
      {!expanded && (
        <div className={tc(theme, "px-2.5 py-1.5 text-xs text-zinc-500 truncate", "px-2.5 py-1.5 text-xs text-zinc-500 truncate")}>
          {blockSummary(block)}
        </div>
      )}
      {expanded && (
        <div className="px-2.5 py-2 space-y-1.5">
          {(blockType?.fields ?? []).length === 0 && (
            <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>No settings for this block.</div>
          )}
          {(blockType?.fields ?? []).map((f) => (
            <label key={f.key} className="block">
              <span className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-600")}>{f.label}</span>
              {f.type === "textarea" ? (
                <WorkTextarea
                  value={String(block.fields?.[f.key] ?? "")}
                  onChange={(e) => onUpdateField(f.key, e.target.value)}
                  rows={3}
                  className={tc(
                    theme,
                    "w-full mt-0.5 px-2 py-1 text-xs rounded bg-zinc-900 border border-zinc-700 resize-none",
                    "w-full mt-0.5 px-2 py-1 text-xs rounded bg-white border border-zinc-300 resize-none"
                  )}
                />
              ) : (
                <WorkInput
                  value={String(block.fields?.[f.key] ?? "")}
                  onChange={(e) => onUpdateField(f.key, e.target.value)}
                  className={tc(
                    theme,
                    "w-full h-7 mt-0.5 px-2 text-xs rounded bg-zinc-900 border border-zinc-700",
                    "w-full h-7 mt-0.5 px-2 text-xs rounded bg-white border border-zinc-300"
                  )}
                />
              )}
            </label>
          ))}
        </div>
      )}
    </div>
  );
}

// Dynamic Personalization (Marketing Growth Platform, Email/SMS upgrades slice,
// 2026-07-18) -- a real preview of what a specific real Customer/Lead would actually
// see, merge-tokens resolved against their real on-file attributes
// (core/email_personalization.py), not just the raw {{first_name}} placeholders the
// Live Preview pane above already shows.
function PersonalizationPreview({ theme, templateId }: { theme: Theme; templateId: string }) {
  const [mergeFields, setMergeFields] = useState<MergeField[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ id: string; entity_type: string; name: string }>>([]);
  const [selected, setSelected] = useState<{ id: string; name: string } | null>(null);
  const [preview, setPreview] = useState<PersonalizedPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetchMergeFields().then(setMergeFields).catch(() => {});
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchQuery.trim() && !selected) {
        searchRecipients(searchQuery).then(setSearchResults).catch(() => setSearchResults([]));
      } else {
        setSearchResults([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [searchQuery, selected]);

  async function loadPreview(personId: string) {
    setLoading(true);
    setError(null);
    try {
      setPreview(await previewPersonalized(templateId, personId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't render a personalized preview.");
      setPreview(null);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-300 bg-zinc-50 p-3")}>
      <div className={tc(theme, "text-xs font-bold uppercase tracking-wide text-zinc-400 mb-2", "text-xs font-bold uppercase tracking-wide text-zinc-500 mb-2")}>
        🪄 Personalize Preview
      </div>
      <div className="space-y-2">
        <WorkField label="Preview as a real Customer or Lead"><WorkInput
          value={searchQuery}
          onChange={(e) => {
            setSearchQuery(e.target.value);
            setSelected(null);
            setPreview(null);
          }}
          placeholder="Preview as a real Customer or Lead…"
          className={tc(theme, "w-full h-8 px-2 text-xs rounded bg-zinc-900 border border-zinc-700", "w-full h-8 px-2 text-xs rounded bg-white border border-zinc-300")}
        /></WorkField>
        {searchResults.length > 0 && !selected && (
          <div className={tc(theme, "rounded border border-zinc-800 divide-y divide-zinc-800 max-h-28 overflow-y-auto", "rounded border border-zinc-300 divide-y divide-zinc-200 max-h-28 overflow-y-auto")}>
            {searchResults.map((r) => (
              <WorkButton type="submit"
                key={r.id}
                onClick={() => {
                  setSelected({ id: r.id, name: r.name });
                  setSearchResults([]);
                  loadPreview(r.id);
                }}
                className={tc(theme, "w-full text-left px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 transition", "w-full text-left px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-100 transition")}
              >
                {r.name} <span className="text-zinc-500">({r.id})</span>
              </WorkButton>
            ))}
          </div>
        )}
        {selected && (
          <div className={tc(theme, "text-xs text-zinc-300 px-2 py-1 rounded bg-zinc-900 border border-zinc-700 flex items-center justify-between", "text-xs text-zinc-700 px-2 py-1 rounded bg-white border border-zinc-300 flex items-center justify-between")}>
            <span>Previewing as: {selected.name}</span>
            <WorkButton type="submit" variant="danger"
              onClick={() => {
                setSelected(null);
                setPreview(null);
              }}
              className="text-zinc-500 hover:text-red-400 transition"
            >
              ✕
            </WorkButton>
          </div>
        )}
        {loading && <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>Rendering…</div>}
        {error && <div className="text-xs text-red-400">{error}</div>}
        {preview && preview.channel === "email" && (
          <div className="space-y-1">
            <div className={tc(theme, "text-xs font-semibold text-zinc-200", "text-xs font-semibold text-zinc-800")}>{preview.subject}</div>
            <SafeHtmlPreview className="bg-white rounded p-2 text-black text-xs max-h-48 overflow-y-auto" html={preview.html} />
          </div>
        )}
        {preview && preview.channel === "sms" && (
          <div className="max-w-[240px] ml-auto bg-brand-teal text-black text-xs rounded-2xl rounded-br-sm px-3 py-2">{preview.sms_body || "…"}</div>
        )}
        <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>
          Merge fields available: {mergeFields.map((f) => `{{${f.key}}}`).join("  ")}
        </div>
      </div>
    </div>
  );
}

// Revenue Tracking + A/B Testing (Marketing Growth Platform, Email/SMS upgrades
// slice, 2026-07-18). Real, honestly-correlational numbers off
// core/campaign_analytics.py once a template is linked to an activated campaign.
function CampaignPerformancePanel({ theme, campaignId }: { theme: Theme; campaignId: string }) {
  const [revenue, setRevenue] = useState<CampaignRevenue | null>(null);
  const [abResults, setAbResults] = useState<AbTestResults | null>(null);
  const [loading, setLoading] = useState(false);

  function refresh() {
    setLoading(true);
    Promise.all([
      getCampaignRevenue(campaignId).catch((e) => ({ error: e instanceof Error ? e.message : "Couldn't load revenue." }) as CampaignRevenue),
      getAbTestResults(campaignId).catch((e) => ({ error: e instanceof Error ? e.message : "" }) as AbTestResults),
    ])
      .then(([rev, ab]) => {
        setRevenue(rev);
        setAbResults(ab);
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    refresh();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [campaignId]);

  // Extracted into a properly-narrowed local rather than a plain boolean flag --
  // a boolean derived from abResults doesn't carry the type narrowing back to
  // abResults itself when referenced later in JSX, so this returns the actual
  // narrowed (eligible-only) shape instead.
  const abData: Extract<AbTestResults, { eligible: true }> | null =
    abResults && !("error" in abResults) && "eligible" in abResults && abResults.eligible ? abResults : null;

  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3 space-y-2", "rounded-lg border border-zinc-300 bg-zinc-50 p-3 space-y-2")}>
      <div className="flex items-center justify-between">
        <div className={tc(theme, "text-xs font-bold uppercase tracking-wide text-zinc-400", "text-xs font-bold uppercase tracking-wide text-zinc-500")}>
          📊 Campaign Performance
        </div>
        <WorkButton type="submit" onClick={refresh} className={tc(theme, "text-xs text-zinc-500 hover:text-white transition", "text-xs text-zinc-500 hover:text-black transition")}>
          {loading ? "…" : "↻"}
        </WorkButton>
      </div>

      {revenue && "error" in revenue && <div className="text-xs text-red-400">{revenue.error}</div>}
      {revenue && !("error" in revenue) && "eligible" in revenue && !revenue.eligible && (
        <div className={tc(theme, "text-xs text-zinc-500", "text-xs text-zinc-500")}>{revenue.reason}</div>
      )}
      {revenue && !("error" in revenue) && "eligible" in revenue && revenue.eligible && (
        <>
          <div className="grid grid-cols-3 gap-1.5">
            <div className={tc(theme, "rounded bg-zinc-900 border border-zinc-800 p-1.5", "rounded bg-white border border-zinc-300 p-1.5")}>
              <div className="text-sm font-semibold text-brand-teal">${revenue.revenue.toLocaleString()}</div>
              <div className="text-xs text-zinc-500">Revenue (correlated)</div>
            </div>
            <div className={tc(theme, "rounded bg-zinc-900 border border-zinc-800 p-1.5", "rounded bg-white border border-zinc-300 p-1.5")}>
              <div className="text-sm font-semibold">{revenue.funded_deals_count}</div>
              <div className="text-xs text-zinc-500">Funded Deals</div>
            </div>
            <div className={tc(theme, "rounded bg-zinc-900 border border-zinc-800 p-1.5", "rounded bg-white border border-zinc-300 p-1.5")}>
              <div className="text-sm font-semibold">{revenue.leads_sold_count}</div>
              <div className="text-xs text-zinc-500">Leads Sold</div>
            </div>
          </div>
          <div className={tc(theme, "text-xs text-zinc-600 leading-snug", "text-xs text-zinc-500 leading-snug")}>{revenue.disclaimer}</div>
        </>
      )}

      {abData && (
        <div className="pt-2 border-t border-zinc-800 space-y-1.5">
          <div className={tc(theme, "text-xs font-bold uppercase tracking-wide text-zinc-500", "text-xs font-bold uppercase tracking-wide text-zinc-500")}>
            A/B Test Results
            {abData.winner && <span className="text-brand-teal"> — Variant {abData.winner.toUpperCase()} winning</span>}
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {(["a", "b"] as const).map((v) => (
              <div key={v} className={tc(theme, "rounded bg-zinc-900 border border-zinc-800 p-1.5", "rounded bg-white border border-zinc-300 p-1.5")}>
                <div className={tc(theme, "text-xs font-semibold text-zinc-300", "text-xs font-semibold text-zinc-700")}>Variant {v.toUpperCase()}</div>
                <div className="text-xs">${abData.results[v].revenue.toLocaleString()}</div>
                <div className="text-xs text-zinc-500">
                  {abData.results[v].conversion_rate}% conv · {abData.results[v].audience_count} sent
                </div>
              </div>
            ))}
          </div>
          <div className={tc(theme, "text-xs text-zinc-600 leading-snug", "text-xs text-zinc-500 leading-snug")}>{abData.disclaimer}</div>
        </div>
      )}
    </div>
  );
}

function RecipientPicker({
  theme,
  channel,
  crmData,
  abCandidates,
  onLaunch,
}: {
  theme: Theme;
  channel: EmailChannel;
  crmData: CrmData | null;
  abCandidates: EmailTemplate[];
  onLaunch: (input: { campaign_type: string; params: Record<string, unknown>; label: string; abVariantBTemplateId?: string }) => void;
}) {
  const [sendMode, setSendMode] = useState<"mass" | "individual">("mass");
  const [campaignType, setCampaignType] = useState("general");
  const [previewCount, setPreviewCount] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Array<{ id: string; entity_type: string; name: string }>>([]);
  const [selectedTarget, setSelectedTarget] = useState<{ id: string; name: string } | null>(null);
  const [abEnabled, setAbEnabled] = useState(false);
  const [variantBId, setVariantBId] = useState("");

  const types = crmData?.campaigns.available_types ?? [];

  useEffect(() => {
    if (sendMode !== "mass") return;
    previewCrmAudience(campaignType, {}).then((r) => setPreviewCount(r.count)).catch(() => setPreviewCount(null));
  }, [sendMode, campaignType]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (sendMode === "individual" && searchQuery.trim()) {
        searchRecipients(searchQuery).then(setSearchResults).catch(() => setSearchResults([]));
      } else {
        setSearchResults([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [searchQuery, sendMode]);

  return (
    <div className={tc(theme, "rounded-lg border border-zinc-800 bg-brand-charcoal p-3", "rounded-lg border border-zinc-300 bg-zinc-50 p-3")}>
      <div className={tc(theme, "text-xs font-bold uppercase tracking-wide text-zinc-400 mb-2", "text-xs font-bold uppercase tracking-wide text-zinc-500 mb-2")}>
        Send To (from the CRM)
      </div>

      <div className="flex gap-1.5 mb-2.5">
        <WorkButton type="submit"
          onClick={() => setSendMode("mass")}
          className={sendMode === "mass" ? "text-xs px-2.5 py-1 rounded-md bg-brand-teal text-black font-semibold" : tc(theme, "text-xs px-2.5 py-1 rounded-md border border-zinc-700 text-zinc-400", "text-xs px-2.5 py-1 rounded-md border border-zinc-300 text-zinc-600")}
        >
          Mass (Segment)
        </WorkButton>
        <WorkButton type="submit"
          onClick={() => setSendMode("individual")}
          className={sendMode === "individual" ? "text-xs px-2.5 py-1 rounded-md bg-brand-teal text-black font-semibold" : tc(theme, "text-xs px-2.5 py-1 rounded-md border border-zinc-700 text-zinc-400", "text-xs px-2.5 py-1 rounded-md border border-zinc-300 text-zinc-600")}
        >
          Individual
        </WorkButton>
      </div>

      {sendMode === "mass" ? (
        <div className="space-y-2">
          <WorkField label="Campaign Type"><WorkSelect
            value={campaignType}
            onChange={(e) => setCampaignType(e.target.value)}
            className={tc(theme, "w-full h-8 px-2 text-xs rounded bg-zinc-900 border border-zinc-700", "w-full h-8 px-2 text-xs rounded bg-white border border-zinc-300")}
          >
            {types.filter((t) => t.key !== "individual").map((t) => (
              <option key={t.key} value={t.key}>{t.name}</option>
            ))}
          </WorkSelect></WorkField>
          {previewCount !== null && (
            <div className={tc(theme, "text-xs text-zinc-400", "text-xs text-zinc-600")}>{previewCount} recipient(s)</div>
          )}

          {abCandidates.length > 0 && (
            <div className={tc(theme, "rounded-md border border-zinc-800 p-2 space-y-1.5", "rounded-md border border-zinc-300 p-2 space-y-1.5")}>
              <label className="flex items-center gap-1.5 text-xs cursor-pointer">
                <WorkInput type="checkbox" checked={abEnabled} onChange={(e) => setAbEnabled(e.target.checked)} />
                <span className={tc(theme, "text-zinc-300", "text-zinc-700")}>🔀 A/B Test against a second message</span>
              </label>
              {abEnabled && (
                <WorkField label="Variant BId"><WorkSelect
                  value={variantBId}
                  onChange={(e) => setVariantBId(e.target.value)}
                  className={tc(theme, "w-full h-7 px-2 text-xs rounded bg-zinc-900 border border-zinc-700", "w-full h-7 px-2 text-xs rounded bg-white border border-zinc-300")}
                >
                  <option value="">Choose Variant B…</option>
                  {abCandidates.map((t) => (
                    <option key={t.id} value={t.id}>{t.name}</option>
                  ))}
                </WorkSelect></WorkField>
              )}
              <div className={tc(theme, "text-xs text-zinc-600", "text-xs text-zinc-500")}>
                A real 50/50 split, deterministic per recipient. Set up before sending -- variants lock once the campaign activates.
              </div>
            </div>
          )}

          <WorkButton type="submit"
            onClick={() => {
              const t = types.find((x) => x.key === campaignType);
              onLaunch({
                campaign_type: campaignType,
                params: {},
                label: t?.name ?? campaignType,
                abVariantBTemplateId: abEnabled && variantBId ? variantBId : undefined,
              });
            }}
            className="w-full text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold hover:brightness-95 transition"
          >
            Use as Campaign →
          </WorkButton>
        </div>
      ) : (
        <div className="space-y-2">
          <WorkField label="Search Customer or Lead"><WorkInput
            value={searchQuery}
            onChange={(e) => {
              setSearchQuery(e.target.value);
              setSelectedTarget(null);
            }}
            placeholder="Search Customer or Lead…"
            className={tc(theme, "w-full h-8 px-2 text-xs rounded bg-zinc-900 border border-zinc-700", "w-full h-8 px-2 text-xs rounded bg-white border border-zinc-300")}
          /></WorkField>
          {searchResults.length > 0 && !selectedTarget && (
            <div className={tc(theme, "rounded border border-zinc-800 divide-y divide-zinc-800 max-h-32 overflow-y-auto", "rounded border border-zinc-300 divide-y divide-zinc-200 max-h-32 overflow-y-auto")}>
              {searchResults.map((r) => (
                <WorkButton type="submit"
                  key={r.id}
                  onClick={() => {
                    setSelectedTarget({ id: r.id, name: r.name });
                    setSearchResults([]);
                  }}
                  className={tc(theme, "w-full text-left px-2 py-1 text-xs text-zinc-300 hover:bg-zinc-800 transition", "w-full text-left px-2 py-1 text-xs text-zinc-700 hover:bg-zinc-100 transition")}
                >
                  {r.name} <span className="text-zinc-500">({r.id})</span>
                </WorkButton>
              ))}
            </div>
          )}
          {selectedTarget && (
            <div className={tc(theme, "text-xs text-zinc-300 px-2 py-1 rounded bg-zinc-900 border border-zinc-700", "text-xs text-zinc-700 px-2 py-1 rounded bg-white border border-zinc-300")}>
              Selected: {selectedTarget.name} ({selectedTarget.id})
            </div>
          )}
          <WorkButton type="submit"
            disabled={!selectedTarget}
            onClick={() => selectedTarget && onLaunch({ campaign_type: "individual", params: { target_id: selectedTarget.id }, label: selectedTarget.name })}
            className="w-full text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold hover:brightness-95 transition disabled:opacity-40"
          >
            Use as Campaign →
          </WorkButton>
        </div>
      )}
      <div className={tc(theme, "text-xs text-zinc-600 mt-2", "text-xs text-zinc-500 mt-2")}>
        Channel: {channel === "sms" ? "SMS" : "Email"} -- creates a draft campaign with this message attached (activate it from the CRM's Campaigns tab).
      </div>
    </div>
  );
}

// Mailchimp-style left-hand library pane -- Sam's "uses all the space" complaint was
// largely about the old single-column layout burying the template list in a tiny
// <select>. This is now a real, always-visible, searchable/filterable list (search +
// All/Mine/Email/SMS tabs), same "browse on the left, work on the right" shape as
// Mailchimp's own Campaigns list, or this codebase's own ListsTab (session 82).
function LibraryPane({
  theme,
  templates,
  selectedId,
  onSelect,
  filter,
  onFilterChange,
  search,
  onSearchChange,
  onNew,
  onWizard,
  creating,
}: {
  theme: Theme;
  templates: EmailTemplate[];
  selectedId: string | null;
  onSelect: (t: EmailTemplate) => void;
  filter: LibraryFilter;
  onFilterChange: (f: LibraryFilter) => void;
  search: string;
  onSearchChange: (s: string) => void;
  onNew: () => void;
  onWizard: () => void;
  creating: boolean;
}) {
  const filterTabs: Array<{ key: LibraryFilter; label: string }> = [
    { key: "all", label: "All" },
    { key: "mine", label: "Mine" },
    { key: "email", label: "Email" },
    { key: "sms", label: "SMS" },
  ];

  return (
    <div className={tc(theme, "w-72 shrink-0 flex flex-col border-r border-zinc-800 bg-brand-charcoal", "w-72 shrink-0 flex flex-col border-r border-zinc-300 bg-zinc-50")}>
      <div className={tc(theme, "p-3 space-y-2 border-b border-zinc-800 shrink-0", "p-3 space-y-2 border-b border-zinc-300 shrink-0")}>
        <div className="flex gap-1.5">
          <WorkButton type="submit"
            onClick={onNew}
            disabled={creating}
            className="flex-1 text-xs px-2.5 py-1.5 rounded-md bg-brand-teal text-black font-semibold hover:brightness-95 transition disabled:opacity-50"
          >
            + New
          </WorkButton>
          <WorkButton type="submit"
            onClick={onWizard}
            className={tc(theme, "flex-1 text-xs px-2.5 py-1.5 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition", "flex-1 text-xs px-2.5 py-1.5 rounded-md border border-zinc-300 text-zinc-700 hover:text-black transition")}
          >
            ✨ AI Wizard
          </WorkButton>
        </div>
        <WorkField label="Search messages"><WorkInput
          value={search}
          onChange={(e) => onSearchChange(e.target.value)}
          placeholder="Search messages…"
          className={tc(theme, "w-full h-8 px-2 text-xs rounded bg-zinc-900 border border-zinc-700", "w-full h-8 px-2 text-xs rounded bg-white border border-zinc-300")}
        /></WorkField>
        <div className="flex gap-1">
          {filterTabs.map((f) => (
            <WorkButton type="submit"
              key={f.key}
              onClick={() => onFilterChange(f.key)}
              className={
                filter === f.key
                  ? "text-xs px-2 py-0.5 rounded-full bg-brand-blue text-white font-semibold"
                  : tc(
                      theme,
                      "text-xs px-2 py-0.5 rounded-full border border-zinc-700 text-zinc-400 hover:text-white transition",
                      "text-xs px-2 py-0.5 rounded-full border border-zinc-300 text-zinc-600 hover:text-black transition"
                    )
              }
            >
              {f.label}
            </WorkButton>
          ))}
        </div>
      </div>

      <div className="flex-1 min-h-0 overflow-y-auto">
        {templates.length === 0 ? (
          <div className={tc(theme, "text-xs text-zinc-600 p-3", "text-xs text-zinc-500 p-3")}>
            No messages match this filter yet.
          </div>
        ) : (
          templates.map((t) => (
            <button
              key={t.id}
              onClick={() => onSelect(t)}
              className={
                t.id === selectedId
                  ? tc(theme, "w-full text-left px-3 py-2 border-b border-zinc-800 bg-zinc-900", "w-full text-left px-3 py-2 border-b border-zinc-200 bg-white")
                  : tc(
                      theme,
                      "w-full text-left px-3 py-2 border-b border-zinc-800 hover:bg-zinc-900/60 transition",
                      "w-full text-left px-3 py-2 border-b border-zinc-200 hover:bg-zinc-100 transition"
                    )
              }
            >
              <div className="flex items-center gap-1.5 mb-0.5">
                <span className="text-xs">{t.channel === "sms" ? "💬" : "✉"}</span>
                <span className={tc(theme, "text-xs font-semibold text-zinc-200 truncate flex-1", "text-xs font-semibold text-zinc-800 truncate flex-1")}>
                  {t.name}
                </span>
                {t.ai_generated && <span className="text-xs px-1 py-0.5 rounded bg-brand-teal/20 text-brand-teal font-semibold shrink-0">AI</span>}
              </div>
              <div className={tc(theme, "text-xs text-zinc-500 truncate", "text-xs text-zinc-500 truncate")}>
                {t.channel === "sms" ? (t.sms_body || "(empty)") : (t.subject || "(no subject)")}
              </div>
              <div className={tc(theme, "text-xs text-zinc-600 mt-0.5", "text-xs text-zinc-500 mt-0.5")}>
                {t.linked_campaign_id ? "Linked to a campaign" : "Not linked"} &middot; {fmtDate(t.updated_at)}
              </div>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

export function EmailSmsBuilder({ theme }: { theme: Theme }) {
  const session = getSession();
  const [overview, setOverview] = useState<EmailSmsOverview | null>(null);
  const [channel, setChannel] = useState<EmailChannel>("email");
  const [mode, setMode] = useState<Mode>("wizard");
  const [blockCatalog, setBlockCatalog] = useState<BlockType[]>([]);
  const [allTemplates, setAllTemplates] = useState<EmailTemplate[]>([]);
  const [libraryFilter, setLibraryFilter] = useState<LibraryFilter>("all");
  const [librarySearch, setLibrarySearch] = useState("");
  const [crmData, setCrmData] = useState<CrmData | null>(null);
  const [lists, setLists] = useState<MarketingList[]>([]);
  const [template, setTemplate] = useState<EmailTemplate | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [wizardGoal, setWizardGoal] = useState("");
  const [wizardAudience, setWizardAudience] = useState("");
  const [wizardTone, setWizardTone] = useState("friendly and professional");
  const [drafting, setDrafting] = useState(false);
  const [launchMsg, setLaunchMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const saveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const skipNextSave = useRef(true);

  const blockTypesByKey = useMemo(() => {
    const m = new Map<string, BlockType>();
    blockCatalog.forEach((b) => m.set(b.key, b));
    return m;
  }, [blockCatalog]);

  function refreshAll() {
    fetchEmailSmsOverview().then(setOverview).catch(() => {});
    listAllTemplates().then(setAllTemplates).catch(() => {});
  }

  useEffect(() => {
    fetchBlockTypes().then(setBlockCatalog).catch(() => {});
    fetchCrmData().then(setCrmData).catch(() => {});
    listAllLists().then(setLists).catch(() => {});
    refreshAll();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const visibleTemplates = useMemo(() => {
    let list = allTemplates;
    if (libraryFilter === "mine") list = list.filter((t) => t.created_by === session?.employeeId);
    else if (libraryFilter === "email" || libraryFilter === "sms") list = list.filter((t) => t.channel === libraryFilter);
    if (librarySearch.trim()) {
      const q = librarySearch.trim().toLowerCase();
      list = list.filter((t) => t.name.toLowerCase().includes(q) || (t.subject ?? "").toLowerCase().includes(q));
    }
    return [...list].sort((a, b) => (a.updated_at < b.updated_at ? 1 : -1));
  }, [allTemplates, libraryFilter, librarySearch, session?.employeeId]);

  // Debounced auto-save, same pattern as ReportDashboardBuilder's -- edits feel
  // instant locally, backend catches up shortly after.
  useEffect(() => {
    if (!template) return;
    if (skipNextSave.current) {
      skipNextSave.current = false;
      return;
    }
    if (saveTimer.current) clearTimeout(saveTimer.current);
    saveTimer.current = setTimeout(() => {
      setSaving(true);
      updateTemplate(template.id, {
        name: template.name,
        subject: template.subject,
        preheader: template.preheader,
        blocks: template.blocks,
        sms_body: template.sms_body,
      })
        .then(() => refreshAll())
        .catch(() => {})
        .finally(() => setSaving(false));
    }, 700);
    return () => {
      if (saveTimer.current) clearTimeout(saveTimer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [template]);

  function selectTemplate(t: EmailTemplate) {
    skipNextSave.current = true;
    setTemplate(t);
    setChannel(t.channel);
    setMode("builder");
  }

  // The visual canvas (EmailBuilderCanvas) owns persistence -- it PATCHes the template
  // itself via updateTemplate and hands the fresh copy back here. We adopt it as the
  // board's current template (keeping the library selection/highlight in sync) and
  // refresh the library, and set skipNextSave so the board's own debounced auto-save
  // doesn't redundantly re-PATCH what the canvas just saved.
  function handleTemplateChange(t: EmailTemplate) {
    skipNextSave.current = true;
    setTemplate(t);
    setChannel(t.channel);
    setMode("builder");
    refreshAll();
  }

  // "+ New" and "AI Wizard" both drop into the canvas's Step 1 (Campaign Setup & AI
  // prompt) by clearing the selection; the canvas creates/drafts the real template
  // from there and calls handleTemplateChange.
  function startSetup() {
    setTemplate(null);
    setMode("wizard");
  }

  async function startNew() {
    setLoading(true);
    setError(null);
    try {
      const t = await createTemplate(channel, channel === "sms" ? "New Text Message" : "New Email");
      skipNextSave.current = true;
      setTemplate(t);
      setMode("builder");
      refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create a new template.");
    } finally {
      setLoading(false);
    }
  }

  async function handleWizardDraft() {
    setDrafting(true);
    setError(null);
    try {
      const t = await draftFromWizard({
        channel,
        goal: wizardGoal,
        audience_description: wizardAudience,
        tone: wizardTone,
      });
      skipNextSave.current = true;
      setTemplate(t);
      setMode("builder");
      refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't reach the AI wizard.");
    } finally {
      setDrafting(false);
    }
  }

  function addBlock(blockKey: string) {
    if (!template) return;
    setTemplate({ ...template, blocks: [...template.blocks, { block_key: blockKey, fields: {} }] });
  }

  function updateBlockField(index: number, key: string, value: string) {
    if (!template) return;
    const blocks = template.blocks.map((b, i) => (i === index ? { ...b, fields: { ...b.fields, [key]: value } } : b));
    setTemplate({ ...template, blocks });
  }

  function removeBlock(index: number) {
    if (!template) return;
    setTemplate({ ...template, blocks: template.blocks.filter((_, i) => i !== index) });
  }

  function reorderBlocks(fromKey: string, toIndex: number) {
    if (!template) return;
    const fromIndex = Number(fromKey);
    if (Number.isNaN(fromIndex) || fromIndex === toIndex) return;
    const blocks = [...template.blocks];
    const [moved] = blocks.splice(fromIndex, 1);
    blocks.splice(toIndex, 0, moved);
    setTemplate({ ...template, blocks });
  }

  async function handleLaunch(input: { campaign_type: string; params: Record<string, unknown>; label: string; abVariantBTemplateId?: string }) {
    if (!template) return;
    setLaunchMsg(null);
    setError(null);
    try {
      const campaign = await createCrmCampaign({
        campaign_type: input.campaign_type,
        name: `${template.name} → ${input.label}`,
        channel,
        params: input.params,
        linked_template_id: template.id,
      });
      let msg = "Draft campaign created -- activate it from the CRM's Campaigns tab.";
      if (input.abVariantBTemplateId && campaign.id) {
        const abResult = await setAbVariant(String(campaign.id), input.abVariantBTemplateId);
        msg = abResult.error
          ? `Draft campaign created, but the A/B variant couldn't be set: ${abResult.error}`
          : "Draft A/B test campaign created -- activate it from the CRM's Campaigns tab.";
      }
      setLaunchMsg(msg);
      refreshAll();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Couldn't create that campaign.");
    }
  }

  // A/B variant candidates: same channel, not the message currently being edited.
  const abCandidates = useMemo(
    () => (template ? allTemplates.filter((t) => t.channel === channel && t.id !== template.id) : []),
    [allTemplates, channel, template]
  );

  const segInfo = template?.sms_body ? smsSegmentInfo(template.sms_body) : null;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <KpiStrip theme={theme} overview={overview} />

      {error && <div className="mx-3 mt-2 text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
      {launchMsg && <div className="mx-3 mt-2 text-xs px-3 py-2 rounded-lg bg-emerald-500/15 border border-emerald-500/40 text-emerald-300">{launchMsg}</div>}

      <div className="flex-1 min-h-0 flex mt-3">
        <LibraryPane
          theme={theme}
          templates={visibleTemplates}
          selectedId={template?.id ?? null}
          onSelect={selectTemplate}
          filter={libraryFilter}
          onFilterChange={setLibraryFilter}
          search={librarySearch}
          onSearchChange={setLibrarySearch}
          onNew={startSetup}
          onWizard={startSetup}
          creating={loading}
        />

        <EmailBuilderCanvas
          theme={theme}
          template={template}
          channel={channel}
          blockCatalog={blockCatalog}
          lists={lists}
          crmData={crmData}
          abCandidates={abCandidates}
          onTemplateChange={handleTemplateChange}
          onChannelChange={setChannel}
          onLaunch={handleLaunch}
        />
      </div>
    </div>
  );
}
