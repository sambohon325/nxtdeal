"""
Tests for a batch of 12 tiny `_api.py` wrapper modules -- each is a thin
pass-through / ACL layer over its own already-larger delegate module, same
"batch several thin wrappers into one combined test file" precedent as
test_routing_api.py / test_opportunities_api.py / the earlier
"5 thin pipeline-wrapper modules" batch (task #179). Every delegate function
is monkeypatched at its own importing module's namespace (top-level `from X
import Y` binding), matching this codebase's established
top-level-vs-deferred-import monkeypatch targeting rule -- no real ledger
fixtures are needed since these modules contain no business logic of their
own beyond validation/role-gating and delegation.

Covers:
  core/manager_dashboard_api.py
  core/audit_network_api.py
  core/workflow_tab_data_api.py
  core/operations_overview_api.py
  core/sales_overview_api.py
  core/service_overview_api.py
  core/ai_business_analyst_api.py
  core/ai_management_network_api.py
  core/platform_metrics_network_api.py
  core/workspace_explain_api.py
  core/operations_alerts_api.py
  core/performance_readiness_api.py

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

import core.manager_dashboard_api as manager_dashboard_api
from core.manager_dashboard_api import get_dashboard

import core.audit_network_api as audit_network_api
from core.audit_network_api import get_operational_health_snapshot_api

import core.workflow_tab_data_api as workflow_tab_data_api
from core.workflow_tab_data_api import get_tab_data_api

import core.operations_overview_api as operations_overview_api
from core.operations_overview_api import get_operations_overview_api

import core.sales_overview_api as sales_overview_api
from core.sales_overview_api import get_my_day_api

import core.service_overview_api as service_overview_api
from core.service_overview_api import get_service_my_day_api

import core.ai_business_analyst_api as ai_business_analyst_api
from core.ai_business_analyst_api import ask_business_analyst_api

import core.ai_management_network_api as ai_management_network_api
from core.ai_management_network_api import get_ai_management_network_snapshot_api

import core.platform_metrics_network_api as platform_metrics_network_api
from core.platform_metrics_network_api import get_platform_metrics_snapshot_api

import core.workspace_explain_api as workspace_explain_api
from core.workspace_explain_api import explain_chart_api

import core.operations_alerts_api as operations_alerts_api
from core.operations_alerts_api import (
    get_alert_feed_api,
    get_alert_stats_api,
    acknowledge_alert_api,
)

import core.performance_readiness_api as performance_readiness_api
from core.performance_readiness_api import (
    get_performance_readiness_overview_api,
    get_performance_readiness_department_api,
)


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


# ---------------------------------------------------------------------------
# core/manager_dashboard_api.py
# ---------------------------------------------------------------------------


class TestGetDashboard:

    def test_delegates_to_get_manager_dashboard(self, monkeypatch):
        monkeypatch.setattr(
            manager_dashboard_api, "get_manager_dashboard",
            lambda: [{"employee_id": "EMP-1"}],
        )
        result = get_dashboard()
        assert result == [{"employee_id": "EMP-1"}]

    def test_no_args_required(self, monkeypatch):
        monkeypatch.setattr(manager_dashboard_api, "get_manager_dashboard", lambda: [])
        assert get_dashboard() == []


# ---------------------------------------------------------------------------
# core/audit_network_api.py
# ---------------------------------------------------------------------------


class TestGetOperationalHealthSnapshotApi:

    def test_bad_network_key_rejected(self, monkeypatch):
        monkeypatch.setattr(audit_network_api, "check_network_key", lambda key: {"error": "invalid or missing X-NXTDeal-Network-Key"})
        result = get_operational_health_snapshot_api("wrong-key")
        assert result == {"error": "invalid or missing X-NXTDeal-Network-Key"}

    def test_valid_network_key_delegates_to_snapshot_builder(self, monkeypatch):
        monkeypatch.setattr(audit_network_api, "check_network_key", lambda key: None)
        monkeypatch.setattr(audit_network_api, "build_operational_health_snapshot", lambda: {"logins": 10})
        result = get_operational_health_snapshot_api("correct-key")
        assert result == {"logins": 10}

    def test_key_check_short_circuits_before_snapshot_build(self, monkeypatch):
        called = {"snapshot_built": False}

        def fake_snapshot():
            called["snapshot_built"] = True
            return {}

        monkeypatch.setattr(audit_network_api, "check_network_key", lambda key: {"error": "bad key"})
        monkeypatch.setattr(audit_network_api, "build_operational_health_snapshot", fake_snapshot)
        get_operational_health_snapshot_api("bad")
        assert called["snapshot_built"] is False


# ---------------------------------------------------------------------------
# core/workflow_tab_data_api.py
# ---------------------------------------------------------------------------


class TestGetTabDataApi:

    def test_delegates_with_all_args(self, monkeypatch):
        captured = {}

        def fake_get_tab_data(role, workflow_key, linked_entity_id=None):
            captured["role"] = role
            captured["workflow_key"] = workflow_key
            captured["linked_entity_id"] = linked_entity_id
            return {"tabs": []}

        monkeypatch.setattr(workflow_tab_data_api, "get_tab_data", fake_get_tab_data)
        result = get_tab_data_api(ADMIN, "sales.up_system", linked_entity_id="LEAD-1")
        assert result == {"tabs": []}
        assert captured == {"role": ADMIN, "workflow_key": "sales.up_system", "linked_entity_id": "LEAD-1"}

    def test_linked_entity_id_defaults_to_none(self, monkeypatch):
        captured = {}

        def fake_get_tab_data(role, workflow_key, linked_entity_id=None):
            captured["linked_entity_id"] = linked_entity_id
            return {}

        monkeypatch.setattr(workflow_tab_data_api, "get_tab_data", fake_get_tab_data)
        get_tab_data_api(SALES, "sales.bdc")
        assert captured["linked_entity_id"] is None


# ---------------------------------------------------------------------------
# core/operations_overview_api.py
# ---------------------------------------------------------------------------


class TestGetOperationsOverviewApi:

    def test_no_role_gate_delegates_directly(self, monkeypatch):
        monkeypatch.setattr(operations_overview_api, "get_operations_overview", lambda role: {"role_seen": role})
        result = get_operations_overview_api(SALES)
        assert result == {"role_seen": SALES}

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_role_passes_through(self, monkeypatch, role):
        monkeypatch.setattr(operations_overview_api, "get_operations_overview", lambda role: {"role_seen": role})
        result = get_operations_overview_api(role)
        assert result == {"role_seen": role}


# ---------------------------------------------------------------------------
# core/sales_overview_api.py
# ---------------------------------------------------------------------------


class TestGetMyDayApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES])
    def test_allowed_roles_delegate(self, monkeypatch, role):
        monkeypatch.setattr(sales_overview_api, "get_my_day", lambda role, employee_id: {"employee_id": employee_id})
        result = get_my_day_api(role, "EMP-1")
        assert result == {"employee_id": "EMP-1"}

    @pytest.mark.parametrize("role", [MARKETING, SERVICE, FINANCE])
    def test_disallowed_roles_denied(self, role):
        result = get_my_day_api(role, "EMP-1")
        assert result == {"error": "You don't have access to the Sales Overview"}

    def test_missing_employee_id_rejected(self):
        result = get_my_day_api(ADMIN, None)
        assert result == {"error": "employee_id is required"}

    def test_empty_string_employee_id_rejected(self):
        result = get_my_day_api(ADMIN, "")
        assert result == {"error": "employee_id is required"}

    def test_role_check_happens_before_employee_id_check(self):
        # a disallowed role with a missing employee_id should surface the role
        # denial, not the employee_id validation -- confirms gate ordering.
        result = get_my_day_api(MARKETING, None)
        assert "access" in result["error"]


# ---------------------------------------------------------------------------
# core/service_overview_api.py
# ---------------------------------------------------------------------------


class TestGetServiceMyDayApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SERVICE])
    def test_allowed_roles_delegate(self, monkeypatch, role):
        monkeypatch.setattr(service_overview_api, "get_service_my_day", lambda role, employee_id: {"employee_id": employee_id})
        result = get_service_my_day_api(role, "EMP-2")
        assert result == {"employee_id": "EMP-2"}

    @pytest.mark.parametrize("role", [MARKETING, SALES, FINANCE])
    def test_disallowed_roles_denied(self, role):
        result = get_service_my_day_api(role, "EMP-2")
        assert result == {"error": "You don't have access to the Service Overview"}

    def test_missing_employee_id_rejected(self):
        result = get_service_my_day_api(ADMIN, None)
        assert result == {"error": "employee_id is required"}


# ---------------------------------------------------------------------------
# core/ai_business_analyst_api.py
# ---------------------------------------------------------------------------


class TestAskBusinessAnalystApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_role_allowed(self, monkeypatch, role):
        monkeypatch.setattr(
            ai_business_analyst_api, "ask_business_analyst",
            lambda question, role, employee_id=None: {"answer": question, "role": role, "employee_id": employee_id},
        )
        result = ask_business_analyst_api(role, "why is inventory aging?", employee_id="EMP-9")
        assert result == {"answer": "why is inventory aging?", "role": role, "employee_id": "EMP-9"}

    def test_unknown_role_denied(self):
        result = ask_business_analyst_api("NOT-A-REAL-ROLE", "question?")
        assert result == {"error": "You don't have access to the AI Business Analyst."}

    def test_employee_id_defaults_to_none(self, monkeypatch):
        captured = {}

        def fake_ask(question, role, employee_id=None):
            captured["employee_id"] = employee_id
            return {}

        monkeypatch.setattr(ai_business_analyst_api, "ask_business_analyst", fake_ask)
        ask_business_analyst_api(ADMIN, "question?")
        assert captured["employee_id"] is None


# ---------------------------------------------------------------------------
# core/ai_management_network_api.py
# ---------------------------------------------------------------------------


class TestGetAiManagementNetworkSnapshotApi:

    def test_bad_network_key_rejected(self, monkeypatch):
        monkeypatch.setattr(ai_management_network_api, "check_network_key", lambda key: {"error": "invalid or missing X-NXTDeal-Network-Key"})
        result = get_ai_management_network_snapshot_api("wrong")
        assert result == {"error": "invalid or missing X-NXTDeal-Network-Key"}

    def test_valid_key_delegates_to_snapshot_builder(self, monkeypatch):
        monkeypatch.setattr(ai_management_network_api, "check_network_key", lambda key: None)
        monkeypatch.setattr(ai_management_network_api, "build_ai_management_network_snapshot", lambda: {"features": []})
        result = get_ai_management_network_snapshot_api("correct")
        assert result == {"features": []}


# ---------------------------------------------------------------------------
# core/platform_metrics_network_api.py
# ---------------------------------------------------------------------------


class TestGetPlatformMetricsSnapshotApi:

    def test_bad_network_key_rejected(self, monkeypatch):
        monkeypatch.setattr(platform_metrics_network_api, "check_network_key", lambda key: {"error": "invalid or missing X-NXTDeal-Network-Key"})
        result = get_platform_metrics_snapshot_api("wrong")
        assert result == {"error": "invalid or missing X-NXTDeal-Network-Key"}

    def test_valid_key_delegates_to_snapshot_builder(self, monkeypatch):
        monkeypatch.setattr(platform_metrics_network_api, "check_network_key", lambda key: None)
        monkeypatch.setattr(platform_metrics_network_api, "get_platform_metrics_snapshot", lambda: {"groups": {}})
        result = get_platform_metrics_snapshot_api("correct")
        assert result == {"groups": {}}


# ---------------------------------------------------------------------------
# core/workspace_explain_api.py
# ---------------------------------------------------------------------------


class TestExplainChartApi:

    def test_wraps_delegate_result_in_text_key(self, monkeypatch):
        monkeypatch.setattr(workspace_explain_api, "explain_chart", lambda **kwargs: "This chart shows real data.")
        result = explain_chart_api(rows=[{"a": 1}], numeric_columns=["a"])
        assert result == {"text": "This chart shows real data."}

    def test_all_kwargs_forwarded(self, monkeypatch):
        captured = {}

        def fake_explain_chart(**kwargs):
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(workspace_explain_api, "explain_chart", fake_explain_chart)
        explain_chart_api(
            source_label="Aging Board",
            department="Inventory",
            item_key="pricing_desk",
            label_column="name",
            numeric_columns=["value"],
            rows=[{"name": "x", "value": 1}],
            prompt_context="why is this low?",
        )
        assert captured == {
            "source_label": "Aging Board",
            "department": "Inventory",
            "item_key": "pricing_desk",
            "label_column": "name",
            "numeric_columns": ["value"],
            "rows": [{"name": "x", "value": 1}],
            "prompt_context": "why is this low?",
        }

    def test_defaults_all_none(self, monkeypatch):
        captured = {}

        def fake_explain_chart(**kwargs):
            captured.update(kwargs)
            return "ok"

        monkeypatch.setattr(workspace_explain_api, "explain_chart", fake_explain_chart)
        explain_chart_api()
        assert captured == {
            "source_label": None,
            "department": None,
            "item_key": None,
            "label_column": None,
            "numeric_columns": None,
            "rows": None,
            "prompt_context": None,
        }


# ---------------------------------------------------------------------------
# core/operations_alerts_api.py
# ---------------------------------------------------------------------------


class TestGetAlertFeedApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_role_view_allowed(self, monkeypatch, role):
        monkeypatch.setattr(operations_alerts_api, "get_alert_feed", lambda role: {"alerts": [], "role": role})
        result = get_alert_feed_api(role)
        assert result == {"alerts": [], "role": role}

    def test_unknown_role_denied(self):
        result = get_alert_feed_api("NOT-A-ROLE")
        assert result == {"error": "You don't have access to the Alerts nervous system"}


class TestGetAlertStatsApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_role_view_allowed(self, monkeypatch, role):
        monkeypatch.setattr(operations_alerts_api, "get_alert_stats", lambda role: {"total": 0})
        result = get_alert_stats_api(role)
        assert result == {"total": 0}

    def test_unknown_role_denied(self):
        result = get_alert_stats_api("NOT-A-ROLE")
        assert result == {"error": "You don't have access to the Alerts nervous system"}


class TestAcknowledgeAlertApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SERVICE])
    def test_allowed_roles_can_acknowledge(self, monkeypatch, role):
        captured = {}

        def fake_acknowledge(alert_type, source_id, employee_id, notes=""):
            captured.update(alert_type=alert_type, source_id=source_id, employee_id=employee_id, notes=notes)
            return {"ok": True}

        monkeypatch.setattr(operations_alerts_api, "acknowledge_alert", fake_acknowledge)
        result = acknowledge_alert_api(role, "EMP-1", "ownership_mismatch", "VEH-1", notes="checked")
        assert result == {"ok": True}
        assert captured == {"alert_type": "ownership_mismatch", "source_id": "VEH-1", "employee_id": "EMP-1", "notes": "checked"}

    @pytest.mark.parametrize("role", [SALES, MARKETING, FINANCE])
    def test_disallowed_roles_denied(self, role):
        result = acknowledge_alert_api(role, "EMP-1", "ownership_mismatch", "VEH-1")
        assert result == {"error": "You don't have access to the Alerts nervous system"}

    def test_notes_default_to_empty_string(self, monkeypatch):
        captured = {}

        def fake_acknowledge(alert_type, source_id, employee_id, notes=""):
            captured["notes"] = notes
            return {}

        monkeypatch.setattr(operations_alerts_api, "acknowledge_alert", fake_acknowledge)
        acknowledge_alert_api(ADMIN, "EMP-1", "stalled_deal", "DEAL-1")
        assert captured["notes"] == ""


# ---------------------------------------------------------------------------
# core/performance_readiness_api.py
# ---------------------------------------------------------------------------


class TestGetPerformanceReadinessOverviewApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_role_allowed(self, monkeypatch, role):
        monkeypatch.setattr(performance_readiness_api, "get_performance_readiness_overview", lambda: {"departments": {}})
        result = get_performance_readiness_overview_api(role)
        assert result == {"departments": {}}

    def test_unknown_role_denied(self):
        result = get_performance_readiness_overview_api("NOT-A-ROLE")
        assert result == {"error": "You don't have access to Performance Readiness data."}


class TestGetPerformanceReadinessDepartmentApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_role_allowed(self, monkeypatch, role):
        monkeypatch.setattr(
            performance_readiness_api, "get_department_performance_readiness",
            lambda department: {"department": department},
        )
        result = get_performance_readiness_department_api(role, "sales")
        assert result == {"department": "sales"}

    def test_unknown_role_denied(self):
        result = get_performance_readiness_department_api("NOT-A-ROLE", "sales")
        assert result == {"error": "You don't have access to Performance Readiness data."}
