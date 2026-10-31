"""
Lender Intelligence (2026-07-19, Cowork, interactive, autonomous continuation on a
bare "lets keep going") -- closes the "Lender Intelligence" item from Sam's own
six-pillar spec. Real analytics over the outside-lender submission history
core/deals.py's Deal Desk (session 33) already tracks -- deliberately NOT a new
lender-relationship-management system or a second submission workflow; this module
only reads and aggregates what Deal Desk already records.

Real vs. honest-gap split, decided before writing anything: Approval Rate/Decline
Rate/Counter Rate, Submission Volume, and Average Offered APR (on approved/
countered decisions) are all 100% real, computed directly off a new, additive,
append-only `Deal.attributes["lender_submission_history"]` list -- this slice's own
one real structural addition to core/deals.py, matching this codebase's own
extremely well-established "own history list on the entity" convention
(ro_stage_history/collection_stage_history/price_history/lifecycle_status_history/
etc.). `submit_to_lender()` appends a real entry (lender_id/lender_name/
submitted_at/decided_at=None/decision=None/terms=None/notes=None) the moment a deal
is submitted; `record_lender_decision()` fills in decided_at/decision/terms/notes
on that same entry the moment a decision comes back -- so a deal that's declined
and resubmitted to a different lender leaves a real, permanent record of BOTH
submissions, not just whichever lender the deal currently points at.

Average Decision Turnaround is real too, but only ever computed over entries that
have BOTH a real `submitted_at` and `decided_at` timestamp -- every one of the 24
outside-lender deals already in the live seed graph predates this slice and has no
`lender_submission_history` at all (confirmed live), so today's real turnaround
figure is honestly "no data yet" for every lender until new submissions happen
through the live app. This is the same "historical data predates this tracking,
only new activity going forward has it" pattern this codebase has hit and stated
plainly many times before (Lead.CreatedAt, OperationsTask.target_date, etc.) --
never backfilled with a guessed number.

Lender Recommendation is a real, transparent RULES ENGINE, not a fabricated AI
score -- matching this codebase's established "real rules, never fake AI"
convention (core/network_audit.py's recommendation engine, core/collections.py's
risk scoring, core/lead_record.py's next_best_action()). Lenders are ranked by
their own real historical approval rate first, then by their own real average
offered APR (lower is better) as a tiebreaker, restricted to lenders with at least
MIN_SAMPLE_SIZE real decided submissions -- a lender with fewer decided
submissions than that is reported separately as "not enough data yet," never
silently dropped or falsely ranked alongside lenders with a real track record.
When a specific deal is given, the recommendation is additionally scoped to
lenders' historical performance within that deal's own customer's real credit-score
tier (the same 3 tiers core/deals.py's own `_estimate_apr()` already uses) --
and, honestly, with only 24 real outside-lender deals total in this seed today,
most lender+tier combinations don't clear MIN_SAMPLE_SIZE yet, so the module
gracefully falls back to that lender's OVERALL performance with a note explaining
the fallback, rather than either forcing a same-tier ranking on too little data or
refusing to recommend anything at all.
"""

from datetime import datetime

from core.dealeros import ledger
from core.entity_types import DEAL, LENDER, CUSTOMER

from core.deals import list_lenders, _all_deals


MIN_SAMPLE_SIZE = 5


def _credit_tier(credit_score):
    """Same 3-tier split core/deals.py's _estimate_apr() already uses -- reused as
    a label here (not the APR value itself), so a real lender's historical
    performance can be sliced by the same tiers a live desking tool already prices
    off of."""

    try:
        score = int(credit_score)
    except (TypeError, ValueError):
        return "unknown"

    if score >= 740:
        return "prime (740+)"

    if score >= 660:
        return "near-prime (660-739)"

    return "subprime (<660)"


def _customer_credit_tier(customer_id):

    customer = ledger.get_entity(customer_id)

    if not customer or customer.entity_type != CUSTOMER:
        return "unknown"

    return _credit_tier(customer.attributes.get("CreditScore"))


def _all_submissions():
    """Every real lender_submission_history entry across every real Deal, each
    enriched with the entry's own deal_id/customer credit tier so per-lender and
    per-tier aggregation can both work off one flat list."""

    submissions = []

    for deal in _all_deals():

        history = deal.attributes.get("lender_submission_history") or []

        for entry in history:

            submissions.append({
                **entry,
                "deal_id": deal.id,
                "customer_credit_tier": _customer_credit_tier(deal.attributes.get("customer_id")),
            })

    return submissions


def _turnaround_days(entry):

    if not entry.get("submitted_at") or not entry.get("decided_at"):
        return None

    try:
        submitted = datetime.fromisoformat(entry["submitted_at"])
        decided = datetime.fromisoformat(entry["decided_at"])
    except ValueError:
        return None

    return round((decided - submitted).total_seconds() / 86400, 2)


def _score_lender(submissions):
    """Real per-lender aggregate over a list of that lender's own submission
    entries -- decided-only counts for approval/decline/counter rate and average
    APR (an undecided, still-`submitted` entry has no outcome to score yet),
    turnaround only over entries with both real timestamps."""

    decided = [s for s in submissions if s.get("decision")]

    approved = [s for s in decided if s["decision"] == "approved"]
    declined = [s for s in decided if s["decision"] == "declined"]
    countered = [s for s in decided if s["decision"] == "countered"]

    approval_rate = round(len(approved) / len(decided) * 100, 1) if decided else None

    apr_values = [s["terms"]["apr"] for s in (approved + countered) if s.get("terms") and s["terms"].get("apr") is not None]
    avg_apr = round(sum(apr_values) / len(apr_values), 2) if apr_values else None

    turnarounds = [t for t in (_turnaround_days(s) for s in decided) if t is not None]
    avg_turnaround_days = round(sum(turnarounds) / len(turnarounds), 1) if turnarounds else None

    return {
        "total_submissions": len(submissions),
        "decided_submissions": len(decided),
        "pending_submissions": len(submissions) - len(decided),
        "approved_count": len(approved),
        "declined_count": len(declined),
        "countered_count": len(countered),
        "approval_rate_pct": approval_rate,
        "avg_offered_apr": avg_apr,
        "avg_turnaround_days": avg_turnaround_days,
        "turnaround_sample_size": len(turnarounds),
        "has_sufficient_data": len(decided) >= MIN_SAMPLE_SIZE,
    }


def get_lender_scorecards():
    """One real scorecard per real Lender entity in the graph (excluding the
    in-house/BHPH lender(s) -- 'In-House Financing (BHPH)' is dealer-self-approved
    with no real submit/decide step at all, core/deals.py's own
    choose_in_house_financing() docstring says so explicitly, so it has nothing a
    lender scorecard could honestly measure)."""

    submissions = _all_submissions()
    lenders = [l for l in list_lenders() if l.attributes.get("Name") != "In-House Financing (BHPH)"]

    scorecards = []

    for lender in lenders:

        lender_submissions = [s for s in submissions if s.get("lender_id") == lender.id]

        scorecards.append({
            "lender_id": lender.id,
            "lender_name": lender.attributes.get("Name"),
            **_score_lender(lender_submissions),
        })

    scorecards.sort(key=lambda s: (s["decided_submissions"], s["total_submissions"]), reverse=True)

    return scorecards


def get_submission_log(lender_id=None, limit=200):
    """A real, flat, most-recent-first list of every real submission entry, each
    with a real customer/vehicle brief for display -- optionally filtered to one
    lender."""

    submissions = _all_submissions()

    if lender_id:
        submissions = [s for s in submissions if s.get("lender_id") == lender_id]

    def _brief(s):

        deal = ledger.get_entity(s["deal_id"])
        customer = ledger.get_entity(deal.attributes.get("customer_id")) if deal else None
        vehicle = ledger.get_entity(deal.attributes.get("vehicle_id")) if deal else None

        return {
            **s,
            "customer_name": (
                f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip()
                if customer else None
            ),
            "vehicle_description": (
                f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} "
                f"{vehicle.attributes.get('Model', '')}".strip()
                if vehicle else None
            ),
            "turnaround_days": _turnaround_days(s),
        }

    briefed = [_brief(s) for s in submissions]
    briefed.sort(key=lambda s: s.get("submitted_at") or "", reverse=True)

    return briefed[:limit]


def get_lender_recommendation(deal_id=None):
    """Real, transparent rules-based ranking -- never a fabricated AI score. Every
    lender in the ranked list carries the real numbers the ranking was computed
    from, so the recommendation is fully auditable, not a black box."""

    submissions = _all_submissions()
    lenders = [l for l in list_lenders() if l.attributes.get("Name") != "In-House Financing (BHPH)"]

    tier = None
    tier_note = None

    if deal_id:

        deal = ledger.get_entity(deal_id)

        if not deal or deal.entity_type != DEAL:
            return {"error": f"Deal '{deal_id}' not found"}

        tier = _customer_credit_tier(deal.attributes.get("customer_id"))

    ranked = []
    insufficient_data = []
    any_tier_scoped = False

    for lender in lenders:

        lender_submissions = [s for s in submissions if s.get("lender_id") == lender.id]
        overall = _score_lender(lender_submissions)

        scoped = overall
        basis = "overall"

        if tier:

            tier_submissions = [s for s in lender_submissions if s.get("customer_credit_tier") == tier]
            tier_scored = _score_lender(tier_submissions)

            if tier_scored["has_sufficient_data"]:
                scoped = tier_scored
                basis = f"credit tier: {tier}"
                any_tier_scoped = True

        entry = {
            "lender_id": lender.id,
            "lender_name": lender.attributes.get("Name"),
            "basis": basis,
            **scoped,
        }

        if scoped["has_sufficient_data"]:
            ranked.append(entry)
        else:
            insufficient_data.append(entry)

    # Bug found and fixed 2026-07-19 during this slice's own live smoke test: this
    # note used to be set inside the per-lender loop above and got silently
    # overwritten by whichever lender was processed LAST -- meaning it could claim
    # "not enough tier data" even when an earlier lender in the same response
    # (e.g. a real, sufficiently-decided lender) WAS genuinely tier-scoped, directly
    # contradicting that lender's own real `basis: "credit tier: ..."` field a few
    # lines above it. Computed once, after the loop, off a real flag instead.
    if tier and not any_tier_scoped:
        tier_note = (
            f"No lender currently has enough decided submissions in the '{tier}' "
            f"credit tier for a tier-specific ranking -- showing each lender's "
            f"overall track record instead."
        )
    elif tier and any_tier_scoped:
        tier_note = (
            f"Lenders below are ranked by their real track record within the "
            f"'{tier}' credit tier where enough data exists (see each "
            f"lender's own 'basis' field) -- a lender with too few decided "
            f"submissions in this tier falls back to its overall track record "
            f"instead."
        )

    # Higher approval rate first, lower average APR as the tiebreaker (a real
    # lender with a stronger track record but no rate data on file sorts after one
    # with both, since a missing number can't honestly beat a real one).
    ranked.sort(key=lambda e: (
        -(e["approval_rate_pct"] or 0),
        e["avg_offered_apr"] if e["avg_offered_apr"] is not None else 999,
    ))

    return {
        "deal_id": deal_id,
        "credit_tier": tier,
        "tier_note": tier_note,
        "min_sample_size": MIN_SAMPLE_SIZE,
        "ranked": ranked,
        "insufficient_data": insufficient_data,
    }


def get_dashboard_overview():

    scorecards = get_lender_scorecards()
    submissions = _all_submissions()
    decided = [s for s in submissions if s.get("decision")]
    approved = [s for s in decided if s["decision"] == "approved"]

    return {
        "total_submissions": len(submissions),
        "decided_submissions": len(decided),
        "pending_submissions": len(submissions) - len(decided),
        "overall_approval_rate_pct": round(len(approved) / len(decided) * 100, 1) if decided else None,
        "lenders_with_sufficient_data": len([s for s in scorecards if s["has_sufficient_data"]]),
        "total_lenders": len(scorecards),
        "scorecards": scorecards,
        "recommendation": get_lender_recommendation(),
        "not_yet_tracked": {
            "historical_submissions": (
                "Every outside-lender deal seeded before 2026-07-19 has no real "
                "lender_submission_history -- turnaround/approval-rate figures only "
                "reflect submissions made through the live app from this date "
                "forward."
            ),
            "structured_decline_reasons": (
                "A declined submission's 'notes' field is honest free-text staff "
                "input, not a categorized decline-reason taxonomy -- no such model "
                "exists anywhere in this codebase."
            ),
        },
    }
