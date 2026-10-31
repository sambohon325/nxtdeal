"use client";
import { WorkButton, WorkInput , WorkStat} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Administration's "Organizations" + "System Configuration" items
// (Administration Control Center rebuild, continued) -- one real singleton
// settings record (core/system_config.py): dealership profile, locations,
// business hours, defaults (currency/timezone), feature flags. Viewing is
// open to any authenticated role; editing is ADMIN/OPERATIONS-only (the
// backend itself enforces this -- a non-admin caller here will simply see
// every mutation fail with a real "Admin/Operations role required" error).
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import { LobbyInformationEditor } from "@/components/LobbyInformationEditor";
import {
  getSystemConfig,
  updateOrganizationProfile,
  addLocation,
  removeLocation,
  updateBusinessHours,
  updateDefaults,
  setFeatureFlag,
  WEEKDAYS,
  FEATURE_FLAG_KEYS,
  type SystemConfig,
} from "@/lib/systemConfig";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

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

function Input({ value, onChange, placeholder }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return (
    <WorkField label={placeholder || "Value"}><WorkInput
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 w-full"
    /></WorkField>
  );
}

export function OrganizationsBoard({ theme }: { theme: Theme }) {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [tab, setTab] = useState<"profile" | "locations" | "hours" | "defaults" | "flags" | "lobby">("profile");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const [profile, setProfile] = useState<Partial<SystemConfig>>({});
  const [locName, setLocName] = useState("");
  const [locAddress, setLocAddress] = useState("");
  const [locPrimary, setLocPrimary] = useState(false);

  function refresh() {
    setLoading(true);
    setError(null);
    getSystemConfig()
      .then((c) => {
        setConfig(c);
        setProfile({
          dealership_name: c.dealership_name,
          dba_name: c.dba_name,
          ein: c.ein,
          address_line1: c.address_line1,
          address_line2: c.address_line2,
          city: c.city,
          state: c.state,
          zip_code: c.zip_code,
          phone: c.phone,
          website_url: c.website_url,
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load System Configuration."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function handleSaveProfile() {
    try {
      const updated = await updateOrganizationProfile(profile);
      setConfig(updated);
      setMessage("Organization profile saved.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save profile.");
    }
  }

  async function handleAddLocation() {
    if (!locName.trim()) return;
    try {
      const updated = await addLocation(locName.trim(), locAddress, locPrimary);
      setConfig(updated);
      setLocName("");
      setLocAddress("");
      setLocPrimary(false);
      setMessage("Location added.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to add location.");
    }
  }

  async function handleRemoveLocation(index: number) {
    try {
      const updated = await removeLocation(index);
      setConfig(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to remove location.");
    }
  }

  async function handleHours(day: string, hours: string) {
    try {
      const updated = await updateBusinessHours(day, hours);
      setConfig(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update business hours.");
    }
  }

  async function handleDefaults(field: "default_currency" | "default_timezone", value: string) {
    try {
      const updated = await updateDefaults({ [field]: value });
      setConfig(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update defaults.");
    }
  }

  async function handleFlag(flag: string, enabled: boolean) {
    try {
      const updated = await setFeatureFlag(flag, enabled);
      setConfig(updated);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update feature flag.");
    }
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Locations" value={String(config?.locations.length ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Currency" value={config?.default_currency ?? "—"} color={RIBBON[1]} />
        <Kpi theme={theme} label="Timezone" value={config?.default_timezone?.split("/")[1] ?? "—"} color={RIBBON[2]} />
        {config?.can_manage_system===true&&<Kpi theme={theme} label="Flags Enabled" value={String(Object.values(config?.feature_flags ?? ({} as Record<string, boolean>)).filter(Boolean).length)} color={RIBBON[3]} />}
      </div>

      <div className="flex items-center gap-1.5 px-4 py-2 border-b border-zinc-800">
        {([
          ["profile", "Dealership Profile"],
          ["locations", "Locations"],
          ["hours", "Business Hours"],
          ["defaults", "Defaults"],
          ["flags", "Feature Flags"],
          ["lobby", "Lobby Information"],
        ] as const).filter(([key])=>key!=="flags"||config?.can_manage_system===true).map(([key, label]) => (
          <WorkButton data-work-view aria-pressed={tab === key} type="submit"
            key={key}
            onClick={() => setTab(key)}
            className={`text-xs px-2.5 py-1 rounded-full font-brand uppercase tracking-wide transition ${tab === key ? "bg-zinc-200 text-black font-medium" : "bg-zinc-200/10 text-zinc-400 hover:text-white"}`}
          >
            {label}
          </WorkButton>
        ))}
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}
      {message && <div className="mx-4 mt-2 text-xs text-emerald-400">{message}</div>}

      <div className="flex-1 p-4">
        {loading || !config ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : tab === "lobby" ? <LobbyInformationEditor /> : tab === "profile" ? (
          <div className="space-y-2 max-w-md">
            <Input value={profile.dealership_name || ""} onChange={(v) => setProfile({ ...profile, dealership_name: v })} placeholder="Dealership name" />
            <Input value={profile.dba_name || ""} onChange={(v) => setProfile({ ...profile, dba_name: v })} placeholder="DBA name (optional)" />
            <Input value={profile.ein || ""} onChange={(v) => setProfile({ ...profile, ein: v })} placeholder="EIN" />
            <Input value={profile.address_line1 || ""} onChange={(v) => setProfile({ ...profile, address_line1: v })} placeholder="Address line 1" />
            <Input value={profile.address_line2 || ""} onChange={(v) => setProfile({ ...profile, address_line2: v })} placeholder="Address line 2" />
            <div className="grid grid-cols-3 gap-2">
              <Input value={profile.city || ""} onChange={(v) => setProfile({ ...profile, city: v })} placeholder="City" />
              <Input value={profile.state || ""} onChange={(v) => setProfile({ ...profile, state: v })} placeholder="State" />
              <Input value={profile.zip_code || ""} onChange={(v) => setProfile({ ...profile, zip_code: v })} placeholder="ZIP" />
            </div>
            <Input value={profile.phone || ""} onChange={(v) => setProfile({ ...profile, phone: v })} placeholder="Phone" />
            <Input value={profile.website_url || ""} onChange={(v) => setProfile({ ...profile, website_url: v })} placeholder="Website URL" />
            <Btn tone="primary" onClick={handleSaveProfile}>Save Profile</Btn>
          </div>
        ) : tab === "locations" ? (
          <div className="space-y-4">
            <div className="rounded border border-zinc-800 p-3 space-y-2 max-w-md">
              <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">Add Location</div>
              <Input value={locName} onChange={setLocName} placeholder="Location name" />
              <Input value={locAddress} onChange={setLocAddress} placeholder="Address" />
              <label className="flex items-center gap-1.5 text-xs text-zinc-400">
                <WorkInput type="checkbox" checked={locPrimary} onChange={(e) => setLocPrimary(e.target.checked)} />
                Primary location
              </label>
              <Btn tone="primary" onClick={handleAddLocation} disabled={!locName.trim()}>Add Location</Btn>
            </div>
            <div className="space-y-1">
              {config.locations.length === 0 && <div className="text-xs text-zinc-600">No locations added.</div>}
              {config.locations.map((loc, i) => (
                <div key={i} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div>
                    <span className="text-zinc-200">{loc.name}</span>
                    <span className="text-zinc-600 ml-2">{loc.address}</span>
                    {loc.is_primary && <span className="ml-2 px-1.5 py-0.5 rounded bg-blue-950/40 text-blue-300 text-xs">primary</span>}
                  </div>
                  <Btn tone="danger" onClick={() => handleRemoveLocation(i)}>Remove</Btn>
                </div>
              ))}
            </div>
          </div>
        ) : tab === "hours" ? (
          <div className="space-y-1 max-w-md">
            {WEEKDAYS.map((day) => (
              <div key={day} className="flex items-center gap-2 text-xs">
                <div className="w-24 text-zinc-400 capitalize">{day}</div>
                <Input
                  value={config.business_hours[day] || ""}
                  onChange={(v) => setConfig({ ...config, business_hours: { ...config.business_hours, [day]: v } })}
                  placeholder="e.g. 9:00 AM - 7:00 PM"
                />
                <Btn onClick={() => handleHours(day, config.business_hours[day] || "")}>Save</Btn>
              </div>
            ))}
          </div>
        ) : tab === "defaults" ? (
          <div className="space-y-3 max-w-md">
            <div>
              <div className="text-xs text-zinc-500 mb-1">Default Currency</div>
              <div className="flex gap-2">
                <Input value={config.default_currency} onChange={(v) => setConfig({ ...config, default_currency: v })} />
                <Btn onClick={() => handleDefaults("default_currency", config.default_currency)}>Save</Btn>
              </div>
            </div>
            <div>
              <div className="text-xs text-zinc-500 mb-1">Default Timezone</div>
              <div className="flex gap-2">
                <Input value={config.default_timezone} onChange={(v) => setConfig({ ...config, default_timezone: v })} />
                <Btn onClick={() => handleDefaults("default_timezone", config.default_timezone)}>Save</Btn>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-2 max-w-md">
            <div className="text-xs text-zinc-600 mb-2">
              These are stored settings toggles -- confirm with core/system_config.py before assuming any of these
              genuinely gate runtime behavior anywhere else in this codebase yet.
            </div>
            {FEATURE_FLAG_KEYS.map((flag) => (
              <label key={flag} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                <span className="text-zinc-200">{flag.replace(/_/g, " ")}</span>
                <WorkInput
                  type="checkbox"
                  checked={!!config.feature_flags[flag]}
                  onChange={(e) => handleFlag(flag, e.target.checked)}
                />
              </label>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
