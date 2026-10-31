"""
MySales adoption signal -- App Suite roadmap Phase 6 (2026-08-03). MySales is the free,
standalone salesperson app that delivers real day-to-day value to a rep whether or not their
dealership has adopted NXTDeal. That makes rep-level MySales usage a bottom-up growth
signal: a dealership where several reps are already leaning on MySales is a warm conversion
target for the sales/Readiness team.

This module tracks that usage and exposes it to Readiness. `record_activity` logs a rep's
MySales action (idempotently maintaining one MySalesAdoption record per rep with a running
count + last-active + per-action breakdown). `get_conversion_signals` aggregates by
dealership and flags the warm ones -- dealerships with active MySales reps that are NOT yet
on NXTDeal -- which is exactly the ready-made outreach list the roadmap describes.

Honest scope: `dealership_on_dealeros` is whatever the caller records (the app knows whether
it resolved a NXTDeal tenant); nothing is inferred or fabricated. A dealership with no
recorded rep usage simply doesn't appear.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import MYSALES_ADOPTION
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


def _now():
    return datetime.now(timezone.utc).isoformat()


def _find(rep_id):
    for e in ledger.get_all().values():
        if e.entity_type == MYSALES_ADOPTION and e.attributes.get("rep_id") == rep_id:
            return e
    return None


def record_activity(rep_id, dealership_id=None, action="open", dealership_on_dealeros=False, rep_name=None):
    """Log one MySales usage event for a rep. Maintains a single rolling record per rep."""
    if not rep_id:
        return {"error": "rep_id is required"}
    rec = _find(rep_id)
    if rec is None:
        rec = Entity(
            id=id_generator.generate("MSAD"),
            entity_type=MYSALES_ADOPTION,
            attributes={
                "rep_id": rep_id,
                "rep_name": rep_name,
                "dealership_id": dealership_id,
                "dealership_on_dealeros": bool(dealership_on_dealeros),
                "activity_count": 0,
                "actions": {},
                "first_active_at": _now(),
                "last_active_at": _now(),
            },
        )
        ledger.add_entity(rec)

    a = rec.attributes
    a["activity_count"] = a.get("activity_count", 0) + 1
    a["actions"][action] = a.get("actions", {}).get(action, 0) + 1
    a["last_active_at"] = _now()
    if dealership_id:
        a["dealership_id"] = dealership_id
    if rep_name:
        a["rep_name"] = rep_name
    a["dealership_on_dealeros"] = bool(dealership_on_dealeros)
    save_graph(GRAPH_PATH)
    return {"rep_id": rep_id, "activity_count": a["activity_count"], "dealership_id": a.get("dealership_id")}


def _all():
    return [e for e in ledger.get_all().values() if e.entity_type == MYSALES_ADOPTION]


def get_adoption_summary():
    reps = _all()
    total_reps = len(reps)
    total_activity = sum(r.attributes.get("activity_count", 0) for r in reps)
    on_dealeros = sum(1 for r in reps if r.attributes.get("dealership_on_dealeros"))
    return {
        "active_reps": total_reps,
        "total_activity": total_activity,
        "reps_on_dealeros_dealers": on_dealeros,
        "reps_on_non_dealeros_dealers": total_reps - on_dealeros,
    }


def get_conversion_signals(min_reps=1):
    """Readiness-facing: dealerships aggregated by MySales rep usage, flagging the WARM ones
    (active MySales reps at a dealership NOT yet on NXTDeal = a ready-made conversion
    outreach list). Sorted by rep count then activity."""
    by_dealer = {}
    for r in _all():
        a = r.attributes
        did = a.get("dealership_id") or "(unknown)"
        d = by_dealer.setdefault(did, {
            "dealership_id": did,
            "on_dealeros": bool(a.get("dealership_on_dealeros")),
            "rep_count": 0,
            "total_activity": 0,
            "reps": [],
        })
        d["rep_count"] += 1
        d["total_activity"] += a.get("activity_count", 0)
        d["reps"].append({"rep_id": a.get("rep_id"), "rep_name": a.get("rep_name"), "activity": a.get("activity_count", 0), "last_active_at": a.get("last_active_at")})
        # if any rep records the dealership as on NXTDeal, treat the dealership as on it
        d["on_dealeros"] = d["on_dealeros"] or bool(a.get("dealership_on_dealeros"))

    dealers = [d for d in by_dealer.values() if d["rep_count"] >= min_reps]
    warm = [d for d in dealers if not d["on_dealeros"]]
    warm.sort(key=lambda d: (d["rep_count"], d["total_activity"]), reverse=True)
    dealers.sort(key=lambda d: (d["rep_count"], d["total_activity"]), reverse=True)

    return {
        "dealers": dealers,
        "warm_conversion_targets": warm,
        "warm_count": len(warm),
        "note": (
            "Warm targets are dealerships with active MySales reps that are NOT yet on "
            "NXTDeal -- reps already showing product engagement (and, via the referral "
            "program, with a financial incentive to champion a conversion). This is a "
            "lead-generation signal for the growth team, not just an internal metric."
        ),
    }
