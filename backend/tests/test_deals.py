"""
Tests for the DMS Deal Desk (core/deals.py, core/deals_api.py) -- session 33. Run from
backend/ with `pytest`.
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
from core.entity_types import CUSTOMER, VEHICLE, LENDER, FINANCE_CONTRACT
from core import deals
from core import deals_api
from core.lending_compliance import record_ofac_screening
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger(monkeypatch):
    # Historical workflow examples use sample data; production denial has its own suite.
    monkeypatch.setenv("DEALEROS_DEMO", "1")

    ledger.reset()

    yield

    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_audit_writes(monkeypatch):

    monkeypatch.setattr(deals_api, "save_audit_log", lambda filepath: None)


def _add_customer(customer_id, credit_score=700, first="Jane", last="Doe"):

    ledger.add_entity(Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={
            "FirstName": first,
            "LastName": last,
            "CreditScore": str(credit_score),
            # Identity fields required by the FACTA Red Flags compliance gate
            # (core/compliance_rules.py, wired into fund_deal in session 38) --
            # without these, funding a deal is correctly blocked.
            "Address": "123 Main St",
            "City": "Springfield",
            "State": "IL",
            "Zip": "62704",
            "Phone": "555-0100",
            "Email": "jane.doe@example.com",
        },
    ))

    return customer_id


def _add_vehicle(vehicle_id, make="Honda", model="Civic", year="2025", vin="VIN123", date_sold=None):

    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"Make": make, "Model": model, "Year": year, "VIN": vin, "DateSold": date_sold},
    ))

    return vehicle_id


def _add_lender(lender_id, name="Third Party Bank"):

    ledger.add_entity(Entity(id=lender_id, entity_type=LENDER, attributes={"Name": name}))

    return lender_id


def _basic_deal(customer_id="CUST-1", vehicle_id="VEH-1", credit_score=700):

    _add_customer(customer_id, credit_score=credit_score)
    _add_vehicle(vehicle_id)

    return deals_api.create_deal_api(SALES, "EMP-00001", customer_id, vehicle_id)


def _deal_with_selected_scenario(**kwargs):

    deal = _basic_deal(**kwargs)
    deal = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "Standard", 30000, 3000, 60)
    scenario_id = deal["scenarios"][0]["id"]
    deal = deals_api.select_scenario_api(SALES, "EMP-00001", deal["id"], scenario_id)

    return deal


# --- Create deal ---


def test_create_deal_starts_as_desking():

    deal = _basic_deal()

    assert "error" not in deal
    assert deal["status"] == "desking"
    assert deal["scenarios"] == []


def test_create_deal_rejects_unknown_customer():

    _add_vehicle("VEH-1")

    result = deals_api.create_deal_api(SALES, "EMP-00001", "CUST-404", "VEH-1")

    assert "error" in result


def test_create_deal_rejects_unknown_vehicle():

    _add_customer("CUST-1")

    result = deals_api.create_deal_api(SALES, "EMP-00001", "CUST-1", "VEH-404")

    assert "error" in result


def test_create_deal_rejects_already_sold_vehicle():

    _add_customer("CUST-1")
    _add_vehicle("VEH-1", date_sold="2026-01-01")

    result = deals_api.create_deal_api(SALES, "EMP-00001", "CUST-1", "VEH-1")

    assert "error" in result

def test_create_deal_rejects_unauthorized_role():
    # Regression test for CAF-00029 (Code Auditor finding, 2026-07-19):
    # create_deal_api used to have NO role parameter and NO gate at all --
    # any authenticated employee of any role, including MARKETING, could
    # create a Deal. Fixed by adding `role` as the function's first
    # parameter and gating it to _BOARD_VIEW_ROLES (ADMIN/OPERATIONS/SALES/
    # FINANCE). This locks that fix in so a future refactor can't silently
    # drop the gate again.

    _add_customer("CUST-1")
    _add_vehicle("VEH-1")

    result = deals_api.create_deal_api(MARKETING, "EMP-00001", "CUST-1", "VEH-1")

    assert "error" in result

def test_create_deal_allows_every_board_view_role():
    # The flip side of the regression above -- confirm the fix didn't
    # accidentally over-tighten the gate for the roles that legitimately
    # desk deals (ADMIN/OPERATIONS/SALES/FINANCE).

    for role in (ADMIN, OPERATIONS, SALES, FINANCE):

        ledger.reset()
        _add_customer("CUST-1")
        _add_vehicle("VEH-1")

        result = deals_api.create_deal_api(role, "EMP-00001", "CUST-1", "VEH-1")

        assert "error" not in result, f"role {role} was unexpectedly rejected"


# --- Scenarios / desking ---


def test_add_scenario_computes_apr_tiers_from_credit_score():

    deal_high = _basic_deal(customer_id="CUST-1", vehicle_id="VEH-1", credit_score=760)
    deal_mid = _basic_deal(customer_id="CUST-2", vehicle_id="VEH-2", credit_score=700)
    deal_low = _basic_deal(customer_id="CUST-3", vehicle_id="VEH-3", credit_score=600)

    high = deals_api.add_scenario_api(SALES, "EMP-00001", deal_high["id"], "A", 30000, 0, 60)
    mid = deals_api.add_scenario_api(SALES, "EMP-00001", deal_mid["id"], "A", 30000, 0, 60)
    low = deals_api.add_scenario_api(SALES, "EMP-00001", deal_low["id"], "A", 30000, 0, 60)

    assert high["scenarios"][0]["estimated_apr"] == 4.9
    assert mid["scenarios"][0]["estimated_apr"] == 6.9
    assert low["scenarios"][0]["estimated_apr"] == 9.9


def test_add_scenario_computes_amount_financed_and_monthly_payment():

    deal = _basic_deal()

    result = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "Standard", 30000, 3000, 60)

    scenario = result["scenarios"][0]
    assert scenario["amount_financed"] == 27000
    assert scenario["estimated_monthly_payment"] > 0


def test_add_scenario_requires_desking_status():

    deal = _deal_with_selected_scenario()

    result = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "New", 31000, 0, 60)

    assert "error" in result


def test_remove_scenario_removes_by_id():

    deal = _basic_deal()
    deal = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "A", 30000, 0, 60)
    deal = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "B", 31000, 0, 72)

    scenario_id = deal["scenarios"][0]["id"]
    result = deals_api.remove_scenario_api(SALES, "EMP-00001", deal["id"], scenario_id)

    assert len(result["scenarios"]) == 1
    assert result["scenarios"][0]["label"] == "B"


def test_remove_scenario_rejects_unknown_id():

    deal = _basic_deal()

    result = deals_api.remove_scenario_api(SALES, "EMP-00001", deal["id"], "scn-99")

    assert "error" in result


def test_select_scenario_moves_status_to_financing():

    deal = _deal_with_selected_scenario()

    assert deal["status"] == "financing"
    assert deal["selected_scenario_id"] is not None


def test_select_scenario_rejects_unknown_scenario():

    deal = _basic_deal()
    deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "A", 30000, 0, 60)

    result = deals_api.select_scenario_api(SALES, "EMP-00001", deal["id"], "not-real")

    assert "error" in result


# --- Financing: in-house ---


def test_choose_in_house_financing_sets_approved_and_terms():

    deal = _deal_with_selected_scenario()

    result = deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal["id"])

    assert result["financing_type"] == "in_house"
    assert result["financing_status"] == "approved"
    assert result["financing_terms"]["amount_financed"] == 27000


def test_choose_in_house_financing_requires_scenario_selected():

    deal = _basic_deal()

    result = deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal["id"])

    assert "error" in result


def test_choose_in_house_financing_reuses_same_lender_entity():

    deal_a = _deal_with_selected_scenario(customer_id="CUST-1", vehicle_id="VEH-1")
    deal_b = _deal_with_selected_scenario(customer_id="CUST-2", vehicle_id="VEH-2")

    result_a = deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal_a["id"])
    result_b = deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal_b["id"])

    assert result_a["lender_id"] == result_b["lender_id"]


# --- Financing: outside lender ---


def test_submit_to_lender_sets_submitted_status():

    deal = _deal_with_selected_scenario()
    lender_id = _add_lender("LENDER-1")

    result = deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], lender_id)

    assert result["financing_type"] == "outside_lender"
    assert result["financing_status"] == "submitted"
    assert result["lender_id"] == lender_id


def test_submit_to_lender_rejects_unknown_lender():

    deal = _deal_with_selected_scenario()

    result = deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], "LENDER-404")

    assert "error" in result


def test_record_lender_decision_approved_sets_terms():

    deal = _deal_with_selected_scenario()
    lender_id = _add_lender("LENDER-1")
    deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], lender_id)

    result = deals_api.record_lender_decision_api(FINANCE, "EMP-00002", deal["id"], "approved")

    assert result["financing_status"] == "approved"
    assert result["financing_terms"] is not None


def test_record_lender_decision_declined_allows_retry_via_in_house():

    deal = _deal_with_selected_scenario()
    lender_id = _add_lender("LENDER-1")
    deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], lender_id)

    # A declined financing decision must carry a documented reason -- the ECOA/Reg B
    # compliance gate (core/compliance_rules.py, wired in session 38) blocks recording a
    # decline with no reason on file.
    declined = deals_api.record_lender_decision_api(
        FINANCE, "EMP-00002", deal["id"], "declined",
        notes="Debt-to-income ratio above lender program maximum.",
    )
    assert declined["financing_status"] == "declined"
    assert declined["status"] == "financing"

    retried = deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal["id"])
    assert retried["financing_status"] == "approved"
    assert retried["financing_type"] == "in_house"


def test_record_lender_decision_countered_requires_countered_terms():

    deal = _deal_with_selected_scenario()
    lender_id = _add_lender("LENDER-1")
    deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], lender_id)

    result = deals_api.record_lender_decision_api(FINANCE, "EMP-00002", deal["id"], "countered")

    assert "error" in result


def test_accept_countered_terms_moves_to_approved():

    deal = _deal_with_selected_scenario()
    lender_id = _add_lender("LENDER-1")
    deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], lender_id)

    countered_terms = {"apr": 8.5, "term_months": 72, "amount_financed": 27000, "down_payment": 3000, "monthly_payment": 470.12}
    deals_api.record_lender_decision_api(FINANCE, "EMP-00002", deal["id"], "countered", countered_terms)

    result = deals_api.accept_countered_terms_api(FINANCE, "EMP-00002", deal["id"])

    assert result["financing_status"] == "approved"
    assert result["financing_terms"]["apr"] == 8.5


# --- Contract ---


def test_generate_contract_requires_financing_approved():

    deal = _deal_with_selected_scenario()

    result = deals_api.generate_contract_api(FINANCE, "EMP-00002", deal["id"])

    assert "error" in result


def test_generate_contract_success_builds_contract_and_advances_status():

    deal = _deal_with_selected_scenario()
    deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal["id"])

    result = deals_api.generate_contract_api(FINANCE, "EMP-00002", deal["id"])

    assert result["status"] == "contract"
    assert result["contract"]["sale_price"] == 30000
    assert result["contract"]["monthly_payment"] > 0
    assert "disclosures" in result["contract"]


# --- Funding ---


def test_fund_deal_requires_contract_status():

    deal = _deal_with_selected_scenario()
    deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal["id"])

    result = deals_api.fund_deal_api(FINANCE, "EMP-00002", deal["id"])

    assert "error" in result


def test_fund_deal_creates_finance_contract_and_marks_vehicle_sold():

    deal = _deal_with_selected_scenario(customer_id="CUST-1", vehicle_id="VEH-1")
    deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal["id"])
    deals_api.generate_contract_api(FINANCE, "EMP-00002", deal["id"])

    record_ofac_screening(deal["id"], True, "EMP-00002", "Synthetic cleared screening fixture")
    result = deals_api.fund_deal_api(FINANCE, "EMP-00002", deal["id"])

    assert result["status"] == "funded"
    finance_id = result["finance_contract_id"]
    assert finance_id is not None

    finance_entity = ledger.get_entity(finance_id)
    assert finance_entity.entity_type == FINANCE_CONTRACT
    assert finance_entity.attributes["CustomerID"] == "CUST-1"

    vehicle = ledger.get_entity("VEH-1")
    assert vehicle.attributes["DateSold"] is not None

    relationship_types = {
        (r.source_id, r.target_id, r.relationship_type) for r in ledger.get_relationships()
    }
    assert ("CUST-1", finance_id, "FINANCED_BY") in relationship_types
    assert ("CUST-1", "VEH-1", "OWNS") in relationship_types
    assert ("CUST-1", "VEH-1", "PURCHASED") in relationship_types
    assert (finance_id, "VEH-1", "COVERS") in relationship_types


def test_cancel_deal_from_desking():

    deal = _basic_deal()

    result = deals_api.cancel_deal_api(SALES, "EMP-00001", deal["id"])

    assert result["status"] == "cancelled"


def test_cancel_deal_rejects_when_already_funded():

    deal = _deal_with_selected_scenario()
    deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal["id"])
    deals_api.generate_contract_api(FINANCE, "EMP-00002", deal["id"])
    record_ofac_screening(deal["id"], True, "EMP-00002", "Synthetic cleared screening fixture")
    funded = deals_api.fund_deal_api(FINANCE, "EMP-00002", deal["id"])
    assert funded["status"] == "funded"

    result = deals_api.cancel_deal_api(SALES, "EMP-00001", deal["id"])

    assert "error" in result


# --- ACL ---


def test_add_scenario_denied_for_unrelated_non_fi_role():

    deal = _basic_deal()

    result = deals_api.add_scenario_api(SALES, "EMP-00002", deal["id"], "A", 30000, 0, 60)

    assert "error" in result


def test_add_scenario_allowed_for_fi_role_regardless_of_creator():

    deal = _basic_deal()

    result = deals_api.add_scenario_api(FINANCE, "EMP-99999", deal["id"], "A", 30000, 0, 60)

    assert "error" not in result


def test_choose_in_house_financing_denied_for_sales():

    deal = _deal_with_selected_scenario()

    result = deals_api.choose_in_house_financing_api(SALES, "EMP-00001", deal["id"])

    assert "error" in result


def test_submit_to_lender_denied_for_sales():

    deal = _deal_with_selected_scenario()
    lender_id = _add_lender("LENDER-1")

    result = deals_api.submit_to_lender_api(SALES, "EMP-00001", deal["id"], lender_id)

    assert "error" in result


def test_pending_financing_denied_for_sales():

    result = deals_api.list_pending_financing_api(SALES)

    assert "error" in result


def test_pending_financing_allowed_for_finance_and_admin():

    deal = _deal_with_selected_scenario()
    lender_id = _add_lender("LENDER-1")
    deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], lender_id)

    for role in (FINANCE, ADMIN, OPERATIONS):
        result = deals_api.list_pending_financing_api(role)
        assert isinstance(result, list)
        assert any(d["id"] == deal["id"] for d in result)


def test_get_deal_visible_to_creator():

    deal = _basic_deal()

    result = deals_api.get_deal_api(SALES, "EMP-00001", deal["id"])

    assert "error" not in result


def test_get_deal_visible_to_collaborating_sales_rep_but_mutations_stay_restricted():

    deal = _basic_deal()

    result = deals_api.get_deal_api(SALES, "EMP-00002", deal["id"])

    assert result["id"] == deal["id"]
    assert "error" in deals_api.cancel_deal_api(SALES, "EMP-00002", deal["id"])


def test_get_deal_visible_to_finance_even_if_not_creator():

    deal = _basic_deal()

    result = deals_api.get_deal_api(FINANCE, "EMP-00002", deal["id"])

    assert "error" not in result


def test_list_my_deals_only_returns_own_deals():

    _basic_deal(customer_id="CUST-1", vehicle_id="VEH-1")

    _add_customer("CUST-2")
    _add_vehicle("VEH-2")
    deals_api.create_deal_api(SALES, "EMP-00002", "CUST-2", "VEH-2")

    mine = deals_api.list_my_deals_api("EMP-00001")

    assert len(mine) == 1
    assert mine[0]["created_by"] == "EMP-00001"


def test_cancel_deal_denied_for_unrelated_sales_rep():

    deal = _basic_deal()

    result = deals_api.cancel_deal_api(SALES, "EMP-00002", deal["id"])

    assert "error" in result


# --- Trade Appraisal: VIN decode cross-check (NXTDeal VIN Intelligence, Phase 2) ---
#
# A real, check-digit-valid VIN with a known offline decode (WMI "1HG" -> Honda,
# position-10 "3" -> 2003 under the pre-2010 model-year cycle) -- see
# backend/tests/test_vin_decoder.py's own VIN_HONDA_2003 constant, which this
# mirrors so a passing decode here doesn't depend on any live NHTSA fetch (this
# sandbox has no outbound network access, same finding documented throughout
# CLAUDE.md for every other AI/live-data feature in this codebase).

_TRADE_VIN_HONDA_2003 = "1HGCM82633A004352"


def test_decode_trade_in_vin_requires_vin_on_file():

    deal = _basic_deal()

    result = deals.decode_trade_in_vin(deal["id"], attempt_live=False)

    assert "error" in result
    assert "no VIN on file" in result["error"]


def test_decode_trade_in_vin_rejects_unknown_deal():

    result = deals.decode_trade_in_vin("DEAL-404", attempt_live=False)

    assert "error" in result


def test_decode_trade_in_vin_matches_entered_year_and_make():

    deal = _basic_deal()
    deals.update_trade_appraisal(
        deal["id"], "EMP-00001", {"vin": _TRADE_VIN_HONDA_2003, "year": "2003", "make": "Honda"}
    )

    result = deals.decode_trade_in_vin(deal["id"], attempt_live=False)

    assert "error" not in result
    assert result["vin"] == _TRADE_VIN_HONDA_2003
    assert result["valid_format"] is True
    assert result["check_digit_valid"] is True
    assert result["decoded"]["year"] == 2003
    assert result["decoded"]["make"] == "Honda"
    assert result["mismatches"] == []


def test_decode_trade_in_vin_flags_year_mismatch():

    deal = _basic_deal()
    deals.update_trade_appraisal(
        deal["id"], "EMP-00001", {"vin": _TRADE_VIN_HONDA_2003, "year": "1999", "make": "Honda"}
    )

    result = deals.decode_trade_in_vin(deal["id"], attempt_live=False)

    fields = {m["field"] for m in result["mismatches"]}
    assert fields == {"year"}
    year_mismatch = result["mismatches"][0]
    assert year_mismatch["entered"] == "1999"
    assert year_mismatch["decoded"] == "2003"


def test_decode_trade_in_vin_flags_make_mismatch():

    deal = _basic_deal()
    deals.update_trade_appraisal(
        deal["id"], "EMP-00001", {"vin": _TRADE_VIN_HONDA_2003, "year": "2003", "make": "Toyota"}
    )

    result = deals.decode_trade_in_vin(deal["id"], attempt_live=False)

    fields = {m["field"] for m in result["mismatches"]}
    assert fields == {"make"}
    make_mismatch = result["mismatches"][0]
    assert make_mismatch["entered"] == "Toyota"
    assert make_mismatch["decoded"] == "Honda"


def test_decode_trade_in_vin_make_comparison_is_case_insensitive():

    deal = _basic_deal()
    deals.update_trade_appraisal(
        deal["id"], "EMP-00001", {"vin": _TRADE_VIN_HONDA_2003, "year": "2003", "make": "HONDA"}
    )

    result = deals.decode_trade_in_vin(deal["id"], attempt_live=False)

    assert result["mismatches"] == []


def test_decode_trade_in_vin_never_writes_back_to_deal():

    deal = _basic_deal()
    deals.update_trade_appraisal(
        deal["id"], "EMP-00001", {"vin": _TRADE_VIN_HONDA_2003, "year": "1999", "make": "Toyota"}
    )

    deals.decode_trade_in_vin(deal["id"], attempt_live=False)

    reloaded = deals.get_deal(deal["id"])
    trade_in = reloaded.attributes["trade_in"]

    # Still the appraiser's own entered values -- a real mismatch was flagged
    # above, but nothing here should have silently corrected it.
    assert trade_in["year"] == "1999"
    assert trade_in["make"] == "Toyota"
    assert "decoded" not in trade_in
    assert "vin_decode" not in trade_in


def test_decode_trade_in_vin_works_after_desking_ends():

    deal = _basic_deal()
    deals.update_trade_appraisal(
        deal["id"], "EMP-00001", {"vin": _TRADE_VIN_HONDA_2003, "year": "2003", "make": "Honda"}
    )
    deal = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "Standard", 30000, 3000, 60)
    scenario_id = deal["scenarios"][0]["id"]
    deal = deals_api.select_scenario_api(SALES, "EMP-00001", deal["id"], scenario_id)

    assert deal["status"] == "financing"

    # update_trade_appraisal itself would now reject an edit (desking-only), but
    # this read-only cross-check has no such restriction -- confirm it still works.
    result = deals.decode_trade_in_vin(deal["id"], attempt_live=False)

    assert "error" not in result
    assert result["mismatches"] == []


# --- Trade Appraisal VIN decode: ACL (core/deals_api.py's decode_trade_in_vin_api) ---


@pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, FINANCE])
def test_decode_trade_in_vin_api_allowed_for_board_view_roles(role):

    deal = _basic_deal()
    deals.update_trade_appraisal(
        deal["id"], "EMP-00001", {"vin": _TRADE_VIN_HONDA_2003, "year": "2003", "make": "Honda"}
    )

    result = deals_api.decode_trade_in_vin_api(role, deal["id"], attempt_live=False)

    assert "error" not in result
    assert result["mismatches"] == []


@pytest.mark.parametrize("role", [MARKETING, SERVICE, "BOGUS_ROLE"])
def test_decode_trade_in_vin_api_denied_for_non_board_view_roles(role):

    deal = _basic_deal()
    deals.update_trade_appraisal(
        deal["id"], "EMP-00001", {"vin": _TRADE_VIN_HONDA_2003, "year": "2003", "make": "Honda"}
    )

    result = deals_api.decode_trade_in_vin_api(role, deal["id"], attempt_live=False)

    assert "error" in result


def test_decode_trade_in_vin_api_rejects_unknown_deal():

    result = deals_api.decode_trade_in_vin_api(ADMIN, "DEAL-404", attempt_live=False)

    assert "error" in result


# ---------------------------------------------------------------------------
# Pillar 4 slice 4c: the deal lifecycle feeds the agentic-bot FLEET's team agents.
# ---------------------------------------------------------------------------

def test_desking_two_deals_makes_sales_agent_recognize_the_workflow():
    """Desking two deals as the same rep (create -> add scenario -> select scenario)
    makes the Sales team agent recognize the repeated 3-step workflow -- real
    multi-step recognition fed through the deals API, not a 1-step stub. Each deal is a
    separate (actor, deal_id) sequence, so the shared 3-gram is seen twice and clears
    MIN_WORKFLOW_OCCURRENCES."""

    from core.bot_fleet import get_team_workflows

    for i in (1, 2):
        _add_customer(f"CUST-{i}")
        _add_vehicle(f"VEH-{i}")
        deal = deals_api.create_deal_api(SALES, "EMP-00001", f"CUST-{i}", f"VEH-{i}")
        deal = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "Standard", 30000, 3000, 60)
        scenario_id = deal["scenarios"][0]["id"]
        deals_api.select_scenario_api(SALES, "EMP-00001", deal["id"], scenario_id)

    wf = get_team_workflows("sales")

    assert wf["step_count"] == 6  # 2 deals x (create_deal + add_scenario + select_scenario)
    recognized = {tuple(w["steps"]): w["occurrences"] for w in wf["recognized_workflows"]}
    assert ("create_deal", "add_scenario", "select_scenario") in recognized
    assert recognized[("create_deal", "add_scenario", "select_scenario")] >= 2


def test_desking_does_not_feed_the_finance_agent():
    """Honest team split: desking steps go to the Sales agent only -- the Finance agent
    stays empty until a real F&I/funding action is taken. No cross-team leakage."""

    from core.bot_fleet import get_team_workflows

    _add_customer("CUST-1")
    _add_vehicle("VEH-1")
    deal = deals_api.create_deal_api(SALES, "EMP-00001", "CUST-1", "VEH-1")
    deal = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "Standard", 30000, 3000, 60)
    deals_api.select_scenario_api(SALES, "EMP-00001", deal["id"], deal["scenarios"][0]["id"])

    assert get_team_workflows("finance")["step_count"] == 0
    assert get_team_workflows("sales")["step_count"] == 3


def test_validate_countered_terms_guards_contract_inputs():
    """Regression: a 'countered' lender decision must not accept malformed terms that would
    later crash generate_contract (KeyError) or write junk onto the deal."""
    from core.deals import _validate_countered_terms
    good = {"apr": 5.9, "term_months": 72, "amount_financed": 20000, "down_payment": 2000, "monthly_payment": 330}
    clean, err = _validate_countered_terms(good)
    assert err is None and clean["term_months"] == 72 and isinstance(clean["term_months"], int)
    assert _validate_countered_terms("nope")[1]                       # not a dict
    assert _validate_countered_terms({"apr": 5.9})[1]                 # missing keys
    assert _validate_countered_terms({**good, "apr": "x"})[1]          # non-numeric
    assert _validate_countered_terms({**good, "amount_financed": -1})[1]  # negative
    assert _validate_countered_terms({**good, "term_months": 0})[1]    # zero term
