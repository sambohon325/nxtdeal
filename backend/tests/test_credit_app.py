"""
Tests for Credit Application (core/credit_app.py, core/credit_app_api.py --
session 104). Run from backend/ with `pytest`.

Covers the real applicant-record lifecycle (draft -> decisioned/withdrawn), the
deterministic rules-based decision engine (_decide()'s score-band ladder plus its
honest "no score on file" fallback), the FCRA-consent/monthly-income gates on
submission, the "locked once decisioned" edit rule, real stats, the ACL layer, and
field-level security masking ssn_last4.
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
from core.entity_types import CUSTOMER, DEAL
from core import credit_app
from core import credit_app_api
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    monkeypatch.setenv("DEALEROS_DEMO", "1")
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(credit_app, "save_graph", lambda filepath: None)


def _add_customer(customer_id="CUST-1", credit_score=None, first="Jane", last="Doe"):
    attrs = {"FirstName": first, "LastName": last}
    if credit_score is not None:
        attrs["CreditScore"] = str(credit_score)
    ledger.add_entity(Entity(id=customer_id, entity_type=CUSTOMER, attributes=attrs))
    return customer_id


def _add_deal(deal_id="DEAL-1"):
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes={"status": "desking"}))
    return deal_id


def _draft_app(customer_id="CUST-1", credit_score=700, **kwargs):
    _add_customer(customer_id, credit_score=credit_score)
    return credit_app.create_credit_application(customer_id, "EMP-00001", **kwargs)


def _ready_to_submit(customer_id="CUST-1", credit_score=700, monthly_income=5000):
    app = _draft_app(customer_id, credit_score=credit_score)
    credit_app.give_fcra_consent(app.id)
    credit_app.update_applicant(app.id, applicant_patch={"monthly_income": monthly_income})
    return app.id


# --- create_credit_application ---

def test_create_rejects_nonexistent_customer():
    result = credit_app.create_credit_application("CUST-999", "EMP-00001")
    assert "error" in result


def test_create_rejects_non_customer_entity():
    ledger.add_entity(Entity(id="VEH-1", entity_type="Vehicle", attributes={}))
    result = credit_app.create_credit_application("VEH-1", "EMP-00001")
    assert "error" in result


def test_create_succeeds_with_valid_customer_and_defaults_to_draft():
    _add_customer("CUST-1")
    app = credit_app.create_credit_application("CUST-1", "EMP-00001")
    assert app.attributes["status"] == "draft"
    assert app.attributes["customer_id"] == "CUST-1"
    assert app.attributes["linked_deal_id"] is None
    assert app.attributes["fcra_consent"] is False
    assert app.attributes["decision"] is None
    assert app.attributes["applicant"]["monthly_income"] is None


def test_create_rejects_nonexistent_linked_deal():
    _add_customer("CUST-1")
    result = credit_app.create_credit_application("CUST-1", "EMP-00001", linked_deal_id="DEAL-999")
    assert "error" in result


def test_create_accepts_valid_linked_deal_and_requested_amount():
    _add_customer("CUST-1")
    _add_deal("DEAL-1")
    app = credit_app.create_credit_application(
        "CUST-1", "EMP-00001", linked_deal_id="DEAL-1", requested_amount="25000.556"
    )
    assert app.attributes["linked_deal_id"] == "DEAL-1"
    assert app.attributes["requested_amount"] == 25000.56


# --- update_applicant ---

def test_update_applicant_rejects_nonexistent_app():
    result = credit_app.update_applicant("CAPP-999", applicant_patch={"monthly_income": 4000})
    assert "error" in result


def test_update_applicant_sets_valid_fields():
    app = _draft_app()
    updated = credit_app.update_applicant(
        app.id,
        applicant_patch={
            "employment_status": "employed",
            "employer_name": "Acme Corp",
            "monthly_income": "4999.999",
            "housing_status": "rent",
            "monthly_housing_payment": 1200,
        },
    )
    assert updated.attributes["applicant"]["employment_status"] == "employed"
    assert updated.attributes["applicant"]["employer_name"] == "Acme Corp"
    assert updated.attributes["applicant"]["monthly_income"] == 5000.0
    assert updated.attributes["applicant"]["housing_status"] == "rent"


def test_update_applicant_rejects_bad_employment_status():
    app = _draft_app()
    result = credit_app.update_applicant(app.id, applicant_patch={"employment_status": "bogus"})
    assert "error" in result


def test_update_applicant_rejects_bad_housing_status():
    app = _draft_app()
    result = credit_app.update_applicant(app.id, applicant_patch={"housing_status": "bogus"})
    assert "error" in result


def test_update_applicant_ignores_unknown_field():
    app = _draft_app()
    updated = credit_app.update_applicant(app.id, applicant_patch={"not_a_real_field": "x"})
    assert "not_a_real_field" not in updated.attributes["applicant"]


def test_update_co_applicant_set_then_clear():
    app = _draft_app()

    updated = credit_app.update_applicant(
        app.id,
        co_applicant_patch={"first_name": "John", "last_name": "Doe", "monthly_income": 3000},
    )
    assert updated.attributes["co_applicant"]["first_name"] == "John"
    assert updated.attributes["co_applicant"]["monthly_income"] == 3000.0

    cleared = credit_app.update_applicant(app.id, co_applicant_patch={})
    assert cleared.attributes["co_applicant"] is None


def test_update_applicant_updates_requested_amount():
    app = _draft_app()
    updated = credit_app.update_applicant(app.id, requested_amount=18000)
    assert updated.attributes["requested_amount"] == 18000.0


def test_update_applicant_rejected_once_decisioned():
    app_id = _ready_to_submit()
    credit_app.submit_credit_application(app_id)

    result = credit_app.update_applicant(app_id, applicant_patch={"monthly_income": 9999})
    assert "error" in result


# --- set_ssn_last4 ---

def test_set_ssn_last4_valid():
    app = _draft_app()
    updated = credit_app.set_ssn_last4(app.id, "1234")
    assert updated.attributes["ssn_last4"] == "1234"


def test_set_ssn_last4_strips_non_digits():
    app = _draft_app()
    updated = credit_app.set_ssn_last4(app.id, "12-34")
    assert updated.attributes["ssn_last4"] == "1234"


def test_set_ssn_last4_rejects_wrong_length():
    app = _draft_app()
    result = credit_app.set_ssn_last4(app.id, "123")
    assert "error" in result


def test_set_ssn_last4_rejected_once_decisioned():
    app_id = _ready_to_submit()
    credit_app.submit_credit_application(app_id)
    result = credit_app.set_ssn_last4(app_id, "1234")
    assert "error" in result


# --- give_fcra_consent ---

def test_give_fcra_consent_sets_flag_and_timestamp():
    app = _draft_app()
    assert app.attributes["fcra_consent"] is False
    updated = credit_app.give_fcra_consent(app.id)
    assert updated.attributes["fcra_consent"] is True
    assert updated.attributes["fcra_consent_at"] is not None


def test_give_fcra_consent_rejected_once_decisioned():
    app_id = _ready_to_submit()
    credit_app.submit_credit_application(app_id)
    result = credit_app.give_fcra_consent(app_id)
    assert "error" in result


# --- link_to_deal ---

def test_link_to_deal_rejects_nonexistent_deal():
    app = _draft_app()
    result = credit_app.link_to_deal(app.id, "DEAL-999")
    assert "error" in result


def test_link_to_deal_succeeds():
    app = _draft_app()
    _add_deal("DEAL-1")
    updated = credit_app.link_to_deal(app.id, "DEAL-1")
    assert updated.attributes["linked_deal_id"] == "DEAL-1"


def test_link_to_deal_allowed_after_decisioned():
    # Linking to a deal is deliberately NOT locked by decision status -- a
    # pre-qualified customer picking a vehicle AFTER their application already
    # decided is exactly the real scenario this field exists for.
    app_id = _ready_to_submit()
    credit_app.submit_credit_application(app_id)
    _add_deal("DEAL-1")
    updated = credit_app.link_to_deal(app_id, "DEAL-1")
    assert updated.attributes["linked_deal_id"] == "DEAL-1"


# --- submit_credit_application: gates ---

def test_submit_rejects_nonexistent_app():
    result = credit_app.submit_credit_application("CAPP-999")
    assert "error" in result


def test_submit_requires_fcra_consent():
    app = _draft_app()
    credit_app.update_applicant(app.id, applicant_patch={"monthly_income": 5000})
    result = credit_app.submit_credit_application(app.id)
    assert "error" in result
    assert "consent" in result["error"].lower()


def test_submit_requires_monthly_income():
    app = _draft_app()
    credit_app.give_fcra_consent(app.id)
    result = credit_app.submit_credit_application(app.id)
    assert "error" in result
    assert "income" in result["error"].lower()


def test_submit_rejects_double_submit():
    app_id = _ready_to_submit()
    credit_app.submit_credit_application(app_id)
    result = credit_app.submit_credit_application(app_id)
    assert "error" in result


# --- _decide() / submit_credit_application: the real decision ladder ---

def test_decision_excellent_band_approved_no_stipulations():
    app_id = _ready_to_submit(credit_score=760)
    decisioned = credit_app.submit_credit_application(app_id)
    d = decisioned.attributes["decision"]
    assert d["decision"] == "approved"
    assert d["score_band"] == "Excellent"
    assert d["simulated_score"] == 760
    assert d["stipulations"] == []
    assert decisioned.attributes["status"] == "decisioned"


def test_decision_good_band_approved_with_income_stipulation():
    app_id = _ready_to_submit(credit_score=700)
    decisioned = credit_app.submit_credit_application(app_id)
    d = decisioned.attributes["decision"]
    assert d["decision"] == "approved"
    assert d["score_band"] == "Good"
    assert "Proof of income required at signing." in d["stipulations"]


def test_decision_fair_band_conditional():
    app_id = _ready_to_submit(credit_score=600)
    decisioned = credit_app.submit_credit_application(app_id)
    d = decisioned.attributes["decision"]
    assert d["decision"] == "conditional"
    assert d["score_band"] == "Fair"
    assert len(d["stipulations"]) == 2


def test_decision_poor_band_declined_with_score_reason():
    app_id = _ready_to_submit(credit_score=520)
    decisioned = credit_app.submit_credit_application(app_id)
    d = decisioned.attributes["decision"]
    assert d["decision"] == "declined"
    assert d["score_band"] == "Poor"
    assert d["estimated_apr"] is None
    assert "Insufficient credit score for requested terms." in d["reasons"]


def test_decision_below_500_declined_with_program_minimum_reason():
    app_id = _ready_to_submit(credit_score=450)
    decisioned = credit_app.submit_credit_application(app_id)
    d = decisioned.attributes["decision"]
    assert d["decision"] == "declined"
    assert "Credit score below program minimum." in d["reasons"]


def test_decision_declined_adds_dti_reason_when_high():
    app = _draft_app(credit_score=520)
    credit_app.give_fcra_consent(app.id)
    credit_app.update_applicant(
        app.id,
        applicant_patch={"monthly_income": 2000, "monthly_housing_payment": 1500},
    )
    decisioned = credit_app.submit_credit_application(app.id)
    d = decisioned.attributes["decision"]
    assert d["decision"] == "declined"
    assert any("Debt-to-income ratio" in r for r in d["reasons"])


def test_decision_no_credit_score_on_file_is_honestly_conditional():
    # Customer with no CreditScore attribute at all -- the module's own honest
    # "a real bureau pull is still required" fallback, not a guessed number.
    _add_customer("CUST-1")  # no credit_score kwarg
    app = credit_app.create_credit_application("CUST-1", "EMP-00001")
    credit_app.give_fcra_consent(app.id)
    credit_app.update_applicant(app.id, applicant_patch={"monthly_income": 5000})

    decisioned = credit_app.submit_credit_application(app.id)
    d = decisioned.attributes["decision"]
    assert d["decision"] == "conditional"
    assert d["score_band"] == "Unknown"
    assert d["simulated_score"] is None
    assert d["estimated_apr"] is None
    assert any("bureau pull" in s for s in d["stipulations"])


def test_decision_apr_matches_deals_estimate_apr_for_same_score():
    from core.deals import _estimate_apr

    app_id = _ready_to_submit(credit_score=760)
    decisioned = credit_app.submit_credit_application(app_id)
    assert decisioned.attributes["decision"]["estimated_apr"] == _estimate_apr(760)


# --- withdraw_credit_application ---

def test_withdraw_sets_status_and_timestamp():
    app = _draft_app()
    withdrawn = credit_app.withdraw_credit_application(app.id)
    assert withdrawn.attributes["status"] == "withdrawn"
    assert withdrawn.attributes["withdrawn_at"] is not None


def test_withdraw_rejects_double_withdraw():
    app = _draft_app()
    credit_app.withdraw_credit_application(app.id)
    result = credit_app.withdraw_credit_application(app.id)
    assert "error" in result


def test_withdraw_allowed_after_decisioned():
    app_id = _ready_to_submit()
    credit_app.submit_credit_application(app_id)
    withdrawn = credit_app.withdraw_credit_application(app_id)
    assert withdrawn.attributes["status"] == "withdrawn"


# --- list_credit_applications ---

def test_list_filters_by_customer_status_and_deal():
    _add_customer("CUST-A", credit_score=760)
    _add_customer("CUST-B", credit_score=760)
    _add_deal("DEAL-1")

    app_a = credit_app.create_credit_application("CUST-A", "EMP-1", linked_deal_id="DEAL-1")
    app_b = credit_app.create_credit_application("CUST-B", "EMP-1")

    credit_app.give_fcra_consent(app_a.id)
    credit_app.update_applicant(app_a.id, applicant_patch={"monthly_income": 5000})
    credit_app.submit_credit_application(app_a.id)

    by_customer = credit_app.list_credit_applications(customer_id="CUST-B")
    assert [a.id for a in by_customer] == [app_b.id]

    by_status = credit_app.list_credit_applications(status="decisioned")
    assert [a.id for a in by_status] == [app_a.id]

    by_deal = credit_app.list_credit_applications(linked_deal_id="DEAL-1")
    assert [a.id for a in by_deal] == [app_a.id]


def test_list_sorted_most_recent_first():
    _add_customer("CUST-1", credit_score=700)
    app1 = credit_app.create_credit_application("CUST-1", "EMP-1")
    app1.attributes["created_at"] = "2020-01-01T00:00:00+00:00"
    app2 = credit_app.create_credit_application("CUST-1", "EMP-1")
    app2.attributes["created_at"] = "2024-01-01T00:00:00+00:00"

    apps = credit_app.list_credit_applications(customer_id="CUST-1")
    assert [a.id for a in apps] == [app2.id, app1.id]


# --- get_stats ---

def test_stats_empty_when_no_applications():
    stats = credit_app.get_stats()
    assert stats["total"] == 0
    assert stats["approval_rate_pct"] is None


def test_stats_reflect_real_counts_and_approval_rate():
    _add_customer("CUST-A", credit_score=760)   # approved
    _add_customer("CUST-B", credit_score=520)   # declined
    _add_customer("CUST-C", credit_score=600)   # conditional
    _add_customer("CUST-D", credit_score=760)   # left as draft

    for cust, submit in (("CUST-A", True), ("CUST-B", True), ("CUST-C", True), ("CUST-D", False)):
        app = credit_app.create_credit_application(cust, "EMP-1")
        if submit:
            credit_app.give_fcra_consent(app.id)
            credit_app.update_applicant(app.id, applicant_patch={"monthly_income": 5000})
            credit_app.submit_credit_application(app.id)

    stats = credit_app.get_stats()
    assert stats["total"] == 4
    assert stats["draft"] == 1
    assert stats["decisioned"] == 3
    assert stats["approved"] == 1
    assert stats["declined"] == 1
    assert stats["conditional"] == 1
    assert stats["approval_rate_pct"] == pytest.approx(33.3, abs=0.1)


# --- ACL layer (core/credit_app_api.py) ---

def test_create_api_denies_unauthorized_role():
    _add_customer("CUST-1")
    result = credit_app_api.create_credit_application_api(MARKETING, "EMP-1", "CUST-1")
    assert "error" in result


def test_create_api_allows_every_credit_app_role():
    for role in (ADMIN, OPERATIONS, SALES, FINANCE):
        ledger.reset()
        _add_customer("CUST-1")
        result = credit_app_api.create_credit_application_api(role, "EMP-1", "CUST-1")
        assert "error" not in result, f"role {role} was unexpectedly rejected"


def test_update_applicant_api_denies_unauthorized_role():
    app = _draft_app()
    result = credit_app_api.update_applicant_api(SERVICE, app.id, applicant_patch={"monthly_income": 4000})
    assert "error" in result


def test_set_ssn_last4_api_denies_unauthorized_role():
    app = _draft_app()
    result = credit_app_api.set_ssn_last4_api(SERVICE, app.id, "1234")
    assert "error" in result


def test_give_fcra_consent_api_denies_unauthorized_role():
    app = _draft_app()
    result = credit_app_api.give_fcra_consent_api(SERVICE, app.id)
    assert "error" in result


def test_submit_api_denies_unauthorized_role():
    app_id = _ready_to_submit()
    result = credit_app_api.submit_credit_application_api(SERVICE, app_id)
    assert "error" in result


def test_withdraw_api_denies_unauthorized_role():
    app = _draft_app()
    result = credit_app_api.withdraw_credit_application_api(SERVICE, app.id)
    assert "error" in result


def test_link_to_deal_api_denies_unauthorized_role():
    app = _draft_app()
    _add_deal("DEAL-1")
    result = credit_app_api.link_credit_application_to_deal_api(SERVICE, app.id, "DEAL-1")
    assert "error" in result


def test_list_api_denies_unauthorized_role():
    result = credit_app_api.list_credit_applications_api(SERVICE)
    assert "error" in result


def test_dashboard_api_denies_unauthorized_role():
    result = credit_app_api.get_credit_app_dashboard_api(SERVICE)
    assert "error" in result


def test_dashboard_api_returns_recent_and_stats_for_authorized_role():
    app_id = _ready_to_submit(credit_score=760)
    credit_app.submit_credit_application(app_id)

    result = credit_app_api.get_credit_app_dashboard_api(ADMIN)
    assert "error" not in result
    assert result["stats"]["total"] == 1
    assert len(result["recent"]) == 1
    assert result["recent"][0]["id"] == app_id


def test_get_api_returns_customer_brief():
    _add_customer("CUST-1", credit_score=760, first="Priya", last="Nair")
    app = credit_app.create_credit_application("CUST-1", "EMP-00001")
    result = credit_app_api.get_credit_application_api(ADMIN, app.id)
    assert "error" not in result
    assert result["customer"]["name"] == "Priya Nair"
    assert result["customer"]["credit_score"] == "760"


def test_get_api_rejects_unknown_app_id():
    result = credit_app_api.get_credit_application_api(ADMIN, "CAPP-999")
    assert "error" in result


# --- field-level security (ssn_last4) ---

def test_ssn_last4_masked_for_role_without_field_access():
    app = _draft_app()
    credit_app.set_ssn_last4(app.id, "1234")

    result = credit_app_api.get_credit_application_api(SALES, app.id, employee_id="EMP-1")
    assert result["ssn_last4"] == "•••• (restricted)"


def test_ssn_last4_visible_for_admin_and_finance():
    app = _draft_app()
    credit_app.set_ssn_last4(app.id, "1234")

    for role in (ADMIN, FINANCE):
        result = credit_app_api.get_credit_application_api(role, app.id, employee_id="EMP-1")
        assert result["ssn_last4"] == "1234", f"role {role} should see the real ssn_last4"
