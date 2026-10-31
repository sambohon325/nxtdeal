"""
Tests for core/entity_update_api.py -- the generic inline entity-attribute edit endpoint
added 2026-07-15 (Sam: "we need to be able to edit the information in the menu dashes
where it makes sense"), backing POST /entity/{entity_id}/update. This is the first
committed regression coverage for that module -- per BUILD_QUEUE.md's standing "convert
the loose test_*.py scripts to a real backend/tests/ pytest suite as each module gets
touched" rule (same rule sessions 46/48/49/71 followed). Run from backend/ with `pytest`.

The invariants locked in here are the ones the module's own docstring promises and that
the frontend (MenuDashPanel's EntityEditCard, DepartmentWorkflowButtons' LiveDataPanel)
relies on:
  * role gating reuses core/security.can_access_entity() verbatim -- editing never
    exceeds what viewing already allowed (a role that can't SEE an entity type can't
    edit one either);
  * `id` and `entity_type` are permanently protected and silently stripped from a patch,
    never overwritten;
  * a patch with no editable fields (empty, or only protected keys) is rejected;
  * a successful update merges the patch onto the entity's live attributes, returns the
    {id, entity_type, attributes} shape GET /entity/{id} and core/ai_tools.py already
    return, and audit-logs a real before/after diff via core/audit.py.

update_entity_api() calls save_graph(GRAPH_PATH) and save_audit_log(AUDIT_PATH); the
autouse fixture below stubs both in the module namespace so the suite never touches the
real graph.json / audit.json -- same precaution tests/test_intake.py documents for its
save_graph calls and tests/test_assets.py for save_audit_log.
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
from core.audit import audit_log
from core.entity_types import VEHICLE, FINANCE_CONTRACT
from core.permissions import ADMIN, SALES, MARKETING, FINANCE

from core import entity_update_api


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """Reset the graph ledger and the audit log before/after every test, and stub the two
    disk-write calls the module makes (save_graph / save_audit_log, both imported by name
    into the module namespace) so the real graph.json / audit.json are never touched.
    Mutate the singletons in place -- other modules hold direct references, same rule as
    test_intake.py."""

    ledger.reset()
    audit_log.reset()

    monkeypatch.setattr(entity_update_api, "save_graph", lambda filepath: None)
    monkeypatch.setattr(entity_update_api, "save_audit_log", lambda filepath: None)

    yield

    ledger.reset()
    audit_log.reset()


def _seed_vehicle():
    ledger.add_entity(
        Entity("VEH-90001", VEHICLE, {"Price": 1000, "Color": "Red"})
    )


def _seed_finance_contract():
    ledger.add_entity(
        Entity("FC-90001", FINANCE_CONTRACT, {"Amount": 5000})
    )


# --------------------------------------------------------------------------
# happy path
# --------------------------------------------------------------------------


def test_update_merges_patch_and_returns_entity_shape():

    _seed_vehicle()

    result = entity_update_api.update_entity_api(
        SALES, "EMP-00001", "VEH-90001", {"Price": 1500}
    )

    assert "error" not in result
    assert result["id"] == "VEH-90001"
    assert result["entity_type"] == VEHICLE
    # patched key changed, untouched key preserved
    assert result["attributes"]["Price"] == 1500
    assert result["attributes"]["Color"] == "Red"


def test_update_mutates_the_live_ledger_entity():

    _seed_vehicle()

    entity_update_api.update_entity_api(
        SALES, "EMP-00001", "VEH-90001", {"Color": "Blue"}
    )

    assert ledger.get_entity("VEH-90001").attributes["Color"] == "Blue"


def test_update_adds_unknown_key():
    """attributes is an open dict, matching how every importer treats it -- a key not
    already present is simply added, not rejected."""

    _seed_vehicle()

    result = entity_update_api.update_entity_api(
        ADMIN, "EMP-00001", "VEH-90001", {"StockNumber": "A-42"}
    )

    assert result["attributes"]["StockNumber"] == "A-42"


# --------------------------------------------------------------------------
# audit trail
# --------------------------------------------------------------------------


def test_update_records_before_after_audit_diff():

    _seed_vehicle()

    entity_update_api.update_entity_api(
        SALES, "EMP-00007", "VEH-90001", {"Price": 2000}
    )

    events = audit_log.get_all()
    assert len(events) == 1

    event = events[0]
    assert event.event_type == "entity_updated"
    assert event.entity_id == "VEH-90001"
    assert event.actor == "EMP-00007"
    assert event.details["before"] == {"Price": 1000}
    assert event.details["after"] == {"Price": 2000}


def test_failed_update_records_no_audit_event():
    """A rejected update (not found / forbidden / empty patch) must not leave an audit
    trail -- nothing changed."""

    _seed_finance_contract()

    entity_update_api.update_entity_api(
        SALES, "EMP-00001", "FC-90001", {"Amount": 1}
    )  # forbidden for SALES
    entity_update_api.update_entity_api(
        ADMIN, "EMP-00001", "DOES-NOT-EXIST", {"x": 1}
    )  # not found
    entity_update_api.update_entity_api(
        ADMIN, "EMP-00001", "FC-90001", {}
    )  # empty patch

    assert audit_log.get_all() == []


# --------------------------------------------------------------------------
# protected identity fields
# --------------------------------------------------------------------------


def test_protected_keys_are_stripped_not_applied():
    """`id` / `entity_type` in a patch are silently dropped; other keys still apply."""

    _seed_vehicle()

    result = entity_update_api.update_entity_api(
        ADMIN, "EMP-00001", "VEH-90001",
        {"id": "HACKED", "entity_type": "Spoofed", "Price": 1500},
    )

    assert result["id"] == "VEH-90001"
    assert result["entity_type"] == VEHICLE
    assert result["attributes"]["Price"] == 1500
    # identity fields never leaked into attributes
    assert ledger.get_entity("VEH-90001").id == "VEH-90001"
    assert ledger.get_entity("VEH-90001").entity_type == VEHICLE


def test_patch_of_only_protected_keys_is_rejected():

    _seed_vehicle()

    result = entity_update_api.update_entity_api(
        ADMIN, "EMP-00001", "VEH-90001", {"id": "x", "entity_type": "y"}
    )

    assert "error" in result
    # nothing changed
    assert ledger.get_entity("VEH-90001").id == "VEH-90001"


# --------------------------------------------------------------------------
# role gating (reuses can_access_entity)
# --------------------------------------------------------------------------


def test_role_without_entity_access_is_forbidden():
    """SALES cannot see FinanceContract (core/permissions.ENTITY_ACCESS), so it cannot
    edit one -- editing never exceeds viewing."""

    _seed_finance_contract()

    result = entity_update_api.update_entity_api(
        SALES, "EMP-00001", "FC-90001", {"Amount": 1}
    )

    assert "error" in result
    assert "Forbidden" in result["error"]
    # unchanged
    assert ledger.get_entity("FC-90001").attributes["Amount"] == 5000


def test_role_with_entity_access_can_edit():
    """FINANCE can access FinanceContract, so it can edit one."""

    _seed_finance_contract()

    result = entity_update_api.update_entity_api(
        FINANCE, "EMP-00001", "FC-90001", {"Amount": 6000}
    )

    assert "error" not in result
    assert result["attributes"]["Amount"] == 6000


def test_admin_can_edit_any_accessible_entity():

    _seed_vehicle()

    result = entity_update_api.update_entity_api(
        ADMIN, "EMP-00001", "VEH-90001", {"Color": "Green"}
    )

    assert result["attributes"]["Color"] == "Green"


def test_marketing_can_edit_vehicle_but_not_finance_contract():
    """Spot-check the gate genuinely follows ENTITY_ACCESS per entity type, not a blanket
    allow/deny: MARKETING is listed for Vehicle but not FinanceContract."""

    _seed_vehicle()
    _seed_finance_contract()

    ok = entity_update_api.update_entity_api(
        MARKETING, "EMP-00001", "VEH-90001", {"Color": "White"}
    )
    denied = entity_update_api.update_entity_api(
        MARKETING, "EMP-00001", "FC-90001", {"Amount": 1}
    )

    assert "error" not in ok
    assert "error" in denied


# --------------------------------------------------------------------------
# missing entity / bad patch shape
# --------------------------------------------------------------------------


def test_missing_entity_returns_not_found():

    result = entity_update_api.update_entity_api(
        ADMIN, "EMP-00001", "NO-SUCH-ID", {"x": 1}
    )

    assert result == {"error": "Entity not found"}


def test_empty_patch_is_rejected():

    _seed_vehicle()

    result = entity_update_api.update_entity_api(
        ADMIN, "EMP-00001", "VEH-90001", {}
    )

    assert "error" in result


def test_non_dict_patch_is_rejected():

    _seed_vehicle()

    result = entity_update_api.update_entity_api(
        ADMIN, "EMP-00001", "VEH-90001", ["not", "a", "dict"]
    )

    assert "error" in result

@pytest.mark.parametrize('kind,patch', [
    ('ApiKey', {'expires_at': '2099-01-01T00:00:00+00:00', 'active': True}),
    ('ApprovalRequest', {'status': 'approved', 'current_step_index': 99}),
    ('PermissionOverride', {'granted': True}),
])
def test_generic_editor_cannot_bypass_security_workflows(kind, patch):
    from copy import deepcopy
    entity = Entity('CONTROL-SYNTHETIC', kind, {'active': False, 'status': 'pending', 'granted': False})
    ledger.add_entity(entity)
    before = deepcopy(entity.attributes)
    result = entity_update_api.update_entity_api(ADMIN, 'EMP-ADMIN', entity.id, patch)
    assert 'error' in result
    assert entity.attributes == before
    assert audit_log.events == []
