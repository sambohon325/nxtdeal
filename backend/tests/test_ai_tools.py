"""
Tests for core/ai_tools.py — the graph-traversal tools given to the AI assistant in the
Phase 11 wrap-up. The main thing worth testing here isn't the graph traversal itself
(core/queries.py already covers that indirectly elsewhere) but that every tool respects
core/security.py's can_access_entity() role check the same way GET /search and
GET /entity/{id} do — see core/ai_tools.py's module docstring for why that matters.
Run from backend/ with `pytest`.
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
from core.permissions import ADMIN, SALES, FINANCE, OPERATIONS, MARKETING
from core.entity_types import CUSTOMER, FINANCE_CONTRACT, VEHICLE, EMPLOYEE

from core.ai_tools import (
    search_entities,
    get_entity_by_id,
    get_related_entities,
    get_workflow_instance_status,
    list_workflow_instances,
    get_workflow_dashboard,
    get_stalled_workflow_instances,
    call_tool,
    TOOLS,
    DISPATCH,
)

from core import workflow_engine_v2 as wev2


@pytest.fixture(autouse=True)
def fresh_ledger():
    """Every test starts with an empty graph. Resets the existing DealerLedger instance
    in place — same reason as AuditLog.reset()/CredentialStore.reset() elsewhere in this
    suite: other modules already hold a direct reference to this singleton."""

    ledger.reset()

    yield

    ledger.reset()


def _seed():

    customer = Entity(
        id="CUS-00001",
        entity_type=CUSTOMER,
        attributes={"name": "Jane Smith"}
    )

    finance_contract = Entity(
        id="FIN-00001",
        entity_type=FINANCE_CONTRACT,
        attributes={"amount": 25000}
    )

    ledger.add_entity(customer)
    ledger.add_entity(finance_contract)

    ledger.add_relationship(
        Relationship(
            source_id="CUS-00001",
            target_id="FIN-00001",
            relationship_type="FINANCED_BY"
        )
    )

    return customer, finance_contract


def test_search_entities_returns_allowed_results():

    _seed()

    # CUSTOMER is allowed for every role in ENTITY_ACCESS, including SALES.
    results = search_entities(SALES, "Smith")

    assert len(results) == 1
    assert results[0]["id"] == "CUS-00001"


def test_search_entities_filters_disallowed_types():

    _seed()

    # FINANCE_CONTRACT is not in SALES's ENTITY_ACCESS list.
    results = search_entities(SALES, "25000")

    assert results == []

    # But FINANCE can see it.
    results = search_entities(FINANCE, "25000")

    assert len(results) == 1
    assert results[0]["id"] == "FIN-00001"


def test_get_entity_by_id_allowed():

    _seed()

    result = get_entity_by_id(SALES, "CUS-00001")

    assert result["id"] == "CUS-00001"
    assert "error" not in result


def test_get_entity_by_id_forbidden_for_disallowed_role():

    _seed()

    result = get_entity_by_id(SALES, "FIN-00001")

    assert result == {
        "error": "Forbidden: your role cannot access this entity type"
    }


def test_get_entity_by_id_not_found():

    _seed()

    result = get_entity_by_id(ADMIN, "DOES-NOT-EXIST")

    assert result == {"error": "Entity not found"}


def test_admin_bypasses_entity_type_restrictions():

    _seed()

    result = get_entity_by_id(ADMIN, "FIN-00001")

    assert result["id"] == "FIN-00001"
    assert "error" not in result


def test_get_related_entities_filters_by_role():

    _seed()

    # FINANCE can see the FINANCED_BY relationship to the finance contract.
    finance_view = get_related_entities(FINANCE, "CUS-00001")

    assert len(finance_view) == 1
    assert finance_view[0]["entity"]["id"] == "FIN-00001"
    assert finance_view[0]["relationship_type"] == "FINANCED_BY"

    # SALES sees the same relationship exist, but the finance contract itself is
    # filtered out since SALES can't access FINANCE_CONTRACT entities.
    sales_view = get_related_entities(SALES, "CUS-00001")

    assert sales_view == []


def test_call_tool_dispatches_by_name():

    _seed()

    result = call_tool(
        "get_entity_by_id",
        ADMIN,
        {"entity_id": "CUS-00001"}
    )

    assert result["id"] == "CUS-00001"


def test_call_tool_rejects_unknown_tool_name():

    result = call_tool("not_a_real_tool", ADMIN, {})

    assert "error" in result


# ---------------------------------------------------------------------------
# Operations Workflow v2 awareness tools -- these give the AI assistant real,
# read-only visibility into core/workflow_engine_v2.py's instances, matching
# Sam's "AI Workflow Awareness" spec (current/next step, blocked steps,
# pending approvals, missing info, suggested actions, dealership-wide
# dashboard counts, and SLA-stalled instances). Same call_tool()/role-first
# boundary as every other tool in this module -- no new ACL logic to test
# here (core/workflow_engine_v2_api.py's own test file already covers its
# _VIEW_ROLES/_MUTATE_ROLES split in depth); the thing worth confirming is
# that these are correctly wired end to end and read-only.
# ---------------------------------------------------------------------------

VEHICLE_INTAKE_KEY = "operations.vehicle_intake_v2"


def _seed_vehicle_intake_instance(started_by="EMP-00001"):
    ledger.add_entity(Entity(id=started_by, entity_type=EMPLOYEE, attributes={}))
    ledger.add_entity(Entity(id="VEH-00001", entity_type=VEHICLE, attributes={"Make": "Chevrolet"}))

    instance, error = wev2.start_workflow_instance_v2(
        workflow_key=VEHICLE_INTAKE_KEY,
        started_by=started_by,
        linked_entity_id="VEH-00001",
    )
    assert error is None
    return instance


def test_new_workflow_tools_registered_in_TOOLS_and_DISPATCH():

    tool_names = {t["function"]["name"] for t in TOOLS}

    for name in (
        "get_workflow_instance_status",
        "list_workflow_instances",
        "get_workflow_dashboard",
        "get_stalled_workflow_instances",
    ):
        assert name in tool_names
        assert name in DISPATCH
        assert DISPATCH[name].__name__ == name


def test_get_workflow_instance_status_returns_real_ai_state():

    instance = _seed_vehicle_intake_instance()

    result = get_workflow_instance_status(OPERATIONS, instance.id)

    assert "error" not in result
    assert result["current_step"]["key"] == "acquire"
    assert result["next_step"]["key"] == "inspect"
    assert result["blocked_steps"] == []
    assert result["required_approvals"] == []


def test_get_workflow_instance_status_forbidden_for_disallowed_role():

    instance = _seed_vehicle_intake_instance()

    # _VIEW_ROLES for workflow v2 is ADMIN/OPERATIONS/SALES/SERVICE/MARKETING/FINANCE --
    # every real role has view access, so use a bogus role to exercise the denial path.
    result = get_workflow_instance_status("NOT_A_REAL_ROLE", instance.id)

    assert result == {"error": "You don't have access to this Workflow"}


def test_get_workflow_instance_status_unknown_instance_errors():

    result = get_workflow_instance_status(ADMIN, "WF2-DOES-NOT-EXIST")

    assert "error" in result


def test_list_workflow_instances_returns_seeded_instance():

    instance = _seed_vehicle_intake_instance()

    result = list_workflow_instances(ADMIN)

    assert result["count"] == 1
    assert result["instances"][0]["id"] == instance.id


def test_list_workflow_instances_filters_by_status():

    _seed_vehicle_intake_instance()

    in_progress = list_workflow_instances(ADMIN, status="in_progress")
    assert in_progress["count"] == 1

    blocked = list_workflow_instances(ADMIN, status="blocked")
    assert blocked["count"] == 0


def test_list_workflow_instances_filters_by_workflow_key():

    _seed_vehicle_intake_instance()

    matching = list_workflow_instances(ADMIN, workflow_key=VEHICLE_INTAKE_KEY)
    assert matching["count"] == 1

    non_matching = list_workflow_instances(ADMIN, workflow_key="operations.recon_v2")
    assert non_matching["count"] == 0


def test_get_workflow_dashboard_reflects_real_counts():

    _seed_vehicle_intake_instance()

    result = get_workflow_dashboard(ADMIN)

    row = next(w for w in result["workflows"] if w["workflow_key"] == VEHICLE_INTAKE_KEY)
    assert row["active"] == 1
    assert row["total"] == 1
    assert row["completed"] == 0


def test_get_stalled_workflow_instances_empty_for_fresh_instance():

    _seed_vehicle_intake_instance()

    result = get_stalled_workflow_instances(ADMIN)

    # A just-started instance hasn't had time to breach any step's SLA yet.
    assert result["stalled"] == []


def test_call_tool_dispatches_new_workflow_tools():

    instance = _seed_vehicle_intake_instance()

    result = call_tool(
        "get_workflow_instance_status",
        MARKETING,
        {"instance_id": instance.id},
    )

    assert "error" not in result
    assert result["current_step"]["key"] == "acquire"
