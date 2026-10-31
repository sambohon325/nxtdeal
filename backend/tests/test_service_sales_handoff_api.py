"""
Tests for core/service_sales_handoff.py / core/service_sales_handoff_api.py --
Service-to-Sales Opportunity Handoff (declined-service signal, high-cost-repair
signal, manual-flag signal, promote-to-Lead/dismiss lifecycle), plus the thin
ACL layer wired into api/app.py.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, SERVICE_RECORD, LEAD
from core.relationship_types import GENERATED_LEAD
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

import core.service_sales_handoff as service_sales_handoff
import core.lead_intake as lead_intake_module
from core.service_sales_handoff import (
    HIGH_COST_THRESHOLD,
    OPPORTUNITY_TYPES,
    get_declined_service_candidates,
    get_high_cost_repair_candidates,
    get_manually_flagged_candidates,
    get_opportunity_queue,
    flag_manual_opportunity,
    get_ro_handoff_status,
    promote_to_sales,
    dismiss_opportunity,
    get_handoff_stats,
)
from core.service_sales_handoff_api import (
    get_opportunity_queue_api,
    get_ro_handoff_status_api,
    flag_manual_opportunity_api,
    promote_to_sales_api,
    dismiss_opportunity_api,
    get_handoff_stats_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(service_sales_handoff, "save_graph", lambda filepath: None)
    monkeypatch.setattr(lead_intake_module, "save_graph", lambda filepath: None)


def _customer(customer_id="CUST-1", first="Jordan", last="Ramirez", email="jordan@example.com", phone="555-0100"):
    entity = Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={"FirstName": first, "LastName": last, "Email": email, "Phone": phone, "CustomerID": customer_id},
    )
    ledger.add_entity(entity)
    return entity


def _vehicle(vehicle_id="VEH-1", vin="VIN0001", year=2020, make="Ford", model="F-150"):
    entity = Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"VIN": vin, "Year": year, "Make": make, "Model": model},
    )
    ledger.add_entity(entity)
    return entity


_rec_counter = [0]


def _service_record(ro_id=None, customer_raw_key=None, vin=None, description="Brake job",
                     cost=None, estimate=None, sales_handoff=None):
    _rec_counter[0] += 1
    if ro_id is None:
        ro_id = f"SRV-TEST-{_rec_counter[0]:05d}"
    attrs = {"CustomerID": customer_raw_key, "VIN": vin, "Description": description}
    if cost is not None:
        attrs["Cost"] = cost
    if estimate is not None:
        attrs["estimate"] = estimate
    if sales_handoff is not None:
        attrs["sales_handoff"] = sales_handoff
    entity = Entity(id=ro_id, entity_type=SERVICE_RECORD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


# ---------------------------------------------------------------------------
# get_declined_service_candidates()
# ---------------------------------------------------------------------------

class TestGetDeclinedServiceCandidates:

    def test_no_declined_records_returns_empty(self):
        _service_record(customer_raw_key="CUST-1", vin="VIN0001")
        assert get_declined_service_candidates() == []

    def test_declined_estimate_surfaces_as_candidate(self):
        _customer()
        _vehicle()
        ro = _service_record(
            customer_raw_key="CUST-1", vin="VIN0001", description="Timing belt",
            estimate={"amount": 900.0, "approved": False, "decline_reason": "Too expensive"},
        )
        candidates = get_declined_service_candidates()
        assert len(candidates) == 1
        c = candidates[0]
        assert c["ro_id"] == ro.id
        assert c["opportunity_type"] == "declined_service"
        assert c["customer_id"] == "CUST-1"
        assert c["amount"] == 900.0
        assert c["reason"] == "Too expensive"
        assert c["handoff_status"] == "open"

    def test_decline_reason_falls_back_to_default_text(self):
        _customer()
        _service_record(customer_raw_key="CUST-1", estimate={"amount": 100.0, "approved": False})
        candidates = get_declined_service_candidates()
        assert candidates[0]["reason"] == "Customer declined estimate"

    def test_already_promoted_ro_excluded(self):
        _customer()
        _service_record(
            customer_raw_key="CUST-1",
            estimate={"amount": 100.0, "approved": False},
            sales_handoff={"status": "promoted"},
        )
        assert get_declined_service_candidates() == []

    def test_already_dismissed_ro_excluded(self):
        _customer()
        _service_record(
            customer_raw_key="CUST-1",
            estimate={"amount": 100.0, "approved": False},
            sales_handoff={"status": "dismissed"},
        )
        assert get_declined_service_candidates() == []


# ---------------------------------------------------------------------------
# get_high_cost_repair_candidates()
# ---------------------------------------------------------------------------

class TestGetHighCostRepairCandidates:

    def test_below_threshold_excluded(self):
        _service_record(customer_raw_key="CUST-1", cost=HIGH_COST_THRESHOLD - 1)
        assert get_high_cost_repair_candidates() == []

    def test_at_or_above_threshold_included(self):
        _customer()
        _vehicle()
        ro = _service_record(customer_raw_key="CUST-1", vin="VIN0001", cost=HIGH_COST_THRESHOLD)
        candidates = get_high_cost_repair_candidates()
        assert len(candidates) == 1
        c = candidates[0]
        assert c["ro_id"] == ro.id
        assert c["opportunity_type"] == "high_cost_repair"
        assert c["amount"] == HIGH_COST_THRESHOLD
        assert "heuristic threshold" in c["reason"]

    def test_non_numeric_cost_skipped_not_errored(self):
        _service_record(customer_raw_key="CUST-1", cost="not-a-number")
        assert get_high_cost_repair_candidates() == []

    def test_none_cost_skipped(self):
        entity = Entity(id="SRV-NOCOST", entity_type=SERVICE_RECORD, attributes={})
        ledger.add_entity(entity)
        assert get_high_cost_repair_candidates() == []

    def test_already_promoted_excluded(self):
        _service_record(customer_raw_key="CUST-1", cost=1000.0, sales_handoff={"status": "promoted"})
        assert get_high_cost_repair_candidates() == []

    def test_sorted_by_amount_descending(self):
        _service_record(ro_id="SRV-LOW", customer_raw_key="CUST-1", cost=800.0)
        _service_record(ro_id="SRV-HIGH", customer_raw_key="CUST-1", cost=1500.0)
        candidates = get_high_cost_repair_candidates()
        assert [c["ro_id"] for c in candidates] == ["SRV-HIGH", "SRV-LOW"]

    def test_limit_applied(self):
        for i in range(5):
            _service_record(customer_raw_key="CUST-1", cost=1000.0 + i)
        candidates = get_high_cost_repair_candidates(limit=2)
        assert len(candidates) == 2

    def test_custom_threshold_respected(self):
        _service_record(customer_raw_key="CUST-1", cost=500.0)
        assert get_high_cost_repair_candidates(threshold=400.0) != []
        assert get_high_cost_repair_candidates(threshold=600.0) == []

    def test_no_customer_or_vehicle_on_file_still_returns_candidate(self):
        ro = _service_record(customer_raw_key="CUST-NOPE", vin="VIN-NOPE", cost=1000.0)
        candidates = get_high_cost_repair_candidates()
        assert len(candidates) == 1
        assert candidates[0]["customer_id"] is None
        assert candidates[0]["customer_name"] is None
        assert candidates[0]["vehicle"] is None


# ---------------------------------------------------------------------------
# get_manually_flagged_candidates()
# ---------------------------------------------------------------------------

class TestGetManuallyFlaggedCandidates:

    def test_no_flags_returns_empty(self):
        _service_record(customer_raw_key="CUST-1")
        assert get_manually_flagged_candidates() == []

    def test_manual_open_flag_included(self):
        _customer()
        ro = _service_record(
            customer_raw_key="CUST-1",
            sales_handoff={"status": "open", "opportunity_type": "manual", "notes": "Mentioned trading in"},
        )
        candidates = get_manually_flagged_candidates()
        assert len(candidates) == 1
        c = candidates[0]
        assert c["ro_id"] == ro.id
        assert c["opportunity_type"] == "manual"
        assert c["amount"] is None
        assert c["reason"] == "Mentioned trading in"
        assert c["handoff_status"] == "open"

    def test_manual_flag_with_no_notes_falls_back_to_default_reason(self):
        _customer()
        _service_record(customer_raw_key="CUST-1", sales_handoff={"status": "open", "opportunity_type": "manual"})
        candidates = get_manually_flagged_candidates()
        assert candidates[0]["reason"] == "Manually flagged by a service advisor"

    def test_non_manual_opportunity_type_excluded(self):
        _service_record(
            customer_raw_key="CUST-1",
            sales_handoff={"status": "open", "opportunity_type": "declined_service"},
        )
        assert get_manually_flagged_candidates() == []

    def test_manual_but_not_open_status_excluded(self):
        _service_record(
            customer_raw_key="CUST-1",
            sales_handoff={"status": "promoted", "opportunity_type": "manual"},
        )
        assert get_manually_flagged_candidates() == []


# ---------------------------------------------------------------------------
# get_opportunity_queue()
# ---------------------------------------------------------------------------

class TestGetOpportunityQueue:

    def test_empty_queue(self):
        result = get_opportunity_queue()
        assert result == {
            "count": 0,
            "declined_service_count": 0,
            "high_cost_repair_count": 0,
            "manual_count": 0,
            "candidates": [],
        }

    def test_combines_all_three_sources(self):
        _customer("CUST-1")
        _service_record(customer_raw_key="CUST-1", estimate={"amount": 100.0, "approved": False})
        _service_record(customer_raw_key="CUST-1", cost=1000.0)
        _service_record(customer_raw_key="CUST-1", sales_handoff={"status": "open", "opportunity_type": "manual"})
        result = get_opportunity_queue()
        assert result["count"] == 3
        assert result["declined_service_count"] == 1
        assert result["high_cost_repair_count"] == 1
        assert result["manual_count"] == 1

    def test_same_ro_flagged_by_multiple_signals_dedupes_by_ro_id(self):
        _customer("CUST-1")
        # a single RO that is both a declined estimate AND above the high-cost threshold
        ro = _service_record(
            customer_raw_key="CUST-1", cost=1000.0,
            estimate={"amount": 1000.0, "approved": False},
        )
        result = get_opportunity_queue()
        # counted once in each source's own count, but only once in the deduped list
        assert result["declined_service_count"] == 1
        assert result["high_cost_repair_count"] == 1
        assert result["count"] == 1
        assert result["candidates"][0]["ro_id"] == ro.id

    def test_sorted_by_amount_descending(self):
        _customer("CUST-1")
        _service_record(ro_id="SRV-LOW", customer_raw_key="CUST-1", cost=800.0)
        _service_record(ro_id="SRV-HIGH", customer_raw_key="CUST-1", cost=1500.0)
        result = get_opportunity_queue()
        assert [c["ro_id"] for c in result["candidates"]] == ["SRV-HIGH", "SRV-LOW"]

    def test_limit_applied_to_final_candidates_list(self):
        _customer("CUST-1")
        for i in range(5):
            _service_record(customer_raw_key="CUST-1", cost=1000.0 + i)
        result = get_opportunity_queue(limit=2)
        assert len(result["candidates"]) == 2
        # counts still reflect the full underlying source lists
        assert result["high_cost_repair_count"] == 2  # high_cost_repair itself is also capped by the same limit


# ---------------------------------------------------------------------------
# flag_manual_opportunity()
# ---------------------------------------------------------------------------

class TestFlagManualOpportunity:

    def test_unknown_ro_returns_error(self):
        result = flag_manual_opportunity("SRV-NOPE", "EMP-1")
        assert result == {"error": "Repair order 'SRV-NOPE' not found"}

    def test_flags_open_ro_successfully(self):
        ro = _service_record()
        result = flag_manual_opportunity(ro.id, "EMP-1", notes="Customer hinted at trading in")
        assert result["ro_id"] == ro.id
        state = result["sales_handoff"]
        assert state["status"] == "open"
        assert state["opportunity_type"] == "manual"
        assert state["notes"] == "Customer hinted at trading in"
        assert state["flagged_by"] == "EMP-1"
        assert "flagged_at" in state
        # persisted onto the entity itself
        assert ro.attributes["sales_handoff"] == state

    def test_already_promoted_ro_rejected(self):
        ro = _service_record(sales_handoff={"status": "promoted"})
        result = flag_manual_opportunity(ro.id, "EMP-1")
        assert "already been promoted" in result["error"]

    def test_already_dismissed_ro_rejected(self):
        ro = _service_record(sales_handoff={"status": "dismissed"})
        result = flag_manual_opportunity(ro.id, "EMP-1")
        assert "already been dismissed" in result["error"]

    def test_default_notes_is_empty_string(self):
        ro = _service_record()
        result = flag_manual_opportunity(ro.id, "EMP-1")
        assert result["sales_handoff"]["notes"] == ""


# ---------------------------------------------------------------------------
# get_ro_handoff_status()
# ---------------------------------------------------------------------------

class TestGetRoHandoffStatus:

    def test_unknown_ro_returns_error(self):
        result = get_ro_handoff_status("SRV-NOPE")
        assert result == {"error": "Repair order 'SRV-NOPE' not found"}

    def test_ro_with_no_handoff_state_defaults_to_open(self):
        ro = _service_record()
        result = get_ro_handoff_status(ro.id)
        assert result == {"ro_id": ro.id, "sales_handoff": {"status": "open"}}

    def test_ro_with_existing_state_returned_verbatim(self):
        state = {"status": "dismissed", "reason": "Not interested"}
        ro = _service_record(sales_handoff=state)
        result = get_ro_handoff_status(ro.id)
        assert result["sales_handoff"] == state


# ---------------------------------------------------------------------------
# promote_to_sales()
# ---------------------------------------------------------------------------

class TestPromoteToSales:

    def test_unknown_ro_returns_error(self):
        result = promote_to_sales("SRV-NOPE", "EMP-1")
        assert result == {"error": "Repair order 'SRV-NOPE' not found"}

    def test_no_customer_on_file_returns_error(self):
        ro = _service_record(customer_raw_key="CUST-NOPE")
        result = promote_to_sales(ro.id, "EMP-1")
        assert result == {"error": f"No customer on file for repair order '{ro.id}'"}

    def test_successful_promotion_creates_real_lead_and_relationship(self):
        customer = _customer("CUST-1", first="Jordan", last="Ramirez", email="jordan@example.com", phone="555-0100")
        vehicle = _vehicle("VEH-1", vin="VIN0001")
        ro = _service_record(customer_raw_key="CUST-1", vin="VIN0001")

        result = promote_to_sales(ro.id, "EMP-1", opportunity_type="high_cost_repair")

        assert "error" not in result
        assert result["ro_id"] == ro.id
        assert result["customer_id"] == customer.id
        assert result["assigned_to"] == "EMP-1"
        lead_id = result["lead_id"]

        lead = ledger.get_entity(lead_id)
        assert lead is not None
        assert lead.entity_type == LEAD
        assert lead.attributes["Source"] == "Service Handoff"
        assert lead.attributes["FirstName"] == "Jordan"
        assert lead.attributes["LastName"] == "Ramirez"
        assert lead.attributes["Email"] == "jordan@example.com"
        assert lead.attributes["Phone"] == "555-0100"
        assert lead.attributes["VIN"] == "VIN0001"

        rels = [r for r in ledger.get_relationships()
                if r.relationship_type == GENERATED_LEAD and r.source_id == customer.id and r.target_id == lead_id]
        assert len(rels) == 1

        state = ro.attributes["sales_handoff"]
        assert state["status"] == "promoted"
        assert state["opportunity_type"] == "high_cost_repair"
        assert state["promoted_lead_id"] == lead_id
        assert state["promoted_by"] == "EMP-1"
        assert state["assigned_to"] == "EMP-1"

    def test_assigned_to_overrides_promoted_by_as_lead_owner(self):
        _customer("CUST-1")
        ro = _service_record(customer_raw_key="CUST-1")
        result = promote_to_sales(ro.id, "EMP-1", assigned_to="EMP-2")
        assert result["assigned_to"] == "EMP-2"
        lead = ledger.get_entity(result["lead_id"])
        assert lead.attributes["AssignedSalesperson"] == "EMP-2"

    def test_no_vehicle_on_file_still_succeeds(self):
        _customer("CUST-1")
        ro = _service_record(customer_raw_key="CUST-1", vin="VIN-NOPE")
        result = promote_to_sales(ro.id, "EMP-1")
        assert "error" not in result

    def test_opportunity_type_defaults_to_existing_state_value(self):
        _customer("CUST-1")
        ro = _service_record(
            customer_raw_key="CUST-1",
            sales_handoff={"status": "open", "opportunity_type": "declined_service"},
        )
        result = promote_to_sales(ro.id, "EMP-1")
        assert ro.attributes["sales_handoff"]["opportunity_type"] == "declined_service"

    def test_opportunity_type_defaults_to_manual_when_no_prior_state(self):
        _customer("CUST-1")
        ro = _service_record(customer_raw_key="CUST-1")
        promote_to_sales(ro.id, "EMP-1")
        assert ro.attributes["sales_handoff"]["opportunity_type"] == "manual"

    def test_notes_falls_back_to_existing_state_notes(self):
        _customer("CUST-1")
        ro = _service_record(
            customer_raw_key="CUST-1",
            sales_handoff={"status": "open", "opportunity_type": "manual", "notes": "Earlier note"},
        )
        promote_to_sales(ro.id, "EMP-1")
        assert ro.attributes["sales_handoff"]["notes"] == "Earlier note"

    def test_explicit_notes_override_existing_state_notes(self):
        _customer("CUST-1")
        ro = _service_record(
            customer_raw_key="CUST-1",
            sales_handoff={"status": "open", "opportunity_type": "manual", "notes": "Earlier note"},
        )
        promote_to_sales(ro.id, "EMP-1", notes="New note")
        assert ro.attributes["sales_handoff"]["notes"] == "New note"

    def test_already_promoted_rejected_with_existing_lead_id_in_message(self):
        ro = _service_record(sales_handoff={"status": "promoted", "promoted_lead_id": "LEAD-EXISTING"})
        result = promote_to_sales(ro.id, "EMP-1")
        assert result == {"error": "This RO was already promoted -- Lead LEAD-EXISTING"}

    def test_already_dismissed_rejected(self):
        ro = _service_record(sales_handoff={"status": "dismissed"})
        result = promote_to_sales(ro.id, "EMP-1")
        assert result == {"error": "This opportunity was already dismissed"}

    def test_promoted_ro_drops_out_of_opportunity_queue(self):
        _customer("CUST-1")
        ro = _service_record(customer_raw_key="CUST-1", cost=1000.0)
        assert get_opportunity_queue()["count"] == 1
        promote_to_sales(ro.id, "EMP-1")
        assert get_opportunity_queue()["count"] == 0


# ---------------------------------------------------------------------------
# dismiss_opportunity()
# ---------------------------------------------------------------------------

class TestDismissOpportunity:

    def test_unknown_ro_returns_error(self):
        result = dismiss_opportunity("SRV-NOPE", "EMP-1")
        assert result == {"error": "Repair order 'SRV-NOPE' not found"}

    def test_successful_dismissal(self):
        ro = _service_record()
        result = dismiss_opportunity(ro.id, "EMP-1", reason="Not interested right now")
        state = result["sales_handoff"]
        assert state["status"] == "dismissed"
        assert state["dismissed_by"] == "EMP-1"
        assert state["reason"] == "Not interested right now"
        assert ro.attributes["sales_handoff"] == state

    def test_opportunity_type_defaults_to_existing_state_value(self):
        ro = _service_record(sales_handoff={"status": "open", "opportunity_type": "high_cost_repair"})
        dismiss_opportunity(ro.id, "EMP-1")
        assert ro.attributes["sales_handoff"]["opportunity_type"] == "high_cost_repair"

    def test_already_promoted_rejected(self):
        ro = _service_record(sales_handoff={"status": "promoted", "promoted_lead_id": "LEAD-1"})
        result = dismiss_opportunity(ro.id, "EMP-1")
        assert result == {"error": "This RO was already promoted -- Lead LEAD-1"}

    def test_already_dismissed_rejected(self):
        ro = _service_record(sales_handoff={"status": "dismissed"})
        result = dismiss_opportunity(ro.id, "EMP-1")
        assert result == {"error": "This opportunity was already dismissed"}

    def test_dismissed_ro_drops_out_of_opportunity_queue(self):
        _customer("CUST-1")
        ro = _service_record(customer_raw_key="CUST-1", cost=1000.0)
        assert get_opportunity_queue()["count"] == 1
        dismiss_opportunity(ro.id, "EMP-1")
        assert get_opportunity_queue()["count"] == 0


# ---------------------------------------------------------------------------
# get_handoff_stats()
# ---------------------------------------------------------------------------

class TestGetHandoffStats:

    def test_stats_with_no_data(self):
        result = get_handoff_stats()
        assert result == {
            "open_opportunities": 0,
            "declined_service_count": 0,
            "high_cost_repair_count": 0,
            "manual_count": 0,
            "promoted_count": 0,
            "dismissed_count": 0,
        }

    def test_counts_promoted_and_dismissed_across_records(self):
        _service_record(sales_handoff={"status": "promoted"})
        _service_record(sales_handoff={"status": "promoted"})
        _service_record(sales_handoff={"status": "dismissed"})
        result = get_handoff_stats()
        assert result["promoted_count"] == 2
        assert result["dismissed_count"] == 1

    def test_includes_open_opportunity_counts_from_queue(self):
        _customer("CUST-1")
        _service_record(customer_raw_key="CUST-1", cost=1000.0)
        result = get_handoff_stats()
        assert result["open_opportunities"] == 1
        assert result["high_cost_repair_count"] == 1


# ---------------------------------------------------------------------------
# ACL layer (core/service_sales_handoff_api.py)
# ---------------------------------------------------------------------------

_VIEW_ROLES = [ADMIN, OPERATIONS, SALES, SERVICE, FINANCE]
_MUTATE_ROLES = [ADMIN, OPERATIONS, SALES, SERVICE]


class TestGetOpportunityQueueApi:

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_allowed_roles_can_view(self, role):
        result = get_opportunity_queue_api(role)
        assert "error" not in result

    def test_marketing_denied(self):
        result = get_opportunity_queue_api(MARKETING)
        assert result == {"error": "You don't have access to the Service-to-Sales Handoff"}


class TestGetRoHandoffStatusApi:

    def test_allowed_role_delegates(self):
        ro = _service_record()
        result = get_ro_handoff_status_api(SALES, ro.id)
        assert result["ro_id"] == ro.id

    def test_marketing_denied(self):
        result = get_ro_handoff_status_api(MARKETING, "SRV-1")
        assert "error" in result


class TestFlagManualOpportunityApi:

    @pytest.mark.parametrize("role", _MUTATE_ROLES)
    def test_allowed_roles_can_flag(self, role):
        ro = _service_record()
        result = flag_manual_opportunity_api(role, "EMP-1", ro.id)
        assert "error" not in result

    def test_finance_denied(self):
        ro = _service_record()
        result = flag_manual_opportunity_api(FINANCE, "EMP-1", ro.id)
        assert result == {"error": "You don't have access to the Service-to-Sales Handoff"}

    def test_marketing_denied(self):
        ro = _service_record()
        result = flag_manual_opportunity_api(MARKETING, "EMP-1", ro.id)
        assert "error" in result


class TestPromoteToSalesApi:

    def test_allowed_role_delegates(self):
        _customer("CUST-1")
        ro = _service_record(customer_raw_key="CUST-1")
        result = promote_to_sales_api(SALES, "EMP-1", ro.id)
        assert "error" not in result
        assert "lead_id" in result

    def test_finance_denied(self):
        ro = _service_record()
        result = promote_to_sales_api(FINANCE, "EMP-1", ro.id)
        assert result == {"error": "You don't have access to the Service-to-Sales Handoff"}


class TestDismissOpportunityApi:

    def test_allowed_role_delegates(self):
        ro = _service_record()
        result = dismiss_opportunity_api(SERVICE, "EMP-1", ro.id, reason="No thanks")
        assert result["sales_handoff"]["reason"] == "No thanks"

    def test_marketing_denied(self):
        ro = _service_record()
        result = dismiss_opportunity_api(MARKETING, "EMP-1", ro.id)
        assert "error" in result


class TestGetHandoffStatsApi:

    @pytest.mark.parametrize("role", _VIEW_ROLES)
    def test_allowed_roles_can_view(self, role):
        result = get_handoff_stats_api(role)
        assert "error" not in result

    def test_marketing_denied(self):
        result = get_handoff_stats_api(MARKETING)
        assert result == {"error": "You don't have access to the Service-to-Sales Handoff"}


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

class TestConstants:

    def test_opportunity_types(self):
        assert OPPORTUNITY_TYPES == ("declined_service", "high_cost_repair", "manual")

    def test_high_cost_threshold(self):
        assert HIGH_COST_THRESHOLD == 750.0
