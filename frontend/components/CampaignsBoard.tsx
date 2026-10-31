"use client";
import { WorkButton } from "./WorkspaceUi";

// Marketing's "Campaigns" item (Marketing Growth Platform, session 113 follow-up).
// Sam confirmed splitting Campaigns back out of the merged "CRM" item (session 79/81's
// own deliberate Hubspot-style merge) into its own dedicated, focused Top Menu item,
// per his later 12-item Growth Platform menu spec, which lists Campaigns as its own
// thing distinct from CRM. This is NOT a rebuild -- it reuses the exact same
// CampaignsTab/CampaignDetailView components components/MarketingCRMBoard.tsx's own
// Campaigns tab already uses (exported from that file for this exact purpose), fed by
// a leaner fetch (backend/core/marketing_menu.py's new campaigns() function, same real
// _campaigns(role) computation crm() already calls) that skips Pipeline/Lists/
// Opportunities/Customer 360/Smart Audiences/Lead Scoring for someone who just wants
// campaigns directly. The CRM workspace's own Campaigns tab is completely untouched --
// this is a second, independent way to reach the same real campaign CRUD/stats/A-B-
// test/revenue actions (backend/core/campaigns_api.py), not a replacement for it.
import { useEffect, useState } from "react";
import { fetchCampaignsData, type CampaignsData } from "@/lib/marketingCrm";
import { CampaignsTab } from "@/components/MarketingCRMBoard";

type Theme = "dark" | "light";

export function CampaignsBoard({ theme, onDraftOpenChange, onSavingChange }: { theme: Theme; onDraftOpenChange?: (open: boolean) => void; onSavingChange?: (saving:boolean)=>void }) {
  const [data, setData] = useState<CampaignsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [revision, setRevision] = useState(0);
  const refresh = () => setRevision(value => value + 1);

  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    fetchCampaignsData()
      .then(result => { if (live) setData(result); })
      .catch(err => { if (live) setError(err instanceof Error ? err.message : "Couldn't load campaigns."); })
      .finally(() => { if (live) setLoading(false); });
    return () => { live = false; };
  }, [revision]);

  if (!data) {
    return <div className="p-4 text-sm">
      {loading ? <p role="status">Loading campaigns…</p> : <>
        <p role="alert">{error || "Campaign records are unavailable."}</p>
        <WorkButton type="submit" className="min-h-11 underline" onClick={refresh}>Retry campaigns</WorkButton>
      </>}
    </div>;
  }

  if (!data) return null;

  return (
    <div className="flex-1 min-h-0 flex flex-col">
      <div className="px-3 pt-3 shrink-0">
        <div className="text-base font-brand">Campaigns</div>
        <div className="text-xs text-zinc-500">
          Review drafts, prepare campaigns, and check recorded outcomes. Opening this workspace does not send messages.
        </div>
      </div>
      {loading && <p role="status" className="px-3 py-2 text-sm">Updating campaign records…</p>}
      {error && <div className="px-3 py-2 text-sm">
        <p role="alert">Campaign records could not be refreshed: {error}. Reload before continuing.</p>
        <WorkButton type="submit" className="min-h-11 underline" onClick={refresh}>Retry campaigns</WorkButton>
      </div>}
      <fieldset disabled={loading || Boolean(error)} className="min-w-0 border-0 p-0 m-0" aria-label="Campaign work">
      <CampaignsTab
        theme={theme}
        campaigns={data}
        onDraftOpenChange={onDraftOpenChange}
        onSavingChange={onSavingChange}
        prefillType={null}
        onClearPrefill={() => {}}
        onRefresh={refresh}
      />
      </fieldset>
    </div>
  );
}
