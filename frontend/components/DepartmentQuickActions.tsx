"use client";

import { useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

// Native per-department quick-entry (session 47) -- Sam: "each section... needs to
// have their own buttons/callouts that are native to their department, and are
// functions that would be difficult to replicate in the chat feature / workspace
// breakout... a way for jobs that require input / field work to add quicker to the
// knowledge graph than using the chat input, but are still necessary for day to day
// for that particular job." Distinct from components/DepartmentDashboard.tsx's 4 OS-
// style *read* dashboards -- these are single-purpose *write* forms, one per chat
// department tab (Operations/Sales/Marketing/Inventory/Service/Finance), each posting
// straight to a new backend quick-entry endpoint (core/lead_intake.py,
// core/vehicle_intake.py, core/service_intake.py, core/field_notes.py).

type FieldType = "text" | "textarea" | "select" | "number";

type FieldDef = {
  key: string;
  label: string;
  type: FieldType;
  required?: boolean;
  options?: string[];
  placeholder?: string;
  default?: string;
};

type QuickAction = {
  key: string;
  label: string;
  color: string;
  endpoint: string;
  fields: FieldDef[];
  buildBody: (values: Record<string, string>) => Record<string, unknown>;
  successMessage: (values: Record<string, string>) => string;
};

const LEAD_CONTACT_FIELDS: FieldDef[] = [
  { key: "first_name", label: "First Name", type: "text", required: true },
  { key: "last_name", label: "Last Name", type: "text", required: true },
  { key: "phone", label: "Phone", type: "text" },
  { key: "email", label: "Email", type: "text" },
  { key: "vin", label: "Interested in VIN (optional)", type: "text" },
];

function buildLeadBody(values: Record<string, string>) {
  return {
    first_name: values.first_name,
    last_name: values.last_name,
    source: values.source,
    phone: values.phone || null,
    email: values.email || null,
    city: values.city || null,
    state: values.state || null,
    vin: values.vin || null,
  };
}

// Keyed by the exact department tab strings used in every chat-first page's
// `agents`/`selectedAgent` state -- Operations/Sales/Marketing/Inventory/Service/
// Finance. Colors reuse the corporate bar palette (#2B68AB/#3FBCC4/#FBCF09/#EE3C25)
// rather than inventing two new off-brand hues for Operations/Inventory -- Operations
// pairs with Finance (both back-office), Inventory pairs with Service (both
// vehicle-focused).
export const QUICK_ACTIONS: Record<string, QuickAction> = {
  Sales: {
    key: "walk_in_lead",
    label: "+ Log a Walk-In",
    color: "#2B68AB",
    endpoint: "/leads",
    fields: [
      { key: "source", label: "Source", type: "select", options: ["Walk-In", "Phone-Up", "Referral"], default: "Walk-In" },
      ...LEAD_CONTACT_FIELDS,
    ],
    buildBody: buildLeadBody,
    successMessage: (v) => `Logged ${v.first_name} ${v.last_name} as a new lead.`,
  },
  Marketing: {
    key: "event_lead",
    label: "+ Log Event Lead",
    color: "#FBCF09",
    endpoint: "/leads",
    fields: [
      { key: "source", label: "Source", type: "select", options: ["Event", "Website", "Referral"], default: "Event" },
      ...LEAD_CONTACT_FIELDS,
    ],
    buildBody: buildLeadBody,
    successMessage: (v) => `Logged ${v.first_name} ${v.last_name} as a new lead.`,
  },
  Service: {
    key: "service_ticket",
    label: "+ Log Service Ticket",
    color: "#3FBCC4",
    endpoint: "/service-records",
    fields: [
      { key: "vin", label: "VIN", type: "text", required: true },
      { key: "customer_id", label: "Customer ID (optional)", type: "text" },
      { key: "description", label: "Description", type: "textarea", required: true },
      { key: "pay_type", label: "Pay Type", type: "select", options: ["Customer Pay", "Warranty", "Internal"], default: "Customer Pay" },
      { key: "status", label: "Status", type: "select", options: ["In Progress", "Completed"], default: "In Progress" },
      { key: "mileage", label: "Mileage", type: "number" },
      { key: "labor_hours", label: "Labor Hours", type: "number" },
    ],
    buildBody: (v) => ({
      vin: v.vin,
      description: v.description,
      pay_type: v.pay_type,
      status: v.status,
      customer_id: v.customer_id || null,
      mileage: v.mileage || null,
      labor_hours: v.labor_hours || null,
    }),
    successMessage: () => "Service ticket logged.",
  },
  Inventory: {
    key: "vehicle_intake",
    label: "+ Add Vehicle Intake",
    color: "#3FBCC4",
    endpoint: "/vehicles",
    fields: [
      { key: "vin", label: "VIN", type: "text", required: true },
      { key: "year", label: "Year", type: "text", required: true },
      { key: "make", label: "Make", type: "text", required: true },
      { key: "model", label: "Model", type: "text", required: true },
      { key: "trim", label: "Trim", type: "text" },
      { key: "color", label: "Color", type: "text" },
      { key: "mileage", label: "Mileage", type: "number" },
      { key: "condition", label: "Condition", type: "select", options: ["New", "Used"], default: "Used" },
      { key: "price", label: "Price", type: "number" },
      { key: "cost", label: "Cost", type: "number" },
      { key: "stock_number", label: "Stock #", type: "text" },
      { key: "lot", label: "Lot", type: "select", options: ["Franchise New/Used", "BHPH Used Lot"], default: "Franchise New/Used" },
    ],
    buildBody: (v) => ({
      vin: v.vin,
      year: v.year,
      make: v.make,
      model: v.model,
      trim: v.trim || null,
      color: v.color || null,
      mileage: v.mileage || null,
      condition: v.condition,
      price: v.price || null,
      cost: v.cost || null,
      stock_number: v.stock_number || null,
      lot: v.lot,
    }),
    successMessage: (v) => `Added ${v.year} ${v.make} ${v.model} to inventory.`,
  },
  Operations: {
    key: "incident_note",
    label: "+ Log Incident",
    color: "#EE3C25",
    endpoint: "/notes",
    fields: [
      { key: "category", label: "Type", type: "select", options: ["incident", "maintenance", "general"], default: "incident" },
      { key: "body", label: "Note", type: "textarea", required: true },
      { key: "linked_entity_id", label: "Related VIN/ID (optional)", type: "text" },
    ],
    buildBody: (v) => ({
      department: "Operations",
      category: v.category,
      body: v.body,
      linked_entity_id: v.linked_entity_id || null,
    }),
    successMessage: () => "Note logged.",
  },
  Finance: {
    key: "payment_note",
    label: "+ Log Payment Note",
    color: "#EE3C25",
    endpoint: "/notes",
    fields: [
      { key: "body", label: "Note", type: "textarea", required: true, placeholder: "e.g. Collected $500 down payment on DEAL-00123" },
      { key: "linked_entity_id", label: "Related Deal/VIN (optional)", type: "text" },
    ],
    buildBody: (v) => ({
      department: "Finance",
      category: "payment",
      body: v.body,
      linked_entity_id: v.linked_entity_id || null,
    }),
    successMessage: () => "Payment note logged.",
  },
};

function QuickActionForm({ action, onDone }: { action: QuickAction; onDone: () => void }) {
  const initial: Record<string, string> = {};
  for (const f of action.fields) {
    if (f.default) initial[f.key] = f.default;
  }

  const [values, setValues] = useState<Record<string, string>>(initial);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  function setField(key: string, value: string) {
    setValues((v) => ({ ...v, [key]: value }));
  }

  async function handleSubmit() {
    const missing = action.fields.filter((f) => f.required && !values[f.key]?.trim());

    if (missing.length > 0) {
      setError(`Required: ${missing.map((f) => f.label).join(", ")}`);
      return;
    }

    setSubmitting(true);
    setError(null);

    try {
      const response = await fetch(`${API_BASE}${action.endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify(action.buildBody(values)),
      });

      const data = await response.json();

      if (!response.ok || data.error) {
        setError(data.error ?? "Something went wrong.");
        return;
      }

      setSuccess(action.successMessage(values));
      setValues(initial);
    } catch {
      setError("Unable to reach NXTDeal backend.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-6">
      <div
        className="w-full max-w-md bg-zinc-950 border rounded-xl overflow-hidden shadow-2xl"
        style={{ borderColor: action.color }}
      >
        <div
          className="flex items-center justify-between px-4 py-3 border-b border-zinc-800"
          style={{ backgroundColor: `${action.color}1a` }}
        >
          <div className="flex items-center gap-2">
            <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: action.color }} />
            <span className="font-medium">{action.label.replace("+ ", "")}</span>
          </div>
          <button onClick={onDone} className="text-zinc-400 hover:text-white transition text-lg leading-none">
            ×
          </button>
        </div>

        <div className="p-4 max-h-[70vh] overflow-y-auto">
          {success ? (
            <div className="text-sm text-center py-6">
              <div className="text-2xl mb-2">✓</div>
              <div className="text-zinc-200 mb-4">{success}</div>
              <div className="flex gap-2 justify-center">
                <button
                  onClick={() => setSuccess(null)}
                  className="text-xs px-3 py-1.5 rounded-lg border border-zinc-700 text-zinc-300 hover:text-white transition"
                >
                  Log another
                </button>
                <button
                  onClick={onDone}
                  className="text-xs px-3 py-1.5 rounded-lg text-black font-medium"
                  style={{ backgroundColor: action.color }}
                >
                  Done
                </button>
              </div>
            </div>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-3">
                {action.fields.map((f) => (
                  <div key={f.key} className={f.type === "textarea" ? "col-span-2" : "col-span-1"}>
                    <label className="block text-xs text-zinc-500 mb-1">
                      {f.label}
                      {f.required && <span style={{ color: action.color }}> *</span>}
                    </label>
                    {f.type === "select" ? (
                      <select aria-label={f.label}
                        value={values[f.key] ?? f.default ?? ""}
                        onChange={(e) => setField(f.key, e.target.value)}
                        className="w-full h-9 px-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                      >
                        {(f.options ?? []).map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : f.type === "textarea" ? (
                      <textarea
                        value={values[f.key] ?? ""}
                        onChange={(e) => setField(f.key, e.target.value)}
                        aria-label={f.label} placeholder={f.placeholder}
                        rows={3}
                        className="w-full px-2 py-1.5 text-sm rounded bg-zinc-900 border border-zinc-800"
                      />
                    ) : (
                      <input
                        type={f.type === "number" ? "number" : "text"}
                        value={values[f.key] ?? ""}
                        onChange={(e) => setField(f.key, e.target.value)}
                        aria-label={f.label} placeholder={f.placeholder}
                        className="w-full h-9 px-2 text-sm rounded bg-zinc-900 border border-zinc-800"
                      />
                    )}
                  </div>
                ))}
              </div>

              {error && <div className="mt-3 text-xs text-[#EE3C25]">{error}</div>}

              <button
                onClick={handleSubmit}
                disabled={submitting}
                className="w-full mt-4 py-2 rounded-lg text-black text-sm font-medium disabled:opacity-50"
                style={{ backgroundColor: action.color }}
              >
                {submitting ? "Saving…" : "Add to Graph"}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function DepartmentQuickActions({ department }: { department: string }) {
  const [open, setOpen] = useState(false);

  const action = QUICK_ACTIONS[department];

  if (!action) return null;

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        className="text-xs px-3 py-2 rounded-lg border border-zinc-800 bg-zinc-900 hover:border-current transition mb-3"
        style={{ color: action.color }}
      >
        {action.label}
      </button>

      {open && <QuickActionForm action={action} onDone={() => setOpen(false)} />}
    </>
  );
}
