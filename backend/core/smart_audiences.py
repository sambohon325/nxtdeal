"""
Marketing CRM: Smart Audiences (Marketing Growth Platform kickoff, 2026-07-17).

Sam's ask: "Smart Audiences" (Truck Owners, No Service In 8 Months, Warranty
Expiring, Lease Ending In 120 Days, Positive Equity, Subprime Customers, Buy Here
Pay Here Customers, Potential Refinance Customers) plus a "Visual Segment Builder"
("Vehicle = Truck AND Mileage > 75,000 AND Positive Equity -- no coding required").

A SmartAudience is a saved, reusable segment DEFINITION -- a plain AND-chain of
conditions over real Customer/Vehicle/FinanceContract/Deal fields, matching Sam's
own literal example -- not a frozen membership snapshot (that's what
core/marketing_lists.py's MarketingList already is, and a SmartAudience can be
frozen into one via "Save as List", reusing that module's build_list_from_pool()-
style membership-array shape). Every evaluate() call is a live re-query against the
current graph, so a saved SmartAudience's membership always reflects today's data,
not whatever it matched when it was created.

Two ways an audience gets defined:
  1. A custom rule set via the generic condition evaluator (`evaluate_conditions()`)
     -- exactly the no-code "field / operator / value" chain Sam's example
     describes, ANDed together (no OR/nesting this pass, matching the one concrete
     example given).
  2. One of the named PRESET_AUDIENCES, each reusing an already-real engine
     elsewhere in this codebase rather than a duplicate computation:
       - "Truck Owners": HEURISTIC -- Vehicle has no BodyStyle field anywhere in
         this codebase (confirmed absent, same finding sessions 63/85/106 already
         made for other body-style-adjacent asks), so this matches real Model
         names against a real, honestly-labeled truck-model keyword list.
       - "No Service In N Months": reuses core/campaigns.py's real
         build_audience("retention", {...}) verbatim.
       - "Warranty Expiring": HEURISTIC -- no warranty term/expiration-DATE field
         exists anywhere in this codebase (same gap core/service_customers.py's
         Lost Customer Recovery already flagged, session 111), so this reuses
         core/repair_orders.py's own Condition-based warranty inference
         (New/Certified Pre-Owned implies likely factory coverage) narrowed to
         vehicles sold within a real, stated window approximating a typical
         factory term, rather than a fabricated exact expiration date.
       - "Lease Ending In N Days": a real, pure (no side effects) re-computation
         of FinanceContract ContractDate + TermMonths -> maturity date, matching
         core/trigger_alerts.py's `_scan_lease_maturity()` math exactly but
         without that function's alert-persistence side effect, since a
         SmartAudience is meant to be freely re-evaluated on every read.
       - "Positive Equity": reuses core/workflow_tab_data.py's real
         `marketing_database_mining()` HEURISTIC elapsed-term candidate list
         directly (the same engine core/trigger_alerts.py's own equity-mining
         scan is built on) -- one real computation, now three consumers.
       - "Subprime Customers": Customer.CreditScore < 660, the same real
         subprime/near-prime threshold core/deals.py's `_estimate_apr()` and
         core/credit_app.py's `_decide()` score bands already use.
       - "Buy Here Pay Here Customers": real Deal.financing_type == "in_house"
         (core/deals.py's `choose_in_house_financing()`), resolved to the
         Deal's customer_id.
       - "Potential Refinance Customers": reuses core/campaigns.py's real
         build_audience("finance_renewal", {...}) verbatim.
"""

from datetime import datetime, timezone, timedelta, date

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import SMART_AUDIENCE, CUSTOMER, VEHICLE, FINANCE_CONTRACT, DEAL
from core.campaigns import build_audience as _campaign_build_audience
from core.workflow_tab_data import marketing_database_mining
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

TRUCK_MODEL_KEYWORDS = [
    "F-150", "F-250", "F-350", "Silverado", "Sierra", "Tacoma", "Tundra",
    "Ranger", "Colorado", "Frontier", "Ridgeline", "Titan", "Ram 1500", "Ram 2500",
]

# HEURISTIC -- new/CPO vehicles sold within this window are treated as likely still
# under a factory warranty approaching expiration, matching the same
# Condition-based inference core/repair_orders.py's `_warranty_status()` already
# uses. No real warranty term/expiration-date field exists on Vehicle.
WARRANTY_TYPICAL_TERM_DAYS = 3 * 365
WARRANTY_EXPIRING_WINDOW_DAYS = 90

FIELD_CATALOG = [
    {"key": "vehicle.make", "label": "Vehicle Make", "type": "text", "entity": "vehicle"},
    {"key": "vehicle.model", "label": "Vehicle Model", "type": "text", "entity": "vehicle"},
    {"key": "vehicle.year", "label": "Vehicle Year", "type": "number", "entity": "vehicle"},
    {"key": "vehicle.mileage", "label": "Vehicle Mileage", "type": "number", "entity": "vehicle"},
    {"key": "vehicle.condition", "label": "Vehicle Condition", "type": "text", "entity": "vehicle"},
    {"key": "customer.credit_score", "label": "Credit Score", "type": "number", "entity": "customer"},
    {"key": "finance.financing_type", "label": "Financing Type (in_house = BHPH)", "type": "text", "entity": "finance"},
]

OPERATORS = ["=", "!=", ">", ">=", "<", "<=", "contains"]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today():
    return datetime.now(timezone.utc).date()


def _all_of_type(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _relationships_from(entity_id, relationship_type):
    return [r for r in ledger.get_relationships() if r.source_id == entity_id and r.relationship_type == relationship_type]


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _customer_vehicles(customer_id):
    return [
        ledger.get_entity(r.target_id) for r in _relationships_from(customer_id, "OWNS")
        if ledger.get_entity(r.target_id) and ledger.get_entity(r.target_id).entity_type == VEHICLE
    ]


def _customer_finance_contracts(customer_id):
    return [
        ledger.get_entity(r.target_id) for r in _relationships_from(customer_id, "FINANCED_BY")
        if ledger.get_entity(r.target_id) and ledger.get_entity(r.target_id).entity_type == FINANCE_CONTRACT
    ]


def _apply_operator(actual, operator, expected):

    if actual is None:
        return False

    try:
        if operator == "contains":
            return str(expected).lower() in str(actual).lower()

        if isinstance(expected, str) and not expected.replace(".", "", 1).lstrip("-").isdigit():
            actual_cmp, expected_cmp = str(actual).lower(), str(expected).lower()
        else:
            actual_cmp, expected_cmp = float(actual), float(expected)

        if operator == "=":
            return actual_cmp == expected_cmp
        if operator == "!=":
            return actual_cmp != expected_cmp
        if operator == ">":
            return actual_cmp > expected_cmp
        if operator == ">=":
            return actual_cmp >= expected_cmp
        if operator == "<":
            return actual_cmp < expected_cmp
        if operator == "<=":
            return actual_cmp <= expected_cmp
    except (TypeError, ValueError):
        return False

    return False


def _customer_matches_conditions(customer, conditions):
    """AND-only, matching Sam's own literal example chain. A vehicle/finance
    condition matches if ANY of the customer's owned vehicles/contracts satisfy
    it (a customer with multiple vehicles qualifies if one of them is a truck,
    not all of them)."""

    vehicles = _customer_vehicles(customer.id)
    contracts = _customer_finance_contracts(customer.id)
    deals = [d for d in _all_of_type(DEAL) if d.attributes.get("customer_id") == customer.id]

    for cond in conditions:

        field = cond.get("field")
        operator = cond.get("operator")
        value = cond.get("value")

        if field == "customer.credit_score":
            if not _apply_operator(customer.attributes.get("CreditScore"), operator, value):
                return False
            continue

        if field and field.startswith("vehicle."):
            attr = field.split(".", 1)[1]
            attr_map = {"make": "Make", "model": "Model", "year": "Year", "mileage": "Mileage", "condition": "Condition"}
            key = attr_map.get(attr)
            if not any(_apply_operator(v.attributes.get(key), operator, value) for v in vehicles):
                return False
            continue

        if field == "finance.financing_type":
            if not any(_apply_operator(d.attributes.get("financing_type"), operator, value) for d in deals):
                return False
            continue

        # Unknown field -- fail closed rather than silently match everyone.
        return False

    return True


def evaluate_conditions(conditions):
    """Live, read-only evaluation -- no persistence, safe to call on every
    preview/refresh."""

    return [c for c in _all_of_type(CUSTOMER) if _customer_matches_conditions(c, conditions or [])]


def _truck_owners():

    matches = []

    for c in _all_of_type(CUSTOMER):
        for v in _customer_vehicles(c.id):
            model = (v.attributes.get("Model") or "")
            if any(kw.lower() in model.lower() for kw in TRUCK_MODEL_KEYWORDS):
                matches.append(c)
                break

    return matches


def _no_service_in_months(months=8):
    return _campaign_build_audience("retention", {"months_since_service": months})


def _warranty_expiring():
    """HEURISTIC -- see module docstring. New/CPO vehicles sold roughly
    WARRANTY_TYPICAL_TERM_DAYS ago (within WARRANTY_EXPIRING_WINDOW_DAYS of that
    typical term), matched back to the owning customer via OWNS."""

    matches = []
    today = _today()

    for v in _all_of_type(VEHICLE):

        condition = (v.attributes.get("Condition") or "").lower()
        if condition not in ("new", "certified pre-owned"):
            continue

        sold = _parse_date(v.attributes.get("DateSold"))
        if not sold:
            continue

        days_since_sale = (today - sold).days
        days_to_typical_expiration = WARRANTY_TYPICAL_TERM_DAYS - days_since_sale

        if 0 <= days_to_typical_expiration <= WARRANTY_EXPIRING_WINDOW_DAYS:
            owner_rel = next((r for r in ledger.get_relationships() if r.target_id == v.id and r.relationship_type == "OWNS"), None)
            if owner_rel:
                owner = ledger.get_entity(owner_rel.source_id)
                if owner and owner.entity_type == CUSTOMER:
                    matches.append(owner)

    return matches


def _lease_ending_in_days(days=120):
    """Pure re-computation of core/trigger_alerts.py's `_scan_lease_maturity()`
    math, without that function's alert-persistence side effect."""

    matches = []

    for c in _all_of_type(CUSTOMER):
        for contract in _customer_finance_contracts(c.id):

            contract_date = _parse_date(contract.attributes.get("ContractDate"))
            term_months = contract.attributes.get("TermMonths")

            if not contract_date or not term_months:
                continue

            try:
                term_months = int(term_months)
            except (TypeError, ValueError):
                continue

            maturity = contract_date + timedelta(days=term_months * 30)
            days_out = (maturity - _today()).days

            if 0 <= days_out <= days:
                matches.append(c)
                break

    return matches


def _customer_id_lookup_by_raw_key():
    """core/workflow_tab_data.py's `marketing_database_mining()` USED TO return
    FinanceContract.CustomerID verbatim -- confirmed live (2026-07-17) this was the
    raw CSV import business key (e.g. "C4077"), NOT the resolved graph CUST- id, the
    same "raw import key never resolved" bug class sessions 39/94 already found and
    fixed for ServiceRecord.Technician/Lead.AssignedSalesperson, here silently making
    core/trigger_alerts.py's `_scan_equity_mining()` return zero real equity alerts.
    **Fixed at the source 2026-07-19** -- `marketing_database_mining()` itself now
    resolves `customer_id` to the real CUST- id before returning it (via the
    identical reverse-lookup-by-CustomerID-attribute approach this function already
    used). This local lookup/workaround is kept as a harmless defensive fallback
    (a raw key would resolve here too if one somehow slipped through) rather than
    removed -- `_positive_equity()`/`get_equity_candidate_for_customer()` below both
    still try `ledger.get_entity(customer_id)` FIRST, which now succeeds directly on
    every real candidate, so this lookup's own `.get(customer_id)` branch is dead
    code on the current data, not a required second resolution step anymore."""

    return {c.attributes.get("CustomerID"): c for c in _all_of_type(CUSTOMER) if c.attributes.get("CustomerID")}


def _positive_equity():

    result = marketing_database_mining("ADMIN")
    lookup = _customer_id_lookup_by_raw_key()
    matches = []

    for cand in result.get("candidates", []):
        customer_id = cand.get("customer_id")
        customer = (ledger.get_entity(customer_id) if customer_id else None) or lookup.get(customer_id)
        if customer and customer.entity_type == CUSTOMER:
            matches.append(customer)

    return matches


def get_equity_candidate_for_customer(customer_id):
    """Public helper (added for the PURL Platform slice) -- returns the real
    marketing_database_mining() candidate dict (pct_term_elapsed/amount_financed/
    finance_contract_id) for ONE specific customer, resolved through this module's
    own `_customer_id_lookup_by_raw_key()` workaround, or None if that customer has
    no real equity-mining candidate. A second real consumer of the same
    lookup-fix logic `_positive_equity()` already established, rather than a third
    copy-pasted resolver."""

    result = marketing_database_mining("ADMIN")
    lookup = _customer_id_lookup_by_raw_key()

    for cand in result.get("candidates", []):
        raw_id = cand.get("customer_id")
        resolved = (ledger.get_entity(raw_id) if raw_id else None) or lookup.get(raw_id)
        if resolved and resolved.id == customer_id:
            return cand

    return None


def _safe_credit_score(customer):
    """Confirmed live (2026-07-17): Customer.CreditScore is stored as a plain
    string (e.g. "700") by imports/customer_import.py, not a number -- same
    tolerant-parsing convention core/deals.py's `_estimate_apr()` already uses."""

    try:
        return float(customer.attributes.get("CreditScore"))
    except (TypeError, ValueError):
        return None


def _subprime_customers():
    matches = []
    for c in _all_of_type(CUSTOMER):
        score = _safe_credit_score(c)
        if score is not None and score < 660:
            matches.append(c)
    return matches


def _bhph_customers():

    bhph_deals = [d for d in _all_of_type(DEAL) if d.attributes.get("financing_type") == "in_house"]
    customer_ids = {d.attributes.get("customer_id") for d in bhph_deals if d.attributes.get("customer_id")}

    return [ledger.get_entity(cid) for cid in customer_ids if ledger.get_entity(cid) and ledger.get_entity(cid).entity_type == CUSTOMER]


def _potential_refinance(months_to_maturity=3):
    return _campaign_build_audience("finance_renewal", {"months_to_maturity": months_to_maturity})


PRESET_AUDIENCES = {
    "truck_owners": {"key": "truck_owners", "name": "Truck Owners", "basis": "heuristic_model_keyword", "params": [], "fn": lambda params: _truck_owners()},
    "no_service_in_months": {"key": "no_service_in_months", "name": "No Service In N Months", "basis": "real", "params": [{"key": "months", "label": "Months since last service", "type": "number", "default": 8}], "fn": lambda params: _no_service_in_months(params.get("months", 8))},
    "warranty_expiring": {"key": "warranty_expiring", "name": "Warranty Expiring", "basis": "heuristic_condition_based", "params": [], "fn": lambda params: _warranty_expiring()},
    "lease_ending": {"key": "lease_ending", "name": "Lease Ending In N Days", "basis": "real", "params": [{"key": "days", "label": "Days until maturity", "type": "number", "default": 120}], "fn": lambda params: _lease_ending_in_days(params.get("days", 120))},
    "positive_equity": {"key": "positive_equity", "name": "Positive Equity", "basis": "heuristic_elapsed_term", "params": [], "fn": lambda params: _positive_equity()},
    "subprime_customers": {"key": "subprime_customers", "name": "Subprime Customers", "basis": "real", "params": [], "fn": lambda params: _subprime_customers()},
    "bhph_customers": {"key": "bhph_customers", "name": "Buy Here Pay Here Customers", "basis": "real", "params": [], "fn": lambda params: _bhph_customers()},
    "potential_refinance": {"key": "potential_refinance", "name": "Potential Refinance Customers", "basis": "real", "params": [{"key": "months_to_maturity", "label": "Months until contract maturity", "type": "number", "default": 3}], "fn": lambda params: _potential_refinance(params.get("months_to_maturity", 3))},
}


def list_presets():
    return [{"key": p["key"], "name": p["name"], "basis": p["basis"], "params": p["params"]} for p in PRESET_AUDIENCES.values()]


def evaluate_preset(preset_key, params=None):

    preset = PRESET_AUDIENCES.get(preset_key)

    if not preset:
        return {"error": f"Unknown preset audience '{preset_key}'"}

    members = preset["fn"](params or {})

    return {"preset": preset_key, "name": preset["name"], "basis": preset["basis"], "count": len(members), "members": members}


def _serialize_member(entity):
    if entity.entity_type == CUSTOMER:
        name = f"{entity.attributes.get('FirstName', '')} {entity.attributes.get('LastName', '')}".strip()
        return {"id": entity.id, "name": name or entity.id, "email": entity.attributes.get("Email"), "phone": entity.attributes.get("Phone")}
    return {"id": entity.id, "name": entity.id}


def preview_preset(preset_key, params=None):

    result = evaluate_preset(preset_key, params)

    if "error" in result:
        return result

    return {
        "preset": result["preset"],
        "name": result["name"],
        "basis": result["basis"],
        "count": result["count"],
        "sample": [_serialize_member(m) for m in result["members"][:10]],
    }


def preview_conditions(conditions):

    members = evaluate_conditions(conditions)

    return {"count": len(members), "sample": [_serialize_member(m) for m in members[:10]]}


def _all_audiences():
    return [e for e in ledger.get_all().values() if e.entity_type == SMART_AUDIENCE]


def create_audience(name, created_by, conditions=None, preset_key=None, preset_params=None, description=""):

    if not name or not name.strip():
        return {"error": "Audience name is required."}

    if preset_key and preset_key not in PRESET_AUDIENCES:
        return {"error": f"Unknown preset audience '{preset_key}'"}

    entity = Entity(
        id=id_generator.generate("AUD"),
        entity_type=SMART_AUDIENCE,
        attributes={
            "name": name.strip(),
            "description": description or "",
            "conditions": conditions or [],
            "preset_key": preset_key,
            "preset_params": preset_params or {},
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    return entity


def delete_audience(audience_id):

    entity = ledger.get_entity(audience_id)

    if not entity or entity.entity_type != SMART_AUDIENCE:
        return {"error": "Smart audience not found"}

    del ledger.entities[audience_id]
    save_graph(GRAPH_PATH)

    return {"deleted": audience_id}


def list_audiences():
    audiences = _all_audiences()
    audiences.sort(key=lambda a: a.attributes.get("created_at") or "", reverse=True)
    return audiences


def evaluate_audience(audience_id):
    """Live re-evaluation of a saved SmartAudience against the CURRENT graph --
    membership is never frozen at save time."""

    entity = ledger.get_entity(audience_id)

    if not entity or entity.entity_type != SMART_AUDIENCE:
        return {"error": "Smart audience not found"}

    if entity.attributes.get("preset_key"):
        result = evaluate_preset(entity.attributes["preset_key"], entity.attributes.get("preset_params") or {})
        if "error" in result:
            return result
        members = result["members"]
        basis = result["basis"]
    else:
        members = evaluate_conditions(entity.attributes.get("conditions") or [])
        basis = "custom_conditions"

    return {
        "audience": entity.id,
        "name": entity.attributes.get("name"),
        "basis": basis,
        "count": len(members),
        "members": [_serialize_member(m) for m in members],
        "member_ids": [m.id for m in members],
    }
