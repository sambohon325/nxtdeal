"""
Tests for the department job-workflow engine (core/workflow_catalog.py,
core/workflow_tracking.py, core/workflow_tracking_api.py) -- session 53. Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger, registry, id_generator
from core.entities import Entity
from core.entity_types import VEHICLE, WORKFLOW_INSTANCE
from core.relationship_types import TRACKS
from core import workflow_catalog
from core import workflow_tracking
from core import workflow_tracking_api


@pytest.fixture(autouse=True)
def fresh_ledger():

    ledger.reset()
    registry.vehicle_vins.clear()
    registry.lead_ids.clear()
    registry.customer_ids.clear()
    registry.employee_ids.clear()
    registry.part_numbers.clear()

    for prefix in id_generator.counters:
        id_generator.counters[prefix] = 0

    yield

    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_disk_writes(monkeypatch):
    """workflow_tracking.py calls save_graph(GRAPH_PATH) directly on every mutation --
    stub it so tests never touch the real storage/graph.json, same precaution
    tests/test_intake.py documents for the other intake-style modules."""

    monkeypatch.setattr(workflow_tracking, "save_graph", lambda filepath: None)


def _add_vehicle(vin="1HGCM82633A004352"):

    ledger.add_entity(Entity(
        id="VEH-00001",
        entity_type=VEHICLE,
        attributes={"VIN": vin, "Make": "Honda", "Model": "Accord"},
    ))
    registry.vehicle_vins[vin] = "VEH-00001"
    return vin


# --------------------------------------------------------------------------
# catalog
# --------------------------------------------------------------------------


def test_catalog_has_nine_departments():

    assert set(workflow_catalog.get_catalog().keys()) == set(workflow_catalog.DEPARTMENTS)
    assert len(workflow_catalog.DEPARTMENTS) == 9


def test_catalog_has_expected_workflows_per_department():

    catalog = workflow_catalog.get_catalog()

    for department in workflow_catalog.DEPARTMENTS:
        assert len(catalog[department]) == (12 if department == "Sales" else 4), department


def test_catalog_has_forty_four_workflows_total_with_unique_keys():

    catalog = workflow_catalog.get_catalog()

    all_keys = [w["key"] for workflows in catalog.values() for w in workflows]

    assert len(all_keys) == 44
    assert len(set(all_keys)) == 44


def test_every_workflow_key_is_prefixed_with_its_own_department():

    catalog = workflow_catalog.get_catalog()

    for department, workflows in catalog.items():
        for workflow in workflows:
            assert workflow["key"].startswith(department.lower() + ".")


def test_every_workflow_has_at_least_three_stages():

    catalog = workflow_catalog.get_catalog()

    for workflows in catalog.values():
        for workflow in workflows:
            assert len(workflow["stages"]) >= 3, workflow["key"]


def test_get_workflow_def_finds_known_key():

    workflow = workflow_catalog.get_workflow_def("sales.desking")

    assert workflow is not None
    assert workflow["title"] == "Desking & Trade Evaluation"


def test_get_workflow_def_unknown_key_returns_none():

    assert workflow_catalog.get_workflow_def("not.a-real-key") is None


# --------------------------------------------------------------------------
# catalog: modal navigation (session 56 -- "tabs" + "core_functionality", sourced
# from Sam's second attached doc, "deparment dash modals.docx")
# --------------------------------------------------------------------------


def test_every_non_sales_workflow_has_current_tab_navigation():

    catalog = workflow_catalog.get_catalog()

    for department, workflows in catalog.items():
        if department == "Sales":
            continue
        for workflow in workflows:
            assert workflow.get("tabs"), workflow["key"]
            assert len(workflow["tabs"]) >= 3, workflow["key"]
            assert "core_functionality" not in workflow


def test_sales_workflows_have_current_tab_navigation():
    """Sales now uses the same five-tab navigation contract as other departments."""

    catalog = workflow_catalog.get_catalog()

    for workflow in catalog["Sales"]:
        assert len(workflow["tabs"]) == 5
        assert "core_functionality" not in workflow


# --------------------------------------------------------------------------
# workflow_tracking (engine)
# --------------------------------------------------------------------------


def test_start_workflow_instance_creates_entity_at_first_stage():

    instance, error = workflow_tracking.start_workflow_instance(
        "operations.recon", started_by="EMP-00001"
    )

    assert error is None
    assert instance.entity_type == WORKFLOW_INSTANCE
    assert instance.attributes["status"] == "in_progress"
    assert instance.attributes["current_stage_index"] == 0
    assert instance.attributes["department"] == "Operations"
    assert instance.attributes["title"] == "Vehicle Intake & Recon"
    assert len(instance.attributes["history"]) == 1
    assert instance.attributes["history"][0]["action"] == "started"


def test_start_workflow_instance_unknown_key_returns_error():

    instance, error = workflow_tracking.start_workflow_instance(
        "not.a-real-key", started_by="EMP-00001"
    )

    assert instance is None
    assert "no workflow definition" in error


def test_start_workflow_instance_resolves_linked_entity_by_vin_and_adds_tracks_relationship():

    vin = _add_vehicle()

    instance, error = workflow_tracking.start_workflow_instance(
        "operations.recon", started_by="EMP-00001", linked_entity_id=vin
    )

    assert error is None
    assert instance.attributes["linked_entity_id"] == "VEH-00001"
    assert instance.attributes["linked_entity_raw"] == vin

    relationships = ledger.get_entity_relationships(instance.id)
    tracks = [r for r in relationships if r.relationship_type == TRACKS]
    assert len(tracks) == 1
    assert tracks[0].target_id == "VEH-00001"


def test_start_workflow_instance_with_unresolvable_linked_entity_still_succeeds():

    instance, error = workflow_tracking.start_workflow_instance(
        "operations.recon", started_by="EMP-00001", linked_entity_id="not-a-real-id"
    )

    assert error is None
    assert instance.attributes["linked_entity_id"] is None
    assert instance.attributes["linked_entity_raw"] == "not-a-real-id"


def test_advance_workflow_instance_moves_to_next_stage():

    instance, _ = workflow_tracking.start_workflow_instance(
        "sales.lead_cadence", started_by="EMP-00001"
    )

    advanced, error = workflow_tracking.advance_workflow_instance(instance.id, actor="EMP-00001")

    assert error is None
    assert advanced.attributes["current_stage_index"] == 1
    assert advanced.attributes["status"] == "in_progress"
    assert advanced.attributes["history"][-1]["action"] == "advanced"


def test_advance_workflow_instance_on_last_stage_completes_it():

    instance, _ = workflow_tracking.start_workflow_instance(
        "readiness.data_maturity", started_by="EMP-00001"
    )
    stage_count = len(instance.attributes["stages"])

    for _ in range(stage_count - 1):
        instance, error = workflow_tracking.advance_workflow_instance(instance.id, actor="EMP-00001")
        assert error is None

    assert instance.attributes["status"] == "in_progress"

    completed, error = workflow_tracking.advance_workflow_instance(instance.id, actor="EMP-00001")

    assert error is None
    assert completed.attributes["status"] == "completed"
    assert completed.attributes["completed_at"] is not None
    assert completed.attributes["history"][-1]["action"] == "completed"


def test_advance_workflow_instance_already_completed_returns_error():

    instance, _ = workflow_tracking.start_workflow_instance(
        "readiness.data_maturity", started_by="EMP-00001"
    )
    for _ in range(len(instance.attributes["stages"])):
        instance, _ = workflow_tracking.advance_workflow_instance(instance.id, actor="EMP-00001")

    result, error = workflow_tracking.advance_workflow_instance(instance.id, actor="EMP-00001")

    assert result is None
    assert "already completed" in error


def test_advance_workflow_instance_unknown_id_returns_error():

    result, error = workflow_tracking.advance_workflow_instance("WF-99999", actor="EMP-00001")

    assert result is None
    assert "no workflow instance" in error


def test_cancel_workflow_instance_marks_cancelled():

    instance, _ = workflow_tracking.start_workflow_instance(
        "marketing.reputation", started_by="EMP-00001"
    )

    cancelled, error = workflow_tracking.cancel_workflow_instance(
        instance.id, actor="EMP-00001", notes="duplicate entry"
    )

    assert error is None
    assert cancelled.attributes["status"] == "cancelled"
    assert cancelled.attributes["history"][-1]["notes"] == "duplicate entry"


def test_cancel_workflow_instance_already_cancelled_returns_error():

    instance, _ = workflow_tracking.start_workflow_instance(
        "marketing.reputation", started_by="EMP-00001"
    )
    workflow_tracking.cancel_workflow_instance(instance.id, actor="EMP-00001")

    result, error = workflow_tracking.cancel_workflow_instance(instance.id, actor="EMP-00001")

    assert result is None
    assert "already cancelled" in error


def test_list_workflow_instances_filters_by_department_key_and_status():

    workflow_tracking.start_workflow_instance("sales.desking", started_by="EMP-00001")
    workflow_tracking.start_workflow_instance("sales.delivery", started_by="EMP-00001")
    finance_instance, _ = workflow_tracking.start_workflow_instance(
        "finance.compliance", started_by="EMP-00002"
    )
    workflow_tracking.cancel_workflow_instance(finance_instance.id, actor="EMP-00002")

    sales_instances = workflow_tracking.list_workflow_instances(department="Sales")
    assert len(sales_instances) == 2
    assert all(i.attributes["department"] == "Sales" for i in sales_instances)

    desking_only = workflow_tracking.list_workflow_instances(workflow_key="sales.desking")
    assert len(desking_only) == 1

    cancelled_only = workflow_tracking.list_workflow_instances(status="cancelled")
    assert len(cancelled_only) == 1
    assert cancelled_only[0].id == finance_instance.id


def test_list_workflow_instances_sorted_most_recently_updated_first():

    first, _ = workflow_tracking.start_workflow_instance("service.intake", started_by="EMP-00001")
    second, _ = workflow_tracking.start_workflow_instance("service.mpi", started_by="EMP-00001")
    workflow_tracking.advance_workflow_instance(first.id, actor="EMP-00001")

    instances = workflow_tracking.list_workflow_instances(department="Service")

    assert instances[0].id == first.id
    assert instances[1].id == second.id


# --------------------------------------------------------------------------
# workflow_tracking_api (thin layer)
# --------------------------------------------------------------------------


def test_get_workflow_catalog_api_matches_raw_catalog():

    assert workflow_tracking_api.get_workflow_catalog_api() == workflow_catalog.get_catalog()


def test_start_workflow_api_serializes_id_and_attributes():

    result = workflow_tracking_api.start_workflow_api("inventory.lot_audit", "EMP-00001")

    assert "error" not in result
    assert result["id"].startswith("WF-")
    assert result["workflow_key"] == "inventory.lot_audit"
    assert result["status"] == "in_progress"


def test_start_workflow_api_missing_employee_id_returns_error():

    result = workflow_tracking_api.start_workflow_api("inventory.lot_audit", None)

    assert "error" in result


def test_start_workflow_api_unknown_workflow_key_returns_error():

    result = workflow_tracking_api.start_workflow_api("not.a-real-key", "EMP-00001")

    assert "error" in result


def test_advance_and_cancel_workflow_api_round_trip():

    started = workflow_tracking_api.start_workflow_api("finance.floorplan_payoff", "EMP-00001")

    advanced = workflow_tracking_api.advance_workflow_api(started["id"], "EMP-00001")
    assert "error" not in advanced
    assert advanced["current_stage_index"] == 1

    cancelled = workflow_tracking_api.cancel_workflow_api(advanced["id"], "EMP-00001")
    assert "error" not in cancelled
    assert cancelled["status"] == "cancelled"


def test_list_workflow_instances_api_rejects_unknown_department():

    result = workflow_tracking_api.list_workflow_instances_api(department="Not A Department")

    assert "error" in result


def test_list_workflow_instances_api_returns_serialized_list():

    workflow_tracking_api.start_workflow_api("network.gap_analysis", "EMP-00001")

    result = workflow_tracking_api.list_workflow_instances_api(department="Network")

    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["department"] == "Network"
