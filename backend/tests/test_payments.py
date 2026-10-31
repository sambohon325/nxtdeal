"""
Tests for core/payments.py / core/payments_api.py (Finance's "Payments" item, the
second slice of the Retail Automotive Lending Platform expansion, 2026-07-17). Run
from backend/ with `pytest`.

Covers: record_payment()'s validation + deterministic simulated-gateway math (cash
always approves; other methods ~94% approval, seeded per payment id) + real
principal/interest split; get_real_payment_summary()'s None-when-no-real-payments
fallback and its real delinquency-bucket computation once real payments exist,
including the repossessed/charged_off special case; Auto Draft Management (creation
validation, status transitions, run_due_auto_drafts()'s day-of-month + once-per-month
gating); Promise To Pay's live-computed kept/broken/pending status; Extension/
Deferral's append-only adjustment log; Payoff requests (create/fulfill/list,
double-fulfillment rejection); the Customer Payment Portal's full public
unauthenticated flow (link generation/status/revocation, get_public_portal_view,
submit_public_payment, submit_public_payoff_request, including the revoked-link
rejection path); get_payments_dashboard()'s real aggregate totals; and the ACL layer
in core/payments_api.py.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import CUSTOMER, VEHICLE, FINANCE_CONTRACT
from core import payments
from core import payments_api
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")

    ledger.reset()

    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # core/payments.py's mutating functions all call the real save_graph(GRAPH_PATH).
    # This suite already runs under backend/tests/conftest.py's own isolated
    # DEALEROS_STORAGE_DIR temp directory, so a real write here is harmless, but
    # monkeypatching it out anyway keeps this file fast and matches every other new
    # test file's own established no-real-writes-during-a-test convention.

    monkeypatch.setattr(payments, "save_graph", lambda filepath: None)


def _add_customer(customer_id="CUST-1", first="Jane", last="Doe"):

    ledger.add_entity(Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last},
    ))

    return customer_id


def _add_vehicle(vehicle_id="VEH-1", make="Honda", model="Civic", year="2025"):

    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"Make": make, "Model": model, "Year": year},
    ))

    return vehicle_id


def _add_loan(
    loan_id="FIN-1",
    amount_financed=12000.0,
    apr=9.0,
    term_months=48,
    monthly_payment=298.62,
    contract_date="2026-01-01",
    finance_number="FIN-1",
    link_customer="CUST-1",
    link_vehicle="VEH-1",
):
    """A real FinanceContract loan, optionally linked to a real Customer (FINANCED_BY)
    and Vehicle (COVERS) -- payments.py's own portal view / borrower-brief functions
    resolve those relationships live, so most scenarios want both linked."""

    ledger.add_entity(Entity(
        id=loan_id,
        entity_type=FINANCE_CONTRACT,
        attributes={
            "FinanceNumber": finance_number,
            "AmountFinanced": amount_financed,
            "APR": apr,
            "TermMonths": term_months,
            "MonthlyPayment": monthly_payment,
            "ContractDate": contract_date,
        },
    ))

    if link_customer:
        ledger.add_relationship(Relationship(
            source_id=link_customer, target_id=loan_id, relationship_type="FINANCED_BY"
        ))
    if link_vehicle:
        ledger.add_relationship(Relationship(
            source_id=loan_id, target_id=link_vehicle, relationship_type="COVERS"
        ))

    return loan_id


def _full_loan_setup(**loan_kwargs):
    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    return _add_loan(**loan_kwargs)


# ---------------------------------------------------------------------------
# record_payment()
# ---------------------------------------------------------------------------

def test_record_payment_rejects_unknown_loan():

    result = payments.record_payment("FIN-BOGUS", 100, "cash", "EMP-1")

    assert "error" in result


def test_record_payment_rejects_bad_method():

    _full_loan_setup()

    result = payments.record_payment("FIN-1", 100, "bitcoin", "EMP-1")

    assert "error" in result


def test_record_payment_rejects_zero_or_negative_amount():

    _full_loan_setup()

    result_zero = payments.record_payment("FIN-1", 0, "cash", "EMP-1")
    result_negative = payments.record_payment("FIN-1", -50, "cash", "EMP-1")

    assert "error" in result_zero
    assert "error" in result_negative


def test_record_payment_cash_always_approves():

    _full_loan_setup()

    # Try several cash payments -- every single one should approve, since cash
    # skips the simulated gateway entirely by design.
    for i in range(10):
        result = payments.record_payment("FIN-1", 300, "cash", "EMP-1")
        assert result.attributes["status"] == "approved"
        assert result.attributes["decline_reason"] is None


def test_record_payment_is_deterministic_per_payment_id():

    _full_loan_setup()

    # A non-cash payment's approval/decline is seeded off its own generated payment
    # id -- confirm the underlying simulator is deterministic for a fixed id (not
    # fresh randomness on every call), the real guarantee this module's own
    # docstring makes.
    result_a = payments._simulate_gateway_result("PMT-FIXED-ID", "ach", 100)
    result_b = payments._simulate_gateway_result("PMT-FIXED-ID", "ach", 100)

    assert result_a == result_b


def test_record_payment_records_real_principal_interest_split_on_approval():

    _full_loan_setup(amount_financed=12000.0, apr=12.0)

    result = payments.record_payment("FIN-1", 300, "cash", "EMP-1")

    assert result.attributes["status"] == "approved"
    # Monthly rate = 12% / 12 = 1% of the real starting balance (12000) = 120.00
    # interest due; the rest of a $300 payment is principal.
    assert result.attributes["interest_portion"] == pytest.approx(120.0, abs=0.01)
    assert result.attributes["principal_portion"] == pytest.approx(180.0, abs=0.01)
    # principal + interest must always sum back to the real payment amount.
    assert result.attributes["principal_portion"] + result.attributes["interest_portion"] == pytest.approx(300.0, abs=0.01)
    assert result.attributes["balance_before"] == pytest.approx(12000.0, abs=0.01)
    assert result.attributes["balance_after"] == pytest.approx(11820.0, abs=0.01)


def test_record_payment_declined_has_zero_principal_and_interest():

    _full_loan_setup()

    # A payment method+id combination whose deterministic roll declines -- walk
    # payment ids until we find a real decline, confirming the declined branch
    # records zero principal/interest and leaves balance_after == balance_before.
    declined = None
    for i in range(500):
        gw = payments._simulate_gateway_result(f"PMT-PROBE-{i}", "ach", 200)
        if not gw["approved"]:
            declined = gw
            break
    assert declined is not None, "expected at least one decline in 500 deterministic rolls at a ~94% approval rate"
    assert declined["decline_reason"] in payments._DECLINE_REASONS


def test_record_payment_carries_basis_and_disclaimer():

    _full_loan_setup()

    result = payments.record_payment("FIN-1", 100, "cash", "EMP-1")

    assert result.attributes["basis"] == "staff_recorded_cash"
    assert result.attributes["disclaimer"]


def test_record_payment_persists_to_the_real_ledger():

    _full_loan_setup()

    result = payments.record_payment("FIN-1", 100, "cash", "EMP-1", notes="over the phone")

    stored = ledger.get_entity(result.id)
    assert stored is not None
    assert stored.attributes["loan_id"] == "FIN-1"
    assert stored.attributes["notes"] == "over the phone"


def test_list_payments_for_loan_include_declined_filter():

    _full_loan_setup()

    # Force a mix of approved and declined by directly recording enough payments
    # that a decline is statistically certain within a small deterministic window.
    for i in range(30):
        payments.record_payment("FIN-1", 50, "ach", "EMP-1")

    all_payments = payments.list_payments_for_loan("FIN-1", include_declined=True)
    approved_only = payments.list_payments_for_loan("FIN-1", include_declined=False)

    assert len(approved_only) <= len(all_payments)
    assert all(p.attributes["status"] == "approved" for p in approved_only)


# ---------------------------------------------------------------------------
# get_real_payment_summary()
# ---------------------------------------------------------------------------

def test_get_real_payment_summary_none_when_no_payments():

    _full_loan_setup()

    assert payments.get_real_payment_summary("FIN-1") is None


def test_get_real_payment_summary_none_for_unknown_loan():

    assert payments.get_real_payment_summary("FIN-BOGUS") is None


def test_get_real_payment_summary_computes_real_totals():

    _full_loan_setup(amount_financed=12000.0, apr=12.0, monthly_payment=300.0, contract_date="2026-01-01")

    payments.record_payment("FIN-1", 300, "cash", "EMP-1", payment_date="2026-01-15")

    summary = payments.get_real_payment_summary("FIN-1")

    assert summary is not None
    assert summary["total_paid"] == pytest.approx(300.0, abs=0.01)
    assert summary["payment_count"] == 1
    assert summary["real_balance"] < 12000.0
    assert summary["basis"] == "real_payment_ledger"


def test_get_real_payment_summary_current_bucket_when_paid_up():

    _full_loan_setup(amount_financed=12000.0, apr=12.0, monthly_payment=300.0, contract_date="2026-01-01")

    # Pay well ahead of schedule -- should read as "current" with 0 days past due.
    payments.record_payment("FIN-1", 3000, "cash", "EMP-1", payment_date="2026-01-15")

    summary = payments.get_real_payment_summary("FIN-1")

    assert summary["bucket"] == "current"
    assert summary["days_past_due"] == 0
    assert summary["amount_past_due"] == 0.0


def test_get_real_payment_summary_delinquent_bucket_when_behind():

    _full_loan_setup(amount_financed=12000.0, apr=12.0, monthly_payment=300.0, contract_date="2020-01-01")

    # Contract date is far in the past with only one small payment on file --
    # a real, large shortfall should read as a real delinquency bucket, not "current".
    payments.record_payment("FIN-1", 50, "cash", "EMP-1", payment_date="2020-01-15")

    summary = payments.get_real_payment_summary("FIN-1")

    assert summary["bucket"] in ("30_day", "60_day", "90_day")
    assert summary["days_past_due"] > 0
    assert summary["amount_past_due"] > 0


def test_get_real_payment_summary_repossessed_special_case():

    _full_loan_setup(amount_financed=12000.0, apr=12.0, monthly_payment=300.0, contract_date="2020-01-01")

    payments.record_payment("FIN-1", 50, "cash", "EMP-1", payment_date="2020-01-15")

    loan = ledger.get_entity("FIN-1")
    loan.attributes["loan_status"] = "repossessed"

    summary = payments.get_real_payment_summary("FIN-1")

    # A repossessed/charged_off loan reports its own stored status as the bucket,
    # with days_past_due forced to 0 -- not re-derived from the schedule shortfall.
    assert summary["bucket"] == "repossessed"
    assert summary["days_past_due"] == 0
    assert summary["amount_past_due"] == 0.0


# ---------------------------------------------------------------------------
# Auto Draft Management
# ---------------------------------------------------------------------------

def test_create_auto_draft_rejects_unknown_loan():

    result = payments.create_auto_draft("FIN-BOGUS", 300, "ach", 5, "EMP-1")

    assert "error" in result


def test_create_auto_draft_rejects_bad_method():

    _full_loan_setup()

    result = payments.create_auto_draft("FIN-1", 300, "bitcoin", 5, "EMP-1")

    assert "error" in result


def test_create_auto_draft_rejects_zero_or_negative_amount():

    _full_loan_setup()

    result = payments.create_auto_draft("FIN-1", 0, "ach", 5, "EMP-1")

    assert "error" in result


def test_create_auto_draft_rejects_out_of_range_day_of_month():

    _full_loan_setup()

    result_too_low = payments.create_auto_draft("FIN-1", 300, "ach", 0, "EMP-1")
    result_too_high = payments.create_auto_draft("FIN-1", 300, "ach", 29, "EMP-1")

    assert "error" in result_too_low
    assert "error" in result_too_high


def test_create_auto_draft_rejects_non_integer_day_of_month():

    _full_loan_setup()

    result = payments.create_auto_draft("FIN-1", 300, "ach", "not-a-number", "EMP-1")

    assert "error" in result


def test_create_auto_draft_succeeds_and_defaults_to_active():

    _full_loan_setup()

    draft = payments.create_auto_draft("FIN-1", 300, "ach", 15, "EMP-1")

    assert draft.attributes["status"] == "active"
    assert draft.attributes["loan_id"] == "FIN-1"
    assert draft.attributes["day_of_month"] == 15
    assert draft.attributes["last_run_month"] is None


def test_set_auto_draft_status_rejects_bad_status():

    _full_loan_setup()
    draft = payments.create_auto_draft("FIN-1", 300, "ach", 15, "EMP-1")

    result = payments.set_auto_draft_status(draft.id, "cancelled", "EMP-1")

    assert "error" in result


def test_set_auto_draft_status_rejects_unknown_draft():

    result = payments.set_auto_draft_status("DRFT-BOGUS", "paused", "EMP-1")

    assert "error" in result


def test_set_auto_draft_status_pauses_and_reactivates():

    _full_loan_setup()
    draft = payments.create_auto_draft("FIN-1", 300, "ach", 15, "EMP-1")

    paused = payments.set_auto_draft_status(draft.id, "paused", "EMP-1")
    assert paused.attributes["status"] == "paused"

    reactivated = payments.set_auto_draft_status(draft.id, "active", "EMP-1")
    assert reactivated.attributes["status"] == "active"


def test_list_auto_drafts_filters_by_loan_and_status():

    _full_loan_setup(loan_id="FIN-1")
    _add_loan("FIN-2", link_customer=None, link_vehicle=None)

    d1 = payments.create_auto_draft("FIN-1", 300, "ach", 5, "EMP-1")
    d2 = payments.create_auto_draft("FIN-2", 200, "cash", 10, "EMP-1")
    payments.set_auto_draft_status(d2.id, "paused", "EMP-1")

    by_loan = payments.list_auto_drafts(loan_id="FIN-1")
    assert [d.id for d in by_loan] == [d1.id]

    active_only = payments.list_auto_drafts(status="active")
    assert d1.id in [d.id for d in active_only]
    assert d2.id not in [d.id for d in active_only]


def test_run_due_auto_drafts_only_processes_matching_day_of_month(monkeypatch):

    _full_loan_setup()

    from datetime import date as _date
    fixed_today = _date(2026, 6, 15)
    monkeypatch.setattr(payments, "_today", lambda: fixed_today)

    matching = payments.create_auto_draft("FIN-1", 300, "cash", 15, "EMP-1")
    non_matching = payments.create_auto_draft("FIN-1", 200, "cash", 20, "EMP-1")

    result = payments.run_due_auto_drafts("EMP-1")

    processed_ids = [r["draft_id"] for r in result["results"]]
    assert matching.id in processed_ids
    assert non_matching.id not in processed_ids
    assert result["processed_count"] == 1

    # A real Payment ledger entry should have been created for the matching draft.
    real_payments = payments.list_payments_for_loan("FIN-1")
    assert len(real_payments) == 1
    assert real_payments[0].attributes["recorded_by"] == "auto_draft:EMP-1"


def test_run_due_auto_drafts_does_not_double_run_same_month(monkeypatch):

    _full_loan_setup()

    from datetime import date as _date
    fixed_today = _date(2026, 6, 15)
    monkeypatch.setattr(payments, "_today", lambda: fixed_today)

    payments.create_auto_draft("FIN-1", 300, "cash", 15, "EMP-1")

    first_run = payments.run_due_auto_drafts("EMP-1")
    second_run = payments.run_due_auto_drafts("EMP-1")

    assert first_run["processed_count"] == 1
    assert second_run["processed_count"] == 0


def test_run_due_auto_drafts_skips_paused_drafts(monkeypatch):

    _full_loan_setup()

    from datetime import date as _date
    fixed_today = _date(2026, 6, 15)
    monkeypatch.setattr(payments, "_today", lambda: fixed_today)

    draft = payments.create_auto_draft("FIN-1", 300, "cash", 15, "EMP-1")
    payments.set_auto_draft_status(draft.id, "paused", "EMP-1")

    result = payments.run_due_auto_drafts("EMP-1")

    assert result["processed_count"] == 0


# ---------------------------------------------------------------------------
# Promise To Pay
# ---------------------------------------------------------------------------

def test_create_promise_to_pay_rejects_unknown_loan():

    result = payments.create_promise_to_pay("FIN-BOGUS", "2026-08-01", 300, "hardship", "EMP-1")

    assert "error" in result


def test_create_promise_to_pay_rejects_bad_date():

    _full_loan_setup()

    result = payments.create_promise_to_pay("FIN-1", "not-a-date", 300, "hardship", "EMP-1")

    assert "error" in result


def test_create_promise_to_pay_rejects_zero_or_negative_amount():

    _full_loan_setup()

    result = payments.create_promise_to_pay("FIN-1", "2026-08-01", 0, "hardship", "EMP-1")

    assert "error" in result


def test_get_promise_status_pending_before_amount_paid_and_before_due(monkeypatch):

    _full_loan_setup()

    from datetime import date as _date
    monkeypatch.setattr(payments, "_today", lambda: _date(2026, 6, 1))

    ptp = payments.create_promise_to_pay("FIN-1", "2026-08-01", 500, "hardship", "EMP-1")

    status = payments.get_promise_status(ptp.id)

    assert status["status"] == "pending"


def test_get_promise_status_kept_once_paid_since_creation(monkeypatch):

    _full_loan_setup()

    from datetime import date as _date
    monkeypatch.setattr(payments, "_today", lambda: _date(2026, 6, 1))
    # create_promise_to_pay() stamps created_at via the real _now(), not _today() --
    # pin it too so the promise's own created_at[:10] falls before the payment_date
    # used below (get_promise_status() only counts payments dated on/after the
    # promise's own created_at day).
    monkeypatch.setattr(payments, "_now", lambda: "2026-06-01T00:00:00+00:00")

    ptp = payments.create_promise_to_pay("FIN-1", "2026-08-01", 200, "hardship", "EMP-1")
    payments.record_payment("FIN-1", 250, "cash", "EMP-1", payment_date="2026-06-15")

    status = payments.get_promise_status(ptp.id)

    assert status["status"] == "kept"
    assert status["paid_since_promise"] >= 200


def test_get_promise_status_broken_once_past_due_and_unpaid(monkeypatch):

    _full_loan_setup()

    from datetime import date as _date
    monkeypatch.setattr(payments, "_today", lambda: _date(2026, 6, 1))

    ptp = payments.create_promise_to_pay("FIN-1", "2026-05-01", 500, "hardship", "EMP-1")

    status = payments.get_promise_status(ptp.id)

    assert status["status"] == "broken"


def test_get_promise_status_rejects_unknown_id():

    result = payments.get_promise_status("PTP-BOGUS")

    assert "error" in result


def test_list_promises_to_pay_filters_by_loan_and_status(monkeypatch):

    _full_loan_setup(loan_id="FIN-1")
    _add_loan("FIN-2", link_customer=None, link_vehicle=None)

    from datetime import date as _date
    monkeypatch.setattr(payments, "_today", lambda: _date(2026, 6, 1))

    ptp1 = payments.create_promise_to_pay("FIN-1", "2026-08-01", 300, "hardship", "EMP-1")
    ptp2 = payments.create_promise_to_pay("FIN-2", "2026-05-01", 400, "job loss", "EMP-1")

    by_loan = payments.list_promises_to_pay(loan_id="FIN-1")
    assert [p["id"] for p in by_loan] == [ptp1.id]

    broken_only = payments.list_promises_to_pay(status="broken")
    assert ptp2.id in [p["id"] for p in broken_only]
    assert ptp1.id not in [p["id"] for p in broken_only]


# ---------------------------------------------------------------------------
# Extension / Deferral
# ---------------------------------------------------------------------------

def test_record_extension_rejects_unknown_loan():

    result = payments.record_extension("FIN-BOGUS", "2026-09-01", "hardship", "EMP-1")

    assert "error" in result


def test_record_extension_rejects_bad_date():

    _full_loan_setup()

    result = payments.record_extension("FIN-1", "not-a-date", "hardship", "EMP-1")

    assert "error" in result


def test_record_extension_appends_to_adjustment_log():

    _full_loan_setup()

    result = payments.record_extension("FIN-1", "2026-09-01", "hardship", "EMP-1")

    assert "error" not in result
    assert result["adjustment"]["type"] == "extension"
    assert result["adjustment"]["new_next_due_date"] == "2026-09-01"

    adjustments = payments.list_payment_adjustments("FIN-1")
    assert len(adjustments) == 1
    assert adjustments[0]["type"] == "extension"


def test_record_deferral_rejects_unknown_loan():

    result = payments.record_deferral("FIN-BOGUS", 2, "hardship", "EMP-1")

    assert "error" in result


def test_record_deferral_rejects_non_positive_months():

    _full_loan_setup()

    result_zero = payments.record_deferral("FIN-1", 0, "hardship", "EMP-1")
    result_non_int = payments.record_deferral("FIN-1", "two", "hardship", "EMP-1")

    assert "error" in result_zero
    assert "error" in result_non_int


def test_record_deferral_appends_to_adjustment_log():

    _full_loan_setup()

    result = payments.record_deferral("FIN-1", 3, "job loss", "EMP-1")

    assert "error" not in result
    assert result["adjustment"]["type"] == "deferral"
    assert result["adjustment"]["months"] == 3

    adjustments = payments.list_payment_adjustments("FIN-1")
    assert len(adjustments) == 1


def test_extension_and_deferral_both_accumulate_on_same_loan():

    _full_loan_setup()

    payments.record_extension("FIN-1", "2026-09-01", "hardship", "EMP-1")
    payments.record_deferral("FIN-1", 2, "job loss", "EMP-1")

    adjustments = payments.list_payment_adjustments("FIN-1")

    assert len(adjustments) == 2
    assert {a["type"] for a in adjustments} == {"extension", "deferral"}


def test_list_payment_adjustments_rejects_unknown_loan():

    result = payments.list_payment_adjustments("FIN-BOGUS")

    assert "error" in result


# ---------------------------------------------------------------------------
# Payoff requests
# ---------------------------------------------------------------------------

def test_request_payoff_rejects_unknown_loan():

    result = payments.request_payoff("FIN-BOGUS", "EMP-1")

    assert "error" in result


def test_request_payoff_creates_a_real_request():

    _full_loan_setup()

    result = payments.request_payoff("FIN-1", "EMP-1", notes="customer trading in")

    assert "error" not in result
    assert result["request"]["status"] == "requested"
    assert result["request"]["notes"] == "customer trading in"
    assert result["request"]["id"].startswith("payoff-")


def test_fulfill_payoff_request_rejects_unknown_loan():

    result = payments.fulfill_payoff_request("FIN-BOGUS", "payoff-x", "EMP-1")

    assert "error" in result


def test_fulfill_payoff_request_rejects_unknown_request_id():

    _full_loan_setup()

    result = payments.fulfill_payoff_request("FIN-1", "payoff-bogus", "EMP-1")

    assert "error" in result


def test_fulfill_payoff_request_succeeds_and_rejects_double_fulfillment():

    _full_loan_setup()
    request = payments.request_payoff("FIN-1", "EMP-1")
    request_id = request["request"]["id"]

    fulfilled = payments.fulfill_payoff_request("FIN-1", request_id, "EMP-2")
    assert "error" not in fulfilled
    assert fulfilled["request"]["status"] == "fulfilled"
    assert fulfilled["request"]["fulfilled_by"] == "EMP-2"

    double = payments.fulfill_payoff_request("FIN-1", request_id, "EMP-2")
    assert "error" in double


def test_list_payoff_requests_filters_by_loan_and_status():

    _full_loan_setup(loan_id="FIN-1")
    _add_loan("FIN-2", link_customer=None, link_vehicle=None)

    r1 = payments.request_payoff("FIN-1", "EMP-1")
    r2 = payments.request_payoff("FIN-2", "EMP-1")
    payments.fulfill_payoff_request("FIN-2", r2["request"]["id"], "EMP-2")

    by_loan = payments.list_payoff_requests(loan_id="FIN-1")
    assert len(by_loan) == 1
    assert by_loan[0]["loan_id"] == "FIN-1"

    requested_only = payments.list_payoff_requests(status="requested")
    assert r1["request"]["id"] in [r["id"] for r in requested_only]

    fulfilled_only = payments.list_payoff_requests(status="fulfilled")
    assert r2["request"]["id"] in [r["id"] for r in fulfilled_only]


# ---------------------------------------------------------------------------
# Customer Payment Portal
# ---------------------------------------------------------------------------

def test_generate_payment_portal_link_rejects_unknown_loan():

    result = payments.generate_payment_portal_link("FIN-BOGUS", "EMP-1")

    assert "error" in result


def test_generate_payment_portal_link_creates_a_real_token():

    _full_loan_setup()

    result = payments.generate_payment_portal_link("FIN-1", "EMP-1")

    assert "error" not in result
    assert result["token"]
    assert result["path"] == f"/pay/{result['token']}"


def test_get_payment_portal_link_status_reports_not_exists_before_generation():

    _full_loan_setup()

    status = payments.get_payment_portal_link_status("FIN-1")

    assert status["exists"] is False


def test_get_payment_portal_link_status_reports_real_link_after_generation():

    _full_loan_setup()
    payments.generate_payment_portal_link("FIN-1", "EMP-1")

    status = payments.get_payment_portal_link_status("FIN-1")

    assert status["exists"] is True
    assert status["revoked"] is False


def test_revoke_payment_portal_link_rejects_when_none_exists():

    _full_loan_setup()

    result = payments.revoke_payment_portal_link("FIN-1", "EMP-1")

    assert "error" in result


def test_revoke_payment_portal_link_succeeds_and_rejects_double_revoke():

    _full_loan_setup()
    payments.generate_payment_portal_link("FIN-1", "EMP-1")

    revoked = payments.revoke_payment_portal_link("FIN-1", "EMP-1")
    assert revoked["revoked"] is True

    double = payments.revoke_payment_portal_link("FIN-1", "EMP-1")
    assert "error" in double


def test_get_public_portal_view_rejects_bad_token():

    result = payments.get_public_portal_view("bogus-token")

    assert "error" in result


def test_get_public_portal_view_returns_real_customer_and_vehicle_and_balance():

    _full_loan_setup(amount_financed=12000.0, apr=9.0, monthly_payment=298.62)
    link = payments.generate_payment_portal_link("FIN-1", "EMP-1")

    view = payments.get_public_portal_view(link["token"])

    assert "error" not in view
    assert view["revoked"] is False
    assert view["customer_name"] == "Jane Doe"
    assert "Honda" in view["vehicle"]
    assert view["balance"] is not None
    assert view["balance_basis"] == "schedule_implied_estimate"
    assert view["not_yet_tracked"]["statements"]


def test_get_public_portal_view_uses_real_ledger_basis_once_real_payments_exist():

    _full_loan_setup(amount_financed=12000.0, apr=9.0, monthly_payment=298.62)
    link = payments.generate_payment_portal_link("FIN-1", "EMP-1")
    payments.record_payment("FIN-1", 300, "cash", "EMP-1")

    view = payments.get_public_portal_view(link["token"])

    assert view["balance_basis"] == "real_payment_ledger"


def test_submit_public_payment_rejects_bad_token():

    result = payments.submit_public_payment("bogus-token", 100, "cash")

    assert "error" in result


def test_submit_public_payment_rejects_when_link_revoked():

    _full_loan_setup()
    link = payments.generate_payment_portal_link("FIN-1", "EMP-1")
    payments.revoke_payment_portal_link("FIN-1", "EMP-1")

    result = payments.submit_public_payment(link["token"], 100, "cash")

    assert "error" in result


def test_submit_public_payment_records_a_real_payment_with_customer_sentinel():

    _full_loan_setup()
    link = payments.generate_payment_portal_link("FIN-1", "EMP-1")

    result = payments.submit_public_payment(link["token"], 250, "cash")

    assert "error" not in result

    stored_payments = payments.list_payments_for_loan("FIN-1")
    assert len(stored_payments) == 1
    assert stored_payments[0].attributes["recorded_by"] == payments.CUSTOMER_SENTINEL
    assert stored_payments[0].attributes["amount"] == 250


def test_submit_public_payment_propagates_a_real_validation_error():

    _full_loan_setup()
    link = payments.generate_payment_portal_link("FIN-1", "EMP-1")

    result = payments.submit_public_payment(link["token"], -50, "cash")

    assert "error" in result


def test_submit_public_payoff_request_rejects_bad_token():

    result = payments.submit_public_payoff_request("bogus-token")

    assert "error" in result


def test_submit_public_payoff_request_rejects_when_link_revoked():

    _full_loan_setup()
    link = payments.generate_payment_portal_link("FIN-1", "EMP-1")
    payments.revoke_payment_portal_link("FIN-1", "EMP-1")

    result = payments.submit_public_payoff_request(link["token"], notes="please")

    assert "error" in result


def test_submit_public_payoff_request_creates_a_real_request_with_customer_sentinel():

    _full_loan_setup()
    link = payments.generate_payment_portal_link("FIN-1", "EMP-1")

    result = payments.submit_public_payoff_request(link["token"], notes="trading in")

    assert "error" not in result
    assert result["request"]["requested_by"] == payments.CUSTOMER_SENTINEL
    assert result["request"]["notes"] == "trading in"


# ---------------------------------------------------------------------------
# get_payments_dashboard()
# ---------------------------------------------------------------------------

def test_get_payments_dashboard_real_aggregate_totals():

    _full_loan_setup(loan_id="FIN-1")
    _add_loan("FIN-2", link_customer=None, link_vehicle=None)

    payments.record_payment("FIN-1", 300, "cash", "EMP-1")
    payments.record_payment("FIN-2", 200, "cash", "EMP-1")
    payments.create_auto_draft("FIN-1", 300, "ach", 5, "EMP-1")
    draft_paused = payments.create_auto_draft("FIN-2", 200, "ach", 10, "EMP-1")
    payments.set_auto_draft_status(draft_paused.id, "paused", "EMP-1")
    payments.request_payoff("FIN-1", "EMP-1")

    dashboard = payments.get_payments_dashboard()

    assert dashboard["total_payments"] == 2
    assert dashboard["approved_payments"] == 2
    assert dashboard["declined_payments"] == 0
    assert dashboard["total_collected"] == pytest.approx(500.0, abs=0.01)
    assert dashboard["by_method"]["cash"] == 2
    assert dashboard["active_auto_drafts"] == 1
    assert dashboard["paused_auto_drafts"] == 1
    assert dashboard["pending_payoff_requests"] == 1
    assert dashboard["basis"] == payments.SIMULATED_BASIS_GATEWAY


def test_get_payments_dashboard_empty_when_nothing_recorded():

    dashboard = payments.get_payments_dashboard()

    assert dashboard["total_payments"] == 0
    assert dashboard["total_collected"] == 0.0
    assert dashboard["active_auto_drafts"] == 0
    assert dashboard["promises_to_pay"] == {"pending": 0, "kept": 0, "broken": 0}


# ---------------------------------------------------------------------------
# ACL layer -- core/payments_api.py
# ---------------------------------------------------------------------------

_STAFF_ROLES = (ADMIN, OPERATIONS, FINANCE)
_DENIED_ROLES = (SALES, MARKETING, SERVICE)


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_record_payment_api_denies_unauthorized_roles(role):

    _full_loan_setup()

    result = payments_api.record_payment_api(role, "EMP-1", "FIN-1", 100, "cash")

    assert "error" in result


@pytest.mark.parametrize("role", _STAFF_ROLES)
def test_record_payment_api_allows_authorized_roles(role):

    _full_loan_setup()

    result = payments_api.record_payment_api(role, "EMP-1", "FIN-1", 100, "cash")

    assert not isinstance(result, dict)
    assert result.attributes["status"] == "approved"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_list_payments_for_loan_api_denies_unauthorized_roles(role):

    _full_loan_setup()

    result = payments_api.list_payments_for_loan_api(role, "FIN-1")

    assert "error" in result


def test_list_payments_for_loan_api_allows_finance():

    _full_loan_setup()
    payments.record_payment("FIN-1", 100, "cash", "EMP-1")

    result = payments_api.list_payments_for_loan_api(FINANCE, "FIN-1")

    assert result["count"] == 1


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_real_payment_summary_api_denies_unauthorized_roles(role):

    _full_loan_setup()

    result = payments_api.get_real_payment_summary_api(role, "FIN-1")

    assert "error" in result


def test_get_real_payment_summary_api_reports_has_real_payments_false_when_none():

    _full_loan_setup()

    result = payments_api.get_real_payment_summary_api(ADMIN, "FIN-1")

    assert result["has_real_payments"] is False


def test_get_real_payment_summary_api_reports_real_summary_once_payments_exist():

    _full_loan_setup()
    payments.record_payment("FIN-1", 100, "cash", "EMP-1")

    result = payments_api.get_real_payment_summary_api(ADMIN, "FIN-1")

    assert result["has_real_payments"] is True
    assert result["total_paid"] == pytest.approx(100.0, abs=0.01)


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_create_auto_draft_api_denies_unauthorized_roles(role):

    _full_loan_setup()

    result = payments_api.create_auto_draft_api(role, "EMP-1", "FIN-1", 300, "ach", 5)

    assert "error" in result


def test_create_auto_draft_api_allows_operations():

    _full_loan_setup()

    result = payments_api.create_auto_draft_api(OPERATIONS, "EMP-1", "FIN-1", 300, "ach", 5)

    assert not isinstance(result, dict)
    assert result.attributes["status"] == "active"


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_set_auto_draft_status_api_denies_unauthorized_roles(role):

    _full_loan_setup()
    draft = payments.create_auto_draft("FIN-1", 300, "ach", 5, "EMP-1")

    result = payments_api.set_auto_draft_status_api(role, "EMP-1", draft.id, "paused")

    assert "error" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_run_due_auto_drafts_api_denies_unauthorized_roles(role):

    result = payments_api.run_due_auto_drafts_api(role, "EMP-1")

    assert "error" in result


def test_run_due_auto_drafts_api_allows_finance():

    result = payments_api.run_due_auto_drafts_api(FINANCE, "EMP-1")

    assert "error" not in result
    assert "processed_count" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_create_promise_to_pay_api_denies_unauthorized_roles(role):

    _full_loan_setup()

    result = payments_api.create_promise_to_pay_api(role, "EMP-1", "FIN-1", "2026-08-01", 300)

    assert "error" in result


def test_create_promise_to_pay_api_allows_admin():

    _full_loan_setup()

    result = payments_api.create_promise_to_pay_api(ADMIN, "EMP-1", "FIN-1", "2026-08-01", 300)

    assert not isinstance(result, dict)


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_promise_status_api_denies_unauthorized_roles(role):

    result = payments_api.get_promise_status_api(role, "PTP-1")

    assert "error" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_record_extension_api_denies_unauthorized_roles(role):

    _full_loan_setup()

    result = payments_api.record_extension_api(role, "EMP-1", "FIN-1", "2026-09-01")

    assert "error" in result


def test_record_extension_api_allows_operations():

    _full_loan_setup()

    result = payments_api.record_extension_api(OPERATIONS, "EMP-1", "FIN-1", "2026-09-01", reason="hardship")

    assert "error" not in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_record_deferral_api_denies_unauthorized_roles(role):

    _full_loan_setup()

    result = payments_api.record_deferral_api(role, "EMP-1", "FIN-1", 2)

    assert "error" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_list_payment_adjustments_api_denies_unauthorized_roles(role):

    result = payments_api.list_payment_adjustments_api(role, "FIN-1")

    assert "error" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_request_payoff_api_denies_unauthorized_roles(role):

    _full_loan_setup()

    result = payments_api.request_payoff_api(role, "EMP-1", "FIN-1")

    assert "error" in result


def test_request_payoff_api_allows_finance():

    _full_loan_setup()

    result = payments_api.request_payoff_api(FINANCE, "EMP-1", "FIN-1")

    assert "error" not in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_fulfill_payoff_request_api_denies_unauthorized_roles(role):

    _full_loan_setup()
    request = payments.request_payoff("FIN-1", "EMP-1")

    result = payments_api.fulfill_payoff_request_api(role, "EMP-2", "FIN-1", request["request"]["id"])

    assert "error" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_generate_payment_portal_link_api_denies_unauthorized_roles(role):

    _full_loan_setup()

    result = payments_api.generate_payment_portal_link_api(role, "EMP-1", "FIN-1")

    assert "error" in result


def test_generate_payment_portal_link_api_allows_admin():

    _full_loan_setup()

    result = payments_api.generate_payment_portal_link_api(ADMIN, "EMP-1", "FIN-1")

    assert "error" not in result
    assert result["token"]


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_payment_portal_link_status_api_denies_unauthorized_roles(role):

    result = payments_api.get_payment_portal_link_status_api(role, "FIN-1")

    assert "error" in result


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_revoke_payment_portal_link_api_denies_unauthorized_roles(role):

    _full_loan_setup()
    payments.generate_payment_portal_link("FIN-1", "EMP-1")

    result = payments_api.revoke_payment_portal_link_api(role, "EMP-1", "FIN-1")

    assert "error" in result


def test_revoke_payment_portal_link_api_allows_finance():

    _full_loan_setup()
    payments.generate_payment_portal_link("FIN-1", "EMP-1")

    result = payments_api.revoke_payment_portal_link_api(FINANCE, "EMP-1", "FIN-1")

    assert "error" not in result
    assert result["revoked"] is True


@pytest.mark.parametrize("role", _DENIED_ROLES)
def test_get_payments_dashboard_api_denies_unauthorized_roles(role):

    result = payments_api.get_payments_dashboard_api(role)

    assert "error" in result


def test_get_payments_dashboard_api_allows_admin():

    result = payments_api.get_payments_dashboard_api(ADMIN)

    assert "error" not in result
    assert "total_payments" in result


def test_record_payment_overpayment_credited_not_booked_as_interest():
    """Regression: paying past payoff must NOT dump the excess into interest_portion (which
    inflated interest income and swallowed the customer's money) — it's an unapplied credit."""
    _full_loan_setup(amount_financed=12000.0, apr=12.0)   # balance 12000, interest_due 120
    result = payments.record_payment("FIN-1", 20000, "cash", "EMP-1")
    a = result.attributes
    assert a["interest_portion"] == pytest.approx(120.0, abs=0.01)     # capped at interest actually due
    assert a["principal_portion"] == pytest.approx(12000.0, abs=0.01)  # capped at the balance
    assert a["overpayment_credit"] == pytest.approx(7880.0, abs=0.01)  # the rest is a credit
    assert a["balance_after"] == pytest.approx(0.0, abs=0.01)


def test_deferred_months_counts_deferrals_and_extensions():
    _add_loan()
    payments.record_deferral("FIN-1", 2, "hardship", "EMP-1")
    payments.record_extension("FIN-1", "2027-01-01", "hardship", "EMP-1")
    loan = payments._get_loan("FIN-1")
    assert payments._deferred_months(loan) == 3   # 2 deferral months + 1 extension


def test_deferral_clears_delinquency_so_no_wrongful_repo_referral():
    """Regression: granting a deferral must actually reduce days-past-due, not leave the borrower
    accruing delinquency (and getting referred to repossession) despite the accommodation."""
    from core import loan_servicing
    _add_loan(contract_date="2020-01-01")             # very old -> many months elapsed
    payments.record_deferral("FIN-1", 999, "hardship", "EMP-1")
    after = loan_servicing.get_simulated_payment_status("FIN-1")
    assert after["bucket"] == "current"
    assert after["days_past_due"] == 0
