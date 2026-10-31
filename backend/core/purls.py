"""
core/purls.py -- the PURL (Personalized URL) Platform, the second slice of the
Marketing Growth Platform reframe (after Customer 360 + Smart Audiences + Lead
Scoring). Sam's own framing: "one of NXTDeal' strongest differentiators" --
dealer.com/john-smith, a real personalized landing page per customer/lead built
around four named offer types (Current Vehicle, Trade Equity, Inventory Matches,
Payment Reduction), tied to Direct Mail via a real Mail Piece + QR code, and
tracked end to end (Visits -> Leads Generated).

Real mechanism, not a mockup, mirroring core/approval_center.py's/
core/appointment_scheduling.py's established public-link pattern exactly: a real
unguessable token (`secrets.token_urlsafe(24)`), a first-class `PersonalizedURL`
entity (not a dict on Customer/Lead -- one person can have several PURLs over
time, a new mail campaign, a new offer, same "own lifecycle" reasoning
Payment/DamageReport/RepossessionCase already established in this codebase), and
genuinely unauthenticated `/public/purl/*` routes for the visitor-facing half.

Every one of Sam's four offer types reuses an already-real engine rather than a
parallel computation:
  - Current Vehicle: the person's real OWNS-linked Vehicle(s), same lookup
    core/sales_menu.py's `_customer_360()` already established (Lead-targeted
    PURLs -- a person who hasn't bought yet -- honestly have none).
  - Trade Equity: core/smart_audiences.py's `get_equity_candidate_for_customer()`
    (itself reusing core/workflow_tab_data.py's real, HEURISTIC elapsed-term
    equity-mining engine) -- an honest HEURISTIC estimate, not a real payoff
    quote, same disclosure this codebase's other equity-mining consumers already
    carry (a third real consumer of that same lookup-fix logic, not a third
    copy-pasted resolver).
  - Inventory Matches: a real, live search of actual unsold Vehicle inventory
    (same make as the person's current vehicle if known, else any unsold unit),
    reusing core/sales_menu.py's own `_vehicle_brief()` shape directly.
  - Payment Reduction: a real comparison of the person's current, on-file
    FinanceContract.MonthlyPayment against a real estimated payment
    (core/deals.py's own `_estimate_apr()`/`_monthly_payment()` amortization
    math) on the closest real inventory match at today's rate -- real math over
    real+matched inputs, not a fabricated "you could save $X" number. Honestly
    omitted when the person has no on-file FinanceContract to compare against.

**This is also the one channel that can honestly close core/customer_360.py's
own "Website Activity" gap** -- every other channel's browsing is genuinely
anonymous in this codebase (no visitor-to-identity link exists anywhere), but a
PURL visitor's identity IS the token, so `record_purl_visit()`'s real visit log
feeds directly into `get_purl_activity_for_customer()` here, a real per-customer
resolver core/customer_360.py can (and does, as of this same slice) consume in
place of its old blanket not_yet_tracked note.

`submit_purl_lead()` is this module's own "promote to CRM" mechanism, same
precedent as core/orphan_owner_mining.py's `claim_orphan_owner()`/
core/trigger_alerts.py's `promote_alert()`/core/service_sales_handoff.py's
`promote_to_sales()`: creates a real Lead via core/lead_intake.py's
`create_lead()` (Source="PURL", added to VALID_SOURCES). Deliberately assigned
to the SAME salesperson who generated the PURL in the first place, not a
round-robin reassignment -- a dealership sends a PURL from a specific rep, so
that rep should own the resulting response, the same real-world convention this
whole feature is modeled on.

A Mail Piece is real metadata (piece name/type/mail date) stored on the PURL
itself. QR code IMAGE rendering happens client-side (the npm `qrcode` package,
pure JS, no native backend dependency) off this module's own real target URL --
this module only stores what the mail piece needs to reference, not the image.

PURL Analytics: Visits and Leads Generated are 100% real, counted directly off
this PURL's own visit_log/generated_lead_id. Appointments/Sales/Revenue are
real too, but explicitly labeled "since PURL created" -- a real correlation (an
Appointment/funded Deal exists for this person after their PURL was generated),
NOT a proven causal attribution (this codebase has no touch-based attribution
model anywhere yet -- Sam's own later-scoped Analytics & Attribution Engine item
is where that would eventually live).
"""

import secrets
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import PERSONALIZED_URL, CUSTOMER, LEAD, VEHICLE, DEAL, APPOINTMENT
from core.relationship_types import OWNS, FINANCED_BY
from core.lead_intake import create_lead, VALID_SOURCES
from core.deals import _estimate_apr, _monthly_payment
from core.smart_audiences import get_equity_candidate_for_customer
from core.sales_menu import _vehicle_brief, _entities as _sales_entities, _safe_float
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

CUSTOMER_SENTINEL = "customer_via_purl"

if "PURL" not in VALID_SOURCES:
    VALID_SOURCES.append("PURL")

OFFER_TYPES = ["current_vehicle", "trade_equity", "inventory_matches", "payment_reduction", "general"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _relationships_from(entity_id, relationship_type):
    return [r for r in ledger.get_relationships() if r.source_id == entity_id and r.relationship_type == relationship_type]


def _get_purl(purl_id):
    e = ledger.get_entity(purl_id)
    return e if e and e.entity_type == PERSONALIZED_URL else None


def _find_purl_by_token(token):
    for e in ledger.get_all().values():
        if e.entity_type == PERSONALIZED_URL and e.attributes.get("token") == token:
            return e
    return None


def _person_for_purl(purl):
    """A PURL always targets either a real Customer or a real Lead, never both."""
    if purl.attributes.get("customer_id"):
        return ledger.get_entity(purl.attributes["customer_id"])
    if purl.attributes.get("lead_id"):
        return ledger.get_entity(purl.attributes["lead_id"])
    return None


def _person_brief(person):
    if not person:
        return None
    return {
        "id": person.id,
        "type": "customer" if person.entity_type == CUSTOMER else "lead",
        "name": f"{person.attributes.get('FirstName', '')} {person.attributes.get('LastName', '')}".strip(),
        "email": person.attributes.get("Email"),
        "phone": person.attributes.get("Phone"),
    }


def _purl_brief(p):
    return {
        "id": p.id,
        "token": p.attributes.get("token"),
        "customer_id": p.attributes.get("customer_id"),
        "lead_id": p.attributes.get("lead_id"),
        "offer_type": p.attributes.get("offer_type"),
        "status": p.attributes.get("status"),
        "created_by": p.attributes.get("created_by"),
        "created_at": p.attributes.get("created_at"),
        "visit_count": p.attributes.get("visit_count", 0),
        "first_visited_at": p.attributes.get("first_visited_at"),
        "last_visited_at": p.attributes.get("last_visited_at"),
        "generated_lead_id": p.attributes.get("generated_lead_id"),
        "mail_piece": p.attributes.get("mail_piece"),
    }


def generate_purl(created_by, offer_type="general", customer_id=None, lead_id=None, notes=None, _skip_save=False):

    if not customer_id and not lead_id:
        return {"error": "A PURL must target a real customer_id or lead_id"}
    if customer_id and lead_id:
        return {"error": "A PURL targets one person -- provide customer_id OR lead_id, not both"}

    if offer_type not in OFFER_TYPES:
        return {"error": f"Invalid offer_type '{offer_type}' -- must be one of {OFFER_TYPES}"}

    person = ledger.get_entity(customer_id) if customer_id else ledger.get_entity(lead_id)
    if not person or person.entity_type not in (CUSTOMER, LEAD):
        return {"error": "Target customer/lead not found"}

    token = secrets.token_urlsafe(16)

    purl = Entity(
        id=id_generator.generate("PURL"),
        entity_type=PERSONALIZED_URL,
        attributes={
            "token": token,
            "customer_id": customer_id,
            "lead_id": lead_id,
            "offer_type": offer_type,
            "status": "active",
            "created_by": created_by,
            "created_at": _now(),
            "notes": notes or "",
            "visit_count": 0,
            "first_visited_at": None,
            "last_visited_at": None,
            "visit_log": [],
            "mail_piece": None,
            "generated_lead_id": None,
        },
    )

    ledger.add_entity(purl)

    if not _skip_save:
        save_graph(GRAPH_PATH)

    return {"purl": _purl_brief(purl), "public_path": f"/purl/{token}"}


BULK_SOURCE_TYPES = ("marketing_list", "smart_audience")


def bulk_generate_purls(created_by, source_type, source_id, offer_type="general", notes=None):
    """Sam's own framing of PURLs as a direct-mail differentiator implies sending a
    whole campaign audience a personalized link, not clicking 'generate' once per
    person -- generate_purl() only ever created one PURL at a time until now. Resolves
    real members from an already-real audience source (a MarketingList's frozen
    membership, session 82, or a SmartAudience's live-evaluated condition chain,
    session 113) and calls generate_purl() once per member.

    Batches the persistence, not the logic: generate_purl() itself is unchanged for
    the single-PURL callers (its own default save-per-call behavior is untouched), but
    this function passes _skip_save=True through the loop and does ONE real save at the
    end -- the same "batch the writes, not the work" technique
    core/websites.py's create_website_from_wizard()/core/dealership_events.py's
    publish_event() already established, since save_graph() costs several real seconds
    per call on this graph's size and a 50-100-person mail list would otherwise be far
    too slow (and blow well past this environment's own bash-tool timeout during
    testing)."""

    if source_type not in BULK_SOURCE_TYPES:
        return {"error": f"source_type must be one of {BULK_SOURCE_TYPES}"}

    if source_type == "marketing_list":
        from core.marketing_lists import get_list
        source = get_list(source_id)
        if not source:
            return {"error": "Marketing list not found"}
        member_ids = source.attributes.get("member_ids") or []
        source_name = source.attributes.get("name")
    else:
        from core.smart_audiences import evaluate_audience
        result = evaluate_audience(source_id)
        if "error" in result:
            return result
        member_ids = [m["id"] for m in result["members"]]
        source_name = result.get("name")

    members = [ledger.get_entity(mid) for mid in member_ids]
    members = [m for m in members if m is not None]

    if not members:
        return {"error": "No real members found in this source -- nothing to generate"}

    created = []
    skipped = []

    for person in members:

        if person.entity_type == CUSTOMER:
            result = generate_purl(created_by, offer_type=offer_type, customer_id=person.id, notes=notes, _skip_save=True)
        elif person.entity_type == LEAD:
            result = generate_purl(created_by, offer_type=offer_type, lead_id=person.id, notes=notes, _skip_save=True)
        else:
            skipped.append({"id": person.id, "reason": f"Unsupported entity type for a PURL: {person.entity_type}"})
            continue

        if "error" in result:
            skipped.append({"id": person.id, "reason": result["error"]})
        else:
            created.append(result["purl"])

    if created:
        save_graph(GRAPH_PATH)

    return {
        "source_type": source_type,
        "source_id": source_id,
        "source_name": source_name,
        "requested": len(members),
        "created_count": len(created),
        "skipped_count": len(skipped),
        "created": created,
        "skipped": skipped,
    }


def revoke_purl(purl_id, revoked_by):

    purl = _get_purl(purl_id)
    if not purl:
        return {"error": f"PURL '{purl_id}' not found"}
    if purl.attributes.get("status") != "active":
        return {"error": f"PURL is already '{purl.attributes.get('status')}'"}

    purl.attributes["status"] = "revoked"
    purl.attributes["revoked_by"] = revoked_by
    purl.attributes["revoked_at"] = _now()

    save_graph(GRAPH_PATH)

    return {"purl": _purl_brief(purl)}


def list_purls(created_by=None, status=None):

    purls = [e for e in ledger.get_all().values() if e.entity_type == PERSONALIZED_URL]

    if created_by:
        purls = [p for p in purls if p.attributes.get("created_by") == created_by]
    if status:
        purls = [p for p in purls if p.attributes.get("status") == status]

    purls.sort(key=lambda p: p.attributes.get("created_at") or "", reverse=True)

    return {"count": len(purls), "purls": [_purl_brief(p) for p in purls]}


# ---------------------------------------------------------------------------
# Offer content -- the real, per-person personalized page
# ---------------------------------------------------------------------------

def _current_vehicles(person):
    """Dedupes by vehicle id -- some customers have duplicate OWNS relationships
    to the very same vehicle, the same real, pre-existing data-quality quirk
    core/service_customers.py's `_vehicles_owned()` already found and defensively
    handled (session 111 follow-up)."""

    if person.entity_type != CUSTOMER:
        return []

    seen = set()
    owned = []
    for r in _relationships_from(person.id, OWNS):
        v = ledger.get_entity(r.target_id)
        if v and v.entity_type == VEHICLE and v.id not in seen:
            seen.add(v.id)
            owned.append(v)

    return [
        {"id": v.id, "vin": v.attributes.get("VIN"), "year": v.attributes.get("Year"), "make": v.attributes.get("Make"), "model": v.attributes.get("Model")}
        for v in owned
    ]


def _trade_equity_offer(person):
    if person.entity_type != CUSTOMER:
        return {"eligible": False, "reason": "No trade-equity signal is computed for leads who haven't purchased yet."}

    candidate = get_equity_candidate_for_customer(person.id)
    if not candidate:
        return {"eligible": False, "reason": "No real equity-mining signal on file for this customer today."}

    return {
        "eligible": True,
        "basis": "heuristic_elapsed_term",
        "disclaimer": "An estimated equity position based on real loan term elapsed, not a confirmed payoff quote -- your actual trade value depends on a real appraisal.",
        "pct_term_elapsed": candidate.get("pct_term_elapsed"),
        "amount_financed": candidate.get("amount_financed"),
        "vin": candidate.get("vin"),
    }


def _inventory_matches(person, current_vehicles, limit=3):

    unsold = [v for v in _sales_entities(VEHICLE) if not v.attributes.get("DateSold")]

    preferred_makes = {cv["make"] for cv in current_vehicles if cv.get("make")}

    if preferred_makes:
        matched = [v for v in unsold if v.attributes.get("Make") in preferred_makes]
        if not matched:
            matched = unsold
    else:
        matched = unsold

    matched = sorted(matched, key=lambda v: _safe_float(v.attributes.get("Price")))[:limit]

    return [_vehicle_brief(v) for v in matched]


def _current_finance_contract(person):
    if person.entity_type != CUSTOMER:
        return None
    contracts = [
        ledger.get_entity(r.target_id) for r in _relationships_from(person.id, FINANCED_BY)
        if ledger.get_entity(r.target_id)
    ]
    return contracts[0] if contracts else None


def _payment_reduction_offer(person, inventory_matches):

    contract = _current_finance_contract(person)
    if not contract:
        return {"eligible": False, "reason": "No on-file finance contract to compare a reduced payment against."}

    current_payment = _safe_float(contract.attributes.get("MonthlyPayment"))
    if not current_payment:
        return {"eligible": False, "reason": "No real current monthly payment on file for this contract."}

    if not inventory_matches:
        return {"eligible": False, "reason": "No matching inventory to estimate a new payment against."}

    best_match = inventory_matches[0]
    price = _safe_float(best_match.get("price"))
    if not price:
        return {"eligible": False, "reason": "Matched vehicle has no real price on file."}

    credit_score = None
    customer = person if person.entity_type == CUSTOMER else None
    if customer:
        try:
            credit_score = int(customer.attributes.get("CreditScore"))
        except (TypeError, ValueError):
            credit_score = None

    apr = _estimate_apr(credit_score)
    term_months = int(contract.attributes.get("TermMonths") or 60)
    estimated_payment = _monthly_payment(price, apr, term_months)

    return {
        "eligible": True,
        "basis": "real_amortization_math",
        "disclaimer": "A real amortization estimate on the matched vehicle at today's rate tiers -- not a guaranteed offer, actual terms depend on a real credit decision.",
        "current_monthly_payment": current_payment,
        "estimated_new_monthly_payment": estimated_payment,
        "estimated_savings": round(current_payment - estimated_payment, 2),
        "estimated_apr": apr,
        "matched_vehicle": best_match,
    }


def get_personalized_offer(token):
    """PUBLIC -- the real, unauthenticated content behind a PURL's landing page."""

    purl = _find_purl_by_token(token)
    if not purl:
        return {"error": "This link is not valid."}

    # SECURITY: a revoked link must expose NOTHING on this public, unauthenticated route. Revoke is
    # the one mitigation staff have when a PURL leaks; previously it only set a flag while still
    # returning the person's PII, owned VINs, trade-equity estimate, and on-file payment.
    if purl.attributes.get("status") == "revoked":
        return {"revoked": True, "error": "This link is no longer valid."}

    person = _person_for_purl(purl)
    if not person:
        return {"error": "This link is no longer valid -- the person it was created for could not be found."}

    current_vehicles = _current_vehicles(person)
    inventory_matches = _inventory_matches(person, current_vehicles)
    trade_equity = _trade_equity_offer(person)
    payment_reduction = _payment_reduction_offer(person, inventory_matches)

    return {
        "revoked": False,
        "person": _person_brief(person),
        "offer_type": purl.attributes.get("offer_type"),
        "current_vehicles": current_vehicles,
        "trade_equity": trade_equity,
        "inventory_matches": inventory_matches,
        "payment_reduction": payment_reduction,
        "already_submitted": bool(purl.attributes.get("generated_lead_id")),
        "generated_lead_id": purl.attributes.get("generated_lead_id"),
    }


def record_purl_visit(token, user_agent=None):
    """PUBLIC -- a real per-visit tracking event, the mechanism that closes the
    Website Activity gap for this one, identity-known channel."""

    purl = _find_purl_by_token(token)
    if not purl:
        return {"error": "This link is not valid."}

    now = _now()

    purl.attributes["visit_count"] = int(purl.attributes.get("visit_count") or 0) + 1
    if not purl.attributes.get("first_visited_at"):
        purl.attributes["first_visited_at"] = now
    purl.attributes["last_visited_at"] = now
    purl.attributes.setdefault("visit_log", []).append({"visited_at": now, "user_agent": user_agent})

    save_graph(GRAPH_PATH)

    return {"visit_count": purl.attributes["visit_count"], "visited_at": now}


def submit_purl_lead(token, notes=None):
    """PUBLIC -- the real "promote to CRM" action. Assigned to the same salesperson
    who generated the PURL, not a round-robin reassignment -- see module
    docstring."""

    purl = _find_purl_by_token(token)
    if not purl:
        return {"error": "This link is not valid."}
    if purl.attributes.get("status") == "revoked":
        return {"error": "This link has been revoked."}
    if purl.attributes.get("generated_lead_id"):
        return {"error": "A lead has already been submitted through this link.", "lead_id": purl.attributes["generated_lead_id"]}

    person = _person_for_purl(purl)
    if not person:
        return {"error": "This link is no longer valid -- the person it was created for could not be found."}

    created_by = purl.attributes.get("created_by")

    lead = create_lead(
        created_by,
        person.attributes.get("FirstName", ""),
        person.attributes.get("LastName", ""),
        "PURL",
        phone=person.attributes.get("Phone"),
        email=person.attributes.get("Email"),
        city=person.attributes.get("City"),
        state=person.attributes.get("State"),
    )

    lead.attributes["Notes"] = notes or ""
    lead.attributes["SourcePurlId"] = purl.id

    purl.attributes["generated_lead_id"] = lead.id
    purl.attributes["lead_submitted_at"] = _now()
    purl.attributes["lead_submitted_by"] = CUSTOMER_SENTINEL

    save_graph(GRAPH_PATH)

    return {"lead_id": lead.id, "assigned_to": created_by}


# ---------------------------------------------------------------------------
# Mail Piece + Analytics -- staff-side
# ---------------------------------------------------------------------------

def create_mail_piece(purl_id, piece_name, piece_type, mail_date=None, created_by=None):

    purl = _get_purl(purl_id)
    if not purl:
        return {"error": f"PURL '{purl_id}' not found"}

    purl.attributes["mail_piece"] = {
        "piece_name": piece_name,
        "piece_type": piece_type,
        "mail_date": mail_date,
        "created_by": created_by,
        "created_at": _now(),
    }

    save_graph(GRAPH_PATH)

    return {"purl": _purl_brief(purl)}


def _appointments_since(person_id, since_iso):
    return [
        e for e in ledger.get_all().values()
        if e.entity_type == APPOINTMENT
        and (e.attributes.get("customer_id") == person_id or e.attributes.get("lead_id") == person_id)
        and (e.attributes.get("created_at") or "") >= (since_iso or "")
    ]


def _funded_deals_since(person_id, since_iso):
    return [
        e for e in ledger.get_all().values()
        if e.entity_type == DEAL
        and e.attributes.get("customer_id") == person_id
        and e.attributes.get("status") == "funded"
        and (e.attributes.get("funded_at") or "") >= (since_iso or "")
    ]


def get_purl_analytics(purl_id):

    purl = _get_purl(purl_id)
    if not purl:
        return {"error": f"PURL '{purl_id}' not found"}

    person = _person_for_purl(purl)
    created_at = purl.attributes.get("created_at") or ""

    appts = _appointments_since(person.id, created_at) if person else []
    lead_id = purl.attributes.get("generated_lead_id")
    deals_since = _funded_deals_since(person.id, created_at) if (person and person.entity_type == CUSTOMER) else []

    revenue = sum(
        (_safe_float(ledger.get_entity(d.attributes.get("vehicle_id")).attributes.get("Price")) if d.attributes.get("vehicle_id") and ledger.get_entity(d.attributes.get("vehicle_id")) else 0)
        for d in deals_since
    )

    return {
        "purl_id": purl.id,
        "visits": purl.attributes.get("visit_count", 0),
        "first_visited_at": purl.attributes.get("first_visited_at"),
        "last_visited_at": purl.attributes.get("last_visited_at"),
        "lead_generated": bool(lead_id),
        "lead_id": lead_id,
        "correlated_since_creation": {
            "basis": "real_but_not_proven_causal",
            "disclaimer": "Appointments/Revenue below are real records for this person dated after this PURL was created -- a real correlation, not proven attribution. This codebase has no touch-based attribution model yet.",
            "appointments_count": len(appts),
            "funded_deals_count": len(deals_since),
            "revenue": round(revenue, 2),
        },
    }


def get_purl_dashboard(role, created_by=None):

    all_purls = list_purls(created_by=created_by)["purls"]

    active = [p for p in all_purls if p["status"] == "active"]
    total_visits = sum(p["visit_count"] for p in all_purls)
    leads_generated = [p for p in all_purls if p["generated_lead_id"]]

    return {
        "kpis": {
            "total_purls": len(all_purls),
            "active_purls": len(active),
            "total_visits": total_visits,
            "leads_generated": len(leads_generated),
            "conversion_rate": round(len(leads_generated) / len(all_purls) * 100, 1) if all_purls else 0.0,
        },
        "recent_purls": all_purls[:50],
    }


def get_purl_activity_for_customer(customer_id):
    """Consumed by core/customer_360.py -- the real per-customer Website Activity
    resolver this codebase's other channels can't honestly provide (see module
    docstring)."""

    purls = [e for e in ledger.get_all().values() if e.entity_type == PERSONALIZED_URL and e.attributes.get("customer_id") == customer_id]

    events = []
    for p in purls:
        for v in p.attributes.get("visit_log", []):
            events.append({"purl_id": p.id, "visited_at": v.get("visited_at"), "offer_type": p.attributes.get("offer_type")})

    events.sort(key=lambda e: e.get("visited_at") or "", reverse=True)

    return {
        "count": len(events),
        "purl_count": len(purls),
        "visits": events[:20],
        "basis": "real_purl_visit_log",
    }
