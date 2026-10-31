"use client";
import { WorkInput, WorkButton, WorkSelect } from "./WorkspaceUi";
import { WorkField } from "./WorkField";

// Credit Application (session 104 follow-up) -- rendered inside Sales' "Credit
// Application" workflow modal (core/workflow_catalog.py's sales.credit_app). The
// fifth of Sam's ~10 "completely missing" dealership workflows; follows the same
// bespoke-action-component-split-by-tab pattern session 103 established for Up
// System/BDC/Demo Drive -- a `section` prop matching this workflow's 5 named tabs
// (Application Queue, Applicant Information, Consent & Submit, Decision Results,
// Application History) rather than one monolithic render on every tab.
//
// Honest scope note (see lib/creditApp.ts / core/credit_app.py for the full version):
// "decision" here is a simulated, deterministic rules engine reusing the customer's
// on-file CreditScore -- there is no live credit-bureau connection in this sandbox.
import { useEffect, useRef, useState } from "react";
import {
  getCreditAppDashboard,
  listCreditApplications,
  createCreditApplication,
  updateCreditApplicant,
  setCreditAppSsnLast4,
  giveCreditAppConsent,
  submitCreditApplication,
  withdrawCreditApplication,
  linkCreditAppToDeal,
  searchCustomersForCreditApp,
  type CreditAppDashboard,
  type CreditApplication,
  type CustomerBrief,
  type EmploymentStatus,
  type HousingStatus,
} from "@/lib/creditApp";

export type CreditAppSection = "queue" | "applicant" | "consent" | "decision" | "history";

const EMPLOYMENT_OPTIONS: EmploymentStatus[] = ["employed", "self_employed", "unemployed", "retired", "other"];
const HOUSING_OPTIONS: HousingStatus[] = ["own", "rent", "other"];

const DECISION_TONE: Record<string, string> = {
  approved: "text-emerald-300",
  conditional: "text-amber-300",
  declined: "text-red-300",
};

function fmt(ts: string | null): string {
  if (!ts) return "—";
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function money(v: number | null): string {
  if (v === null || v === undefined) return "—";
  return `$${v.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
}

function StatusBadge({ status }: { status: string }) {
  const tone =
    status === "decisioned" ? "text-sky-300" : status === "withdrawn" ? "text-zinc-500" : "text-amber-300";
  return <span className={`text-xs uppercase tracking-wide ${tone}`}>{status}</span>;
}

export function CreditAppBoard({ section = "queue" }: { section?: CreditAppSection }) {
  const [data, setData] = useState<CreditAppDashboard | null>(null);
  const [decisionedHistory, setDecisionedHistory] = useState<CreditApplication[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);

  const [selected, setSelected] = useState<CreditApplication | null>(null);

  // New application form
  const [customerQuery, setCustomerQuery] = useState("");
  const [customerResults, setCustomerResults] = useState<CustomerBrief[]>([]);
  const customerSearchSeq = useRef(0);   // drop out-of-order responses to the customer search
  const [pickedCustomer, setPickedCustomer] = useState<CustomerBrief | null>(null);
  const [requestedAmount, setRequestedAmount] = useState("");

  // Applicant form
  const [employmentStatus, setEmploymentStatus] = useState<EmploymentStatus>("employed");
  const [employerName, setEmployerName] = useState("");
  const [monthlyIncome, setMonthlyIncome] = useState("");
  const [yearsAtEmployer, setYearsAtEmployer] = useState("");
  const [monthlyHousing, setMonthlyHousing] = useState("");
  const [housingStatus, setHousingStatus] = useState<HousingStatus>("rent");
  const [ssnLast4, setSsnLast4] = useState("");

  const [linkDealId, setLinkDealId] = useState("");

  function refresh() {
    setLoading(true);
    Promise.all([getCreditAppDashboard(), listCreditApplications({ status: "decisioned" }), listCreditApplications({ status: "withdrawn" })])
      .then(([d, decisioned, withdrawn]) => {
        setData(d);
        setDecisionedHistory([...decisioned, ...withdrawn].sort((a, b) => (b.updated_at || "").localeCompare(a.updated_at || "")));
        setError(null);
        setSelected((prev) => {
          if (prev) {
            const fresh = d.recent.find((a) => a.id === prev.id);
            if (fresh) return fresh;
          }
          return d.recent.find((a) => a.status === "draft") || d.recent[0] || null;
        });
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Unable to load credit applications."))
      .finally(() => setLoading(false));
  }

  useEffect(refresh, []);

  useEffect(() => {
    if (selected?.applicant) {
      const a = selected.applicant;
      setEmploymentStatus(a.employment_status || "employed");
      setEmployerName(a.employer_name || "");
      setMonthlyIncome(a.monthly_income !== null ? String(a.monthly_income) : "");
      setYearsAtEmployer(a.years_at_employer !== null ? String(a.years_at_employer) : "");
      setMonthlyHousing(a.monthly_housing_payment !== null ? String(a.monthly_housing_payment) : "");
      setHousingStatus(a.housing_status || "rent");
      setSsnLast4(selected.ssn_last4 || "");
    }
  }, [selected?.id]);

  async function startApplication() {
    if (!pickedCustomer) return;
    setBusy(true);
    try {
      const app = await createCreditApplication({
        customer_id: pickedCustomer.id,
        requested_amount: requestedAmount.trim() ? Number(requestedAmount) : null,
      });
      setSelected(app);
      setPickedCustomer(null);
      setCustomerQuery("");
      setCustomerResults([]);
      setRequestedAmount("");
      setMessage(`Started ${app.id} for ${pickedCustomer.name}.`);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to start application.");
    } finally {
      setBusy(false);
    }
  }

  async function saveApplicant() {
    if (!selected) return;
    setBusy(true);
    try {
      await updateCreditApplicant(selected.id, {
        applicant_patch: {
          employment_status: employmentStatus,
          employer_name: employerName || null,
          monthly_income: monthlyIncome.trim() ? Number(monthlyIncome) : null,
          years_at_employer: yearsAtEmployer.trim() ? Number(yearsAtEmployer) : null,
          monthly_housing_payment: monthlyHousing.trim() ? Number(monthlyHousing) : null,
          housing_status: housingStatus,
        },
      });
      if (ssnLast4.trim()) {
        await setCreditAppSsnLast4(selected.id, ssnLast4.trim());
      }
      setMessage("Applicant information saved.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to save applicant information.");
    } finally {
      setBusy(false);
    }
  }

  async function doConsent() {
    if (!selected) return;
    setBusy(true);
    try {
      await giveCreditAppConsent(selected.id);
      setMessage("FCRA consent captured.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to capture consent.");
    } finally {
      setBusy(false);
    }
  }

  async function doSubmit() {
    if (!selected) return;
    setBusy(true);
    try {
      const app = await submitCreditApplication(selected.id);
      setSelected(app);
      setMessage(`Decision: ${app.decision?.decision}.`);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to submit application.");
    } finally {
      setBusy(false);
    }
  }

  async function doWithdraw(appId: string) {
    setBusy(true);
    try {
      await withdrawCreditApplication(appId);
      setMessage("Application withdrawn.");
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to withdraw application.");
    } finally {
      setBusy(false);
    }
  }

  async function doLinkDeal() {
    if (!selected || !linkDealId.trim()) return;
    setBusy(true);
    try {
      const app = await linkCreditAppToDeal(selected.id, linkDealId.trim());
      setSelected(app);
      setLinkDealId("");
      setMessage(`Linked to ${app.linked_deal_id}.`);
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unable to link this application to a deal.");
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
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Total Applications</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-emerald-300">{stats ? stats.approved : "—"}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Approved</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-amber-300">{stats ? stats.conditional : "—"}</div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Conditional</div>
            </div>
            <div className="p-2.5 rounded-lg bg-zinc-900 border border-zinc-800">
              <div className="text-lg font-semibold text-zinc-100">
                {stats && stats.approval_rate_pct !== null ? `${stats.approval_rate_pct}%` : "—"}
              </div>
              <div className="text-xs text-zinc-500 uppercase tracking-wide">Approval Rate</div>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800 mb-3">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Start a Credit Application</div>
            <div className="relative mb-2">
              <WorkField label="Search customer by name/email/phone"><WorkInput
                value={customerQuery}
                onChange={(e) => {
                  const value = e.target.value;
                  setCustomerQuery(value);
                  setPickedCustomer(null);
                  if (value.trim()) {
                    const seq = ++customerSearchSeq.current;
                    searchCustomersForCreditApp(value)
                      .then((r) => { if (seq === customerSearchSeq.current) setCustomerResults(r); })
                      .catch(() => { if (seq === customerSearchSeq.current) setCustomerResults([]); });
                  } else {
                    customerSearchSeq.current++;
                    setCustomerResults([]);
                  }
                }}
                placeholder="Search customer by name/email/phone…"
                className="w-full bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
              /></WorkField>
              {customerResults.length > 0 && !pickedCustomer && (
                <div className="absolute z-10 mt-1 w-full max-h-40 overflow-y-auto rounded border border-zinc-800 bg-zinc-950">
                  {customerResults.map((c) => (
                    <WorkButton type="submit"
                      key={c.id}
                      onClick={() => {
                        setPickedCustomer(c);
                        setCustomerQuery(c.name);
                        setCustomerResults([]);
                      }}
                      className="block w-full text-left px-2 py-1 text-xs text-zinc-200 hover:bg-zinc-800"
                    >
                      {c.name} {c.credit_score ? `· score ${c.credit_score}` : ""}
                    </WorkButton>
                  ))}
                </div>
              )}
            </div>
            <div className="flex items-center gap-2">
              <WorkField label="Requested amount (optional)"><WorkInput
                value={requestedAmount}
                onChange={(e) => setRequestedAmount(e.target.value)}
                inputMode="numeric"
                placeholder="Requested amount (optional)"
                className="flex-1 bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
              /></WorkField>
              <WorkButton type="submit"
                onClick={startApplication}
                disabled={busy || !pickedCustomer}
                className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
              >
                {busy ? "…" : "Start Application"}
              </WorkButton>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
            <div className="text-xs font-medium text-zinc-200 mb-1.5">Recent Applications ({data?.recent.length ?? 0})</div>
            {!data || data.recent.length === 0 ? (
              <div className="text-xs text-zinc-600">No credit applications yet.</div>
            ) : (
              <div className="space-y-1.5">
                {data.recent.map((a) => (
                  <button
                    key={a.id}
                    onClick={() => setSelected(a)}
                    className={`w-full text-left text-xs px-2 py-1.5 rounded border ${
                      selected?.id === a.id ? "border-zinc-500 bg-zinc-800/60" : "border-zinc-800"
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-zinc-200 truncate">{a.customer?.name || a.customer_id} · {a.id}</span>
                      <StatusBadge status={a.status} />
                    </div>
                    <div className="text-zinc-500">
                      {a.decision ? (
                        <span className={DECISION_TONE[a.decision.decision]}>{a.decision.decision}</span>
                      ) : (
                        "not yet decisioned"
                      )}
                      {" · "}
                      {fmt(a.updated_at)}
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      {section === "applicant" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Applicant Information</div>
          {!selected ? (
            <div className="text-xs text-zinc-600">
              Pick or start an application from the Application Queue tab first.
            </div>
          ) : (
            <>
              <div className="text-xs text-zinc-400 mb-2">
                {selected.customer?.name || selected.customer_id} · {selected.id} · <StatusBadge status={selected.status} />
              </div>
              <div className="grid grid-cols-3 gap-2 mb-2">
                <WorkField label="Employment Status"><WorkSelect
                  value={employmentStatus}
                  onChange={(e) => setEmploymentStatus(e.target.value as EmploymentStatus)}
                  disabled={selected.status !== "draft"}
                  className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 disabled:opacity-40"
                >
                  {EMPLOYMENT_OPTIONS.map((o) => (
                    <option key={o} value={o}>{o.replace(/_/g, " ")}</option>
                  ))}
                </WorkSelect></WorkField>
                <WorkField label="Employer name"><WorkInput
                  value={employerName}
                  onChange={(e) => setEmployerName(e.target.value)}
                  disabled={selected.status !== "draft"}
                  placeholder="Employer name"
                  className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 disabled:opacity-40"
                /></WorkField>
                <WorkField label="Years at employer"><WorkInput
                  value={yearsAtEmployer}
                  onChange={(e) => setYearsAtEmployer(e.target.value)}
                  disabled={selected.status !== "draft"}
                  inputMode="decimal"
                  placeholder="Years at employer"
                  className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 disabled:opacity-40"
                /></WorkField>
                <WorkField label="Monthly income"><WorkInput
                  value={monthlyIncome}
                  onChange={(e) => setMonthlyIncome(e.target.value)}
                  disabled={selected.status !== "draft"}
                  inputMode="numeric"
                  placeholder="Monthly income"
                  className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 disabled:opacity-40"
                /></WorkField>
                <WorkField label="Monthly housing payment"><WorkInput
                  value={monthlyHousing}
                  onChange={(e) => setMonthlyHousing(e.target.value)}
                  disabled={selected.status !== "draft"}
                  inputMode="numeric"
                  placeholder="Monthly housing payment"
                  className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 disabled:opacity-40"
                /></WorkField>
                <WorkField label="Housing Status"><WorkSelect
                  value={housingStatus}
                  onChange={(e) => setHousingStatus(e.target.value as HousingStatus)}
                  disabled={selected.status !== "draft"}
                  className="bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 disabled:opacity-40"
                >
                  {HOUSING_OPTIONS.map((o) => (
                    <option key={o} value={o}>{o}</option>
                  ))}
                </WorkSelect></WorkField>
              </div>
              <div className="flex items-center gap-2">
                <WorkField label="SSN last 4 digits only"><WorkInput
                  value={ssnLast4}
                  onChange={(e) => setSsnLast4(e.target.value.replace(/\D/g, "").slice(0, 4))}
                  disabled={selected.status !== "draft"}
                  inputMode="numeric"
                  placeholder="SSN last 4 digits only"
                  className="w-44 bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600 disabled:opacity-40"
                /></WorkField>
                {selected.status === "draft" && (
                  <WorkButton type="submit"
                    onClick={saveApplicant}
                    disabled={busy}
                    className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
                  >
                    {busy ? "…" : "Save"}
                  </WorkButton>
                )}
              </div>
              {selected.status !== "draft" && (
                <p className="text-xs text-zinc-600 mt-2">
                  This application is {selected.status} -- only a draft application can be edited.
                </p>
              )}
            </>
          )}
        </div>
      )}

      {section === "consent" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Consent &amp; Submit</div>
          {!selected ? (
            <div className="text-xs text-zinc-600">
              Pick or start an application from the Application Queue tab first.
            </div>
          ) : (
            <>
              <p className="text-xs text-zinc-500 leading-relaxed mb-3">
                FCRA requires the applicant&rsquo;s consent (a permissible purpose) before a
                credit decision can run -- an enforced gate, not just a UI checkbox: the
                backend refuses to decision an application without it on file.
              </p>
              <div className="flex items-center gap-3 mb-3">
                <span className="text-xs text-zinc-300">
                  Consent on file: {selected.fcra_consent ? (
                    <span className="text-emerald-300">yes ({fmt(selected.fcra_consent_at)})</span>
                  ) : (
                    <span className="text-amber-300">not yet</span>
                  )}
                </span>
                {!selected.fcra_consent && selected.status === "draft" && (
                  <WorkButton type="submit"
                    onClick={doConsent}
                    disabled={busy}
                    className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
                  >
                    {busy ? "…" : "Capture Consent"}
                  </WorkButton>
                )}
              </div>
              {selected.status === "draft" && (
                <WorkButton type="submit"
                  onClick={doSubmit}
                  disabled={busy || !selected.fcra_consent || !selected.applicant.monthly_income}
                  className="bg-emerald-900/50 border border-emerald-800 text-emerald-200 rounded px-3 py-1.5 text-xs disabled:opacity-40"
                >
                  {busy ? "…" : "Run Decision"}
                </WorkButton>
              )}
              {!selected.applicant.monthly_income && selected.status === "draft" && (
                <p className="text-xs text-zinc-600 mt-2">
                  Monthly income is required (Applicant Information tab) before submitting.
                </p>
              )}
              {selected.status === "decisioned" && (
                <p className="text-xs text-zinc-500 mt-1">Already decisioned -- see Decision Results.</p>
              )}
              {selected.status === "draft" && (
                <div className="mt-3">
                  <WorkButton type="submit"
                    onClick={() => doWithdraw(selected.id)}
                    disabled={busy}
                    className="bg-zinc-800 border border-zinc-700 text-zinc-300 rounded px-3 py-1 text-xs disabled:opacity-40"
                  >
                    Withdraw Application
                  </WorkButton>
                </div>
              )}
            </>
          )}
        </div>
      )}

      {section === "decision" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Decision Results</div>
          {!selected ? (
            <div className="text-xs text-zinc-600">
              Pick or start an application from the Application Queue tab first.
            </div>
          ) : !selected.decision ? (
            <div className="text-xs text-zinc-600">
              No decision yet -- capture consent and applicant info, then run a decision
              from the Consent &amp; Submit tab.
            </div>
          ) : (
            <>
              <div className="flex items-center gap-3 mb-2">
                <span className={`text-sm font-semibold uppercase ${DECISION_TONE[selected.decision.decision]}`}>
                  {selected.decision.decision}
                </span>
                <span className="text-xs text-zinc-400">{selected.decision.score_band} band</span>
                {selected.decision.simulated_score !== null && (
                  <span className="text-xs text-zinc-500">score {selected.decision.simulated_score}</span>
                )}
                {selected.decision.estimated_apr !== null && (
                  <span className="text-xs text-zinc-500">~{selected.decision.estimated_apr}% APR</span>
                )}
              </div>
              <p className="text-xs text-zinc-600 mb-2">
                Simulated decision, not a real credit-bureau pull -- reuses the customer&rsquo;s
                on-file credit score as input to a deterministic rules engine.
              </p>
              {selected.decision.stipulations.length > 0 && (
                <div className="mb-2">
                  <div className="text-xs text-zinc-400 mb-1">Stipulations:</div>
                  <ul className="text-xs text-zinc-300 list-disc list-inside space-y-0.5">
                    {selected.decision.stipulations.map((s, i) => <li key={i}>{s}</li>)}
                  </ul>
                </div>
              )}
              {selected.decision.reasons.length > 0 && (
                <div className="mb-3">
                  <div className="text-xs text-zinc-400 mb-1">Reasons (ECOA/Reg B adverse-action):</div>
                  <ul className="text-xs text-red-300 list-disc list-inside space-y-0.5">
                    {selected.decision.reasons.map((r, i) => <li key={i}>{r}</li>)}
                  </ul>
                </div>
              )}
              {requestedAmountLine(selected)}
              <div className="flex items-center gap-2 mt-3">
                <WorkField label="Link Deal ID"><WorkInput
                  value={linkDealId}
                  onChange={(e) => setLinkDealId(e.target.value)}
                  placeholder={selected.linked_deal_id ? `Linked: ${selected.linked_deal_id}` : "Deal ID to link (DEAL-…)"}
                  className="flex-1 bg-zinc-950 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200 placeholder:text-zinc-600"
                /></WorkField>
                <WorkButton type="submit"
                  onClick={doLinkDeal}
                  disabled={busy || !linkDealId.trim()}
                  className="bg-zinc-200 text-black font-medium rounded px-3 py-1 text-xs disabled:opacity-40"
                >
                  Link
                </WorkButton>
              </div>
            </>
          )}
        </div>
      )}

      {section === "history" && (
        <div className="p-3 rounded-lg bg-zinc-900 border border-zinc-800">
          <div className="text-xs font-medium text-zinc-200 mb-1.5">Application History ({decisionedHistory.length})</div>
          {decisionedHistory.length === 0 ? (
            <div className="text-xs text-zinc-600">No decisioned or withdrawn applications yet.</div>
          ) : (
            <div className="space-y-1.5">
              {decisionedHistory.map((a) => (
                <div key={a.id} className="text-xs px-2 py-1.5 rounded border border-zinc-800">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-zinc-200 truncate">{a.customer?.name || a.customer_id} · {a.id}</span>
                    <StatusBadge status={a.status} />
                  </div>
                  <div className="text-zinc-500">
                    {a.decision && <span className={DECISION_TONE[a.decision.decision]}>{a.decision.decision}</span>}
                    {a.decision && " · "}
                    {fmt(a.updated_at)}
                    {a.linked_deal_id ? ` · linked to ${a.linked_deal_id}` : ""}
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

function requestedAmountLine(app: CreditApplication) {
  if (app.requested_amount === null) return null;
  return (
    <div className="text-xs text-zinc-400">
      Requested amount: <span className="text-zinc-200">{money(app.requested_amount)}</span>
    </div>
  );
}
