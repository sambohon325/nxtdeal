"use client";
import { WorkButton, WorkInput, WorkSelect , WorkStat} from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import { WorkField } from "./WorkField";

// Administration's "Users" item, enriched (Administration Control Center
// rebuild, closing slice, 2026-07-19) -- the central employee directory,
// now a genuine identity + access + security composite per employee rather
// than a flat roster. Reuses every action this rebuild already built rather
// than duplicating any of it: unlock/IP-allowlist (lib/securityAdmin.ts),
// grant/revoke a permission override (lib/rolesPermissions.ts), generate/
// revoke an API key (lib/apiKeys.ts). This board is the one place an admin
// can see and act on all three for one employee without cross-referencing
// three separate screens.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useRef, useState } from "react";
import {
  getUsersOverview,
  getUserDetail,
  type UsersOverview,
  type UserAdministrationRow,
  type UserDetail,
} from "@/lib/adminUsers";
import { unlockAccount, setIpAllowlist } from "@/lib/securityAdmin";
import {
  getPermissionCatalog,
  setPermissionOverride,
  revokeOverride,
  type PermissionCatalog,
} from "@/lib/rolesPermissions";
import { generateApiKey, revokeApiKey, type NewApiKey } from "@/lib/apiKeys";

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

function fmt(ts: string | null | undefined): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString([], { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
  } catch {
    return ts;
  }
}

function UserRow({ row, onOpen }: { row: UserAdministrationRow; onOpen: (id: string) => void }) {
  return (
    <button
      onClick={() => onOpen(row.employee_id)}
      className="w-full flex flex-wrap items-center justify-between gap-3 min-h-11 text-sm px-3 py-2 rounded border border-zinc-800 hover:border-zinc-600 text-left"
    >
      <div className="flex flex-wrap items-center gap-2 min-w-0">
        <span className="text-zinc-200 font-medium truncate">{row.name || row.employee_id}</span>
        <span className="text-zinc-600 font-mono">{row.employee_id}</span>
        <span className="text-zinc-600">{row.title || "—"}</span>
        <span className="text-zinc-600">{row.department || "—"}</span>
        <span className="px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-300 text-xs">{row.role}</span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {row.locked && <span className="px-1.5 py-0.5 rounded bg-red-950/40 text-red-300 text-xs">locked</span>}
        {row.must_change_password && <span className="px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 text-xs">pw reset req.</span>}
        {row.active_permission_overrides > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-blue-950/40 text-blue-300 text-xs">{row.active_permission_overrides} override{row.active_permission_overrides === 1 ? "" : "s"}</span>
        )}
        {row.active_api_keys > 0 && (
          <span className="px-1.5 py-0.5 rounded bg-emerald-950/40 text-emerald-300 text-xs">{row.active_api_keys} key{row.active_api_keys === 1 ? "" : "s"}</span>
        )}
      </div>
    </button>
  );
}

export function UserDetailWorkspace({ theme, employeeId, onClose, onChanged, onDraftOpenChange, onSavingChange }: { theme: Theme; employeeId: string; onClose: () => void; onChanged: () => void; onDraftOpenChange?: (open:boolean)=>void; onSavingChange?: (saving:boolean)=>void }) {
  const [detail, setDetail] = useState<UserDetail | null>(null);
  const [catalog, setCatalog] = useState<PermissionCatalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ipInput, setIpInput] = useState("");
  const [overrideKey, setOverrideKey] = useState("");
  const [overrideGranted, setOverrideGranted] = useState(true);
  const [overrideReason, setOverrideReason] = useState("");
  const [keyLabel, setKeyLabel] = useState("");
  const [newKey, setNewKey] = useState<NewApiKey | null>(null);

  const [ipBaseline, setIpBaseline] = useState("");
  const [overrideTouched, setOverrideTouched] = useState(false);
  const [confirmExit, setConfirmExit] = useState(false);
  const initialized = useRef(false);
  const dirty = ipInput !== ipBaseline || overrideTouched || !!keyLabel.trim() || !!newKey;
  useEffect(() => { onDraftOpenChange?.(dirty); return () => onDraftOpenChange?.(false); }, [dirty,onDraftOpenChange]);
  useEffect(() => { if(!dirty)return; const warn=(e:BeforeUnloadEvent)=>{e.preventDefault();e.returnValue="";}; window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn); },[dirty]);
  const [revision, setRevision] = useState(0);
  const [saving, setSaving] = useState(false);
  const mutationPending = useRef(false);
  useEffect(() => { onSavingChange?.(saving); return () => onSavingChange?.(false); }, [saving, onSavingChange]);
  const refresh = () => setRevision(v => v + 1);
  useEffect(() => {
    let live = true;
    setError(null); setDetail(null);
    Promise.all([getUserDetail(employeeId), getPermissionCatalog()])
      .then(([d, c]) => {
        if (!live) return;
        setDetail(d); setCatalog(c);
        if(!initialized.current){const value=(d.identity_and_access.ip_allowlist || []).join(", "); setIpInput(value);setIpBaseline(value);initialized.current=true;}
        setOverrideKey(current => current || c.categories[0]?.permissions[0]?.key || "");
      }).catch(e => { if (live) setError(e instanceof Error ? e.message : "Unable to load this employee."); });
    return () => { live = false; };
  }, [employeeId, revision]);

  async function handleUnlock() {
    if (mutationPending.current) return;
    mutationPending.current = true; setSaving(true); setError(null);
    try {
      await unlockAccount(employeeId);
      refresh();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to unlock this account.");
    } finally { mutationPending.current = false; setSaving(false); }
  }

  async function handleSetIp() {
    if (mutationPending.current) return;
    mutationPending.current = true; setSaving(true); setError(null);
    try {
      const list = ipInput.split(",").map((s) => s.trim()).filter(Boolean);
      await setIpAllowlist(employeeId, list);
      setIpBaseline(ipInput);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update the IP allowlist.");
    } finally { mutationPending.current = false; setSaving(false); }
  }

  async function handleGrantOverride() {
    if (!overrideKey) return;
    if (mutationPending.current) return;
    mutationPending.current = true; setSaving(true); setError(null);
    try {
      await setPermissionOverride(employeeId, overrideKey, overrideGranted, overrideReason.trim());
      setOverrideReason("");
      setOverrideTouched(false);
      refresh();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to set this permission override.");
    } finally { mutationPending.current = false; setSaving(false); }
  }

  async function handleRevokeOverride(overrideId: string) {
    if (mutationPending.current) return;
    mutationPending.current = true; setSaving(true); setError(null);
    try {
      await revokeOverride(overrideId);
      refresh();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to revoke this override.");
    } finally { mutationPending.current = false; setSaving(false); }
  }

  async function handleGenerateKey() {
    if (mutationPending.current) return;
    mutationPending.current = true; setSaving(true); setError(null);
    try {
      const key = await generateApiKey(keyLabel.trim(), employeeId);
      setNewKey(key);
      setKeyLabel("");
      refresh();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to generate an API key.");
    } finally { mutationPending.current = false; setSaving(false); }
  }

  async function handleRevokeKey(keyId: string) {
    if (mutationPending.current) return;
    mutationPending.current = true; setSaving(true); setError(null);
    try {
      await revokeApiKey(keyId);
      refresh();
      onChanged();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to revoke this key.");
    } finally { mutationPending.current = false; setSaving(false); }
  }

  const attrs = (detail?.employee.attributes || {}) as Record<string, unknown>;
  const name = [attrs.FirstName, attrs.LastName].filter(Boolean).join(" ") || employeeId;

  return (
    <div aria-label="Employee workspace">
      <div
        className={tc(theme, "bg-brand-charcoal text-white", "bg-white text-black")}
        style={{ width: "100%" }}
      >
        <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-800">
          <div>
            <div className="text-sm font-brand font-medium">{name}</div>
            <div className="text-xs text-zinc-500 font-mono">{employeeId} · {String(attrs.Title || "—")} · {String(attrs.Department || "—")}</div>
          </div>
          <Btn disabled={saving} onClick={()=>{if(mutationPending.current)return; dirty?setConfirmExit(true):onClose();}}>← Back to employee directory</Btn>
        </div>

        <fieldset disabled={saving} className="p-4 space-y-4">
          {saving && <p role="status">Saving employee changes. Wait for the result before leaving this screen.</p>}
          {confirmExit&&<section role="alert" className="rounded border border-amber-700 p-3"><h3>Leave unfinished employee work?</h3><p>Your unsaved entries or newly displayed key are still below.</p><Btn onClick={()=>setConfirmExit(false)}>Keep editing employee</Btn><Btn disabled={saving} onClick={()=>{if(!mutationPending.current)onClose();}}>Discard and return to directory</Btn></section>}
          {error && <div role="alert" className="text-sm text-red-400">{error}{!detail && <Btn onClick={refresh}>Retry employee</Btn>}</div>}

          {!detail ? (
            <div role="status" className="text-sm text-zinc-500">{error ? "Employee details unavailable." : "Loading employee…"}</div>
          ) : (
            <>
              {/* Identity + lockout */}
              <details open className="rounded border border-zinc-800 p-3 space-y-2">
                <summary className="text-xs font-brand uppercase tracking-wide text-zinc-500">Identity & Security</summary>
                <div className="text-xs text-zinc-400">
                  Role: <span className="text-zinc-200">{detail.identity_and_access.role}</span>
                  {" · "}Email: <span className="text-zinc-200">{detail.identity_and_access.email || "—"}</span>
                  {detail.identity_and_access.must_change_password && (
                    <span className="ml-2 px-1.5 py-0.5 rounded bg-amber-950/40 text-amber-300 text-xs">password reset required</span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs">
                  {detail.identity_and_access.lockout.locked ? (
                    <>
                      <span className="px-1.5 py-0.5 rounded bg-red-950/40 text-red-300 text-xs">
                        locked until {fmt(detail.identity_and_access.lockout.locked_until)}
                      </span>
                      <Btn tone="primary" onClick={handleUnlock}>Unlock Now</Btn>
                    </>
                  ) : (
                    <span className="text-zinc-500">Not locked · {detail.identity_and_access.lockout.failed_attempts} failed attempt(s) on file</span>
                  )}
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-zinc-500 shrink-0">IP allowlist (comma-separated, empty = unrestricted):</span>
                  <WorkInput
                    aria-label="Employee IP allowlist"
                    value={ipInput}
                    onChange={(e) => setIpInput(e.target.value)}
                    className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 flex-1"
                  />
                  <Btn onClick={handleSetIp}>Save</Btn>
                </div>
              </details>

              {/* Permission overrides */}
              <details className="rounded border border-zinc-800 p-3 space-y-2">
                <summary className="text-xs font-brand uppercase tracking-wide text-zinc-500">Permission Overrides</summary>
                <div className="space-y-1">
                  {detail.identity_and_access.active_permission_overrides.length === 0 && (
                    <div className="text-xs text-zinc-600">No active overrides -- this employee runs on their role's defaults.</div>
                  )}
                  {detail.identity_and_access.active_permission_overrides.map((o) => (
                    <div key={String(o.id)} className="flex items-center justify-between text-xs px-2 py-1 rounded border border-zinc-800">
                      <span>
                        <span className="text-zinc-200">{String(o.permission_key)}</span>
                        <span className={`ml-2 px-1.5 py-0.5 rounded text-xs ${o.granted ? "bg-emerald-950/40 text-emerald-300" : "bg-red-950/40 text-red-300"}`}>
                          {o.granted ? "granted" : "revoked"}
                        </span>
                        {!!o.reason && <span className="text-zinc-600 ml-2">"{String(o.reason)}"</span>}
                      </span>
                      <Btn tone="danger" onClick={() => handleRevokeOverride(String(o.id))}>Remove</Btn>
                    </div>
                  ))}
                </div>
                {catalog && (
                  <div className="flex items-center gap-1.5 pt-1 flex-wrap">
                    <WorkSelect
                      aria-label="Permission to override"
                    value={overrideKey}
                      onChange={(e) => {setOverrideKey(e.target.value);setOverrideTouched(true);}}
                      className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200"
                    >
                      {catalog.categories.map((cat) => (
                        <optgroup key={cat.category} label={cat.category}>
                          {cat.permissions.map((p) => (
                            <option key={p.key} value={p.key}>{p.label}</option>
                          ))}
                        </optgroup>
                      ))}
                    </WorkSelect>
                    <WorkSelect
                      aria-label="Permission decision"
                    value={overrideGranted ? "grant" : "revoke"}
                      onChange={(e) => {setOverrideGranted(e.target.value === "grant");setOverrideTouched(true);}}
                      className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200"
                    >
                      <option value="grant">Grant</option>
                      <option value="revoke">Explicitly deny</option>
                    </WorkSelect>
                    <WorkField label="Reason"><WorkInput
                      value={overrideReason}
                      onChange={(e) => {setOverrideReason(e.target.value);setOverrideTouched(true);}}
                      placeholder="Reason"
                      className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 flex-1 min-w-[8rem]"
                    /></WorkField>
                    <Btn tone="primary" onClick={handleGrantOverride}>Apply</Btn>
                  </div>
                )}
              </details>

              {/* API keys */}
              <details className="rounded border border-zinc-800 p-3 space-y-2">
                <summary className="text-xs font-brand uppercase tracking-wide text-zinc-500">API Keys</summary>
                <div className="space-y-1">
                  {detail.identity_and_access.api_keys.length === 0 && (
                    <div className="text-xs text-zinc-600">No API keys for this employee.</div>
                  )}
                  {detail.identity_and_access.api_keys.map((k) => (
                    <div key={String(k.id)} className="flex items-center justify-between text-xs px-2 py-1 rounded border border-zinc-800">
                      <span>
                        <span className="text-zinc-200">{String(k.label) || "(unlabeled)"}</span>
                        <span className="text-zinc-600 ml-2 font-mono">dos_…{String(k.last4)}</span>
                        {!k.active && <span className="ml-2 px-1.5 py-0.5 rounded bg-red-950/40 text-red-300 text-xs">revoked</span>}
                      </span>
                      {k.active === true && <Btn tone="danger" onClick={() => handleRevokeKey(String(k.id))}>Revoke</Btn>}
                    </div>
                  ))}
                </div>
                <div className="flex items-center gap-1.5">
                  <WorkField label="Label for a new key"><WorkInput
                    value={keyLabel}
                    onChange={(e) => setKeyLabel(e.target.value)}
                    placeholder="Label for a new key"
                    className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 flex-1"
                  /></WorkField>
                  <Btn tone="primary" onClick={handleGenerateKey}>Generate Key</Btn>
                </div>
                {newKey && (
                  <div className="text-xs rounded border border-amber-700 p-2 space-y-1">
                    <div className="text-amber-300">Copy this now -- it will not be shown again:</div>
                    <code className="block break-all text-zinc-200">{newKey.raw_key}</code>
                    <Btn onClick={()=>setNewKey(null)}>I have saved this key</Btn>
                  </div>
                )}
              </details>

              {/* Effective permissions */}
              <details className="rounded border border-zinc-800 p-3 space-y-1">
                <summary className="text-xs font-brand uppercase tracking-wide text-zinc-500">
                  Effective Permissions ({detail.identity_and_access.effective_permissions.filter((p) => p.effective).length} of {detail.identity_and_access.effective_permissions.length})
                </summary>
                <div className="grid grid-cols-2 gap-1 max-h-40 overflow-y-auto">
                  {detail.identity_and_access.effective_permissions.map((p) => (
                    <div key={p.key} className="flex items-center gap-1.5 text-xs">
                      <span className={p.effective ? "text-emerald-400" : "text-zinc-600"}>{p.effective ? "✓" : "✕"}</span>
                      <span className="text-zinc-400 truncate">{p.label}</span>
                      {p.overridden && <span className="text-blue-400 text-xs">(override)</span>}
                    </div>
                  ))}
                </div>
              </details>

              {/* Recent activity */}
              <details className="rounded border border-zinc-800 p-3 space-y-1">
                <summary className="text-xs font-brand uppercase tracking-wide text-zinc-500">
                  Recent Activity ({detail.recent_activity.total_events})
                </summary>
                <div className="space-y-1 max-h-40 overflow-y-auto">
                  {detail.recent_activity.events.length === 0 && <div className="text-xs text-zinc-600">No audit activity recorded for this actor yet.</div>}
                  {detail.recent_activity.events.map((e) => (
                    <div key={e.id} className="text-xs text-zinc-400 flex items-center justify-between">
                      <span>{e.event_type}{e.entity_id ? ` · ${e.entity_id}` : ""}</span>
                      <span className="text-zinc-600">{fmt(e.timestamp)}</span>
                    </div>
                  ))}
                </div>
              </details>
            </>
          )}
        </fieldset>
      </div>
    </div>
  );
}

export function AdminUsersBoard({ theme, onDraftOpenChange, onSavingChange }: { theme: Theme; onDraftOpenChange?: (open:boolean)=>void; onSavingChange?: (saving:boolean)=>void }) {
  const [data, setData] = useState<UsersOverview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [openEmployee, setOpenEmployee] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [pageSize,setPageSize]=useState(25);

  function refresh() {
    setLoading(true);
    setError(null);
    getUsersOverview()
      .then(setData)
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load the user directory."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const rows = (data?.user_administration.rows || []).filter((r) => {
    if (!search.trim()) return true;
    const q = search.trim().toLowerCase();
  return (
      r.employee_id.toLowerCase().includes(q) ||
      (r.name || "").toLowerCase().includes(q) ||
      (r.title || "").toLowerCase().includes(q) ||
      (r.department || "").toLowerCase().includes(q) ||
      (r.role || "").toLowerCase().includes(q)
    );
  });

    const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.min(page, pageCount - 1);
  if (openEmployee) return <UserDetailWorkspace key={openEmployee} theme={theme} employeeId={openEmployee} onClose={() => setOpenEmployee(null)} onChanged={refresh} onDraftOpenChange={onDraftOpenChange} onSavingChange={onSavingChange} />;

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-2 md:grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Active Employees" value={String(data?.active_employees.count ?? "—")} color={RIBBON[0]} />
        <Kpi theme={theme} label="Locked Accounts" value={String(data?.user_administration.locked_count ?? "—")} color={RIBBON[3]} />
        <Kpi theme={theme} label="With Active Overrides" value={String(data?.user_administration.with_active_overrides_count ?? "—")} color={RIBBON[1]} />
        <Kpi theme={theme} label="With API Keys" value={String(data?.user_administration.with_active_api_keys_count ?? "—")} color={RIBBON[2]} />
      </div>

      {error && <div role="alert" className="mx-4 mt-2 text-sm text-red-400"><p>{error}</p><WorkButton type="submit" disabled={loading} onClick={refresh} className="min-h-11 underline">Retry directory</WorkButton></div>}

      <div className="p-4 space-y-3">
        <div className="flex items-center gap-2">
          <WorkInput
            type="search"
            aria-label="Find an employee"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(0); }}
            placeholder="Search by name, employee id, title, department or role…"
            className="min-h-11 text-base px-3 py-2 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 flex-1"
          />
          <span className="text-xs text-zinc-500">{rows.length} of {data?.user_administration.count ?? 0}</span>
        </div>

        {loading ? (
          <div role="status" className="text-sm text-zinc-500">Loading employee directory…</div>
        ) : (
          <div className="space-y-1">
            {rows.slice(currentPage * pageSize, (currentPage + 1) * pageSize).map((r) => (
              <UserRow key={r.employee_id} row={r} onOpen={setOpenEmployee} />
            ))}
            {rows.length === 0 && <div role="status" className="text-sm">{error && !data ? "Directory unavailable. Retry above." : search.trim() ? "No employees match this search." : "No employees are available in this directory."}{search && <WorkButton type="submit" onClick={() => setSearch("")} className="ml-3 min-h-11 underline">Clear search</WorkButton>}</div>}
          </div>
        )}

        {!loading && rows.length > 0 && <CollectionPagination label="Employees" total={rows.length} page={currentPage} pageSize={pageSize} onPageChange={setPage} onPageSizeChange={setPageSize}/>}
        {data && data.permission_requests.count > 0 && (
          <div className="rounded border border-zinc-800 p-3 space-y-1">
            <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">
              Permission / Role Change Requests ({data.permission_requests.count})
            </div>
            <div className="flex items-center gap-2 text-xs text-zinc-400">
              {Object.entries(data.permission_requests.by_status).map(([status, count]) => (
                <span key={status} className="px-1.5 py-0.5 rounded bg-zinc-800">{status}: {count}</span>
              ))}
            </div>
            <div className="space-y-1 max-h-40 overflow-y-auto">
              {data.permission_requests.requests.map((r) => (
                <div key={r.id} className="text-xs text-zinc-400 flex items-center justify-between">
                  <span>{r.subject} <span className="text-zinc-600">({r.chain_key})</span></span>
                  <span className="text-zinc-600">{r.status} · {r.requested_by}</span>
                </div>
              ))}
            </div>
            <div className="text-xs text-zinc-600">Manage the full approval workflow on the Roles & Permissions item.</div>
          </div>
        )}

        {data?.employees_without_login && data.employees_without_login.count > 0 && (
          <div className="text-xs text-zinc-500">
            {data.employees_without_login.count} employee(s) have no login credential on file at all.
          </div>
        )}
      </div>

    </div>
  );
}
