"use client";
import { WorkField } from "./WorkField";

// Shared workspace-panel rendering (session 27 — extracted out of /admin alongside
// lib/useArtifactPanel.ts so every page renders roster/audit/compliance/reset/profile/
// dashboard/readiness/network panels identically). One Artifact in, the right chunk of
// UI out.

import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useState } from "react";
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  LineChart,
  Line,
  PieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  Tooltip,
  Legend,
} from "recharts";
import { EntityProfileView } from "@/components/EntityProfile";
import type { Artifact, AudiencePreview, WebsiteSection } from "@/lib/useArtifactPanel";

export function ArtifactView({
  artifact,
  onSelectProfile,
  onConfirmReset,
  onCancelReset,
  resetLoading,
  role,
  onSelectAssetTemplate,
  onCreateAsset,
  onSelectAsset,
  onApproveAsset,
  onRejectAsset,
  onSelectCampaignType,
  onPreviewAudience,
  onCreateCampaign,
  onSelectCampaign,
  onActivateCampaign,
  onCompleteCampaign,
  onCancelCampaign,
  onCreateWebsite,
  onCreateWebsiteWizard,
  onStartWebsiteWizard,
  onAddSection,
  onRemoveSection,
  onToggleSectionLock,
  onSetWebsiteMode,
  onUpdateWebsiteAdminSettings,
  onFetchWebsiteDnsInstructions,
  onFetchWebsiteRobotsTxt,
  onSubmitWebsite,
  onSelectWebsite,
  onApproveWebsite,
  onRejectWebsite,
  onCreateDeal,
  onSelectDeal,
  onAddScenario,
  onRemoveScenario,
  onSelectScenario,
  onChooseInHouseFinancing,
  onSubmitToLender,
  onRecordLenderDecision,
  onAcceptCounteredTerms,
  onGenerateContract,
  onFundDeal,
  onCancelDeal,
  onSelectIntelligenceDepartment,
  onResolveComplianceAlert,
  onOverrideComplianceAlert,
}: {
  artifact: Artifact;
  onSelectProfile: (entityId: string) => void;
  onConfirmReset: (employeeId: string) => void;
  onCancelReset: () => void;
  resetLoading: boolean;
  // Asset/campaign workflow props are optional -- only /workspace, /admin, /readiness,
  // /network wire these up today, but any future page rendering an Artifact without
  // them (e.g. the pop-out /panel route) still satisfies ArtifactView's contract.
  role?: string;
  onSelectAssetTemplate?: (templateKey: string) => void;
  onCreateAsset?: (templateKey: string, fields: Record<string, string>, vehicleId: string) => void;
  onSelectAsset?: (assetId: string) => void;
  onApproveAsset?: (assetId: string, notes: string) => void;
  onRejectAsset?: (assetId: string, notes: string) => void;
  onSelectCampaignType?: (campaignTypeKey: string) => void;
  onPreviewAudience?: (
    campaignType: string,
    params: Record<string, unknown>
  ) => Promise<AudiencePreview | null>;
  onCreateCampaign?: (
    campaignType: string,
    name: string,
    channel: string,
    params: Record<string, unknown>,
    linkedAssetId: string
  ) => void;
  onSelectCampaign?: (campaignId: string) => void;
  onActivateCampaign?: (campaignId: string) => void;
  onCompleteCampaign?: (campaignId: string) => void;
  onCancelCampaign?: (campaignId: string) => void;
  onCreateWebsite?: (name: string, mode: "traditional" | "dealer_gpt") => void;
  onCreateWebsiteWizard?: (
    dealershipInfo: import("@/lib/useArtifactPanel").WizardDealershipInfo,
    mode: "traditional" | "dealer_gpt"
  ) => void;
  onStartWebsiteWizard?: () => void;
  onAddSection?: (
    websiteId: string,
    pageKey: string,
    sectionKey: string,
    fields: Record<string, string>
  ) => void;
  onRemoveSection?: (websiteId: string, pageKey: string, sectionIndex: number) => void;
  onToggleSectionLock?: (
    websiteId: string,
    pageKey: string,
    sectionIndex: number,
    locked: boolean
  ) => void;
  onSetWebsiteMode?: (websiteId: string, mode: "traditional" | "dealer_gpt") => void;
  onUpdateWebsiteAdminSettings?: (
    websiteId: string,
    patch: Partial<import("@/lib/useArtifactPanel").WebsiteAdminSettings>
  ) => void;
  onFetchWebsiteDnsInstructions?: (websiteId: string) => Promise<unknown>;
  onFetchWebsiteRobotsTxt?: (websiteId: string) => Promise<unknown>;
  onSubmitWebsite?: (websiteId: string) => void;
  onSelectWebsite?: (websiteId: string) => void;
  onApproveWebsite?: (websiteId: string, notes: string) => void;
  onRejectWebsite?: (websiteId: string, notes: string) => void;
  onCreateDeal?: (customerId: string, vehicleId: string, tradeInValue?: number) => void;
  onSelectDeal?: (dealId: string) => void;
  onAddScenario?: (
    dealId: string,
    label: string,
    salePrice: number,
    downPayment: number,
    termMonths: number
  ) => void;
  onRemoveScenario?: (dealId: string, scenarioId: string) => void;
  onSelectScenario?: (dealId: string, scenarioId: string) => void;
  onChooseInHouseFinancing?: (dealId: string) => void;
  onSubmitToLender?: (dealId: string, lenderId: string) => void;
  onRecordLenderDecision?: (
    dealId: string,
    decision: "approved" | "declined" | "countered",
    counteredTerms?: {
      apr: number;
      term_months: number;
      amount_financed: number;
      down_payment: number;
      monthly_payment: number;
    },
    notes?: string
  ) => void;
  onAcceptCounteredTerms?: (dealId: string) => void;
  onGenerateContract?: (dealId: string) => void;
  onFundDeal?: (dealId: string) => void;
  onCancelDeal?: (dealId: string) => void;
  onSelectIntelligenceDepartment?: (key: string) => void;
  onResolveComplianceAlert?: (alertId: string, notes?: string) => void;
  onOverrideComplianceAlert?: (alertId: string, notes: string) => void;
}) {
  // Declared unconditionally (Rules of Hooks) even though only the asset_form/
  // asset_detail/campaign_form branches below use them -- resets automatically whenever
  // a new artifact swaps in, since every call site keys ArtifactView's wrapper by
  // `artifact.id`, remounting this component fresh.
  const [chartType, setChartType] = useState<"bar" | "line" | "pie" | "donut">("bar");
  const [formFields, setFormFields] = useState<Record<string, string>>({});
  const [formVehicleId, setFormVehicleId] = useState("");
  const [reviewNotes, setReviewNotes] = useState("");
  const [campaignName, setCampaignName] = useState("");
  const [campaignChannel, setCampaignChannel] = useState("");
  const [campaignParams, setCampaignParams] = useState<Record<string, string>>({});
  const [campaignLinkedAsset, setCampaignLinkedAsset] = useState("");
  const [audiencePreview, setAudiencePreview] = useState<AudiencePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [websiteName, setWebsiteName] = useState("");
  const [websiteMode, setWebsiteMode] = useState<"traditional" | "dealer_gpt">("traditional");
  const [activePageKey, setActivePageKey] = useState("home");
  const [selectedSectionKey, setSelectedSectionKey] = useState("");
  const [sectionFields, setSectionFields] = useState<Record<string, string>>({});
  // Session 58 -- AI setup wizard form fields.
  const [wizardName, setWizardName] = useState("");
  const [wizardAddress, setWizardAddress] = useState("");
  const [wizardPhone, setWizardPhone] = useState("");
  const [wizardHours, setWizardHours] = useState("");
  const [wizardBrandingMode, setWizardBrandingMode] = useState<"independent" | "oem">("independent");
  const [wizardOemName, setWizardOemName] = useState("");
  const [wizardGoogleRating, setWizardGoogleRating] = useState("");
  const [wizardFacebook, setWizardFacebook] = useState("");
  const [wizardInstagram, setWizardInstagram] = useState("");
  // Session 58 -- Admin Settings panel (DNS/SEO/Bot/Analytics/OEM branding), plus
  // read-only DNS/robots.txt lookups fetched on demand.
  const [showAdminSettings, setShowAdminSettings] = useState(false);
  const [adminSettingsDraft, setAdminSettingsDraft] = useState<Record<string, string | boolean>>({});
  const [dnsInfo, setDnsInfo] = useState<{ note?: string; record_target?: string; record_host?: string; configured?: boolean } | null>(null);
  const [robotsTxt, setRobotsTxt] = useState<string | null>(null);
  const [dealCustomerId, setDealCustomerId] = useState("");
  const [dealVehicleId, setDealVehicleId] = useState("");
  const [dealTradeInValue, setDealTradeInValue] = useState("");
  const [scenarioLabel, setScenarioLabel] = useState("");
  const [scenarioSalePrice, setScenarioSalePrice] = useState("");
  const [scenarioDownPayment, setScenarioDownPayment] = useState("");
  const [scenarioTermMonths, setScenarioTermMonths] = useState("60");
  const [selectedLenderId, setSelectedLenderId] = useState("");
  const [showCounterForm, setShowCounterForm] = useState(false);
  const [counterApr, setCounterApr] = useState("");
  const [counterTermMonths, setCounterTermMonths] = useState("");
  const [counterAmountFinanced, setCounterAmountFinanced] = useState("");
  const [counterDownPayment, setCounterDownPayment] = useState("");
  const [counterMonthlyPayment, setCounterMonthlyPayment] = useState("");
  const [lenderDecisionNotes, setLenderDecisionNotes] = useState("");

  if (artifact.type === "roster") {
    return (
      <>
        <h3 className="font-medium mb-4">{artifact.title}</h3>
        {artifact.records.length === 0 ? (
          <div className="text-sm text-zinc-500">No credentials provisioned yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
                  <th className="p-2 font-medium">Employee ID</th>
                  <th className="p-2 font-medium">Role</th>
                  <th className="p-2 font-medium">Status</th>
                  <th className="p-2 font-medium">Email</th>
                  <th className="p-2 font-medium">Created By</th>
                </tr>
              </thead>
              <tbody>
                {artifact.records.map((record) => (
                  <tr key={record.employee_id} className="border-b border-zinc-800/60 last:border-0">
                    <td className="p-2 font-mono">{record.employee_id}</td>
                    <td className="p-2">{record.role}</td>
                    <td className="p-2">
                      {record.must_change_password ? (
                        <span className="text-[#FBCF09]">Needs Password Change</span>
                      ) : (
                        <span className="text-green-400">Active</span>
                      )}
                    </td>
                    <td className="p-2 text-zinc-400">{record.email ?? "—"}</td>
                    <td className="p-2 text-zinc-400">{record.created_by ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }

  if (artifact.type === "audit") {
    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          {artifact.dashboard.total_events} total events recorded.
        </div>

        {Object.keys(artifact.dashboard.by_type).length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {Object.entries(artifact.dashboard.by_type).map(([type, count]) => (
              <span
                key={type}
                className="text-xs bg-zinc-950 border border-zinc-800 rounded-full px-3 py-1 text-zinc-400"
              >
                {type}: {count}
              </span>
            ))}
          </div>
        )}

        {artifact.dashboard.recent.length === 0 ? (
          <div className="text-sm text-zinc-500">No audit events recorded yet.</div>
        ) : (
          <div className="overflow-x-auto max-h-96 overflow-y-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
                  <th className="p-2 font-medium">Time</th>
                  <th className="p-2 font-medium">Event</th>
                  <th className="p-2 font-medium">Summary</th>
                  <th className="p-2 font-medium">Actor</th>
                  <th className="p-2 font-medium">Entity</th>
                </tr>
              </thead>
              <tbody>
                {artifact.dashboard.recent.map((event) => (
                  <tr key={event.id} className="border-b border-zinc-800/60 last:border-0 align-top">
                    <td className="p-2 text-zinc-500 whitespace-nowrap">
                      {event.timestamp.replace("T", " ").slice(0, 19)}
                    </td>
                    <td className="p-2 whitespace-nowrap">{event.event_type}</td>
                    <td className="p-2 text-zinc-300">{event.summary}</td>
                    <td className="p-2 font-mono text-zinc-400">{event.actor}</td>
                    <td className="p-2 font-mono text-zinc-400">{event.entity_id ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }

  if (artifact.type === "compliance_alerts_list") {

    const openAlerts = artifact.alerts.filter((a) => a.status === "open");
    const resolvedAlerts = artifact.alerts.filter((a) => a.status !== "open");

    return (
      <>
        <h3 className="font-medium mb-2">{artifact.title}</h3>

        {artifact.notice && (
          <div className="text-xs text-zinc-500 mb-4 border border-zinc-800 rounded-lg p-2">
            {artifact.notice}
          </div>
        )}

        {artifact.alerts.length === 0 ? (
          <div className="text-sm text-zinc-500">No compliance alerts on file.</div>
        ) : (
          <div className="space-y-3">
            {openAlerts.length > 0 && (
              <div className="text-xs uppercase text-[#EE3C25] tracking-wide">
                Open ({openAlerts.length})
              </div>
            )}

            {openAlerts.map((alert) => (
              <div key={alert.id} className="bg-zinc-950 border border-[#EE3C25]/40 rounded-lg p-3 text-sm">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium">
                    {alert.entity_type} {alert.entity_id}
                  </span>
                  <span className="text-xs text-zinc-500">{alert.action}</span>
                </div>

                {alert.violations.map((v, idx) => (
                  <div key={idx} className="text-xs text-zinc-400 mb-1">
                    <span className="text-[#FBCF09]">[{v.law}, {v.citation}]</span> {v.description}
                  </div>
                ))}

                <div className="flex gap-3 mt-2">
                  {onResolveComplianceAlert && (
                    <button
                      onClick={() => onResolveComplianceAlert(alert.id)}
                      className="text-xs text-green-400 hover:text-white transition"
                    >
                      Mark Resolved
                    </button>
                  )}
                  {onOverrideComplianceAlert && role === "ADMIN" && (
                    <button
                      onClick={() => {
                        const notes = window.prompt("Reason for overriding this compliance block:");
                        if (notes && notes.trim()) onOverrideComplianceAlert(alert.id, notes.trim());
                      }}
                      className="text-xs text-zinc-400 hover:text-white transition"
                    >
                      Override (admin)
                    </button>
                  )}
                </div>
              </div>
            ))}

            {resolvedAlerts.length > 0 && (
              <div className="text-xs uppercase text-zinc-500 tracking-wide pt-2">
                Resolved / Overridden ({resolvedAlerts.length})
              </div>
            )}

            {resolvedAlerts.map((alert) => (
              <div key={alert.id} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm opacity-70">
                <div className="flex items-center justify-between mb-1">
                  <span className="font-medium">
                    {alert.entity_type} {alert.entity_id}
                  </span>
                  <span className="text-xs text-zinc-500">{alert.status}</span>
                </div>
                <div className="text-xs text-zinc-500">
                  {alert.resolution_notes} — {alert.resolved_by}
                </div>
              </div>
            ))}
          </div>
        )}
      </>
    );
  }

  if (artifact.type === "readiness_score") {
    return (
      <>
        <h3 className="font-medium mb-4">{artifact.title}</h3>
        <div className="text-6xl font-bold text-cyan-400 mb-2">{artifact.score}</div>
        <div className="text-sm text-zinc-400">Overall readiness across departments.</div>
      </>
    );
  }

  if (artifact.type === "performance_rank") {
    return (
      <>
        <h3 className="font-medium mb-4">{artifact.title}</h3>
        <div className="text-6xl font-bold text-yellow-400 mb-2">{artifact.rank}</div>
        <div className="text-sm text-zinc-400">Percentile rank across the NXTDeal network.</div>
      </>
    );
  }

  if (artifact.type === "growth_opportunities") {
    return (
      <>
        <h3 className="font-medium mb-4">{artifact.title}</h3>
        <div className="space-y-2 text-sm">
          {artifact.opportunities.map((item) => (
            <div key={item} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
              {item}
            </div>
          ))}
        </div>
      </>
    );
  }

  if (artifact.type === "reset_confirm") {
    return (
      <>
        <h3 className="font-medium mb-2">Reset Password</h3>
        <div className="text-sm text-zinc-400 mb-4">
          Reset the password for{" "}
          <span className="font-mono text-white">{artifact.employeeId}</span>? This
          generates a new temporary password and forces a password change on next
          login. This cannot be undone from here.
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => onConfirmReset(artifact.employeeId)}
            disabled={resetLoading}
            className="px-4 py-2 rounded-lg brand-cta text-sm disabled:opacity-50"
          >
            {resetLoading ? "Resetting…" : "Confirm Reset"}
          </button>
          <button
            onClick={onCancelReset}
            className="px-4 py-2 rounded-lg text-sm text-zinc-500 hover:text-white transition"
          >
            Cancel
          </button>
        </div>
      </>
    );
  }

  if (artifact.type === "reset_result") {
    return (
      <>
        <h3 className="font-medium mb-4">Password Reset</h3>
        <div className="text-xs bg-zinc-950 border border-[#FBCF09]/30 rounded-lg p-3">
          <div className="text-zinc-400 mb-1">
            New temp password for {artifact.employeeId} — shown once:
          </div>
          <div className="font-mono text-[#FBCF09] break-all text-sm">{artifact.tempPassword}</div>
        </div>
      </>
    );
  }

  if (artifact.type === "profile") {
    return <EntityProfileView profile={artifact.profile} onSelect={onSelectProfile} />;
  }

  if (artifact.type === "asset_templates") {
    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          Pick a template, fill it in, and submit for MARKETING/ADMIN approval.
        </div>
        <div className="space-y-2">
          {artifact.templates.map((template) => (
            <button
              key={template.key}
              onClick={() => onSelectAssetTemplate?.(template.key)}
              className="w-full text-left bg-zinc-950 border border-zinc-800 rounded-lg p-3 hover:border-[#3FBCC4] transition"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">{template.name}</span>
                <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                  {template.category}
                </span>
              </div>
              <div className="text-xs text-zinc-500">{template.description}</div>
            </button>
          ))}
        </div>
      </>
    );
  }

  if (artifact.type === "asset_form") {
    const missingRequired = artifact.template.fields.some(
      (field) => field.required && !formFields[field.key]?.trim()
    );

    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">{artifact.template.description}</div>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-zinc-500 mb-1">
              Link a vehicle (optional -- e.g. VEH-00042)
            </label>
            <input aria-label="Link a vehicle (optional -- e.g. VEH-00042)"
              value={formVehicleId}
              onChange={(e) => setFormVehicleId(e.target.value)}
              placeholder="VEH-00042"
              className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            />
          </div>

          {artifact.template.fields.map((field) => (
            <div key={field.key}>
              <label className="block text-xs text-zinc-500 mb-1">
                {field.label}
                {field.required && <span className="text-[#EE3C25]"> *</span>}
              </label>
              {field.type === "textarea" ? (
                <textarea
                  aria-label={field.label} value={formFields[field.key] ?? ""}
                  onChange={(e) => setFormFields((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  rows={3}
                  className="w-full px-3 py-2 text-sm rounded bg-zinc-950 border border-zinc-800"
                />
              ) : (
                <input
                  aria-label={field.label} value={formFields[field.key] ?? ""}
                  onChange={(e) => setFormFields((prev) => ({ ...prev, [field.key]: e.target.value }))}
                  className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
                />
              )}
            </div>
          ))}

          <button
            onClick={() => onCreateAsset?.(artifact.template.key, formFields, formVehicleId)}
            disabled={missingRequired}
            className="px-4 py-2 rounded-lg brand-cta text-sm disabled:opacity-50"
          >
            Submit for Approval
          </button>
        </div>
      </>
    );
  }

  if (artifact.type === "asset_list") {
    return (
      <>
        <h3 className="font-medium mb-4">{artifact.title}</h3>
        {artifact.assets.length === 0 ? (
          <div className="text-sm text-zinc-500">
            {artifact.mode === "pending" ? "Nothing pending approval." : "You haven't requested any assets yet."}
          </div>
        ) : (
          <div className="space-y-2">
            {artifact.assets.map((asset) => (
              <button
                key={asset.id}
                onClick={() => onSelectAsset?.(asset.id)}
                className="w-full text-left bg-zinc-950 border border-zinc-800 rounded-lg p-3 hover:border-[#3FBCC4] transition flex items-center justify-between"
              >
                <span className="text-sm truncate">
                  {asset.fields?.headline || asset.fields?.offer_title || asset.fields?.customer_name || asset.template_key}
                </span>
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 shrink-0 ml-2">
                  {asset.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </>
    );
  }

  if (artifact.type === "asset_detail") {
    const asset = artifact.asset;
    const canReview = asset.status === "pending_approval" && (role === "MARKETING" || role === "ADMIN");

    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          Requested by {asset.requested_by}
          {asset.vehicle_id && <> · linked to {asset.vehicle_id}</>}
          {asset.reviewed_by && <> · reviewed by {asset.reviewed_by}</>}
        </div>

        <div className="space-y-2 mb-4">
          {Object.entries(asset.fields ?? {}).map(([key, value]) =>
            value ? (
              <div key={key} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm">
                <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">{key}</div>
                <div>{value}</div>
              </div>
            ) : null
          )}
        </div>

        {asset.review_notes && (
          <div className="text-xs text-zinc-400 mb-4">
            Review notes: {asset.review_notes}
          </div>
        )}

        {canReview && (
          <div className="space-y-2">
            <WorkField label="Notes (optional)"><textarea
              value={reviewNotes}
              onChange={(e) => setReviewNotes(e.target.value)}
              placeholder="Notes (optional)"
              rows={2}
              className="w-full px-3 py-2 text-sm rounded bg-zinc-950 border border-zinc-800"
            /></WorkField>
            <div className="flex gap-2">
              <button
                onClick={() => onApproveAsset?.(asset.id, reviewNotes)}
                className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-sm"
              >
                Approve
              </button>
              <button
                onClick={() => onRejectAsset?.(asset.id, reviewNotes)}
                className="px-4 py-2 rounded-lg bg-[#EE3C25] hover:bg-red-500 text-sm"
              >
                Reject
              </button>
            </div>
          </div>
        )}
      </>
    );
  }

  if (artifact.type === "campaign_types") {
    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          Pick a campaign type, set the audience, and activate it (MARKETING/ADMIN)
          when it's ready to go out.
        </div>
        <div className="space-y-2">
          {artifact.types.map((campaignType) => (
            <button
              key={campaignType.key}
              onClick={() => onSelectCampaignType?.(campaignType.key)}
              className="w-full text-left bg-zinc-950 border border-zinc-800 rounded-lg p-3 hover:border-[#3FBCC4] transition"
            >
              <div className="flex items-center justify-between mb-1">
                <span className="text-sm font-medium">{campaignType.name}</span>
                <span className="text-[10px] uppercase tracking-wider text-zinc-500">
                  {campaignType.category}
                </span>
              </div>
              <div className="text-xs text-zinc-500">{campaignType.description}</div>
            </button>
          ))}
        </div>
      </>
    );
  }

  if (artifact.type === "campaign_form") {
    const campaignType = artifact.campaignType;
    const channel = campaignChannel || campaignType.default_channel;

    // Audience fields can carry a `default` (e.g. "6 months since last service") that's
    // shown in the input but never gets typed by the user -- fold defaults in here so
    // validation/preview/submit all see the same effective value the input displays,
    // rather than treating an untouched default field as missing.
    function effectiveParams(): Record<string, string> {
      const merged: Record<string, string> = {};

      for (const field of campaignType.audience_fields) {
        merged[field.key] =
          campaignParams[field.key] ?? (field.default != null ? String(field.default) : "");
      }

      return merged;
    }

    const missingRequired = campaignType.audience_fields.some(
      (field) => field.required && !effectiveParams()[field.key]?.trim()
    );

    async function handlePreview() {
      if (!onPreviewAudience) return;

      setPreviewLoading(true);
      const result = await onPreviewAudience(campaignType.key, effectiveParams());
      setAudiencePreview(result);
      setPreviewLoading(false);
    }

    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">{campaignType.description}</div>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Campaign Name</label>
            <input aria-label="Campaign Name"
              value={campaignName}
              onChange={(e) => setCampaignName(e.target.value)}
              placeholder="e.g. Fall Service Retention Push"
              className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            />
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">Channel</label>
            <select aria-label="Channel"
              value={channel}
              onChange={(e) => setCampaignChannel(e.target.value)}
              className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            >
              {["email", "sms", "direct_mail", "ringless_voicemail"].map((option) => (
                <option key={option} value={option}>
                  {option.replace(/_/g, " ")}
                </option>
              ))}
            </select>
          </div>

          <div>
            <label className="block text-xs text-zinc-500 mb-1">
              Linked asset (optional -- must be approved before this campaign can activate)
            </label>
            <input aria-label="Linked asset (optional -- must be approved before this campaign can activate)"
              value={campaignLinkedAsset}
              onChange={(e) => setCampaignLinkedAsset(e.target.value)}
              placeholder="ASSET-00001"
              className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            />
          </div>

          {campaignType.audience_fields.map((field) => (
            <div key={field.key}>
              <label className="block text-xs text-zinc-500 mb-1">
                {field.label}
                {field.required && <span className="text-[#EE3C25]"> *</span>}
              </label>
              <input
                aria-label={field.label} value={campaignParams[field.key] ?? (field.default != null ? String(field.default) : "")}
                onChange={(e) =>
                  setCampaignParams((prev) => ({ ...prev, [field.key]: e.target.value }))
                }
                className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
              />
            </div>
          ))}

          <button
            onClick={handlePreview}
            disabled={previewLoading}
            className="px-4 py-2 rounded-lg border border-zinc-800 hover:border-[#3FBCC4] text-sm disabled:opacity-50"
          >
            {previewLoading ? "Checking reach…" : "Preview Audience"}
          </button>

          {audiencePreview && (
            <div className="text-xs text-zinc-400 bg-zinc-950 border border-zinc-800 rounded-lg p-3">
              This would reach <span className="text-white font-medium">{audiencePreview.count}</span>{" "}
              {audiencePreview.entity_type.toLowerCase()}
              {audiencePreview.count === 1 ? "" : "s"}
              {audiencePreview.sample.length > 0 && (
                <> — e.g. {audiencePreview.sample.slice(0, 3).map((m) => m.name).join(", ")}</>
              )}
            </div>
          )}

          <button
            onClick={() =>
              onCreateCampaign?.(campaignType.key, campaignName, channel, effectiveParams(), campaignLinkedAsset)
            }
            disabled={missingRequired || !campaignName.trim()}
            className="px-4 py-2 rounded-lg brand-cta text-sm disabled:opacity-50"
          >
            Save Draft Campaign
          </button>
        </div>
      </>
    );
  }

  if (artifact.type === "campaign_list") {
    return (
      <>
        <h3 className="font-medium mb-4">{artifact.title}</h3>
        {artifact.campaigns.length === 0 ? (
          <div className="text-sm text-zinc-500">
            {artifact.mode === "pending" ? "No draft campaigns waiting to activate." : "You haven't created any campaigns yet."}
          </div>
        ) : (
          <div className="space-y-2">
            {artifact.campaigns.map((campaign) => (
              <button
                key={campaign.id}
                onClick={() => onSelectCampaign?.(campaign.id)}
                className="w-full text-left bg-zinc-950 border border-zinc-800 rounded-lg p-3 hover:border-[#3FBCC4] transition flex items-center justify-between"
              >
                <span className="text-sm truncate">
                  {campaign.name} · {campaign.audience_count} {campaign.audience_entity_type.toLowerCase()}
                  {campaign.audience_count === 1 ? "" : "s"}
                </span>
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 shrink-0 ml-2">
                  {campaign.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </>
    );
  }

  if (artifact.type === "campaign_detail") {
    const campaign = artifact.campaign;
    const canActivate = campaign.status === "draft" && (role === "MARKETING" || role === "ADMIN");
    const canComplete = campaign.status === "active" && (role === "MARKETING" || role === "ADMIN");
    const canCancel = campaign.status === "draft" || campaign.status === "active";

    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          {campaign.campaign_type.replace(/_/g, " ")} · {campaign.channel.replace(/_/g, " ")} · created by{" "}
          {campaign.created_by}
          {campaign.linked_asset_id && <> · linked to {campaign.linked_asset_id}</>}
        </div>

        <div className="space-y-2 mb-4">
          <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm">
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Audience</div>
            <div>
              {campaign.audience_count} {campaign.audience_entity_type.toLowerCase()}
              {campaign.audience_count === 1 ? "" : "s"}
            </div>
          </div>

          {campaign.status === "active" || campaign.status === "completed" ? (
            <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Sent</div>
              <div>{campaign.sent_count}</div>
            </div>
          ) : null}
        </div>

        <div className="flex gap-2 flex-wrap">
          {canActivate && (
            <button
              onClick={() => onActivateCampaign?.(campaign.id)}
              className="px-4 py-2 rounded-lg brand-cta text-sm"
            >
              Activate
            </button>
          )}
          {canComplete && (
            <button
              onClick={() => onCompleteCampaign?.(campaign.id)}
              className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-sm"
            >
              Mark Completed
            </button>
          )}
          {canCancel && (
            <button
              onClick={() => onCancelCampaign?.(campaign.id)}
              className="px-4 py-2 rounded-lg bg-[#EE3C25] hover:bg-red-500 text-sm"
            >
              Cancel
            </button>
          )}
        </div>
      </>
    );
  }

  if (artifact.type === "website_sections") {
    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          Name a site to start a blank draft, or let AI set one up for you. Add/lock
          sections on each page, then submit for MARKETING/ADMIN approval when it's
          ready to publish.
        </div>

        <button
          onClick={() => onStartWebsiteWizard?.()}
          className="w-full mb-4 px-4 py-2.5 rounded-lg bg-[#3FBCC4] hover:bg-[#39a8af] text-black text-sm font-medium"
        >
          ✨ Use AI Setup Wizard
        </button>

        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">
          Or start blank
        </div>
        <div className="flex gap-2 mb-4">
          <WorkField label="Website Name"><input
            value={websiteName}
            onChange={(e) => setWebsiteName(e.target.value)}
            placeholder="e.g. Acme Ford"
            className="flex-1 h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
          /></WorkField>
          <WorkField label="Website Mode"><select
            value={websiteMode}
            onChange={(e) => setWebsiteMode(e.target.value as "traditional" | "dealer_gpt")}
            className="h-9 px-2 text-sm rounded bg-zinc-950 border border-zinc-800 shrink-0"
          >
            <option value="traditional">Traditional</option>
            <option value="dealer_gpt">DealerGPT</option>
          </select></WorkField>
          <button
            onClick={() => onCreateWebsite?.(websiteName, websiteMode)}
            disabled={!websiteName.trim()}
            className="px-4 py-2 rounded-lg brand-cta text-sm disabled:opacity-50 shrink-0"
          >
            Start Draft Site
          </button>
        </div>

        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">
          Available Sections
        </div>
        <div className="space-y-2">
          {artifact.sections.map((section) => (
            <div key={section.key} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
              <div className="text-sm font-medium mb-1">{section.name}</div>
              <div className="text-xs text-zinc-500">{section.description}</div>
            </div>
          ))}
        </div>
      </>
    );
  }

  if (artifact.type === "website_wizard") {
    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          A few basics and AI drafts your hero headline, about-us copy, financing
          pitch, and sample testimonials -- you can edit anything afterward in canvas
          mode. Pick DealerGPT for a stripped-down "build your car" configurator
          instead of the full traditional template.
        </div>

        <div className="flex gap-1 mb-4">
          <button
            onClick={() => setWebsiteMode("traditional")}
            className={
              websiteMode === "traditional"
                ? "flex-1 px-3 py-2 rounded-lg text-sm bg-[#3FBCC4] text-black font-medium"
                : "flex-1 px-3 py-2 rounded-lg text-sm bg-zinc-950 border border-zinc-800 text-zinc-400"
            }
          >
            Traditional Site
          </button>
          <button
            onClick={() => setWebsiteMode("dealer_gpt")}
            className={
              websiteMode === "dealer_gpt"
                ? "flex-1 px-3 py-2 rounded-lg text-sm bg-[#3FBCC4] text-black font-medium"
                : "flex-1 px-3 py-2 rounded-lg text-sm bg-zinc-950 border border-zinc-800 text-zinc-400"
            }
          >
            DealerGPT (Build Your Car)
          </button>
        </div>

        <div className="space-y-2 mb-3">
          <WorkField label="Dealership name"><input
            value={wizardName}
            onChange={(e) => setWizardName(e.target.value)}
            placeholder="Dealership name (e.g. Acme Ford)"
            className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
          /></WorkField>
          <WorkField label="Address"><input
            value={wizardAddress}
            onChange={(e) => setWizardAddress(e.target.value)}
            placeholder="Address"
            className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
          /></WorkField>
          <div className="flex gap-2">
            <WorkField label="Phone"><input
              value={wizardPhone}
              onChange={(e) => setWizardPhone(e.target.value)}
              placeholder="Phone"
              className="flex-1 h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            /></WorkField>
            <WorkField label="Hours"><input
              value={wizardHours}
              onChange={(e) => setWizardHours(e.target.value)}
              placeholder="Hours (e.g. Mon-Sat 9-7)"
              className="flex-1 h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            /></WorkField>
          </div>
        </div>

        <div className="flex items-center gap-3 mb-3">
          <label className="flex items-center gap-1.5 text-xs text-zinc-400">
            <input
              type="radio"
              checked={wizardBrandingMode === "independent"}
              onChange={() => setWizardBrandingMode("independent")}
            />
            Independent dealership
          </label>
          <label className="flex items-center gap-1.5 text-xs text-zinc-400">
            <input
              type="radio"
              checked={wizardBrandingMode === "oem"}
              onChange={() => setWizardBrandingMode("oem")}
            />
            OEM-branded
          </label>
        </div>

        {wizardBrandingMode === "oem" && (
          <WorkField label="Manufacturer name"><input
            value={wizardOemName}
            onChange={(e) => setWizardOemName(e.target.value)}
            placeholder="Manufacturer name (e.g. Ford)"
            className="w-full h-9 px-3 mb-3 text-sm rounded bg-zinc-950 border border-zinc-800"
          /></WorkField>
        )}

        {websiteMode === "traditional" && (
          <div className="space-y-2 mb-4">
            <WorkField label="Google rating summary (optional"><input
              value={wizardGoogleRating}
              onChange={(e) => setWizardGoogleRating(e.target.value)}
              placeholder="Google rating summary (optional, e.g. '4.8★ from 320 reviews')"
              className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            /></WorkField>
            <div className="flex gap-2">
              <WorkField label="Facebook URL (optional)"><input
                value={wizardFacebook}
                onChange={(e) => setWizardFacebook(e.target.value)}
                placeholder="Facebook URL (optional)"
                className="flex-1 h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
              /></WorkField>
              <WorkField label="Instagram URL (optional)"><input
                value={wizardInstagram}
                onChange={(e) => setWizardInstagram(e.target.value)}
                placeholder="Instagram URL (optional)"
                className="flex-1 h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
              /></WorkField>
            </div>
          </div>
        )}

        <button
          onClick={() =>
            onCreateWebsiteWizard?.(
              {
                dealership_name: wizardName,
                address: wizardAddress,
                phone: wizardPhone,
                hours: wizardHours,
                branding_mode: wizardBrandingMode,
                oem_name: wizardBrandingMode === "oem" ? wizardOemName : undefined,
                google_rating_text: wizardGoogleRating || undefined,
                social_links: { facebook: wizardFacebook || undefined, instagram: wizardInstagram || undefined },
              },
              websiteMode
            )
          }
          disabled={!wizardName.trim()}
          className="w-full py-2.5 rounded-lg brand-cta text-sm font-medium disabled:opacity-50"
        >
          Generate Site with AI
        </button>
      </>
    );
  }

  if (artifact.type === "website_list") {
    return (
      <>
        <h3 className="font-medium mb-4">{artifact.title}</h3>
        {artifact.websites.length === 0 ? (
          <div className="text-sm text-zinc-500">
            {artifact.mode === "pending" ? "No sites waiting to publish." : "You haven't built any sites yet."}
          </div>
        ) : (
          <div className="space-y-2">
            {artifact.websites.map((website) => (
              <button
                key={website.id}
                onClick={() => onSelectWebsite?.(website.id)}
                className="w-full text-left bg-zinc-950 border border-zinc-800 rounded-lg p-3 hover:border-[#3FBCC4] transition flex items-center justify-between"
              >
                <span className="text-sm truncate">{website.name}</span>
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 shrink-0 ml-2">
                  {website.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </>
    );
  }

  if (artifact.type === "website_detail") {
    const website = artifact.website;
    // Server enforces "builder or ADMIN" on every edit/submit call regardless (see
    // core/websites_api.py) -- this just decides whether to show the edit controls at
    // all, same lightweight client-side gating the campaign_detail Cancel button uses.
    const canEdit = website.status === "draft" || website.status === "rejected";
    const canReview = website.status === "pending_approval" && (role === "MARKETING" || role === "ADMIN");
    const page = website.pages[activePageKey] ?? { sections: [] };
    const template = artifact.sectionTemplates.find((t) => t.key === selectedSectionKey);

    function renderSectionSummary(section: WebsiteSection) {
      const fields = section.fields ?? {};

      if (section.section_key === "hero_banner") {
        return (
          <>
            <div className="font-medium">{fields.headline}</div>
            {fields.subheadline && <div className="text-zinc-400">{fields.subheadline}</div>}
            {fields.image_url && <div className="text-zinc-500 truncate">{fields.image_url}</div>}
          </>
        );
      }

      if (section.section_key === "text_block") {
        return (
          <>
            {fields.heading && <div className="font-medium">{fields.heading}</div>}
            <div className="text-zinc-400">{fields.body}</div>
          </>
        );
      }

      if (section.section_key === "image_gallery") {
        return <div className="text-zinc-400">{fields.image_urls}</div>;
      }

      if (section.section_key === "contact_form") {
        return (
          <>
            {fields.heading && <div className="font-medium">{fields.heading}</div>}
            <div className="text-zinc-400">{[fields.phone, fields.address].filter(Boolean).join(" · ")}</div>
          </>
        );
      }

      if (section.section_key === "inventory_grid") {
        const vehicles = section.live_vehicles ?? [];

        return (
          <>
            <div className="text-zinc-500 mb-2">
              {fields.make && <>Make: {fields.make} · </>}
              {fields.max_price && <>Max ${fields.max_price} · </>}
              {vehicles.length} vehicle{vehicles.length === 1 ? "" : "s"} live from inventory
            </div>
            {vehicles.length > 0 && (
              <div className="grid grid-cols-2 gap-2">
                {vehicles.map((v) => (
                  <div key={v.id} className="bg-zinc-900 border border-zinc-800 rounded p-2 text-xs">
                    <div className="font-medium">
                      {v.year} {v.make} {v.model}
                    </div>
                    <div className="text-zinc-500">${v.price}</div>
                  </div>
                ))}
              </div>
            )}
          </>
        );
      }

      if (section.section_key === "testimonials_carousel") {
        const lines = (fields.testimonials ?? "").split("\n").filter(Boolean);
        return (
          <>
            {fields.heading && <div className="font-medium mb-1">{fields.heading}</div>}
            <div className="space-y-1">
              {lines.map((line, i) => (
                <div key={i} className="text-zinc-400">
                  {line}
                </div>
              ))}
            </div>
          </>
        );
      }

      if (section.section_key === "google_rating_badge") {
        return <div className="font-medium">⭐ {fields.rating_text}</div>;
      }

      if (section.section_key === "social_links") {
        const links = [
          fields.facebook_url && `Facebook: ${fields.facebook_url}`,
          fields.instagram_url && `Instagram: ${fields.instagram_url}`,
          fields.tiktok_url && `TikTok: ${fields.tiktok_url}`,
          fields.x_url && `X: ${fields.x_url}`,
        ].filter(Boolean);
        return <div className="text-zinc-400 space-y-0.5">{links.map((l, i) => <div key={i}>{l}</div>)}</div>;
      }

      if (section.section_key === "financing_info") {
        return (
          <>
            {fields.heading && <div className="font-medium">{fields.heading}</div>}
            <div className="text-zinc-400">{fields.body}</div>
            {fields.apply_url && <div className="text-zinc-500 truncate">{fields.apply_url}</div>}
          </>
        );
      }

      if (section.section_key === "oem_branding_banner") {
        return (
          <>
            <div className="font-medium">{fields.oem_name}</div>
            {fields.oem_logo_url && <div className="text-zinc-500 truncate">{fields.oem_logo_url}</div>}
            {fields.disclaimer && <div className="text-zinc-500">{fields.disclaimer}</div>}
          </>
        );
      }

      if (section.section_key === "car_builder") {
        const options = section.live_options ?? [];
        const totalModels = options.reduce((sum, m) => sum + m.models.length, 0);
        return (
          <>
            {fields.heading && <div className="font-medium mb-1">{fields.heading}</div>}
            {fields.intro_text && <div className="text-zinc-400 mb-2">{fields.intro_text}</div>}
            <div className="text-zinc-500 mb-2">
              {options.length} make{options.length === 1 ? "" : "s"}, {totalModels} model
              {totalModels === 1 ? "" : "s"} live from inventory
            </div>
            <div className="flex flex-wrap gap-1">
              {options.slice(0, 8).map((m) => (
                <span key={m.make} className="px-2 py-0.5 rounded-full text-xs bg-zinc-900 border border-zinc-800">
                  {m.make}
                </span>
              ))}
            </div>
          </>
        );
      }

      return null;
    }

    const canManage = role === "MARKETING" || role === "ADMIN";

    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-1">
          Built by {website.requested_by}
          {website.reviewed_by && <> · reviewed by {website.reviewed_by}</>}
          {website.owners && website.owners.length > 0 && <> · owners: {website.owners.join(", ")}</>}
        </div>

        <div className="flex items-center gap-2 mb-4">
          <span className="text-[10px] px-2 py-0.5 rounded-full border border-zinc-700 text-zinc-400 uppercase tracking-wide">
            {website.mode === "dealer_gpt" ? "DealerGPT" : "Traditional"}
          </span>
          {canEdit && canManage && (
            <button
              onClick={() =>
                onSetWebsiteMode?.(website.id, website.mode === "dealer_gpt" ? "traditional" : "dealer_gpt")
              }
              className="text-[10px] text-zinc-500 hover:text-white underline"
            >
              switch to {website.mode === "dealer_gpt" ? "Traditional" : "DealerGPT"}
            </button>
          )}
        </div>

        <div className="flex gap-1 mb-3 flex-wrap">
          {artifact.pageKeys.map((p) => (
            <button
              key={p.key}
              onClick={() => setActivePageKey(p.key)}
              className={
                activePageKey === p.key
                  ? "px-3 py-1 rounded-full text-xs bg-[#3FBCC4] text-black"
                  : "px-3 py-1 rounded-full text-xs bg-zinc-950 border border-zinc-800 text-zinc-400 hover:text-white"
              }
            >
              {p.label}
            </button>
          ))}
        </div>

        <div className="space-y-2 mb-4">
          {page.sections.length === 0 ? (
            <div className="text-sm text-zinc-500">No sections on this page yet.</div>
          ) : (
            page.sections.map((section, index) => (
              <div
                key={index}
                className={
                  section.locked
                    ? "bg-zinc-950 border border-amber-800/60 rounded-lg p-3 text-sm"
                    : "bg-zinc-950 border border-zinc-800 rounded-lg p-3 text-sm"
                }
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    {section.locked && (
                      <span className="text-[10px] text-amber-500 mr-1.5">🔒 locked</span>
                    )}
                    {renderSectionSummary(section)}
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    {canManage && (
                      <button
                        onClick={() => onToggleSectionLock?.(website.id, activePageKey, index, !section.locked)}
                        className="text-xs text-zinc-500 hover:text-white"
                      >
                        {section.locked ? "Unlock" : "Lock"}
                      </button>
                    )}
                    {canEdit && (!section.locked || canManage) && (
                      <button
                        onClick={() => onRemoveSection?.(website.id, activePageKey, index)}
                        className="text-xs text-[#EE3C25] hover:text-red-400"
                      >
                        Remove
                      </button>
                    )}
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {canEdit && (
          <div className="space-y-2 mb-4 bg-zinc-950 border border-zinc-800 rounded-lg p-3">

            <WorkField label="Add a Section"><select
              value={selectedSectionKey}
              onChange={(e) => {
                setSelectedSectionKey(e.target.value);
                setSectionFields({});
              }}
              className="w-full h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
            >
              <option value="">Choose a section type…</option>
              {artifact.sectionTemplates.map((t) => (
                <option key={t.key} value={t.key}>
                  {t.name}
                </option>
              ))}
            </select></WorkField>

            {template &&
              template.fields.map((field) => (
                <div key={field.key}>
                  <label className="block text-xs text-zinc-500 mb-1">
                    {field.label}
                    {field.required && <span className="text-[#EE3C25]"> *</span>}
                  </label>
                  {field.type === "textarea" ? (
                    <textarea
                      aria-label={field.label} value={sectionFields[field.key] ?? ""}
                      onChange={(e) => setSectionFields((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      rows={2}
                      className="w-full px-3 py-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                    />
                  ) : (
                    <input aria-label={field.label}
                      value={
                        sectionFields[field.key] ?? (field.default != null ? String(field.default) : "")
                      }
                      onChange={(e) => setSectionFields((prev) => ({ ...prev, [field.key]: e.target.value }))}
                      className="w-full h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                    />
                  )}
                </div>
              ))}

            {template && (
              <button
                onClick={() => {
                  onAddSection?.(website.id, activePageKey, template.key, sectionFields);
                  setSelectedSectionKey("");
                  setSectionFields({});
                }}
                disabled={template.fields.some(
                  (f) => f.required && !sectionFields[f.key]?.trim()
                )}
                className="px-4 py-2 rounded-lg brand-cta text-sm disabled:opacity-50"
              >
                Add Section
              </button>
            )}
          </div>
        )}

        {canManage && (
          <div className="mb-4 bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <button
              onClick={() => {
                setShowAdminSettings((s) => !s);
                setAdminSettingsDraft(website.admin_settings as unknown as Record<string, string | boolean>);
              }}
              className="w-full flex items-center justify-between text-xs uppercase tracking-wider text-zinc-500"
            >
              <span>Admin Settings — DNS · SEO · Bot · Analytics · Branding</span>
              <span>{showAdminSettings ? "▲" : "▼"}</span>
            </button>

            {showAdminSettings && (
              <div className="mt-3 space-y-3">
                <div>
                  <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Domain / DNS</div>
                  <input
                    value={(adminSettingsDraft.custom_domain as string) ?? ""}
                    onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, custom_domain: e.target.value }))}
                    aria-label="Custom domain" placeholder="e.g. www.acmeford.com"
                    className="w-full h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800 mb-2"
                  />
                  <button
                    onClick={async () => setDnsInfo((await onFetchWebsiteDnsInstructions?.(website.id)) as typeof dnsInfo)}
                    className="text-xs text-[#3FBCC4] hover:underline"
                  >
                    Show DNS instructions
                  </button>
                  {dnsInfo && (
                    <div className="mt-2 p-2 rounded bg-zinc-900 border border-zinc-800 text-xs text-zinc-400">
                      {dnsInfo.configured ? (
                        <>
                          CNAME <span className="text-zinc-200">{dnsInfo.record_host}</span> →{" "}
                          <span className="text-zinc-200">{dnsInfo.record_target}</span>
                          <div className="mt-1 text-zinc-500">{dnsInfo.note}</div>
                        </>
                      ) : (
                        dnsInfo.note
                      )}
                    </div>
                  )}
                </div>

                <div>

                  <WorkField label="SEO"><input
                    value={(adminSettingsDraft.meta_title as string) ?? ""}
                    onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, meta_title: e.target.value }))}
                    placeholder="Meta title"
                    className="w-full h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800 mb-2"
                  /></WorkField>
                  <WorkField label="Meta description"><textarea
                    value={(adminSettingsDraft.meta_description as string) ?? ""}
                    onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, meta_description: e.target.value }))}
                    placeholder="Meta description"
                    rows={2}
                    className="w-full px-3 py-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                  /></WorkField>
                </div>

                <div>
                  <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Bot / Crawlers</div>
                  <label className="flex items-center gap-2 text-xs text-zinc-400 mb-1">
                    <input
                      type="checkbox"
                      checked={Boolean(adminSettingsDraft.allow_search_engines ?? true)}
                      onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, allow_search_engines: e.target.checked }))}
                    />
                    Allow search engines to index this site
                  </label>
                  <label className="flex items-center gap-2 text-xs text-zinc-400 mb-1">
                    <input
                      type="checkbox"
                      checked={Boolean(adminSettingsDraft.block_ai_crawlers ?? false)}
                      onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, block_ai_crawlers: e.target.checked }))}
                    />
                    Block AI crawlers (GPTBot, ClaudeBot, CCBot, Google-Extended…)
                  </label>
                  <label className="flex items-center gap-2 text-xs text-zinc-400 mb-2">
                    <input
                      type="checkbox"
                      checked={Boolean(adminSettingsDraft.sitemap_enabled ?? true)}
                      onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, sitemap_enabled: e.target.checked }))}
                    />
                    Publish sitemap.xml reference in robots.txt
                  </label>
                  <button
                    onClick={async () => {
                      const r = (await onFetchWebsiteRobotsTxt?.(website.id)) as { robots_txt?: string } | null;
                      setRobotsTxt(r?.robots_txt ?? null);
                    }}
                    className="text-xs text-[#3FBCC4] hover:underline"
                  >
                    Preview robots.txt
                  </button>
                  {robotsTxt && (
                    <pre className="mt-2 p-2 rounded bg-zinc-900 border border-zinc-800 text-[11px] text-zinc-400 whitespace-pre-wrap">
                      {robotsTxt}
                    </pre>
                  )}
                </div>

                <div>

                  <WorkField label="Analytics & Tracking"><input
                    value={(adminSettingsDraft.google_analytics_id as string) ?? ""}
                    onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, google_analytics_id: e.target.value }))}
                    placeholder="Google Analytics ID (e.g. G-XXXXXXX)"
                    className="w-full h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800 mb-2"
                  /></WorkField>
                  <div className="flex gap-2 mb-2">
                    <WorkField label="Umami Site ID"><input
                      value={(adminSettingsDraft.umami_site_id as string) ?? ""}
                      onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, umami_site_id: e.target.value }))}
                      placeholder="Umami Site ID"
                      className="flex-1 h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                    /></WorkField>
                    <WorkField label="Umami Script URL"><input
                      value={(adminSettingsDraft.umami_script_url as string) ?? ""}
                      onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, umami_script_url: e.target.value }))}
                      placeholder="Umami Script URL"
                      className="flex-1 h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                    /></WorkField>
                  </div>
                  <WorkField label="Facebook Pixel ID"><input
                    value={(adminSettingsDraft.facebook_pixel_id as string) ?? ""}
                    onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, facebook_pixel_id: e.target.value }))}
                    placeholder="Facebook Pixel ID"
                    className="w-full h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800 mb-2"
                  /></WorkField>
                  <WorkField label="Custom <head> code snippet"><textarea
                    value={(adminSettingsDraft.custom_head_snippet as string) ?? ""}
                    onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, custom_head_snippet: e.target.value }))}
                    placeholder="Custom <head> code snippet"
                    rows={2}
                    className="w-full px-3 py-2 text-sm rounded bg-zinc-900 border border-zinc-800 mb-2"
                  /></WorkField>
                  <WorkField label="Custom <body> code snippet"><textarea
                    value={(adminSettingsDraft.custom_body_snippet as string) ?? ""}
                    onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, custom_body_snippet: e.target.value }))}
                    placeholder="Custom <body> code snippet"
                    rows={2}
                    className="w-full px-3 py-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                  /></WorkField>
                </div>

                <div>
                  <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">Branding</div>
                  <div className="flex items-center gap-3 mb-2">
                    <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                      <input
                        type="radio"
                        checked={(adminSettingsDraft.branding_mode ?? "independent") === "independent"}
                        onChange={() => setAdminSettingsDraft((p) => ({ ...p, branding_mode: "independent" }))}
                      />
                      Independent
                    </label>
                    <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                      <input
                        type="radio"
                        checked={adminSettingsDraft.branding_mode === "oem"}
                        onChange={() => setAdminSettingsDraft((p) => ({ ...p, branding_mode: "oem" }))}
                      />
                      OEM-branded
                    </label>
                  </div>
                  {adminSettingsDraft.branding_mode === "oem" && (
                    <div className="flex gap-2">
                      <WorkField label="OEM name"><input
                        value={(adminSettingsDraft.oem_name as string) ?? ""}
                        onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, oem_name: e.target.value }))}
                        placeholder="OEM name"
                        className="flex-1 h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                      /></WorkField>
                      <WorkField label="OEM logo URL"><input
                        value={(adminSettingsDraft.oem_logo_url as string) ?? ""}
                        onChange={(e) => setAdminSettingsDraft((p) => ({ ...p, oem_logo_url: e.target.value }))}
                        placeholder="OEM logo URL"
                        className="flex-1 h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                      /></WorkField>
                    </div>
                  )}
                </div>

                <button
                  onClick={() =>
                    onUpdateWebsiteAdminSettings?.(
                      website.id,
                      adminSettingsDraft as unknown as Partial<import("@/lib/useArtifactPanel").WebsiteAdminSettings>
                    )
                  }
                  className="w-full py-2 rounded-lg brand-cta text-sm font-medium"
                >
                  Save Admin Settings
                </button>
              </div>
            )}
          </div>
        )}

        {website.review_notes && (
          <div className="text-xs text-zinc-400 mb-4">Review notes: {website.review_notes}</div>
        )}

        {canReview && (
          <WorkField label="Notes (optional)"><textarea
            value={reviewNotes}
            onChange={(e) => setReviewNotes(e.target.value)}
            placeholder="Notes (optional)"
            rows={2}
            className="w-full mb-2 px-3 py-2 text-sm rounded bg-zinc-950 border border-zinc-800"
          /></WorkField>
        )}

        <div className="flex gap-2 flex-wrap">
          {canEdit && (
            <button
              onClick={() => onSubmitWebsite?.(website.id)}
              className="px-4 py-2 rounded-lg brand-cta text-sm"
            >
              Submit for Approval
            </button>
          )}

          {canReview && (
            <>
              <button
                onClick={() => onApproveWebsite?.(website.id, reviewNotes)}
                className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-sm"
              >
                Publish
              </button>
              <button
                onClick={() => onRejectWebsite?.(website.id, reviewNotes)}
                className="px-4 py-2 rounded-lg bg-[#EE3C25] hover:bg-red-500 text-sm"
              >
                Reject
              </button>
            </>
          )}
        </div>
      </>
    );
  }

  if (artifact.type === "deal_start") {
    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          Link a customer and a vehicle to open a deal. Next you'll build 2-3 pricing
          scenarios side by side before locking one in and moving to financing.
        </div>

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Customer ID</label>
            <input aria-label="Customer ID"
              value={dealCustomerId}
              onChange={(e) => setDealCustomerId(e.target.value)}
              placeholder="CUST-00042"
              className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Vehicle ID</label>
            <input aria-label="Vehicle ID"
              value={dealVehicleId}
              onChange={(e) => setDealVehicleId(e.target.value)}
              placeholder="VEH-00042"
              className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            />
          </div>
          <div>
            <label className="block text-xs text-zinc-500 mb-1">Trade-in value (optional)</label>
            <input aria-label="Trade-in value (optional)"
              value={dealTradeInValue}
              onChange={(e) => setDealTradeInValue(e.target.value)}
              placeholder="0"
              className="w-full h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
            />
          </div>

          <button
            onClick={() =>
              onCreateDeal?.(
                dealCustomerId.trim(),
                dealVehicleId.trim(),
                dealTradeInValue.trim() ? Number(dealTradeInValue) : undefined
              )
            }
            disabled={!dealCustomerId.trim() || !dealVehicleId.trim()}
            className="px-4 py-2 rounded-lg brand-cta text-sm disabled:opacity-50"
          >
            Start Deal
          </button>
        </div>
      </>
    );
  }

  if (artifact.type === "deal_list") {
    return (
      <>
        <h3 className="font-medium mb-4">{artifact.title}</h3>
        {artifact.deals.length === 0 ? (
          <div className="text-sm text-zinc-500">
            {artifact.mode === "pending"
              ? "No deals awaiting a financing decision."
              : "You haven't started any deals yet."}
          </div>
        ) : (
          <div className="space-y-2">
            {artifact.deals.map((deal) => (
              <button
                key={deal.id}
                onClick={() => onSelectDeal?.(deal.id)}
                className="w-full text-left bg-zinc-950 border border-zinc-800 rounded-lg p-3 hover:border-[#3FBCC4] transition flex items-center justify-between"
              >
                <span className="text-sm truncate">
                  {deal.id} · {deal.customer_id} / {deal.vehicle_id}
                </span>
                <span className="text-[10px] uppercase tracking-wider text-zinc-500 shrink-0 ml-2">
                  {deal.status === "financing" && deal.financing_status !== "not_started"
                    ? `financing · ${deal.financing_status}`
                    : deal.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </>
    );
  }

  if (artifact.type === "deal_detail") {
    const deal = artifact.deal;
    // Mirrors core/deals_api.py's _FI_ROLES exactly -- SALES can desk a deal but never
    // move financing/contract/funding forward, since that touches real pricing/money.
    // Scenario add/remove/select is gated more loosely here (server enforces the precise
    // creator-or-FI-role check; client just hides controls once desking is over).
    const canDoFinancing = role === "ADMIN" || role === "OPERATIONS" || role === "FINANCE";
    const canManageScenarios = deal.status === "desking";
    const canCancel = deal.status !== "funded" && deal.status !== "cancelled";
    const selectedScenario = deal.scenarios.find((s) => s.id === deal.selected_scenario_id) ?? null;

    function money(value: number | null | undefined) {
      if (value == null) return "—";
      return `$${value.toLocaleString(undefined, { maximumFractionDigits: 2 })}`;
    }

    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          Customer {deal.customer_id} · Vehicle {deal.vehicle_id}
          {deal.trade_in?.value ? <> · Trade-in {money(deal.trade_in.value)}</> : null}
          {" · started by "}
          {deal.created_by}
        </div>

        {/* Scenarios (multi-scenario desking) */}
        <div className="mb-4">
          <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">
            Pricing Scenarios
          </div>
          {deal.scenarios.length === 0 ? (
            <div className="text-sm text-zinc-500 mb-2">No scenarios built yet.</div>
          ) : (
            <div className="overflow-x-auto mb-2">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-zinc-500 border-b border-zinc-800">
                    <th className="p-2 font-medium">Label</th>
                    <th className="p-2 font-medium">Sale Price</th>
                    <th className="p-2 font-medium">Down</th>
                    <th className="p-2 font-medium">Term</th>
                    <th className="p-2 font-medium">Financed</th>
                    <th className="p-2 font-medium">Est. APR</th>
                    <th className="p-2 font-medium">Est. Payment</th>
                    <th className="p-2 font-medium"></th>
                  </tr>
                </thead>
                <tbody>
                  {deal.scenarios.map((scenario) => (
                    <tr
                      key={scenario.id}
                      className={
                        scenario.id === deal.selected_scenario_id
                          ? "border-b border-zinc-800/60 bg-zinc-900/60"
                          : "border-b border-zinc-800/60"
                      }
                    >
                      <td className="p-2">
                        {scenario.label}
                        {scenario.id === deal.selected_scenario_id && (
                          <span className="ml-2 text-[10px] text-[#3FBCC4]">Selected</span>
                        )}
                      </td>
                      <td className="p-2">{money(scenario.sale_price)}</td>
                      <td className="p-2">{money(scenario.down_payment)}</td>
                      <td className="p-2">{scenario.term_months}mo</td>
                      <td className="p-2">{money(scenario.amount_financed)}</td>
                      <td className="p-2">{scenario.estimated_apr}%</td>
                      <td className="p-2">{money(scenario.estimated_monthly_payment)}/mo</td>
                      <td className="p-2 whitespace-nowrap">
                        {canManageScenarios && (
                          <>
                            <button
                              onClick={() => onSelectScenario?.(deal.id, scenario.id)}
                              className="text-[#3FBCC4] hover:text-white mr-2"
                            >
                              Select
                            </button>
                            <button
                              onClick={() => onRemoveScenario?.(deal.id, scenario.id)}
                              className="text-[#EE3C25] hover:text-red-400"
                            >
                              Remove
                            </button>
                          </>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {canManageScenarios && (
            <div className="bg-zinc-950 border border-zinc-800 rounded-lg p-3 space-y-2">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500">
                Add a Scenario
              </div>
              <div className="grid grid-cols-2 gap-2">
                <WorkField label="Label"><input
                  value={scenarioLabel}
                  onChange={(e) => setScenarioLabel(e.target.value)}
                  placeholder="Label (e.g. 60mo standard)"
                  className="col-span-2 h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                /></WorkField>
                <WorkField label="Sale price"><input
                  value={scenarioSalePrice}
                  onChange={(e) => setScenarioSalePrice(e.target.value)}
                  placeholder="Sale price"
                  className="h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                /></WorkField>
                <WorkField label="Down payment"><input
                  value={scenarioDownPayment}
                  onChange={(e) => setScenarioDownPayment(e.target.value)}
                  placeholder="Down payment"
                  className="h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                /></WorkField>
                <WorkField label="Scenario Term Months"><select
                  value={scenarioTermMonths}
                  onChange={(e) => setScenarioTermMonths(e.target.value)}
                  className="col-span-2 h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                >
                  <option value="24">24 months</option>
                  <option value="36">36 months</option>
                  <option value="48">48 months</option>
                  <option value="60">60 months</option>
                  <option value="72">72 months</option>
                </select></WorkField>
              </div>
              <button
                onClick={() => {
                  onAddScenario?.(
                    deal.id,
                    scenarioLabel.trim() || `Scenario ${deal.scenarios.length + 1}`,
                    Number(scenarioSalePrice) || 0,
                    Number(scenarioDownPayment) || 0,
                    Number(scenarioTermMonths)
                  );
                  setScenarioLabel("");
                  setScenarioSalePrice("");
                  setScenarioDownPayment("");
                }}
                disabled={!scenarioSalePrice.trim()}
                className="px-4 py-2 rounded-lg brand-cta text-sm disabled:opacity-50"
              >
                Add Scenario
              </button>
            </div>
          )}
        </div>

        {/* Financing */}
        {(deal.status === "financing" || deal.status === "contract" || deal.status === "funded") && (
          <div className="mb-4 bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">Financing</div>

            {selectedScenario && (
              <div className="text-xs text-zinc-400 mb-2">
                Selected: {selectedScenario.label} · {money(selectedScenario.amount_financed)} financed
              </div>
            )}

            {deal.status === "financing" && deal.financing_status === "not_started" && canDoFinancing && (
              <div className="space-y-2">
                <button
                  onClick={() => onChooseInHouseFinancing?.(deal.id)}
                  className="px-4 py-2 rounded-lg brand-cta text-sm"
                >
                  Use In-House Financing (BHPH)
                </button>
                <div className="flex gap-2 items-center">
                  <WorkField label="Selected Lender ID"><select
                    value={selectedLenderId}
                    onChange={(e) => setSelectedLenderId(e.target.value)}
                    className="flex-1 h-9 px-3 text-sm rounded bg-zinc-900 border border-zinc-800"
                  >
                    <option value="">Choose an outside lender…</option>
                    {artifact.lenders.map((lender) => (
                      <option key={lender.id} value={lender.id}>
                        {lender.name}
                      </option>
                    ))}
                  </select></WorkField>
                  <button
                    onClick={() => onSubmitToLender?.(deal.id, selectedLenderId)}
                    disabled={!selectedLenderId}
                    className="px-4 py-2 rounded-lg brand-cta text-sm disabled:opacity-50 shrink-0"
                  >
                    Submit to Lender
                  </button>
                </div>
              </div>
            )}

            {deal.financing_status === "submitted" && (
              <div className="space-y-2">
                <div className="text-sm text-zinc-400">Awaiting lender decision…</div>
                {canDoFinancing && (
                  <>
                    <div className="flex gap-2 flex-wrap">
                      <button
                        onClick={() => onRecordLenderDecision?.(deal.id, "approved", undefined, lenderDecisionNotes)}
                        className="px-3 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-sm"
                      >
                        Record: Approved
                      </button>
                      <button
                        onClick={() => onRecordLenderDecision?.(deal.id, "declined", undefined, lenderDecisionNotes)}
                        className="px-3 py-2 rounded-lg bg-[#EE3C25] hover:bg-red-500 text-sm"
                      >
                        Record: Declined
                      </button>
                      <button
                        onClick={() => setShowCounterForm((v) => !v)}
                        className="px-3 py-2 rounded-lg bg-[#FBCF09] text-black hover:bg-yellow-400 text-sm"
                      >
                        Record: Countered
                      </button>
                    </div>

                    {showCounterForm && (
                      <div className="grid grid-cols-2 gap-2 bg-zinc-900 border border-zinc-800 rounded-lg p-3">
                        <WorkField label="Counter Apr"><input
                          value={counterApr}
                          onChange={(e) => setCounterApr(e.target.value)}
                          placeholder={`APR (e.g. ${selectedScenario?.estimated_apr ?? ""})`}
                          className="h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
                        /></WorkField>
                        <WorkField label="Counter Term Months"><input
                          value={counterTermMonths}
                          onChange={(e) => setCounterTermMonths(e.target.value)}
                          placeholder={`Term months (e.g. ${selectedScenario?.term_months ?? ""})`}
                          className="h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
                        /></WorkField>
                        <WorkField label="Counter Amount Financed"><input
                          value={counterAmountFinanced}
                          onChange={(e) => setCounterAmountFinanced(e.target.value)}
                          placeholder={`Amount financed (e.g. ${selectedScenario?.amount_financed ?? ""})`}
                          className="h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
                        /></WorkField>
                        <WorkField label="Counter Down Payment"><input
                          value={counterDownPayment}
                          onChange={(e) => setCounterDownPayment(e.target.value)}
                          placeholder={`Down payment (e.g. ${selectedScenario?.down_payment ?? ""})`}
                          className="h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
                        /></WorkField>
                        <WorkField label="Counter Monthly Payment"><input
                          value={counterMonthlyPayment}
                          onChange={(e) => setCounterMonthlyPayment(e.target.value)}
                          placeholder={`Monthly payment (e.g. ${selectedScenario?.estimated_monthly_payment ?? ""})`}
                          className="col-span-2 h-9 px-3 text-sm rounded bg-zinc-950 border border-zinc-800"
                        /></WorkField>
                        <button
                          onClick={() => {
                            onRecordLenderDecision?.(
                              deal.id,
                              "countered",
                              {
                                apr: Number(counterApr) || selectedScenario?.estimated_apr || 0,
                                term_months: Number(counterTermMonths) || selectedScenario?.term_months || 0,
                                amount_financed:
                                  Number(counterAmountFinanced) || selectedScenario?.amount_financed || 0,
                                down_payment: Number(counterDownPayment) || selectedScenario?.down_payment || 0,
                                monthly_payment:
                                  Number(counterMonthlyPayment) ||
                                  selectedScenario?.estimated_monthly_payment ||
                                  0,
                              },
                              lenderDecisionNotes
                            );
                            setShowCounterForm(false);
                          }}
                          className="col-span-2 px-4 py-2 rounded-lg brand-cta text-sm"
                        >
                          Submit Counter
                        </button>
                      </div>
                    )}

                    <WorkField label="Notes (optional)"><textarea
                      value={lenderDecisionNotes}
                      onChange={(e) => setLenderDecisionNotes(e.target.value)}
                      placeholder="Notes (optional)"
                      rows={2}
                      className="w-full px-3 py-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                    /></WorkField>
                  </>
                )}
              </div>
            )}

            {deal.financing_status === "countered" && deal.financing_terms && (
              <div className="space-y-2">
                <div className="text-sm text-zinc-300">
                  Lender countered: {deal.financing_terms.apr}% APR · {deal.financing_terms.term_months}mo ·{" "}
                  {money(deal.financing_terms.monthly_payment)}/mo
                </div>
                {canDoFinancing && (
                  <button
                    onClick={() => onAcceptCounteredTerms?.(deal.id)}
                    className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-sm"
                  >
                    Accept Countered Terms
                  </button>
                )}
              </div>
            )}

            {deal.financing_status === "declined" && (
              <div className="text-sm text-[#EE3C25]">
                Financing declined. Try in-house financing or another lender above.
              </div>
            )}

            {deal.financing_status === "approved" && deal.financing_terms && (
              <div className="space-y-2">
                <div className="text-sm text-green-400">
                  Approved: {deal.financing_terms.apr}% APR · {deal.financing_terms.term_months}mo ·{" "}
                  {money(deal.financing_terms.monthly_payment)}/mo
                  {deal.financing_type === "in_house" ? " · In-House (BHPH)" : " · Outside Lender"}
                </div>
                {deal.status === "financing" && canDoFinancing && (
                  <button
                    onClick={() => onGenerateContract?.(deal.id)}
                    className="px-4 py-2 rounded-lg brand-cta text-sm"
                  >
                    Generate Contract
                  </button>
                )}
              </div>
            )}
          </div>
        )}

        {/* Contract */}
        {deal.contract && (
          <div className="mb-4 bg-zinc-950 border border-zinc-800 rounded-lg p-3">
            <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">
              Contract — {deal.contract.vehicle_description}
            </div>
            <div className="text-sm space-y-1 mb-2">
              <div>Customer: {deal.contract.customer_name} ({deal.contract.customer_id})</div>
              <div>VIN: {deal.contract.vin ?? "—"}</div>
              <div>Sale price: {money(deal.contract.sale_price)}</div>
              {deal.contract.trade_in_value ? <div>Trade-in: {money(deal.contract.trade_in_value)}</div> : null}
              <div>Down payment: {money(deal.contract.down_payment)}</div>
              <div>Amount financed: {money(deal.contract.amount_financed)}</div>
              <div>
                APR: {deal.contract.apr}% · {deal.contract.term_months} months
              </div>
              <div>Monthly payment: {money(deal.contract.monthly_payment)}/mo</div>
              <div>
                Financing: {deal.contract.financing_type === "in_house" ? "In-House (BHPH)" : "Outside Lender"}
                {deal.contract.lender_name ? ` — ${deal.contract.lender_name}` : ""}
              </div>
            </div>
            {deal.contract.disclosures.length > 0 && (
              <div className="text-[11px] text-zinc-500 space-y-1 mb-2">
                {deal.contract.disclosures.map((d, i) => (
                  <div key={i}>{d}</div>
                ))}
              </div>
            )}
            {deal.status === "contract" && canDoFinancing && (
              <button
                onClick={() => onFundDeal?.(deal.id)}
                className="px-4 py-2 rounded-lg bg-green-600 hover:bg-green-500 text-sm"
              >
                Fund Deal
              </button>
            )}
          </div>
        )}

        {deal.status === "funded" && (
          <div className="mb-4 text-sm text-green-400">
            Funded — Finance Contract {deal.finance_contract_id}
          </div>
        )}

        {deal.status === "cancelled" && <div className="mb-4 text-sm text-zinc-500">This deal was cancelled.</div>}

        {canCancel && (
          <button
            onClick={() => onCancelDeal?.(deal.id)}
            className="px-4 py-2 rounded-lg bg-zinc-800 hover:bg-zinc-700 text-sm"
          >
            Cancel Deal
          </button>
        )}
      </>
    );
  }

  if (artifact.type === "intelligence_departments") {
    return (
      <>
        <h3 className="font-medium mb-1">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">
          Real-time visibility across the dealership — pick a department to see gross
          profit, margin, and volume KPIs computed live from NXTDeal's graph.
        </div>

        <div className="grid grid-cols-1 gap-2">
          {artifact.departments.map((dept) => (
            <button
              key={dept.key}
              onClick={() => onSelectIntelligenceDepartment?.(dept.key)}
              className="w-full text-left bg-zinc-950 border border-zinc-800 rounded-lg p-3 hover:border-[#3FBCC4] transition"
            >
              <div className="text-sm font-medium">{dept.title}</div>
              <div className="text-xs text-zinc-500">{dept.subtitle}</div>
            </button>
          ))}
        </div>
      </>
    );
  }

  if (artifact.type === "intelligence_dashboard") {
    const dashboard = artifact.dashboard;

    function formatKpiValue(k: (typeof dashboard.kpis)[number]) {
      let base: string;

      if (k.format === "currency") {
        base = `$${k.value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
      } else if (k.format === "percent") {
        base = `${k.value}%`;
      } else if (k.format === "ratio") {
        base = `${k.value}x`;
      } else {
        base = k.value.toLocaleString();
      }

      return k.suffix ? `${base}${k.suffix}` : base;
    }

    return (
      <>
        <h3 className="font-medium mb-1">{dashboard.title}</h3>
        <div className="text-xs text-zinc-500 mb-4">{dashboard.subtitle}</div>

        {dashboard.alert && (
          <div className="mb-4 bg-[#FBCF09]/10 border border-[#FBCF09]/30 rounded-lg p-3">
            <div className="text-xs font-medium text-[#FBCF09] mb-1">
              🔍 {dashboard.alert.label}
            </div>
            <div className="text-xs text-zinc-300">{dashboard.alert.description}</div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-2 mb-4">
          {dashboard.kpis.map((k) => (
            <div key={k.key} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
              <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-1">
                {k.label}
              </div>
              <div className="text-lg font-medium mb-1">{formatKpiValue(k)}</div>
              {k.has_history ? (
                k.delta_pct === null ? (
                  <div className="text-[11px] text-zinc-500">± no change vs {k.compared_to}</div>
                ) : (
                  <div
                    className={
                      k.delta_pct >= 0
                        ? "text-[11px] text-green-400"
                        : "text-[11px] text-[#EE3C25]"
                    }
                  >
                    {k.delta_pct >= 0 ? "▲" : "▼"} {Math.abs(k.delta_pct)}% vs {k.compared_to}
                  </div>
                )
              ) : (
                <div className="text-[11px] text-zinc-500">Not enough history yet</div>
              )}
            </div>
          ))}
        </div>

        <div className="text-[10px] uppercase tracking-wider text-zinc-500 mb-2">
          Key Capabilities
        </div>
        <div className="space-y-2">
          {dashboard.capabilities.map((cap, i) => (
            <div key={i} className="bg-zinc-950 border border-zinc-800 rounded-lg p-3">
              <div className="text-sm font-medium mb-1">{cap.title}</div>
              <div className="text-xs text-zinc-500">{cap.description}</div>
            </div>
          ))}
        </div>
      </>
    );
  }

  if (artifact.type === "bot_coverage_list") {
    return (
      <>
        <h3 className="font-medium mb-4">{artifact.title}</h3>
        {artifact.coverage.length === 0 ? (
          <div className="text-sm text-zinc-500">No bot coverage has been activated yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
                  <th className="p-2 font-medium">Employee</th>
                  <th className="p-2 font-medium">Mode</th>
                  <th className="p-2 font-medium">Section</th>
                  <th className="p-2 font-medium">Window</th>
                  <th className="p-2 font-medium">Status</th>
                  <th className="p-2 font-medium">Activated By</th>
                </tr>
              </thead>
              <tbody>
                {artifact.coverage.map((c) => (
                  <tr key={c.id} className="border-b border-zinc-800/60 last:border-0">
                    <td className="p-2 font-mono">{c.employee_id}</td>
                    <td className="p-2">{c.mode}</td>
                    <td className="p-2 text-zinc-400">{c.section}</td>
                    <td className="p-2 text-zinc-400 text-xs">
                      {new Date(c.starts_at).toLocaleString()} → {new Date(c.ends_at).toLocaleString()}
                    </td>
                    <td className="p-2">
                      {c.status === "active" ? (
                        <span className="text-green-400">Active</span>
                      ) : (
                        <span className="text-zinc-500">Ended</span>
                      )}
                    </td>
                    <td className="p-2 text-zinc-400">{c.activated_by}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }

  if (artifact.type === "employee_value_list") {
    return (
      <>
        <h3 className="font-medium mb-2">{artifact.title}</h3>
        <div className="text-xs text-zinc-500 mb-4 bg-zinc-950 border border-zinc-800 rounded-lg p-2">
          {artifact.disclaimer}
        </div>
        {artifact.employees.length === 0 ? (
          <div className="text-sm text-zinc-500">No employee data available yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs uppercase tracking-wider text-zinc-500 border-b border-zinc-800">
                  <th className="p-2 font-medium">Employee</th>
                  <th className="p-2 font-medium">Department</th>
                  <th className="p-2 font-medium">Tier</th>
                  <th className="p-2 font-medium">Est. Monthly Value</th>
                  <th className="p-2 font-medium">Basis</th>
                  <th className="p-2 font-medium">Automation</th>
                </tr>
              </thead>
              <tbody>
                {artifact.employees.map((emp) => (
                  <tr key={emp.employee_id} className="border-b border-zinc-800/60 last:border-0">
                    <td className="p-2">
                      <div>{emp.name}</div>
                      <div className="text-xs text-zinc-500">{emp.title ?? "—"}</div>
                    </td>
                    <td className="p-2 text-zinc-400">{emp.department ?? "—"}</td>
                    <td className="p-2 text-zinc-400">{emp.tier}</td>
                    <td className="p-2 font-mono">
                      ${emp.monthly_value_estimate.toLocaleString()}
                    </td>
                    <td className="p-2">
                      <span
                        className={
                          emp.basis === "ledger"
                            ? "text-green-400"
                            : emp.basis === "blended"
                            ? "text-[#FBCF09]"
                            : "text-zinc-500"
                        }
                      >
                        {emp.basis === "ledger"
                          ? "Ledger-verified"
                          : emp.basis === "blended"
                          ? "Blended"
                          : "Industry estimate"}
                      </span>
                    </td>
                    <td className="p-2 text-zinc-400">
                      {emp.automation_coverage
                        ? `${emp.automation_coverage.automation_pct}%`
                        : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </>
    );
  }

  // artifact.type === "dashboard"
  const CHART_COLORS = PRODUCT_ACCENT_COLORS;
  const chartTypeOptions: { key: typeof chartType; label: string }[] = [
    { key: "bar", label: "Bar" },
    { key: "line", label: "Line" },
    { key: "pie", label: "Pie" },
    { key: "donut", label: "Donut" },
  ];

  return (
    <>
      <div className="flex items-center justify-between mb-4">
        <h3 className="font-medium">{artifact.title}</h3>
        <div className="flex gap-1 bg-zinc-950 border border-zinc-800 rounded-lg p-0.5">
          {chartTypeOptions.map((opt) => (
            <button
              key={opt.key}
              onClick={() => setChartType(opt.key)}
              className={
                chartType === opt.key
                  ? "text-xs px-2 py-1 rounded-md bg-[#3FBCC4] text-black font-medium"
                  : "text-xs px-2 py-1 rounded-md text-zinc-400 hover:text-white"
              }
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {artifact.data.length === 0 ? (
        <div className="text-sm text-zinc-500">No data available for this dashboard yet.</div>
      ) : (
        <div className="h-64">
          <ResponsiveContainer width="100%" height="100%">
            {chartType === "bar" ? (
              <BarChart data={artifact.data}>
                <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis />
                <Tooltip />
                <Bar dataKey="value" fill="#3FBCC4" radius={[4, 4, 0, 0]} />
              </BarChart>
            ) : chartType === "line" ? (
              <LineChart data={artifact.data}>
                <XAxis dataKey="name" tick={{ fontSize: 11 }} interval={0} angle={-20} textAnchor="end" height={50} />
                <YAxis />
                <Tooltip />
                <Line type="monotone" dataKey="value" stroke="#3FBCC4" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            ) : (
              <PieChart>
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Pie
                  data={artifact.data}
                  dataKey="value"
                  nameKey="name"
                  cx="50%"
                  cy="50%"
                  outerRadius={80}
                  innerRadius={chartType === "donut" ? 45 : 0}
                  label={({ name }) => name}
                >
                  {artifact.data.map((_, i) => (
                    <Cell key={i} fill={CHART_COLORS[i % CHART_COLORS.length]} />
                  ))}
                </Pie>
              </PieChart>
            )}
          </ResponsiveContainer>
        </div>
      )}
    </>
  );
}
