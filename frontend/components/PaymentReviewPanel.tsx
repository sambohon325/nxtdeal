"use client";
import {WorkButton} from "./WorkspaceUi";
import {CollectionPagination} from "./CollectionPagination";
import {RecordTable} from "./RecordTable";

import { useEffect, useState } from "react";
import { getPaymentReview, paymentReviewReasons, type PaymentReview } from "@/lib/paymentReview";

export function PaymentReviewPanel() {
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const requestKey = `${offset}:${revision}`;
  const [result, setResult] = useState<{ key: string; report?: PaymentReview; error?: string } | null>(null);
  const current = result?.key === requestKey ? result : null;
  const loading = current === null;
  const report = current?.report;

  useEffect(() => {
    const controller = new AbortController();
    getPaymentReview(offset, controller.signal).then(report => {
      if (!controller.signal.aborted) setResult({ key: requestKey, report });
    }).catch(error => {
      if (!controller.signal.aborted) setResult({ key: requestKey, error: error instanceof Error ? error.message : "Unable to load payment review." });
    });
    return () => controller.abort();
  }, [offset, requestKey]);

  return <section aria-labelledby="payment-review-heading" className="p-4 space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div><h2 id="payment-review-heading" className="font-semibold">Payment evidence review</h2>
        <p className="text-sm opacity-75">Read-only review of receipts that need supporting evidence.</p></div>
      <WorkButton className="rounded border px-3 py-1.5 text-sm disabled:opacity-50" disabled={loading}
        onClick={() => { setOffset(0); setRevision(value => value + 1); }}>Refresh review</WorkButton>
    </div>
    <p className="text-sm">Match flagged receipts to original receipts and bank records before making a correction. Reviewing this list does not change a loan balance or confirm settlement.</p>
    {loading && <p role="status">Loading payment review…</p>}
    {current?.error && <p role="alert">{current.error} <WorkButton className="underline" onClick={() => setRevision(value => value + 1)}>Try again</WorkButton></p>}
    {report && <>
      <dl className="grid gap-3 sm:grid-cols-3 text-sm">
        <div className="rounded border p-3"><dt>Receipts checked</dt><dd className="text-xl font-semibold">{report.scanned_payments}</dd></div>
        <div className="rounded border p-3"><dt>Receipts needing review</dt><dd className="text-xl font-semibold">{report.flagged_payments}</dd></div>
        <div className="rounded border p-3"><dt>Flagged approved receipt values</dt><dd className="text-xl font-semibold break-all">${report.flagged_approved_receipt_total}</dd><p className="text-xs">Recorded amounts, not verified cash or a balance adjustment.</p></div>
      </dl>
      {report.records.length ? <div className="overflow-x-auto"><RecordTable paginate={false} label="Receipts" className="w-full text-left text-sm">
        <caption className="sr-only">Receipts requiring evidence review</caption>
        <thead><tr>{["Receipt / loan", "Recorded amount", "Record status", "Review reason"].map(label => <th key={label} scope="col" className="p-2 border-b">{label}</th>)}</tr></thead>
        <tbody>{report.records.map(row => <tr key={row.payment_id}>
          <th scope="row" className="p-2 border-b font-normal">{row.payment_id}<div className="text-xs opacity-75">{row.loan_id || "No linked loan"}</div></th>
          <td className="p-2 border-b">{row.amount === null ? "Invalid or missing" : `$${row.amount}`}</td>
          <td className="p-2 border-b">{row.approved ? "Marked approved" : "Not marked approved"}<div className="text-xs">{row.posted ? "Posted to accounting" : "Not posted"}</div></td>
          <td className="p-2 border-b"><ul>{row.reasons.map(reason => <li key={reason}>{paymentReviewReasons[reason] || "Additional review required"}</li>)}</ul></td>
        </tr>)}</tbody>
      </RecordTable></div> : <p>{report.flagged_payments === 0 ? "No receipts were flagged by these checks. This does not confirm bank reconciliation." : "No receipts on this page. Refresh to load the latest review."}</p>}
      <CollectionPagination label="Receipts" total={report.flagged_payments} page={Math.floor(offset / 25)} pageSize={25} onPageChange={page=>setOffset(page * 25)} busy={loading}/>
    </>}
  </section>;
}
