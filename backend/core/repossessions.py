"""
core/repossessions.py -- Finance's "Repossessions" item, the fourth slice of Sam's
Retail Automotive Lending Platform expansion (2026-07-17), the direct continuation of
Collections' own "repossession_referral" collection stage and Sam's own stated loan
lifecycle (Lead -> Deal -> Credit -> Approval -> Contract -> Funding -> Loan Servicing
-> Collections -> Repossession -> Recovery -> Payoff).

A RepossessionCase is a real, first-class lifecycle entity (referred -> assigned ->
located -> recovered -> stored -> disposed, with redeemed/cancelled as terminal
off-ramps at any point before disposal) -- not an additive dict on FinanceContract,
same "own lifecycle, not a dict on something else" reasoning Payment/DamageReport/
OperationsTask/LoanerAssignment already established in this codebase, since many
distinct real events (agent assignment, recovery, storage, disposition) happen over
one case's life.

The Referral Queue is deliberately NOT a new signal-detection pass -- it's real loans
already sitting in Collections' own "repossession_referral" collection stage
(core/collections.py, session 112 follow-up) with no open case yet. This module
doesn't re-decide who's a repo candidate, it works the queue Collections already
built.

Agent Assignment is honestly free-text (agent_name/agency/phone), same "vendor_name"
convention core/vehicle_lifecycle.py's assign_vendor() already established -- no
fabricated Recovery Agent roster exists anywhere in this codebase (confirmed absent,
same finding sessions 65/106 already made for Vendor generally). GPS location data is
deliberately NOT built here -- Sam scoped GPS & Device Management as its own separate
future Finance menu item in the original kickoff message; record_location() is a
plain, manually-entered location field, not a device pull, same "don't preempt a
separately-scoped future slice" discipline core/loan_servicing.py's own docstring
already applied to GPS/Starter-Interrupt/Repossessions when it shipped.

Storage fee accrual is real math (days elapsed since storage start * a real,
dealer-entered daily rate) -- no fabrication needed, same as recon/lot-fee
computations elsewhere in this codebase.

The Deficiency Balance -- "Recovery" in Sam's own lifecycle naming -- is 100% real
math over already-real-or-disclosed inputs: the loan's real-or-schedule-implied
current balance (core/loan_servicing.py's get_loan_financials()'s current_balance)
plus real recorded repo/storage/transport costs, minus the real recorded sale
proceeds. A negative result is a real surplus owed back to the customer, a positive
result is what the customer still owes -- standard BHPH/finance-company recovery
accounting, not simulated.

Redemption (the customer pays off/reinstates before disposal) is the real "Recovery"
alternate path -- it reactivates the loan via core/loan_servicing.py's own
set_loan_status(), the exact hook that module reserved for this slice since it
shipped ("Real mutation, reserved for future modules (Repossessions marking a loan
repossessed...)"). Disposition (auction/private sale) closes the loop the other way,
also via set_loan_status(loan_id, "repossessed", ...).
"""

from datetime import datetime, timezone, date

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import REPOSSESSION_CASE, FINANCE_CONTRACT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.loan_servicing import (
    _get_loan, _safe_float, _today, _customer_brief, _vehicle_brief,
    _linked_customer_id, _linked_vehicle_id, get_loan_financials, set_loan_status,
)

CASE_STAGES = ("referred", "assigned", "located", "recovered", "stored", "disposed")
TERMINAL_STAGES = ("disposed", "redeemed", "cancelled")
DISPOSITION_TYPES = ("auction_sale", "private_sale", "dealer_retail")

_STAGE_LABELS = {
    "referred": "Referred",
    "assigned": "Agent Assigned",
    "located": "Located",
    "recovered": "Recovered",
    "stored": "In Storage",
    "disposed": "Disposed",
    "redeemed": "Redeemed",
    "cancelled": "Cancelled",
}

_TRANSITIONS = {
    "referred": ("assigned", "cancelled", "redeemed"),
    "assigned": ("located", "cancelled", "redeemed"),
    "located": ("recovered", "cancelled", "redeemed"),
    "recovered": ("stored", "redeemed"),
    "stored": ("disposed", "redeemed"),
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _today_iso():
    return _today().isoformat()


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _all_cases():
    return [e for e in ledger.get_all().values() if e.entity_type == REPOSSESSION_CASE]


def _get_case(case_id):
    e = ledger.get_entity(case_id)
    if not e or e.entity_type != REPOSSESSION_CASE:
        return None
    return e


def _open_case_for_loan(loan_id):
    for c in _all_cases():
        if c.attributes.get("loan_id") == loan_id and c.attributes.get("stage") not in TERMINAL_STAGES:
            return c
    return None


def _case_brief(case):
    return {
        "id": case.id,
        "loan_id": case.attributes.get("loan_id"),
        "stage": case.attributes.get("stage"),
        "stage_label": _STAGE_LABELS.get(case.attributes.get("stage"), case.attributes.get("stage")),
        "referred_at": case.attributes.get("referred_at"),
        "referred_by": case.attributes.get("referred_by"),
        "agent_name": case.attributes.get("agent_name"),
    }


# ---------------------------------------------------------------------------
# Referral Queue -- real loans already in Collections' repossession_referral
# stage with no open case yet. Doesn't re-decide delinquency.
# ---------------------------------------------------------------------------

def get_referral_queue():
    from core.collections import get_collection_stage
    from core.loan_servicing import get_loan_status

    loans = [e for e in ledger.get_all().values() if e.entity_type == FINANCE_CONTRACT]
    rows = []

    for loan in loans:
        stage = get_collection_stage(loan.id)
        if stage != "repossession_referral":
            continue
        if _open_case_for_loan(loan.id):
            continue
        # A loan already marked repossessed/charged-off has already been through this
        # module (or a disposition already closed the vehicle out) -- it's not a real
        # NEW referral candidate anymore, even if it has no currently-open case.
        if get_loan_status(loan.id) in ("repossessed", "charged_off"):
            continue

        customer = _customer_brief(_linked_customer_id(loan))
        vehicle = _vehicle_brief(_linked_vehicle_id(loan))
        financials = get_loan_financials(loan.id)

        rows.append({
            "loan_id": loan.id,
            "finance_number": loan.attributes.get("FinanceNumber"),
            "customer_name": customer.get("name") if customer else None,
            "vehicle": f"{vehicle.get('year', '')} {vehicle.get('make', '')} {vehicle.get('model', '')}".strip() if vehicle else None,
            "current_balance": financials.get("current_balance") if isinstance(financials, dict) else None,
            "current_balance_basis": financials.get("current_balance_basis") if isinstance(financials, dict) else None,
        })

    return {"count": len(rows), "loans": rows}


# ---------------------------------------------------------------------------
# Case lifecycle
# ---------------------------------------------------------------------------

def create_case(loan_id, referred_by, reason=""):
    from core.loan_servicing import get_loan_status

    loan = _get_loan(loan_id)
    if not loan:
        return {"error": f"Loan '{loan_id}' not found"}

    existing = _open_case_for_loan(loan_id)
    if existing:
        return {"error": f"Loan '{loan_id}' already has an open repossession case ({existing.id})"}

    current_status = get_loan_status(loan_id)
    if current_status in ("repossessed", "charged_off"):
        return {"error": f"Loan '{loan_id}' is already marked '{current_status}' -- see its existing repossession case history rather than opening a new case."}

    case_id = id_generator.generate("REPO")
    customer_id = _linked_customer_id(loan)
    vehicle_id = _linked_vehicle_id(loan)
    financials = get_loan_financials(loan_id)

    case = Entity(
        id=case_id,
        entity_type=REPOSSESSION_CASE,
        attributes={
            "loan_id": loan_id,
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "stage": "referred",
            "reason": reason,
            "referred_by": referred_by,
            "referred_at": _now(),
            "balance_at_referral": financials.get("current_balance") if isinstance(financials, dict) else None,
            "balance_at_referral_basis": financials.get("current_balance_basis") if isinstance(financials, dict) else None,
            "agent_name": None,
            "agent_agency": None,
            "agent_phone": None,
            "location": None,
            "recovered_at": None,
            "recovered_condition": None,
            "recovered_odometer": None,
            "storage_facility": None,
            "storage_start_date": None,
            "storage_daily_rate": None,
            "transport_cost": 0.0,
            "disposition": None,
            "stage_history": [{"stage": "referred", "by": referred_by, "reason": reason, "at": _now()}],
        },
    )

    ledger.add_entity(case)
    save_graph(GRAPH_PATH)

    return case


def _advance(case_id, stage, by, reason="", extra_attrs=None):
    case = _get_case(case_id)
    if not case:
        return {"error": f"Repossession case '{case_id}' not found"}

    current = case.attributes.get("stage")
    if current in TERMINAL_STAGES:
        return {"error": f"Case is already in a terminal stage ('{current}') -- cannot advance further"}

    allowed = _TRANSITIONS.get(current, ())
    if stage not in allowed:
        return {"error": f"Cannot move from '{current}' to '{stage}' -- valid next stages are {allowed}"}

    case.attributes["stage"] = stage
    if extra_attrs:
        case.attributes.update(extra_attrs)
    case.attributes.setdefault("stage_history", []).append({"stage": stage, "by": by, "reason": reason, "at": _now()})
    save_graph(GRAPH_PATH)

    return case


def assign_agent(case_id, agent_name, by, agency="", phone=""):
    if not agent_name:
        return {"error": "agent_name is required"}
    return _advance(case_id, "assigned", by, extra_attrs={"agent_name": agent_name, "agent_agency": agency, "agent_phone": phone})


def record_location(case_id, location, by, notes=""):
    if not location:
        return {"error": "location is required"}
    return _advance(case_id, "located", by, reason=notes, extra_attrs={"location": location})


def record_recovery(case_id, by, recovered_date=None, condition="", odometer=None):
    return _advance(
        case_id, "recovered", by,
        extra_attrs={
            "recovered_at": recovered_date or _today_iso(),
            "recovered_condition": condition,
            "recovered_odometer": odometer,
        },
    )


def record_storage(case_id, storage_facility, by, storage_start_date=None, daily_rate=0.0, transport_cost=0.0):
    if not storage_facility:
        return {"error": "storage_facility is required"}
    return _advance(
        case_id, "stored", by,
        extra_attrs={
            "storage_facility": storage_facility,
            "storage_start_date": storage_start_date or _today_iso(),
            "storage_daily_rate": _safe_float(daily_rate),
            "transport_cost": _safe_float(transport_cost),
        },
    )


def _storage_fees_accrued(case):
    start = _parse_date(case.attributes.get("storage_start_date"))
    rate = _safe_float(case.attributes.get("storage_daily_rate"))
    if not start or rate <= 0:
        return 0.0
    end_str = case.attributes.get("disposition", {}).get("sale_date") if isinstance(case.attributes.get("disposition"), dict) else None
    end = _parse_date(end_str) or _today()
    days = max(0, (end - start).days)
    return round(days * rate, 2)


def compute_deficiency_balance(case_id):
    """Real math, no simulation: real outstanding loan balance (schedule-implied or
    real-payment-ledger-derived, whichever core/loan_servicing.py's own
    get_loan_financials() currently prefers) plus real recorded repo/storage/transport
    costs, minus real recorded sale proceeds. Positive = customer owes a deficiency,
    negative = a real surplus owed back to the customer."""

    case = _get_case(case_id)
    if not case:
        return {"error": f"Repossession case '{case_id}' not found"}

    loan_id = case.attributes.get("loan_id")
    financials = get_loan_financials(loan_id)
    if not isinstance(financials, dict) or "error" in financials:
        return financials

    outstanding_balance = financials.get("current_balance") or 0.0
    storage_fees = _storage_fees_accrued(case)
    transport_cost = _safe_float(case.attributes.get("transport_cost"))

    disposition = case.attributes.get("disposition") or {}
    sale_price = _safe_float(disposition.get("sale_price"))

    deficiency = round(outstanding_balance + storage_fees + transport_cost - sale_price, 2)

    return {
        "case_id": case_id,
        "loan_id": loan_id,
        "outstanding_balance": outstanding_balance,
        "outstanding_balance_basis": financials.get("current_balance_basis"),
        "storage_fees_accrued": storage_fees,
        "transport_cost": transport_cost,
        "sale_price": sale_price,
        "deficiency_balance": deficiency,
        "note": (
            "Positive deficiency_balance is what the customer still owes after sale "
            "proceeds and recovery costs; a negative value is a real surplus owed back "
            "to the customer. Real math over the loan's real-or-schedule-implied "
            "balance plus real recorded costs -- no fabrication."
        ),
    }


def record_disposition(case_id, disposition_type, sale_price, by, sale_date=None, buyer="", notes=""):
    if disposition_type not in DISPOSITION_TYPES:
        return {"error": f"disposition_type must be one of {DISPOSITION_TYPES}"}

    case = _get_case(case_id)
    if not case:
        return {"error": f"Repossession case '{case_id}' not found"}

    if case.attributes.get("stage") != "stored":
        return {"error": "A case must be in 'stored' before it can be disposed"}

    disposition = {
        "disposition_type": disposition_type,
        "sale_price": _safe_float(sale_price),
        "sale_date": sale_date or _today_iso(),
        "buyer": buyer,
        "notes": notes,
        "recorded_by": by,
    }

    result = _advance(case_id, "disposed", by, reason=notes, extra_attrs={"disposition": disposition})
    if isinstance(result, dict) and "error" in result:
        return result

    loan_id = case.attributes.get("loan_id")
    set_loan_status(loan_id, "repossessed", by, reason=f"Repossession case {case_id} disposed ({disposition_type})")

    deficiency = compute_deficiency_balance(case_id)
    case.attributes["deficiency_balance"] = deficiency.get("deficiency_balance") if isinstance(deficiency, dict) else None
    save_graph(GRAPH_PATH)

    return result


def redeem_case(case_id, redemption_amount, by, notes=""):
    """The real 'Recovery' alternate path -- the customer pays off/reinstates before
    disposal. Reactivates the loan via loan_servicing.set_loan_status()."""

    case = _get_case(case_id)
    if not case:
        return {"error": f"Repossession case '{case_id}' not found"}

    if case.attributes.get("stage") in ("disposed",):
        return {"error": "Cannot redeem a case that has already been disposed"}
    if case.attributes.get("stage") in TERMINAL_STAGES:
        return {"error": f"Case is already in a terminal stage ('{case.attributes.get('stage')}')"}

    case.attributes["stage"] = "redeemed"
    case.attributes["redemption_amount"] = _safe_float(redemption_amount)
    case.attributes.setdefault("stage_history", []).append({"stage": "redeemed", "by": by, "reason": notes, "at": _now()})
    save_graph(GRAPH_PATH)

    loan_id = case.attributes.get("loan_id")
    set_loan_status(loan_id, "active", by, reason=f"Redeemed from repossession case {case_id}")

    return case


def cancel_case(case_id, by, reason=""):
    case = _get_case(case_id)
    if not case:
        return {"error": f"Repossession case '{case_id}' not found"}
    if case.attributes.get("stage") in TERMINAL_STAGES:
        return {"error": f"Case is already in a terminal stage ('{case.attributes.get('stage')}')"}

    case.attributes["stage"] = "cancelled"
    case.attributes.setdefault("stage_history", []).append({"stage": "cancelled", "by": by, "reason": reason, "at": _now()})
    save_graph(GRAPH_PATH)

    return case


def get_case(case_id):
    case = _get_case(case_id)
    if not case:
        return {"error": f"Repossession case '{case_id}' not found"}

    loan_id = case.attributes.get("loan_id")
    financials = get_loan_financials(loan_id)
    deficiency = compute_deficiency_balance(case_id) if case.attributes.get("stage") in ("stored", "disposed") else None

    return {
        "id": case.id,
        "loan_id": loan_id,
        "customer": _customer_brief(case.attributes.get("customer_id")),
        "vehicle": _vehicle_brief(case.attributes.get("vehicle_id")),
        "current_balance": financials.get("current_balance") if isinstance(financials, dict) else None,
        "current_balance_basis": financials.get("current_balance_basis") if isinstance(financials, dict) else None,
        **case.attributes,
        "storage_fees_accrued": _storage_fees_accrued(case),
        "deficiency": deficiency,
    }


def list_cases(status=None, loan_id=None):
    cases = _all_cases()
    if status:
        cases = [c for c in cases if c.attributes.get("stage") == status]
    if loan_id:
        cases = [c for c in cases if c.attributes.get("loan_id") == loan_id]
    cases.sort(key=lambda c: c.attributes.get("referred_at") or "", reverse=True)
    return {"count": len(cases), "cases": [_case_brief(c) for c in cases]}


def get_case_history_for_loan(loan_id):
    """Real, composed event list for core/loan_servicing.py's get_loan_timeline() --
    every stage transition across every repossession case this loan has ever had."""

    cases = [c for c in _all_cases() if c.attributes.get("loan_id") == loan_id]
    events = []
    for case in cases:
        for h in case.attributes.get("stage_history", []):
            events.append({
                "type": "repossession_stage",
                "at": h.get("at"),
                "note": f"Case {case.id}: stage set to '{_STAGE_LABELS.get(h.get('stage'), h.get('stage'))}' by {h.get('by')}" + (f" -- {h.get('reason')}" if h.get("reason") else ""),
            })
    return events


def get_recovery_stats():
    """Real recovery-rate math across every disposed case (2026-07-18, Network's
    BHPH Benchmarks slice, core/network_benchmark.py) -- sum of real recorded sale
    proceeds vs. the real total amount owed at disposition. Since
    compute_deficiency_balance() defines deficiency_balance = amount_owed -
    sale_price, amount_owed = sale_price + deficiency_balance is real math over
    already-real/recorded fields, not a fabricated ratio. A recovery_rate_pct above
    100% is a real, honest signal that this dealer's disposed units net-recovered a
    surplus on average, not a bug."""

    disposed = [c for c in _all_cases() if c.attributes.get("stage") == "disposed"]

    total_sale_price = 0.0
    total_owed = 0.0

    for case in disposed:
        disposition = case.attributes.get("disposition") or {}
        sale_price = _safe_float(disposition.get("sale_price"))
        deficiency = case.attributes.get("deficiency_balance")
        deficiency = _safe_float(deficiency) if deficiency is not None else 0.0

        total_sale_price += sale_price
        total_owed += sale_price + deficiency

    recovery_rate_pct = round(total_sale_price / total_owed * 100, 2) if total_owed else None

    return {
        "disposed_case_count": len(disposed),
        "total_sale_price": round(total_sale_price, 2),
        "total_amount_owed_at_disposition": round(total_owed, 2),
        "recovery_rate_pct": recovery_rate_pct,
        "note": (
            "Real math: recovery_rate_pct = total real recorded sale proceeds / "
            "total real amount owed at disposition (sale_price + deficiency_balance "
            "per case). recovery_rate_pct is null (not zero) when no case has been "
            "disposed yet -- see disposed_case_count."
        ),
    }


def get_repossessions_dashboard():
    cases = _all_cases()
    open_cases = [c for c in cases if c.attributes.get("stage") not in TERMINAL_STAGES]

    stage_counts = {s: 0 for s in CASE_STAGES}
    for c in open_cases:
        stage = c.attributes.get("stage")
        if stage in stage_counts:
            stage_counts[stage] += 1

    disposed = [c for c in cases if c.attributes.get("stage") == "disposed"]
    redeemed = [c for c in cases if c.attributes.get("stage") == "redeemed"]

    total_deficiency = round(sum(_safe_float(c.attributes.get("deficiency_balance")) for c in disposed if c.attributes.get("deficiency_balance") is not None), 2)

    referral_queue = get_referral_queue()

    return {
        "referral_queue_count": referral_queue["count"],
        "open_cases": len(open_cases),
        "stage_counts": stage_counts,
        "disposed_count": len(disposed),
        "redeemed_count": len(redeemed),
        "total_deficiency_outstanding": total_deficiency,
    }
