"""Tests for core/administration_menu.py -- Administration's Top Menu dispatcher
(overview/users/roles_permissions/security/systems/integrations/vendors/
organizations/data_management/identity_access/audit_center/workflow_automation/
ai_management/governance/reporting).

Every underlying engine call is a bare, module-level import (no deferred imports,
same simplicity as readiness_menu.py) -- mocked directly on the module alias.
`ledger`/`credential_store` are objects, not functions, so they get lightweight
fakes rather than lambda overrides."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.administration_menu as am
import pytest
from types import SimpleNamespace


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeEntity:
    def __init__(self, entity_id, entity_type, attributes=None):
        self.id = entity_id
        self.entity_type = entity_type
        self.attributes = attributes or {}


class _FakeLedger:
    def __init__(self, entities=None):
        self._entities = {e.id: e for e in (entities or [])}

    def get_all(self):
        return self._entities

    def get_entity(self, entity_id):
        return self._entities.get(entity_id)


class _FakeCredentialStore:
    def __init__(self, records=None, lockouts=None):
        self._records = {r["employee_id"]: r for r in (records or [])}
        self._lockouts = lockouts or {}

    def list_records(self):
        return list(self._records.values())

    def get_record(self, employee_id):
        return self._records.get(employee_id)

    def get_lockout_status(self, employee_id):
        return self._lockouts.get(employee_id, {"locked": False, "failed_attempts": 0})


def _stub_engines(monkeypatch, **overrides):
    defaults = {
        "list_audit_events": lambda event_type=None: [],
        "get_audit_dashboard": lambda: {"total_events": 0},
        "list_connections_api": lambda role: {"connections": []},
        "list_alerts_api": lambda role, status=None: {"alerts": []},
        "list_pending_campaigns_api": lambda role: [],
        "list_pending_approvals_api": lambda role: [],
        "list_pending_websites_api": lambda role: [],
        "list_pending_financing_api": lambda role: [],
        "get_escalation_dashboard": lambda: {},
        "get_governance_overview": lambda: {
            "governance_action_log": [], "compliance_summary": {}, "approval_hierarchy": {},
            "governance_health": {}, "not_yet_tracked": {},
        },
        "administration_onboarding_roster": lambda role: {
            "total_employees": 0, "by_department": {}, "employees_without_login": [],
        },
        "list_workflow_instances_api": lambda: [],
        "search_entities": lambda role, query: [],
        "get_entity_by_id": lambda role, entity_id: {"error": "Not found"},
        "get_related_entities": lambda role, entity_id: [],
        "get_department_api": lambda role, department: {},
        "list_permission_catalog": lambda: {},
        "get_effective_permissions": lambda role, employee_id: {},
        "list_overrides_for_employee": lambda employee_id: [],
        "list_all_overrides": lambda: [],
        "list_approval_chains": lambda: [],
        "list_approval_requests": lambda: [],
        "get_tier_distribution": lambda: {},
        "get_vendor_dashboard": lambda: {
            "total_vendors": 0, "active_vendors": 0, "total_monthly_cost": 0.0,
            "upcoming_renewals": [], "by_category": {},
        },
        "list_vendors": lambda category=None: [],
        "get_system_config": lambda: {"dealer_name": "NXTDeal"},
        "list_exportable_entity_types": lambda: [],
        "list_backups": lambda: [],
        "list_all_api_keys": lambda: [],
        "list_api_keys_for_employee": lambda employee_id: [],
        "get_audit_center_overview": lambda: {
            "total_events": 0, "by_type": {}, "suspicious_activity_summary": {},
        },
        "get_actor_timeline": lambda employee_id, limit=25: [],
        "get_automation_dashboard": lambda run_now=False: {},
        "get_ai_management_overview": lambda role: {
            "summary": {"total_features": 0, "enabled_count": 0, "disabled_count": 0, "features_with_recorded_activity": 0},
        },
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(am, name, value)


def _use_ledger(monkeypatch, entities=None):
    monkeypatch.setattr(am, "ledger", _FakeLedger(entities))


def _use_credential_store(monkeypatch, records=None, lockouts=None):
    monkeypatch.setattr(am, "credential_store", _FakeCredentialStore(records, lockouts))


# ---------------------------------------------------------------------------
# _entities() / _pending_count() / _approval_queue()
# ---------------------------------------------------------------------------


class TestEntities:

    def test_filters_by_entity_type(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _FakeEntity("EMP-1", am.EMPLOYEE),
            _FakeEntity("VEH-1", "Vehicle"),
        ])

        result = am._entities(am.EMPLOYEE)

        assert len(result) == 1
        assert result[0].id == "EMP-1"


class TestPendingCount:

    def test_error_dict(self):
        assert am._pending_count({"error": "Forbidden"}) == {"count": None, "error": "Forbidden"}

    def test_plain_list(self):
        result = am._pending_count([{"id": "CAMP-1"}, {"id": "CAMP-2"}])

        assert result == {"count": 2, "items": [{"id": "CAMP-1"}, {"id": "CAMP-2"}]}


class TestApprovalQueue:

    def test_composes_four_pending_sources(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_pending_campaigns_api=lambda role: [{"id": "CAMP-1"}],
            list_pending_approvals_api=lambda role: {"error": "Forbidden"},
            list_pending_websites_api=lambda role: [],
            list_pending_financing_api=lambda role: [{"id": "DEAL-1"}, {"id": "DEAL-2"}],
        )

        result = am._approval_queue("ADMIN")

        assert result["campaigns"] == {"count": 1, "items": [{"id": "CAMP-1"}]}
        assert result["assets"] == {"count": None, "error": "Forbidden"}
        assert result["websites"] == {"count": 0, "items": []}
        assert result["financing"]["count"] == 2


# ---------------------------------------------------------------------------
# overview()
# ---------------------------------------------------------------------------


class TestOverview:

    def test_admin_path(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            administration_onboarding_roster=lambda role: {
                "total_employees": 45, "by_department": {"Sales": {"with_login": 10}},
                "employees_without_login": [],
            },
            list_connections_api=lambda role: {"connections": [{"id": "CONN-1"}, {"id": "CONN-2"}]},
            list_alerts_api=lambda role, status=None: {"alerts": [{"id": "ALERT-1"}]},
            list_pending_campaigns_api=lambda role: [],
            list_pending_approvals_api=lambda role: [],
            list_pending_websites_api=lambda role: [],
            list_pending_financing_api=lambda role: [],
        )

        result = am.overview("ADMIN")

        assert result["active_users"]["count"] == 45
        assert result["connected_platforms"]["count"] == 2
        assert result["security_alerts"]["count"] == 1
        assert result["user_activity_by_department"] == {"Sales": {"with_login": 10}}
        assert "permissions_exceptions" in result["not_yet_tracked"]

    def test_non_admin_path(self, monkeypatch):
        _stub_engines(monkeypatch)

        result = am.overview("SALES")

        assert result["active_users"] == {"error": "Admin/Operations role required."}
        assert result["user_activity_by_department"] == {"error": "Admin/Operations role required."}


# ---------------------------------------------------------------------------
# _employee_brief() / _user_administration_row()
# ---------------------------------------------------------------------------


class TestEmployeeBrief:

    def test_found_employee(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _FakeEntity("EMP-1", am.EMPLOYEE, {"FirstName": "Ada", "LastName": "Lovelace", "Title": "Sales Manager", "Department": "Sales"}),
        ])

        result = am._employee_brief("EMP-1")

        assert result == {"name": "Ada Lovelace", "title": "Sales Manager", "department": "Sales"}

    def test_missing_or_wrong_type(self, monkeypatch):
        _use_ledger(monkeypatch, [_FakeEntity("VEH-1", "Vehicle")])

        assert am._employee_brief("EMP-999") == {"name": None, "title": None, "department": None}
        assert am._employee_brief("VEH-1") == {"name": None, "title": None, "department": None}


class TestUserAdministrationRow:

    def test_full_composite(self, monkeypatch):
        monkeypatch.setattr(am, "_employee_brief", lambda employee_id: {"name": "Ada Lovelace", "title": "Sales Manager", "department": "Sales"})
        _use_credential_store(monkeypatch, lockouts={"EMP-1": {"locked": True, "failed_attempts": 3}})
        _stub_engines(
            monkeypatch,
            list_overrides_for_employee=lambda employee_id: [{"id": "PERM-1", "active": True}, {"id": "PERM-2", "active": False}],
            list_api_keys_for_employee=lambda employee_id: [{"id": "KEY-1", "active": True}],
        )

        result = am._user_administration_row({"employee_id": "EMP-1", "role": "SALES", "must_change_password": True})

        assert result["employee_id"] == "EMP-1"
        assert result["name"] == "Ada Lovelace"
        assert result["locked"] is True
        assert result["failed_attempts"] == 3
        assert result["active_permission_overrides"] == 1
        assert result["active_api_keys"] == 1


# ---------------------------------------------------------------------------
# users()
# ---------------------------------------------------------------------------


class TestUsers:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.users("SALES") == am._ADMIN_ONLY_ERROR

    @pytest.mark.parametrize("system", [False, True])
    def test_query_emp_id_success(self, monkeypatch, system):
        monkeypatch.setattr(am, "system_admin_context", SimpleNamespace(get=lambda:system))
        _stub_engines(
            monkeypatch,
            get_entity_by_id=lambda role, entity_id: {"id": "EMP-1", "entity_type": "Employee"},
            get_related_entities=lambda role, entity_id: [{"id": "LEAD-1"}],
            get_effective_permissions=lambda role, employee_id: {"deals.view": True},
            list_overrides_for_employee=lambda employee_id: [{"id": "PERM-1", "active": True}],
            list_api_keys_for_employee=lambda employee_id: [{"id": "KEY-1"}],
            get_actor_timeline=lambda employee_id, limit=25: [{"event_type": "login_success"}],
        )
        _use_credential_store(monkeypatch, records=[{"employee_id": "EMP-1", "role": "SALES", "must_change_password": False, "created_at": "t1", "email": "a@b.com", "ip_allowlist": ["1.2.3.4"]}])

        result = am.users("ADMIN", query="emp-1")

        assert result["employee"] == {"id": "EMP-1", "entity_type": "Employee"}
        assert result["related_entities"] == [{"id": "LEAD-1"}]
        assert result["identity_and_access"]["role"] == "SALES"
        assert result["identity_and_access"]["email"] == "a@b.com"
        assert result["identity_and_access"]["ip_allowlist"] == ["1.2.3.4"]
        assert result["identity_and_access"]["effective_permissions"] == {"deals.view": True}
        assert result["identity_and_access"]["active_permission_overrides"] == [{"id": "PERM-1", "active": True}]
        assert result["recent_activity"] == ([{"event_type": "login_success"}] if system else {"notice": "System activity requires NXTDeal system administrator access"})
        assert result["identity_and_access"]["api_keys"] == ([{"id":"KEY-1"}] if system else [])

    def test_query_emp_id_not_found(self, monkeypatch):
        _stub_engines(monkeypatch, get_entity_by_id=lambda role, entity_id: {"error": "Not found"})

        assert am.users("ADMIN", query="EMP-999") == {"error": "Not found"}

    def test_query_free_text_filters_by_employee(self, monkeypatch):
        _stub_engines(monkeypatch, search_entities=lambda role, query: [
            {"entity_type": "Employee", "id": "EMP-1"},
            {"entity_type": "Vehicle", "id": "VEH-1"},
        ])

        result = am.users("ADMIN", query="Ada")

        assert result["count"] == 1
        assert result["results"] == [{"entity_type": "Employee", "id": "EMP-1"}]

    def test_default_view(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            administration_onboarding_roster=lambda role: {
                "total_employees": 2, "by_department": {"Sales": {}},
                "employees_without_login": [],
            },
            list_approval_requests=lambda: [
                {"chain_key": "permission_change_request", "status": "pending"},
                {"chain_key": "role_change_request", "status": "approved"},
                {"chain_key": "expense_request", "status": "pending"},
            ],
        )
        _use_credential_store(monkeypatch, records=[
            {"employee_id": "EMP-1", "role": "SALES"},
            {"employee_id": "EMP-2", "role": "SALES"},
            {"employee_id": "EMP-3", "role": "ADMIN"},
        ])
        monkeypatch.setattr(am, "_user_administration_row", lambda rec: {
            "employee_id": rec["employee_id"], "locked": rec["employee_id"] == "EMP-1",
            "active_permission_overrides": 1 if rec["employee_id"] == "EMP-2" else 0,
            "active_api_keys": 0,
        })

        result = am.users("ADMIN")

        assert result["active_employees"]["count"] == 2
        assert result["role_assignments"] == {"SALES": 2, "ADMIN": 1}
        assert result["user_administration"]["count"] == 3
        assert result["user_administration"]["locked_count"] == 1
        assert result["user_administration"]["with_active_overrides_count"] == 1
        assert result["permission_requests"]["count"] == 2  # expense_request excluded
        assert result["permission_requests"]["by_status"] == {"pending": 1, "approved": 1}
        assert "new_hires" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# roles_permissions()
# ---------------------------------------------------------------------------


class TestRolesPermissions:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.roles_permissions("SALES") == am._ADMIN_ONLY_ERROR

    def test_query_emp_id_success(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            get_entity_by_id=lambda role, entity_id: {"id": "EMP-1"},
            get_effective_permissions=lambda role, employee_id: {"deals.view": True},
            list_overrides_for_employee=lambda employee_id: [{"id": "PERM-1"}],
        )

        result = am.roles_permissions("ADMIN", query="EMP-1")

        assert result == {
            "employee": {"id": "EMP-1"},
            "effective_permissions": {"deals.view": True},
            "overrides": [{"id": "PERM-1"}],
        }

    def test_query_emp_id_not_found(self, monkeypatch):
        _stub_engines(monkeypatch, get_entity_by_id=lambda role, entity_id: {"error": "Not found"})

        assert am.roles_permissions("ADMIN", query="EMP-999") == {"error": "Not found"}

    def test_query_free_text(self, monkeypatch):
        _stub_engines(monkeypatch, search_entities=lambda role, query: [{"entity_type": "Employee", "id": "EMP-1"}])

        result = am.roles_permissions("ADMIN", query="Ada")

        assert result["count"] == 1

    def test_default_view(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_permission_catalog=lambda: {"deals.view": {}},
            get_tier_distribution=lambda: {"staff": {"count": 30}, "manager": {"count": 5}},
            list_all_overrides=lambda: [{"id": "PERM-1", "active": True}, {"id": "PERM-2", "active": False}],
            list_approval_chains=lambda: [{"key": "permission_change_request"}],
            list_approval_requests=lambda: [{"status": "pending"}, {"status": "pending"}, {"status": "approved"}],
        )

        result = am.roles_permissions("ADMIN")

        assert result["permission_catalog"] == {"deals.view": {}}
        assert result["tier_distribution"] == {"staff": 30, "manager": 5}
        assert result["active_overrides"]["count"] == 1
        assert result["approval_requests"] == {"by_status": {"pending": 2, "approved": 1}, "total": 3}


# ---------------------------------------------------------------------------
# security()
# ---------------------------------------------------------------------------


class TestSecurity:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.security("SALES") == am._ADMIN_ONLY_ERROR

    def test_full_path(self, monkeypatch):
        def _events(event_type=None):
            return {
                "login_success": [{"id": "AUD-1", "actor": "EMP-1", "entity_id": "EMP-1", "timestamp": "t1"}],
                "login_failed": [{"id": "AUD-2"}],
                "credential_created": [{"id": "AUD-3"}],
                "credential_reset": [],
                "password_changed": [{"id": "AUD-4"}],
            }[event_type]

        _stub_engines(monkeypatch, list_audit_events=_events)
        _use_credential_store(
            monkeypatch,
            records=[{"employee_id": "EMP-1"}, {"employee_id": "EMP-2"}],
            lockouts={"EMP-1": {"locked": True, "failed_attempts": 5}},
        )
        # get_record needs to expose ip_allowlist for the coverage count
        store = am.credential_store
        store._records["EMP-1"]["ip_allowlist"] = ["1.2.3.4"]
        store._records["EMP-2"]["ip_allowlist"] = []

        result = am.security("ADMIN")

        assert result["login_activity"]["count"] == 1
        assert result["failed_logins"]["count"] == 1
        assert result["security_events"] == {"credential_created": 1, "credential_reset": 0, "password_changed": 1}
        assert result["account_lockouts"]["count"] == 1
        assert result["account_lockouts"]["locked_employees"][0]["employee_id"] == "EMP-1"
        assert result["ip_allowlist_coverage"] == {"restricted_employee_count": 1, "total_employee_count": 2, **result["ip_allowlist_coverage"]}
        assert result["ip_allowlist_coverage"]["restricted_employee_count"] == 1
        assert "mfa_status" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# systems()
# ---------------------------------------------------------------------------


class TestSystems:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.systems("SALES") == am._ADMIN_ONLY_ERROR

    def test_full_path_with_instances(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            get_audit_dashboard=lambda: {"total_events": 500},
            list_workflow_instances_api=lambda: [
                {"status": "active"}, {"status": "active"}, {"status": "completed"},
            ],
        )

        result = am.systems("ADMIN")

        assert result["audit_logs"] == {"total_events": 500}
        assert result["workflow_engine"] == {"total_instances": 3, "by_status": {"active": 2, "completed": 1}}
        assert "dealeros_services" in result["not_yet_tracked"]

    def test_non_list_instances(self, monkeypatch):
        _stub_engines(monkeypatch, list_workflow_instances_api=lambda: {"error": "Forbidden"})

        result = am.systems("ADMIN")

        assert result["workflow_engine"] == {"total_instances": None, "by_status": {}}


# ---------------------------------------------------------------------------
# integrations()
# ---------------------------------------------------------------------------


class TestIntegrations:

    def test_error_passthrough(self, monkeypatch):
        _stub_engines(monkeypatch, list_connections_api=lambda role: {"error": "Forbidden"})

        assert am.integrations("SALES") == {"error": "Forbidden"}

    def test_full_path(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_connections_api=lambda role: {"connections": [
                {"connection_type": "api", "status": "connected", "department": "sales"},
                {"connection_type": "csv", "status": "error", "department": "service"},
                {"connection_type": "api", "status": "connected", "department": "sales"},
            ]},
            list_vendors=lambda category=None: [
                {"status": "active", "monthly_cost": 100.0},
                {"status": "active", "monthly_cost": 50.5},
                {"status": "cancelled", "monthly_cost": 200.0},
            ],
        )

        result = am.integrations("ADMIN")

        assert result["total_connections"] == 3
        assert result["by_connection_type"] == {"api": 2, "csv": 1}
        assert result["by_status"] == {"connected": 2, "error": 1}
        assert result["by_department"] == {"sales": 2, "service": 1}
        assert result["software_vendor_contracts"]["count"] == 3
        assert result["software_vendor_contracts"]["active_monthly_cost"] == 150.5


# ---------------------------------------------------------------------------
# vendors()
# ---------------------------------------------------------------------------


class TestVendors:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.vendors("SALES") == am._ADMIN_ONLY_ERROR

    def test_full_path(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_connections_api=lambda role: {"connections": [{"id": "CONN-1"}]},
            get_vendor_dashboard=lambda: {"total_vendors": 4, "active_vendors": 3},
        )

        result = am.vendors("ADMIN")

        assert result["vendors"] == {"total_vendors": 4, "active_vendors": 3}
        assert result["active_vendors_proxy"]["count"] == 1
        assert "usage_analysis" in result["not_yet_tracked"]

    def test_connections_forbidden_falls_back_to_empty(self, monkeypatch):
        _stub_engines(monkeypatch, list_connections_api=lambda role: {"error": "Forbidden"})

        result = am.vendors("ADMIN")

        assert result["active_vendors_proxy"]["count"] == 0


# ---------------------------------------------------------------------------
# organizations()
# ---------------------------------------------------------------------------


class TestOrganizations:

    def test_thin_passthrough(self, monkeypatch):
        _stub_engines(monkeypatch, get_system_config=lambda: {"dealer_name": "Acme Motors"})

        assert am.organizations("SALES") == {"dealer_name": "Acme Motors"}


# ---------------------------------------------------------------------------
# data_management()
# ---------------------------------------------------------------------------


class TestDataManagement:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.data_management("SALES") == am._ADMIN_ONLY_ERROR

    def test_full_path(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_exportable_entity_types=lambda: ["Vehicle", "Customer"],
            list_backups=lambda: [{"id": "BACKUP-1"}],
        )

        result = am.data_management("ADMIN")

        assert result["exportable_entity_types"] == ["Vehicle", "Customer"]
        assert result["backups"] == [{"id": "BACKUP-1"}]
        assert "scheduled_backups" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# identity_access()
# ---------------------------------------------------------------------------


class TestIdentityAccess:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.identity_access("SALES") == am._ADMIN_ONLY_ERROR

    def test_full_path(self, monkeypatch):
        _stub_engines(monkeypatch, list_all_api_keys=lambda: [
            {"id": "KEY-1", "active": True}, {"id": "KEY-2", "active": False}, {"id": "KEY-3", "active": True},
        ])

        result = am.identity_access("ADMIN")

        assert result["total_keys"] == 3
        assert result["active_keys"]["count"] == 2
        assert result["revoked_keys"]["count"] == 1


# ---------------------------------------------------------------------------
# audit_center() / workflow_automation() / ai_management()
# ---------------------------------------------------------------------------


class TestAuditCenter:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.audit_center("SALES") == am._ADMIN_ONLY_ERROR

    def test_thin_passthrough(self, monkeypatch):
        _stub_engines(monkeypatch, get_audit_center_overview=lambda: {"total_events": 200})

        assert am.audit_center("ADMIN") == {"total_events": 200}


class TestWorkflowAutomation:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.workflow_automation("SALES") == am._ADMIN_ONLY_ERROR

    def test_thin_passthrough(self, monkeypatch):
        _stub_engines(monkeypatch, get_automation_dashboard=lambda run_now=False: {"rules": [], "run_now_used": run_now})

        assert am.workflow_automation("ADMIN") == {"rules": [], "run_now_used": True}


class TestAiManagement:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.ai_management("SALES") == am._ADMIN_ONLY_ERROR

    def test_thin_passthrough(self, monkeypatch):
        _stub_engines(monkeypatch, get_ai_management_overview=lambda role: {"features": []})

        assert am.ai_management("ADMIN") == {"features": []}


# ---------------------------------------------------------------------------
# governance()
# ---------------------------------------------------------------------------


class TestGovernance:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.governance("SALES") == am._ADMIN_ONLY_ERROR

    def test_full_path(self, monkeypatch):
        monkeypatch.setattr(am, "_approval_queue", lambda role: {"campaigns": {"count": 1}})
        _stub_engines(
            monkeypatch,
            get_escalation_dashboard=lambda: {"open_escalations": 2},
            get_governance_overview=lambda: {
                "governance_action_log": [{"event": "resolved"}],
                "compliance_summary": {"open": 3},
                "approval_hierarchy": {"pending": 1},
                "governance_health": {"score": 90.0},
                "not_yet_tracked": {"policy_management": "gap"},
            },
        )

        result = am.governance("ADMIN")

        assert result["approval_queue"] == {"campaigns": {"count": 1}}
        assert result["escalation_rules"] == {"open_escalations": 2}
        assert result["audit_trail"] == [{"event": "resolved"}]
        assert result["compliance_summary"] == {"open": 3}
        assert result["approval_hierarchy"] == {"pending": 1}
        assert result["governance_health"] == {"score": 90.0}
        assert result["not_yet_tracked"] == {"policy_management": "gap"}


# ---------------------------------------------------------------------------
# reporting()
# ---------------------------------------------------------------------------


class TestReporting:

    def test_non_admin_denied(self, monkeypatch):
        _stub_engines(monkeypatch)

        assert am.reporting("SALES") == am._ADMIN_ONLY_ERROR

    @pytest.mark.parametrize("system", [False, True])
    def test_full_path(self, monkeypatch, system):
        monkeypatch.setattr(am, "system_admin_context", SimpleNamespace(get=lambda:system))
        monkeypatch.setattr(am, "_approval_queue", lambda role: {"campaigns": {"count": 1}})
        _stub_engines(
            monkeypatch,
            administration_onboarding_roster=lambda role: {
                "total_employees": 10,
                "by_department": {"Sales": {"with_login": 4}, "Service": {"with_login": 3}},
                "employees_without_login": [],
            },
            list_connections_api=lambda role: {"connections": [
                {"status": "connected"}, {"status": "connected"}, {"status": "error"},
            ]},
            get_vendor_dashboard=lambda: {
                "total_vendors": 5, "active_vendors": 4, "total_monthly_cost": 999.0,
                "upcoming_renewals": [{"id": "V-1"}], "by_category": {"software": 5},
            },
            get_audit_center_overview=lambda: {
                "total_events": 300, "by_type": {"login_success": 100}, "suspicious_activity_summary": {"count": 2},
            },
            get_tier_distribution=lambda: {"staff": {"count": 8}, "manager": {"count": 2}},
            list_all_overrides=lambda: [{"id": "PERM-1"}],
            list_approval_requests=lambda: [{"status": "pending"}, {"status": "approved"}, {"status": "approved"}],
            get_ai_management_overview=lambda role: {
                "summary": {"total_features": 13, "enabled_count": 10, "disabled_count": 3, "features_with_recorded_activity": 5},
            },
            get_department_api=lambda role, department: {"department": department, "kpis": {}},
        )

        result = am.reporting("ADMIN")

        assert result["user_reports"] == {"total_employees": 10, "with_login": 7, "dealeros_adoption_rate": 0.7}
        assert result["integration_reports"] == {"by_status": {"connected": 2, "error": 1}}
        assert result["governance_reports"] == {"approval_queue": {"campaigns": {"count": 1}}}
        assert result["vendor_summary"] == {
            "total_vendors": 5, "active_vendors": 4, "total_monthly_cost": 999.0,
            "upcoming_renewals_count": 1, "by_category": {"software": 5},
        }
        assert result["audit_summary"] == ({"total_events": 300, "by_type": {"login_success": 100}, "suspicious_activity": {"count": 2}} if system else {"notice": "System audit reports require NXTDeal system administrator access"})
        assert result["permissions_summary"] == {
            "tier_distribution": {"staff": 8, "manager": 2},
            "active_overrides_count": 1,
            "approval_requests_by_status": {"pending": 1, "approved": 2},
            "total_approval_requests": 3,
        }
        assert result["ai_adoption_summary"] == {
            "total_features": 13, "enabled_count": 10, "disabled_count": 3, "features_with_recorded_activity": 5,
        }
        assert result["forecasting"] is None
        assert result["department_intelligence"] == {"department": "executive", "kpis": {}}
        assert "security_reports" in result["not_yet_tracked"]

    def test_zero_employees_avoids_division(self, monkeypatch):
        monkeypatch.setattr(am, "_approval_queue", lambda role: {})
        _stub_engines(monkeypatch, administration_onboarding_roster=lambda role: {
            "total_employees": 0, "by_department": {}, "employees_without_login": [],
        })

        result = am.reporting("ADMIN")

        assert result["user_reports"]["dealeros_adoption_rate"] is None
