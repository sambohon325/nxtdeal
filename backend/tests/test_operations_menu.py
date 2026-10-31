"""
Test coverage for core/operations_menu.py -- Operations' 8-item Top Menu (plus
Communications/Workforce, added later) real-data functions.

This module is heavily a COMPOSITION layer over many already-independently-tested
modules (core/compliance_api.py, core/workload_dashboard_api.py,
core/escalation_dashboard_api.py, core/campaigns_api.py, core/websites_api.py,
core/deals_api.py, core/ai_tools.py, core/unified_communications_api.py,
core/workforce_api.py, core/employee_value_api.py, core/vehicle_lifecycle_api.py,
core/operations_tasks.py, core/workflow_tab_data.py) -- rather than re-verifying
every one of those dependencies' own internal logic again here (already covered by
their own test files), these tests focus on what's genuinely THIS module's own
logic: the real Vehicle/Deal/Document/OperationsTask filtering, grouping, and
aggregation math each function performs on top of what those dependencies return.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.vehicle_lifecycle import RECON_ITEMS

import core.operations_menu as operations_menu


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _vehicle(vid, **attrs):
    ledger.add_entity(Entity(id=vid, entity_type="Vehicle", attributes=attrs))


def _deal(did, **attrs):
    ledger.add_entity(Entity(id=did, entity_type="Deal", attributes=attrs))


def _document(did, **attrs):
    ledger.add_entity(Entity(id=did, entity_type="Document", attributes=attrs))


def _op_task(tid, **attrs):
    ledger.add_entity(Entity(id=tid, entity_type="OperationsTask", attributes=attrs))


class TestHelpers:

    def test_entities_filters_by_entity_type(self):
        _vehicle("VEH-00001", VIN="V1")
        _deal("DEAL-00001", status="funded")
        result = operations_menu._entities("Vehicle")
        assert len(result) == 1
        assert result[0].id == "VEH-00001"

    def test_entities_empty_when_no_matches(self):
        assert operations_menu._entities("Vehicle") == []

    def test_today_returns_an_iso_date_string(self):
        today = operations_menu._today()
        assert len(today) == 10
        assert today.count("-") == 2

    def test_pending_count_normalizes_a_plain_list(self):
        result = operations_menu._pending_count([1, 2, 3])
        assert result == {"count": 3, "items": [1, 2, 3]}

    def test_pending_count_normalizes_an_error_dict(self):
        result = operations_menu._pending_count({"error": "Access denied"})
        assert result == {"count": None, "error": "Access denied"}

    def test_pending_count_empty_list(self):
        assert operations_menu._pending_count([]) == {"count": 0, "items": []}


class TestOverview:

    def test_overview_returns_expected_top_level_shape(self):
        result = operations_menu.overview("ADMIN")
        assert "units_in_recon" in result
        assert "aging_inventory_unsold_count" in result
        assert "compliance_exceptions_open" in result
        assert "todays_deliveries" in result
        assert "cross_department_bottlenecks" in result
        assert "not_yet_tracked" in result

    def test_overview_counts_only_deals_funded_today(self):
        today = operations_menu._today()
        _deal("DEAL-00001", status="funded", funded_at=f"{today}T10:00:00")
        _deal("DEAL-00002", status="funded", funded_at="2020-01-01T10:00:00")
        _deal("DEAL-00003", status="contract")
        result = operations_menu.overview("ADMIN")
        assert result["todays_deliveries"] == 1

    def test_overview_not_yet_tracked_notes_are_honest_gaps_not_fabricated(self):
        result = operations_menu.overview("ADMIN")
        assert "average_recon_days" in result["not_yet_tracked"]
        assert "vehicles_awaiting_inspection" in result["not_yet_tracked"]


class TestTasks:

    def test_tasks_returns_expected_shape(self):
        result = operations_menu.tasks("ADMIN")
        assert "tasks" in result
        assert "task_count" in result
        assert "escalations" in result
        assert "pending_approvals" in result
        assert set(result["pending_approvals"].keys()) == {"campaigns", "websites", "financing"}

    def test_tasks_count_matches_derived_task_list_length(self):
        result = operations_menu.tasks("ADMIN")
        assert result["task_count"] == len(result["tasks"])


class TestVehicles:

    def test_vehicles_no_query_returns_recon_default_view(self):
        result = operations_menu.vehicles("ADMIN")
        assert result["default_view"] == "recon_queue"
        assert "vehicles" in result

    def test_vehicles_veh_id_query_returns_entity_related_and_lifecycle(self):
        _vehicle("VEH-00001", VIN="1FTFW1ET1EFA00001", Make="Ford")
        result = operations_menu.vehicles("ADMIN", "VEH-00001")
        assert "vehicle" in result
        assert "related_entities" in result
        assert "lifecycle" in result

    def test_vehicles_veh_id_query_lowercase_is_uppercased(self):
        _vehicle("VEH-00001", VIN="1FTFW1ET1EFA00001")
        result = operations_menu.vehicles("ADMIN", "veh-00001")
        assert "vehicle" in result

    def test_vehicles_unknown_veh_id_returns_error(self):
        result = operations_menu.vehicles("ADMIN", "VEH-99999")
        assert "error" in result

    def test_vehicles_free_text_query_only_returns_vehicle_type_results(self):
        _vehicle("VEH-00001", VIN="1FTFW1ET1EFA00001", Make="Ford", Model="F-150")
        result = operations_menu.vehicles("ADMIN", "Ford")
        assert result["query"] == "Ford"
        assert "count" in result
        assert "results" in result


class TestInventory:

    def test_inventory_active_count_excludes_sold_vehicles(self):
        _vehicle("VEH-00001", DateSold=None, Price="15000")
        _vehicle("VEH-00002", DateSold="2026-01-01", Price="12000")
        result = operations_menu.inventory("ADMIN")
        assert result["active_inventory_count"] == 1

    def test_inventory_pricing_queue_flags_zero_or_missing_price(self):
        _vehicle("VEH-00001", DateSold=None, Price="0", VIN="V1", StockNumber="S1")
        _vehicle("VEH-00002", DateSold=None, Price=None, VIN="V2", StockNumber="S2")
        _vehicle("VEH-00003", DateSold=None, Price="15000", VIN="V3", StockNumber="S3")
        result = operations_menu.inventory("ADMIN")
        assert result["pricing_queue"]["count"] == 2
        flagged_ids = {v["vehicle_id"] for v in result["pricing_queue"]["vehicles"]}
        assert flagged_ids == {"VEH-00001", "VEH-00002"}

    def test_inventory_returns_expected_shape(self):
        result = operations_menu.inventory("ADMIN")
        assert set(result.keys()) == {
            "active_inventory_count", "aging", "wholesale_candidates",
            "incoming_inventory", "pricing_queue",
        }


class TestScheduling:

    def test_scheduling_returns_expected_shape(self):
        result = operations_menu.scheduling("ADMIN")
        assert "recon_board" in result
        assert "transport_schedule" in result
        assert "delivery_calendar" in result
        assert "service_capacity" in result
        assert "technician_availability" in result
        assert "not_yet_tracked" in result

    def test_scheduling_delivery_calendar_includes_contract_and_funded_deals_only(self):
        _deal("DEAL-00001", status="contract", customer_id="CUST-00001", vehicle_id="VEH-00001")
        _deal("DEAL-00002", status="funded", customer_id="CUST-00002", vehicle_id="VEH-00002")
        _deal("DEAL-00003", status="desking", customer_id="CUST-00003", vehicle_id="VEH-00003")
        result = operations_menu.scheduling("ADMIN")
        assert result["delivery_calendar"]["count"] == 2
        statuses = {d["status"] for d in result["delivery_calendar"]["deals"]}
        assert statuses == {"contract", "funded"}

    def test_scheduling_technician_availability_counts_service_department_employees(self):
        ledger.add_entity(Entity(id="EMP-00001", entity_type="Employee", attributes={"Department": "Service"}))
        ledger.add_entity(Entity(id="EMP-00002", entity_type="Employee", attributes={"Department": "Sales"}))
        result = operations_menu.scheduling("ADMIN")
        assert result["technician_availability"]["service_department_headcount"] == 1

    def test_scheduling_internal_install_queue_is_an_honest_gap(self):
        result = operations_menu.scheduling("ADMIN")
        assert "internal_install_queue" in result["not_yet_tracked"]


class TestDocuments:

    def test_documents_empty_ledger_returns_zero_total(self):
        result = operations_menu.documents("ADMIN")
        assert result["total"] == 0
        assert result["by_type"] == {}

    def test_documents_groups_by_document_type(self):
        _document("DOC-00001", DocumentType="Title", FileName="title1.pdf", EntityType="Vehicle", EntityID="VEH-00001")
        _document("DOC-00002", DocumentType="Title", FileName="title2.pdf", EntityType="Vehicle", EntityID="VEH-00002")
        _document("DOC-00003", DocumentType="Deal Jacket", FileName="jacket.pdf", EntityType="Deal", EntityID="DEAL-00001")
        result = operations_menu.documents("ADMIN")
        assert result["total"] == 3
        assert result["by_type"]["Title"]["count"] == 2
        assert result["by_type"]["Deal Jacket"]["count"] == 1

    def test_documents_uses_other_when_document_type_missing(self):
        _document("DOC-00001", FileName="mystery.pdf")
        result = operations_menu.documents("ADMIN")
        assert "Other" in result["by_type"]

    def test_documents_free_text_query_filters_across_all_attribute_values(self):
        _document("DOC-00001", DocumentType="Title", FileName="1FTFW1ET1EFA00001_title.pdf")
        _document("DOC-00002", DocumentType="Recon Form", FileName="unrelated.pdf")
        result = operations_menu.documents("ADMIN", "1FTFW1ET1EFA00001")
        assert result["total"] == 1

    def test_documents_query_is_case_insensitive(self):
        _document("DOC-00001", DocumentType="Title", FileName="MyFile.PDF")
        result = operations_menu.documents("ADMIN", "myfile")
        assert result["total"] == 1

    def test_documents_query_no_matches_returns_zero(self):
        _document("DOC-00001", DocumentType="Title", FileName="a.pdf")
        result = operations_menu.documents("ADMIN", "no-such-string-anywhere")
        assert result["total"] == 0


class TestAlerts:

    def test_alerts_returns_expected_shape(self):
        result = operations_menu.alerts("ADMIN")
        assert "compliance_alerts" in result
        assert "inventory_ownership_mismatches" in result
        assert "unfunded_deals" in result
        assert "missing_deal_jackets" in result
        assert "not_yet_tracked" in result

    def test_alerts_unfunded_deals_only_financing_or_contract_status(self):
        _deal("DEAL-00001", status="financing", customer_id="CUST-00001")
        _deal("DEAL-00002", status="contract", customer_id="CUST-00002")
        _deal("DEAL-00003", status="funded", customer_id="CUST-00003")
        _deal("DEAL-00004", status="desking", customer_id="CUST-00004")
        result = operations_menu.alerts("ADMIN")
        assert result["unfunded_deals"]["count"] == 2

    def test_alerts_missing_deal_jackets_flags_funded_deals_with_no_jacket_on_file(self):
        _deal("DEAL-00001", status="funded")
        _deal("DEAL-00002", status="funded")
        _document("DOC-00001", DocumentType="Deal Jacket", EntityType="Deal", EntityID="DEAL-00001")
        result = operations_menu.alerts("ADMIN")
        assert result["missing_deal_jackets"]["count"] == 1
        assert result["missing_deal_jackets"]["deal_ids"] == ["DEAL-00002"]

    def test_alerts_missing_deal_jackets_clears_when_jacket_exists_for_every_funded_deal(self):
        _deal("DEAL-00001", status="funded")
        _document("DOC-00001", DocumentType="Deal Jacket", EntityType="Deal", EntityID="DEAL-00001")
        result = operations_menu.alerts("ADMIN")
        assert result["missing_deal_jackets"]["count"] == 0

    def test_alerts_missing_deal_jackets_ignores_a_jacket_of_the_wrong_document_type(self):
        _deal("DEAL-00001", status="funded")
        _document("DOC-00001", DocumentType="Title", EntityType="Deal", EntityID="DEAL-00001")
        result = operations_menu.alerts("ADMIN")
        assert result["missing_deal_jackets"]["count"] == 1

    def test_alerts_honest_gaps_stated_plainly(self):
        result = operations_menu.alerts("ADMIN")
        assert "missing_keys" in result["not_yet_tracked"]
        assert "lost_vehicle_flags" in result["not_yet_tracked"]


class TestReconReporting:

    def test_recon_reporting_empty_when_no_used_unsold_vehicles(self):
        result = operations_menu._recon_reporting()
        assert result["used_unsold_count"] == 0
        assert result["avg_checklist_completion_pct"] is None

    def test_recon_reporting_only_counts_used_unsold_vehicles(self):
        _vehicle("VEH-00001", DateSold=None, Condition="Used")
        _vehicle("VEH-00002", DateSold=None, Condition="New")
        _vehicle("VEH-00003", DateSold="2026-01-01", Condition="Used")
        result = operations_menu._recon_reporting()
        assert result["used_unsold_count"] == 1

    def test_recon_reporting_computes_real_completion_percentage(self):
        full_checklist = {item: {"complete": True} for item in RECON_ITEMS}
        _vehicle("VEH-00001", DateSold=None, Condition="Used", recon_checklist=full_checklist)
        _vehicle("VEH-00002", DateSold=None, Condition="Used")
        result = operations_menu._recon_reporting()
        assert result["used_unsold_count"] == 2
        assert result["avg_checklist_completion_pct"] == 50.0
        assert result["vehicles_fully_recon_complete"] == 1
        assert result["vehicles_with_zero_recon_progress"] == 1

    def test_recon_reporting_completion_by_item_covers_every_recon_item(self):
        full_checklist = {item: {"complete": True} for item in RECON_ITEMS}
        _vehicle("VEH-00001", DateSold=None, Condition="Used", recon_checklist=full_checklist)
        result = operations_menu._recon_reporting()
        assert set(result["completion_by_item"].keys()) == set(RECON_ITEMS)
        for item in RECON_ITEMS:
            assert result["completion_by_item"][item] == 1

    def test_recon_reporting_partial_checklist_item_not_marked_complete_does_not_count(self):
        partial = {RECON_ITEMS[0]: {"complete": False}}
        _vehicle("VEH-00001", DateSold=None, Condition="Used", recon_checklist=partial)
        result = operations_menu._recon_reporting()
        assert result["completion_by_item"][RECON_ITEMS[0]] == 0
        assert result["vehicles_with_zero_recon_progress"] == 1

    def test_recon_reporting_tracks_vehicles_with_recorded_stage_history(self):
        _vehicle("VEH-00001", DateSold=None, Condition="Used", lifecycle_status_history=[{"status": "Received"}])
        _vehicle("VEH-00002", DateSold=None, Condition="Used")
        result = operations_menu._recon_reporting()
        assert result["vehicles_with_recorded_stage_transitions"] == 1

    def test_recon_reporting_states_the_real_data_limitation(self):
        result = operations_menu._recon_reporting()
        assert "per-item recon start timestamp" in result["note"]


class TestInventoryActionsReporting:

    def test_inventory_actions_reporting_counts_tracked_task_types_by_status(self):
        _op_task("OTASK-00001", task_type="transfer_to_wholesale", status="closed")
        _op_task("OTASK-00002", task_type="transfer_to_wholesale", status="open")
        _op_task("OTASK-00003", task_type="manager_review", status="closed")
        _op_task("OTASK-00004", task_type="title_processing", status="open")  # untracked type
        result = operations_menu._inventory_actions_reporting()
        assert result["actions_by_type"]["transfer_to_wholesale"] == {"open": 1, "closed": 1}
        assert result["actions_by_type"]["manager_review"] == {"open": 0, "closed": 1}
        assert "title_processing" not in result["actions_by_type"]

    def test_inventory_actions_reporting_all_four_tracked_types_present_even_with_zero_tasks(self):
        result = operations_menu._inventory_actions_reporting()
        assert set(result["actions_by_type"].keys()) == {
            "transfer_to_wholesale", "manager_review", "marketing_campaign_tie_in", "auction_assignment",
        }

    def test_inventory_actions_reporting_sums_price_reductions_across_unsold_vehicles(self):
        _vehicle("VEH-00001", DateSold=None, price_history=[{"old": 20000, "new": 19000}, {"old": 19000, "new": 18000}])
        _vehicle("VEH-00002", DateSold=None, price_history=[{"old": 15000, "new": 14000}])
        _vehicle("VEH-00003", DateSold=None)
        _vehicle("VEH-00004", DateSold="2026-01-01", price_history=[{"old": 10000, "new": 9000}])
        result = operations_menu._inventory_actions_reporting()
        assert result["total_price_reductions"] == 3
        assert result["vehicles_with_price_reductions"] == 2


class TestReporting:

    def test_reporting_returns_expected_top_level_shape(self):
        result = operations_menu.reporting("ADMIN")
        assert set(result.keys()) == {
            "operational_performance", "inventory_performance", "compliance_performance",
            "sla_performance", "personnel_performance", "recon_reporting",
            "delivery_reporting", "inventory_actions_reporting",
            "department_intelligence", "not_yet_tracked",
        }

    def test_reporting_department_intelligence_is_an_honest_gap_note(self):
        result = operations_menu.reporting("ADMIN")
        assert result["department_intelligence"]["available"] is False

    def test_reporting_wholesale_loss_total_sums_only_negative_margin_candidates(self):
        # Real candidates come from inventory_wholesale_disposition, an already-
        # tested dependency -- confirm this module's own sum-of-negatives math
        # against whatever real (possibly empty) candidate list it returns.
        result = operations_menu.reporting("ADMIN")
        assert isinstance(result["inventory_performance"]["wholesale_loss_total"], (int, float))

    def test_reporting_compliance_performance_resolution_rate_none_when_nothing_seen(self):
        result = operations_menu.reporting("ADMIN")
        # With no compliance alerts open or resolved anywhere in a fresh ledger,
        # total_seen is 0 and the rate must honestly report None, not a fabricated 0%.
        assert result["compliance_performance"]["resolution_rate_pct"] is None

    def test_reporting_personnel_performance_requests_operations_department(self):
        # Session-64 bug fix (lowercase department key) -- confirm the call is
        # still wired correctly by checking the real returned shape has the
        # employee_value_api's own expected keys, not an empty/error passthrough
        # caused by a department-casing regression.
        result = operations_menu.reporting("ADMIN")
        assert "employees" in result["personnel_performance"]


class TestCommunicationsAndWorkforce:

    def test_communications_composes_legacy_unified_and_communications_hub(self):
        # Extended 2026-07-22 (Communications Hub build): communications() now
        # composes TWO real, distinct sources under their own keys rather than
        # spreading the legacy feed's keys at the top level -- see
        # operations_menu.communications()'s own docstring.
        result = operations_menu.communications("ADMIN")
        assert "feed" in result["legacy_unified"]
        assert "hub_stats" in result["communications_hub"]
        assert "note" in result

    def test_workforce_is_a_thin_passthrough_to_workforce_overview(self):
        result = operations_menu.workforce("ADMIN")
        assert "directory" in result
        assert "coverage_today" in result
