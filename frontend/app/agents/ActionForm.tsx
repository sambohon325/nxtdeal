"use client";
import { useState } from "react";

export type InputSchema = { properties?: Record<string, { title?: string; type?: string; enum?: string[]; default?: unknown; maxLength?: number; anyOf?: { type: string }[] }>; required?: string[] };

export default function ActionForm({ schema, busy, submit }: { schema: InputSchema; busy: boolean; submit: (data: Record<string, unknown>) => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  return <form onSubmit={event => {
    event.preventDefault();
    const data: Record<string, unknown> = {};
    for (const [name, property] of Object.entries(schema.properties || {})) {
      const value = values[name] ?? (property.default == null ? "" : String(property.default));
      if (value !== "" || schema.required?.includes(name)) data[name] = value;
    }
    submit(data);
  }}>
    <div style={{ display: "grid", gap: 12, margin: "16px 0" }}>{Object.entries(schema.properties || {}).map(([name, field]) => <label key={name} style={{ display: "grid", gap: 6, fontSize: 13 }}>
      {field.title || name}{schema.required?.includes(name) ? " *" : ""}
      {field.enum ? <select required={schema.required?.includes(name)} value={values[name] ?? String(field.default ?? "")} onChange={e => setValues({ ...values, [name]: e.target.value })}><option value="">Select…</option>{field.enum.map(value => <option key={value}>{value}</option>)}</select> :
        <input required={schema.required?.includes(name)} maxLength={field.maxLength} value={values[name] ?? String(field.default ?? "")} onChange={e => setValues({ ...values, [name]: e.target.value })} placeholder={name.includes("scheduled") || name === "due_at" ? "2026-10-05T10:00:00-05:00" : undefined} style={{ padding: 10, border: "1px solid #bcc7da", borderRadius: 7 }} />}
    </label>)}</div><button disabled={busy} type="submit">Prepare action for review</button>
  </form>;
}
