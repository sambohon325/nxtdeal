"""
core/asset_management.py -- Finance's "Assets" item, the sixth slice of Sam's Retail
Automotive Lending Platform expansion (2026-07-17), and the last explicitly-named
item on Sam's original 13-item Finance menu spec before the broader Compliance/
Accounting/Commissions/Reporting extensions. In a retail lending platform, "Assets"
means Collateral / Asset Management -- the vehicle securing each loan is the lender's
real asset, and this module tracks the three things a real finance company actually
manages about that collateral: Title & Lien status, Insurance (loss-payee) coverage,
and Collateral Valuation / Loan-to-Value.

Deliberately NOT a new entity type for Lien/Insurance -- a handful of additive
attributes on the existing FinanceContract (lien_status/lienholder_name/
lien_released_at, insurance dict), same convention as core/deals.py's
trade_in/delivery_checklist/core/fi_products.py's fi_products, since these are a few
real fields per loan rather than a first-class object with its own many-event
lifecycle (unlike Payment/RepossessionCase/InstalledDevice elsewhere in this arc).

Title status is REAL, reusing core/document_workflows.py's existing
get_title_status(vehicle_id) verbatim -- the same categorized Document-vault
completeness check core/inventory_menu.py's wholesale() and this arc's own
Repossessions slice already established as the honest Title-on-file signal. No
second title-tracking mechanism is built here.

Lien tracking is REAL: every funded loan starts with an implicit active lien in favor
of the dealer/lender (lienholder_name defaults to the linked Lender's real name, or
"Dealer / In-House Financing" for BHPH loans with no linked Lender), computed on
first read the same computed-default-then-real-value convention as loan_status
itself. release_lien() is a real, gated mutation -- it refuses to run unless the
loan's own real loan_status (core/loan_servicing.py) is already "paid_off", since
releasing a lien on an active loan would be a real compliance problem, not a UI
nicety.

Insurance is REAL, dealer-entered data (carrier/policy_number/expiration_date/
loss_payee_confirmed) -- unlike a real-time insurance-verification API (which this
sandbox has no path to), a dealer/finance company genuinely does keep this on file
manually today, so there's no reason to fabricate or skip it. is_lapsed is real math
(expiration_date < today), not simulated.

Collateral Valuation blends a REAL book value (the collateral vehicle's own real
Vehicle.Price, confirmed present on all 315 real FinanceContract-linked vehicles in
this seed) with core/pricing_desk.py's existing SIMULATED current-market-value engine
(get_market_pricing(), reused directly rather than a second simulated-pricing
mechanism) to compute a real, honestly-labeled Loan-to-Value ratio per loan --
current_balance (real-or-schedule-implied, from core/loan_servicing.py) divided by
the SIMULATED current market value. LTV itself is therefore a real ratio computed
over one real and one simulated input, and is labeled accordingly.
"""

from datetime import date

from core.dealeros import ledger
from core.entity_types import FINANCE_CONTRACT, LENDER
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.loan_servicing import (
    _get_loan, _safe_float, _today, _linked_vehicle_id, _linked_lender_id,
    get_loan_status, get_loan_financials,
)
from core.document_workflows import get_title_status
from core.pricing_desk import get_market_pricing
from core.vin_decoder import check_vehicle_vin_match

LIEN_STATUSES = ("active", "released")

_DEFAULT_LIENHOLDER = "Dealer / In-House Financing"


def _now_date_iso():
    return _today().isoformat()


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _all_loans():
    return [e for e in ledger.get_all().values() if e.entity_type == FINANCE_CONTRACT]


def _default_lienholder(loan):
    lender_id = _linked_lender_id(loan)
    if lender_id:
        lender = ledger.get_entity(lender_id)
        if lender and lender.entity_type == LENDER:
            return lender.attributes.get("Name") or _DEFAULT_LIENHOLDER
    return _DEFAULT_LIENHOLDER


# ---------------------------------------------------------------------------
# Lien
# ---------------------------------------------------------------------------

def get_lien_status(loan_id):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    stored_status = loan.attributes.get("lien_status")
    status = stored_status if stored_status in LIEN_STATUSES else "active"
    lienholder = loan.attributes.get("lienholder_name") or _default_lienholder(loan)

    return {
        "loan_id": loan_id,
        "lien_status": status,
        "lienholder_name": lienholder,
        "lien_released_at": loan.attributes.get("lien_released_at"),
        "lien_released_by": loan.attributes.get("lien_released_by"),
        "is_stored_value": stored_status is not None,
    }


def update_lienholder(loan_id, lienholder_name, by):
    if not lienholder_name:
        return {"error": "lienholder_name is required"}

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    loan.attributes["lienholder_name"] = lienholder_name
    loan.attributes.setdefault("lienholder_history", []).append({"lienholder_name": lienholder_name, "by": by})
    save_graph(GRAPH_PATH)

    return get_lien_status(loan_id)


def release_lien(loan_id, by, reason=""):
    """Real, enforced gate: refuses to release a lien unless the loan's own real
    loan_status is already 'paid_off' -- releasing a lien on an active loan is a
    real compliance problem, not a UI nicety."""

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    current = get_lien_status(loan_id)
    if current["lien_status"] == "released":
        return {"error": "Lien is already released"}

    loan_status = get_loan_status(loan_id)
    if loan_status != "paid_off":
        return {"error": f"Cannot release a lien on a loan that is not paid off (current loan_status: '{loan_status}')"}

    loan.attributes["lien_status"] = "released"
    loan.attributes["lien_released_at"] = _now_date_iso()
    loan.attributes["lien_released_by"] = by
    loan.attributes["lien_release_reason"] = reason
    save_graph(GRAPH_PATH)

    return get_lien_status(loan_id)


# ---------------------------------------------------------------------------
# Insurance -- real, dealer-entered
# ---------------------------------------------------------------------------

def get_insurance_status(loan_id):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    insurance = loan.attributes.get("insurance")
    if not insurance:
        return {"loan_id": loan_id, "on_file": False, "note": "No insurance information on file for this loan yet."}

    expiration = _parse_date(insurance.get("expiration_date"))
    is_lapsed = bool(expiration and expiration < _today())

    return {
        "loan_id": loan_id,
        "on_file": True,
        "carrier": insurance.get("carrier"),
        "policy_number": insurance.get("policy_number"),
        "expiration_date": insurance.get("expiration_date"),
        "loss_payee_confirmed": insurance.get("loss_payee_confirmed", False),
        "is_lapsed": is_lapsed,
        "updated_by": insurance.get("updated_by"),
        "updated_at": insurance.get("updated_at"),
    }


def update_insurance(loan_id, carrier, policy_number, expiration_date, loss_payee_confirmed, by):
    if not carrier or not policy_number or not expiration_date:
        return {"error": "carrier, policy_number, and expiration_date are all required"}
    if not _parse_date(expiration_date):
        return {"error": "expiration_date must be a valid date (YYYY-MM-DD)"}

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    loan.attributes["insurance"] = {
        "carrier": carrier,
        "policy_number": policy_number,
        "expiration_date": expiration_date,
        "loss_payee_confirmed": bool(loss_payee_confirmed),
        "updated_by": by,
        "updated_at": _now_date_iso(),
    }
    save_graph(GRAPH_PATH)

    return get_insurance_status(loan_id)


# ---------------------------------------------------------------------------
# Collateral Valuation & LTV -- real book value + SIMULATED market value
# ---------------------------------------------------------------------------

def get_collateral_valuation(loan_id):
    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    vehicle_id = _linked_vehicle_id(loan)
    if not vehicle_id:
        return {"error": f"Loan '{loan_id}' has no linked vehicle -- cannot value collateral"}

    vehicle = ledger.get_entity(vehicle_id)
    book_value = _safe_float(vehicle.attributes.get("Price")) if vehicle else None

    # Phase 2 of NXTDeal VIN Intelligence: a real, in-process cross-check
    # (no HTTP round-trip, no new route needed) confirming the vehicle
    # securing this loan is actually who its own VIN says it is -- a real
    # collateral-integrity signal for Finance, distinct from and additive to
    # book_value/market_value above.
    vin_match, _vin_match_error = check_vehicle_vin_match(vehicle_id) if vehicle_id else (None, None)

    market = get_market_pricing(vehicle_id)
    market_value = market.get("market_avg_price") if isinstance(market, dict) else None

    financials = get_loan_financials(loan_id)
    current_balance = financials.get("current_balance") if isinstance(financials, dict) else None

    ltv = None
    if current_balance is not None and market_value:
        ltv = round((current_balance / market_value) * 100, 1)

    return {
        "loan_id": loan_id,
        "vehicle_id": vehicle_id,
        "book_value": book_value,
        "book_value_basis": "real_vehicle_price",
        "market_value": market_value,
        "market_value_basis": market.get("basis") if isinstance(market, dict) else None,
        "current_balance": current_balance,
        "current_balance_basis": financials.get("current_balance_basis") if isinstance(financials, dict) else None,
        "loan_to_value_pct": ltv,
        "vin_match": vin_match,
        "note": (
            "book_value is real (the vehicle's own on-file Price). market_value is "
            "SIMULATED (core/pricing_desk.py's market-pricing engine -- no real "
            "market-data feed is connected in this sandbox). loan_to_value_pct is a "
            "real ratio computed over one real input (current_balance) and one "
            "simulated input (market_value)."
        ),
    }


def get_asset_summary(loan_id):
    """The composed per-loan Assets view: Title, Lien, Insurance, Valuation."""

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    vehicle_id = _linked_vehicle_id(loan)

    return {
        "loan_id": loan_id,
        "title": get_title_status(vehicle_id) if vehicle_id else {"error": "No linked vehicle"},
        "lien": get_lien_status(loan_id),
        "insurance": get_insurance_status(loan_id),
        "valuation": get_collateral_valuation(loan_id),
    }


# ---------------------------------------------------------------------------
# Portfolio-wide dashboard
# ---------------------------------------------------------------------------

def get_asset_portfolio_dashboard():
    loans = _all_loans()

    total_book_value = 0.0
    total_market_value = 0.0
    total_outstanding = 0.0
    ltv_values = []
    missing_title_count = 0
    lapsed_insurance_count = 0
    no_insurance_count = 0
    active_lien_count = 0
    released_lien_count = 0

    for loan in loans:
        valuation = get_collateral_valuation(loan.id)
        if isinstance(valuation, dict) and "error" not in valuation:
            if valuation.get("book_value"):
                total_book_value += valuation["book_value"]
            if valuation.get("market_value"):
                total_market_value += valuation["market_value"]
            if valuation.get("current_balance"):
                total_outstanding += valuation["current_balance"]
            if valuation.get("loan_to_value_pct") is not None:
                ltv_values.append(valuation["loan_to_value_pct"])

        vehicle_id = _linked_vehicle_id(loan)
        title = get_title_status(vehicle_id) if vehicle_id else None
        if isinstance(title, dict) and not title.get("is_complete", True):
            missing_title_count += 1

        insurance = get_insurance_status(loan.id)
        if not insurance.get("on_file"):
            no_insurance_count += 1
        elif insurance.get("is_lapsed"):
            lapsed_insurance_count += 1

        lien = get_lien_status(loan.id)
        if lien["lien_status"] == "active":
            active_lien_count += 1
        else:
            released_lien_count += 1

    avg_ltv = round(sum(ltv_values) / len(ltv_values), 1) if ltv_values else None

    return {
        "total_loans": len(loans),
        "total_book_value": round(total_book_value, 2),
        "total_market_value": round(total_market_value, 2),
        "total_market_value_basis": "simulated_market_data",
        "total_outstanding_balance": round(total_outstanding, 2),
        "average_loan_to_value_pct": avg_ltv,
        "missing_title_count": missing_title_count,
        "lapsed_insurance_count": lapsed_insurance_count,
        "no_insurance_on_file_count": no_insurance_count,
        "active_lien_count": active_lien_count,
        "released_lien_count": released_lien_count,
        "note": "total_market_value and average_loan_to_value_pct rest partly on "
                "core/pricing_desk.py's SIMULATED market pricing -- see individual "
                "loan valuations for the real/simulated breakdown of each figure.",
    }
