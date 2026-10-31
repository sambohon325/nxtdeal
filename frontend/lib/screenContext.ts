// Builds the small, human-readable summary of "what's on screen" that gets sent to
// POST /help/ask (2026-07-13, session 34) so the help assistant's answers are grounded
// in the real workspace panel content rather than just the department tab name. This is
// deliberately a short summary, not a raw entity dump — see core/help_api.py's
// docstring for why (same "don't send more graph data to OpenAI than necessary"
// posture core/ai_tools.py already flags for the main assistant).

import type { Artifact } from "@/lib/useArtifactPanel";
import type { ScreenContext } from "@/components/HelpWidget";

export function buildScreenContext(artifact: Artifact | undefined): ScreenContext {
  if (!artifact) return null;

  const base = { artifact_type: artifact.type, title: artifact.title };

  switch (artifact.type) {
    case "dashboard":
      return { ...base, summary: `${artifact.data.length} data point(s) shown.` };
    case "profile":
      return { ...base, summary: `Viewing entity ${artifact.entityId}.` };
    case "asset_detail":
      return { ...base, summary: `Asset status: ${artifact.asset.status}.` };
    case "asset_list":
      return { ...base, summary: `${artifact.mode} list, ${artifact.assets.length} asset(s).` };
    case "campaign_detail":
      return { ...base, summary: `Campaign status: ${artifact.campaign.status}.` };
    case "campaign_list":
      return { ...base, summary: `${artifact.mode} list, ${artifact.campaigns.length} campaign(s).` };
    case "website_detail":
      return { ...base, summary: `Website status: ${artifact.website.status}.` };
    case "website_list":
      return { ...base, summary: `${artifact.mode} list, ${artifact.websites.length} website(s).` };
    case "deal_detail":
      return {
        ...base,
        summary:
          `Deal status: ${artifact.deal.status}, financing_status: ${artifact.deal.financing_status}, ` +
          `${artifact.deal.scenarios.length} scenario(s).`,
      };
    case "deal_list":
      return { ...base, summary: `${artifact.mode} list, ${artifact.deals.length} deal(s).` };
    case "roster":
      return { ...base, summary: `${artifact.records.length} employee record(s).` };
    case "audit":
      return { ...base, summary: `${artifact.dashboard.total_events} total audit event(s).` };
    case "compliance_alerts_list":
      return { ...base, summary: `${artifact.alerts.length} compliance alert(s).` };
    case "readiness_score":
      return { ...base, summary: `Readiness score: ${artifact.score}.` };
    case "performance_rank":
      return { ...base, summary: `Performance rank: ${artifact.rank}.` };
    case "growth_opportunities":
      return { ...base, summary: `${artifact.opportunities.length} opportunity(ies) listed.` };
    default:
      return base;
  }
}
