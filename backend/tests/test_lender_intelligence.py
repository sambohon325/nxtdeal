"""
Tests for Lender Intelligence (core/lender_intelligence.py,
core/lender_intelligence_api.py -- 2026-07-19). Run from backend/ with `pytest`.

This is a pure read/composition module -- no mutation of its own. Every scenario
here is built by driving the real core/deals.py Deal Desk functions (submit_to_
lender_api/record_lender_decision_api/choose_in_house_financing_api) exactly the
way a real desking session would, then asserting on what Lender Intelligence
composes from the resulting real `lender_submission_history` entries -- matching
this codebase's own "compose, don't fabricate a parallel fixture" discipline.
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
from core.entity_types import CUSTOMER, VEHICLE, LENDER
from core import deals_api
from core import lender_intelligence as li
from core import lender_intelligence_api as li_api
from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()

    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    # core/deals.py's submit_to_lender()/record_lender_decision()/
    # choose_in_house_financing() all call the real save_graph(GRAPH_PATH) --
    # this suite runs under backend/tests/conftest.py's own isolated
    # DEALEROS_STORAGE_DIR temp directory already, so a real write here is
    # harmless, but monkeypatching it out anyway keeps this file fast and
    # matches test_deals.py's own established no-real-writes-during-a-test
    # convention.
    from core import deals

    monkeypatch.setattr(deals, "save_graph", lambda filepath: None)


def _add_customer(customer_id, credit_score=700, first="Jane", last="Doe"):

    ledger.add_entity(Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={
            "FirstName": first,
            "LastName": last,
            "CreditScore": str(credit_score),
        },
    ))

    return customer_id


def _add_vehicle(vehicle_id, make="Honda", model="Civic", year="2025", vin="VIN123"):

    ledger.add_entity(Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"Make": make, "Model": model, "Year": year, "VIN": vin, "DateSold": None},
    ))

    return vehicle_id


def _add_lender(lender_id, name="Third Party Bank"):

    ledger.add_entity(Entity(id=lender_id, entity_type=LENDER, attributes={"Name": name}))

    return lender_id


def _deal_submitted_to_lender(lender_id, customer_id, vehicle_id, credit_score=700):
    """Builds a real deal all the way through desking + financing submission,
    the same real happy path a live desking session follows. credit_score
    controls which of core/deals.py's 3 real APR tiers the scenario prices
    at (700 = near-prime/6.9%, 750 = prime/4.9%, 600 = subprime/9.9%)."""

    _add_customer(customer_id, credit_score=credit_score)
    _add_vehicle(vehicle_id)

    deal = deals_api.create_deal_api(SALES, "EMP-00001", customer_id, vehicle_id)
    deal = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "Standard", 30000, 3000, 60)
    scenario_id = deal["scenarios"][0]["id"]
    deal = deals_api.select_scenario_api(SALES, "EMP-00001", deal["id"], scenario_id)
    deal = deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], lender_id)

    return deal


def _decide(deal_id, decision, countered_terms=None, notes=None):
    # core/deals_api.py's record_lender_decision_api() runs a real ECOA/Reg B
    # compliance gate (core/compliance_rules.py's "ecoa_adverse_action" rule,
    # session 38) on every "declined" decision -- it's correctly BLOCKED unless
    # a real documented reason is supplied. Default to a real reason here so
    # this helper's callers don't need to remember that for every decline.
    if decision == "declined" and notes is None:
        notes = "Insufficient documented income for requested terms"

    return deals_api.record_lender_decision_api(
        FINANCE, "EMP-00002", deal_id, decision, countered_terms=countered_terms, notes=notes
    )


def _n_decided_submissions(lender_id, decision, count, credit_score=700, prefix="CUST"):
    """Creates `count` real deals, each submitted to `lender_id` and decided the
    same way -- the bulk-fixture helper the sample-size/ranking tests below
    build on."""

    for i in range(count):
        deal = _deal_submitted_to_lender(
            lender_id, f"{prefix}-{i}", f"VEH-{prefix}-{i}", credit_score=credit_score
        )
        result = _decide(deal["id"], decision)
        assert "error" not in result, f"decision {decision} #{i} unexpectedly failed: {result}"


# --- Dashboard overview ---


def test_dashboard_overview_with_no_submissions():

    overview = li.get_dashboard_overview()

    assert overview["total_submissions"] == 0
    assert overview["decided_submissions"] == 0
    assert overview["overall_approval_rate_pct"] is None
    assert overview["lenders_with_sufficient_data"] == 0


# --- Scorecards ---


def test_scorecard_reflects_approved_submission():

    _add_lender("LENDER-1")
    deal = _deal_submitted_to_lender("LENDER-1", "CUST-1", "VEH-1", credit_score=700)
    _decide(deal["id"], "approved")

    scorecards = li.get_lender_scorecards()
    card = next(c for c in scorecards if c["lender_id"] == "LENDER-1")

    assert card["total_submissions"] == 1
    assert card["decided_submissions"] == 1
    assert card["approved_count"] == 1
    assert card["declined_count"] == 0
    assert card["approval_rate_pct"] == 100.0
    assert card["avg_offered_apr"] == 6.9
    assert card["has_sufficient_data"] is False


def test_scorecard_has_sufficient_data_at_min_sample_size():

    _add_lender("LENDER-1")
    _n_decided_submissions("LENDER-1", "approved", li.MIN_SAMPLE_SIZE)

    card = next(c for c in li.get_lender_scorecards() if c["lender_id"] == "LENDER-1")

    assert card["decided_submissions"] == li.MIN_SAMPLE_SIZE
    assert card["has_sufficient_data"] is True


def test_scorecard_excludes_in_house_lender():

    _add_customer("CUST-1", credit_score=700)
    _add_vehicle("VEH-1")
    deal = deals_api.create_deal_api(SALES, "EMP-00001", "CUST-1", "VEH-1")
    deal = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "Standard", 30000, 3000, 60)
    scenario_id = deal["scenarios"][0]["id"]
    deal = deals_api.select_scenario_api(SALES, "EMP-00001", deal["id"], scenario_id)
    deals_api.choose_in_house_financing_api(FINANCE, "EMP-00002", deal["id"])

    from core.deals import list_lenders, IN_HOUSE_LENDER_NAME

    assert any(l.attributes.get("Name") == IN_HOUSE_LENDER_NAME for l in list_lenders())

    scorecards = li.get_lender_scorecards()

    assert all(c["lender_name"] != IN_HOUSE_LENDER_NAME for c in scorecards)


# --- Submission log ---


def test_submission_log_filters_by_lender():

    _add_lender("LENDER-1", name="Bank A")
    _add_lender("LENDER-2", name="Bank B")

    deal_a = _deal_submitted_to_lender("LENDER-1", "CUST-1", "VEH-1")
    deal_b = _deal_submitted_to_lender("LENDER-2", "CUST-2", "VEH-2")

    log_a = li.get_submission_log(lender_id="LENDER-1")

    assert len(log_a) == 1
    assert log_a[0]["deal_id"] == deal_a["id"]


def test_submission_log_includes_customer_and_vehicle_brief():

    _add_lender("LENDER-1")
    _add_customer("CUST-1", credit_score=700, first="Priya", last="Nair")
    _add_vehicle("VEH-1", make="Toyota", model="Camry", year="2024")

    deal = deals_api.create_deal_api(SALES, "EMP-00001", "CUST-1", "VEH-1")
    deal = deals_api.add_scenario_api(SALES, "EMP-00001", deal["id"], "Standard", 30000, 3000, 60)
    scenario_id = deal["scenarios"][0]["id"]
    deal = deals_api.select_scenario_api(SALES, "EMP-00001", deal["id"], scenario_id)
    deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], "LENDER-1")

    entry = li.get_submission_log()[0]

    assert entry["customer_name"] == "Priya Nair"
    assert entry["vehicle_description"] == "2024 Toyota Camry"


def test_resubmission_after_decline_leaves_both_entries_on_record():

    _add_lender("LENDER-1", name="Bank A")
    _add_lender("LENDER-2", name="Bank B")

    deal = _deal_submitted_to_lender("LENDER-1", "CUST-1", "VEH-1")
    _decide(deal["id"], "declined", notes="Insufficient income")

    # A declined deal stays in "financing" status (core/deals.py's own documented
    # "no dead end, try again" behavior) -- resubmitting to a different lender
    # should succeed and leave the FIRST submission's real record intact.
    resubmitted = deals_api.submit_to_lender_api(FINANCE, "EMP-00002", deal["id"], "LENDER-2")

    assert "error" not in resubmitted

    entries = [s for s in li.get_submission_log() if s["deal_id"] == deal["id"]]

    assert len(entries) == 2
    assert {e["lender_id"] for e in entries} == {"LENDER-1", "LENDER-2"}
    declined_entry = next(e for e in entries if e["lender_id"] == "LENDER-1")
    assert declined_entry["decision"] == "declined"


# --- Recommendation ---


def test_recommendation_insufficient_data_when_below_min_sample():

    _add_lender("LENDER-1")
    deal = _deal_submitted_to_lender("LENDER-1", "CUST-1", "VEH-1")
    _decide(deal["id"], "approved")

    rec = li.get_lender_recommendation()

    assert not any(r["lender_id"] == "LENDER-1" for r in rec["ranked"])
    assert any(r["lender_id"] == "LENDER-1" for r in rec["insufficient_data"])


def test_recommendation_ranks_by_approval_rate_then_apr():

    _add_lender("LENDER-STRONG", name="Strong Bank")
    _add_lender("LENDER-WEAK", name="Weak Bank")

    _n_decided_submissions("LENDER-STRONG", "approved", li.MIN_SAMPLE_SIZE, prefix="STRONG")
    # A mix so LENDER-WEAK's real approval rate is strictly lower.
    for i in range(li.MIN_SAMPLE_SIZE):
        deal = _deal_submitted_to_lender("LENDER-WEAK", f"WEAK-{i}", f"VEH-WEAK-{i}")
        _decide(deal["id"], "approved" if i == 0 else "declined")

    rec = li.get_lender_recommendation()
    ranked_ids = [r["lender_id"] for r in rec["ranked"]]

    assert ranked_ids[0] == "LENDER-STRONG"
    assert "LENDER-WEAK" in ranked_ids
    assert ranked_ids.index("LENDER-STRONG") < ranked_ids.index("LENDER-WEAK")


def test_recommendation_rejects_unknown_deal_id():

    result = li.get_lender_recommendation(deal_id="DEAL-404")

    assert "error" in result


def test_recommendation_tier_scoping_when_sufficient_tier_data_exists():

    _add_lender("LENDER-1")
    # 5 real decided, near-prime-tier (credit_score=700) submissions -- clears
    # MIN_SAMPLE_SIZE within that specific tier.
    _n_decided_submissions("LENDER-1", "approved", li.MIN_SAMPLE_SIZE, credit_score=700)

    # A separate deal for the same near-prime tier, used only to scope the
    # recommendation call itself.
    _add_customer("CUST-LOOKUP", credit_score=705)
    _add_vehicle("VEH-LOOKUP")
    lookup_deal = deals_api.create_deal_api(SALES, "EMP-00001", "CUST-LOOKUP", "VEH-LOOKUP")

    rec = li.get_lender_recommendation(deal_id=lookup_deal["id"])
    entry = next(r for r in rec["ranked"] if r["lender_id"] == "LENDER-1")

    assert rec["credit_tier"] == "near-prime (660-739)"
    assert entry["basis"] == "credit tier: near-prime (660-739)"
    assert "ranked by their real track record" in rec["tier_note"]


def test_recommendation_falls_back_to_overall_when_tier_data_insufficient():

    _add_lender("LENDER-1")
    # Only near-prime submissions on file for this lender -- a prime-tier lookup
    # deal has no same-tier data to scope against, so this must fall back to the
    # lender's overall track record with the honest fallback note, not silently
    # omit the lender or fabricate a tier-scoped number.
    _n_decided_submissions("LENDER-1", "approved", li.MIN_SAMPLE_SIZE, credit_score=700)

    _add_customer("CUST-PRIME", credit_score=750)
    _add_vehicle("VEH-PRIME")
    prime_deal = deals_api.create_deal_api(SALES, "EMP-00001", "CUST-PRIME", "VEH-PRIME")

    rec = li.get_lender_recommendation(deal_id=prime_deal["id"])
    entry = next(r for r in rec["ranked"] if r["lender_id"] == "LENDER-1")

    assert rec["credit_tier"] == "prime (740+)"
    assert entry["basis"] == "overall"
    assert "No lender currently has enough decided submissions" in rec["tier_note"]


# --- ACL layer ---


def test_dashboard_overview_api_denies_unauthorized_role():

    result = li_api.get_dashboard_overview_api(MARKETING)

    assert "error" in result


def test_dashboard_overview_api_allows_every_view_role():

    for role in (ADMIN, OPERATIONS, SALES, FINANCE):

        result = li_api.get_dashboard_overview_api(role)

        assert "error" not in result, f"role {role} was unexpectedly denied"


def test_lender_scorecards_api_denies_unauthorized_role():

    result = li_api.get_lender_scorecards_api(SERVICE)

    assert "error" in result


def test_submission_log_api_denies_unauthorized_role():

    result = li_api.get_submission_log_api(MARKETING)

    assert "error" in result


def test_lender_recommendation_api_denies_unauthorized_role():

    result = li_api.get_lender_recommendation_api(SERVICE)

    assert "error" in result
