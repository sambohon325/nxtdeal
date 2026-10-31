"use client";
import { WorkButton, WorkSelect, WorkInput } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Operations' "Documents" item (session 106 follow-up #6) -- Deal Jacket
// Workflow, Title Processing workflow, Compliance Packets, Digital
// Approvals. Backend: core/document_workflows.py / _api.py.

import { useEffect, useState } from "react";
import {
  getDealJacketStatus,
  getTitleStatus,
  getDocumentPacket,
  requestDocument,
  getPendingApprovals,
  approveDocument,
  rejectDocument,
  type DocEntityType,
  type CompletenessCheck,
  type PendingApprovals,
} from "@/lib/documentWorkflows";
import { EntityHoverLink } from "@/components/EntityHoverLink";

type Theme = "dark" | "light";
type Tab = "lookup" | "approvals";

function tc(theme: Theme, dark: string, light: string): string {
  return theme === "dark" ? dark : light;
}

const ENTITY_TYPES: DocEntityType[] = ["Deal", "Vehicle", "Customer"];

function CompletenessCard({ theme, data, onRequestDocument }: { theme: Theme; data: CompletenessCheck; onRequestDocument: (docType: string) => void }) {
  const cardClass = tc(theme, "rounded-lg border border-black/20 bg-brand-charcoal p-3", "rounded-lg border border-zinc-200 bg-zinc-50 p-3");
  return (
    <div className={cardClass}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-brand uppercase tracking-wide text-zinc-500">
          {data.entity_type} <EntityHoverLink id={data.entity_id} />
        </div>
        <span className={`text-xs px-2 py-0.5 rounded ${data.is_complete ? "bg-green-950/40 text-green-300" : "bg-amber-950/40 text-amber-300"}`}>
          {data.is_complete ? "Complete" : "Missing docs"}
        </span>
      </div>
      <div className="space-y-1 mb-2">
        {data.documents.length === 0 ? (
          <div className="text-xs text-zinc-600">No documents on file.</div>
        ) : (
          data.documents.map((d) => (
            <div key={d.id} className="text-xs flex items-center justify-between">
              <span>{d.document_type} — {d.file_name}</span>
              <span className={`text-xs px-1.5 py-0.5 rounded ${d.approval_status === "approved" ? "bg-green-950/40 text-green-300" : d.approval_status === "rejected" ? "bg-red-950/40 text-red-300" : "bg-zinc-800 text-zinc-400"}`}>{d.approval_status}</span>
            </div>
          ))
        )}
      </div>
      {data.missing_types.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {data.missing_types.map((t) => (
            <WorkButton type="submit" variant="primary" key={t} onClick={() => onRequestDocument(t)} className="text-xs px-2.5 py-1 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition">
              Request {t}
            </WorkButton>
          ))}
        </div>
      )}
    </div>
  );
}

function LookupTab({ theme }: { theme: Theme }) {
  const [entityType, setEntityType] = useState<DocEntityType>("Deal");
  const [entityId, setEntityId] = useState("");
  const [data, setData] = useState<CompletenessCheck | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);

  const inputClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function lookup() {
    if (!entityId.trim()) return;
    setLoading(true);
    setError(null);
    setError(null);
    setMessage(null);
    try {
      const fn = entityType === "Deal" ? getDealJacketStatus : entityType === "Vehicle" ? getTitleStatus : (id: string) => getDocumentPacket("Customer", id);
      const result = await fn(entityId.trim());
      setData(result);
    } catch (e) {
      setError((e as Error).message);
      setData(null);
    } finally {
      setLoading(false);
    }
  }

  async function handleRequest(docType: string) {
    if (!data) return;
    try {
      await requestDocument(data.entity_type, data.entity_id, docType, "");
      setMessage(`${docType} requested — a real task was created for the Title Clerk / Accounting queue.`);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-3">
      <div className="text-xs text-zinc-600 italic">
        Deal Jacket Workflow, Title Processing, and Compliance Packets are all the same lookup -- pick the entity type and paste a real ID (e.g. DEAL-00004, VEH-00003, CUST-00001).
      </div>
      <div className="flex items-center gap-1.5">
        <WorkField label="Record type"><WorkSelect value={entityType} onChange={(e) => setEntityType(e.target.value as DocEntityType)} className={`rounded-md border px-2 py-1.5 text-xs ${inputClass}`}>
          {ENTITY_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
        </WorkSelect></WorkField>
        <WorkField label="Entity ID"><WorkInput value={entityId} onChange={(e) => setEntityId(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") lookup(); }} placeholder={`${entityType} ID…`} className={`flex-1 rounded-md border px-2 py-1.5 text-xs ${inputClass}`} /></WorkField>
        <WorkButton type="submit" variant="primary" disabled={loading} onClick={lookup} className="text-xs px-2.5 py-1.5 rounded bg-brand-blue text-white font-medium hover:opacity-90 transition disabled:opacity-50">Look Up</WorkButton>
      </div>
      {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
      {message && <div className="text-xs px-3 py-2 rounded-lg bg-green-500/15 border border-green-500/40 text-green-300">{message}</div>}
      {data && <CompletenessCard theme={theme} data={data} onRequestDocument={handleRequest} />}
    </div>
  );
}

function ApprovalsTab({ theme }: { theme: Theme }) {
  const [data, setData] = useState<PendingApprovals | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);

  function refresh() {
    setLoading(true);
    setError(null);
    getPendingApprovals().then(setData).catch((e) => setError((e as Error).message)).finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  const inputClass = tc(theme, "bg-zinc-900 border-zinc-700 text-white placeholder:text-zinc-600", "bg-white border-zinc-300 text-black placeholder:text-zinc-400");

  async function handleApprove(id: string) {
    setBusyId(id);
    setError(null);
    try {
      await approveDocument(id);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  async function handleReject(id: string) {
    const reason = reasons[id];
    if (!reason) {
      setError("A reason is required to reject a document.");
      return;
    }
    setBusyId(id);
    setError(null);
    try {
      await rejectDocument(id, reason);
      refresh();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusyId(null);
    }
  }

  if (loading) return <div className="text-sm text-zinc-500" role="status">Loading…</div>;
  if (!data) return <div role="alert"><p>{error || "Unable to load records."}</p><WorkButton type="submit" onClick={refresh}>Try again</WorkButton></div>;

  return (
    <div className="space-y-2">
      {error && <div className="text-xs px-3 py-2 rounded-lg bg-red-500/15 border border-red-500/40 text-red-300">{error}</div>}
      <div className="text-xs text-zinc-600 italic">{data.count} documents awaiting digital approval.</div>
      {data.documents.map((d) => (
        <div key={d.id} className={tc(theme, "rounded-lg border border-zinc-800 bg-black/20 p-2.5", "rounded-lg border border-zinc-200 bg-white p-2.5")}>
          <div className="text-xs font-medium">{d.document_type} — {d.file_name}</div>
          <div className="text-xs text-zinc-500 mb-1.5">uploaded by {d.uploaded_by}</div>
          <div className="flex items-center gap-1.5">
            <WorkButton type="submit" disabled={busyId === d.id} onClick={() => handleApprove(d.id)} className="text-xs px-2.5 py-1 rounded bg-green-700 text-white font-medium hover:opacity-90 transition disabled:opacity-50">Approve</WorkButton>
            <WorkField label="Rejection reason"><WorkInput
              value={reasons[d.id] || ""}
              onChange={(e) => setReasons((prev) => ({ ...prev, [d.id]: e.target.value }))}
              placeholder="Rejection reason…"
              className={`flex-1 rounded-md border px-2 py-1 text-xs ${inputClass}`}
            /></WorkField>
            <WorkButton type="submit" variant="danger" disabled={busyId === d.id} onClick={() => handleReject(d.id)} className="text-xs px-2.5 py-1 rounded bg-red-800 text-white font-medium hover:opacity-90 transition disabled:opacity-50">Reject</WorkButton>
          </div>
        </div>
      ))}
    </div>
  );
}

export function DocumentWorkflowsBoard({ theme }: { theme: Theme }) {
  const [tab, setTab] = useState<Tab>("lookup");

  return (
    <div className={tc(theme, "flex-1 flex flex-col min-h-0 bg-brand-ink text-white", "flex-1 flex flex-col min-h-0 bg-white text-black")}>
      <div className={tc(theme, "flex items-center gap-1.5 p-3 border-b border-zinc-800", "flex items-center gap-1.5 p-3 border-b border-zinc-200")}>
        <WorkButton data-work-view aria-pressed={tab === "lookup"} type="submit"  onClick={() => setTab("lookup")} className={`text-xs px-3 py-1.5 rounded font-medium ${tab === "lookup" ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-300"}`}>Deal Jacket / Title / Compliance Packet</WorkButton>
        <WorkButton data-work-view aria-pressed={tab === "approvals"} type="submit"  onClick={() => setTab("approvals")} className={`text-xs px-3 py-1.5 rounded font-medium ${tab === "approvals" ? "bg-brand-blue text-white" : "bg-zinc-800 text-zinc-300"}`}>Digital Approvals</WorkButton>
      </div>
      <div className="flex-1 overflow-y-auto p-4">
        {tab === "lookup" && <LookupTab theme={theme} />}
        {tab === "approvals" && <ApprovalsTab theme={theme} />}
      </div>
    </div>
  );
}
