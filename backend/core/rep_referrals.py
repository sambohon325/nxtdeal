"""
MySales rep referral & reward program (2026-07-24, Sam: "a referral / reward system if they
get their dealership to schedule a demo with us, and if they get their dealership to
implement / convert to NXTDeal. We also need to have a referral code / reward system for
them to recruit other sales people onto the app").

Two reward tracks, one model:
  • Dealership growth — a rep refers their own store: reward when it books a NXTDeal demo,
    a bigger reward when it actually converts to NXTDeal.
  • Rep recruiting — every rep has a shareable code; when another salesperson joins MySales
    with it, the referrer is credited.

A rep has one RepReferralProfile (their stable, shareable code). Each referral event is a
Referral entity with a kind, a subject, a status flow, and an accrued reward. Rewards accrue
as a dollar value tied to a milestone; a referral only counts as EARNED once its status
reaches "rewarded" (a NXTDeal/admin step), everything before that is "pending". Nothing here
pays anyone — it tracks what's owed; payout runs through whatever finance process NXTDeal uses.

Scoping note: this lives in the dealer backend keyed by the signed-in rep (employee_id),
consistent with every other core module. If MySales later supports reps who aren't yet on a
NXTDeal store, the profiles/referrals would move to a central (Hub) store — see the handoff.
"""

import secrets
from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import REP_REFERRAL_PROFILE, REFERRAL
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.audit import audit_log


# What each milestone is worth (USD). Configurable — a real program would tune these.
REWARD_TIERS = {
    "dealership_demo": {"label": "Dealership booked a NXTDeal demo", "reward": 100.0},
    "dealership_conversion": {"label": "Dealership converted to NXTDeal", "reward": 1000.0},
    "rep_recruit": {"label": "Recruited a salesperson to MySales", "reward": 250.0},
}

# The status a referral of each kind can move through (rep submits the first, NXTDeal/admin
# advances the rest). "rewarded" is the terminal earned state; "declined" is terminal unpaid.
STATUS_FLOW = {
    "dealership_demo": ["submitted", "contacted", "demo_scheduled", "rewarded", "declined"],
    "dealership_conversion": ["submitted", "contacted", "demo_scheduled", "converted", "rewarded", "declined"],
    "rep_recruit": ["joined", "active", "rewarded", "declined"],
}

EARNED_STATUSES = {"rewarded"}
DECLINED_STATUSES = {"declined"}

# Unambiguous code alphabet (no 0/O/1/I) — codes get read aloud and typed.
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_CODE_LEN = 7


def _now():
    return datetime.now(timezone.utc).isoformat()


# =====================================================================================
# Rep profile + code
# =====================================================================================

def _all_profiles():
    return [e for e in ledger.get_all().values() if e.entity_type == REP_REFERRAL_PROFILE]


def _profile_for(employee_id):
    for e in _all_profiles():
        if e.attributes.get("employee_id") == employee_id:
            return e
    return None


def _generate_unique_code():
    existing = {e.attributes.get("code") for e in _all_profiles()}
    while True:
        code = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(_CODE_LEN))
        if code not in existing:
            return code


def get_or_create_profile(employee_id):
    if not employee_id:
        return None
    existing = _profile_for(employee_id)
    if existing:
        return existing
    entity = Entity(
        id=id_generator.generate("RPRO"),
        entity_type=REP_REFERRAL_PROFILE,
        attributes={
            "employee_id": employee_id,
            "code": _generate_unique_code(),
            "created_at": _now(),
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return entity


def find_profile_by_code(code):
    code = (code or "").strip().upper()
    if not code:
        return None
    for e in _all_profiles():
        if e.attributes.get("code") == code:
            return e
    return None


# =====================================================================================
# Referral events
# =====================================================================================

def _referral_brief(entity):
    a = entity.attributes
    kind = a.get("kind")
    tier = REWARD_TIERS.get(kind, {})
    status = a.get("status")
    return {
        "id": entity.id,
        "kind": kind,
        "label": tier.get("label", kind),
        "subject": a.get("subject"),
        "contact_name": a.get("contact_name"),
        "contact_email": a.get("contact_email"),
        "notes": a.get("notes"),
        "status": status,
        "reward": a.get("reward_value", tier.get("reward", 0.0)),
        "earned": status in EARNED_STATUSES,
        "declined": status in DECLINED_STATUSES,
        "created_at": a.get("created_at"),
        "updated_at": a.get("updated_at"),
        "history": a.get("history", []),
    }


def submit_dealership_referral(employee_id, kind, dealership_name,
                               contact_name=None, contact_email=None, notes=None):
    """A rep reports they're referring their dealership for a demo or a conversion."""
    if kind not in ("dealership_demo", "dealership_conversion"):
        return {"error": "Referral kind must be a dealership demo or conversion."}
    if not (dealership_name or "").strip():
        return {"error": "Enter the dealership's name."}
    get_or_create_profile(employee_id)
    tier = REWARD_TIERS[kind]
    entity = Entity(
        id=id_generator.generate("REFR"),
        entity_type=REFERRAL,
        attributes={
            "referrer_employee_id": employee_id,
            "kind": kind,
            "subject": dealership_name.strip(),
            "contact_name": contact_name,
            "contact_email": contact_email,
            "notes": notes,
            "status": "submitted",
            "reward_value": tier["reward"],
            "created_at": _now(),
            "updated_at": _now(),
            "history": [{"status": "submitted", "at": _now(), "by": employee_id}],
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="rep_referral_submitted",
        summary=f"{employee_id} referred {dealership_name} ({kind})",
        entity_id=entity.id, actor=employee_id,
        details={"kind": kind, "dealership": dealership_name.strip()},
    )
    return _referral_brief(entity)


def attribute_signup(new_employee_id, code):
    """Credit the owner of `code` for recruiting new_employee_id onto MySales. Called at rep
    sign-up (task #85) or directly by a newly-joined rep entering who referred them. Guards
    self-referral and a rep being credited more than once."""
    profile = find_profile_by_code(code)
    if profile is None:
        return {"error": "That referral code isn't valid."}
    referrer = profile.attributes.get("employee_id")
    if referrer == new_employee_id:
        return {"error": "You can't refer yourself."}
    # Already credited for this recruit?
    for e in ledger.get_all().values():
        if (e.entity_type == REFERRAL and e.attributes.get("kind") == "rep_recruit"
                and e.attributes.get("subject") == new_employee_id):
            return {"error": "This salesperson was already credited to a referrer."}
    tier = REWARD_TIERS["rep_recruit"]
    entity = Entity(
        id=id_generator.generate("REFR"),
        entity_type=REFERRAL,
        attributes={
            "referrer_employee_id": referrer,
            "kind": "rep_recruit",
            "subject": new_employee_id,
            "status": "joined",
            "reward_value": tier["reward"],
            "created_at": _now(),
            "updated_at": _now(),
            "history": [{"status": "joined", "at": _now(), "by": new_employee_id}],
        },
    )
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="rep_referral_recruit",
        summary=f"{new_employee_id} joined MySales via {referrer}'s referral code",
        entity_id=entity.id, actor=new_employee_id,
        details={"referrer": referrer},
    )
    return _referral_brief(entity)


def advance_referral(referral_id, status, actor):
    """NXTDeal/admin moves a referral along its flow. Setting it to 'rewarded' is what marks
    the reward earned."""
    entity = ledger.get_entity(referral_id)
    if entity is None or entity.entity_type != REFERRAL:
        return {"error": "Referral not found."}
    kind = entity.attributes.get("kind")
    allowed = STATUS_FLOW.get(kind, [])
    if status not in allowed:
        return {"error": f"'{status}' isn't a valid status for a {kind} referral."}
    entity.attributes["status"] = status
    entity.attributes["updated_at"] = _now()
    entity.attributes.setdefault("history", []).append({"status": status, "at": _now(), "by": actor})
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="rep_referral_advanced",
        summary=f"Referral {referral_id} → {status}",
        entity_id=referral_id, actor=actor,
        details={"status": status},
    )
    return _referral_brief(entity)


# =====================================================================================
# Read views
# =====================================================================================

def list_my_referrals(employee_id):
    return [
        _referral_brief(e)
        for e in ledger.get_all().values()
        if e.entity_type == REFERRAL and e.attributes.get("referrer_employee_id") == employee_id
    ]


def get_my_summary(employee_id):
    profile = get_or_create_profile(employee_id)
    referrals = sorted(list_my_referrals(employee_id), key=lambda r: r["created_at"], reverse=True)
    earned = sum(r["reward"] for r in referrals if r["earned"])
    pending = sum(r["reward"] for r in referrals if not r["earned"] and not r["declined"])
    return {
        "code": profile.attributes.get("code"),
        "tiers": REWARD_TIERS,
        "totals": {
            "earned": round(earned, 2),
            "pending": round(pending, 2),
            "recruits": sum(1 for r in referrals if r["kind"] == "rep_recruit"),
            "dealership_referrals": sum(1 for r in referrals if r["kind"].startswith("dealership")),
        },
        "referrals": referrals,
    }


def list_all(status=None):
    out = []
    for e in ledger.get_all().values():
        if e.entity_type != REFERRAL:
            continue
        if status and e.attributes.get("status") != status:
            continue
        out.append(_referral_brief(e))
    return sorted(out, key=lambda r: r["created_at"], reverse=True)
