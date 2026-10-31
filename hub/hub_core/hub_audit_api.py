"""
NXTDeal Hub -- thin functions between hub/app.py's route handlers and
hub_core/hub_audit.py, matching backend/core/*_api.py's "validate + call the
real function + shape the response" convention.
"""

from hub_core.dealer_registry import registry as dealer_registry
from hub_core.hub_audit import hub_audit_log, CATEGORY_LABELS
from hub_core.hub_audit_storage import save_hub_audit_log

HUB_AUDIT_LOG_PATH = "storage/hub_audit.json"


def record_and_save(event_type, summary, dealer_id=None, actor="nxtdeal_staff", details=None):
    """The one real place every retrofitted mutation across slices 1-5 calls
    to log a Hub audit event -- centralized here (rather than each *_api.py
    module calling hub_audit_log.record() + save_hub_audit_log() separately)
    specifically so persistence can never be forgotten at a call site, the
    exact bug class CLAUDE.md's own missing-save_graph() audit documented
    happening ~19 times across the tenant codebase."""

    event = hub_audit_log.record(
        event_type=event_type,
        summary=summary,
        dealer_id=dealer_id,
        actor=actor,
        details=details,
    )
    save_hub_audit_log(HUB_AUDIT_LOG_PATH)
    return event


def get_audit_catalog_api():
    return {
        "categories": [
            {"key": key, "label": label} for key, label in CATEGORY_LABELS.items()
        ],
    }


def list_audit_events_api(dealer_id=None, category=None, event_type=None, limit=200):

    events = hub_audit_log.get_all()

    if dealer_id:
        events = [e for e in events if e.dealer_id == dealer_id]

    if event_type:
        events = [e for e in events if e.event_type == event_type]

    events = sorted(events, key=lambda e: e.timestamp, reverse=True)

    events_dicts = [e.to_dict() for e in events]

    if category:
        events_dicts = [e for e in events_dicts if e["category"] == category]

    total_matches = len(events_dicts)
    events_dicts = events_dicts[:limit]

    by_category = {}
    for e in hub_audit_log.get_all():
        cat = e.to_dict()["category"]
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "events": events_dicts,
        "total_matches": total_matches,
        "total_events": len(hub_audit_log.get_all()),
        "by_category": by_category,
        "filters_applied": {
            "dealer_id": dealer_id,
            "category": category,
            "event_type": event_type,
        },
    }


def get_dealer_audit_summary_api(dealer_id):

    dealer = dealer_registry.get(dealer_id)
    if not dealer:
        return {"error": f"no dealer with id '{dealer_id}'"}

    events = sorted(
        hub_audit_log.get_for_dealer(dealer_id),
        key=lambda e: e.timestamp,
        reverse=True,
    )

    by_category = {}
    for e in events:
        cat = e.to_dict()["category"]
        by_category[cat] = by_category.get(cat, 0) + 1

    return {
        "dealer_id": dealer_id,
        "dealer_name": dealer.name,
        "event_count": len(events),
        "by_category": by_category,
        "recent_events": [e.to_dict() for e in events[:50]],
    }
