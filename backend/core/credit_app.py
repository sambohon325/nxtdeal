"""
core/credit_app.py -- Credit Application (session 104 follow-up), the fifth of Sam's
~10 "completely missing" dealership workflows (Up System, BDC, Manager TO, Demo Drive,
Credit App, eSignature, F&I Workflow, Delivery Checklist, Lost Sale Recovery, Orphan
Owner Mining -- session 92's original spec).

A real applicant-level record: employment/income, consent, and a decision -- tied to a
Customer and OPTIONALLY a specific Deal. This is deliberately not the same thing as
core/deals.py's financing_status/financing_terms fields on Deal: those describe one
deal's outside-lender submission/decision for one selected scenario. A
CreditApplication can exist before a Deal does at all (a customer walks in and wants
to know what they qualify for before picking a car -- the same "not everything needs a
Deal first" shape core/lead_record.py's Opportunity Creation already established), can
later be linked to a Deal once one exists, and is never fabricated as a second,
competing financing-decision surface.

Honest scope note, matching core/demo_drive.py's license-verification precedent: this
sandbox has no live connection to a real credit bureau (Experian/Equifax/TransUnion) --
there is no such thing here. `decision()`'s "simulated_score" is not a bureau pull; it
reuses the applicant's Customer.CreditScore (itself synthetic seed data) as the input
to a deterministic, rules-based decision engine -- same score bands core/deals.py's
_estimate_apr() already uses for APR estimation, extended down into a real decline
tier. Where a Customer has no CreditScore on file at all, the decision comes back
"conditional" with an honest stipulation that a real bureau pull is still needed,
rather than inventing a number. Declined applications carry real, specific reasons
(ECOA/Reg B, 12 CFR 1002.9, requires an adverse-action notice to state specific
reasons) -- core/compliance_rules.py's existing `_check_ecoa_adverse_action` check is
for Deal.financing_status declines, not wired to this module this pass; flagged for a
future session, not silently assumed done.

Decisioning is a single synchronous step (create -> capture applicant info -> consent
-> submit, which decides immediately) rather than a submit/wait-for-decision two-step
like core/deals.py's outside-lender flow. That two-step models a real human
underwriter's turnaround; a simulated rules engine has no such delay to model, so
collapsing it to one step is the honest choice here, not a shortcut.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import CREDIT_APPLICATION, CUSTOMER, DEAL
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.deals import _estimate_apr
from core import integrations_registry

STATUSES = ["draft", "decisioned", "withdrawn"]
DECISIONS = ["approved", "conditional", "declined"]
EMPLOYMENT_STATUSES = ["employed", "self_employed", "unemployed", "retired", "other"]
HOUSING_STATUSES = ["own", "rent", "other"]

_APPLICANT_FIELDS = (
    "employment_status", "employer_name", "monthly_income",
    "years_at_employer", "monthly_housing_payment", "housing_status",
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _to_float(value):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


def _all_applications():
    return [e for e in ledger.get_all().values() if e.entity_type == CREDIT_APPLICATION]


def get_credit_application(app_id):
    entity = ledger.get_entity(app_id)
    if entity and entity.entity_type == CREDIT_APPLICATION:
        return entity
    return None


def _empty_applicant():
    return {f: None for f in _APPLICANT_FIELDS}


def create_credit_application(customer_id, created_by, linked_deal_id=None, requested_amount=None):

    customer = ledger.get_entity(customer_id)
    if not customer or customer.entity_type != CUSTOMER:
        return {"error": f"'{customer_id}' is not a Customer"}

    if linked_deal_id:
        deal = ledger.get_entity(linked_deal_id)
        if not deal or deal.entity_type != DEAL:
            return {"error": f"'{linked_deal_id}' is not a Deal"}

    app_id = id_generator.generate("CAPP")

    app = Entity(
        id=app_id,
        entity_type=CREDIT_APPLICATION,
        attributes={
            "customer_id": customer_id,
            "linked_deal_id": linked_deal_id,
            "status": "draft",
            "applicant": _empty_applicant(),
            "co_applicant": None,
            "requested_amount": _to_float(requested_amount),
            "ssn_last4": "",
            "fcra_consent": False,
            "fcra_consent_at": None,
            "decision": None,
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
            "withdrawn_at": None,
        },
    )

    ledger.add_entity(app)
    save_graph(GRAPH_PATH)

    return app


def update_applicant(app_id, applicant_patch=None, co_applicant_patch=None, requested_amount=None):
    """Editable only in 'draft' -- once a decision is on file, the application is a
    record of what was actually submitted, same "locked once acted on" convention as
    core/deals.py's trade appraisal (re-editing after approval resets it) rather than
    silently mutating a decisioned record."""

    app = get_credit_application(app_id)
    if not app:
        return {"error": "Credit application not found"}

    if app.attributes.get("status") != "draft":
        return {"error": f"Application is '{app.attributes.get('status')}' -- only a draft application can be edited"}

    if applicant_patch:
        current = dict(app.attributes.get("applicant") or _empty_applicant())
        for key, value in applicant_patch.items():
            if key not in _APPLICANT_FIELDS:
                continue
            if key in ("monthly_income", "years_at_employer", "monthly_housing_payment"):
                current[key] = _to_float(value)
            elif key == "employment_status" and value and value not in EMPLOYMENT_STATUSES:
                return {"error": f"employment_status must be one of {EMPLOYMENT_STATUSES}"}
            elif key == "housing_status" and value and value not in HOUSING_STATUSES:
                return {"error": f"housing_status must be one of {HOUSING_STATUSES}"}
            else:
                current[key] = value
        app.attributes["applicant"] = current

    if co_applicant_patch is not None:
        if co_applicant_patch == {}:
            app.attributes["co_applicant"] = None
        else:
            current_co = dict(app.attributes.get("co_applicant") or _empty_applicant())
            current_co.setdefault("first_name", None)
            current_co.setdefault("last_name", None)
            for key, value in co_applicant_patch.items():
                if key in ("first_name", "last_name") or key in _APPLICANT_FIELDS:
                    if key in ("monthly_income", "years_at_employer", "monthly_housing_payment"):
                        current_co[key] = _to_float(value)
                    else:
                        current_co[key] = value
            app.attributes["co_applicant"] = current_co

    if requested_amount is not None:
        app.attributes["requested_amount"] = _to_float(requested_amount)

    app.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return app


def set_ssn_last4(app_id, ssn_last4):
    """Last 4 digits only -- this codebase never captures or stores a full SSN
    anywhere, same boundary core/deals.py's contract generation and
    core/compliance_rules.py's Red Flags identity check already respect."""

    app = get_credit_application(app_id)
    if not app:
        return {"error": "Credit application not found"}

    if app.attributes.get("status") != "draft":
        return {"error": f"Application is '{app.attributes.get('status')}' -- only a draft application can be edited"}

    digits = "".join(ch for ch in str(ssn_last4 or "") if ch.isdigit())
    if len(digits) != 4:
        return {"error": "ssn_last4 must be exactly 4 digits"}

    app.attributes["ssn_last4"] = digits
    app.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return app


def give_fcra_consent(app_id):
    """The real permissible-purpose gate before a pull can run -- FCRA requires the
    applicant's consent before a credit report is obtained. submit_credit_application()
    refuses to run without this on file, an enforced gate, same shape as
    core/demo_drive.py's license_verified gate."""

    app = get_credit_application(app_id)
    if not app:
        return {"error": "Credit application not found"}

    if app.attributes.get("status") != "draft":
        return {"error": f"Application is '{app.attributes.get('status')}' -- only a draft application can be edited"}

    app.attributes["fcra_consent"] = True
    app.attributes["fcra_consent_at"] = _now()
    app.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return app


def link_to_deal(app_id, deal_id):
    """Attaches an already-created application to a Deal once one exists -- the real
    connective tissue for a customer who was pre-qualified before picking a vehicle."""

    app = get_credit_application(app_id)
    if not app:
        return {"error": "Credit application not found"}

    deal = ledger.get_entity(deal_id)
    if not deal or deal.entity_type != DEAL:
        return {"error": f"'{deal_id}' is not a Deal"}

    app.attributes["linked_deal_id"] = deal_id
    app.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return app


def _decide(app, customer):
    """Deterministic, rules-based simulated decision -- see this module's docstring
    for the full honest scope note. Reuses core/deals.py's _estimate_apr() score bands
    for approved/conditional so the APR an applicant is quoted here is consistent with
    what Deal Desk's desking tool would estimate for the same customer."""

    # Production decisions are unavailable pending reviewed procedures. Demo
    # simulation is allowed only without a live bureau adapter; dispatch failures
    # must not become fallback approvals or persisted decision records.
    from core.workflow_readiness import simulation_block
    blocked = simulation_block("credit_decisioning")
    if blocked:
        return blocked
    applicant_info = app.attributes.get("applicant") or {}
    pull = integrations_registry.pull_credit({
        "customer_id": (customer.id if customer else None),
        "ssn_last4": app.attributes.get("ssn_last4"),
        "first_name": applicant_info.get("first_name"),
        "last_name": applicant_info.get("last_name"),
    })
    if pull.get("error"):
        return pull
    pulled_live = bool(pull.get("pulled")) and pull.get("score") is not None

    if pulled_live:
        raw_score = pull.get("score")
    else:
        raw_score = customer.attributes.get("CreditScore") if customer else None

    try:
        score = int(raw_score)
    except (TypeError, ValueError):
        score = None

    applicant = app.attributes.get("applicant") or {}
    income = applicant.get("monthly_income")
    housing = applicant.get("monthly_housing_payment")

    if score is None:
        return {
            "decision": "conditional",
            "score_band": "Unknown",
            "simulated_score": None,
            "estimated_apr": None,
            "stipulations": [
                "No credit score on file for this customer -- a real bureau pull is "
                "still required before a final decision can be made.",
            ],
            "reasons": [],
            "decisioned_at": _now(),
        }

    if score >= 740:
        return {
            "decision": "approved",
            "score_band": "Excellent",
            "simulated_score": score,
            "estimated_apr": _estimate_apr(score),
            "stipulations": [],
            "reasons": [],
            "decisioned_at": _now(),
        }

    if score >= 660:
        return {
            "decision": "approved",
            "score_band": "Good",
            "simulated_score": score,
            "estimated_apr": _estimate_apr(score),
            "stipulations": ["Proof of income required at signing."],
            "reasons": [],
            "decisioned_at": _now(),
        }

    if score >= 580:
        stipulations = [
            "Co-signer or a larger down payment may be required to finalize terms.",
            "Proof of income required at signing.",
        ]
        return {
            "decision": "conditional",
            "score_band": "Fair",
            "simulated_score": score,
            "estimated_apr": _estimate_apr(score),
            "stipulations": stipulations,
            "reasons": [],
            "decisioned_at": _now(),
        }

    reasons = []
    if score < 500:
        reasons.append("Credit score below program minimum.")
    else:
        reasons.append("Insufficient credit score for requested terms.")

    if income and housing and income > 0 and (housing / income) > 0.4:
        reasons.append("Debt-to-income ratio too high relative to reported housing expense.")

    if not reasons:
        reasons.append("Unable to verify sufficient credit history.")

    return {
        "decision": "declined",
        "score_band": "Poor",
        "simulated_score": score,
        "estimated_apr": None,
        "stipulations": [],
        "reasons": reasons,
        "decisioned_at": _now(),
    }


def submit_credit_application(app_id):

    from core.workflow_readiness import simulation_block
    blocked = simulation_block("credit_decisioning")
    if blocked:
        return blocked

    app = get_credit_application(app_id)
    if not app:
        return {"error": "Credit application not found"}

    if app.attributes.get("status") != "draft":
        return {"error": f"Application is already '{app.attributes.get('status')}'"}

    if not app.attributes.get("fcra_consent"):
        return {"error": "FCRA consent must be captured before an application can be submitted"}

    applicant = app.attributes.get("applicant") or {}
    if not applicant.get("monthly_income"):
        return {"error": "Applicant monthly income is required before submitting"}

    customer = ledger.get_entity(app.attributes["customer_id"])

    decision = _decide(app, customer)
    if decision.get("error"):
        return decision
    # Surface whether a real bureau pull backed this decision (Phase 4). is_live is the
    # honest "is a credit-bureau provider connected" signal.
    decision["pull_mode"] = "live" if integrations_registry.is_live("credit_bureau") else "simulated"
    app.attributes["decision"] = decision
    app.attributes["status"] = "decisioned"
    app.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return app


def withdraw_credit_application(app_id):

    app = get_credit_application(app_id)
    if not app:
        return {"error": "Credit application not found"}

    if app.attributes.get("status") == "withdrawn":
        return {"error": "Application is already withdrawn"}

    app.attributes["status"] = "withdrawn"
    app.attributes["withdrawn_at"] = _now()
    app.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return app


def list_credit_applications(customer_id=None, status=None, linked_deal_id=None):

    apps = _all_applications()

    if customer_id:
        apps = [a for a in apps if a.attributes.get("customer_id") == customer_id]

    if status:
        apps = [a for a in apps if a.attributes.get("status") == status]

    if linked_deal_id:
        apps = [a for a in apps if a.attributes.get("linked_deal_id") == linked_deal_id]

    apps.sort(key=lambda a: a.attributes.get("created_at") or "", reverse=True)

    return apps


def get_stats():
    """Real numbers off real records -- counts by status/decision and an approval
    rate over decisioned applications. Empty/None where there's no sample yet, never
    a fabricated figure, same convention as core/demo_drive.py's get_stats()."""

    apps = _all_applications()

    if not apps:
        return {
            "total": 0,
            "draft": 0,
            "decisioned": 0,
            "withdrawn": 0,
            "approved": 0,
            "conditional": 0,
            "declined": 0,
            "approval_rate_pct": None,
        }

    decisioned = [a for a in apps if a.attributes.get("status") == "decisioned"]
    approved = sum(1 for a in decisioned if (a.attributes.get("decision") or {}).get("decision") == "approved")
    conditional = sum(1 for a in decisioned if (a.attributes.get("decision") or {}).get("decision") == "conditional")
    declined = sum(1 for a in decisioned if (a.attributes.get("decision") or {}).get("decision") == "declined")

    return {
        "total": len(apps),
        "draft": sum(1 for a in apps if a.attributes.get("status") == "draft"),
        "decisioned": len(decisioned),
        "withdrawn": sum(1 for a in apps if a.attributes.get("status") == "withdrawn"),
        "approved": approved,
        "conditional": conditional,
        "declined": declined,
        "approval_rate_pct": round(100 * approved / len(decisioned), 1) if decisioned else None,
    }
