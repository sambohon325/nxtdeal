"""
NXTDeal Hub -- Infrastructure & Platform Operations rebuild, slice 3 of 4:
AI Infrastructure.

Sam's ask: "AI INFRASTRUCTURE -- new tab. Models: Sales Advisor/Service
Advisor/Marketing Advisor/20 Group Advisor. Track: Usage/Response Time/
Accuracy/Cost. Training Jobs: Running/Queued/Failed."

REUSES, does not duplicate: this module builds ZERO new tenant-side data
collection. It composes hub/hub_core/dealer_ai_management.py's ALREADY-REAL,
already-fetched per-dealer AI snapshots (backend/core/ai_management.py's
13-feature AI_FEATURE_CATALOG + real in-memory call-attempt counters, pulled
via the already-shipped GET /network/ai-management-snapshot tenant route,
Dealer Management rebuild slice 4) into a Hub-WIDE view -- this is the same
underlying data hub/hub_core/dealer_ai_management.py already shows per-dealer,
re-sliced across every dealer at once and re-grouped into Sam's own 4 named
"Models" for THIS screen.

MODEL MAPPING -- Sam's 4 named models here (Sales Advisor/Service Advisor/
Marketing Advisor/20 Group Advisor) are a DIFFERENT grouping than Dealer
Management's own 5 named areas (Sales AI/Service AI/Finance AI/Marketing AI/
Collections AI) -- no Finance/Collections here, but a new "20 Group Advisor"
that ties directly to this whole rebuild's own "24/7 AI 20 Group" framing for
the Network department (backend/core/network_advisors.py's 5 real
department-specific Q&A advisors + the Network/Readiness Executive Summary
polish wizards). Rather than re-deriving a second raw feature-key mapping
from scratch, this module REUSES dealer_ai_management.AI_AREA_CATALOG's own
already-reasoned-through feature lists directly for the 3 models that carry
over unchanged (Sales/Service/Marketing), and only defines ONE genuinely new
grouping here (20 Group Advisor), pulled out of that same module's existing
"other_ai" catch-all. A 5th "Platform-Wide / Other AI" bucket holds the 3
remaining other_ai features NOT claimed by 20 Group Advisor (help_assistant,
workspace_explain, readiness_executive_summary) so every one of the 13 real
AI_FEATURE_CATALOG entries is still accounted for somewhere on this screen,
even though Sam's own named list is only 4 items -- confirmed by direct
count: 1 (sales) + 0 (service) + 6 (marketing) + 3 (20 group) + 3
(platform-wide) = 13. Finance AI / Collections AI are NOT reproduced as
separate model cards here (both are real, honest zero-feature areas already
covered by Dealer Management's own per-dealer AI Management screen) -- Sam's
own spec for THIS screen doesn't name them, and inventing two permanently-
empty model cards here would add noise without adding a real signal this
screen doesn't already have via "Platform-Wide / Other AI"'s own honest
non-inclusion.

USAGE: the real 'attempted' counter, same honest proxy dealer_ai_management.py
already established -- summed across every dealer that has ever been
checked.

RESPONSE TIME -- CONFIRMED GAP, not "coming soon." A direct grep of
backend/core/ai_management.py (its _stats_for()/record_call_attempt()) found
exactly 4 real counters per feature (attempted/succeeded/fell_back/blocked)
plus last_outcome/last_at/last_detail -- no duration, latency, or timing
field of any kind is captured anywhere for an AI call in this codebase. No
number is fabricated in its place.

ACCURACY -- CONFIRMED GAP. No accuracy/quality-scoring mechanism exists
anywhere in this codebase for any AI-backed feature (every one either
succeeds, falls back to a template, or is blocked by its kill switch -- none
of those three outcomes says anything about whether the OUTPUT was
"accurate"). Stated plainly, not guessed at.

COST / TOKENS -- CONFIRMED GAP, same finding hub/hub_core/dealer_ai_management.py
already made and disclosed via its own _CONSUMPTION_NOTE: no token count or
dollar cost is tracked anywhere in this codebase. Not re-litigated here,
restated for this screen's own context.

TRAINING JOBS (Running/Queued/Failed) -- CONFIRMED STRUCTURAL GAP, not a
"coming soon" placeholder. A full grep across backend/core/*.py for
"fine-tun"/"training_job"/"model_train"/"TrainingJob"/"accuracy_score"
returned zero matches. Every one of the 13 real AI-backed features in this
codebase is INFERENCE-ONLY against the hosted OpenAI API -- there is no
custom model, no fine-tuning pipeline, and therefore structurally no such
thing as a "training job" anywhere in this system today. This is stated as a
fact about the architecture, not a missing feature waiting to be built next.
"""

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.dealer_ai_management import (
    registry as dealer_ai_registry,
    AI_AREA_CATALOG as _DEALER_AI_AREA_CATALOG,
)


_AREA_FEATURE_KEYS = {key: feature_keys for key, _, feature_keys in _DEALER_AI_AREA_CATALOG}

_TWENTY_GROUP_FEATURE_KEYS = [
    "network_advisors", "network_executive_summary", "ai_business_analyst",
]

_PLATFORM_WIDE_FEATURE_KEYS = [
    key for key in _AREA_FEATURE_KEYS.get("other_ai", [])
    if key not in _TWENTY_GROUP_FEATURE_KEYS
]

MODEL_CATALOG = [
    {
        "key": "sales_advisor",
        "label": "Sales Advisor",
        "feature_keys": list(_AREA_FEATURE_KEYS.get("sales_ai", [])),
        "reasoning": (
            "Reuses hub/hub_core/dealer_ai_management.py's own 'sales_ai' area "
            "verbatim -- the main tool-calling Workspace Chat assistant "
            "(ai_assistant), heavily used on Sales screens."
        ),
    },
    {
        "key": "service_advisor",
        "label": "Service Advisor",
        "feature_keys": list(_AREA_FEATURE_KEYS.get("service_ai", [])),
        "reasoning": (
            "Reuses hub/hub_core/dealer_ai_management.py's own 'service_ai' "
            "area verbatim -- a real, confirmed zero-feature area. No "
            "AI-backed feature exists anywhere in the tenant codebase for "
            "Service today."
        ),
    },
    {
        "key": "marketing_advisor",
        "label": "Marketing Advisor",
        "feature_keys": list(_AREA_FEATURE_KEYS.get("marketing_ai", [])),
        "reasoning": (
            "Reuses hub/hub_core/dealer_ai_management.py's own 'marketing_ai' "
            "area verbatim -- the Email/SMS/Website/Social Caption/"
            "Reputation/Website-Chat-Receptionist/Advertising wizards, "
            "where most of this codebase's real AI capability lives."
        ),
    },
    {
        "key": "twenty_group_advisor",
        "label": "20 Group Advisor",
        "feature_keys": list(_TWENTY_GROUP_FEATURE_KEYS),
        "reasoning": (
            "NEW grouping, not carried over from Dealer Management's own "
            "area catalog -- pulled out of that module's 'other_ai' "
            "catch-all specifically because it ties directly to this whole "
            "NXTDeal Hub rebuild's own '24/7 AI 20 Group' framing for the "
            "Network department: the 5 real department-specific Network AI "
            "Advisors (backend/core/network_advisors.py) plus the Network "
            "and Readiness Executive Summary polish wizards -- the "
            "peer-benchmark / cross-dealer intelligence side of this "
            "codebase's AI capability, distinct from any one department's "
            "own workflow assistant."
        ),
    },
    {
        "key": "platform_wide_ai",
        "label": "Platform-Wide / Other AI",
        "feature_keys": list(_PLATFORM_WIDE_FEATURE_KEYS),
        "reasoning": (
            "Not one of Sam's 4 named models -- an honest catch-all so "
            "every one of the 13 real AI_FEATURE_CATALOG entries is still "
            "accounted for somewhere on this screen (the Help Widget, "
            "Workspace Chart Explanations, and Readiness Executive Summary "
            "polish, none of which is department-specific enough to belong "
            "to one of the 4 named models above)."
        ),
    },
]

RESPONSE_TIME_GAP_NOTE = (
    "CONFIRMED GAP: no duration/latency field is captured anywhere for an "
    "AI call in this codebase (backend/core/ai_management.py's own "
    "record_call_attempt() tracks exactly 4 counters -- attempted/"
    "succeeded/fell_back/blocked -- plus a last_outcome/last_at/last_detail "
    "string, never a timing value). Not fabricated in its place."
)

ACCURACY_GAP_NOTE = (
    "CONFIRMED GAP: no accuracy/quality-scoring mechanism exists anywhere "
    "in this codebase for any AI-backed feature -- an outcome is only ever "
    "'succeeded' (a real OpenAI response was returned), 'fell_back' (the "
    "template fallback ran instead), or 'blocked' (the feature's own kill "
    "switch was off). None of those three says anything about whether the "
    "output itself was accurate."
)

COST_GAP_NOTE = (
    "CONFIRMED GAP, same finding hub/hub_core/dealer_ai_management.py already "
    "made for the per-dealer AI Management screen: no token count or "
    "dollar cost is tracked anywhere in this codebase. 'Usage (attempted)' "
    "below is the closest real proxy to a prompt count -- a real, "
    "in-memory, per-tenant-process call-attempt counter, not a literal "
    "prompt/token log."
)

TRAINING_JOBS_NOTE = (
    "CONFIRMED STRUCTURAL GAP, not a 'coming soon' placeholder: a full "
    "grep across backend/core/*.py for fine-tun*/training_job/model_train/"
    "TrainingJob/accuracy_score returned zero matches. Every real AI-backed "
    "feature in this codebase is INFERENCE-ONLY against the hosted OpenAI "
    "API -- there is no custom model and no fine-tuning pipeline anywhere "
    "in this system, so 'Running/Queued/Failed' training-job states do not "
    "apply to how this platform actually works today."
)


def list_model_catalog():
    return [
        {
            "key": m["key"],
            "label": m["label"],
            "feature_keys": m["feature_keys"],
            "reasoning": m["reasoning"],
        }
        for m in MODEL_CATALOG
    ]


def _model_breakdown(features):

    by_key = {f["key"]: f for f in features}

    breakdown = []
    for model in MODEL_CATALOG:
        mapped = [by_key[k] for k in model["feature_keys"] if k in by_key]
        breakdown.append({
            "key": model["key"],
            "label": model["label"],
            "feature_count": len(model["feature_keys"]),
            "mapped_feature_count": len(mapped),
            "enabled_count": len([f for f in mapped if f["enabled"]]),
            "usage_attempted": sum(f["attempted"] for f in mapped),
            "usage_succeeded": sum(f["succeeded"] for f in mapped),
            "usage_fell_back": sum(f["fell_back"] for f in mapped),
            "usage_blocked": sum(f["blocked"] for f in mapped),
            "features": mapped,
            "gap_note": (
                None if model["feature_keys"] else
                f"No real AI-backed feature exists anywhere in the tenant "
                f"codebase for {model['label']} yet -- an honest gap."
            ),
        })

    return breakdown


def get_ai_infrastructure_overview():
    """Hub-wide aggregate over every dealer's LAST-KNOWN AI snapshot (see
    hub/hub_core/dealer_ai_management.py -- fetched on demand via Recheck, never
    automatically on every page view). A dealer that has never been checked
    contributes zero usage, honestly, rather than being silently skipped
    from the dealer counts."""

    dealers = dealer_registry.list_all()
    snapshots = dealer_ai_registry.list_all()
    snapshots_by_dealer = {s.dealer_id: s for s in snapshots}

    aggregate_by_key = {m["key"]: {
        "usage_attempted": 0, "usage_succeeded": 0, "usage_fell_back": 0,
        "usage_blocked": 0, "enabled_count": 0,
    } for m in MODEL_CATALOG}

    per_dealer = []
    reachable_count = 0

    for dealer in dealers:

        snapshot = snapshots_by_dealer.get(dealer.dealer_id)

        if not snapshot:
            per_dealer.append({
                "dealer_id": dealer.dealer_id,
                "dealer_name": dealer.name,
                "checked": False,
                "reachable": False,
                "fetched_at": None,
                "fetch_error": None,
                "models": _model_breakdown([]),
            })
            continue

        breakdown = _model_breakdown(snapshot.features if snapshot.reachable else [])

        per_dealer.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "checked": True,
            "reachable": snapshot.reachable,
            "fetched_at": snapshot.fetched_at,
            "fetch_error": snapshot.error,
            "models": breakdown,
        })

        if snapshot.reachable:
            reachable_count += 1
            for entry in breakdown:
                agg = aggregate_by_key[entry["key"]]
                agg["usage_attempted"] += entry["usage_attempted"]
                agg["usage_succeeded"] += entry["usage_succeeded"]
                agg["usage_fell_back"] += entry["usage_fell_back"]
                agg["usage_blocked"] += entry["usage_blocked"]
                agg["enabled_count"] = max(agg["enabled_count"], entry["enabled_count"])

    models_summary = []
    for model in MODEL_CATALOG:
        agg = aggregate_by_key[model["key"]]
        models_summary.append({
            "key": model["key"],
            "label": model["label"],
            "reasoning": model["reasoning"],
            "feature_count": len(model["feature_keys"]),
            "gap_note": (
                None if model["feature_keys"] else
                f"No real AI-backed feature exists anywhere in the tenant "
                f"codebase for {model['label']} yet -- an honest gap."
            ),
            **agg,
        })

    return {
        "dealers_total": len(dealers),
        "dealers_checked": len(snapshots),
        "dealers_reachable": reachable_count,
        "models": models_summary,
        "per_dealer": per_dealer,
        "response_time_gap": RESPONSE_TIME_GAP_NOTE,
        "accuracy_gap": ACCURACY_GAP_NOTE,
        "cost_gap": COST_GAP_NOTE,
        "training_jobs": {
            "running": None,
            "queued": None,
            "failed": None,
            "applicable": False,
            "note": TRAINING_JOBS_NOTE,
        },
        "note": (
            "Real, aggregate, per-model usage counters composed from every "
            "dealer's LAST-KNOWN AI feature snapshot (hub/hub_core/"
            "dealer_ai_management.py) -- not live-refetched on every page "
            "load. Click Recheck (a dealer at a time, or Recheck All) to "
            "pull a fresh live snapshot. A dealer with 'checked: false' has "
            "never had its AI snapshot pulled yet."
        ),
    }


def recheck_all_dealer_ai_infrastructure():
    """Bulk live re-fetch across every registered dealer with a recorded
    api_base_url -- reuses hub/hub_core/dealer_ai_management_api.py's own
    already-real, already-persisting recheck function per dealer rather than
    a second fetch implementation. A dealer with no api_base_url on file is
    honestly skipped, not silently retried forever."""

    from hub_core.dealer_ai_management_api import recheck_dealer_ai_management_api

    results = []
    checked = 0
    skipped = 0

    for dealer in dealer_registry.list_all():

        if not dealer.api_base_url:
            skipped += 1
            results.append({
                "dealer_id": dealer.dealer_id,
                "dealer_name": dealer.name,
                "skipped": True,
                "reason": "no api_base_url on file -- not yet deployed / not yet recorded",
            })
            continue

        result = recheck_dealer_ai_management_api(dealer.dealer_id)
        checked += 1
        results.append({
            "dealer_id": dealer.dealer_id,
            "dealer_name": dealer.name,
            "skipped": False,
            "reachable": result.get("reachable"),
            "fetch_error": result.get("fetch_error"),
        })

    return {
        "checked": checked,
        "skipped": skipped,
        "results": results,
    }
