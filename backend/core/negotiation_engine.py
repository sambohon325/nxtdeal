"""
core/negotiation_engine.py -- NXTDeal AI Negotiation Engine (Digital Retail slice DR-3,
2026-07-24). Sam's spec: "Allow negotiation without giving away dealership profitability."
A customer (or an AI Negotiator, or a salesperson) can move the deal levers -- selling price,
trade value, down payment, term, incentives -- but only inside a dealer-configured profit
envelope. An offer that stays inside the envelope is approved on the spot; one that breaks it
is not silently rejected, it is ESCALATED for manager approval.

There was no deal-level gross floor anywhere in NXTDeal before this -- the only profit
guardrail was core/pricing_desk.py's vehicle-level `cost * 1.03` recommendation floor. This
module adds the real thing: a rules engine that computes front gross, total gross, discount,
trade over-allowance, payment variance and loss position for a proposed set of terms and checks
them against dealer-set floors/ceilings.

Two entities: a per-dealer singleton NegotiationRules (prefix NRUL) holding the six configurable
limits + the default session length, and a DealSession (prefix DSES) -- one time-boxed
negotiation per deal that expires after a dealer-defined window (24/48/72h) and carries the
running terms, the offer history, and any open escalation. Nothing here fabricates numbers:
gross uses the real Vehicle Cost/Price, the deal's real trade ACV, the real accepted F&I gross
(core/fi_products.py), and the same payment math as core/deals.py. Whether a customer or an AI
worker is even ALLOWED to drive a negotiation is governed by core/execution_modes.py (the
"negotiation" workflow) -- apply_offer() honors that gate when given an actor kind.
"""

from datetime import datetime, timezone, timedelta

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import NEGOTIATION_RULES, DEAL_SESSION, DEAL, VEHICLE, CUSTOMER
from core.audit import audit_log
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

from core.deals import get_deal, _monthly_payment, _estimate_apr, add_scenario
from core.fi_products import get_fi_menu
from core.execution_modes import require_actor

# ------------------------------------------------------------------------------------
# Dealer rules (singleton) -- the profit envelope.
# ------------------------------------------------------------------------------------

_DEFAULT_RULES = {
    "min_front_gross": 500.0,          # $ -- floor on selling_price - cost - trade over-allowance
    "min_total_gross": 1500.0,         # $ -- floor on front + back (F&I) gross
    "max_discount": 3000.0,            # $ -- ceiling on (asking price - selling price)
    "max_trade_over_allowance": 1000.0,  # $ -- ceiling on (trade allowance - ACV)
    "max_payment_variance": 25.0,      # $ -- ceiling on |monthly - customer target payment|
    "max_loss_position": 0.0,          # $ -- ceiling on a negative total gross (default: no loss)
    "default_session_ttl_hours": 48,   # negotiation window (24/48/72 typical)
}

_RULE_KEYS = tuple(_DEFAULT_RULES.keys())
SESSION_STATUSES = ("active", "escalated", "accepted", "expired")


def _now():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.isoformat() if dt else None


def _find_rules():
    for e in ledger.get_all().values():
        if e.entity_type == NEGOTIATION_RULES:
            return e
    return None


def get_or_create_rules():
    existing = _find_rules()
    if existing is not None:
        return existing
    rules = Entity(
        id=id_generator.generate("NRUL"),
        entity_type=NEGOTIATION_RULES,
        attributes={**_DEFAULT_RULES, "updated_by": None,
                    "updated_at": _iso(_now()), "created_at": _iso(_now())},
    )
    ledger.add_entity(rules)
    save_graph(GRAPH_PATH)
    return rules


def get_rules():
    r = get_or_create_rules().attributes
    return {k: r.get(k) for k in _RULE_KEYS} | {
        "updated_by": r.get("updated_by"), "updated_at": r.get("updated_at")
    }


def set_rules(patch, admin_id):
    """Update one or more of the six limits (+ default TTL). Values must be non-negative
    numbers; TTL must be a positive integer."""
    if not isinstance(patch, dict):
        return {"error": "patch must be an object"}
    rules = get_or_create_rules()
    clean = {}
    for k, v in patch.items():
        if k not in _RULE_KEYS:
            return {"error": f"Unknown rule '{k}' -- valid: {list(_RULE_KEYS)}"}
        if k == "default_session_ttl_hours":
            if not isinstance(v, int) or v <= 0:
                return {"error": "default_session_ttl_hours must be a positive integer"}
        else:
            try:
                v = float(v)
            except (TypeError, ValueError):
                return {"error": f"'{k}' must be a number"}
            if v < 0:
                return {"error": f"'{k}' must be >= 0"}
        clean[k] = v
    rules.attributes.update(clean)
    rules.attributes["updated_by"] = admin_id
    rules.attributes["updated_at"] = _iso(_now())
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="negotiation_rules_changed",
        summary=f"{admin_id} updated negotiation rules: {', '.join(clean)}",
        entity_id=rules.id, actor=admin_id, details=clean,
    )
    return {"rules": get_rules()}


# ------------------------------------------------------------------------------------
# Metrics -- the real gross/discount/payment math for a set of proposed terms.
# ------------------------------------------------------------------------------------

_LEVERS = ("selling_price", "trade_allowance", "down_payment", "term_months", "apr", "incentives")


def _num(x):
    try:
        return float(x or 0)
    except (TypeError, ValueError):
        return 0.0


def _deal_context(deal):
    a = deal.attributes
    vehicle = ledger.get_entity(a.get("vehicle_id"))
    customer = ledger.get_entity(a.get("customer_id"))
    trade = a.get("trade_in") or {}
    asking = _num(vehicle.attributes.get("Price")) if vehicle else 0.0
    cost = _num(vehicle.attributes.get("Cost")) if vehicle else 0.0
    trade_acv = _num(trade.get("acv"))
    credit_score = (customer.attributes.get("CreditScore") if customer else None)
    fi = get_fi_menu(deal.id)
    back_gross = 0.0
    if isinstance(fi, dict) and "totals" in fi:
        back_gross = _num(fi["totals"].get("total_gross_accepted"))
    return {"asking": asking, "cost": cost, "trade_acv": trade_acv,
            "credit_score": credit_score, "back_gross": back_gross}


def _effective_terms(session, proposal):
    terms = dict(session.attributes.get("current_terms") or {})
    for k, v in (proposal or {}).items():
        if k in _LEVERS:
            terms[k] = v
    return terms


def _compute_metrics(deal, terms, target_payment):
    ctx = _deal_context(deal)
    selling_price = _num(terms.get("selling_price"))
    trade_allowance = _num(terms.get("trade_allowance"))
    down_payment = _num(terms.get("down_payment"))
    # Safe numeric parsing — a proposal with term_months="abc" or apr="n/a" must not 500.
    term_months = int(_num(terms.get("term_months"))) or 60
    apr = terms.get("apr")
    apr = _num(apr) if apr not in (None, "") else _estimate_apr(ctx["credit_score"])

    # Dealer-funded incentives are a real cost — subtract them from gross so an offer can't slip
    # inside the profit envelope by loading up on giveaways the envelope math otherwise ignored.
    incentives_total = 0.0
    for inc in (terms.get("incentives") or []):
        incentives_total += _num(inc.get("amount") if isinstance(inc, dict) else inc)

    trade_over_allowance = max(0.0, trade_allowance - ctx["trade_acv"])
    front_gross = selling_price - ctx["cost"] - trade_over_allowance - incentives_total
    total_gross = front_gross + ctx["back_gross"]
    discount = max(0.0, ctx["asking"] - selling_price)
    loss_position = max(0.0, -total_gross)

    amount_financed = max(0.0, selling_price - down_payment - trade_allowance)
    monthly_payment = _monthly_payment(amount_financed, apr, term_months)
    payment_variance = (abs(monthly_payment - _num(target_payment))
                        if target_payment not in (None, "") else None)

    return {
        "selling_price": round(selling_price, 2),
        "asking_price": round(ctx["asking"], 2),
        "vehicle_cost": round(ctx["cost"], 2),
        "trade_allowance": round(trade_allowance, 2),
        "trade_acv": round(ctx["trade_acv"], 2),
        "trade_over_allowance": round(trade_over_allowance, 2),
        "incentives_total": round(incentives_total, 2),
        "front_gross": round(front_gross, 2),
        "back_gross": round(ctx["back_gross"], 2),
        "total_gross": round(total_gross, 2),
        "discount": round(discount, 2),
        "loss_position": round(loss_position, 2),
        "apr": round(apr, 3),
        "term_months": term_months,
        "amount_financed": round(amount_financed, 2),
        "monthly_payment": monthly_payment,
        "payment_variance": (round(payment_variance, 2) if payment_variance is not None else None),
    }


def _violations(metrics, rules):
    v = []
    if metrics["front_gross"] < rules["min_front_gross"]:
        v.append(f"front gross ${metrics['front_gross']:.0f} below minimum ${rules['min_front_gross']:.0f}")
    if metrics["total_gross"] < rules["min_total_gross"]:
        v.append(f"total gross ${metrics['total_gross']:.0f} below minimum ${rules['min_total_gross']:.0f}")
    if metrics["discount"] > rules["max_discount"]:
        v.append(f"discount ${metrics['discount']:.0f} over maximum ${rules['max_discount']:.0f}")
    if metrics["trade_over_allowance"] > rules["max_trade_over_allowance"]:
        v.append(f"trade over-allowance ${metrics['trade_over_allowance']:.0f} over maximum "
                 f"${rules['max_trade_over_allowance']:.0f}")
    if metrics["loss_position"] > rules["max_loss_position"]:
        v.append(f"loss position ${metrics['loss_position']:.0f} over maximum ${rules['max_loss_position']:.0f}")
    if metrics["payment_variance"] is not None and metrics["payment_variance"] > rules["max_payment_variance"]:
        v.append(f"payment variance ${metrics['payment_variance']:.0f} over maximum "
                 f"${rules['max_payment_variance']:.0f}")
    return v


# ------------------------------------------------------------------------------------
# Deal sessions -- one time-boxed negotiation per deal.
# ------------------------------------------------------------------------------------

def _find_session(session_id):
    e = ledger.get_entity(session_id)
    return e if e and e.entity_type == DEAL_SESSION else None


def _refresh(session):
    """Lazily flip an active/escalated session to expired once its window passes."""
    a = session.attributes
    if a["status"] in ("active", "escalated"):
        if _now() > datetime.fromisoformat(a["expires_at"]):
            a["status"] = "expired"
            save_graph(GRAPH_PATH)
    return session


def _seed_terms(deal):
    """Start from the deal's selected scenario if it has one, else from the vehicle's asking
    price with empty levers."""
    a = deal.attributes
    scenarios = a.get("scenarios") or []
    selected_id = a.get("selected_scenario_id")
    selected = next((s for s in scenarios if s.get("id") == selected_id), None)
    if selected:
        return {
            "selling_price": selected.get("sale_price"),
            "trade_allowance": _num((a.get("trade_in") or {}).get("acv")),
            "down_payment": selected.get("down_payment"),
            "term_months": selected.get("term_months"),
            "apr": selected.get("estimated_apr"),
            "incentives": [],
        }
    vehicle = ledger.get_entity(a.get("vehicle_id"))
    asking = vehicle.attributes.get("Price") if vehicle else None
    return {
        "selling_price": asking, "trade_allowance": _num((a.get("trade_in") or {}).get("acv")),
        "down_payment": 0, "term_months": 60, "apr": None, "incentives": [],
    }


def start_session(deal_id, created_by, ttl_hours=None, target_payment=None):
    deal = get_deal(deal_id)
    if not deal or deal.entity_type != DEAL:
        return {"error": f"'{deal_id}' is not a Deal"}
    rules = get_or_create_rules().attributes
    if ttl_hours is None:
        ttl_hours = rules.get("default_session_ttl_hours", 48)
    if not isinstance(ttl_hours, int) or ttl_hours <= 0:
        return {"error": "ttl_hours must be a positive integer"}

    now = _now()
    session = Entity(
        id=id_generator.generate("DSES"),
        entity_type=DEAL_SESSION,
        attributes={
            "deal_id": deal_id,
            "customer_id": deal.attributes.get("customer_id"),
            "vehicle_id": deal.attributes.get("vehicle_id"),
            "status": "active",
            "ttl_hours": ttl_hours,
            "created_by": created_by,
            "created_at": _iso(now),
            "expires_at": _iso(now + timedelta(hours=ttl_hours)),
            "target_payment": target_payment,
            "current_terms": _seed_terms(deal),
            "offers": [],
            "escalation": None,
            "final_terms": None,
        },
    )
    ledger.add_entity(session)
    save_graph(GRAPH_PATH)
    return {"session": _view(session)}


def evaluate_offer(session_id, proposal):
    """Score a proposed set of terms WITHOUT committing it -- what the customer/AI/UI sees
    live as levers move. Returns the effective terms, the metrics, any rule violations, and
    whether it's inside AI authority."""
    session = _find_session(session_id)
    if not session:
        return {"error": f"No deal session {session_id}"}
    _refresh(session)
    deal = get_deal(session.attributes["deal_id"])
    if not deal:
        return {"error": "Underlying deal no longer exists"}
    terms = _effective_terms(session, proposal)
    metrics = _compute_metrics(deal, terms, session.attributes.get("target_payment"))
    violations = _violations(metrics, get_or_create_rules().attributes)
    within = not violations
    return {
        "session_id": session_id,
        "effective_terms": terms,
        "metrics": metrics,
        "violations": violations,
        "within_authority": within,
        "decision": "ai_approved" if within else "needs_manager_approval",
    }


def apply_offer(session_id, proposal, actor, actor_kind=None):
    """Commit a proposed offer. If it's inside the profit envelope the running terms are
    updated and it's approved. If it breaks a rule the session is ESCALATED for manager
    approval (the terms are NOT changed until a manager approves). If actor_kind is given
    ('human'/'ai'/'customer'), the negotiation execution mode must permit that actor."""
    session = _find_session(session_id)
    if not session:
        return {"error": f"No deal session {session_id}"}
    _refresh(session)
    a = session.attributes
    if a["status"] == "expired":
        return {"error": "This negotiation session has expired"}
    if a["status"] == "accepted":
        return {"error": "This negotiation has already been accepted"}
    if a["status"] == "escalated":
        return {"error": "This session is awaiting manager approval -- resolve that first"}
    if actor_kind is not None:
        ok, err = require_actor("negotiation", actor_kind)
        if not ok:
            return {"error": err}

    deal = get_deal(a["deal_id"])
    if not deal:
        return {"error": "Underlying deal no longer exists"}
    terms = _effective_terms(session, proposal)
    metrics = _compute_metrics(deal, terms, a.get("target_payment"))
    violations = _violations(metrics, get_or_create_rules().attributes)
    within = not violations
    decision = "ai_approved" if within else "needs_manager_approval"

    a["offers"].append({
        "at": _iso(_now()), "by": actor, "actor_kind": actor_kind,
        "proposal": proposal, "metrics": metrics, "decision": decision,
    })

    if within:
        a["current_terms"] = terms
    else:
        a["status"] = "escalated"
        a["escalation"] = {
            "reason": "offer outside dealer profit envelope",
            "violations": violations,
            "proposed_terms": terms,
            "proposed_metrics": metrics,
            "requested_by": actor,
            "requested_at": _iso(_now()),
            "resolved": False,
            "decision": None,
            "manager_id": None,
            "note": None,
            "resolved_at": None,
        }
        audit_log.record(
            event_type="negotiation_escalated",
            summary=f"Negotiation {session_id} escalated for manager approval ({len(violations)} rule(s))",
            entity_id=session_id, actor=actor,
            details={"violations": violations},
        )
    save_graph(GRAPH_PATH)
    return {"decision": decision, "within_authority": within,
            "metrics": metrics, "violations": violations, "session": _view(session)}


def resolve_escalation(session_id, decision, manager_id, note=None):
    """Manager approves or denies an escalated offer. Approve -> the proposed terms become the
    running terms and the session returns to active. Deny -> the terms are left unchanged."""
    session = _find_session(session_id)
    if not session:
        return {"error": f"No deal session {session_id}"}
    _refresh(session)
    a = session.attributes
    if a["status"] != "escalated" or not a.get("escalation"):
        return {"error": "This session has no open escalation"}
    decision = str(decision or "").strip().lower()
    if decision not in ("approve", "deny"):
        return {"error": "decision must be 'approve' or 'deny'"}

    esc = a["escalation"]
    esc.update({"resolved": True, "decision": decision, "manager_id": manager_id,
                "note": note, "resolved_at": _iso(_now())})
    if decision == "approve":
        a["current_terms"] = esc["proposed_terms"]
    a["status"] = "active"
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="negotiation_escalation_resolved",
        summary=f"{manager_id} {decision}d escalation on negotiation {session_id}",
        entity_id=session_id, actor=manager_id, details={"decision": decision},
    )
    return {"session": _view(session)}


def accept_session(session_id, accepted_by):
    """Lock in the running terms as the agreed deal structure. Records final_terms and, when
    the underlying deal is still in desking, writes the agreed terms back as a real deal
    scenario (core/deals.add_scenario) so the negotiation output becomes an actual deal
    structure rather than a dead-end record."""
    session = _find_session(session_id)
    if not session:
        return {"error": f"No deal session {session_id}"}
    _refresh(session)
    a = session.attributes
    if a["status"] == "expired":
        return {"error": "This negotiation session has expired"}
    if a["status"] == "escalated":
        return {"error": "Resolve the open manager escalation before accepting"}
    if a["status"] == "accepted":
        return {"error": "This negotiation has already been accepted"}

    terms = a["current_terms"]
    a["final_terms"] = dict(terms)
    a["status"] = "accepted"
    a["accepted_by"] = accepted_by
    a["accepted_at"] = _iso(_now())

    scenario_id = None
    deal = get_deal(a["deal_id"])
    if deal and deal.attributes.get("status") == "desking":
        res = add_scenario(
            a["deal_id"], "Negotiated (NXTDeal)",
            _num(terms.get("selling_price")), _num(terms.get("down_payment")),
            int(_num(terms.get("term_months"))) or 60,
        )
        # add_scenario returns the Deal entity (or {"error": ...}); the new scenario is the
        # last one appended.
        if not (isinstance(res, dict) and res.get("error")):
            scenarios = getattr(res, "attributes", {}).get("scenarios") or []
            if scenarios:
                scenario_id = scenarios[-1].get("id")
    a["accepted_scenario_id"] = scenario_id
    save_graph(GRAPH_PATH)
    audit_log.record(
        event_type="negotiation_accepted",
        summary=f"{accepted_by} accepted negotiation {session_id}",
        entity_id=session_id, actor=accepted_by, details={"scenario_id": scenario_id},
    )
    return {"session": _view(session), "accepted_scenario_id": scenario_id}


# ------------------------------------------------------------------------------------
# Views / listings.
# ------------------------------------------------------------------------------------

def _view(session):
    a = session.attributes
    return {
        "id": session.id,
        "deal_id": a.get("deal_id"),
        "customer_id": a.get("customer_id"),
        "vehicle_id": a.get("vehicle_id"),
        "status": a.get("status"),
        "ttl_hours": a.get("ttl_hours"),
        "created_at": a.get("created_at"),
        "expires_at": a.get("expires_at"),
        "target_payment": a.get("target_payment"),
        "current_terms": a.get("current_terms"),
        "offer_count": len(a.get("offers") or []),
        "offers": a.get("offers") or [],
        "escalation": a.get("escalation"),
        "final_terms": a.get("final_terms"),
        "accepted_scenario_id": a.get("accepted_scenario_id"),
    }


def get_session(session_id):
    session = _find_session(session_id)
    if not session:
        return None
    _refresh(session)
    return _view(session)


def list_sessions(deal_id=None, status=None, limit=100):
    rows = []
    for e in ledger.get_all().values():
        if e.entity_type != DEAL_SESSION:
            continue
        _refresh(e)
        a = e.attributes
        if deal_id and a.get("deal_id") != deal_id:
            continue
        if status and a.get("status") != status:
            continue
        rows.append(_view(e))
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    return {"sessions": rows[:limit], "count": min(len(rows), limit), "total": len(rows)}


def negotiation_summary():
    by_status = {s: 0 for s in SESSION_STATUSES}
    total = 0
    open_escalations = 0
    for e in ledger.get_all().values():
        if e.entity_type != DEAL_SESSION:
            continue
        _refresh(e)
        total += 1
        by_status[e.attributes.get("status", "active")] += 1
        esc = e.attributes.get("escalation")
        if esc and not esc.get("resolved"):
            open_escalations += 1
    return {"total_sessions": total, "by_status": by_status,
            "open_escalations": open_escalations, "rules": get_rules()}
