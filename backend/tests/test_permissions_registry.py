"""Tests for core/permissions_registry.py -- the Administration Control
Center's "Roles & Permissions" module: granular per-employee permission
overrides layered on top of core/permissions.py's 6-role system, real
field-level security masking (Customer.CreditScore, CreditApplication.
ssn_last4), and a real 3-tier (staff/manager/executive) Approval Hierarchy.

Written 2026-07-20 as part of CAF-00123 (missing_test_coverage) closure --
this module previously had zero *dedicated* pytest coverage: test_governance.py
exercises create_approval_request/approve_step/reject_step/set_override only
as a downstream consumer of core/governance.py's own composed dashboard, not
as direct unit tests of this module's own functions and edge cases (unknown-
key/unknown-employee validation, override supersede-not-delete history,
field-security fast paths, tier-rank comparison rules, the requester-only
cancel gate, etc).

Note: this core module has NO role-based ACL of its own -- every mutating
function here (set_override/revoke_override/create_approval_request/
approve_step/reject_step/cancel_request) takes no `role` parameter at all.
Role gating for this feature, if any, lives at the api/app.py route layer,
outside this module's own scope -- confirmed by reading the real function
signatures directly rather than assumed. This file tests the real behavior
this module actually implements: permission-key/employee validation, the
supersede-not-delete override history mechanism, field-level masking, and
the tier-rank comparison approve_step()/reject_step()/list_approval_requests()
enforce via core/bot_tasks.py's real infer_tier().

Follows this codebase's established multi-target monkeypatch convention:
core/permissions_registry.py imports save_graph from core.storage and
save_audit_log from core.audit_storage at its own module level, so a stub
must patch THOSE bindings (permissions_registry.save_graph /
permissions_registry.save_audit_log), not core.storage.save_graph directly.
"""

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE
from core.audit import audit_log
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

import core.permissions_registry as permissions_registry

from core.permissions_registry import (
    PERMISSION_CATALOG,
    ALL_ROLES,
    FIELD_SECURITY,
    APPROVAL_CHAINS,
    list_permission_catalog,
    has_permission,
    get_effective_permissions,
    list_overrides_for_employee,
    list_all_overrides,
    set_override,
    revoke_override,
    can_see_field,
    filter_sensitive_fields,
    list_approval_chains,
    create_approval_request,
    approve_step,
    reject_step,
    cancel_request,
    get_approval_request,
    list_approval_requests,
    get_tier_distribution,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield

@pytest.fixture(autouse=True)
def fresh_audit_log():
    audit_log.reset()
    yield

@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(permissions_registry, "save_graph", lambda filepath: None)
    monkeypatch.setattr(permissions_registry, "save_audit_log", lambda filepath: None)


def make_employee(employee_id, title, first="Test", last="Employee", department="Sales"):
    entity = Entity(
        id=employee_id,
        entity_type=EMPLOYEE,
        attributes={
            "Title": title,
            "FirstName": first,
            "LastName": last,
            "Department": department,
        },
    )
    ledger.add_entity(entity)
    return entity


@pytest.fixture
def staff_employee():
    return make_employee("EMP-STAFF1", "Sales Associate")


@pytest.fixture
def manager_employee():
    return make_employee("EMP-MGR1", "Sales Manager")


@pytest.fixture
def executive_employee():
    return make_employee("EMP-EXEC1", "General Manager")


def _single_manager_step_chain_key():
    """The one real chain whose first (and only) step is manager-tier -- used
    to exercise the straightforward single-step approval path without
    hardcoding a specific catalog key that might shift."""
    for key, chain in APPROVAL_CHAINS.items():
        if chain["steps"] == ["manager"]:
            return key
    raise AssertionError("expected at least one single-step manager-tier chain in APPROVAL_CHAINS")


def _multi_step_chain_key():
    for key, chain in APPROVAL_CHAINS.items():
        if len(chain["steps"]) >= 2:
            return key
    raise AssertionError("expected at least one multi-step chain in APPROVAL_CHAINS")


# ---------------------------------------------------------------------------
# list_permission_catalog
# ---------------------------------------------------------------------------

class TestListPermissionCatalog:
    def test_returns_categories_and_roles(self):
        result = list_permission_catalog()
        assert "categories" in result
        assert "roles" in result
        assert result["roles"] == list(ALL_ROLES)

    def test_every_category_maps_to_its_real_catalog_entries(self):
        result = list_permission_catalog()
        by_category = {c["category"]: c["permissions"] for c in result["categories"]}
        for category, entries in PERMISSION_CATALOG.items():
            assert by_category[category] == entries

    def test_every_permission_entry_has_the_required_shape(self):
        for entries in PERMISSION_CATALOG.values():
            for entry in entries:
                assert "key" in entry
                assert "label" in entry
                assert "roles" in entry
                assert isinstance(entry["roles"], list)

    def test_every_permission_key_is_globally_unique(self):
        keys = []
        for entries in PERMISSION_CATALOG.values():
            keys.extend(e["key"] for e in entries)
        assert len(keys) == len(set(keys))

    def test_every_role_in_the_catalog_is_a_recognized_role(self):
        for entries in PERMISSION_CATALOG.values():
            for entry in entries:
                for role in entry["roles"]:
                    assert role in ALL_ROLES


# ---------------------------------------------------------------------------
# has_permission
# ---------------------------------------------------------------------------

class TestHasPermission:
    def test_unknown_permission_key_fails_closed(self):
        assert has_permission(SALES, "EMP-00001", "not_a_real_permission") is False

    def test_role_default_allow_with_no_override(self):
        assert has_permission(SALES, "EMP-00001", "deals.view_board") is True

    def test_role_default_deny_with_no_override(self):
        assert has_permission(MARKETING, "EMP-00001", "deals.view_board") is False

    def test_no_employee_id_still_falls_back_to_role_default(self):
        assert has_permission(SALES, None, "deals.view_board") is True
        assert has_permission(MARKETING, None, "deals.view_board") is False

    def test_active_override_grants_beyond_role_default(self, staff_employee):
        assert has_permission(MARKETING, staff_employee.id, "deals.view_board") is False
        set_override(staff_employee.id, "deals.view_board", True, ADMIN, "test grant")
        assert has_permission(MARKETING, staff_employee.id, "deals.view_board") is True

    def test_active_override_denies_beyond_role_default(self, staff_employee):
        assert has_permission(SALES, staff_employee.id, "deals.view_board") is True
        set_override(staff_employee.id, "deals.view_board", False, ADMIN, "test revoke")
        assert has_permission(SALES, staff_employee.id, "deals.view_board") is False

    def test_override_is_per_employee_not_global(self, staff_employee):
        other_employee = "EMP-OTHER1"
        set_override(staff_employee.id, "deals.view_board", True, ADMIN, "grant")
        assert has_permission(MARKETING, staff_employee.id, "deals.view_board") is True
        assert has_permission(MARKETING, other_employee, "deals.view_board") is False

    def test_revoked_override_falls_back_to_role_default(self, staff_employee):
        set_override(staff_employee.id, "deals.view_board", True, ADMIN, "grant")
        assert has_permission(MARKETING, staff_employee.id, "deals.view_board") is True
        overrides = list_overrides_for_employee(staff_employee.id)
        override_id = overrides[0]["id"]
        revoke_override(override_id, ADMIN)
        assert has_permission(MARKETING, staff_employee.id, "deals.view_board") is False


# ---------------------------------------------------------------------------
# get_effective_permissions
# ---------------------------------------------------------------------------

class TestGetEffectivePermissions:
    def test_returns_an_entry_for_every_catalog_permission(self):
        result = get_effective_permissions(SALES, "EMP-00001")
        total_catalog_keys = sum(len(entries) for entries in PERMISSION_CATALOG.values())
        assert len(result) == total_catalog_keys

    def test_each_entry_reflects_role_default_and_no_override(self):
        result = get_effective_permissions(SALES, "EMP-00001")
        entry = next(e for e in result if e["key"] == "deals.view_board")
        assert entry["role_default"] is True
        assert entry["effective"] is True
        assert entry["overridden"] is False

    def test_overridden_flag_is_true_once_a_grant_exists(self, staff_employee):
        set_override(staff_employee.id, "deals.view_board", True, ADMIN, "grant")
        result = get_effective_permissions(MARKETING, staff_employee.id)
        entry = next(e for e in result if e["key"] == "deals.view_board")
        assert entry["role_default"] is False
        assert entry["effective"] is True
        assert entry["overridden"] is True

    def test_denied_by_default_without_an_override_stays_not_overridden(self):
        result = get_effective_permissions(MARKETING, "EMP-00001")
        entry = next(e for e in result if e["key"] == "deals.view_board")
        assert entry["effective"] is False
        assert entry["overridden"] is False


# ---------------------------------------------------------------------------
# set_override
# ---------------------------------------------------------------------------

class TestSetOverride:
    def test_unknown_permission_key_returns_an_error(self, staff_employee):
        result = set_override(staff_employee.id, "not_a_real_key", True, ADMIN)
        assert "error" in result

    def test_unknown_employee_returns_an_error(self):
        result = set_override("EMP-DOES-NOT-EXIST", "deals.view_board", True, ADMIN)
        assert "error" in result

    def test_successful_grant_returns_the_expected_shape(self, staff_employee):
        result = set_override(staff_employee.id, "deals.view_board", False, ADMIN, "revoke test")
        assert "error" not in result
        assert result["employee_id"] == staff_employee.id
        assert result["permission_key"] == "deals.view_board"
        assert result["granted"] is False
        assert result["active"] is True
        assert result["reason"] == "revoke test"
        assert result["granted_by"] == ADMIN

    def test_a_second_override_for_the_same_pair_supersedes_not_deletes_the_first(self, staff_employee):
        first = set_override(staff_employee.id, "deals.view_board", True, ADMIN, "first")
        second = set_override(staff_employee.id, "deals.view_board", False, ADMIN, "second")
        overrides = list_overrides_for_employee(staff_employee.id)
        assert len(overrides) == 2
        first_record = next(o for o in overrides if o["id"] == first["id"])
        second_record = next(o for o in overrides if o["id"] == second["id"])
        assert first_record["active"] is False
        assert first_record["superseded_at"] is not None
        assert second_record["active"] is True

    def test_writes_a_real_audit_log_event(self, staff_employee):
        set_override(staff_employee.id, "deals.view_board", True, ADMIN, "audit check")
        events = [e for e in audit_log.events if e.event_type == "permission_override_set"]
        assert len(events) == 1
        assert events[0].actor == ADMIN
        assert events[0].details["permission_key"] == "deals.view_board"
        assert events[0].details["granted"] is True

    def test_field_security_synthetic_key_can_also_be_overridden(self, staff_employee):
        field_key = "field:Customer.CreditScore"
        result = set_override(staff_employee.id, field_key, True, ADMIN, "reveal credit score")
        assert "error" not in result
        assert result["permission_key"] == field_key


# ---------------------------------------------------------------------------
# revoke_override
# ---------------------------------------------------------------------------

class TestRevokeOverride:
    def test_not_found_returns_an_error(self):
        result = revoke_override("PERM-DOES-NOT-EXIST", ADMIN)
        assert "error" in result

    def test_already_inactive_returns_an_error(self, staff_employee):
        override = set_override(staff_employee.id, "deals.view_board", True, ADMIN, "grant")
        revoke_override(override["id"], ADMIN)
        result = revoke_override(override["id"], ADMIN)
        assert "error" in result

    def test_successful_revoke_reverts_to_role_default(self, staff_employee):
        override = set_override(staff_employee.id, "deals.view_board", True, ADMIN, "grant")
        assert has_permission(MARKETING, staff_employee.id, "deals.view_board") is True
        result = revoke_override(override["id"], ADMIN)
        assert "error" not in result
        assert result["active"] is False
        assert has_permission(MARKETING, staff_employee.id, "deals.view_board") is False

    def test_writes_a_real_audit_log_event(self, staff_employee):
        override = set_override(staff_employee.id, "deals.view_board", True, ADMIN, "grant")
        revoke_override(override["id"], ADMIN)
        events = [e for e in audit_log.events if e.event_type == "permission_override_revoked"]
        assert len(events) == 1
        assert events[0].actor == ADMIN


# ---------------------------------------------------------------------------
# list_overrides_for_employee / list_all_overrides
# ---------------------------------------------------------------------------

class TestListOverrides:
    def test_list_for_employee_includes_active_and_inactive(self, staff_employee):
        first = set_override(staff_employee.id, "deals.view_board", True, ADMIN, "first")
        set_override(staff_employee.id, "deals.view_board", False, ADMIN, "second")
        overrides = list_overrides_for_employee(staff_employee.id)
        assert len(overrides) == 2
        statuses = {o["id"]: o["active"] for o in overrides}
        assert statuses[first["id"]] is False

    def test_list_for_employee_only_returns_that_employees_own_overrides(self, staff_employee):
        other_id = "EMP-OTHER2"
        make_employee(other_id, "Sales Associate")
        set_override(staff_employee.id, "deals.view_board", True, ADMIN, "a")
        set_override(other_id, "deals.view_board", True, ADMIN, "b")
        result = list_overrides_for_employee(staff_employee.id)
        assert all(o["employee_id"] == staff_employee.id for o in result)
        assert len(result) == 1

    def test_list_for_employee_with_no_overrides_is_empty(self):
        assert list_overrides_for_employee("EMP-NEVER-OVERRIDDEN") == []

    def test_list_all_overrides_spans_every_employee(self, staff_employee):
        other_id = "EMP-OTHER3"
        make_employee(other_id, "Sales Associate")
        set_override(staff_employee.id, "deals.view_board", True, ADMIN, "a")
        set_override(other_id, "deals.view_board", True, ADMIN, "b")
        result = list_all_overrides()
        assert len(result) == 2
        employee_ids = {o["employee_id"] for o in result}
        assert employee_ids == {staff_employee.id, other_id}


# ---------------------------------------------------------------------------
# Field-level security -- can_see_field / filter_sensitive_fields
# ---------------------------------------------------------------------------

class TestCanSeeField:
    def test_ungated_field_is_always_visible_regardless_of_role(self):
        assert can_see_field(MARKETING, None, "Customer", "FirstName") is True

    def test_gated_field_visible_to_a_default_allowed_role(self):
        assert can_see_field(FINANCE, None, "Customer", "CreditScore") is True

    def test_gated_field_hidden_from_a_role_not_on_the_default_list(self):
        assert can_see_field(SALES, None, "Customer", "CreditScore") is False

    def test_none_employee_id_skips_the_override_check_entirely(self, staff_employee):
        set_override(staff_employee.id, "deals.view_board", True, ADMIN, "unrelated")
        assert can_see_field(SALES, None, "Customer", "CreditScore") is False

    def test_field_override_grants_visibility_beyond_role_default(self, staff_employee):
        assert can_see_field(SALES, staff_employee.id, "Customer", "CreditScore") is False
        set_override(staff_employee.id, "field:Customer.CreditScore", True, ADMIN, "reveal")
        assert can_see_field(SALES, staff_employee.id, "Customer", "CreditScore") is True

    def test_field_override_denies_visibility_below_role_default(self, staff_employee):
        assert can_see_field(FINANCE, staff_employee.id, "Customer", "CreditScore") is True
        set_override(staff_employee.id, "field:Customer.CreditScore", False, ADMIN, "hide")
        assert can_see_field(FINANCE, staff_employee.id, "Customer", "CreditScore") is False

    def test_unknown_entity_type_is_always_visible(self):
        assert can_see_field(MARKETING, None, "NotARealEntityType", "AnyField") is True

    def test_unknown_field_on_a_known_entity_type_is_always_visible(self):
        assert can_see_field(SALES, None, "Customer", "SomeUnratedField") is True


class TestFilterSensitiveFields:
    def test_unguarded_entity_type_returns_the_same_object_unchanged(self):
        attrs = {"FirstName": "Jane", "LastName": "Doe"}
        result = filter_sensitive_fields(MARKETING, None, "Vehicle", attrs)
        assert result is attrs

    def test_falsy_attributes_returns_the_same_falsy_value(self):
        assert filter_sensitive_fields(MARKETING, None, "Customer", {}) == {}
        assert filter_sensitive_fields(MARKETING, None, "Customer", None) is None

    def test_gated_field_is_redacted_for_a_role_without_access(self):
        attrs = {"FirstName": "Jane", "CreditScore": "720"}
        result = filter_sensitive_fields(SALES, None, "Customer", attrs)
        assert result["FirstName"] == "Jane"
        assert result["CreditScore"] != "720"

    def test_gated_field_is_untouched_for_a_role_with_access(self):
        attrs = {"FirstName": "Jane", "CreditScore": "720"}
        result = filter_sensitive_fields(FINANCE, None, "Customer", attrs)
        assert result["CreditScore"] == "720"

    def test_gated_field_absent_from_attributes_stays_absent(self):
        attrs = {"FirstName": "Jane"}
        result = filter_sensitive_fields(SALES, None, "Customer", attrs)
        assert "CreditScore" not in result

    def test_original_attributes_dict_is_not_mutated(self):
        attrs = {"FirstName": "Jane", "CreditScore": "720"}
        filter_sensitive_fields(SALES, None, "Customer", attrs)
        assert attrs["CreditScore"] == "720"

    def test_field_override_unlocks_a_redacted_field_end_to_end(self, staff_employee):
        attrs = {"FirstName": "Jane", "CreditScore": "720"}
        redacted = filter_sensitive_fields(SALES, staff_employee.id, "Customer", attrs)
        assert redacted["CreditScore"] != "720"
        set_override(staff_employee.id, "field:Customer.CreditScore", True, ADMIN, "reveal")
        revealed = filter_sensitive_fields(SALES, staff_employee.id, "Customer", attrs)
        assert revealed["CreditScore"] == "720"

    def test_credit_application_ssn_last4_is_also_gated(self):
        attrs = {"employer_name": "Acme Co", "ssn_last4": "1234"}
        result = filter_sensitive_fields(SALES, None, "CreditApplication", attrs)
        assert result["employer_name"] == "Acme Co"
        assert result["ssn_last4"] != "1234"


# ---------------------------------------------------------------------------
# list_approval_chains
# ---------------------------------------------------------------------------

class TestListApprovalChains:
    def test_returns_one_entry_per_chain_with_its_key(self):
        result = list_approval_chains()
        assert len(result) == len(APPROVAL_CHAINS)
        keys = {r["key"] for r in result}
        assert keys == set(APPROVAL_CHAINS.keys())

    def test_every_chain_has_at_least_one_step(self):
        for chain_key, chain in APPROVAL_CHAINS.items():
            assert isinstance(chain_key, str) and chain_key
            assert isinstance(chain["steps"], list)
            assert len(chain["steps"]) >= 1

    def test_every_step_is_a_recognized_tier(self):
        recognized = {"staff", "manager", "executive"}
        for chain in APPROVAL_CHAINS.values():
            for step in chain["steps"]:
                assert step in recognized


# ---------------------------------------------------------------------------
# create_approval_request
# ---------------------------------------------------------------------------

class TestCreateApprovalRequest:
    def test_unknown_chain_key_returns_an_error(self, staff_employee):
        result = create_approval_request("not_a_real_chain", staff_employee.id, "a request")
        assert "error" in result

    def test_unknown_requester_returns_an_error(self):
        chain_key = _single_manager_step_chain_key()
        result = create_approval_request(chain_key, "EMP-DOES-NOT-EXIST", "a request")
        assert "error" in result

    def test_successful_create_has_pending_status_and_step_zero(self, staff_employee):
        chain_key = _single_manager_step_chain_key()
        result = create_approval_request(chain_key, staff_employee.id, "a request")
        assert "error" not in result
        assert result["status"] == "pending"
        assert result["current_step_index"] == 0
        assert result["requested_by"] == staff_employee.id
        assert isinstance(result["history"], list)
        assert len(result["history"]) == 1
        assert result["history"][0]["action"] == "requested"

    def test_writes_a_real_audit_log_event(self, staff_employee):
        chain_key = _single_manager_step_chain_key()
        create_approval_request(chain_key, staff_employee.id, "a request")
        events = [e for e in audit_log.events if e.event_type == "approval_request_created"]
        assert len(events) == 1
        assert events[0].actor == staff_employee.id


# ---------------------------------------------------------------------------
# approve_step
# ---------------------------------------------------------------------------

class TestApproveStep:
    def test_not_found_returns_an_error(self, manager_employee):
        result = approve_step("REQ-DOES-NOT-EXIST", manager_employee.id)
        assert "error" in result

    def test_non_pending_status_returns_an_error(self, staff_employee, manager_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        approve_step(req["id"], manager_employee.id)  # clears it -> approved
        result = approve_step(req["id"], manager_employee.id, "too late")
        assert "error" in result

    def test_unknown_approver_returns_an_error(self, staff_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = approve_step(req["id"], "EMP-DOES-NOT-EXIST")
        assert "error" in result

    def test_insufficient_tier_returns_an_error(self, staff_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = approve_step(req["id"], staff_employee.id, "too junior")
        assert "error" in result

    def test_a_tier_higher_than_required_still_passes(self, staff_employee, executive_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = approve_step(req["id"], executive_employee.id, "exec covering a manager step")
        assert "error" not in result
        assert result["status"] == "approved"

    def test_multi_step_chain_stays_pending_until_the_final_step(self, staff_employee, manager_employee):
        chain_key = _multi_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = approve_step(req["id"], manager_employee.id, "step 1")
        assert "error" not in result
        assert result["status"] == "pending"
        assert result["current_step_index"] == 1

    def test_multi_step_chain_requires_the_right_tier_at_each_step(
        self, staff_employee, manager_employee, executive_employee
    ):
        chain_key = _multi_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        approve_step(req["id"], manager_employee.id, "step 1: manager clears it")

        # step 2 requires executive tier -- a manager retrying should fail.
        blocked = approve_step(req["id"], manager_employee.id, "manager tries step 2")
        assert "error" in blocked

        final = approve_step(req["id"], executive_employee.id, "step 2: exec clears it")
        assert "error" not in final
        assert final["status"] == "approved"

    def test_final_step_flips_status_to_approved_and_appends_history(
        self, staff_employee, executive_employee
    ):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = approve_step(req["id"], executive_employee.id, "clearing")
        assert result["status"] == "approved"
        actions = [h["action"] for h in result["history"]]
        assert "approved_step" in actions
        assert "fully_approved" in actions

    def test_writes_a_real_audit_log_event(self, staff_employee, executive_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        approve_step(req["id"], executive_employee.id, "clearing")
        events = [e for e in audit_log.events if e.event_type == "approval_step_approved"]
        assert len(events) == 1
        assert events[0].actor == executive_employee.id


# ---------------------------------------------------------------------------
# reject_step
# ---------------------------------------------------------------------------

class TestRejectStep:
    def test_not_found_returns_an_error(self, manager_employee):
        result = reject_step("REQ-DOES-NOT-EXIST", manager_employee.id, "reason")
        assert "error" in result

    def test_empty_reason_returns_an_error(self, staff_employee, manager_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = reject_step(req["id"], manager_employee.id, "")
        assert "error" in result

    def test_whitespace_only_reason_returns_an_error(self, staff_employee, manager_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = reject_step(req["id"], manager_employee.id, "   ")
        assert "error" in result

    def test_successful_reject_sets_terminal_rejected_status(self, staff_employee, manager_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = reject_step(req["id"], manager_employee.id, "not approved, budget concerns")
        assert "error" not in result
        assert result["status"] == "rejected"

    def test_non_pending_status_returns_an_error(self, staff_employee, manager_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        reject_step(req["id"], manager_employee.id, "first rejection")
        result = reject_step(req["id"], manager_employee.id, "second attempt")
        assert "error" in result

    def test_writes_a_real_audit_log_event(self, staff_employee, manager_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        reject_step(req["id"], manager_employee.id, "declined")
        events = [e for e in audit_log.events if e.event_type == "approval_request_rejected"]
        assert len(events) == 1
        assert events[0].actor == manager_employee.id


# ---------------------------------------------------------------------------
# cancel_request
# ---------------------------------------------------------------------------

class TestCancelRequest:
    def test_not_found_returns_an_error(self, staff_employee):
        result = cancel_request("REQ-DOES-NOT-EXIST", staff_employee.id)
        assert "error" in result

    def test_wrong_requester_is_denied(self, staff_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = cancel_request(req["id"], "EMP-SOMEONE-ELSE")
        assert "error" in result

    def test_original_requester_can_cancel_a_pending_request(self, staff_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        result = cancel_request(req["id"], staff_employee.id)
        assert "error" not in result
        assert result["status"] == "cancelled"

    def test_non_pending_request_cannot_be_cancelled(self, staff_employee, manager_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        reject_step(req["id"], manager_employee.id, "already rejected")
        result = cancel_request(req["id"], staff_employee.id)
        assert "error" in result


# ---------------------------------------------------------------------------
# get_approval_request
# ---------------------------------------------------------------------------

class TestGetApprovalRequest:
    def test_not_found_returns_an_error_dict(self):
        result = get_approval_request("REQ-DOES-NOT-EXIST")
        assert "error" in result

    def test_returns_the_real_request(self, staff_employee):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        fetched = get_approval_request(req["id"])
        assert fetched["id"] == req["id"]
        assert fetched["status"] == "pending"


# ---------------------------------------------------------------------------
# list_approval_requests
# ---------------------------------------------------------------------------

class TestListApprovalRequests:
    def test_filters_by_status(self, staff_employee, manager_employee):
        chain_key = _single_manager_step_chain_key()
        pending_req = create_approval_request(chain_key, staff_employee.id, "pending one")
        rejected_req = create_approval_request(chain_key, staff_employee.id, "rejected one")
        reject_step(rejected_req["id"], manager_employee.id, "declined")

        pending_only = list_approval_requests(status="pending")
        assert any(r["id"] == pending_req["id"] for r in pending_only)
        assert not any(r["id"] == rejected_req["id"] for r in pending_only)

        rejected_only = list_approval_requests(status="rejected")
        assert any(r["id"] == rejected_req["id"] for r in rejected_only)
        assert not any(r["id"] == pending_req["id"] for r in rejected_only)

    def test_filters_by_requested_by(self, staff_employee):
        other_id = "EMP-OTHER-REQUESTER"
        make_employee(other_id, "Sales Associate")
        chain_key = _single_manager_step_chain_key()
        mine = create_approval_request(chain_key, staff_employee.id, "mine")
        theirs = create_approval_request(chain_key, other_id, "theirs")

        result = list_approval_requests(requested_by=staff_employee.id)
        assert any(r["id"] == mine["id"] for r in result)
        assert not any(r["id"] == theirs["id"] for r in result)

    def test_pending_for_employee_only_includes_requests_that_employees_tier_can_act_on(
        self, staff_employee, manager_employee
    ):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "needs a manager")

        pending_for_manager = list_approval_requests(pending_for_employee=manager_employee.id)
        assert any(r["id"] == req["id"] for r in pending_for_manager)

        pending_for_staff = list_approval_requests(pending_for_employee=staff_employee.id)
        assert not any(r["id"] == req["id"] for r in pending_for_staff)

    def test_pending_for_employee_excludes_already_decided_requests(
        self, staff_employee, manager_employee
    ):
        chain_key = _single_manager_step_chain_key()
        req = create_approval_request(chain_key, staff_employee.id, "note")
        approve_step(req["id"], manager_employee.id, "cleared")
        pending_for_manager = list_approval_requests(pending_for_employee=manager_employee.id)
        assert not any(r["id"] == req["id"] for r in pending_for_manager)

    def test_with_no_filters_returns_every_request(self, staff_employee):
        chain_key = _single_manager_step_chain_key()
        create_approval_request(chain_key, staff_employee.id, "one")
        create_approval_request(chain_key, staff_employee.id, "two")
        result = list_approval_requests()
        assert len(result) == 2

    def test_results_include_every_created_request(self, staff_employee):
        chain_key = _single_manager_step_chain_key()
        first = create_approval_request(chain_key, staff_employee.id, "first")
        second = create_approval_request(chain_key, staff_employee.id, "second")
        result = list_approval_requests()
        ids = {r["id"] for r in result}
        assert ids == {first["id"], second["id"]}


# ---------------------------------------------------------------------------
# get_tier_distribution
# ---------------------------------------------------------------------------

class TestGetTierDistribution:
    def test_buckets_employees_by_inferred_tier(self, staff_employee, manager_employee, executive_employee):
        result = get_tier_distribution()
        assert "staff" in result
        assert "manager" in result
        assert "executive" in result

        staff_ids = {e["id"] for e in result["staff"]["employees"]}
        manager_ids = {e["id"] for e in result["manager"]["employees"]}
        executive_ids = {e["id"] for e in result["executive"]["employees"]}

        assert staff_employee.id in staff_ids
        assert manager_employee.id in manager_ids
        assert executive_employee.id in executive_ids

    def test_counts_match_employees_list_length(self, staff_employee, manager_employee):
        result = get_tier_distribution()
        for tier_data in result.values():
            assert tier_data["count"] == len(tier_data["employees"])

    def test_empty_ledger_still_returns_all_three_known_tiers(self):
        result = get_tier_distribution()
        assert set(result.keys()) >= {"staff", "manager", "executive"}
        for tier_data in result.values():
            assert tier_data["count"] == 0

@pytest.mark.parametrize('actor', ['EMP-STAFF1', 'EMP-MISSING'])
def test_unauthorized_rejection_has_no_side_effects(staff_employee, actor):
    from copy import deepcopy
    req = create_approval_request(_single_manager_step_chain_key(), staff_employee.id, 'Synthetic request')
    before = deepcopy(ledger.get_entity(req['id']).attributes)
    events = len(audit_log.events)
    result = reject_step(req['id'], actor, 'Unauthorized rejection')
    assert 'error' in result
    assert ledger.get_entity(req['id']).attributes == before
    assert len(audit_log.events) == events


def test_rejection_requires_current_step_tier(staff_employee, manager_employee, executive_employee):
    from copy import deepcopy
    req = create_approval_request(_multi_step_chain_key(), staff_employee.id, 'Synthetic request')
    approve_step(req['id'], manager_employee.id)
    before = deepcopy(ledger.get_entity(req['id']).attributes)
    assert 'error' in reject_step(req['id'], manager_employee.id, 'Not an executive')
    assert ledger.get_entity(req['id']).attributes == before
    assert reject_step(req['id'], executive_employee.id, 'Executive decision')['status'] == 'rejected'
