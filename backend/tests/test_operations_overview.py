"""
Test coverage for core/operations_overview.py -- Operations' Action Center +
Department Health + Workload Distribution, composed on top of
core/operations_menu.py's own (untouched) KPI overview().

Deals/Vehicles/Documents/Employees are real ledger fixtures (the module's own
_missing_title_vehicles()/_deal_delivery_ready()/stale-financing/employee-
grouping logic all read the graph directly, no external call). The 5
composed dependencies (core.vehicle_lifecycle.list_by_stage as
lifecycle_by_stage, core.compliance_api.list_alerts_api,
core.workflow_tab_data's operations_recon_queue/
inventory_wholesale_disposition/inventory_lot_audit) are all top-level
imports into this module's own namespace, so they're monkeypatched there
directly for full control rather than exercised via their own real,
much-deeper dependency chains (each of those functions has its own test
file).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime, timezone, timedelta

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE, DEAL, DOCUMENT, EMPLOYEE

import core.operations_overview as oo


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _vehicle(vid, date_sold=None, vin=None, stock_number=None):
    attrs = {}
    if date_sold is not None:
        attrs["DateSold"] = date_sold
    if vin is not None:
        attrs["VIN"] = vin
    if stock_number is not None:
        attrs["StockNumber"] = stock_number
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes=attrs))
    return ledger.get_entity(vid)


def _title_document(did, vehicle_id, entity_type=VEHICLE, doc_type="Title"):
    ledger.add_entity(Entity(id=did, entity_type=DOCUMENT, attributes={
        "EntityID": vehicle_id,
        "EntityType": entity_type,
        "DocumentType": doc_type,
    }))


def _deal(did, status=None, customer_id=None, vehicle_id=None, delivery_checklist=None, updated_at=None):
    attrs = {}
    if status is not None:
        attrs["status"] = status
    if customer_id is not None:
        attrs["customer_id"] = customer_id
    if vehicle_id is not None:
        attrs["vehicle_id"] = vehicle_id
    if delivery_checklist is not None:
        attrs["delivery_checklist"] = delivery_checklist
    if updated_at is not None:
        attrs["updated_at"] = updated_at
    ledger.add_entity(Entity(id=did, entity_type=DEAL, attributes=attrs))
    return ledger.get_entity(did)


def _employee(eid, department=None, title=None):
    attrs = {}
    if department is not None:
        attrs["Department"] = department
    if title is not None:
        attrs["Title"] = title
    ledger.add_entity(Entity(id=eid, entity_type=EMPLOYEE, attributes=attrs))
    return ledger.get_entity(eid)


COMPLETE_CHECKLIST = {s: {"a": True, "b": True} for s in oo._DELIVERY_SECTIONS}


def _fake_lifecycle_by_stage(stage_map):
    def fn(stage=None):
        if stage is not None:
            return {stage: stage_map.get(stage, [])}
        return dict(stage_map)
    return fn


def _fake_list_alerts_api(alerts=None, error=None):
    def fn(role, status=None):
        if error is not None:
            return {"error": error}
        return {"alerts": alerts or []}
    return fn


def _fake_wholesale(count=0, candidates=None):
    def fn(role):
        return {"count": count, "candidates": candidates or []}
    return fn


def _fake_recon(used_unsold_count=0):
    def fn(role):
        return {"used_unsold_count": used_unsold_count}
    return fn


def _fake_lot_audit(sold_without_purchase_relationship=0):
    def fn(role):
        return {"sold_without_purchase_relationship": sold_without_purchase_relationship}
    return fn


def _rig(monkeypatch, lifecycle_map=None, alerts=None, alerts_error=None, wholesale_count=0, wholesale_candidates=None):
    monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage(lifecycle_map or {}))
    monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=alerts, error=alerts_error))
    monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale(wholesale_count, wholesale_candidates))


class TestSectionComplete:

    def test_none_is_not_complete(self):
        assert oo._section_complete(None) is False

    def test_empty_dict_is_not_complete(self):
        assert oo._section_complete({}) is False

    def test_no_bool_items_is_not_complete(self):
        assert oo._section_complete({"notes": "some text"}) is False

    def test_all_bool_true_is_complete(self):
        assert oo._section_complete({"a": True, "b": True}) is True

    def test_one_bool_false_is_not_complete(self):
        assert oo._section_complete({"a": True, "b": False}) is False

    def test_ignores_non_bool_fields_alongside_bool_ones(self):
        assert oo._section_complete({"done": True, "notes": "text"}) is True


class TestDealDeliveryReady:

    def test_no_checklist_at_all_is_not_ready(self):
        deal = _deal("DEAL-1", status="contract")
        assert oo._deal_delivery_ready(deal) is False

    def test_fully_complete_checklist_is_ready(self):
        deal = _deal("DEAL-1", status="contract", delivery_checklist=COMPLETE_CHECKLIST)
        assert oo._deal_delivery_ready(deal) is True

    def test_one_incomplete_section_is_not_ready(self):
        checklist = dict(COMPLETE_CHECKLIST)
        checklist["vehicle_prep"] = {"a": True, "b": False}
        deal = _deal("DEAL-1", status="contract", delivery_checklist=checklist)
        assert oo._deal_delivery_ready(deal) is False


class TestMissingTitleVehicles:

    def test_unsold_vehicle_with_no_title_doc_is_included(self):
        _vehicle("V1")
        result = oo._missing_title_vehicles()
        assert [v.id for v in result] == ["V1"]

    def test_unsold_vehicle_with_a_matching_title_doc_is_excluded(self):
        _vehicle("V1")
        _title_document("DOC-1", "V1")
        assert oo._missing_title_vehicles() == []

    def test_sold_vehicle_is_excluded_regardless_of_title_doc(self):
        _vehicle("V1", date_sold="2026-01-01")
        assert oo._missing_title_vehicles() == []

    def test_a_non_title_document_does_not_satisfy_the_check(self):
        _vehicle("V1")
        _title_document("DOC-1", "V1", doc_type="Recon Form")
        assert [v.id for v in oo._missing_title_vehicles()] == ["V1"]

    def test_a_title_doc_on_the_wrong_entity_type_does_not_satisfy_the_check(self):
        _vehicle("V1")
        _title_document("DOC-1", "V1", entity_type="Customer")
        assert [v.id for v in oo._missing_title_vehicles()] == ["V1"]


class TestGetActionCenter:

    def test_deliveries_at_risk_includes_incomplete_contract_and_funded_deals(self, monkeypatch):
        _rig(monkeypatch)
        _deal("DEAL-1", status="contract", delivery_checklist={})
        _deal("DEAL-2", status="funded", delivery_checklist={})
        _deal("DEAL-3", status="desking", delivery_checklist={})
        _deal("DEAL-4", status="contract", delivery_checklist=COMPLETE_CHECKLIST)

        result = oo.get_action_center("ADMIN")

        assert result["deliveries_at_risk"]["count"] == 2
        assert {d["deal_id"] for d in result["deliveries_at_risk"]["deals"]} == {"DEAL-1", "DEAL-2"}

    def test_deliveries_at_risk_capped_at_25(self, monkeypatch):
        _rig(monkeypatch)
        for i in range(27):
            _deal(f"DEAL-{i}", status="contract", delivery_checklist={})

        result = oo.get_action_center("ADMIN")

        assert result["deliveries_at_risk"]["count"] == 27
        assert len(result["deliveries_at_risk"]["deals"]) == 25

    def test_vehicles_missing_titles_reflects_real_ledger_state(self, monkeypatch):
        _rig(monkeypatch)
        _vehicle("V1", vin="VIN1", stock_number="S1")
        _vehicle("V2", vin="VIN2", stock_number="S2")
        _title_document("DOC-1", "V2")

        result = oo.get_action_center("ADMIN")

        assert result["vehicles_missing_titles"]["count"] == 1
        assert result["vehicles_missing_titles"]["vehicles"][0]["vehicle_id"] == "V1"
        assert result["vehicles_missing_titles"]["vehicles"][0]["vin"] == "VIN1"

    def test_vehicles_awaiting_inspection_reads_the_inspection_stage(self, monkeypatch):
        _rig(monkeypatch, lifecycle_map={"Inspection": ["V1", "V2"]})

        result = oo.get_action_center("ADMIN")

        assert result["vehicles_awaiting_inspection"]["count"] == 2
        assert result["vehicles_awaiting_inspection"]["vehicles"] == ["V1", "V2"]

    def test_compliance_violations_reflects_real_open_alert_count(self, monkeypatch):
        _rig(monkeypatch, alerts=[{"id": "A1"}, {"id": "A2"}])

        result = oo.get_action_center("ADMIN")

        assert result["compliance_violations"]["count"] == 2
        assert result["compliance_violations"]["error"] is None

    def test_compliance_violations_surfaces_a_real_access_error(self, monkeypatch):
        _rig(monkeypatch, alerts_error="Access denied")

        result = oo.get_action_center("SALES")

        assert result["compliance_violations"]["count"] is None
        assert result["compliance_violations"]["error"] == "Access denied"

    def test_wholesale_candidates_reflects_the_real_count_and_note(self, monkeypatch):
        _rig(monkeypatch, wholesale_count=3, wholesale_candidates=[{"vehicle_id": "V1"}])

        result = oo.get_action_center("ADMIN")

        assert result["wholesale_candidates_needing_decision"]["count"] == 3
        assert result["wholesale_candidates_needing_decision"]["vehicles"] == [{"vehicle_id": "V1"}]
        assert "substituted_for" in result["wholesale_candidates_needing_decision"]


class TestGetDepartmentHealth:

    def test_sales_ready_inventory_healthy_when_ratio_at_least_half(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({
            "Front Line Ready": ["V1", "V2", "V3"],
            "Inspection": ["V4"],
            "Sold": ["V5"],
            "Delivered": ["V6"],
        }))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Sales Ready Inventory")

        # front_line_ready=3, total_active=3+1=4 (Sold/Delivered excluded) -> 0.75 >= 0.5
        assert check["status"] == "healthy"

    def test_sales_ready_inventory_warning_when_ratio_below_half(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({
            "Front Line Ready": ["V1"],
            "Inspection": ["V2", "V3", "V4"],
        }))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Sales Ready Inventory")

        assert check["status"] == "warning"

    def test_sales_ready_inventory_warning_when_no_active_pipeline_at_all(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Sales Ready Inventory")

        assert check["status"] == "warning"

    def test_recon_delays_warning_above_20(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(21))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Recon Delays")

        assert check["status"] == "warning"

    def test_recon_delays_healthy_at_exactly_20(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(20))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Recon Delays")

        assert check["status"] == "healthy"

    def test_funding_delays_counts_stale_financing_deals(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        now = datetime.now(timezone.utc)
        stale = (now - timedelta(days=5)).isoformat()
        recent = (now - timedelta(days=1)).isoformat()

        _deal("DEAL-STALE", status="financing", updated_at=stale)
        _deal("DEAL-RECENT", status="financing", updated_at=recent)
        _deal("DEAL-NO-UPDATE", status="financing")
        _deal("DEAL-DESKING", status="desking", updated_at=stale)
        _deal("DEAL-BAD-DATE", status="financing", updated_at="not-a-real-date")

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Funding Delays")

        assert check["status"] == "warning"
        assert "1 deals in financing" in check["detail"]

    def test_funding_delays_healthy_with_no_stale_deals(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Funding Delays")

        assert check["status"] == "healthy"

    def test_funding_delays_handles_naive_datetime_string(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        naive_stale = (datetime.now() - timedelta(days=10)).isoformat()
        _deal("DEAL-NAIVE", status="financing", updated_at=naive_stale)

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Funding Delays")

        assert check["status"] == "warning"

    def test_compliance_warning_when_alerts_open(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[{"id": "A1"}]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Compliance")

        assert check["status"] == "warning"

    def test_compliance_degrades_gracefully_on_a_denied_role(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(error="Access denied"))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_department_health("SALES")
        check = next(c for c in result["checks"] if c["area"] == "Compliance")

        assert check["status"] == "healthy"

    def test_aged_inventory_warning_above_5(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale(count=6))

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Aged Inventory")

        assert check["status"] == "warning"

    def test_aged_inventory_healthy_at_exactly_5(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "list_alerts_api", _fake_list_alerts_api(alerts=[]))
        monkeypatch.setattr(oo, "lifecycle_by_stage", _fake_lifecycle_by_stage({}))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale(count=5))

        result = oo.get_department_health("ADMIN")
        check = next(c for c in result["checks"] if c["area"] == "Aged Inventory")

        assert check["status"] == "healthy"


class TestGetWorkloadDistribution:

    def test_groups_employees_into_the_three_real_functional_areas(self, monkeypatch):
        _employee("EMP-1", department="Operations", title="Title & Registration Clerk")
        _employee("EMP-2", department="Operations", title="Lot Attendant")
        _employee("EMP-3", department="Service", title="Technician")
        _employee("EMP-4", department="Sales", title="Salesperson")

        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "inventory_lot_audit", _fake_lot_audit(0))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_workload_distribution("ADMIN")
        areas = {a["area"]: a for a in result["areas"]}

        assert areas["Title Processing"]["employee_ids"] == ["EMP-1"]
        assert areas["Lot / Inventory Operations"]["employee_ids"] == ["EMP-2"]
        assert areas["Recon / Vehicle Prep"]["employee_ids"] == ["EMP-3"]

    def test_title_match_is_case_insensitive(self, monkeypatch):
        _employee("EMP-1", department="Operations", title="TITLE Clerk")

        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "inventory_lot_audit", _fake_lot_audit(0))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_workload_distribution("ADMIN")
        areas = {a["area"]: a for a in result["areas"]}

        assert areas["Title Processing"]["headcount"] == 1

    def test_ratio_bucket_unstaffed_when_zero_headcount(self, monkeypatch):
        _vehicle("V1")

        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "inventory_lot_audit", _fake_lot_audit(0))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_workload_distribution("ADMIN")
        areas = {a["area"]: a for a in result["areas"]}

        assert areas["Title Processing"]["headcount"] == 0
        assert areas["Title Processing"]["open_task_count"] == 1
        assert areas["Title Processing"]["load"] == "unstaffed"

    def test_ratio_bucket_high_at_15_or_above(self, monkeypatch):
        _employee("EMP-1", department="Operations", title="Title Clerk")
        for i in range(15):
            _vehicle(f"V{i}")

        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "inventory_lot_audit", _fake_lot_audit(0))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_workload_distribution("ADMIN")
        areas = {a["area"]: a for a in result["areas"]}

        assert areas["Title Processing"]["load"] == "high"

    def test_ratio_bucket_moderate_between_5_and_15(self, monkeypatch):
        _employee("EMP-1", department="Operations", title="Title Clerk")
        for i in range(5):
            _vehicle(f"V{i}")

        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "inventory_lot_audit", _fake_lot_audit(0))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_workload_distribution("ADMIN")
        areas = {a["area"]: a for a in result["areas"]}

        assert areas["Title Processing"]["load"] == "moderate"

    def test_ratio_bucket_low_below_5(self, monkeypatch):
        _employee("EMP-1", department="Operations", title="Title Clerk")
        _vehicle("V1")

        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "inventory_lot_audit", _fake_lot_audit(0))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_workload_distribution("ADMIN")
        areas = {a["area"]: a for a in result["areas"]}

        assert areas["Title Processing"]["load"] == "low"

    def test_lot_task_count_sums_lot_audit_and_wholesale(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "inventory_lot_audit", _fake_lot_audit(sold_without_purchase_relationship=4))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale(count=3))

        result = oo.get_workload_distribution("ADMIN")
        areas = {a["area"]: a for a in result["areas"]}

        assert areas["Lot / Inventory Operations"]["open_task_count"] == 7

    def test_recon_area_reads_used_unsold_count_from_recon_queue(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(used_unsold_count=9))
        monkeypatch.setattr(oo, "inventory_lot_audit", _fake_lot_audit(0))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_workload_distribution("ADMIN")
        areas = {a["area"]: a for a in result["areas"]}

        assert areas["Recon / Vehicle Prep"]["open_task_count"] == 9

    def test_methodology_and_reassignment_notes_present(self, monkeypatch):
        monkeypatch.setattr(oo, "operations_recon_queue", _fake_recon(0))
        monkeypatch.setattr(oo, "inventory_lot_audit", _fake_lot_audit(0))
        monkeypatch.setattr(oo, "inventory_wholesale_disposition", _fake_wholesale())

        result = oo.get_workload_distribution("ADMIN")

        assert "HEURISTIC" in result["methodology_note"]
        assert "Universal Operations Work Queue" in result["reassignment_note"]


class TestGetOperationsOverview:

    def test_composes_all_three_sections(self, monkeypatch):
        monkeypatch.setattr(oo, "get_action_center", lambda role: {"a": 1})
        monkeypatch.setattr(oo, "get_department_health", lambda role: {"b": 2})
        monkeypatch.setattr(oo, "get_workload_distribution", lambda role: {"c": 3})

        result = oo.get_operations_overview("ADMIN")

        assert result == {
            "action_center": {"a": 1},
            "department_health": {"b": 2},
            "workload_distribution": {"c": 3},
        }
