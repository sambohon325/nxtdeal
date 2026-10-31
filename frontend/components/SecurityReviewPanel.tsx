"use client";
import { WorkButton } from "./WorkspaceUi";
import { useEffect, useState } from "react";
import { API_BASE } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

type SecurityReview = {
  production_verified: false;
  observed_at: string;
  runtime_mode: string;
  mfa: { credential_records: number; enrolled: number; not_enrolled: number; admin_operations_not_enrolled: number; note: string };
  verification_required: { control: string; evidence: string }[];
};
const labels: Record<string, string> = {
  deployed_revision: "Deployed release", tenant_isolation: "Dealer separation", transport_encryption: "Connection encryption",
  storage_encryption: "Stored data encryption", backup_restore: "Backup and restore", incident_response: "Incident response",
  retention: "Retention and deletion", vendor_access: "Vendor access",
};

export function SecurityReviewPanel() {
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<{ revision: number; report?: SecurityReview; error?: string } | null>(null);
  const current = result?.revision === revision ? result : null;
  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      try {
        const response = await fetch(`${API_BASE}/compliance/security-review`, { headers: authHeaders(), cache: "no-store", signal: controller.signal });
        const report = await response.json();
        if (!response.ok || report?.error) throw new Error(report?.error || "Unable to load security review.");
        if (report?.production_verified !== false || !report?.mfa || !Array.isArray(report?.verification_required)) throw new Error("Security review is unavailable on this server.");
        if (!controller.signal.aborted) setResult({ revision, report });
      } catch (error) {
        if (!controller.signal.aborted) setResult({ revision, error: error instanceof TypeError
          ? "Unable to connect to security review. Check your connection and try again."
          : error instanceof Error ? error.message : "Unable to load security review." });
      }
    }
    void load();
    return () => controller.abort();
  }, [revision]);
  const report = current?.report;
  return <section className="space-y-4" aria-labelledby="security-review-title">
    <div className="flex justify-between gap-3"><h2 id="security-review-title" className="font-semibold">Security evidence review</h2>
      <WorkButton type="submit" className="border rounded px-3 py-1 text-sm disabled:opacity-50" disabled={!current} onClick={() => setRevision(value => value + 1)}>Refresh</WorkButton></div>
    <p className="text-sm">Production security is not yet verified. These observations help identify evidence still needed; they are not a compliance certification.</p>
    {!current && <p role="status">Loading security review…</p>}
    {current?.error && <p role="alert">{current.error} <WorkButton type="submit" className="underline" onClick={() => setRevision(value => value + 1)}>Try again</WorkButton></p>}
    {report && <>
      <p className="text-xs opacity-75">Observed {new Date(report.observed_at).toLocaleString()} · {report.runtime_mode === "sample_data_only" ? "Demo runtime" : "Production mode; deployment verification pending"}</p>
      <h3 className="font-medium">Staff MFA enrollment</h3>
      <dl className="grid gap-3 sm:grid-cols-3 text-sm">
        <div className="border rounded p-3"><dt>Credential records</dt><dd className="text-xl">{report.mfa.credential_records}</dd></div>
        <div className="border rounded p-3"><dt>Not enrolled in MFA</dt><dd className="text-xl">{report.mfa.not_enrolled}</dd></div>
        <div className="border rounded p-3"><dt>Admin / Operations not enrolled</dt><dd className="text-xl">{report.mfa.admin_operations_not_enrolled}</dd></div>
      </dl>
      <p className="text-sm opacity-75">{report.mfa.note}</p>
      <h3 className="font-medium">Evidence requiring verification</h3>
      <ul className="space-y-2">{report.verification_required.map(item => <li key={item.control} className="border rounded p-3 text-sm">
        <div className="font-medium">{labels[item.control] || "Additional control"} <span className="font-normal opacity-75">· Unverified</span></div>
        <p>{item.evidence}</p>
      </li>)}</ul>
    </>}
  </section>;
}
