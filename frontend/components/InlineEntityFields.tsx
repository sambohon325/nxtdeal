"use client";
import { WorkButton, WorkInput } from "./WorkspaceUi";

// Shared, lightweight inline-edit affordance for a curated subset of an entity's own
// attributes -- reuses the exact same generic, already-role-gated, already-audit-logged
// POST /entity/{id}/update endpoint components/MenuDashPanel.tsx's EntityEditCard
// established (core/entity_update_api.py), but scoped to a caller-curated field list
// instead of dumping every primitive attribute on the entity into a generic table. This
// lets a purpose-built view -- Customer360Panel's identity card, LeadRecordModal's
// Customer Profile grid, a vehicle detail view -- offer editing for just its own
// displayed fields, in its own layout, rather than pulling in a second, differently-shaped
// edit surface. Never invents a new mutation surface -- same backend route, same
// before/after diffing (only genuinely changed fields are ever sent in the patch), same
// server-side ACL (core/security.py's can_access_entity, the same gate GET /entity/{id}
// already uses, so editing never exceeds viewing access).
import { useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type InlineEditField = {
  key: string;
  label: string;
  value: unknown;
  type?: "text" | "number";
};

export function InlineEntityFields({
  theme,
  entityId,
  fields,
  onSaved,
}: {
  theme: "dark" | "light";
  entityId: string;
  fields: InlineEditField[];
  onSaved: (patch: Record<string, unknown>) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function tc(dark: string, light: string): string {
    return theme === "dark" ? dark : light;
  }

  function startEditing() {
    const seed: Record<string, string> = {};
    fields.forEach((f) => {
      seed[f.key] = f.value === null || f.value === undefined ? "" : String(f.value);
    });
    setDraft(seed);
    setError(null);
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    setError(null);

    const patch: Record<string, unknown> = {};
    fields.forEach((f) => {
      const next = draft[f.key];
      const original = f.value === null || f.value === undefined ? "" : String(f.value);
      if (next === original) return;
      patch[f.key] = f.type === "number" ? (next === "" ? null : Number(next)) : next;
    });

    if (Object.keys(patch).length === 0) {
      setEditing(false);
      setSaving(false);
      return;
    }

    try {
      const res = await fetch(`${API_BASE}/entity/${encodeURIComponent(entityId)}/update`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...authHeaders() },
        body: JSON.stringify({ patch }),
      });
      const data = await res.json();
      if (!res.ok || data.error) {
        setError(data.error || data.detail || "Unable to save changes. Please try again.");
      } else {
        onSaved(patch);
        setEditing(false);
      }
    } catch {
      setError("Unable to reach NXTDeal backend.");
    } finally {
      setSaving(false);
    }
  }

  if (!editing) {
    return (
      <WorkButton type="submit"
        onClick={startEditing}
        className={tc(
          "text-xs px-2 py-0.5 rounded border border-zinc-700 text-zinc-400 hover:text-white hover:border-zinc-500 transition",
          "text-xs px-2 py-0.5 rounded border border-zinc-300 text-zinc-600 hover:text-black hover:border-zinc-500 transition"
        )}
      >
        ✎ Edit
      </WorkButton>
    );
  }

  return (
    <div
      data-inline-record-editor=""
      className={tc(
        "rounded-lg border border-zinc-700 bg-zinc-900 p-3 space-y-2",
        "rounded-lg border border-zinc-300 bg-zinc-50 p-3 space-y-2"
      )}
    >
      {error && (
        <div role="alert" className="text-xs px-2 py-1 rounded bg-red-500/15 border border-red-500/40 text-red-300">
          {error}
        </div>
      )}
      <div className="grid grid-cols-2 gap-2">
        {fields.map((f) => (
          <label key={f.key} className="text-xs text-zinc-500 flex flex-col gap-0.5">
            {f.label}
            <WorkInput
              value={draft[f.key] ?? ""}
              disabled={saving}
              onChange={(e) => setDraft((d) => ({ ...d, [f.key]: e.target.value }))}
              type={f.type === "number" ? "number" : "text"}
              className={tc(
                "rounded-md border border-zinc-700 bg-zinc-950 text-white px-2 py-1 text-xs",
                "rounded-md border border-zinc-300 bg-white text-black px-2 py-1 text-xs"
              )}
            />
          </label>
        ))}
      </div>
      <div className="flex items-center gap-2">
        <WorkButton type="submit" variant="primary"
          disabled={saving}
          onClick={save}
          className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white hover:opacity-90 transition disabled:opacity-50"
        >
          {saving ? "Saving…" : "Save"}
        </WorkButton>
        <WorkButton type="submit"
          disabled={saving}
          onClick={() => setEditing(false)}
          className={tc(
            "text-xs px-2.5 py-1 rounded text-zinc-500 hover:text-white transition",
            "text-xs px-2.5 py-1 rounded text-zinc-500 hover:text-black transition"
          )}
        >
          Cancel
        </WorkButton>
      </div>
    </div>
  );
}
