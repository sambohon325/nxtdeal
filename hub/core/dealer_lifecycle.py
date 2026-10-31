"""
hub/core/dealer_lifecycle.py -- the free-account inactivity lifecycle (NXTDeal Freemium, 2026-08-03).

Sam's rule for self-serve Free Forever accounts:
  * A NXTDeal instance DEACTIVATES after 6 months of no activity.
  * 6 months after that (12 months of no activity total) it is automatically DELETED --
  * UNLESS it is re-logged into, which reactivates it and resets the clock.

This keeps abandoned free instances from accumulating forever, while giving a real, generous window
(and a full second window after deactivation) to come back. Any dealer login or product activity
calls record_dealer_activity(), which bumps the clock and un-deactivates an inactivity-suspended
account. A periodic sweep() applies the transitions.

Design notes:
  * Only inactivity-driven suspensions are eligible for auto-deletion. A dealer an admin suspended
    for another reason (billing, abuse) is never auto-deleted by this sweep -- suspended_reason
    gates that.
  * Paid dealers are exempt from auto-deletion (never delete a paying customer for going quiet); they
    can still be flagged, but the destructive step is Foundation-only. This is a safety default, not
    a limit -- adjust DELETE_ELIGIBLE_TIERS if desired.
  * Time is injectable (now=) so the rules are unit-tested deterministically; the store is injected
    (see _signup_store.py) so this is drop-in for the real Hub.
"""

from hub.core._signup_store import InMemoryDealerStore, utcnow, parse_iso


# ~6 months each (183 days keeps it simple + slightly generous vs a strict 182.5).
INACTIVITY_DEACTIVATE_DAYS = 183          # active -> deactivated after this much no-activity
DELETE_AFTER_DEACTIVATED_DAYS = 183       # deactivated -> deleted after this much more (12mo total)

# A dealer is "inactivity-deactivated" when status == suspended AND this reason is set.
INACTIVITY_REASON = "inactivity"

# Only these plan tiers may be AUTO-DELETED by the sweep (never auto-delete a paying dealer).
DELETE_ELIGIBLE_TIERS = {"foundation"}

# Statuses that are actively "in use" and therefore eligible to be deactivated for inactivity. A
# dealer already suspended, or still a lead/demo/trial in the sales funnel, isn't touched by the
# inactivity->deactivate step.
ACTIVE_STATUSES = {"active", "expansion", "churn_risk"}


_store = InMemoryDealerStore()


def set_store(store):
    global _store
    _store = store


def _days_between(earlier_iso, now):
    dt = parse_iso(earlier_iso)
    if dt is None:
        return None
    return (now - dt).total_seconds() / 86400.0


# ---------------------------------------------------------------------------
# Activity / reactivation -- called on any dealer login or product activity.
# ---------------------------------------------------------------------------

def record_dealer_activity(dealer_id, now=None):
    """Stamp last_activity_at=now and, if the dealer was deactivated FOR INACTIVITY, bring it back to
    life (this is the "unless re-logged into" reactivation). Returns the fresh record, or an error."""
    now = now or utcnow()
    dealer = _store.get(dealer_id)
    if not dealer:
        return {"error": f"No dealer '{dealer_id}'."}

    reactivated = False
    if dealer.get("status") == "suspended" and dealer.get("suspended_reason") == INACTIVITY_REASON:
        dealer["status"] = "active"
        dealer["suspended_reason"] = None
        dealer["deactivated_at"] = None
        dealer["scheduled_deletion_at"] = None
        reactivated = True

    dealer["last_activity_at"] = now.isoformat()
    _store.save(dealer)
    return {"ok": True, "dealer_id": dealer_id, "reactivated": reactivated, "status": dealer["status"]}


# ---------------------------------------------------------------------------
# The sweep -- run periodically (Hub cron). Idempotent.
# ---------------------------------------------------------------------------

def evaluate_dealer(dealer, now):
    """Pure classification of one dealer against the rules right now -> one of:
    'ok' | 'deactivate' | 'delete' | 'skip'. No mutation."""
    status = dealer.get("status")
    inactive_days = _days_between(dealer.get("last_activity_at"), now)

    # Already inactivity-deactivated -> candidate for deletion once the second window passes.
    if status == "suspended" and dealer.get("suspended_reason") == INACTIVITY_REASON:
        if dealer.get("plan_tier") not in DELETE_ELIGIBLE_TIERS:
            return "skip"  # never auto-delete a paid dealer
        since = _days_between(dealer.get("deactivated_at"), now)
        if since is not None and since >= DELETE_AFTER_DEACTIVATED_DAYS:
            return "delete"
        return "ok"

    # In-use dealer -> deactivate once the first window passes.
    if status in ACTIVE_STATUSES:
        if inactive_days is not None and inactive_days >= INACTIVITY_DEACTIVATE_DAYS:
            return "deactivate"
        return "ok"

    # Leads/demos/trials/other suspensions: not this sweep's job.
    return "skip"


def sweep(now=None):
    """Apply the inactivity rules across all dealers. Returns what changed. Idempotent -- safe to run
    as often as the Hub likes (daily is plenty)."""
    now = now or utcnow()
    deactivated, deleted = [], []

    for dealer in list(_store.all()):
        verdict = evaluate_dealer(dealer, now)
        if verdict == "deactivate":
            dealer["status"] = "suspended"
            dealer["suspended_reason"] = INACTIVITY_REASON
            dealer["deactivated_at"] = now.isoformat()
            # For transparency: when it will be deleted if still untouched.
            from datetime import timedelta
            dealer["scheduled_deletion_at"] = (now + timedelta(days=DELETE_AFTER_DEACTIVATED_DAYS)).isoformat()
            _store.save(dealer)
            deactivated.append(dealer["dealer_id"])
        elif verdict == "delete":
            _store.delete(dealer["dealer_id"])
            deleted.append(dealer["dealer_id"])

    return {
        "swept_at": now.isoformat(),
        "deactivated": deactivated,
        "deleted": deleted,
        "deactivated_count": len(deactivated),
        "deleted_count": len(deleted),
    }


def lifecycle_status(dealer_id, now=None):
    """A human-facing read for one dealer: where it stands and the days until the next transition.
    Powers a 'your free instance is inactive' banner or the Hub's dealer record."""
    now = now or utcnow()
    dealer = _store.get(dealer_id)
    if not dealer:
        return {"error": f"No dealer '{dealer_id}'."}

    inactive_days = _days_between(dealer.get("last_activity_at"), now)
    verdict = evaluate_dealer(dealer, now)
    out = {
        "dealer_id": dealer_id,
        "status": dealer.get("status"),
        "suspended_reason": dealer.get("suspended_reason"),
        "inactive_days": None if inactive_days is None else round(inactive_days, 1),
        "next": None,
    }
    if dealer.get("status") in ACTIVE_STATUSES and inactive_days is not None:
        out["days_until_deactivation"] = max(0, round(INACTIVITY_DEACTIVATE_DAYS - inactive_days, 1))
        out["next"] = "deactivation"
    elif dealer.get("suspended_reason") == INACTIVITY_REASON:
        since = _days_between(dealer.get("deactivated_at"), now)
        out["days_until_deletion"] = None if since is None else max(0, round(DELETE_AFTER_DEACTIVATED_DAYS - since, 1))
        out["scheduled_deletion_at"] = dealer.get("scheduled_deletion_at")
        out["next"] = "deletion (unless re-logged in)"
    return out
