"use client";
import { WorkInput, WorkSelect, WorkButton } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// eSignature (session 104 follow-up) -- rendered inside Sales' "eSignature" workflow
// modal (core/workflow_catalog.py's sales.esignature). The sixth of Sam's ~10
// "completely missing" dealership workflows; follows the same bespoke-action-
// component-split-by-tab pattern session 103/104 established for Up System/BDC/
// Demo Drive/Credit App -- a `section` prop matching this workflow's 5 named tabs
// (Envelope Queue, Signer Setup, Send for Signature, Sign & Consent, Completed
// Envelopes) rather than one monolithic render on every tab.
//
// Honest scope note (see lib/esignature.ts / core/esignature.py for the full
// version): there is no live e-signature platform connected in this sandbox --
// "sending" is a state transition, and "signing" is a typed-name capture, not a
// cryptographic signature.
import { useEffect, useState } from "react";
import {
  getEsignatureDashboard,
  listSignatureRequests,
  createSignatureRequest,
  addSigner,
  removeSigner,
  sendSignatureRequest,
  captureSignerConsent,
  signEnvelope,
  declineSigner,
  voidSignatureRequest,
  type EsignatureDashboard,
  type SignatureRequest,
  type SignerRole,
} from "@/lib/esignature";

export type ESignatureSection = "queue" | "signers" | "send" | "sign" | "history";

const SIGNER_ROLES: SignerRole[] = ["customer", "co_signer", "dealer_rep"];

const STATUS_TONE: Record<string, string> = {
  draft: "text-zinc-500",
  sent: "text-amber-300",
  completed: "text-emerald-300",
  declined: "text-red-300",
  voided: "text-zinc-600",
};

function fmt(ts: string | null): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function money(v: number | null | undefined): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function StatusBadge({ status }: { status: string }) {
  return <span className={`text-xs uppercase tracking-wide ${STATUS_TONE[status] || "text-zinc-400"}`}>{status}</span>;
}

function NoEnvelope() {
  return (
    <div className="text-xs text-zinc-600">
      Pick or start an envelope from the Envelope Queue tab first.
    </div>
  );
}

export function ESignatureBoard({ section = "queue" }: { section?: ESignatureSection }) {
  const [data, setData] = useState<EsignatureDashboard | null>(null);
  const [history, setHistory] = useState<SignatureRequest[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [selected, setSelected] = useState<SignatureRequest | null>(null);

  // New envelope form
  const [dealId, setDealId] = useState("");
  const [starterName, setStarterName] = useState("");
  const [starterRole, setStarterRole] = useState<SignerRole>("customer");

  // Add-signer form
  const [signerName, setSignerName] = useState("");
  const [signerRole, setSignerRole] = useState<SignerRole>("co_signer");
  const [signerEmail, setSignerEmail] = useState("");

  // Sign form state, keyed by signer index
  const [typedSignatures, setTypedSignatures] = useState<Record<number, string>>({});
  const [declineReasons, setDeclineReasons] = useState<Record<number, string>>({});

  function refresh() {
    setLoading(true);
    Promise.all([
      getEsignatureDashboard(),
      listSignatureRequests({ status: "completed" }),
      listSignatureRequests({ status: "declined" }),
      listSignatureRequests({ status: "voided" }),
    ])
      .then(([d, completed, declined, voided]) => {
        setData(d);
        setHistory(
          [...completed, ...declined, ...voided].sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || "")),
        );
        setError(null);
        setSelected((prev) => {
          if (prev) {
            const fresh = d.recent.find((r) => r.id === prev.id);
            if (fresh) return fresh;
          }
          return d.recent.find((r) => r.status === "draft" || r.status === "sent") || d.recent[0] || null;
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load signature envelopes."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  async function startEnvelope() {
    if (!dealId.trim() || !starterName.trim()) return;
    setBusy(true);
    try {
      const req = await createSignatureRequest({
        linked_deal_id: dealId.trim(),
        signers: [{ name: starterName.trim(), role: starterRole }],
      });
      setSelected(req);
      setDealId("");
      setStarterName("");
      setMessage(`Started ${req.id}.`);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to start envelope.");
    } finally {
      setBusy(false);
    }
  }

  async function handleAddSigner() {
    if (!selected || !signerName.trim()) return;
    setBusy(true);
    try {
      const req = await addSigner(selected.id, { name: signerName.trim(), role: signerRole, email: signerEmail.trim() || undefined });
      setSelected(req);
      setSignerName("");
      setSignerEmail("");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to add signer.");
    } finally {
      setBusy(false);
    }
  }

  async function handleRemoveSigner(index: number) {
    if (!selected) return;
    setBusy(true);
    try {
      const req = await removeSigner(selected.id, index);
      setSelected(req);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to remove signer.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSend() {
    if (!selected) return;
    setBusy(true);
    try {
      const req = await sendSignatureRequest(selected.id);
      setSelected(req);
      setMessage("Envelope sent for signature.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to send envelope.");
    } finally {
      setBusy(false);
    }
  }

  async function handleVoid() {
    if (!selected) return;
    setBusy(true);
    try {
      const req = await voidSignatureRequest(selected.id);
      setSelected(req);
      setMessage("Envelope voided.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to void envelope.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConsent(index: number) {
    if (!selected) return;
    setBusy(true);
    try {
      const req = await captureSignerConsent(selected.id, index);
      setSelected(req);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to capture consent.");
    } finally {
      setBusy(false);
    }
  }

  async function handleSign(index: number) {
    if (!selected) return;
    const typed = typedSignatures[index] || "";
    if (!typed.trim()) return;
    setBusy(true);
    try {
      const req = await signEnvelope(selected.id, index, typed.trim());
      setSelected(req);
      setTypedSignatures((prev) => ({ ...prev, [index]: "" }));
      setMessage("Signature captured.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to record signature.");
    } finally {
      setBusy(false);
    }
  }

  async function handleDecline(index: number) {
    if (!selected) return;
    const reason = declineReasons[index] || "";
    if (!reason.trim()) return;
    setBusy(true);
    try {
      const req = await declineSigner(selected.id, index, reason.trim());
      setSelected(req);
      setDeclineReasons((prev) => ({ ...prev, [index]: "" }));
      setMessage("Signer declined -- envelope voided.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to record decline.");
    } finally {
      setBusy(false);
    }
  }

  const stats = data?.stats;

  if (loading) {
    return <div className="mb-5 text-xs text-zinc-600">Loading…</div>;
  }

  return (
    <div className="mb-5">
      {error && <div className="text-xs text-red-400 mb-2">{error}</div>}
      {message && <div className="text-xs text-emerald-400 mb-2">{message}</div>}

      {section === "queue" && (
        <>
          <div className="grid grid-cols-4 gap-2 mb-3">
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">{stats ? stats.total : "—"}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Total Envelopes</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-amber-300">{stats ? stats.sent : "—"}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Awaiting Signature</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-emerald-300">{stats ? stats.completed : "—"}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Completed</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">
                {stats && stats.completion_rate_pct !== null ? `${stats.completion_rate_pct}%` : "—"}
              </div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Completion Rate</div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 mb-3">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Start a Signing Envelope</div>
            <p className="text-xs text-zinc-600 mb-2">
              Requires the deal to already have a generated contract (Desking → Contract Readiness).
            </p>
            <div className="grid grid-cols-3 gap-2 mb-2">
              <WorkField label="Deal ID (DEAL-…)"><WorkInput
                value={dealId}
                onChange={(e) => setDealId(e.target.value)}
                placeholder="Deal ID (DEAL-…)"
                className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
              /></WorkField>
              <WorkField label="First signer's name"><WorkInput
                value={starterName}
                onChange={(e) => setStarterName(e.target.value)}
                placeholder="First signer's name"
                className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
              /></WorkField>
              <WorkField label="Starter Role"><WorkSelect
                value={starterRole}
                onChange={(e) => setStarterRole(e.target.value as SignerRole)}
                className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200"
              >
                {SIGNER_ROLES.map((r) => (
                  <option key={r} value={r}>{r.replace(/_/g, " ")}</option>
                ))}
              </WorkSelect></WorkField>
            </div>
            <WorkButton type="submit"
              onClick={startEnvelope}
              disabled={busy || !dealId.trim() || !starterName.trim()}
              className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
            >
              {busy ? "…" : "Start Envelope"}
            </WorkButton>
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Recent Envelopes ({data?.recent.length ?? 0})</div>
            {!data || data.recent.length === 0 ? (
              <div className="text-xs text-zinc-600">No signature envelopes yet.</div>
            ) : (
              <div className="space-y-1.5">
                {data.recent.map((r) => (
                  <button
                    key={r.id}
                    onClick={() => setSelected(r)}
                    className={`w-full text-left text-xs px-2 py-1.5 rounded border ${
                      selected?.id === r.id ? "border-zinc-500 bg-zinc-800/60" : "border-zinc-800"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-zinc-200 truncate">
                        {r.customer?.name || r.linked_deal_id} · {r.id} · {r.linked_deal_id}
                      </span>
                      <StatusBadge status={r.status} />
                    </div>
                    <div className="text-zinc-500">
                      {r.signers.filter((s) => s.status === "signed").length}/{r.signers.length} signed · {fmt(r.updated_at)}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {section === "signers" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Signer Setup</div>
          {!selected ? (
            <NoEnvelope />
          ) : (
            <>
              <div className="text-xs text-zinc-400 mb-2">
                {selected.id} · Deal {selected.linked_deal_id} · <StatusBadge status={selected.status} />
              </div>
              <div className="p-2.5 rounded-lg bg-zinc-950 border border-zinc-800 mb-3 text-xs text-zinc-300 space-y-0.5">
                <div className="text-zinc-200 font-medium">{selected.contract_snapshot.vehicle_description}</div>
                <div>Sale price {money(selected.contract_snapshot.sale_price)} · APR {selected.contract_snapshot.apr}% · {selected.contract_snapshot.term_months}mo</div>
                <div>Monthly payment {money(selected.contract_snapshot.monthly_payment)}</div>
              </div>

              <div className="space-y-1.5 mb-3">
                {selected.signers.map((s, i) => (
                  <div key={i} className="flex items-center justify-between gap-2 text-xs px-2 py-1.5 rounded border border-zinc-800">
                    <span className="text-zinc-200">{s.name} <span className="text-zinc-500">({s.role.replace(/_/g, " ")})</span></span>
                    <div className="flex items-center gap-2">
                      <StatusBadge status={s.status} />
                      {selected.status === "draft" && (
                        <WorkButton type="submit" variant="danger"
                          onClick={() => handleRemoveSigner(i)}
                          disabled={busy}
                          className="text-xs text-red-400 disabled:opacity-40"
                        >
                          Remove
                        </WorkButton>
                      )}
                    </div>
                  </div>
                ))}
              </div>

              {selected.status === "draft" && (
                <div className="flex flex-wrap items-center gap-2">
                  <WorkField label="Signer name"><WorkInput
                    value={signerName}
                    onChange={(e) => setSignerName(e.target.value)}
                    placeholder="Signer name"
                    className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
                  /></WorkField>
                  <WorkField label="Signer Role"><WorkSelect
                    value={signerRole}
                    onChange={(e) => setSignerRole(e.target.value as SignerRole)}
                    className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200"
                  >
                    {SIGNER_ROLES.map((r) => (
                      <option key={r} value={r}>{r.replace(/_/g, " ")}</option>
                    ))}
                  </WorkSelect></WorkField>
                  <WorkField label="Email (optional)"><WorkInput
                    value={signerEmail}
                    onChange={(e) => setSignerEmail(e.target.value)}
                    placeholder="Email (optional)"
                    className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
                  /></WorkField>
                  <WorkButton type="submit"
                    onClick={handleAddSigner}
                    disabled={busy || !signerName.trim()}
                    className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
                  >
                    + Add Signer
                  </WorkButton>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {section === "send" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Send for Signature</div>
          {!selected ? (
            <NoEnvelope />
          ) : (
            <>
              <p className="text-xs text-zinc-500 leading-relaxed mb-3">
                Sending is a simulated dispatch in this environment -- no real email or
                SMS goes out. Once sent, each signer can consent and sign from the
                Sign &amp; Consent tab.
              </p>
              <div className="text-xs text-zinc-300 mb-3">
                Status: <StatusBadge status={selected.status} />
                {selected.sent_at && <span className="text-zinc-500"> · sent {fmt(selected.sent_at)}</span>}
              </div>
              {selected.status === "draft" && (
                <WorkButton type="submit"
                  onClick={handleSend}
                  disabled={busy || selected.signers.length === 0}
                  className="bg-emerald-900/50 border border-emerald-800 text-emerald-200 rounded px-3 py-1.5 text-xs disabled:opacity-40 mr-2"
                >
                  {busy ? "…" : "Send Envelope"}
                </WorkButton>
              )}
              {(selected.status === "draft" || selected.status === "sent") && (
                <WorkButton type="submit"
                  onClick={handleVoid}
                  disabled={busy}
                  className="bg-zinc-800 border border-zinc-700 text-zinc-300 rounded px-3 py-1 text-xs disabled:opacity-40"
                >
                  Void Envelope
                </WorkButton>
              )}
              {selected.signers.length === 0 && selected.status === "draft" && (
                <p className="text-xs text-zinc-600 mt-2">Add at least one signer (Signer Setup tab) before sending.</p>
              )}
            </>
          )}
        </div>
      )}

      {section === "sign" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Sign &amp; Consent</div>
          {!selected ? (
            <NoEnvelope />
          ) : selected.status !== "sent" ? (
            <div className="text-xs text-zinc-600">
              This envelope is {selected.status} -- signing is only available once it's been sent.
            </div>
          ) : (
            <div className="space-y-2">
              {selected.signers.map((s, i) => (
                <div key={i} className="p-2.5 rounded-lg border border-zinc-800">
                  <div className="flex items-center justify-between gap-2 mb-1.5">
                    <span className="text-xs text-zinc-200">{s.name} <span className="text-zinc-500">({s.role.replace(/_/g, " ")})</span></span>
                    <StatusBadge status={s.status} />
                  </div>
                  {s.status === "signed" && (
                    <div className="text-xs text-zinc-500">
                      Signed &ldquo;{s.typed_signature}&rdquo; · {fmt(s.signed_at)}
                    </div>
                  )}
                  {s.status === "declined" && (
                    <div className="text-xs text-red-300">Declined: {s.decline_reason}</div>
                  )}
                  {s.status === "pending" && (
                    <>
                      {!s.esign_consent ? (
                        <WorkButton type="submit"
                          onClick={() => handleConsent(i)}
                          disabled={busy}
                          className="bg-zinc-200 text-black font-medium rounded px-2.5 py-1 text-xs disabled:opacity-40"
                        >
                          Capture Electronic Signature Consent
                        </WorkButton>
                      ) : (
                        <div className="flex flex-wrap items-center gap-2">
                          <WorkField label="Type full name to sign"><WorkInput
                            value={typedSignatures[i] || ""}
                            onChange={(e) => setTypedSignatures((prev) => ({ ...prev, [i]: e.target.value }))}
                            placeholder="Type full name to sign"
                            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
                          /></WorkField>
                          <WorkButton type="submit"
                            onClick={() => handleSign(i)}
                            disabled={busy || !(typedSignatures[i] || "").trim()}
                            className="bg-emerald-900/50 border border-emerald-800 text-emerald-200 rounded px-2.5 py-1 text-xs disabled:opacity-40"
                          >
                            Sign
                          </WorkButton>
                          <WorkField label="Decline reason"><WorkInput
                            value={declineReasons[i] || ""}
                            onChange={(e) => setDeclineReasons((prev) => ({ ...prev, [i]: e.target.value }))}
                            placeholder="Decline reason"
                            className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
                          /></WorkField>
                          <WorkButton type="submit" variant="danger"
                            onClick={() => handleDecline(i)}
                            disabled={busy || !(declineReasons[i] || "").trim()}
                            className="bg-red-950/50 border border-red-900 text-red-300 rounded px-2.5 py-1 text-xs disabled:opacity-40"
                          >
                            Decline
                          </WorkButton>
                        </div>
                      )}
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {section === "history" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Completed Envelopes ({history.length})</div>
          {history.length === 0 ? (
            <div className="text-xs text-zinc-600">No completed, declined, or voided envelopes yet.</div>
          ) : (
            <div className="space-y-1.5">
              {history.map((r) => (
                <div key={r.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-zinc-200 truncate">{r.customer?.name || r.linked_deal_id} · {r.id}</span>
                    <StatusBadge status={r.status} />
                  </div>
                  <div className="text-zinc-500">
                    {r.signers.filter((s) => s.status === "signed").length}/{r.signers.length} signed · {fmt(r.updated_at)}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
