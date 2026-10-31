"use client";
import { WorkButton, WorkInput, WorkSelect } from "./WorkspaceUi";

// Bumper-parity user management (2026-07-25): create a user (Employee + login + role) in
// one action, see the roster, and reassign roles — including the new BDC role. Backed by
// lib/userManagement.ts (backend/core/user_management_api.py). ADMIN-only surface.
import { useEffect, useRef, useState } from "react";
import {
  listRoles,
  listUsers,
  createUser,
  updateUserRole,
  type RoleInfo,
  type UserRow,
  type CreatedUser,
} from "@/lib/userManagement";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

export function UserManagementBoard({ theme, onDraftOpenChange, onSavingChange }: { theme: Theme; onDraftOpenChange?: (open:boolean)=>void; onSavingChange?: (saving:boolean)=>void }) {
  const [roles, setRoles] = useState<RoleInfo[]>([]);
  const [users, setUsers] = useState<UserRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<CreatedUser | null>(null);
  const [showForm, setShowForm] = useState(false);

  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState("SALES");
  const [department, setDepartment] = useState("");
  const [title, setTitle] = useState("");
  const [busy, setBusy] = useState(false);

  const [roleDraft,setRoleDraft] = useState<{employeeId:string;name:string;from:string;to:string}|null>(null);
  const [roleSaving,setRoleSaving] = useState(false);
  const [roleError,setRoleError] = useState("");
  const [roleSuccess,setRoleSuccess] = useState("");
  const savingRole = useRef(false);
  const creatingUser = useRef(false);
  useEffect(() => { onSavingChange?.(busy || roleSaving); return () => onSavingChange?.(false); }, [busy, roleSaving, onSavingChange]);
  const hasNewUserDraft = !!(firstName || lastName || email || department || title || role !== "SALES");
  const hasUnfinishedWork = !!roleDraft || hasNewUserDraft || !!created || busy;
  useEffect(() => {
    onDraftOpenChange?.(hasUnfinishedWork);
    return () => onDraftOpenChange?.(false);
  }, [hasUnfinishedWork, onDraftOpenChange]);

  const card = tc(theme, "rounded-md border border-zinc-800 bg-zinc-900/60 p-3", "rounded-md border border-zinc-200 bg-white p-3");
  const input = tc(theme, "w-full rounded-md bg-zinc-950 border border-zinc-800 px-2 py-1.5 text-[12px]", "w-full rounded-md bg-white border border-zinc-300 px-2 py-1.5 text-[12px]");

  function refresh() {
    setLoading(true);
    Promise.all([listRoles(), listUsers()])
      .then(([r, u]) => {
        setRoles(r.roles);
        setUsers(u.users);
        setError(null);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Couldn't load users."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function submit() {
    if (creatingUser.current || created || !firstName.trim() || !lastName.trim()) return;
    creatingUser.current = true;
    setBusy(true);
    setError(null);
    try {
      const u = await createUser({ first_name: firstName.trim(), last_name: lastName.trim(), email: email.trim() || null, role, department: department.trim() || null, title: title.trim() || null });
      setCreated(u);
      setFirstName(""); setLastName(""); setEmail(""); setDepartment(""); setTitle(""); setRole("SALES");
      setShowForm(false);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Couldn't create user.");
    } finally {
      creatingUser.current = false;
      setBusy(false);
    }
  }

  async function saveRole() {
    if(!roleDraft || savingRole.current)return;
    savingRole.current=true;setRoleSaving(true);setRoleError("");
    const draft=roleDraft;
    try {
      await updateUserRole(draft.employeeId,draft.to);
      setUsers(current=>current.map(user=>user.employee_id===draft.employeeId?{...user,role:draft.to}:user));
      setRoleSuccess(`${draft.name}: role saved as ${draft.to}.`);
      setRoleDraft(null);
    } catch(e) {
      setRoleError(e instanceof Error?e.message:"Couldn't save this role. Your selection is retained.");
    } finally {savingRole.current=false;setRoleSaving(false);}
  }

  if (loading && users.length === 0 && !created && !showForm) {
    return <div className="p-4 text-sm text-zinc-500">Loading users…</div>;
  }

  return (
    <div className="flex-1 min-h-0 flex flex-col overflow-y-auto">
      <div className="px-3 pt-3 shrink-0 flex items-center justify-between">
        <div>
          <div className="text-base font-brand">User Management</div>
          <div className="text-xs text-zinc-500">Add staff, assign roles (including the BDC team), and manage logins.</div>
        </div>
        <WorkButton type="submit" disabled={busy || !!created} onClick={() => setShowForm((s) => !s)} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold">
          {showForm ? "Hide setup" : hasNewUserDraft ? "Resume staff setup" : "+ Add user"}
        </WorkButton>
      </div>

      {error && <div role="alert" className="mx-3 mt-2 rounded-md bg-red-500/10 border border-red-500/30 px-3 py-2 text-xs text-red-400">{error}</div>}

      {roleSuccess&&<p role="status" className="mx-3 mt-2 text-sm">{roleSuccess}</p>}
      {roleDraft&&<section aria-label="Review employee role change" className={card+" mx-3 mt-3 space-y-2"}>
        <h3 className="text-base">Review role change for {roleDraft.name}</h3>
        <p className="text-sm">{roleDraft.employeeId} · {roleDraft.from} → {roleDraft.to}</p>
        <p className="text-sm">{roles.find(r=>r.role===roleDraft.to)?.description}</p>
        <p className="text-sm">This changes the employee’s role-based access. Review the selection before saving.</p>
        {roleError&&<p role="alert">{roleError}</p>}
        <WorkButton type="submit" className="min-h-11 px-3 rounded border" disabled={roleSaving} onClick={saveRole}>{roleSaving?"Saving role…":"Save role change"}</WorkButton>
        <WorkButton type="submit" className="min-h-11 px-3 rounded border ml-2" disabled={roleSaving} onClick={()=>{setRoleDraft(null);setRoleError("");}}>Cancel role change</WorkButton>
        {roleSaving&&<p role="status">Wait for the result before leaving this screen.</p>}
      </section>}

      {created && (
        <section aria-label="New employee login handoff" className={card + " mx-3 mt-3 space-y-2"}>
          <h3 className="text-base">Login ready for {created.name}</h3>
          <p>Employee ID: {created.employee_id} · Role: {created.role}</p>
          <p>Temporary password: <span className="font-mono font-bold">{created.temp_password}</span></p>
          <p>Share these login details securely with the employee. They must change the password at first login.</p>
          <p>Keep this screen open until you have recorded the handoff. Acknowledging clears the temporary password from this view.</p>
          <WorkButton type="submit" className="min-h-11 px-3 rounded border" onClick={() => setCreated(null)}>I have recorded the login handoff</WorkButton>
        </section>
      )}
      {!showForm && hasNewUserDraft && <p role="status" className="mx-3 mt-2 text-sm">Unfinished staff setup is retained. Resume setup to continue.</p>}

      <div className="p-3 space-y-3">
        {showForm && (
          <fieldset disabled={busy} aria-label="New employee setup" className={card + " grid grid-cols-2 gap-2"}>
            <legend>Set up an employee login</legend>
            <WorkInput className={input} aria-label="First name" placeholder="First name" value={firstName} onChange={(e) => setFirstName(e.target.value)} />
            <WorkInput className={input} aria-label="Last name" placeholder="Last name" value={lastName} onChange={(e) => setLastName(e.target.value)} />
            <WorkInput className={input} aria-label="Email (optional, enables email login)" placeholder="Email (optional, enables email login)" value={email} onChange={(e) => setEmail(e.target.value)} />
            <WorkSelect aria-label="New employee role" className={input} value={role} onChange={(e) => setRole(e.target.value)}>
              {roles.map((r) => (
                <option key={r.role} value={r.role}>{r.role}</option>
              ))}
            </WorkSelect>
            <WorkInput className={input} aria-label="Department (e.g. Sales)" placeholder="Department (e.g. Sales)" value={department} onChange={(e) => setDepartment(e.target.value)} />
            <WorkInput className={input} aria-label="Title (e.g. BDC Rep)" placeholder="Title (e.g. BDC Rep)" value={title} onChange={(e) => setTitle(e.target.value)} />
            <div className="col-span-2 flex items-center gap-2">
              <WorkButton type="submit" onClick={submit} disabled={busy || !firstName.trim() || !lastName.trim()} className="text-xs px-3 py-1.5 rounded-md bg-brand-teal text-black font-semibold disabled:opacity-50">
                {busy ? "Creating…" : "Create user"}
              </WorkButton>
              <span className="text-xs text-zinc-500">{roles.find((r) => r.role === role)?.description}</span>
            </div>
            {busy && <p role="status" className="col-span-2">Creating the login. Wait for the result before leaving this screen.</p>}
          </fieldset>
        )}

        <div className={card}>
          <div className="text-xs font-semibold mb-2">Roster ({users.length})</div>
          <div className="space-y-1">
            {users.map((u) => (
              <div key={u.employee_id || Math.random()} className="flex items-center gap-2 text-xs py-1 border-b border-zinc-800/50">
                <div className="w-40 truncate">{u.name || u.employee_id}</div>
                <div className="w-48 truncate text-zinc-500">{u.email || "—"}</div>
                <div className="w-24 truncate text-zinc-500">{u.department || "—"}</div>
                {u.has_login && u.employee_id ? (
                  <WorkSelect
                    aria-label={`Role for ${u.name || u.employee_id}`}
                    disabled={roleSaving || !!roleDraft && roleDraft.employeeId!==u.employee_id}
                    value={roleDraft?.employeeId===u.employee_id?roleDraft.to:u.role || ""}
                    onChange={(e) => {setRoleError("");setRoleSuccess("");setRoleDraft(e.target.value===u.role?null:{employeeId:u.employee_id as string,name:u.name||u.employee_id as string,from:u.role||"Unassigned",to:e.target.value});}}
                    className={tc(theme, "rounded bg-zinc-950 border border-zinc-800 px-1.5 py-0.5 text-xs ml-auto", "rounded bg-white border border-zinc-300 px-1.5 py-0.5 text-xs ml-auto")}
                  >
                    {roles.map((r) => (
                      <option key={r.role} value={r.role}>{r.role}</option>
                    ))}
                  </WorkSelect>
                ) : (
                  <div className="ml-auto text-xs text-zinc-600">no login</div>
                )}
              </div>
            ))}
            {users.length === 0 && <div className="text-xs text-zinc-500">No users yet.</div>}
          </div>
        </div>
      </div>
    </div>
  );
}

export default UserManagementBoard;
