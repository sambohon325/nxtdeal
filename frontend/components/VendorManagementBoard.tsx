"use client";
import {RecordTable} from "./RecordTable";
import { WorkButton, WorkInput, WorkSelect , WorkStat, WorkOverlay} from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Administration's "Vendors" item (Administration Control Center rebuild,
// continued) -- real Vendor entities (core/vendor_management.py): contact
// info, contract term (start/end date, auto-renew), monthly cost, category.
// ADMIN/OPERATIONS-only throughout, same convention as this whole department.
import { PRODUCT_ACCENT_COLORS } from "@/lib/productTheme";
import { useEffect, useState } from "react";
import {
  getVendorDashboard,
  listVendors,
  createVendor,
  updateVendor,
  setVendorStatus,
  type Vendor,
  type VendorDashboard,
  type VendorCategory,
  type VendorStatus,
} from "@/lib/vendorManagement";

type Theme = "dark" | "light";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const RIBBON = PRODUCT_ACCENT_COLORS;

const CATEGORIES: VendorCategory[] = ["software", "parts_supplier", "service_provider", "marketing", "other"];
const STATUSES: VendorStatus[] = ["active", "inactive", "under_review"];

const STATUS_TONE: Record<string, string> = {
  active: "bg-emerald-950/40 text-emerald-300",
  inactive: "bg-zinc-800 text-zinc-400",
  under_review: "bg-amber-950/40 text-amber-300",
};

function money(n: number | null | undefined): string {
  if (n === null || n === undefined) return "—";
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

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

function Input({ value, onChange, placeholder, type }: { value: string; onChange: (v: string) => void; placeholder?: string; type?: string }) {
  return (
    <WorkField label={placeholder || "Value"}><WorkInput
      type={type || "text"}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200 placeholder:text-zinc-600 w-full"
    /></WorkField>
  );
}

function emptyForm() {
  return {
    name: "",
    category: "software" as VendorCategory,
    contact_name: "",
    contact_email: "",
    contact_phone: "",
    monthly_cost: "",
    contract_start_date: "",
    contract_end_date: "",
    auto_renew: false,
    notes: "",
  };
}

export function VendorManagementBoard({ theme }: { theme: Theme }) {
  const [dashboard, setDashboard] = useState<VendorDashboard | null>(null);
  const [vendors, setVendors] = useState<Vendor[]>([]);
  const [categoryFilter, setCategoryFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [selected, setSelected] = useState<Vendor | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(emptyForm());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    Promise.all([getVendorDashboard(), listVendors({ category: categoryFilter || undefined, status: statusFilter || undefined })])
      .then(([d, v]) => {
        setDashboard(d);
        setVendors(v.vendors);
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load Vendor data."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, [categoryFilter, statusFilter]);

  async function handleCreate() {
    if (!form.name.trim()) return;
    try {
      await createVendor({
        name: form.name.trim(),
        category: form.category,
        contact_name: form.contact_name,
        contact_email: form.contact_email,
        contact_phone: form.contact_phone,
        monthly_cost: form.monthly_cost ? Number(form.monthly_cost) : undefined,
        contract_start_date: form.contract_start_date || undefined,
        contract_end_date: form.contract_end_date || undefined,
        auto_renew: form.auto_renew,
        notes: form.notes,
      });
      setMessage(`Vendor '${form.name.trim()}' created.`);
      setForm(emptyForm());
      setShowForm(false);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to create vendor.");
    }
  }

  async function handleStatus(vendorId: string, status: VendorStatus) {
    try {
      const updated = await setVendorStatus(vendorId, status);
      refresh();
      if (selected?.id === vendorId) setSelected(updated as Vendor);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update vendor status.");
    }
  }

  async function handleSaveDetail(fields: Partial<Vendor>) {
    if (!selected) return;
    try {
      const updated = await updateVendor(selected.id, fields);
      setSelected(updated as Vendor);
      setMessage("Vendor updated.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to update vendor.");
    }
  }

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white overflow-y-auto", "flex-1 flex flex-col min-h-0 bg-white text-black overflow-y-auto")}>
      <div className={tc(theme, "grid grid-cols-4 gap-3 p-4 border-b border-zinc-800", "grid grid-cols-4 gap-3 p-4 border-b border-zinc-200")}>
        <Kpi theme={theme} label="Total Vendors" value={String(dashboard?.total_vendors ?? 0)} color={RIBBON[0]} />
        <Kpi theme={theme} label="Active" value={String(dashboard?.active_vendors ?? 0)} color={RIBBON[1]} />
        <Kpi theme={theme} label="Monthly Spend" value={money(dashboard?.total_monthly_cost)} color={RIBBON[2]} />
        <Kpi theme={theme} label="Renewals (60d)" value={String(dashboard?.upcoming_renewals.length ?? 0)} color={RIBBON[3]} />
      </div>

      {error && <div className="mx-4 mt-2 text-xs text-red-400">{error}</div>}
      {message && <div className="mx-4 mt-2 text-xs text-emerald-400">{message}</div>}

      <div className="flex items-center gap-2 px-4 py-2 border-b border-zinc-800 flex-wrap">
        <WorkField label="Category Filter"><WorkSelect value={categoryFilter} onChange={(e) => setCategoryFilter(e.target.value)} className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200">
          <option value="">All categories</option>
          {CATEGORIES.map((c) => (
            <option key={c} value={c}>{c.replace("_", " ")}</option>
          ))}
        </WorkSelect></WorkField>
        <WorkField label="Status"><WorkSelect value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200">
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>{s.replace("_", " ")}</option>
          ))}
        </WorkSelect></WorkField>
        <div className="flex-1" />
        <Btn tone="primary" onClick={() => setShowForm((v) => !v)}>{showForm ? "Cancel" : "+ New Vendor"}</Btn>
      </div>

      {showForm && (
        <div className="mx-4 mt-3 rounded border border-zinc-800 p-3 space-y-2">
          <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">New Vendor</div>
          <div className="grid grid-cols-3 gap-2">
            <Input value={form.name} onChange={(v) => setForm({ ...form, name: v })} placeholder="Vendor name" />
            <WorkField label="Category"><WorkSelect value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value as VendorCategory })} className="text-xs px-2 py-1 rounded bg-zinc-900 border border-zinc-700 text-zinc-200">
              {CATEGORIES.map((c) => (
                <option key={c} value={c}>{c.replace("_", " ")}</option>
              ))}
            </WorkSelect></WorkField>
            <Input value={form.monthly_cost} onChange={(v) => setForm({ ...form, monthly_cost: v })} placeholder="Monthly cost" type="number" />
            <Input value={form.contact_name} onChange={(v) => setForm({ ...form, contact_name: v })} placeholder="Contact name" />
            <Input value={form.contact_email} onChange={(v) => setForm({ ...form, contact_email: v })} placeholder="Contact email" />
            <Input value={form.contact_phone} onChange={(v) => setForm({ ...form, contact_phone: v })} placeholder="Contact phone" />
            <Input value={form.contract_start_date} onChange={(v) => setForm({ ...form, contract_start_date: v })} placeholder="Contract start (YYYY-MM-DD)" />
            <Input value={form.contract_end_date} onChange={(v) => setForm({ ...form, contract_end_date: v })} placeholder="Contract end (YYYY-MM-DD)" />
            <label className="flex items-center gap-1.5 text-xs text-zinc-400">
              <WorkInput type="checkbox" checked={form.auto_renew} onChange={(e) => setForm({ ...form, auto_renew: e.target.checked })} />
              Auto-renew
            </label>
          </div>
          <Input value={form.notes} onChange={(v) => setForm({ ...form, notes: v })} placeholder="Notes (optional)" />
          <Btn tone="primary" onClick={handleCreate} disabled={!form.name.trim()}>Create Vendor</Btn>
        </div>
      )}

      <div className="flex-1 p-4">
        {loading ? (
          <div className="text-sm text-zinc-500">Loading…</div>
        ) : (
          <RecordTable label="Vendors" key={`${categoryFilter}:${statusFilter}`}><thead><tr><th>Vendor</th><th>Category</th><th>Monthly cost</th><th>Renewal</th><th>Status</th><th>Next step</th></tr></thead><tbody>{vendors.map(v=><tr key={v.id}><td><strong>{v.name}</strong></td><td>{v.category.replace("_"," ")}</td><td>{money(v.monthly_cost)}</td><td>{v.days_to_renewal!=null&&v.days_to_renewal>=0?`${v.days_to_renewal} days`:v.contract_end_date||"Not set"}</td><td>{v.status.replace("_"," ")}</td><td><WorkButton onClick={()=>setSelected(v)}>Open vendor</WorkButton></td></tr>)}</tbody></RecordTable>

        )}

        {!loading&&!vendors.length&&<p>No vendors match these filters.</p>}
        {dashboard?.not_yet_tracked&&Object.keys(dashboard.not_yet_tracked).length>0&&<p className="mt-4 text-sm">Vendor usage measurements are not available yet. Spend and renewals use the contract details recorded here.</p>}

      </div>

      {selected && (
        <WorkOverlay className="fixed inset-0 z-50 flex items-center justify-center bg-black/60" onClick={() => setSelected(null)}>
          <div className="bg-brand-charcoal border border-black/30 rounded-xl p-5 w-[28rem] text-white space-y-3" onClick={(e) => e.stopPropagation()}>
            <div className="flex items-center justify-between">
              <div className="text-sm font-brand font-medium">{selected.name}</div>
              <span className={`px-1.5 py-0.5 rounded text-xs ${STATUS_TONE[selected.status]}`}>{selected.status.replace("_", " ")}</span>
            </div>
            <div className="text-xs text-zinc-400 space-y-1">
              <div>Category: {selected.category.replace("_", " ")}</div>
              <div>Contact: {selected.contact_name || "—"} · {selected.contact_email || "—"} · {selected.contact_phone || "—"}</div>
              <div>Monthly cost: {money(selected.monthly_cost)}</div>
              <div>Contract: {selected.contract_start_date || "—"} → {selected.contract_end_date || "—"} {selected.auto_renew ? "(auto-renew)" : ""}</div>
              {selected.notes && <div>Notes: {selected.notes}</div>}
            </div>
            <div className="flex gap-1.5 flex-wrap">
              {STATUSES.filter((s) => s !== selected.status).map((s) => (
                <Btn key={s} onClick={() => handleStatus(selected.id, s)}>Mark {s.replace("_", " ")}</Btn>
              ))}
            </div>
            <div className="grid grid-cols-2 gap-2 pt-2 border-t border-zinc-800">
              <Input value={selected.monthly_cost != null ? String(selected.monthly_cost) : ""} onChange={(v) => setSelected({ ...selected, monthly_cost: v ? Number(v) : null })} placeholder="Monthly cost" type="number" />
              <Input value={selected.contract_end_date || ""} onChange={(v) => setSelected({ ...selected, contract_end_date: v })} placeholder="Contract end (YYYY-MM-DD)" />
            </div>
            <div className="flex gap-1.5">
              <Btn tone="primary" onClick={() => handleSaveDetail({ monthly_cost: selected.monthly_cost, contract_end_date: selected.contract_end_date })}>Save Changes</Btn>
              <Btn onClick={() => setSelected(null)}>Close</Btn>
            </div>
          </div>
        </WorkOverlay>
      )}
    </div>
  );
}
