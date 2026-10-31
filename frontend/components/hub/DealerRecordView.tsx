"use client";

import { dealerDisplayName } from "@/lib/brandDisplay";

// NXTDeal Hub -- "Dealer Management" rebuild (2026-07-19). The real per-dealer
// Dealer Record -- replaces the old small DealerDetailPanel modal with a full
// workspace covering Dealer Profile, Subscription Info, NXTDeal Version, plus the
// pre-existing Status/API Base URL controls (kept, unchanged behavior).
//
// Sam's framing for the whole Hub rebuild: "Salesforce Trust + Azure Admin Center +
// HubSpot Operations Hub + Datadog + 20 Group Intelligence inside one control
// center." This is the "click into one customer's record" screen that framing
// implies -- a real editable record, not a read-only summary.

import { useEffect, useState } from "react";
import DealerProvisionControl from "@/components/hub/DealerProvisionControl";
import {
  HubApiError,
  updateDealerStatus,
  updateDealerApiBaseUrl,
  updateDealerProfile,
  updateDealerSubscription,
  updateDealerVersion,
  DEALER_ALL_STATUSES,
  DEALER_INDUSTRY_TYPES,
  type Dealer,
} from "@/lib/hubApi";

function errorMessage(error: unknown): string {
  return error instanceof HubApiError ? error.message : "Unable to reach the Hub.";
}

const STATUS_COLORS: Record<string, string> = {
  lead: "text-zinc-400",
  demo: "text-sky-400",
  trial: "text-blue-400",
  provisioning: "text-yellow-400",
  active: "text-green-400",
  expansion: "text-emerald-400",
  churn_risk: "text-orange-400",
  suspended: "text-red-400",
};

function SectionCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="bg-zinc-900 rounded-lg p-5 mb-4">
      <h4 className="font-brand font-bold uppercase tracking-wide text-xs text-zinc-400 mb-3">
        {title}
      </h4>
      {children}
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">{label}</div>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 focus:outline-none text-sm"
      />
    </div>
  );
}

function ListField({
  label,
  values,
  onChange,
}: {
  label: string;
  values: string[];
  onChange: (v: string[]) => void;
}) {
  const [text, setText] = useState(values.join(", "));

  useEffect(() => {
    setText(values.join(", "));
  }, [values]);

  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
        {label} (comma-separated)
      </div>
      <input
        value={text}
        onChange={(e) => {
          setText(e.target.value);
          onChange(
            e.target.value
              .split(",")
              .map((v) => v.trim())
              .filter(Boolean)
          );
        }}
        className="w-full h-9 px-3 rounded bg-zinc-950 border border-zinc-800 focus:outline-none text-sm"
      />
    </div>
  );
}

export default function DealerRecordView({
  dealer,
  onClose,
  onChanged,
}: {
  dealer: Dealer;
  onClose: () => void;
  onChanged: (updated: Dealer) => void;
}) {
  const [saving, setSaving] = useState<string>("");
  const [error, setError] = useState("");

  // Profile
  const [group, setGroup] = useState(dealer.group ?? "");
  const [oem, setOem] = useState(dealer.oem ?? "");
  const [locationCount, setLocationCount] = useState(String(dealer.location_count));
  const [industryType, setIndustryType] = useState(dealer.industry_type);

  // Subscription
  const [planTier, setPlanTier] = useState(dealer.plan_tier);
  const [activeModules, setActiveModules] = useState<string[]>(dealer.active_modules);
  const [renewalDate, setRenewalDate] = useState(dealer.renewal_date ?? "");
  const [seatCount, setSeatCount] = useState(
    dealer.seat_count !== null ? String(dealer.seat_count) : ""
  );

  // Version
  const [currentRelease, setCurrentRelease] = useState(dealer.current_release ?? "");
  const [betaPrograms, setBetaPrograms] = useState<string[]>(dealer.beta_programs);

  // Status / API base URL (pre-existing behavior, carried over from the old modal)
  const [apiBaseUrl, setApiBaseUrl] = useState(dealer.api_base_url ?? "");

  useEffect(() => {
    setGroup(dealer.group ?? "");
    setOem(dealer.oem ?? "");
    setLocationCount(String(dealer.location_count));
    setIndustryType(dealer.industry_type);
    setPlanTier(dealer.plan_tier);
    setActiveModules(dealer.active_modules);
    setRenewalDate(dealer.renewal_date ?? "");
    setSeatCount(dealer.seat_count !== null ? String(dealer.seat_count) : "");
    setCurrentRelease(dealer.current_release ?? "");
    setBetaPrograms(dealer.beta_programs);
    setApiBaseUrl(dealer.api_base_url ?? "");
  }, [dealer]);

  async function run(key: string, fn: () => Promise<Dealer>) {
    setSaving(key);
    setError("");
    try {
      const updated = await fn();
      onChanged(updated);
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setSaving("");
    }
  }

  return (
    <div className="fixed inset-0 bg-black/60 flex items-start justify-center z-50 px-8 py-8 overflow-y-auto">
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl p-6 w-full max-w-3xl">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h3 className="text-xl font-brand font-bold">{dealerDisplayName(dealer.name)}</h3>
            <div className="text-xs text-zinc-500 mt-1">
              {dealer.dealer_id} · {dealer.slug} · {dealer.contact_email}
            </div>
          </div>
          <button onClick={onClose} className="text-zinc-500 hover:text-white text-sm">
            Close
          </button>
        </div>

        {error && (
          <div className="mt-3 mb-2 text-sm text-red-400 bg-red-950/30 border border-red-900 rounded-lg px-4 py-3">
            {error}
          </div>
        )}

        <div className="mt-4 grid grid-cols-2 gap-4">
          <div>
            <SectionCard title="Lifecycle Status">
              <div className="flex flex-wrap gap-1.5 mb-1">
                {DEALER_ALL_STATUSES.map((s) => (
                  <button
                    key={s}
                    onClick={() =>
                      run("status", () => updateDealerStatus(dealer.dealer_id, s))
                    }
                    disabled={!!saving}
                    className={
                      s === dealer.status
                        ? "bg-zinc-200 text-black px-2.5 py-1 rounded text-[11px] font-medium"
                        : `bg-zinc-800 hover:text-white px-2.5 py-1 rounded text-[11px] transition ${
                            STATUS_COLORS[s] ?? "text-zinc-400"
                          }`
                    }
                  >
                    {s.replace("_", " ")}
                  </button>
                ))}
              </div>
            </SectionCard>

            <SectionCard title="Dealer Profile">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <Field label="Group (multi-rooftop)" value={group} onChange={setGroup} placeholder="e.g. NXTDeal Auto Group" />
                <Field label="OEM" value={oem} onChange={setOem} placeholder="e.g. Ford" />
                <Field label="Location Count" value={locationCount} onChange={setLocationCount} />
                <div>
                  <div className="text-[10px] uppercase tracking-wide text-zinc-500 mb-1">
                    Industry Type
                  </div>
                  <select
                    value={industryType}
                    onChange={(e) => setIndustryType(e.target.value)}
                    className="w-full h-9 px-2 rounded bg-zinc-950 border border-zinc-800 text-sm"
                  >
                    {DEALER_INDUSTRY_TYPES.map((t) => (
                      <option key={t} value={t}>
                        {t.replace("_", " ")}
                      </option>
                    ))}
                  </select>
                </div>
              </div>
              <button
                onClick={() =>
                  run("profile", () =>
                    updateDealerProfile(dealer.dealer_id, {
                      group,
                      oem,
                      location_count: Number(locationCount) || 1,
                      industry_type: industryType,
                    })
                  )
                }
                disabled={!!saving}
                className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
              >
                {saving === "profile" ? "Saving…" : "Save Profile"}
              </button>
            </SectionCard>
          </div>

          <div>
            <SectionCard title="Subscription Info">
              <div className="grid grid-cols-2 gap-3 mb-3">
                <Field label="Plan Tier" value={planTier} onChange={setPlanTier} />
                <Field label="Seat Count" value={seatCount} onChange={setSeatCount} />
                <Field
                  label="Renewal Date"
                  value={renewalDate}
                  onChange={setRenewalDate}
                  placeholder="YYYY-MM-DD"
                />
                <div className="col-span-2">
                  <ListField label="Active Modules" values={activeModules} onChange={setActiveModules} />
                </div>
              </div>
              <button
                onClick={() =>
                  run("subscription", () =>
                    updateDealerSubscription(dealer.dealer_id, {
                      plan_tier: planTier,
                      active_modules: activeModules,
                      renewal_date: renewalDate,
                      seat_count: seatCount ? Number(seatCount) : undefined,
                    })
                  )
                }
                disabled={!!saving}
                className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
              >
                {saving === "subscription" ? "Saving…" : "Save Subscription"}
              </button>
            </SectionCard>

            <SectionCard title="NXTDeal Version">
              <div className="grid grid-cols-1 gap-3 mb-3">
                <Field
                  label="Current Release"
                  value={currentRelease}
                  onChange={setCurrentRelease}
                  placeholder="e.g. 2026.07.19"
                />
                <ListField label="Beta Programs" values={betaPrograms} onChange={setBetaPrograms} />
              </div>
              <button
                onClick={() =>
                  run("version", () =>
                    updateDealerVersion(dealer.dealer_id, {
                      current_release: currentRelease,
                      beta_programs: betaPrograms,
                    })
                  )
                }
                disabled={!!saving}
                className="bg-zinc-200 text-black font-medium px-3 py-1.5 rounded text-xs uppercase tracking-wide disabled:opacity-50"
              >
                {saving === "version" ? "Saving…" : "Save Version"}
              </button>
            </SectionCard>
          </div>
        </div>

        <SectionCard title="Deployment (API Base URL)">
          <div className="flex gap-2">
            <input
              value={apiBaseUrl}
              onChange={(e) => setApiBaseUrl(e.target.value)}
              placeholder="https://dealer{N}-api.nxtdeal.app"
              className="flex-1 h-9 px-3 rounded bg-zinc-950 border border-zinc-800 focus:outline-none text-sm"
            />
            <button
              onClick={() =>
                run("api_base_url", () =>
                  updateDealerApiBaseUrl(dealer.dealer_id, apiBaseUrl.trim())
                )
              }
              disabled={!!saving}
              className="bg-zinc-200 text-black font-medium px-4 rounded text-xs uppercase tracking-wide disabled:opacity-50"
            >
              {saving === "api_base_url" ? "Saving…" : "Save"}
            </button>
          </div>
          <DealerProvisionControl
            dealerId={dealer.dealer_id}
            hasApiBaseUrl={!!dealer.api_base_url}
            onProvisioned={(apiUrl) => {
              setApiBaseUrl(apiUrl);
              onChanged({ ...dealer, api_base_url: apiUrl });
            }}
          />
          <p className="text-[11px] text-zinc-500 mt-3">
            Provisioning creates + deploys this dealer&apos;s apps in Coolify and records the API
            URL above automatically. You can also set it manually if you deployed by hand.
          </p>
        </SectionCard>
      </div>
    </div>
  );
}
