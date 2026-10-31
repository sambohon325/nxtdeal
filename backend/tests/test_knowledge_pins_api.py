"""
Tests for core/knowledge_pins.py / core/knowledge_pins_api.py -- Shared Knowledge
(session 72): sharing a pinned reference with a department/role, "Everyone," or
keeping it private, plus the thin ACL layer wired into api/app.py.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import KNOWLEDGE_PIN
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

import core.knowledge_pins as knowledge_pins
from core.knowledge_pins import (
    SHARE_ROLES,
    VISIBILITY_ALL,
    VISIBILITY_ROLES,
    create_pin,
    list_pins_for_role,
    retag_pin,
    update_sharing,
    delete_pin,
)
from core.knowledge_pins_api import (
    share_roles_api,
    create_shared_pin_api,
    list_shared_pins_api,
    retag_shared_pin_api,
    share_shared_pin_api,
    delete_shared_pin_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(knowledge_pins, "save_graph", lambda filepath: None)


def _employee(employee_id="EMP-1", name="Ada Lovelace"):
    ledger.add_entity(Entity(id=employee_id, entity_type="Employee", attributes={"Name": name}))


def _pin(owner="EMP-1", visibility=VISIBILITY_ALL, roles=None, label="A Real Pin"):
    return create_pin(owner, "profile", "CUST-1", label, "General", visibility, roles)


# ---------------------------------------------------------------------------
# share_roles_api()
# ---------------------------------------------------------------------------

class TestShareRolesApi:

    def test_returns_the_real_fixed_share_roles_list(self):
        result = share_roles_api()
        assert result == {"roles": SHARE_ROLES}

    def test_covers_all_six_real_roles(self):
        result = share_roles_api()
        assert set(result["roles"]) == {ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE}


# ---------------------------------------------------------------------------
# create_pin() -- direct
# ---------------------------------------------------------------------------

class TestCreatePin:

    def test_unknown_visibility_rejected(self):
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", "everyone")
        assert "error" in result
        assert "Unknown visibility" in result["error"]

    def test_roles_visibility_with_no_roles_rejected(self):
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ROLES, roles=[])
        assert "error" in result
        assert "Pick at least one department" in result["error"]

    def test_roles_visibility_with_none_roles_rejected(self):
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ROLES, roles=None)
        assert "error" in result

    def test_roles_visibility_filters_out_invalid_role_values(self):
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ROLES,
                             roles=[SALES, "not-a-real-role"])
        assert result["roles"] == [SALES]

    def test_roles_visibility_with_only_invalid_values_rejected(self):
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ROLES,
                             roles=["not-a-real-role"])
        assert "error" in result

    def test_all_visibility_ignores_roles_param(self):
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ALL,
                             roles=[SALES, MARKETING])
        assert result["visibility"] == VISIBILITY_ALL
        assert result["roles"] == []

    def test_pin_id_has_real_prefix(self):
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ALL)
        assert result["id"].startswith("PIN")

    def test_entity_is_created_on_the_ledger(self):
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ALL)
        entity = ledger.get_entity(result["id"])
        assert entity is not None
        assert entity.entity_type == KNOWLEDGE_PIN
        assert entity.attributes["active"] is True

    def test_owner_and_kind_and_ref_id_and_label_and_tag_stored(self):
        result = create_pin("EMP-1", "dashboard", "some-ref", "My Label", "MyTag", VISIBILITY_ALL)
        assert result["owner_employee_id"] == "EMP-1"
        assert result["kind"] == "dashboard"
        assert result["ref_id"] == "some-ref"
        assert result["label"] == "My Label"
        assert result["tag"] == "MyTag"

    def test_owner_name_resolved_when_employee_exists(self):
        _employee("EMP-1", "Ada Lovelace")
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ALL)
        assert result["owner_name"] == "Ada Lovelace"

    def test_owner_name_none_when_employee_does_not_exist(self):
        result = create_pin("EMP-UNKNOWN", "profile", "CUST-1", "Label", "General", VISIBILITY_ALL)
        assert result["owner_name"] is None

    def test_shared_at_is_set(self):
        result = create_pin("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ALL)
        assert result["shared_at"] is not None


# ---------------------------------------------------------------------------
# list_pins_for_role()
# ---------------------------------------------------------------------------

class TestListPinsForRole:

    def test_all_visibility_pin_visible_to_everyone(self):
        _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = list_pins_for_role(SALES)
        assert len(result) == 1

    def test_roles_visibility_pin_visible_only_to_matching_role(self):
        _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])

        assert list_pins_for_role(SALES) == []
        assert len(list_pins_for_role(FINANCE)) == 1

    def test_admin_sees_every_active_pin_regardless_of_sharing(self):
        _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        _pin(owner="EMP-2", visibility=VISIBILITY_ROLES, roles=[SERVICE])

        result = list_pins_for_role(ADMIN)
        assert len(result) == 2

    def test_owner_always_sees_their_own_pin_via_employee_id(self):
        _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])

        # SALES role wouldn't normally see this, but the owner should never lose it.
        result = list_pins_for_role(SALES, employee_id="EMP-1")
        assert len(result) == 1

    def test_non_owner_without_matching_role_does_not_see_it(self):
        _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])

        result = list_pins_for_role(SALES, employee_id="EMP-2")
        assert result == []

    def test_inactive_pin_excluded_from_results(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        delete_pin(pin["id"], "EMP-1", SALES)

        result = list_pins_for_role(ADMIN)
        assert result == []

    def test_results_sorted_by_shared_at_descending(self):
        first = _pin(owner="EMP-1", visibility=VISIBILITY_ALL, label="First")
        second = _pin(owner="EMP-1", visibility=VISIBILITY_ALL, label="Second")

        result = list_pins_for_role(ADMIN)
        # most-recently-shared first
        assert result[0]["id"] == second["id"]
        assert result[1]["id"] == first["id"]

    def test_no_employee_id_still_only_shows_broadly_visible_pins(self):
        _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = list_pins_for_role(SALES, employee_id=None)
        assert result == []


# ---------------------------------------------------------------------------
# retag_pin()
# ---------------------------------------------------------------------------

class TestRetagPin:

    def test_unknown_pin_id_errors(self):
        result = retag_pin("PIN-DOES-NOT-EXIST", "EMP-1", ADMIN, "NewTag")
        assert "error" in result
        assert "not found" in result["error"]

    def test_wrong_entity_type_errors(self):
        ledger.add_entity(Entity(id="CUST-1", entity_type="Customer", attributes={}))
        result = retag_pin("CUST-1", "EMP-1", ADMIN, "NewTag")
        assert "error" in result

    def test_non_owner_non_admin_denied(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = retag_pin(pin["id"], "EMP-2", SALES, "NewTag")
        assert "error" in result
        assert "Only the person who shared this" in result["error"]

    def test_owner_can_retag(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = retag_pin(pin["id"], "EMP-1", SALES, "NewTag")
        assert result["tag"] == "NewTag"

    def test_admin_can_retag_someone_elses_pin(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = retag_pin(pin["id"], "EMP-999", ADMIN, "AdminTag")
        assert result["tag"] == "AdminTag"

    def test_tag_is_stripped(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = retag_pin(pin["id"], "EMP-1", SALES, "  Spaced  ")
        assert result["tag"] == "Spaced"

    def test_blank_tag_falls_back_to_general(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = retag_pin(pin["id"], "EMP-1", SALES, "   ")
        assert result["tag"] == "General"


# ---------------------------------------------------------------------------
# update_sharing()
# ---------------------------------------------------------------------------

class TestUpdateSharing:

    def test_unknown_pin_id_errors(self):
        result = update_sharing("PIN-NOPE", "EMP-1", ADMIN, add_roles=[SALES])
        assert "error" in result

    def test_non_owner_non_admin_denied(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = update_sharing(pin["id"], "EMP-2", SALES, add_roles=[SALES])
        assert "error" in result
        assert "Only the person who shared this" in result["error"]

    def test_set_all_widens_to_everyone(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = update_sharing(pin["id"], "EMP-1", SALES, set_all=True)
        assert result["visibility"] == VISIBILITY_ALL
        assert result["roles"] == []

    def test_add_roles_merges_into_existing_roles(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = update_sharing(pin["id"], "EMP-1", SALES, add_roles=[SERVICE])
        assert sorted(result["roles"]) == sorted([FINANCE, SERVICE])

    def test_add_roles_filters_out_invalid_role_values(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = update_sharing(pin["id"], "EMP-1", SALES, add_roles=["not-a-real-role"])
        assert result["roles"] == [FINANCE]

    def test_add_roles_sets_visibility_to_roles_when_not_already_all(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = update_sharing(pin["id"], "EMP-1", SALES, add_roles=[SERVICE])
        assert result["visibility"] == VISIBILITY_ROLES

    def test_add_roles_does_not_narrow_an_already_everyone_pin(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = update_sharing(pin["id"], "EMP-1", SALES, add_roles=[SERVICE])
        # widening-only: adding specific roles to an already-"everyone" pin must
        # never narrow it back down to just those roles.
        assert result["visibility"] == VISIBILITY_ALL

    def test_neither_set_all_nor_add_roles_leaves_sharing_unchanged(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = update_sharing(pin["id"], "EMP-1", SALES)
        assert result["visibility"] == VISIBILITY_ROLES
        assert result["roles"] == [FINANCE]

    def test_admin_can_widen_someone_elses_pin(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = update_sharing(pin["id"], "EMP-999", ADMIN, add_roles=[SERVICE])
        assert sorted(result["roles"]) == sorted([FINANCE, SERVICE])


# ---------------------------------------------------------------------------
# delete_pin()
# ---------------------------------------------------------------------------

class TestDeletePin:

    def test_unknown_pin_id_errors(self):
        result = delete_pin("PIN-NOPE", "EMP-1", ADMIN)
        assert "error" in result

    def test_non_owner_non_admin_denied(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = delete_pin(pin["id"], "EMP-2", SALES)
        assert "error" in result
        assert "Only the person who shared this" in result["error"]

    def test_owner_can_delete(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = delete_pin(pin["id"], "EMP-1", SALES)
        assert result == {"ok": True}

    def test_admin_can_delete_someone_elses_pin(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = delete_pin(pin["id"], "EMP-999", ADMIN)
        assert result == {"ok": True}

    def test_delete_is_a_soft_flag_not_a_hard_delete(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        delete_pin(pin["id"], "EMP-1", SALES)
        # still exists on the ledger, just no longer surfaced as active
        entity = ledger.get_entity(pin["id"])
        assert entity is not None
        assert entity.attributes["active"] is False

    def test_deleted_pin_no_longer_appears_in_list(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        delete_pin(pin["id"], "EMP-1", SALES)
        assert list_pins_for_role(ADMIN) == []


# ---------------------------------------------------------------------------
# ACL layer (core/knowledge_pins_api.py)
# ---------------------------------------------------------------------------

class TestCreateSharedPinApi:

    def test_empty_label_rejected(self):
        result = create_shared_pin_api("EMP-1", "profile", "CUST-1", "", "General", VISIBILITY_ALL)
        assert "error" in result
        assert "needs a label" in result["error"]

    def test_whitespace_only_label_rejected(self):
        result = create_shared_pin_api("EMP-1", "profile", "CUST-1", "   ", "General", VISIBILITY_ALL)
        assert "error" in result

    def test_none_label_rejected(self):
        result = create_shared_pin_api("EMP-1", "profile", "CUST-1", None, "General", VISIBILITY_ALL)
        assert "error" in result

    def test_label_is_stripped(self):
        result = create_shared_pin_api("EMP-1", "profile", "CUST-1", "  Padded Label  ", "General", VISIBILITY_ALL)
        assert result["label"] == "Padded Label"

    def test_tag_is_stripped(self):
        result = create_shared_pin_api("EMP-1", "profile", "CUST-1", "Label", "  Padded Tag  ", VISIBILITY_ALL)
        assert result["tag"] == "Padded Tag"

    def test_falsy_tag_defaults_to_general(self):
        result = create_shared_pin_api("EMP-1", "profile", "CUST-1", "Label", None, VISIBILITY_ALL)
        assert result["tag"] == "General"

    def test_empty_string_tag_defaults_to_general(self):
        result = create_shared_pin_api("EMP-1", "profile", "CUST-1", "Label", "", VISIBILITY_ALL)
        assert result["tag"] == "General"

    def test_delegates_correctly_to_create_pin(self):
        result = create_shared_pin_api("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ROLES,
                                        roles=[SALES])
        assert result["visibility"] == VISIBILITY_ROLES
        assert result["roles"] == [SALES]

    def test_still_propagates_a_real_validation_error_from_create_pin(self):
        result = create_shared_pin_api("EMP-1", "profile", "CUST-1", "Label", "General", VISIBILITY_ROLES,
                                        roles=[])
        assert "error" in result


class TestListSharedPinsApi:

    def test_wraps_result_in_pins_key(self):
        result = list_shared_pins_api(ADMIN, "EMP-1")
        assert result == {"pins": []}

    def test_matches_list_pins_for_role(self):
        _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = list_shared_pins_api(SALES, "EMP-2")
        assert len(result["pins"]) == 1


class TestRetagSharedPinApi:

    def test_delegates_to_retag_pin(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = retag_shared_pin_api(pin["id"], "EMP-1", SALES, "NewTag")
        assert result["tag"] == "NewTag"

    def test_denies_non_owner_non_admin(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = retag_shared_pin_api(pin["id"], "EMP-2", SALES, "NewTag")
        assert "error" in result


class TestShareSharedPinApi:

    def test_delegates_set_all(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = share_shared_pin_api(pin["id"], "EMP-1", SALES, set_all=True)
        assert result["visibility"] == VISIBILITY_ALL

    def test_delegates_add_roles(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = share_shared_pin_api(pin["id"], "EMP-1", SALES, add_roles=[SERVICE])
        assert sorted(result["roles"]) == sorted([FINANCE, SERVICE])

    def test_denies_non_owner_non_admin(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ROLES, roles=[FINANCE])
        result = share_shared_pin_api(pin["id"], "EMP-2", SALES, add_roles=[SERVICE])
        assert "error" in result


class TestDeleteSharedPinApi:

    def test_delegates_to_delete_pin(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = delete_shared_pin_api(pin["id"], "EMP-1", SALES)
        assert result == {"ok": True}

    def test_denies_non_owner_non_admin(self):
        pin = _pin(owner="EMP-1", visibility=VISIBILITY_ALL)
        result = delete_shared_pin_api(pin["id"], "EMP-2", SALES)
        assert "error" in result
