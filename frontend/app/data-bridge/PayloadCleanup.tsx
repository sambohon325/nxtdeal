"use client";
import {useState} from "react";
import {API_BASE} from "@/lib/api";
import {authHeaders} from "@/lib/auth";
import styles from "./page.module.css";

type Cleanup = {removed_at: string; removed_by: string; row_count: number; preview_row_count: number};
type Review = {eligible: boolean; retained_rows: number; retained_preview_rows: number; review_token: string; receipt_required: boolean; receipt_consistent: boolean; cleanup: Cleanup | null; notice: string};

export default function PayloadCleanup({jobId, disabled, onRemoved, resource = "imports"}: {jobId: string; disabled: boolean; onRemoved: () => Promise<void>; resource?: "imports" | "event-imports"}) {
  const [review, setReview] = useState<Review | null>(null);
  const [reason, setReason] = useState("");
  const [acknowledged, setAcknowledged] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function exchange(remove: boolean) {
    setBusy(true); setError(""); setAcknowledged(false);
    try {
      const response = await fetch(`${API_BASE}/dealer-bridge/${resource}/${jobId}/payload-cleanup`, {
        method: remove ? "POST" : "GET", headers: {...authHeaders(), "Content-Type": "application/json"},
        ...(remove && review ? {body: JSON.stringify({review_token: review.review_token, reason})} : {}),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(typeof result.detail === "string" ? result.detail : "Staging-copy cleanup could not be completed.");
      if (remove && review) {
        setReview({...review, eligible: false, retained_rows: 0, retained_preview_rows: 0, cleanup: result.cleanup});
        setReason(""); await onRemoved();
      } else setReview(result);
    } catch (failure) {setError(failure instanceof Error ? failure.message : "Cleanup review could not be loaded.");}
    finally {setBusy(false);}
  }
  return <details><summary>Review staging-copy cleanup</summary>
    <p>This permanently removes only the duplicate staging rows and cached preview for this finished import. Imported records and source history remain.</p>
    <button disabled={disabled || busy} onClick={() => exchange(false)}>{review ? "Refresh cleanup review" : "Load cleanup review"}</button>
    {error && <p role="alert" className={styles.error}>{error}</p>}
    {review && <div><p>{review.notice}</p>
      <p>{review.retained_rows} staging rows and {review.retained_preview_rows} cached preview rows remain.</p>
      {review.cleanup ? <p role="status">Staging copy removed by {review.cleanup.removed_by} at {review.cleanup.removed_at}. Source history and approval evidence remain.</p> : <>
        {review.receipt_required && !review.receipt_consistent && <p role="alert">Cleanup is unavailable because this import does not have a consistent recorded approval receipt.</p>}
        {review.eligible && <fieldset disabled={disabled || busy}>
          <label>Cleanup reason<input value={reason} maxLength={500} onChange={event => {setReason(event.target.value); setAcknowledged(false);}} placeholder="Record your retention decision" /></label>
          <label className={styles.checkOption}><input type="checkbox" checked={acknowledged} onChange={event => setAcknowledged(event.target.checked)} />I reviewed the retention requirements and understand this staging copy will be permanently removed.</label>
          <button disabled={!acknowledged || reason.trim().length < 8} onClick={() => exchange(true)}>Permanently remove staging copy</button>
        </fieldset>}
      </>}
    </div>}
  </details>;
}
