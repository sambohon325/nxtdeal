"""
DMS Deal Desk (2026-07-13, session 33) -- phase 1 of the DMS buildout Sam scoped after
looking at DealerSocket and Tekion: "full inventory data, be able to sell a car, create
the contract, have in-house financing for independent dealers or hook up to outside
lenders, and go through financing all through the structure that we have." Modeled on
those platforms' Desking -> F&I -> Contracting modules, graph-native like everything
else in NXTDeal.

A Deal tracks one vehicle sale through a fixed lifecycle:

    desking -> financing -> contract -> funded
                  \-> cancelled (from desking or financing)

Desking: multiple pricing/term scenarios (Sam's explicit scoping choice -- side-by-side
comparison, not a single streamlined offer) get built and compared before one is locked
in via select_scenario().

Financing: once a scenario is selected, the deal is financed either in-house (BHPH-style
-- the dealer is the lender, self-approved) or through an outside Lender entity already
in the graph, via a simulated submit/decide workflow (approve/decline/counter) mirroring
the asset/campaign approval pattern already established in this codebase.

Contract: generate_contract() builds a non-executable estimate worksheet. The legacy
contract key/stage is retained for compatibility; it is not legal execution readiness.
As of 2026-10-14, funding is blocked outside the isolated sample-data demo pending
reviewed forms, calculations, execution and security evidence.

Funding: fund_deal() is the one place this module writes to the REST of the graph --
it creates a real FinanceContract entity and the exact FINANCED_BY/OWNS/PURCHASED/
COVERS/FUNDED_BY relationships imports/finance_import.py already establishes for
historical seed data, plus marks the Vehicle sold (DateSold). A funded Deal is
indistinguishable from imported historical data to every existing dashboard/profile
view -- no parallel "deals" reporting surface was invented.
"""

from datetime import datetime, timezone, date

from core.dealeros import ledger, id_generator, registry
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import DEAL, CUSTOMER, VEHICLE, LENDER, FINANCE_CONTRACT
from core.relationship_types import FINANCED_BY, FUNDED_BY, COVERS, OWNS, PURCHASED
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
# core.vin_decoder is deliberately NOT imported at module level here -- it
# imports core.workflow_tab_data, which (several hops later, via
# core.data_connections_api -> core.compliance -> core.bot_tasks) imports
# core.deals itself, a real circular-import loop. decode_trade_in_vin()
# below does its own deferred, in-function import instead, the same
# technique core/loan_servicing.py's get_loan_financials() already
# established for this exact class of problem.


IN_HOUSE_LENDER_NAME = "In-House Financing (BHPH)"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today_iso():
    return date.today().isoformat()


def _estimate_apr(credit_score):
    """Deterministic tiering (not the randomized spread
    imports/generate_seed_data.py uses for synthetic variety) -- a live desking tool
    needs the same inputs to always produce the same estimate."""

    try:
        credit_score = int(credit_score)
    except (TypeError, ValueError):
        credit_score = 660

    if credit_score >= 740:
        return 4.9

    if credit_score >= 660:
        return 6.9

    return 9.9


def _monthly_payment(principal, apr, term_months):

    principal = float(principal or 0)
    term_months = int(term_months or 1)
    monthly_rate = float(apr or 0) / 100 / 12

    if monthly_rate == 0:
        return round(principal / term_months, 2)

    payment = (
        principal
        * (monthly_rate * (1 + monthly_rate) ** term_months)
        / ((1 + monthly_rate) ** term_months - 1)
    )

    return round(payment, 2)


def _all_deals():
    return [e for e in ledger.get_all().values() if e.entity_type == DEAL]


def get_deal(deal_id):

    entity = ledger.get_entity(deal_id)

    if entity and entity.entity_type == DEAL:
        return entity

    return None


def list_lenders():
    return [e for e in ledger.get_all().values() if e.entity_type == LENDER]


def create_deal(customer_id, vehicle_id, created_by, trade_in=None):

    customer = ledger.get_entity(customer_id)

    if not customer or customer.entity_type != CUSTOMER:
        return {"error": f"Customer '{customer_id}' not found"}

    vehicle = ledger.get_entity(vehicle_id)

    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": f"Vehicle '{vehicle_id}' not found"}

    if vehicle.attributes.get("DateSold"):
        return {"error": f"Vehicle '{vehicle_id}' is already sold"}

    deal_id = id_generator.generate("DEAL")

    entity = Entity(
        id=deal_id,
        entity_type=DEAL,
        attributes={
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "trade_in": trade_in,
            "status": "desking",
            "scenarios": [],
            "selected_scenario_id": None,
            "financing_type": None,
            "lender_id": None,
            "financing_status": "not_started",
            "financing_terms": None,
            "contract": None,
            "finance_contract_id": None,
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
            "funded_at": None,
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)

    # Pillar 4 slice 2 (2026-07-23): feed the Sales team agent its first REAL observed
    # workflow step. Best-effort and fully isolated -- recording is an observation signal,
    # never load-bearing, so a failure here must never break deal creation. workflow_key is
    # the deal id so that when future deal-lifecycle sites (add_scenario, select_scenario,
    # fund_deal, ...) are wired with the same key, the Sales agent will mine the real
    # multi-step deal workflow rather than isolated one-off steps. See core/bot_fleet.py.
    try:
        from core.bot_fleet import record_workflow_step

        record_workflow_step(
            "sales",
            created_by,
            "create_deal",
            step_label="Created a deal",
            workflow_key=deal_id,
        )
    except Exception:
        pass

    return entity


def add_scenario(deal_id, label, sale_price, down_payment, term_months):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") != "desking":
        return {"error": f"Deal is '{deal.attributes.get('status')}', not in desking"}

    customer = ledger.get_entity(deal.attributes["customer_id"])
    credit_score = customer.attributes.get("CreditScore") if customer else None

    sale_price = float(sale_price or 0)
    down_payment = float(down_payment or 0)
    term_months = int(term_months or 60)
    amount_financed = round(sale_price - down_payment, 2)
    apr = _estimate_apr(credit_score)

    scenario = {
        "id": f"scn-{len(deal.attributes['scenarios']) + 1}",
        "label": label or f"Scenario {len(deal.attributes['scenarios']) + 1}",
        "sale_price": sale_price,
        "down_payment": down_payment,
        "term_months": term_months,
        "amount_financed": amount_financed,
        "estimated_apr": apr,
        "estimated_monthly_payment": _monthly_payment(amount_financed, apr, term_months),
    }

    deal.attributes["scenarios"].append(scenario)
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


def remove_scenario(deal_id, scenario_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") != "desking":
        return {"error": f"Deal is '{deal.attributes.get('status')}', not in desking"}

    scenarios = deal.attributes["scenarios"]
    remaining = [s for s in scenarios if s["id"] != scenario_id]

    if len(remaining) == len(scenarios):
        return {"error": f"No scenario '{scenario_id}' on this deal"}

    deal.attributes["scenarios"] = remaining
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


def select_scenario(deal_id, scenario_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") != "desking":
        return {"error": f"Deal is '{deal.attributes.get('status')}', not in desking"}

    scenario = next((s for s in deal.attributes["scenarios"] if s["id"] == scenario_id), None)

    if not scenario:
        return {"error": f"No scenario '{scenario_id}' on this deal"}

    deal.attributes["selected_scenario_id"] = scenario_id
    deal.attributes["status"] = "financing"
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


def _selected_scenario(deal):
    scenario_id = deal.attributes.get("selected_scenario_id")
    return next((s for s in deal.attributes["scenarios"] if s["id"] == scenario_id), None)


def _get_or_create_in_house_lender():

    lender_id = registry.find_lender(IN_HOUSE_LENDER_NAME)

    if lender_id and ledger.get_entity(lender_id):
        return lender_id

    lender_id = id_generator.generate("LENDER")

    ledger.add_entity(Entity(
        id=lender_id,
        entity_type=LENDER,
        attributes={"Name": IN_HOUSE_LENDER_NAME},
    ))

    registry.register_lender(IN_HOUSE_LENDER_NAME, lender_id)

    return lender_id


def choose_in_house_financing(deal_id):
    """In-house/BHPH financing is dealer-self-approved -- no submission/decision step,
    matching how a real independent dealer runs their own paper. Financing terms are
    taken directly from the selected scenario; there's no negotiation against yourself."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") != "financing":
        return {"error": f"Deal is '{deal.attributes.get('status')}', not ready for financing"}

    scenario = _selected_scenario(deal)

    if not scenario:
        return {"error": "No scenario selected on this deal"}

    lender_id = _get_or_create_in_house_lender()

    deal.attributes["financing_type"] = "in_house"
    deal.attributes["lender_id"] = lender_id
    deal.attributes["financing_status"] = "approved"
    deal.attributes["financing_terms"] = {
        "apr": scenario["estimated_apr"],
        "term_months": scenario["term_months"],
        "amount_financed": scenario["amount_financed"],
        "down_payment": scenario["down_payment"],
        "monthly_payment": scenario["estimated_monthly_payment"],
    }
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


def submit_to_lender(deal_id, lender_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") != "financing":
        return {"error": f"Deal is '{deal.attributes.get('status')}', not ready for financing"}

    if not _selected_scenario(deal):
        return {"error": "No scenario selected on this deal"}

    lender = ledger.get_entity(lender_id)

    if not lender or lender.entity_type != LENDER:
        return {"error": f"Lender '{lender_id}' not found"}

    deal.attributes["financing_type"] = "outside_lender"
    deal.attributes["lender_id"] = lender_id
    deal.attributes["financing_status"] = "submitted"
    deal.attributes["financing_terms"] = None
    deal.attributes["updated_at"] = _now()

    # Lender Intelligence (2026-07-19) -- a real, append-only per-submission log,
    # same "own history list on the entity" convention as ro_stage_history/
    # collection_stage_history/price_history elsewhere in this codebase. A deal can
    # be submitted, declined, then resubmitted to a different lender, so this is a
    # list of every real submission, not a single mutable pair of fields -- the
    # decision half of each entry is filled in by record_lender_decision() below.
    # Historical deals seeded before this slice have no history at all here --
    # core/lender_intelligence.py treats that honestly as "no data," never guessed.
    deal.attributes.setdefault("lender_submission_history", []).append({
        "lender_id": lender_id,
        "lender_name": lender.attributes.get("Name"),
        "submitted_at": deal.attributes["updated_at"],
        "decided_at": None,
        "decision": None,
        "terms": None,
        "notes": None,
    })

    save_graph(GRAPH_PATH)

    return deal


_REQUIRED_TERM_KEYS = ("apr", "term_months", "amount_financed", "down_payment", "monthly_payment")


def _validate_countered_terms(terms):
    """A 'countered' decision stores lender-supplied terms verbatim as financing_terms, which
    generate_contract later indexes (terms["amount_financed"], ["apr"], ...) and computes a
    payment from. Validate the shape HERE so a malformed counter can't crash contract
    generation with a KeyError or write non-numeric / negative terms onto the deal. Returns
    (clean_terms, None) or (None, error_message)."""
    if not isinstance(terms, dict):
        return None, "Countered terms must be an object with apr, term_months, amount_financed, down_payment, and monthly_payment."
    clean = {}
    for key in _REQUIRED_TERM_KEYS:
        if terms.get(key) is None:
            return None, f"Countered terms are missing '{key}'."
        try:
            value = float(terms[key])
        except (TypeError, ValueError):
            return None, f"Countered term '{key}' must be a number."
        if value < 0:
            return None, f"Countered term '{key}' can't be negative."
        clean[key] = int(value) if key == "term_months" else value
    if clean["term_months"] <= 0:
        return None, "Countered term 'term_months' must be greater than zero."
    return clean, None


def record_lender_decision(deal_id, decision, countered_terms=None, notes=None):
    """decision is one of 'approved' / 'declined' / 'countered'. A declined deal stays
    in 'financing' status so the desk can try a different lender or switch to in-house
    -- same "no dead end, try again" shape core/websites.py's rejected-can-resubmit
    deviation already established for this codebase."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("financing_status") != "submitted":
        return {"error": f"Deal's financing is '{deal.attributes.get('financing_status')}', not awaiting a decision"}

    if decision not in ("approved", "declined", "countered"):
        return {"error": f"Unknown decision '{decision}'"}

    scenario = _selected_scenario(deal)

    if decision == "approved":

        deal.attributes["financing_status"] = "approved"
        deal.attributes["financing_terms"] = {
            "apr": scenario["estimated_apr"],
            "term_months": scenario["term_months"],
            "amount_financed": scenario["amount_financed"],
            "down_payment": scenario["down_payment"],
            "monthly_payment": scenario["estimated_monthly_payment"],
        }

    elif decision == "countered":

        if not countered_terms:
            return {"error": "Countered decisions require countered_terms"}

        clean_terms, terms_error = _validate_countered_terms(countered_terms)
        if terms_error:
            return {"error": terms_error}

        deal.attributes["financing_status"] = "countered"
        deal.attributes["financing_terms"] = clean_terms

    else:

        deal.attributes["financing_status"] = "declined"
        deal.attributes["financing_terms"] = None
        deal.attributes["lender_id"] = None
        deal.attributes["financing_type"] = None

    deal.attributes["financing_notes"] = notes
    deal.attributes["updated_at"] = _now()

    # Fill in the decision half of the most recent still-open submission entry
    # (the one submit_to_lender() appended and left decided_at=None on) -- this is
    # a real per-submission ledger, not the live financing_status/lender_id fields
    # themselves, so it survives even the decline path clearing lender_id above.
    history = deal.attributes.get("lender_submission_history") or []
    if history and history[-1].get("decided_at") is None:
        history[-1]["decided_at"] = deal.attributes["updated_at"]
        history[-1]["decision"] = decision
        history[-1]["terms"] = deal.attributes.get("financing_terms")
        history[-1]["notes"] = notes

    save_graph(GRAPH_PATH)

    return deal


def accept_countered_terms(deal_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("financing_status") != "countered":
        return {"error": "This deal's financing isn't in a countered state"}

    deal.attributes["financing_status"] = "approved"
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


def generate_contract(deal_id):
    """Build the legacy workflow summary as an explicitly non-executable worksheet."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") != "financing":
        return {"error": f"Deal is '{deal.attributes.get('status')}', not ready for a contract"}

    if deal.attributes.get("financing_status") != "approved":
        return {"error": "Financing must be approved before generating a contract"}

    customer = ledger.get_entity(deal.attributes["customer_id"])
    vehicle = ledger.get_entity(deal.attributes["vehicle_id"])
    lender = ledger.get_entity(deal.attributes["lender_id"])
    scenario = _selected_scenario(deal)
    terms = deal.attributes["financing_terms"]
    trade_in = deal.attributes.get("trade_in") or {}

    # Roll accepted F&I products into the financed amount + payment (2026-07-24). The scenario/
    # financing terms are the BASE deal (price - down); accepted back-end products (VSC/GAP/etc.,
    # core/fi_products.py) are financed on top, so the authoritative contract -- and the
    # FinanceContract fund_deal() mints from it -- must include them. Lazy import avoids a
    # deals<->fi_products import cycle (fi_products imports get_deal from here).
    from core.fi_products import get_fi_menu
    fi_menu = get_fi_menu(deal_id)
    accepted_fi = []
    fi_financed = 0.0
    if isinstance(fi_menu, dict) and "products" in fi_menu:
        accepted_fi = [
            {"product_key": p.get("product_key"), "name": p.get("name"), "price": p.get("price")}
            for p in fi_menu["products"] if p.get("status") == "accepted"
        ]
        fi_financed = float(fi_menu.get("totals", {}).get("total_price_accepted") or 0)

    base_amount_financed = terms["amount_financed"]
    amount_financed = round(base_amount_financed + fi_financed, 2)
    monthly_payment = _monthly_payment(amount_financed, terms["apr"], terms["term_months"])

    customer_name = f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip()
    vehicle_description = (
        f"{vehicle.attributes.get('Year', '')} {vehicle.attributes.get('Make', '')} "
        f"{vehicle.attributes.get('Model', '')}"
    ).strip()

    contract = {
        "document_kind": "estimate_worksheet",
        "executable": False,
        "label": "Estimate worksheet - not a legal contract",
        "deal_id": deal_id,
        "customer_id": customer.id,
        "customer_name": customer_name or customer.id,
        "vehicle_id": vehicle.id,
        "vehicle_description": vehicle_description or vehicle.id,
        "vin": vehicle.attributes.get("VIN"),
        "sale_price": scenario["sale_price"],
        "trade_in_value": (trade_in.get("acv") if trade_in.get("acv") is not None else trade_in.get("value")) if trade_in else None,
        "down_payment": terms["down_payment"],
        "base_amount_financed": base_amount_financed,
        "fi_products_financed": round(fi_financed, 2),
        "fi_products": accepted_fi,
        "amount_financed": amount_financed,
        "apr": terms["apr"],
        "term_months": terms["term_months"],
        "base_monthly_payment": terms["monthly_payment"],
        "monthly_payment": monthly_payment,
        "financing_type": deal.attributes["financing_type"],
        "lender_name": lender.attributes.get("Name") if lender else None,
        "generated_at": _now(),
        "disclosures": [
            "This is a structured internal contract summary generated by NXTDeal for "
            "workflow purposes -- it is not a legally binding retail installment "
            "contract and does not replace state-required disclosure forms.",
        ],
    }

    deal.attributes["contract"] = contract
    deal.attributes["status"] = "contract"
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


def fund_deal(deal_id):
    """The one place this module writes outside the Deal entity itself -- creates a
    real FinanceContract entity and the exact relationship shape
    imports/finance_import.py already establishes (FINANCED_BY/OWNS/COVERS/FUNDED_BY),
    plus a PURCHASED relationship (imports/deal_import.py's shape) and marks the
    Vehicle sold. A funded Deal's FinanceContract is indistinguishable from imported
    historical data to every existing dashboard/profile view."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") != "contract":
        return {"error": f"Deal is '{deal.attributes.get('status')}', not ready to fund -- generate the contract first"}

    from core.contracting_readiness import execution_block
    blocked = execution_block("deal_fund")
    if blocked:
        return blocked

    customer_id = deal.attributes["customer_id"]
    vehicle_id = deal.attributes["vehicle_id"]
    lender_id = deal.attributes["lender_id"]
    contract = deal.attributes["contract"]

    finance_id = id_generator.generate("FIN")

    finance_entity = Entity(
        id=finance_id,
        entity_type=FINANCE_CONTRACT,
        attributes={
            "FinanceNumber": finance_id,
            "CustomerID": customer_id,
            "VIN": contract.get("vin"),
            "LenderName": contract.get("lender_name"),
            "SalePrice": str(contract["sale_price"]),
            "DownPayment": str(contract["down_payment"]),
            "AmountFinanced": str(contract["amount_financed"]),
            "APR": str(contract["apr"]),
            "TermMonths": str(contract["term_months"]),
            "MonthlyPayment": str(contract["monthly_payment"]),
            "FundingStatus": "Funded",
            "ContractDate": _today_iso(),
        },
    )

    ledger.add_entity(finance_entity)

    ledger.add_relationship(Relationship(source_id=customer_id, target_id=finance_id, relationship_type=FINANCED_BY))
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=vehicle_id, relationship_type=OWNS))
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=vehicle_id, relationship_type=PURCHASED))
    ledger.add_relationship(Relationship(source_id=finance_id, target_id=vehicle_id, relationship_type=COVERS))
    ledger.add_relationship(Relationship(source_id=finance_id, target_id=lender_id, relationship_type=FUNDED_BY))

    vehicle = ledger.get_entity(vehicle_id)
    vehicle.attributes["DateSold"] = _today_iso()

    deal.attributes["status"] = "funded"
    deal.attributes["finance_contract_id"] = finance_id
    deal.attributes["funded_at"] = _now()
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


_TRADE_APPRAISAL_FIELDS = {
    "vin", "year", "make", "model", "trim", "mileage", "condition",
    "photos", "recon_estimate", "acv", "market_value_estimate", "notes",
}


def update_trade_appraisal(deal_id, appraised_by, patch):
    """Trade Appraisal (sales.pdf's "Deals" item): VIN/year/make/model/trim/mileage,
    a plain condition note, a photo-URL list, a reconditioning cost estimate, and the
    two dollar figures a desk actually negotiates on -- Actual Cash Value (what the
    dealer will pay/allow) and a market-value estimate (what it should retail for).
    No real market-data API exists in this sandbox, so market_value_estimate is
    still a salesperson/appraiser-entered field, not auto-populated. A real VIN
    decoder exists as of NXTDeal VIN Intelligence Phase 2 (core/vin_decoder.py) --
    see decode_trade_in_vin() below for a read-only cross-check against whatever
    VIN/year/make an appraiser enters here; this function itself still never
    auto-writes a decode over an appraiser's own entered values, preserving their
    authority over the appraisal. Editable only pre-financing (same "desking is the
    editable window" rule as scenarios) so a trade's numbers can't shift after the
    customer has already been financed against them."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") != "desking":
        return {"error": f"Deal is '{deal.attributes.get('status')}', not in desking -- trade appraisal can only be edited during desking"}

    trade_in = dict(deal.attributes.get("trade_in") or {})

    for key, value in (patch or {}).items():
        if key in _TRADE_APPRAISAL_FIELDS:
            trade_in[key] = value

    trade_in["appraised_by"] = appraised_by
    trade_in["appraised_at"] = _now()
    trade_in["approved"] = False
    trade_in["approved_by"] = None
    trade_in["approved_at"] = None

    deal.attributes["trade_in"] = trade_in
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


def decode_trade_in_vin(deal_id, attempt_live=True):
    """NXTDeal VIN Intelligence, Phase 2: a real, read-only decision-support
    check for a trade-in -- decodes the VIN an appraiser entered on
    update_trade_appraisal() above and compares it against that same
    appraiser's own entered year/make, flagging real mismatches. Deliberately
    does NOT write anything back to the deal (no auto-populate, no silent
    overwrite) -- the appraiser stays the authority on the trade's own
    year/make/model/trim, exactly as update_trade_appraisal()'s own docstring
    states; this is a second opinion for the appraiser to act on themselves,
    not a mutation. Editable-only-during-desking doesn't apply here either,
    since nothing is edited -- this can be run at any point a trade_in with a
    VIN exists on the deal, including after financing, for anyone reviewing
    the file."""

    from core.vin_decoder import decode_vin

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    trade_in = deal.attributes.get("trade_in") or {}
    vin = (trade_in.get("vin") or "").strip()

    if not vin:
        return {"error": "This deal's trade-in has no VIN on file to decode."}

    decode = decode_vin(vin, attempt_live=attempt_live)

    entered_year = str(trade_in.get("year") or "").strip()
    entered_make = (trade_in.get("make") or "").strip()
    decoded_year = decode["resolved"].get("year")
    decoded_make = decode["resolved"].get("make")

    mismatches = []
    if decoded_year and entered_year and str(decoded_year) != entered_year:
        mismatches.append({
            "field": "year",
            "entered": entered_year,
            "decoded": str(decoded_year),
            "basis": decode["basis"].get("year"),
        })
    if decoded_make and entered_make and decoded_make.strip().lower() != entered_make.strip().lower():
        mismatches.append({
            "field": "make",
            "entered": entered_make,
            "decoded": decoded_make,
            "basis": decode["basis"].get("make"),
        })

    return {
        "deal_id": deal_id,
        "vin": vin,
        "valid_format": decode["valid_format"],
        "format_error": decode["format_error"],
        "check_digit_valid": decode["check_digit_valid"],
        "decoded": decode["resolved"],
        "mismatches": mismatches,
        "gap_note": decode["gap_note"],
        "note": (
            "Read-only decision support -- this never writes back to the trade "
            "appraisal. If a mismatch is real, the appraiser should correct it "
            "themselves via update_trade_appraisal()."
        ),
    }


def approve_trade_appraisal(deal_id, approved_by):
    """Manager approval workflow sales.pdf explicitly asks for on the trade appraisal
    -- a second set of eyes on the ACV before it's baked into a scenario/contract.
    Re-editing the appraisal (update_trade_appraisal above) resets approval, so an
    approval can never silently survive a numbers change."""

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    trade_in = deal.attributes.get("trade_in")

    if not trade_in:
        return {"error": "This deal has no trade appraisal to approve"}

    if trade_in.get("approved"):
        return {"error": "This trade appraisal is already approved"}

    trade_in["approved"] = True
    trade_in["approved_by"] = approved_by
    trade_in["approved_at"] = _now()

    deal.attributes["trade_in"] = trade_in
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


_DELIVERY_CHECKLIST_SECTIONS = ("vehicle_prep", "quality_control", "tech_setup", "documentation", "csi")


def update_delivery_checklist(deal_id, section, patch, updated_by):
    """Delivery Experience (session 102 follow-up) -- the last of Sales' original 4
    workflow-catalog jobs, and the one with the least existing data behind it: Deal had
    no delivery-prep/QC/tech-setup/documentation tracking at all before this. A real,
    lightweight per-section checklist (additive attribute, same convention as
    trade_in), not a fabricated read-only screen.

    The `csi` section's `review_requested` flag is honestly labeled, not a real send --
    no review-request dispatch mechanism (SMS/email) exists anywhere in this codebase
    (confirmed absent, same as core/marketing_menu.py's own review_requests
    not_yet_tracked note). Flipping it just marks the deal for review outreach and
    timestamps who/when, the same "simulate the action, label it honestly" precedent
    core/campaigns.py's activate_campaign() established."""

    if section not in _DELIVERY_CHECKLIST_SECTIONS:
        return {"error": f"section must be one of {list(_DELIVERY_CHECKLIST_SECTIONS)}"}

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    checklist = dict(deal.attributes.get("delivery_checklist") or {})
    current = dict(checklist.get(section) or {})

    current.update(patch or {})
    current["updated_by"] = updated_by
    current["updated_at"] = _now()

    if section == "csi" and (patch or {}).get("review_requested") and not checklist.get("csi", {}).get("review_requested"):
        current["review_requested_by"] = updated_by
        current["review_requested_at"] = _now()

    checklist[section] = current
    deal.attributes["delivery_checklist"] = checklist
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


def cancel_deal(deal_id):

    deal = get_deal(deal_id)

    if not deal:
        return {"error": "Deal not found"}

    if deal.attributes.get("status") in ("funded", "cancelled"):
        return {"error": f"Deal is already '{deal.attributes.get('status')}'"}

    deal.attributes["status"] = "cancelled"
    deal.attributes["updated_at"] = _now()
    save_graph(GRAPH_PATH)

    return deal


def list_deals(status=None, created_by=None):

    deals = _all_deals()

    if status:
        deals = [d for d in deals if d.attributes.get("status") == status]

    if created_by:
        deals = [d for d in deals if d.attributes.get("created_by") == created_by]

    # Same (created_at, id) tiebreaker as every other *_api.py list function in this
    # codebase (core/assets.py/core/campaigns.py/core/websites.py).
    deals.sort(key=lambda d: (d.attributes.get("created_at", ""), d.id), reverse=True)

    return deals


def list_pending_financing():
    """Deals awaiting a lender's decision -- the DMS equivalent of
    list_pending_approvals()/list_pending_campaigns()/list_pending_approvals() in the
    asset/campaign/website workflows."""

    return [d for d in _all_deals() if d.attributes.get("financing_status") == "submitted"]
