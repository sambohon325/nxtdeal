"use client";
import { WorkButton, WorkSelect, WorkInput, WorkTextarea } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Marketing's "Advertising" Top Menu item (session 83). Sam: "we also need to have an
// advertising dash, this will be a advertising tool to start meta and google ad
// campaings that include inventory and allow ai recommendations / buidling, or
// granular control."
//
// A KPI strip (by status/platform), a campaign list, and a builder that supports
// either an AI-drafted starting point (headline/primary text/description/disclaimer/
// targeting suggestion, editable before saving) or fully manual granular entry --
// one form, not two parallel flows. Launching is an honestly-labeled SIMULATED action
// (see core/advertising.py's module docstring) -- no real Meta/Google Ads API access
// exists in this sandbox. Mounted by components/MenuDashPanel.tsx the same way
// MarketingCRMBoard.tsx/EmailSmsBuilder.tsx/SocialReputationBoard.tsx are.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useMemo, useState, type DragEvent } from "react";
import {
  listAdPlatforms,
  listAdObjectives,
  generateAdRecommendation,
  createAdCampaign,
  listAdCampaigns,
  getAdCampaign,
  updateAdCampaign,
  launchAdCampaign,
  pauseAdCampaign,
  completeAdCampaign,
  cancelAdCampaign,
  type AdPlatform,
  type AdObjective,
  type AdCampaign,
  type AdLinkedVehicle,
} from "@/lib/advertising";
import { searchInventoryForPost } from "@/lib/socialReputation";
import { VISUALIZATION_DRAG_TYPE, type VisualizationDropPayload } from "@/lib/useVisualizationWorkspace";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

// Same brand-ribbon order as components/DepartmentWorkflowButtons.tsx's RIBBON_COLORS.
const KPI_RIBBON = PRODUCT_ACCENT_COLORS;

const PLATFORM_LABELS: Record<string, string> = { meta: "Meta (Facebook/Instagram)", google: "Google Ads" };
const PLATFORM_ICONS: Record<string, string> = { meta: "📘", google: "🔍" };

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-zinc-800 text-zinc-400",
  active: "bg-green-900 text-green-300",
  paused: "bg-amber-900 text-amber-300",
  completed: "bg-blue-900 text-blue-300",
  cancelled: "bg-zinc-800 text-zinc-500",
};

function DragHandle({
  theme,
  fieldPath,
  sourceLabel,
  rows,
  numericColumns,
  labelColumn,
}: {
  theme: Theme;
  fieldPath: string[];
  sourceLabel: string;
  rows: Record<string, unknown>[];
  numericColumns: string[];
  labelColumn: string;
}) {
  if (rows.length === 0 || numericColumns.length === 0) return null;

  function handleDragStart(event: DragEvent<HTMLButtonElement>) {
    const payload: VisualizationDropPayload = {
      department: "Marketing",
      itemKey: "advertising",
      fieldPath,
      sourceLabel,
      rows,
      numericColumns,
      labelColumn,
    };
    event.dataTransfer.setData(VISUALIZATION_DRAG_TYPE, JSON.stringify(payload));
    event.dataTransfer.effectAllowed = "copy";
  }

  return (
    <WorkButton type="submit"
      draggable
      onDragStart={handleDragStart}
      title="Drag into the Workspace to build a chart, then pin it"
      className={tc(
        theme,
        "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-700 text-zinc-500 hover:text-white hover:border-zinc-500 transition cursor-grab active:cursor-grabbing",
        "text-xs px-2 py-0.5 rounded border border-dashed border-zinc-400 text-zinc-600 hover:text-black hover:border-zinc-600 transition cursor-grab active:cursor-grabbing"
      )}
    >
      ⠿ Drag to Workspace
    </WorkButton>
  );
}

export function AdvertisingBoard({ theme }: { theme: Theme }) {
  const [platforms, setPlatforms] = useState<AdPlatform[]>([]);
  const [objectives, setObjectives] = useState<AdObjective[]>([]);
  const [campaigns, setCampaigns] = useState<AdCampaign[]>([]);
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<"list" | "new">("list");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    listAdCampaigns()
      .then(setCampaigns)
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    listAdPlatforms().then(setPlatforms);
    listAdObjectives().then(setObjectives);
    refresh();
  }, []);

  const byStatus = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const c of campaigns) counts[c.status] = (counts[c.status] || 0) + 1;
    return counts;
  }, [campaigns]);

  const byPlatform = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const c of campaigns) counts[c.platform] = (counts[c.platform] || 0) + 1;
    return counts;
  }, [campaigns]);

  const selected = campaigns.find((c) => c.id === selectedId) || null;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      {/* KPI strip */}
      <div className={tc(theme, "grid grid-cols-5 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-5 gap-3 p-4 border-b border-zinc-200")}>
        {[
          { label: "Total Campaigns", value: campaigns.length },
          { label: "Active", value: byStatus.active || 0 },
          { label: "Draft", value: byStatus.draft || 0 },
          { label: "Meta", value: byPlatform.meta || 0 },
          { label: "Google", value: byPlatform.google || 0 },
        ].map((k, i) => (
          <div key={k.label} className={tc(theme, "relative overflow-hidden rounded-lg border border-black/20 bg-brand-charcoal p-3 pl-4", "relative overflow-hidden rounded-lg border border-zinc-200 bg-zinc-50 p-3 pl-4")}>
            <span className="nxt-accent absolute left-0 top-0 bottom-0 w-2.5"
              style={{ background: KPI_RIBBON[i % KPI_RIBBON.length], clipPath: "polygon(0 0, 100% 0, 45% 100%, 0 100%)" }}
            />
            <div className="text-2xl font-semibold">{k.value}</div>
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">{k.label}</div>
          </div>
        ))}
      </div>

      <div className={tc(theme, "border-b border-zinc-800 px-4 py-2 flex items-center justify-between", "border-b border-zinc-200 px-4 py-2 flex items-center justify-between")}>
        <div className="flex items-center gap-2">
          {(["list", "new"] as const).map((v) => (
            <WorkButton data-work-view aria-pressed={view === v} type="submit"
              key={v}
              onClick={() => { setView(v); setSelectedId(null); }}
              className={
                view === v
                  ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                  : tc(theme, "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition", "text-xs px-2.5 py-1 rounded-md text-zinc-600 hover:text-black hover:bg-zinc-200 transition")
              }
            >
              {v === "list" ? "Campaigns" : "+ New Campaign"}
            </WorkButton>
          ))}
        </div>
        <DragHandle
          theme={theme}
          fieldPath={["by_status"]}
          sourceLabel="Ad Campaigns by Status"
          rows={Object.entries(byStatus).map(([status, count]) => ({ status, count }))}
          numericColumns={["count"]}
          labelColumn="status"
        />
      </div>

      <div className="flex-1 overflow-y-auto p-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : selected ? (
          <CampaignDetail theme={theme} campaign={selected} onChanged={refresh} onBack={() => setSelectedId(null)} />
        ) : view === "new" ? (
          <NewCampaignForm
            theme={theme}
            platforms={platforms}
            objectives={objectives}
            onCreated={(id) => { refresh(); setSelectedId(id); setView("list"); }}
          />
        ) : (
          <CampaignList theme={theme} campaigns={campaigns} onSelect={setSelectedId} />
        )}
      </div>
    </div>
  );
}

function CampaignList({ theme, campaigns, onSelect }: { theme: Theme; campaigns: AdCampaign[]; onSelect: (id: string) => void }) {
  if (campaigns.length === 0) {
    return <div className="text-sm text-zinc-500">No ad campaigns yet -- use "+ New Campaign" to start one.</div>;
  }

  return (
    <div className="space-y-2">
      {campaigns.map((c) => (
        <button
          key={c.id}
          onClick={() => onSelect(c.id)}
          className={tc(
            theme,
            "w-full text-left rounded-lg border border-black/20 bg-brand-charcoal p-3 hover:border-zinc-600 transition",
            "w-full text-left rounded-lg border border-zinc-200 bg-zinc-50 p-3 hover:border-zinc-400 transition"
          )}
        >
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span>{PLATFORM_ICONS[c.platform]}</span>
              <span className="text-sm font-medium">{c.name}</span>
              {c.ai_generated && <span className="text-xs px-1.5 py-0.5 rounded bg-purple-900 text-purple-300">AI</span>}
            </div>
            <span className={`text-xs px-1.5 py-0.5 rounded uppercase ${STATUS_COLORS[c.status] || "bg-zinc-800 text-zinc-400"}`}>{c.status}</span>
          </div>
          <div className="text-xs text-zinc-500 mt-1">{c.objective} {c.daily_budget ? `· $${c.daily_budget}/day` : ""}</div>
        </button>
      ))}
    </div>
  );
}

function CampaignDetail({
  theme,
  campaign,
  onChanged,
  onBack,
}: {
  theme: Theme;
  campaign: AdCampaign;
  onChanged: () => void;
  onBack: () => void;
}) {
  const [full, setFull] = useState<AdCampaign | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    getAdCampaign(campaign.id).then(setFull);
  }, [campaign.id]);

  const c = full || campaign;

  async function act(fn: (id: string) => Promise<AdCampaign>) {
    setBusy(true);
    try {
      const updated = await fn(c.id);
      setFull(updated);
      onChanged();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-2xl space-y-3">
      <WorkButton type="submit" onClick={onBack} className="text-xs text-zinc-500 hover:text-white transition">← Back to campaigns</WorkButton>

      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xl">{PLATFORM_ICONS[c.platform]}</span>
          <span className="text-lg font-medium">{c.name}</span>
        </div>
        <span className={`text-xs px-2 py-1 rounded uppercase ${STATUS_COLORS[c.status] || "bg-zinc-800 text-zinc-400"}`}>{c.status}</span>
      </div>

      <div className={tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3 space-y-2", "rounded-lg border border-zinc-200 bg-zinc-50 p-3 space-y-2")}>
        <div><span className="text-xs text-zinc-500">Headline: </span><span className="text-sm">{c.headline || "—"}</span></div>
        <div><span className="text-xs text-zinc-500">Primary Text: </span><span className="text-sm">{c.primary_text || "—"}</span></div>
        <div><span className="text-xs text-zinc-500">Description: </span><span className="text-sm">{c.description || "—"}</span></div>
        <div><span className="text-xs text-zinc-500">Disclaimer: </span><span className="text-sm">{c.disclaimer || "—"}</span></div>
        <div><span className="text-xs text-zinc-500">Daily Budget: </span><span className="text-sm">{c.daily_budget ? `$${c.daily_budget}` : "—"}</span></div>
        {c.linked_vehicles && c.linked_vehicles.length > 0 && (
          <div>
            <span className="text-xs text-zinc-500">Vehicles: </span>
            <span className="text-sm">{c.linked_vehicles.map((v) => `${v.year} ${v.make} ${v.model}`).join(", ")}</span>
          </div>
        )}
      </div>

      {c.performance_note && (
        <div className={tc(theme, "text-xs text-zinc-500 rounded-md border border-dashed border-zinc-800 p-2", "text-xs text-zinc-500 rounded-md border border-dashed border-zinc-300 p-2")}>
          {c.performance_note}
        </div>
      )}

      <div className="flex items-center gap-2">
        {(c.status === "draft" || c.status === "paused") && (
          <WorkButton type="submit" variant="primary" disabled={busy} onClick={() => act(launchAdCampaign)} className="text-xs px-3 py-1.5 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
            🚀 Launch
          </WorkButton>
        )}
        {c.status === "active" && (
          <WorkButton type="submit" disabled={busy} onClick={() => act(pauseAdCampaign)} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition disabled:opacity-50">
            ⏸ Pause
          </WorkButton>
        )}
        {(c.status === "active" || c.status === "paused") && (
          <WorkButton type="submit" disabled={busy} onClick={() => act(completeAdCampaign)} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-300 hover:text-white transition disabled:opacity-50">
            ✓ Complete
          </WorkButton>
        )}
        {(c.status === "draft" || c.status === "paused") && (
          <WorkButton type="submit" variant="danger" disabled={busy} onClick={() => act(cancelAdCampaign)} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-red-400 hover:text-red-300 transition disabled:opacity-50">
            ✕ Cancel
          </WorkButton>
        )}
      </div>
    </div>
  );
}

function NewCampaignForm({
  theme,
  platforms,
  objectives,
  onCreated,
}: {
  theme: Theme;
  platforms: AdPlatform[];
  objectives: AdObjective[];
  onCreated: (id: string) => void;
}) {
  const [platform, setPlatform] = useState<AdPlatform>("meta");
  const [objective, setObjective] = useState("traffic");
  const [name, setName] = useState("");
  const [headline, setHeadline] = useState("");
  const [primaryText, setPrimaryText] = useState("");
  const [description, setDescription] = useState("");
  const [disclaimer, setDisclaimer] = useState("");
  const [dailyBudget, setDailyBudget] = useState("");
  const [audienceDesc, setAudienceDesc] = useState("");
  const [vehicleDesc, setVehicleDesc] = useState("");
  const [invQuery, setInvQuery] = useState("");
  const [invResults, setInvResults] = useState<AdLinkedVehicle[]>([]);
  const [linked, setLinked] = useState<AdLinkedVehicle[]>([]);
  const [aiGenerated, setAiGenerated] = useState(false);
  const [aiLoading, setAiLoading] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (platforms.length) setPlatform(platforms[0]);
  }, [platforms]);
  useEffect(() => {
    if (objectives.length) setObjective(objectives[0].key);
  }, [objectives]);

  const textClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleAiRecommend() {
    setAiLoading(true);
    try {
      const rec = await generateAdRecommendation({
        platform,
        objective,
        audience_description: audienceDesc || undefined,
        vehicle_description: vehicleDesc || (linked.length ? linked.map((l) => `${l.year} ${l.make} ${l.model}`).join(", ") : undefined),
      });
      setHeadline(rec.headline);
      setPrimaryText(rec.primary_text);
      setDescription(rec.description);
      setDisclaimer(rec.disclaimer);
      setAiGenerated(rec.ai_generated);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setAiLoading(false);
    }
  }

  async function handleInvSearch() {
    const results = await searchInventoryForPost(invQuery);
    setInvResults(results as AdLinkedVehicle[]);
  }

  function attachVehicle(v: AdLinkedVehicle) {
    if (!linked.find((l) => l.id === v.id)) setLinked([...linked, v]);
  }

  function removeVehicle(id: string) {
    setLinked(linked.filter((l) => l.id !== id));
  }

  async function handleSubmit() {
    setSaving(true);
    try {
      const created = await createAdCampaign({
        platform,
        objective,
        name: name || undefined,
        fields: {
          headline,
          primary_text: primaryText,
          description,
          disclaimer,
          daily_budget: dailyBudget ? Number(dailyBudget) : null,
          ai_generated: aiGenerated,
        },
        linked_vehicle_ids: linked.map((l) => l.id),
      });
      onCreated(created.id);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="max-w-xl space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="text-xs text-zinc-500">Platform</label>
          <div className="flex gap-1.5 mt-1">
            {platforms.map((p) => (
              <WorkButton type="submit"
                key={p}
                onClick={() => setPlatform(p)}
                className={
                  platform === p
                    ? "text-xs px-2.5 py-1.5 rounded-md bg-brand-blue text-white font-medium transition"
                    : "text-xs px-2.5 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition"
                }
              >
                {PLATFORM_ICONS[p]} {PLATFORM_LABELS[p]}
              </WorkButton>
            ))}
          </div>
        </div>
        <div>
          <label className="text-xs text-zinc-500">Objective</label>
          <WorkSelect aria-label="Objective" value={objective} onChange={(e) => setObjective(e.target.value)} className={`w-full mt-1 rounded-md border px-2 py-1.5 text-sm ${textClass}`}>
            {objectives.map((o) => (
              <option key={o.key} value={o.key}>{o.name}</option>
            ))}
          </WorkSelect>
        </div>
      </div>

      <div>
        <label className="text-xs text-zinc-500">Campaign Name</label>
        <WorkInput aria-label="Campaign Name" value={name} onChange={(e) => setName(e.target.value)} placeholder="New campaign name" className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>

      {/* AI recommendation inputs */}
      <div className={tc(theme, "rounded-lg border border-dashed border-zinc-700 p-3 space-y-2", "rounded-lg border border-dashed border-zinc-300 p-3 space-y-2")}>

        <WorkField label="✨ AI Recommendation (optional)"><WorkInput value={audienceDesc} onChange={(e) => setAudienceDesc(e.target.value)} placeholder="Audience, e.g. 'local families in a 25mi radius'" className={`w-full rounded-md border px-2.5 py-1.5 text-xs ${textClass}`} /></WorkField>
        <WorkField label="Vehicle(s)"><WorkInput value={vehicleDesc} onChange={(e) => setVehicleDesc(e.target.value)} placeholder="Vehicle(s), e.g. '2024 CR-V Hybrid'" className={`w-full rounded-md border px-2.5 py-1.5 text-xs ${textClass}`} /></WorkField>
        <WorkButton type="submit" onClick={handleAiRecommend} disabled={aiLoading} className="text-xs px-3 py-1.5 rounded-md bg-purple-700 text-white hover:opacity-90 transition disabled:opacity-50">
          {aiLoading ? "Drafting…" : "✨ Generate Draft"}
        </WorkButton>
      </div>

      <div>
        <label className="text-xs text-zinc-500">Headline</label>
        <WorkInput aria-label="Headline" value={headline} onChange={(e) => setHeadline(e.target.value)} className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>
      <div>
        <label className="text-xs text-zinc-500">Primary Text</label>
        <WorkTextarea aria-label="Primary Text" value={primaryText} onChange={(e) => setPrimaryText(e.target.value)} rows={3} className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>
      <div>
        <label className="text-xs text-zinc-500">Description</label>
        <WorkInput aria-label="Description" value={description} onChange={(e) => setDescription(e.target.value)} className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>
      <div>
        <label className="text-xs text-zinc-500">Disclaimer</label>
        <WorkInput aria-label="Disclaimer" value={disclaimer} onChange={(e) => setDisclaimer(e.target.value)} placeholder="Required if pricing/financing terms are mentioned" className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>
      <div>
        <label className="text-xs text-zinc-500">Daily Budget ($)</label>
        <WorkInput aria-label="Daily Budget ($)" value={dailyBudget} onChange={(e) => setDailyBudget(e.target.value)} type="number" className={`w-full mt-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} />
      </div>

      <div>
        <label className="text-xs text-zinc-500">🚗 Inventory Integration</label>
        <div className="flex gap-1.5 mt-1">
          <WorkField label="Search unsold inventory"><WorkInput value={invQuery} onChange={(e) => setInvQuery(e.target.value)} placeholder="Search unsold inventory…" className={`flex-1 rounded-md border px-3 py-1.5 text-sm ${textClass}`} /></WorkField>
          <WorkButton type="submit" onClick={handleInvSearch} className="text-xs px-3 py-1.5 rounded-md border border-zinc-700 text-zinc-400 hover:text-white transition">Search</WorkButton>
        </div>
        {invResults.length > 0 && (
          <div className={tc(theme, "mt-1.5 border border-zinc-800 rounded-md divide-y divide-zinc-800 max-h-40 overflow-y-auto", "mt-1.5 border border-zinc-200 rounded-md divide-y divide-zinc-200 max-h-40 overflow-y-auto")}>
            {invResults.map((v) => (
              <WorkButton type="submit" key={v.id} onClick={() => attachVehicle(v)} className="w-full text-left px-2.5 py-1.5 text-xs hover:bg-zinc-800/50 transition">
                {v.year} {v.make} {v.model} {v.trim} — {v.price ? `$${Number(v.price).toLocaleString()}` : "—"}
              </WorkButton>
            ))}
          </div>
        )}
        {linked.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mt-1.5">
            {linked.map((v) => (
              <span key={v.id} className="text-xs px-2 py-1 rounded bg-zinc-800 text-zinc-300 flex items-center gap-1.5">
                {v.year} {v.make} {v.model}
                <WorkButton type="submit" onClick={() => removeVehicle(v.id)} className="text-zinc-500 hover:text-white">✕</WorkButton>
              </span>
            ))}
          </div>
        )}
      </div>

      <WorkButton type="submit" variant="primary" onClick={handleSubmit} disabled={saving} className="text-xs px-4 py-2 rounded-md bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">
        {saving ? "Saving…" : "Save Draft"}
      </WorkButton>
    </div>
  );
}
