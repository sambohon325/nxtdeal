"""
core/dealeros_verify.py -- NXTDeal Verify: the identity-tier gate for Digital Retail
(2026-07-24). Sam's Digital Retail spec: "NXTDeal Verify... Required platform service.
Human Verification. Purpose: Prevent abuse and negotiation scraping." A visitor climbs a
ladder of trust, and each rung unlocks more of the self-service purchase journey:

    anonymous          -> browse inventory, vehicle research, FAQ            (no proof)
    verified_human     -> saved vehicles, trade estimates, pricing requests  (email + SMS)
    identity_verified  -> negotiation, deal creation, vehicle reservation    (license + selfie)
    credit_verified    -> final financing, contracting, delivery scheduling  (credit application)

This is a NEW, self-contained service -- there was no identity/verification model anywhere in
NXTDeal before this (the only prior art was demo_drive.py's manual, salesperson-set
`license_verified` flag). It follows the same conventions as the rest of the platform: one
Verification is an ordinary entity in the single ledger (prefix VERF), persisted with
save_graph; other modules gate customer-facing actions through `require_capability()`.

HONESTY POSTURE (the platform's "real data or an honest gap, never fabricate" convention):
this sandbox has no real email/SMS gateway, no DMV/AAMVA lookup, and no biometric face-match
provider. So the email/SMS one-time codes are REAL, unguessable codes with real expiry and
attempt limits -- but they are not actually delivered (a real deployment routes delivery
through NXTDeal Connect / a provider like Twilio; until then the code is returned to the
caller under `dev_code` and clearly labelled simulated). The license + selfie "match" is a
transparently SIMULATED check, not a real identity-document or biometric verification. Every
such spot is labelled with a disclaimer rather than pretending to be authoritative.
"""

import secrets
from datetime import datetime, timezone, timedelta

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import VERIFICATION, CUSTOMER, LEAD, CREDIT_APPLICATION
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# A customer acting through the Verify portal is recorded with this honest, distinct marker --
# never an employee id -- mirroring payments.CUSTOMER_SENTINEL.
CUSTOMER_SENTINEL = "customer_via_verify_portal"

# ------------------------------------------------------------------------------------
# The trust ladder.
# ------------------------------------------------------------------------------------

TIER_ANONYMOUS = "anonymous"
TIER_VERIFIED_HUMAN = "verified_human"
TIER_IDENTITY_VERIFIED = "identity_verified"
TIER_CREDIT_VERIFIED = "credit_verified"

# Ordered lowest -> highest. A tier's rank is its index.
TIER_ORDER = (TIER_ANONYMOUS, TIER_VERIFIED_HUMAN, TIER_IDENTITY_VERIFIED, TIER_CREDIT_VERIFIED)
TIER_RANK = {t: i for i, t in enumerate(TIER_ORDER)}

TIER_LABELS = {
    TIER_ANONYMOUS: "Anonymous Visitor",
    TIER_VERIFIED_HUMAN: "Verified Human",
    TIER_IDENTITY_VERIFIED: "Identity Verified",
    TIER_CREDIT_VERIFIED: "Credit Verified",
}

# The NEW capabilities unlocked AT each tier (cumulative -- a tier also grants every lower
# tier's capabilities). These strings are the contract other modules gate on.
TIER_CAPABILITIES = {
    TIER_ANONYMOUS: ("browse_inventory", "vehicle_research", "faq"),
    TIER_VERIFIED_HUMAN: ("save_vehicles", "trade_estimate", "pricing_request"),
    TIER_IDENTITY_VERIFIED: ("negotiate", "create_deal", "reserve_vehicle"),
    TIER_CREDIT_VERIFIED: ("final_financing", "contracting", "schedule_delivery"),
}


def capabilities_for_tier(tier):
    """Every capability a subject at `tier` has -- cumulative across this tier and all below."""
    rank = TIER_RANK.get(tier, 0)
    caps = []
    for t in TIER_ORDER:
        if TIER_RANK[t] <= rank:
            caps.extend(TIER_CAPABILITIES[t])
    return caps


# capability -> the minimum tier that unlocks it.
CAPABILITY_MIN_TIER = {
    cap: tier for tier in TIER_ORDER for cap in TIER_CAPABILITIES[tier]
}
ALL_CAPABILITIES = tuple(CAPABILITY_MIN_TIER.keys())

# ------------------------------------------------------------------------------------
# One-time codes + identity check -- honestly-labelled simulations (see module docstring).
# ------------------------------------------------------------------------------------

OTP_TTL_SECONDS = 600            # 10 minutes
OTP_MAX_ATTEMPTS = 5
_OTP_CHANNELS = ("email", "sms")

OTP_DISCLAIMER = (
    "The code is real (unguessable, expiring, attempt-limited) but is NOT actually delivered -- "
    "this sandbox has no email/SMS gateway. A real deployment routes delivery through NXTDeal "
    "Connect / a provider like Twilio; until then the code is returned as dev_code."
)
IDENTITY_DISCLAIMER = (
    "Driver-license + selfie 'match' is a transparently SIMULATED check -- no DMV/AAMVA document "
    "lookup and no biometric face-match provider is wired in this sandbox. A real deployment "
    "integrates an identity-verification provider before this tier should be trusted."
)


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


def _mask_email(email):
    if not email or "@" not in email:
        return email
    name, _, domain = email.partition("@")
    head = name[0] if name else ""
    return f"{head}{'*' * max(len(name) - 1, 1)}@{domain}"


def _mask_phone(phone):
    if not phone:
        return phone
    digits = "".join(c for c in str(phone) if c.isdigit())
    return f"***-***-{digits[-4:]}" if len(digits) >= 4 else "***"


# ------------------------------------------------------------------------------------
# Verification entities.
# ------------------------------------------------------------------------------------

def _find_by_token(token):
    if not token:
        return None
    for entity in ledger.get_all().values():
        if entity.entity_type == VERIFICATION and entity.attributes.get("session_token") == token:
            return entity
    return None


def _get(verf_id):
    entity = ledger.get_entity(verf_id)
    if not entity or entity.entity_type != VERIFICATION:
        return None
    return entity


def _record(entity, event, detail=None):
    entity.attributes["history"].append({"at": _iso(_now()), "event": event, "detail": detail})
    entity.attributes["updated_at"] = _iso(_now())


def start_verification(email=None, phone=None, linked_entity_id=None, created_by=CUSTOMER_SENTINEL):
    """Begin a verification session for a visitor. Everyone starts at `anonymous`. `email`/
    `phone` may be supplied up front (they can also be set later via set_contact). An optional
    `linked_entity_id` ties the session to a known Customer/Lead."""

    if linked_entity_id is not None:
        subject = ledger.get_entity(linked_entity_id)
        if not subject or subject.entity_type not in (CUSTOMER, LEAD):
            return {"error": f"'{linked_entity_id}' is not a Customer or Lead"}

    entity = Entity(
        id=id_generator.generate("VERF"),
        entity_type=VERIFICATION,
        attributes={
            "session_token": secrets.token_urlsafe(24),
            "tier": TIER_ANONYMOUS,
            "linked_entity_id": linked_entity_id,
            "email": email,
            "email_verified": False,
            "email_verified_at": None,
            "phone": phone,
            "phone_verified": False,
            "phone_verified_at": None,
            "identity": {
                "license_last4": None,
                "selfie_provided": False,
                "license_verified": False,
                "verified_at": None,
            },
            "credit": {
                "credit_app_id": None,
                "credit_decision": None,
                "credit_verified": False,
                "verified_at": None,
            },
            "challenges": {},          # channel -> active challenge dict
            "created_by": created_by,
            "created_at": _iso(_now()),
            "updated_at": _iso(_now()),
            "history": [],
        },
    )
    _record(entity, "started", {"created_by": created_by})
    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return {"verification": _view(entity)}


def set_contact(verf_id, email=None, phone=None):
    """Add or change the email / phone on a session. Changing a value that was already verified
    resets that channel's verified flag (and recomputes the tier down if needed)."""
    entity = _get(verf_id)
    if not entity:
        return {"error": f"No verification found with id {verf_id}"}
    a = entity.attributes
    if email is not None and email != a.get("email"):
        a["email"] = email
        a["email_verified"] = False
        a["email_verified_at"] = None
        a["challenges"].pop("email", None)
    if phone is not None and phone != a.get("phone"):
        a["phone"] = phone
        a["phone_verified"] = False
        a["phone_verified_at"] = None
        a["challenges"].pop("sms", None)
    _record(entity, "contact_updated")
    _recompute_tier(entity)
    save_graph(GRAPH_PATH)
    return {"verification": _view(entity)}


def link_subject(verf_id, entity_id):
    """Attach the session to a known Customer/Lead (e.g. once a Lead is created from it)."""
    entity = _get(verf_id)
    if not entity:
        return {"error": f"No verification found with id {verf_id}"}
    subject = ledger.get_entity(entity_id)
    if not subject or subject.entity_type not in (CUSTOMER, LEAD):
        return {"error": f"'{entity_id}' is not a Customer or Lead"}
    entity.attributes["linked_entity_id"] = entity_id
    _record(entity, "linked_subject", {"entity_id": entity_id})
    save_graph(GRAPH_PATH)
    return {"verification": _view(entity)}


# ------------------------------------------------------------------------------------
# Verified Human -- email + SMS one-time codes.
# ------------------------------------------------------------------------------------

def _request_code(entity, channel):
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("customer_verification")
    if blocked:
        return blocked
    a = entity.attributes
    contact = a.get("email") if channel == "email" else a.get("phone")
    if not contact:
        return {"error": f"No {channel} on file -- set one with set_contact first"}
    code = f"{secrets.randbelow(1000000):06d}"
    now = _now()
    a["challenges"][channel] = {
        "code": code,
        "created_at": _iso(now),
        "expires_at": _iso(now + timedelta(seconds=OTP_TTL_SECONDS)),
        "attempts": 0,
        "consumed": False,
    }
    _record(entity, f"{channel}_code_requested")
    save_graph(GRAPH_PATH)
    return {
        "channel": channel,
        "sent_to": _mask_email(contact) if channel == "email" else _mask_phone(contact),
        "expires_at": a["challenges"][channel]["expires_at"],
        "simulated": True,
        "dev_code": code,               # honest: real delivery is not wired -- see disclaimer
        "disclaimer": OTP_DISCLAIMER,
    }


def request_email_code(verf_id):
    entity = _get(verf_id)
    if not entity:
        return {"error": f"No verification found with id {verf_id}"}
    return _request_code(entity, "email")


def request_sms_code(verf_id):
    entity = _get(verf_id)
    if not entity:
        return {"error": f"No verification found with id {verf_id}"}
    return _request_code(entity, "sms")


def _confirm_code(entity, channel, code):
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("customer_verification")
    if blocked:
        return blocked
    a = entity.attributes
    challenge = a["challenges"].get(channel)
    if not challenge or challenge.get("consumed"):
        return {"error": f"No active {channel} code -- request one first"}
    if _now() > datetime.fromisoformat(challenge["expires_at"]):
        return {"error": f"That {channel} code has expired -- request a new one"}
    if challenge["attempts"] >= OTP_MAX_ATTEMPTS:
        return {"error": f"Too many attempts on this {channel} code -- request a new one"}
    challenge["attempts"] += 1
    if str(code).strip() != challenge["code"]:
        remaining = OTP_MAX_ATTEMPTS - challenge["attempts"]
        save_graph(GRAPH_PATH)
        return {"error": f"Incorrect code -- {remaining} attempt(s) left"}

    challenge["consumed"] = True
    if channel == "email":
        a["email_verified"] = True
        a["email_verified_at"] = _iso(_now())
    else:
        a["phone_verified"] = True
        a["phone_verified_at"] = _iso(_now())
    _record(entity, f"{channel}_verified")
    _recompute_tier(entity)
    save_graph(GRAPH_PATH)
    return {"verification": _view(entity)}


def confirm_email_code(verf_id, code):
    entity = _get(verf_id)
    if not entity:
        return {"error": f"No verification found with id {verf_id}"}
    return _confirm_code(entity, "email", code)


def confirm_sms_code(verf_id, code):
    entity = _get(verf_id)
    if not entity:
        return {"error": f"No verification found with id {verf_id}"}
    return _confirm_code(entity, "sms", code)


# ------------------------------------------------------------------------------------
# Identity Verified -- driver license + selfie (SIMULATED match, see disclaimer).
# ------------------------------------------------------------------------------------

def submit_identity(verf_id, license_number, selfie_provided=True):
    """Record a driver license + selfie and run the (simulated) identity match. Requires the
    subject to already be a Verified Human -- you can't prove identity before proving you're a
    reachable human. Both a license number and a selfie are required to pass."""
    entity = _get(verf_id)
    if not entity:
        return {"error": f"No verification found with id {verf_id}"}
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("customer_verification")
    if blocked:
        return blocked
    a = entity.attributes
    if not a.get("email_verified") or not a.get("phone_verified"):
        return {"error": "Must reach Verified Human (email + SMS) before identity verification"}
    lic = str(license_number or "").strip()
    if not lic:
        return {"error": "A driver license number is required"}
    if not selfie_provided:
        return {"error": "A selfie is required for identity verification"}

    a["identity"] = {
        "license_last4": lic[-4:],
        "selfie_provided": True,
        "license_verified": True,       # SIMULATED pass -- see IDENTITY_DISCLAIMER
        "verified_at": _iso(_now()),
        "basis": "simulated",
    }
    _record(entity, "identity_verified", {"basis": "simulated"})
    _recompute_tier(entity)
    save_graph(GRAPH_PATH)
    result = {"verification": _view(entity)}
    result["disclaimer"] = IDENTITY_DISCLAIMER
    return result


# ------------------------------------------------------------------------------------
# Credit Verified -- a completed (decisioned) credit application on file.
# ------------------------------------------------------------------------------------

def submit_credit_verification(verf_id, credit_app_id):
    """Attach a completed credit application. Requires Identity Verified first. The credit app
    must exist and have been decisioned (from core/credit_app.py). Reaching this tier unlocks
    final financing, contracting, and delivery scheduling -- it does NOT itself approve the
    loan; the deal's own financing decision still governs terms."""
    entity = _get(verf_id)
    if not entity:
        return {"error": f"No verification found with id {verf_id}"}
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("customer_verification")
    if blocked:
        return blocked
    a = entity.attributes
    if TIER_RANK[a["tier"]] < TIER_RANK[TIER_IDENTITY_VERIFIED]:
        return {"error": "Must reach Identity Verified before credit verification"}
    app = ledger.get_entity(credit_app_id)
    if not app or app.entity_type != CREDIT_APPLICATION:
        return {"error": f"'{credit_app_id}' is not a Credit Application"}
    if app.attributes.get("status") != "decisioned":
        return {"error": "That credit application has not been submitted/decisioned yet"}

    a["credit"] = {
        "credit_app_id": credit_app_id,
        "credit_decision": app.attributes.get("decision"),
        "credit_verified": True,
        "verified_at": _iso(_now()),
    }
    _record(entity, "credit_verified", {"credit_app_id": credit_app_id})
    _recompute_tier(entity)
    save_graph(GRAPH_PATH)
    return {"verification": _view(entity)}


# ------------------------------------------------------------------------------------
# Tier computation + capability gating (what other modules call).
# ------------------------------------------------------------------------------------

def _recompute_tier(entity):
    """Set the tier to the highest rung whose requirements are currently satisfied. Monotonic
    upward as proofs are added; recomputes DOWN if a proof is invalidated (e.g. email changed)."""
    a = entity.attributes
    tier = TIER_ANONYMOUS
    if a.get("email_verified") and a.get("phone_verified"):
        tier = TIER_VERIFIED_HUMAN
        if a.get("identity", {}).get("license_verified"):
            tier = TIER_IDENTITY_VERIFIED
            if a.get("credit", {}).get("credit_verified"):
                tier = TIER_CREDIT_VERIFIED
    if tier != a["tier"]:
        previous = a["tier"]
        a["tier"] = tier
        _record(entity, "tier_changed", {"from": previous, "to": tier})
        audit_log.record(
            event_type="verify_tier_changed",
            summary=f"Verification {entity.id} moved {previous} -> {tier}",
            entity_id=entity.id,
            actor=a.get("created_by") or CUSTOMER_SENTINEL,
            details={"from": previous, "to": tier},
        )
    return tier


def _effective_tier(entity):
    # Stored tiers predate this release gate and may have been produced by the
    # simulator. Never trust them for production access, including old tokens.
    from core.json_graph_repository import demo_persistence_disabled
    if not demo_persistence_disabled():
        return TIER_ANONYMOUS
    tier = entity.attributes.get("tier", TIER_ANONYMOUS)
    return tier if tier in TIER_RANK else TIER_ANONYMOUS


def _next_tier_requirements(entity):
    """Human-readable list of what's still needed to reach the next rung (or None at the top)."""
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("customer_verification")
    if blocked:
        return {"tier": TIER_VERIFIED_HUMAN, "label": TIER_LABELS[TIER_VERIFIED_HUMAN],
                "needs": [blocked["error"]], "available": False}
    a = entity.attributes
    rank = TIER_RANK[_effective_tier(entity)]
    if rank >= TIER_RANK[TIER_CREDIT_VERIFIED]:
        return None
    nxt = TIER_ORDER[rank + 1]
    needs = []
    if nxt == TIER_VERIFIED_HUMAN:
        if not a.get("email_verified"):
            needs.append("verify email")
        if not a.get("phone_verified"):
            needs.append("verify phone (SMS)")
    elif nxt == TIER_IDENTITY_VERIFIED:
        needs.append("submit driver license + selfie")
    elif nxt == TIER_CREDIT_VERIFIED:
        needs.append("complete a credit application")
    return {"tier": nxt, "label": TIER_LABELS[nxt], "needs": needs}


def can(verf_id_or_entity, capability):
    """True if this verification currently unlocks `capability`. Accepts an id or the entity."""
    entity = verf_id_or_entity if isinstance(verf_id_or_entity, Entity) else _get(verf_id_or_entity)
    if not entity:
        return False
    return capability in capabilities_for_tier(_effective_tier(entity))


def require_capability(verf_id, capability):
    """Gate for OTHER modules: returns (ok, error). error is a clear, customer-safe message
    naming the tier the capability requires. Unknown capability -> hard error (fail closed)."""
    entity = _get(verf_id)
    if not entity:
        return False, f"No verification found with id {verf_id}"
    if capability not in CAPABILITY_MIN_TIER:
        return False, f"Unknown capability '{capability}'"
    if can(entity, capability):
        return True, None
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("customer_verification")
    if blocked:
        return False, blocked["error"]
    need = CAPABILITY_MIN_TIER[capability]
    return False, (
        f"'{capability}' requires {TIER_LABELS[need]} verification "
        f"(current: {TIER_LABELS[_effective_tier(entity)]})"
    )


# ------------------------------------------------------------------------------------
# Views / listings / catalog.
# ------------------------------------------------------------------------------------

def _view(entity):
    a = entity.attributes
    tier = _effective_tier(entity)
    from core.json_graph_repository import demo_persistence_disabled
    sample = demo_persistence_disabled()
    return {
        "id": entity.id,
        "tier": tier,
        "tier_label": TIER_LABELS[tier],
        "tier_rank": TIER_RANK[tier],
        "linked_entity_id": a.get("linked_entity_id"),
        "email": _mask_email(a.get("email")),
        "email_verified": sample and a.get("email_verified", False),
        "phone": _mask_phone(a.get("phone")),
        "phone_verified": sample and a.get("phone_verified", False),
        "identity_verified": sample and a.get("identity", {}).get("license_verified", False),
        "license_last4": a.get("identity", {}).get("license_last4"),
        "credit_verified": sample and a.get("credit", {}).get("credit_verified", False),
        "verification_mode": "sample_only" if sample else "unavailable",
        "credit_app_id": a.get("credit", {}).get("credit_app_id"),
        "capabilities": capabilities_for_tier(tier),
        "next_tier": _next_tier_requirements(entity),
        "created_at": a.get("created_at"),
        "updated_at": a.get("updated_at"),
    }


def get_verification(verf_id):
    entity = _get(verf_id)
    return _view(entity) if entity else None


def get_verification_by_token(token):
    entity = _find_by_token(token)
    return _view(entity) if entity else None


def list_verifications(tier=None, linked_entity_id=None, limit=100):
    rows = []
    for entity in ledger.get_all().values():
        if entity.entity_type != VERIFICATION:
            continue
        a = entity.attributes
        if tier and _effective_tier(entity) != tier:
            continue
        if linked_entity_id and a.get("linked_entity_id") != linked_entity_id:
            continue
        rows.append(_view(entity))
    rows.sort(key=lambda r: r.get("updated_at") or "", reverse=True)
    return {"verifications": rows[:limit], "count": min(len(rows), limit), "total": len(rows)}


def verification_summary():
    by_tier = {t: 0 for t in TIER_ORDER}
    total = 0
    for entity in ledger.get_all().values():
        if entity.entity_type != VERIFICATION:
            continue
        total += 1
        by_tier[_effective_tier(entity)] += 1
    return {
        "total": total,
        "by_tier": by_tier,
        "verified_humans_or_above": total - by_tier[TIER_ANONYMOUS],
    }


def capability_catalog():
    """The full trust ladder for a UI: each tier, its label, requirement summary, and the
    capabilities it unlocks (cumulative)."""
    requirement = {
        TIER_ANONYMOUS: "None (any visitor)",
        TIER_VERIFIED_HUMAN: "Email + SMS verification",
        TIER_IDENTITY_VERIFIED: "Driver license + selfie",
        TIER_CREDIT_VERIFIED: "Credit application",
    }
    return {
        "tiers": [
            {
                "tier": t,
                "label": TIER_LABELS[t],
                "rank": TIER_RANK[t],
                "requirement": requirement[t],
                "unlocks": list(TIER_CAPABILITIES[t]),
                "all_capabilities": capabilities_for_tier(t),
            }
            for t in TIER_ORDER
        ],
        "disclaimers": {"otp": OTP_DISCLAIMER, "identity": IDENTITY_DISCLAIMER},
    }
