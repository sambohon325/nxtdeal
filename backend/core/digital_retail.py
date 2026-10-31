"""
core/digital_retail.py -- NXTDeal Digital Retail self-service orchestration (slice DR-4,
2026-07-24). Sam's spec success criterion: a customer can browse -> verify -> evaluate trade ->
negotiate -> apply for credit -> select F&I -> sign -> schedule delivery -> take possession
ENTIRELY through NXTDeal, "without requiring dealership personnel involvement unless dealer-
defined approval thresholds are reached."

This slice is the customer-facing ORCHESTRATION layer. It does not reimplement desking,
trade, negotiation, credit, F&I or e-sign -- those already exist as staff modules. It wraps
them so the CUSTOMER can drive them from a Verify session token, and it enforces the two
governance gates on every step:

  * NXTDeal Verify (core/dealeros_verify.py) -- the customer must have climbed to the tier
    that unlocks the capability (e.g. `negotiate` needs Identity Verified). Checked with
    require_capability().
  * Execution modes (core/execution_modes.py) -- the dealer must have opened that workflow to
    the customer (or hybrid). Checked with require_actor(workflow, "customer").

Every underlying action is recorded against dealeros_verify.CUSTOMER_SENTINEL, never an
employee id -- an honest marker that the customer, not staff, drove it. The one authoritative
identity is the Verify session token (the same posture as the Customer Payment Portal).

It also closes a real gap the recon found: accepted F&I products were never rolled into the
financed amount / payment. estimate_payment_with_fi() and the deal room now surface a
financed-with-F&I figure and its monthly impact so the customer sees the true payment.
"""

from datetime import datetime, timezone

from core.entities import Entity
from core.dealeros import ledger, id_generator
from core.entity_types import CUSTOMER, VEHICLE, DEAL

from core import dealeros_verify as verify
from core import execution_modes as xm
from core import deals
from core import negotiation_engine as neg
from core import fi_products
from core import credit_app
from core import esignature
from core import delivery_fulfillment
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

CUSTOMER_SENTINEL = verify.CUSTOMER_SENTINEL  # one honest marker across the whole flow


def _now():
    return datetime.now(timezone.utc).isoformat()


# ------------------------------------------------------------------------------------
# Token + gate helpers.
# ------------------------------------------------------------------------------------

def _resolve(token):
    """token -> (verification view, error). The token is the customer's only credential."""
    view = verify.get_verification_by_token(token)
    if not view:
        return None, "Invalid or unknown verification token"
    return view, None


def _gate(token, capability, workflow):
    """The two-gate check every self-service step runs: the Verify tier unlocks the capability
    AND the dealer has opened the workflow to the customer. Returns (view, error)."""
    view, err = _resolve(token)
    if err:
        return None, err
    ok, cap_err = verify.require_capability(view["id"], capability)
    if not ok:
        return None, cap_err
    ok, mode_err = xm.require_actor(workflow, "customer")
    if not ok:
        return None, mode_err
    return view, None


def _ensure_customer(view):
    """Return the Customer id backing this verified session, materializing a minimal Customer
    from the session's contact info the first time (no staff needed). Honest: no CreditScore is
    fabricated -- absent means the payment math falls back to a default tier, same as any
    walk-in with no credit data on file."""
    linked = view.get("linked_entity_id")
    if linked:
        subject = ledger.get_entity(linked)
        if subject and subject.entity_type == CUSTOMER:
            return subject.id
    verf = ledger.get_entity(view["id"])
    a = verf.attributes
    customer = Entity(
        id=id_generator.generate("CUST"),
        entity_type=CUSTOMER,
        attributes={
            "FirstName": "",
            "LastName": "",
            "Email": a.get("email") or "",
            "Phone": a.get("phone") or "",
            "Source": "NXTDeal Digital Retail",
            "CreatedAt": _now(),
            "CreatedBy": CUSTOMER_SENTINEL,
        },
    )
    ledger.add_entity(customer)
    save_graph(GRAPH_PATH)
    verify.link_subject(view["id"], customer.id)
    return customer.id


def _owns(view, deal):
    """The verified customer must own the deal they're acting on."""
    if not deal or deal.entity_type != DEAL:
        return False
    linked = view.get("linked_entity_id")
    return linked is not None and deal.attributes.get("customer_id") == linked


# ------------------------------------------------------------------------------------
# Light customer-facing deal view (staff deals_api serialization is role-gated).
# ------------------------------------------------------------------------------------

def _deal_view(deal):
    a = deal.attributes
    return {
        "id": deal.id,
        "status": a.get("status"),
        "customer_id": a.get("customer_id"),
        "vehicle_id": a.get("vehicle_id"),
        "scenarios": a.get("scenarios") or [],
        "selected_scenario_id": a.get("selected_scenario_id"),
        "trade_in": a.get("trade_in"),
        "financing_type": a.get("financing_type"),
        "financing_status": a.get("financing_status"),
        "contract": a.get("contract"),
    }


# ------------------------------------------------------------------------------------
# Step 1 -- start a deal (Identity Verified + desking open to customer).
# ------------------------------------------------------------------------------------

def start_deal(token, vehicle_id):
    view, err = _gate(token, "create_deal", "desking")
    if err:
        return {"error": err}
    vehicle = ledger.get_entity(vehicle_id)
    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": f"'{vehicle_id}' is not a Vehicle"}
    customer_id = _ensure_customer(view)
    result = deals.create_deal(customer_id, vehicle_id, CUSTOMER_SENTINEL)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"deal": _deal_view(result)}


# ------------------------------------------------------------------------------------
# Step 2 -- evaluate a trade (Verified Human + trade open to customer).
# ------------------------------------------------------------------------------------

def submit_trade(token, deal_id, patch):
    view, err = _gate(token, "trade_estimate", "trade")
    if err:
        return {"error": err}
    deal = deals.get_deal(deal_id)
    if not _owns(view, deal):
        return {"error": "This deal is not on your account"}
    result = deals.update_trade_appraisal(deal_id, CUSTOMER_SENTINEL, patch)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"deal": _deal_view(deals.get_deal(deal_id))}


# ------------------------------------------------------------------------------------
# Step 3 -- negotiate (Identity Verified + negotiation open to customer). The engine itself
# also re-checks require_actor("negotiation", "customer").
# ------------------------------------------------------------------------------------

def start_negotiation(token, deal_id, target_payment=None):
    view, err = _gate(token, "negotiate", "negotiation")
    if err:
        return {"error": err}
    deal = deals.get_deal(deal_id)
    if not _owns(view, deal):
        return {"error": "This deal is not on your account"}
    return neg.start_session(deal_id, CUSTOMER_SENTINEL, target_payment=target_payment)


def make_offer(token, session_id, proposal):
    view, err = _resolve(token)
    if err:
        return {"error": err}
    ok, cap_err = verify.require_capability(view["id"], "negotiate")
    if not ok:
        return {"error": cap_err}
    session = neg.get_session(session_id)
    if not session:
        return {"error": f"No negotiation session {session_id}"}
    if not _owns(view, deals.get_deal(session["deal_id"])):
        return {"error": "This negotiation is not on your account"}
    # apply_offer re-checks the negotiation execution mode for the customer actor.
    return neg.apply_offer(session_id, proposal, CUSTOMER_SENTINEL, actor_kind="customer")


def accept_negotiation(token, session_id):
    view, err = _resolve(token)
    if err:
        return {"error": err}
    ok, cap_err = verify.require_capability(view["id"], "negotiate")
    if not ok:
        return {"error": cap_err}
    session = neg.get_session(session_id)
    if not session:
        return {"error": f"No negotiation session {session_id}"}
    if not _owns(view, deals.get_deal(session["deal_id"])):
        return {"error": "This negotiation is not on your account"}
    return neg.accept_session(session_id, CUSTOMER_SENTINEL)


# ------------------------------------------------------------------------------------
# Step 4 -- apply for credit (Identity Verified + credit open to customer). A decisioned
# application auto-advances the Verify session to Credit Verified.
# ------------------------------------------------------------------------------------

def apply_credit(token, deal_id, applicant, monthly_income=None,
                 co_applicant=None, requested_amount=None):
    view, err = _gate(token, "create_deal", "credit")
    if err:
        return {"error": err}
    deal = deals.get_deal(deal_id)
    if not _owns(view, deal):
        return {"error": "This deal is not on your account"}

    app = credit_app.create_credit_application(
        deal.attributes["customer_id"], CUSTOMER_SENTINEL,
        linked_deal_id=deal_id, requested_amount=requested_amount,
    )
    if isinstance(app, dict) and app.get("error"):
        return app
    app_id = app.id

    patch = dict(applicant or {})
    if monthly_income is not None:
        patch["monthly_income"] = monthly_income
    upd = credit_app.update_applicant(app_id, applicant_patch=patch, co_applicant_patch=co_applicant)
    if isinstance(upd, dict) and upd.get("error"):
        return upd
    consent = credit_app.give_fcra_consent(app_id)
    if isinstance(consent, dict) and consent.get("error"):
        return consent
    submitted = credit_app.submit_credit_application(app_id)
    if isinstance(submitted, dict) and submitted.get("error"):
        return submitted

    # Completing a decisioned application advances the trust ladder to Credit Verified.
    promotion = verify.submit_credit_verification(view["id"], app_id)

    app_entity = credit_app.get_credit_application(app_id)
    return {
        "credit_application_id": app_id,
        "decision": app_entity.attributes.get("decision") if app_entity else None,
        "verification": promotion.get("verification") if isinstance(promotion, dict) else None,
    }


# ------------------------------------------------------------------------------------
# Step 5 -- choose financing (Credit Verified + credit open to customer). Selects the
# negotiated scenario and self-approves in-house/BHPH financing, moving the deal to financing.
# ------------------------------------------------------------------------------------

def choose_financing(token, deal_id):
    view, err = _gate(token, "final_financing", "credit")
    if err:
        return {"error": err}
    deal = deals.get_deal(deal_id)
    if not _owns(view, deal):
        return {"error": "This deal is not on your account"}
    scenarios = deal.attributes.get("scenarios") or []
    if not scenarios:
        return {"error": "Build a deal (negotiate/accept) before choosing financing"}
    if deal.attributes.get("status") == "desking":
        scenario_id = deal.attributes.get("selected_scenario_id") or scenarios[-1]["id"]
        sel = deals.select_scenario(deal_id, scenario_id)
        if isinstance(sel, dict) and sel.get("error"):
            return sel
    fin = deals.choose_in_house_financing(deal_id)
    if isinstance(fin, dict) and fin.get("error"):
        return fin
    return {"deal": _deal_view(deals.get_deal(deal_id))}


# ------------------------------------------------------------------------------------
# Step 6 -- select F&I (Credit Verified + fi open to customer). Auto-presents the product so
# the customer can accept/decline it, then rolls the accepted price into the payment estimate.
# ------------------------------------------------------------------------------------

def select_fi(token, deal_id, product_key, decision):
    view, err = _gate(token, "final_financing", "fi")
    if err:
        return {"error": err}
    deal = deals.get_deal(deal_id)
    if not _owns(view, deal):
        return {"error": "This deal is not on your account"}

    menu = fi_products.get_fi_menu(deal_id)
    if isinstance(menu, dict) and menu.get("error"):
        return menu
    present_keys = {p["product_key"] for p in menu.get("products", [])}
    if product_key not in present_keys:
        pres = fi_products.present_fi_products(deal_id, [product_key], CUSTOMER_SENTINEL)
        if isinstance(pres, dict) and pres.get("error"):
            return pres
    result = fi_products.decide_fi_product(deal_id, product_key, decision)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"fi_menu": fi_products.get_fi_menu(deal_id),
            "payment": estimate_payment_with_fi(deal_id)}


# ------------------------------------------------------------------------------------
# Step 7 -- sign (Credit Verified + contracting open to customer). Generates the contract if
# needed, then creates + sends + consents + signs a single-customer e-signature request.
# ------------------------------------------------------------------------------------

def sign(token, deal_id, typed_signature):
    view, err = _gate(token, "contracting", "contracting")
    if err:
        return {"error": err}
    deal = deals.get_deal(deal_id)
    if not _owns(view, deal):
        return {"error": "This deal is not on your account"}

    from core.contracting_readiness import execution_block
    blocked = execution_block("retail_sign")
    if blocked:
        return blocked

    if not deal.attributes.get("contract"):
        gen = deals.generate_contract(deal_id)
        if isinstance(gen, dict) and gen.get("error"):
            return gen

    verf = ledger.get_entity(view["id"])
    signer = {"name": "Customer", "role": "customer", "email": verf.attributes.get("email")}
    # list_signature_requests returns a list of entities; reuse an open one, else create.
    active = [r for r in esignature.list_signature_requests(linked_deal_id=deal_id)
              if r.attributes.get("status") in ("draft", "sent")]
    if active:
        req = active[0]
    else:
        req = esignature.create_signature_request(deal_id, CUSTOMER_SENTINEL, [signer])
        if isinstance(req, dict) and req.get("error"):
            return req
    req_id = req.id

    if req.attributes.get("status") == "draft":
        sent = esignature.send_signature_request(req_id)
        if isinstance(sent, dict) and sent.get("error"):
            return sent
    consent = esignature.capture_signer_consent(req_id, 0)
    if isinstance(consent, dict) and consent.get("error"):
        return consent
    result = esignature.sign(req_id, 0, typed_signature)
    if isinstance(result, dict) and result.get("error"):
        return result
    return {"signature_request_id": req_id,
            "fully_signed": esignature.is_deal_fully_signed(deal_id),
            "deal": _deal_view(deals.get_deal(deal_id))}


# ------------------------------------------------------------------------------------
# Step 8 -- schedule delivery (Credit Verified + delivery open to customer). The final step
# of the self-service journey.
# ------------------------------------------------------------------------------------

def schedule_delivery(token, deal_id, mode, window_start, window_end=None, address=None):
    view, err = _gate(token, "schedule_delivery", "delivery")
    if err:
        return {"error": err}
    deal = deals.get_deal(deal_id)
    if not _owns(view, deal):
        return {"error": "This deal is not on your account"}
    return delivery_fulfillment.schedule_delivery(
        deal_id, mode, window_start, CUSTOMER_SENTINEL,
        window_end=window_end, address=address,
    )


# ------------------------------------------------------------------------------------
# Payment WITH F&I rolled in (closes the recon gap) + the consolidated deal room.
# ------------------------------------------------------------------------------------

def estimate_payment_with_fi(deal_id):
    """The true monthly payment once accepted F&I products are financed -- the gap the recon
    found (F&I was never rolled into amount_financed). Uses the selected scenario's numbers +
    the F&I menu's accepted price and the same amortization as core/deals.py."""
    deal = deals.get_deal(deal_id)
    if not deal:
        return {"error": "Deal not found"}
    scenarios = deal.attributes.get("scenarios") or []
    sel_id = deal.attributes.get("selected_scenario_id")
    scenario = next((s for s in scenarios if s["id"] == sel_id), scenarios[-1] if scenarios else None)
    if not scenario:
        return {"error": "No scenario to price yet"}

    menu = fi_products.get_fi_menu(deal_id)
    fi_price = 0.0
    if isinstance(menu, dict) and "totals" in menu:
        fi_price = float(menu["totals"].get("total_price_accepted") or 0)

    base_financed = float(scenario.get("amount_financed") or 0)
    apr = float(scenario.get("estimated_apr") or deals._estimate_apr(None))
    term = int(scenario.get("term_months") or 60)
    financed_with_fi = round(base_financed + fi_price, 2)
    return {
        "base_amount_financed": round(base_financed, 2),
        "fi_accepted_price": round(fi_price, 2),
        "amount_financed_with_fi": financed_with_fi,
        "apr": apr,
        "term_months": term,
        "base_monthly_payment": deals._monthly_payment(base_financed, apr, term),
        "monthly_payment_with_fi": deals._monthly_payment(financed_with_fi, apr, term),
    }


def _next_steps(view, deal):
    """A plain-language checklist of what the customer can do next, given their tier + the
    deal's state. Purely informational."""
    tier = view["tier"]
    status = deal.attributes.get("status")
    steps = []
    if tier == "anonymous":
        steps.append("Verify your email and phone to save vehicles and value your trade.")
    if tier in ("anonymous", "verified_human") and status == "desking":
        steps.append("Verify your identity to build and negotiate a deal.")
    if verify.can(view["id"], "negotiate") and status == "desking":
        steps.append("Negotiate your price and payment.")
    if not view["credit_verified"]:
        steps.append("Apply for financing to unlock contracting and delivery.")
    if view["credit_verified"] and status in ("financing", "contract"):
        steps.append("Choose F&I coverage and sign your documents.")
    return steps


def get_deal_room(token, deal_id):
    """One consolidated customer-facing view: their verification tier + capabilities, the
    deal, any negotiations on it, the F&I menu, the true payment (F&I rolled in), and next
    steps. Read-only."""
    view, err = _resolve(token)
    if err:
        return {"error": err}
    deal = deals.get_deal(deal_id)
    if not _owns(view, deal):
        return {"error": "This deal is not on your account"}
    return {
        "verification": {"tier": view["tier"], "tier_label": view["tier_label"],
                         "capabilities": view["capabilities"], "next_tier": view["next_tier"]},
        "deal": _deal_view(deal),
        "negotiations": neg.list_sessions(deal_id=deal_id)["sessions"],
        "fi_menu": fi_products.get_fi_menu(deal_id),
        "payment": estimate_payment_with_fi(deal_id),
        "next_steps": _next_steps(view, deal),
    }
