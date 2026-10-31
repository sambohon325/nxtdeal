"use client";
import { WorkInput, WorkButton } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// The gear icon's account settings Dash (session 74). Sam: "we need to have a gear
// icon on the far right at the top - when clicked, it should show user profile
// settings / password administration, notification settings." Two real tabs:
// Profile & Password (read-only employee record via GET /me + a change-password form
// reusing the already-built POST /auth/change-password) and Notifications (real
// per-employee toggle storage via GET/POST /notification-preferences,
// core/notification_preferences.py -- see that module's own honest scope note: these
// toggles are persisted for real but nothing downstream reads them to gate delivery
// yet).
//
// AccountSettingsBody is exported chrome-free, same split as
// MenuDashPanel/MenuDashBody and WorkflowDashPanel/WorkflowWindowBody, so both the
// in-page docked Dash (AccountDashPanel below) and the pop-out route
// (app/panel/account/page.tsx) render the exact same real functionality.

import { useEffect, useState } from "react";
import { getMyAiStatus, setMyAi, type MyAiStatus } from "@/lib/aiSpend";
import { API_BASE } from "@/lib/api";
import { authHeaders, clearSession, getSession, saveSession } from "@/lib/auth";

export type AccountTabKey = "profile" | "notifications";

export const ACCOUNT_TABS: { key: AccountTabKey; label: string }[] = [
  { key: "profile", label: "Profile & Password" },
  { key: "notifications", label: "Notifications" },
];

type MyProfile = {
  id: string;
  entity_type: string;
  attributes: Record<string, unknown>;
  role: string;
};

function prettify(key: string): string {
  return key.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Fields worth surfacing on the profile card, in a sensible read order -- the rest of
// whatever's on the Employee entity (there may be internal bookkeeping fields) is left
// out rather than dumping the raw attribute bag.
const PROFILE_FIELD_ORDER = ["FirstName", "LastName", "Title", "Department", "Email", "EmployeeID"];

function ProfileTab({ hideAssistant = false }: { hideAssistant?: boolean }) {
  const [profile, setProfile] = useState<MyProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [pwError, setPwError] = useState("");
  const [pwSuccess, setPwSuccess] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE}/me`, { headers: { ...authHeaders() } })
      .then((r) => r.json())
      .then((d) => {
        if (cancelled) return;
        if (d.error) {
          setLoadError(d.error);
        } else {
          setProfile(d);
        }
      })
      .catch(() => {
        if (!cancelled) setLoadError("Unable to reach NXTDeal backend.");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function handleChangePassword() {
    if (saving) return;

    if (!oldPassword || !newPassword || !confirmPassword) {
      setPwError("All fields are required.");
      setPwSuccess(false);
      return;
    }

    if (newPassword !== confirmPassword) {
      setPwError("New passwords don't match.");
      setPwSuccess(false);
      return;
    }

    setPwError("");
    setSaving(true);

    try {
      const res = await fetch(`${API_BASE}/auth/change-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
      });
      const data = await res.json();

      if (!res.ok || data.error) {
        if (data.error === "Invalid or expired token") {
          clearSession();
          window.location.href = "/";
          return;
        }
        setPwError(data.error ?? "Unable to change password.");
        setPwSuccess(false);
        return;
      }

      const currentSession = getSession();
      if (currentSession && typeof data.token === "string") {
        saveSession({ ...currentSession, token: data.token });
      }

      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPwSuccess(true);
    } catch {
      setPwError("Unable to reach NXTDeal backend.");
      setPwSuccess(false);
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return <div className="text-sm text-zinc-600 p-4">Loading…</div>;
  }

  if (loadError || !profile) {
    return <div className="text-sm text-red-400 p-4">{loadError ?? "Unable to load your profile."}</div>;
  }

  const attrs = profile.attributes;
  const orderedKeys = PROFILE_FIELD_ORDER.filter((k) => attrs[k] !== undefined);
  const remainingKeys = Object.keys(attrs).filter((k) => !PROFILE_FIELD_ORDER.includes(k));

  return (
    <div className="p-4 space-y-6">
      <div className="rounded-lg border border-zinc-800 overflow-hidden">
        <div className="flex items-center justify-between px-3 py-2 bg-brand-charcoal border-b border-zinc-800">
          <div className="text-xs">
            <span className="text-zinc-500">{profile.entity_type}</span>{" "}
            <span className="text-zinc-200">{profile.id}</span>
          </div>
          <span className="text-xs px-2 py-0.5 rounded bg-zinc-800 text-zinc-300 uppercase tracking-wide">
            {profile.role}
          </span>
        </div>
        <div className="p-2">
          <table className="w-full text-xs">
            <tbody>
              {[...orderedKeys, ...remainingKeys].map((k) => (
                <tr key={k} className="border-b border-zinc-900 last:border-0 align-top">
                  <td className="py-1.5 pr-3 text-zinc-500 whitespace-nowrap">{prettify(k)}</td>
                  <td className="py-1.5 text-zinc-200">{String(attrs[k] ?? "—")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div>
        <div className="text-sm font-medium mb-1">Change Password</div>
        <p className="text-xs text-zinc-500 mb-3">
          Requires your current password. This changes the password for this account only.
        </p>

        {pwError && <div className="mb-3 text-xs text-red-400">{pwError}</div>}
        {pwSuccess && <div className="mb-3 text-xs text-emerald-400">Password updated.</div>}

        <WorkField label="Current password"><WorkInput
          type="password"
          placeholder="Current password"
          value={oldPassword}
          onChange={(e) => setOldPassword(e.target.value)}
          className="w-full h-9 px-3 mb-2 text-sm rounded-lg bg-zinc-900 border border-zinc-800 focus:outline-none focus:border-zinc-600"
        /></WorkField>
        <WorkField label="New password"><WorkInput
          type="password"
          placeholder="New password"
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
          className="w-full h-9 px-3 mb-2 text-sm rounded-lg bg-zinc-900 border border-zinc-800 focus:outline-none focus:border-zinc-600"
        /></WorkField>
        <WorkField label="Confirm new password"><WorkInput
          type="password"
          placeholder="Confirm new password"
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") handleChangePassword();
          }}
          className="w-full h-9 px-3 mb-3 text-sm rounded-lg bg-zinc-900 border border-zinc-800 focus:outline-none focus:border-zinc-600"
        /></WorkField>

        <WorkButton type="submit"
          onClick={handleChangePassword}
          disabled={saving}
          className="text-xs px-3 py-1.5 rounded-lg bg-zinc-200 text-black font-medium hover:bg-white transition disabled:opacity-40"
        >
          {saving ? "Updating…" : "Update Password"}
        </WorkButton>
      </div>

      {!hideAssistant && <AiPreferenceCard />}
    </div>
  );
}

// Per-user AI on/off (Freemium 2026-08-03). Some people simply don't want AI in their face -- this
// lets a user hide the AI chat, bot, and assistant across NXTDeal for themselves, without affecting
// anyone else. If an admin has turned AI off dealer-wide, this shows that state read-only.
function AiPreferenceCard() {
  const [status, setStatus] = useState<MyAiStatus | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    getMyAiStatus().then(setStatus).catch(() => {});
  }, []);

  async function toggle() {
    if (!status) return;
    setSaving(true);
    try {
      // Turn AI on for me = clear my opt-out. setMyAi(enabled) where enabled = currently-off.
      const next = await setMyAi(status.user_ai_off);
      setStatus(next);
    } catch {
      /* ignore */
    } finally {
      setSaving(false);
    }
  }

  if (!status) return null;
  const dealerOff = !status.dealer_ai_enabled;
  const onForMe = status.ai_enabled;

  return (
    <div>
      <div className="text-sm font-medium mb-1">AI Assistant</div>
      <p className="text-xs text-zinc-500 mb-3">
        {dealerOff
          ? "AI is turned off for your whole dealership by an admin. The AI chat, bot, and assistant are hidden."
          : "Turn AI on or off for yourself. When off, the AI chat, bot, and assistant simply disappear from your view — everything else works exactly the same, and NXTDeal keeps running normally in the background."}
      </p>
      <div className="rounded-lg border border-zinc-800 flex items-center justify-between px-3 py-2.5">
        <span className="text-sm text-zinc-200">AI enabled for me</span>
        <Toggle on={onForMe} onClick={() => (dealerOff || saving ? undefined : toggle())} />
      </div>
    </div>
  );
}

type Preferences = Record<string, boolean>;

const PREFERENCE_LABELS: Record<string, string> = {
  compliance_alerts: "Compliance alerts",
  workflow_updates: "Workflow updates",
  direct_messages: "Direct messages",
  channel_messages: "Channel messages",
  bot_suggestions: "Bot task suggestions",
};

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <WorkButton type="submit"
      onClick={onClick}
      role="switch"
      aria-checked={on}
      className={
        on
          ? "relative w-9 h-5 rounded-full bg-brand-teal transition shrink-0"
          : "relative w-9 h-5 rounded-full bg-zinc-700 transition shrink-0"
      }
    >
      <span
        className={
          on
            ? "absolute top-0.5 left-[18px] w-4 h-4 rounded-full bg-white transition"
            : "absolute top-0.5 left-0.5 w-4 h-4 rounded-full bg-white transition"
        }
      />
    </WorkButton>
  );
}

function NotificationsTab() {
  const [prefs, setPrefs] = useState<Preferences | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;

    fetch(`${API_BASE}/notification-preferences`, { headers: { ...authHeaders() } })
      .then((r) => r.json())
      .then((d) => {
        if (!cancelled) setPrefs(d.preferences ?? {});
      })
      .catch(() => {
        if (!cancelled) setPrefs({});
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, []);

  async function toggle(key: string) {
    if (!prefs) return;

    const next = { ...prefs, [key]: !prefs[key] };
    setPrefs(next);
    setSaving(true);

    try {
      const res = await fetch(`${API_BASE}/notification-preferences`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ preferences: next }),
      });
      const data = await res.json();
      if (data.preferences) {
        setPrefs(data.preferences);
        setSavedAt(Date.now());
      }
    } catch {
      // Leave the optimistic toggle in place -- a real network failure here isn't
      // worth a jarring revert for a personal preference toggle.
    } finally {
      setSaving(false);
    }
  }

  if (loading || !prefs) {
    return <div className="text-sm text-zinc-600 p-4">Loading…</div>;
  }

  return (
    <div className="p-4">
      <p className="text-xs text-zinc-500 mb-4">
        Choose what you want to be notified about. These preferences are saved to your account.
      </p>

      <div className="rounded-lg border border-zinc-800 divide-y divide-zinc-900">
        {Object.keys(PREFERENCE_LABELS).map((key) => (
          <div key={key} className="flex items-center justify-between px-3 py-2.5">
            <span className="text-sm text-zinc-200">{PREFERENCE_LABELS[key]}</span>
            <Toggle on={!!prefs[key]} onClick={() => toggle(key)} />
          </div>
        ))}
      </div>

      <div className="text-xs text-zinc-600 mt-2 h-4">
        {saving ? "Saving…" : savedAt ? "Saved." : ""}
      </div>
    </div>
  );
}

export function AccountSettingsBody({
  activeTab,
  onSelectTab,
  hideAssistant = false,
}: {
  hideAssistant?: boolean;
  activeTab: AccountTabKey;
  onSelectTab: (tab: AccountTabKey) => void;
}) {
  const session = getSession();

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-brand-ink">
      <div className="border-b border-zinc-800 bg-brand-charcoal px-3 py-2">
        <div className="flex items-center gap-1 flex-wrap">
          {ACCOUNT_TABS.map((tab) => (
            <WorkButton type="submit"
              key={tab.key}
              onClick={() => onSelectTab(tab.key)}
              className={
                tab.key === activeTab
                  ? "text-xs px-2.5 py-1 rounded-md bg-zinc-200 text-black font-medium transition"
                  : "text-xs px-2.5 py-1 rounded-md text-zinc-400 hover:text-white hover:bg-zinc-900 transition"
              }
            >
              {tab.label}
            </WorkButton>
          ))}
          {session && (
            <span className="ml-auto text-xs text-zinc-600 self-center pr-1">
              Signed in as {session.role}
            </span>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto">
        {activeTab === "profile" ? <ProfileTab hideAssistant={hideAssistant} /> : <NotificationsTab />}
      </div>
    </div>
  );
}

// Charcoal Dash chrome, same shape as MenuDashPanel/WorkflowDashPanel -- a header with
// a teal left stripe, pop-out (⇱) and close (×) -- so the account Dash is visually
// indistinguishable from a Top Menu Dash or a workflow Dash except for its content.
export function AccountDashPanel({
  itemKey,
  onSelectItem,
  onClose,
  onPopOut,
}: {
  itemKey: string;
  onSelectItem: (key: string) => void;
  onClose: () => void;
  onPopOut: () => void;
}) {
  const activeTab: AccountTabKey = itemKey === "notifications" ? "notifications" : "profile";

  return (
    <div className="flex-1 min-w-0 flex flex-col bg-brand-ink border-x border-zinc-800">
      <div className="relative flex items-center justify-between pl-5 pr-4 py-3 border-b border-zinc-800 shrink-0 bg-brand-charcoal overflow-hidden">
        <span className="absolute left-0 top-0 bottom-0 w-1.5 bg-brand-teal" />
        <div className="flex items-center gap-2 min-w-0">
          <span className="font-brand font-bold uppercase tracking-wide truncate">Account Settings</span>
        </div>
        <div className="flex items-center gap-3 shrink-0 ml-3">
          <WorkButton type="submit"
            onClick={onPopOut}
            title="Pop out to its own window -- drag it to a second monitor"
            className="text-zinc-400 hover:text-white transition text-sm leading-none"
          >
            ⇱
          </WorkButton>
          <WorkButton type="submit" onClick={onClose} className="text-zinc-400 hover:text-white transition text-lg leading-none">
            ×
          </WorkButton>
        </div>
      </div>

      <AccountSettingsBody activeTab={activeTab} onSelectTab={onSelectItem} />
    </div>
  );
}
