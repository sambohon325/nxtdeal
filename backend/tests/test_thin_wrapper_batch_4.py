"""
Tests for a fourth batch of thin `_api.py` wrapper/ACL modules -- same batching
precedent as test_thin_wrapper_batch_2.py/test_thin_wrapper_batch_3.py: pure
gate+delegate modules are exercised via monkeypatched delegates at the importing
module's own namespace; modules with real business logic (entity lookups,
ownership checks, attribute mutation) get real ledger fixtures instead.

Covers: lead_assignment_api, general_ledger_api, smart_audiences_api,
audit_center_api, campaign_analytics_api, event_planning_api,
workflow_automation_api, operations_tasks_api, appointments_api,
social_posts_api, permissions_registry_api, marketing_lists_api.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


# ---------------------------------------------------------------------------
# lead_assignment_api.py
# ---------------------------------------------------------------------------

import core.lead_assignment_api as lead_assignment_api
from core.lead_assignment_api import transfer_lead_api, list_sales_employees_api


@pytest.fixture(autouse=True)
def no_real_persistence_lead_assignment(monkeypatch):
    monkeypatch.setattr(lead_assignment_api, "save_graph", lambda filepath: None)


class TestTransferLeadApi:

    @pytest.mark.parametrize("role", [MARKETING, SERVICE, FINANCE])
    def test_disallowed_roles_denied(self, role):
        result = transfer_lead_api(role, "EMP-1", "LEAD-1", "EMP-2")
        assert "error" in result

    def test_lead_not_found(self):
        result = transfer_lead_api(ADMIN, "EMP-1", "LEAD-missing", "EMP-2")
        assert result == {"error": "Lead 'LEAD-missing' not found"}

    def test_lead_wrong_entity_type_rejected(self):
        ledger.add_entity(Entity(id="LEAD-1", entity_type="Customer", attributes={}))
        result = transfer_lead_api(ADMIN, "EMP-1", "LEAD-1", "EMP-2")
        assert result == {"error": "Lead 'LEAD-1' not found"}

    def test_employee_not_found(self):
        ledger.add_entity(Entity(id="LEAD-1", entity_type=LEAD, attributes={}))
        result = transfer_lead_api(ADMIN, "EMP-1", "LEAD-1", "EMP-missing")
        assert result == {"error": "Employee 'EMP-missing' not found"}

    def test_employee_wrong_entity_type_rejected(self):
        ledger.add_entity(Entity(id="LEAD-1", entity_type=LEAD, attributes={}))
        ledger.add_entity(Entity(id="EMP-2", entity_type="Customer", attributes={}))
        result = transfer_lead_api(ADMIN, "EMP-1", "LEAD-1", "EMP-2")
        assert result == {"error": "Employee 'EMP-2' not found"}

    def test_successful_transfer(self, monkeypatch):
        ledger.add_entity(Entity(id="LEAD-1", entity_type=LEAD, attributes={}))
        ledger.add_entity(Entity(id="EMP-2", entity_type="Employee", attributes={}))

        called = {}
        monkeypatch.setattr(
            lead_assignment_api, "assign_lead",
            lambda lead_id, employee_id: called.update(lead_id=lead_id, employee_id=employee_id),
        )

        result = transfer_lead_api(SALES, "EMP-1", "LEAD-1", "EMP-2")

        assert result == {"lead_id": "LEAD-1", "transferred_from": "EMP-1", "transferred_to": "EMP-2"}
        assert called == {"lead_id": "LEAD-1", "employee_id": "EMP-2"}
        assert ledger.get_entity("LEAD-1").attributes["AssignedSalesperson"] == "EMP-2"


class TestListSalesEmployeesApi:

    @pytest.mark.parametrize("role", [MARKETING, SERVICE, FINANCE])
    def test_disallowed_roles_denied(self, role):
        result = list_sales_employees_api(role)
        assert result == {"error": "You don't have access to the employee roster"}

    def test_filters_to_sales_department_only(self):
        ledger.add_entity(Entity(
            id="EMP-1", entity_type="Employee",
            attributes={"Department": "Sales", "FirstName": "Alice", "LastName": "Smith", "Title": "Rep"},
        ))
        ledger.add_entity(Entity(
            id="EMP-2", entity_type="Employee",
            attributes={"Department": " sales ", "FirstName": "Bob", "LastName": "Jones", "Title": "Manager"},
        ))
        ledger.add_entity(Entity(
            id="EMP-3", entity_type="Employee",
            attributes={"Department": "Service", "FirstName": "Carl", "LastName": "Lee", "Title": "Tech"},
        ))
        ledger.add_entity(Entity(id="VEH-1", entity_type="Vehicle", attributes={}))

        result = list_sales_employees_api(ADMIN)

        ids = {r["id"] for r in result}
        assert ids == {"EMP-1", "EMP-2"}
        alice = next(r for r in result if r["id"] == "EMP-1")
        assert alice == {"id": "EMP-1", "name": "Alice Smith", "title": "Rep"}


# ---------------------------------------------------------------------------
# general_ledger_api.py
# ---------------------------------------------------------------------------

import core.general_ledger_api as general_ledger_api
from core.general_ledger_api import (
    get_chart_of_accounts_api,
    sync_real_entries_api,
    generate_simulated_entries_api,
    delete_entry_api,
    get_general_ledger_api,
    get_trial_balance_api,
    get_income_statement_api,
    get_balance_sheet_api,
)

_GL_DENIED_ROLES = [SALES, MARKETING, SERVICE]


class TestGeneralLedgerApi:

    @pytest.mark.parametrize("role", _GL_DENIED_ROLES)
    def test_get_chart_of_accounts_denied(self, role):
        assert "error" in get_chart_of_accounts_api(role)

    def test_get_chart_of_accounts_delegates(self, monkeypatch):
        monkeypatch.setattr(general_ledger_api, "get_chart_of_accounts", lambda: [{"account": "Cash"}])
        result = get_chart_of_accounts_api(FINANCE)
        assert result == {"accounts": [{"account": "Cash"}]}

    @pytest.mark.parametrize("role", _GL_DENIED_ROLES)
    def test_sync_real_entries_denied(self, role):
        assert "error" in sync_real_entries_api(role, "EMP-1")

    def test_sync_real_entries_delegates(self, monkeypatch):
        monkeypatch.setattr(general_ledger_api, "sync_real_entries", lambda synced_by: {"synced_by": synced_by})
        assert sync_real_entries_api(ADMIN, "EMP-1") == {"synced_by": "EMP-1"}

    @pytest.mark.parametrize("role", _GL_DENIED_ROLES)
    def test_generate_simulated_entries_denied(self, role):
        assert "error" in generate_simulated_entries_api(role, 2026, 7, "EMP-1")

    def test_generate_simulated_entries_delegates(self, monkeypatch):
        captured = {}

        def fake(year, month, generated_by, floorplan_exposure):
            captured.update(year=year, month=month, generated_by=generated_by, floorplan_exposure=floorplan_exposure)
            return {"ok": True}

        monkeypatch.setattr(general_ledger_api, "generate_simulated_entries", fake)
        result = generate_simulated_entries_api(OPERATIONS, 2026, 7, "EMP-1", floorplan_exposure=5000.0)
        assert result == {"ok": True}
        assert captured == {"year": 2026, "month": 7, "generated_by": "EMP-1", "floorplan_exposure": 5000.0}

    @pytest.mark.parametrize("role", _GL_DENIED_ROLES)
    def test_delete_entry_denied(self, role):
        assert "error" in delete_entry_api(role, "GLE-1", "EMP-1")

    def test_delete_entry_delegates(self, monkeypatch):
        monkeypatch.setattr(general_ledger_api, "delete_entry", lambda entry_id, deleted_by: {"deleted": entry_id})
        assert delete_entry_api(ADMIN, "GLE-1", "EMP-1") == {"deleted": "GLE-1"}

    @pytest.mark.parametrize("role", _GL_DENIED_ROLES)
    def test_get_general_ledger_denied(self, role):
        assert "error" in get_general_ledger_api(role)

    def test_get_general_ledger_delegates(self, monkeypatch):
        captured = {}

        def fake(account_number, start_date, end_date, *, limit, offset):
            captured.update(account_number=account_number, start_date=start_date, end_date=end_date, limit=limit, offset=offset)
            return {"entries": []}

        monkeypatch.setattr(general_ledger_api, "get_general_ledger", fake)
        result = get_general_ledger_api(FINANCE, account_number="1000", start_date="2026-01-01", end_date="2026-12-31", limit=25, offset=50)
        assert result == {"entries": []}
        assert captured == {"account_number": "1000", "start_date": "2026-01-01", "end_date": "2026-12-31", "limit": 25, "offset": 50}

    @pytest.mark.parametrize("role", _GL_DENIED_ROLES)
    def test_get_trial_balance_denied(self, role):
        assert "error" in get_trial_balance_api(role)

    def test_get_trial_balance_delegates(self, monkeypatch):
        monkeypatch.setattr(general_ledger_api, "get_trial_balance", lambda start_date, end_date: {"balanced": True})
        assert get_trial_balance_api(ADMIN) == {"balanced": True}

    @pytest.mark.parametrize("role", _GL_DENIED_ROLES)
    def test_get_income_statement_denied(self, role):
        assert "error" in get_income_statement_api(role)

    def test_get_income_statement_delegates(self, monkeypatch):
        monkeypatch.setattr(general_ledger_api, "get_income_statement", lambda start_date, end_date: {"net_income": 0})
        assert get_income_statement_api(OPERATIONS) == {"net_income": 0}

    @pytest.mark.parametrize("role", _GL_DENIED_ROLES)
    def test_get_balance_sheet_denied(self, role):
        assert "error" in get_balance_sheet_api(role)

    def test_get_balance_sheet_delegates(self, monkeypatch):
        monkeypatch.setattr(general_ledger_api, "get_balance_sheet", lambda as_of_date: {"total_assets": 0})
        assert get_balance_sheet_api(FINANCE, as_of_date="2026-07-19") == {"total_assets": 0}


# ---------------------------------------------------------------------------
# smart_audiences_api.py
# ---------------------------------------------------------------------------

import core.smart_audiences_api as smart_audiences_api
from core.smart_audiences_api import (
    get_field_catalog_api,
    list_presets_api,
    preview_preset_api,
    preview_conditions_api,
    create_audience_api,
    delete_audience_api,
    list_audiences_api,
    evaluate_audience_api,
)


class _FakeAudience:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class TestSmartAudiencesApi:

    @pytest.mark.parametrize("role", [SERVICE, FINANCE])
    def test_view_functions_denied_for_disallowed_roles(self, role):
        assert "error" in get_field_catalog_api(role)
        assert "error" in list_presets_api(role)
        assert "error" in preview_preset_api(role, "some_preset")
        assert "error" in preview_conditions_api(role, [])
        assert "error" in list_audiences_api(role)
        assert "error" in evaluate_audience_api(role, "AUD-1")

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, MARKETING])
    def test_get_field_catalog_allowed(self, role):
        result = get_field_catalog_api(role)
        assert "fields" in result and "operators" in result

    def test_list_presets_delegates(self, monkeypatch):
        monkeypatch.setattr(smart_audiences_api, "list_presets", lambda: [{"key": "positive_equity"}])
        result = list_presets_api(SALES)
        assert result == {"presets": [{"key": "positive_equity"}]}

    def test_preview_preset_delegates(self, monkeypatch):
        monkeypatch.setattr(
            smart_audiences_api, "preview_preset",
            lambda preset_key, params: {"preset_key": preset_key, "params": params},
        )
        result = preview_preset_api(MARKETING, "positive_equity", params={"x": 1})
        assert result == {"preset_key": "positive_equity", "params": {"x": 1}}

    def test_preview_conditions_delegates(self, monkeypatch):
        monkeypatch.setattr(smart_audiences_api, "preview_conditions", lambda conditions: {"matches": len(conditions)})
        result = preview_conditions_api(SALES, [{"field": "make"}])
        assert result == {"matches": 1}

    def test_evaluate_audience_delegates(self, monkeypatch):
        monkeypatch.setattr(smart_audiences_api, "evaluate_audience", lambda audience_id: {"audience_id": audience_id})
        assert evaluate_audience_api(OPERATIONS, "AUD-1") == {"audience_id": "AUD-1"}

    @pytest.mark.parametrize("role", [SALES, SERVICE, OPERATIONS])
    def test_create_audience_denied_for_view_only_roles(self, role):
        result = create_audience_api(role, "My Audience", "EMP-1")
        assert result == {"error": "Only Admin or Marketing can create or delete saved Smart Audiences."}

    @pytest.mark.parametrize("role", [ADMIN, MARKETING])
    def test_create_audience_allowed(self, monkeypatch, role):
        captured = {}

        def fake_create(name, created_by, conditions, preset_key, preset_params, description):
            captured.update(
                name=name, created_by=created_by, conditions=conditions,
                preset_key=preset_key, preset_params=preset_params, description=description,
            )
            return {"id": "AUD-1"}

        monkeypatch.setattr(smart_audiences_api, "create_audience", fake_create)
        result = create_audience_api(role, "My Audience", "EMP-1", description="desc")
        assert result == {"id": "AUD-1"}
        assert captured["name"] == "My Audience"
        assert captured["description"] == "desc"

    @pytest.mark.parametrize("role", [SALES, SERVICE, OPERATIONS])
    def test_delete_audience_denied_for_view_only_roles(self, role):
        result = delete_audience_api(role, "AUD-1")
        assert result == {"error": "Only Admin or Marketing can create or delete saved Smart Audiences."}

    def test_delete_audience_allowed_for_admin(self, monkeypatch):
        monkeypatch.setattr(smart_audiences_api, "delete_audience", lambda audience_id: {"deleted": audience_id})
        assert delete_audience_api(ADMIN, "AUD-1") == {"deleted": "AUD-1"}

    def test_list_audiences_serializes_real_attributes(self, monkeypatch):
        fake_audiences = [
            _FakeAudience(
                "AUD-1", name="Truck Owners", description="d", preset_key="truck_owners",
                conditions=None, created_by="EMP-1", created_at="2026-01-01",
            ),
        ]
        monkeypatch.setattr(smart_audiences_api, "list_audiences", lambda: fake_audiences)

        result = list_audiences_api(SALES)

        assert result == {
            "audiences": [
                {
                    "id": "AUD-1",
                    "name": "Truck Owners",
                    "description": "d",
                    "preset_key": "truck_owners",
                    "conditions": None,
                    "created_by": "EMP-1",
                    "created_at": "2026-01-01",
                }
            ]
        }


# ---------------------------------------------------------------------------
# audit_center_api.py
# ---------------------------------------------------------------------------

import core.audit_center_api as audit_center_api
from core.audit_center_api import (
    get_audit_center_overview_api,
    get_event_catalog_api,
    search_audit_log_api,
    get_actor_activity_api,
    get_actor_timeline_api,
    get_suspicious_activity_api,
    export_audit_events_csv_api,
)

_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}
_AC_DENIED_ROLES = [SALES, MARKETING, SERVICE, FINANCE]


class TestAuditCenterApi:

    @pytest.mark.parametrize("role", _AC_DENIED_ROLES)
    def test_get_overview_denied(self, role):
        assert get_audit_center_overview_api(role) == _ADMIN_ONLY_ERROR

    def test_get_overview_delegates(self, monkeypatch):
        monkeypatch.setattr(audit_center_api, "get_audit_center_overview", lambda: {"total_events": 5})
        assert get_audit_center_overview_api(ADMIN) == {"total_events": 5}

    @pytest.mark.parametrize("role", _AC_DENIED_ROLES)
    def test_get_event_catalog_denied(self, role):
        assert get_event_catalog_api(role) == _ADMIN_ONLY_ERROR

    def test_get_event_catalog_delegates(self, monkeypatch):
        monkeypatch.setattr(audit_center_api, "get_event_catalog", lambda: {"categories": []})
        assert get_event_catalog_api(OPERATIONS) == {"categories": []}

    @pytest.mark.parametrize("role", _AC_DENIED_ROLES)
    def test_search_audit_log_denied(self, role):
        assert search_audit_log_api(role) == _ADMIN_ONLY_ERROR

    def test_search_audit_log_delegates_with_kwargs(self, monkeypatch):
        captured = {}

        def fake_search(entity_id, actor, event_type, category, date_from, date_to, query, limit):
            captured.update(
                entity_id=entity_id, actor=actor, event_type=event_type, category=category,
                date_from=date_from, date_to=date_to, query=query, limit=limit,
            )
            return {"events": []}

        monkeypatch.setattr(audit_center_api, "search_audit_log", fake_search)
        result = search_audit_log_api(
            ADMIN, entity_id="LEAD-1", actor="EMP-1", event_type="login_success",
            category="security", date_from="2026-01-01", date_to="2026-12-31", query="text", limit=10,
        )
        assert result == {"events": []}
        assert captured == {
            "entity_id": "LEAD-1", "actor": "EMP-1", "event_type": "login_success",
            "category": "security", "date_from": "2026-01-01", "date_to": "2026-12-31",
            "query": "text", "limit": 10,
        }

    @pytest.mark.parametrize("role", _AC_DENIED_ROLES)
    def test_get_actor_activity_denied(self, role):
        assert get_actor_activity_api(role) == _ADMIN_ONLY_ERROR

    def test_get_actor_activity_delegates(self, monkeypatch):
        monkeypatch.setattr(audit_center_api, "get_actor_activity", lambda limit: {"limit": limit})
        assert get_actor_activity_api(ADMIN, limit=25) == {"limit": 25}

    @pytest.mark.parametrize("role", _AC_DENIED_ROLES)
    def test_get_actor_timeline_denied(self, role):
        assert get_actor_timeline_api(role, "EMP-1") == _ADMIN_ONLY_ERROR

    def test_get_actor_timeline_delegates(self, monkeypatch):
        monkeypatch.setattr(audit_center_api, "get_actor_timeline", lambda actor, limit: {"actor": actor, "limit": limit})
        assert get_actor_timeline_api(OPERATIONS, "EMP-1", limit=50) == {"actor": "EMP-1", "limit": 50}

    @pytest.mark.parametrize("role", _AC_DENIED_ROLES)
    def test_get_suspicious_activity_denied(self, role):
        assert get_suspicious_activity_api(role) == _ADMIN_ONLY_ERROR

    def test_get_suspicious_activity_delegates(self, monkeypatch):
        monkeypatch.setattr(
            audit_center_api, "get_suspicious_activity",
            lambda off_hours_lookback_days: {"days": off_hours_lookback_days},
        )
        assert get_suspicious_activity_api(ADMIN, off_hours_lookback_days=14) == {"days": 14}

    @pytest.mark.parametrize("role", _AC_DENIED_ROLES)
    def test_export_csv_denied_returns_two_tuple(self, role):
        result, error = export_audit_events_csv_api(role)
        assert result is None
        assert error == _ADMIN_ONLY_ERROR

    def test_export_csv_delegates(self, monkeypatch):
        monkeypatch.setattr(
            audit_center_api, "export_audit_events_csv",
            lambda entity_id, actor, event_type, category, date_from, date_to, query: ("csv,data", None),
        )
        result = export_audit_events_csv_api(ADMIN)
        assert result == ("csv,data", None)


# ---------------------------------------------------------------------------
# campaign_analytics_api.py
# ---------------------------------------------------------------------------

import core.campaign_analytics_api as campaign_analytics_api
from core.campaign_analytics_api import (
    set_ab_variant_api,
    clear_ab_variant_api,
    get_campaign_ab_config_api,
    get_ab_test_results_api,
    get_campaign_revenue_api,
    list_merge_fields_api,
    get_merge_values_api,
    render_personalized_api,
)


class _FakeCampaign:
    def __init__(self, created_by):
        self.attributes = {"created_by": created_by}


class _FakeTemplate:
    def __init__(self, created_by):
        self.attributes = {"created_by": created_by}


class TestCampaignAnalyticsApi:

    @pytest.mark.parametrize("role", [SALES, SERVICE, FINANCE, OPERATIONS])
    def test_set_ab_variant_denied_for_non_manage_all_roles(self, role):
        result = set_ab_variant_api(role, "CAMP-1", "TMPL-1")
        assert result == {"error": "You don't have access to configure A/B tests"}

    @pytest.mark.parametrize("role", [ADMIN, MARKETING])
    def test_set_ab_variant_allowed(self, monkeypatch, role):
        monkeypatch.setattr(
            campaign_analytics_api, "set_ab_variant",
            lambda campaign_id, variant_b_template_id: {"campaign_id": campaign_id, "variant": variant_b_template_id},
        )
        result = set_ab_variant_api(role, "CAMP-1", "TMPL-1")
        assert result == {"campaign_id": "CAMP-1", "variant": "TMPL-1"}

    @pytest.mark.parametrize("role", [SALES, SERVICE])
    def test_clear_ab_variant_denied(self, role):
        result = clear_ab_variant_api(role, "CAMP-1")
        assert result == {"error": "You don't have access to configure A/B tests"}

    def test_clear_ab_variant_allowed(self, monkeypatch):
        monkeypatch.setattr(campaign_analytics_api, "clear_ab_variant", lambda campaign_id: {"cleared": campaign_id})
        assert clear_ab_variant_api(ADMIN, "CAMP-1") == {"cleared": "CAMP-1"}

    @pytest.mark.parametrize(
        "fn", [get_campaign_ab_config_api, get_ab_test_results_api, get_campaign_revenue_api],
    )
    def test_campaign_functions_error_when_campaign_missing(self, monkeypatch, fn):
        monkeypatch.setattr(campaign_analytics_api, "get_campaign", lambda campaign_id: None)
        result = fn(ADMIN, "EMP-1", "CAMP-missing")
        assert result == {"error": "Campaign not found"}

    @pytest.mark.parametrize(
        "fn", [get_campaign_ab_config_api, get_ab_test_results_api, get_campaign_revenue_api],
    )
    def test_campaign_functions_denied_to_non_creator_non_manager(self, monkeypatch, fn):
        monkeypatch.setattr(campaign_analytics_api, "get_campaign", lambda campaign_id: _FakeCampaign("EMP-other"))
        result = fn(SALES, "EMP-1", "CAMP-1")
        assert result == {"error": "You don't have access to this campaign"}

    def test_get_campaign_ab_config_allowed_for_creator(self, monkeypatch):
        monkeypatch.setattr(campaign_analytics_api, "get_campaign", lambda campaign_id: _FakeCampaign("EMP-1"))
        monkeypatch.setattr(campaign_analytics_api, "get_campaign_ab_config", lambda campaign_id: {"variant_b": None})
        result = get_campaign_ab_config_api(SALES, "EMP-1", "CAMP-1")
        assert result == {"variant_b": None}

    def test_get_ab_test_results_allowed_for_manager_role(self, monkeypatch):
        monkeypatch.setattr(campaign_analytics_api, "get_campaign", lambda campaign_id: _FakeCampaign("EMP-other"))
        monkeypatch.setattr(campaign_analytics_api, "get_ab_test_results", lambda campaign_id: {"winner": "A"})
        result = get_ab_test_results_api(MARKETING, "EMP-1", "CAMP-1")
        assert result == {"winner": "A"}

    def test_get_campaign_revenue_allowed_for_admin(self, monkeypatch):
        monkeypatch.setattr(campaign_analytics_api, "get_campaign", lambda campaign_id: _FakeCampaign("EMP-other"))
        monkeypatch.setattr(campaign_analytics_api, "get_campaign_revenue", lambda campaign_id: {"revenue": 100})
        result = get_campaign_revenue_api(ADMIN, "EMP-1", "CAMP-1")
        assert result == {"revenue": 100}

    def test_list_merge_fields_delegates_with_no_args(self, monkeypatch):
        monkeypatch.setattr(campaign_analytics_api, "list_merge_fields", lambda: ["first_name"])
        assert list_merge_fields_api() == ["first_name"]

    def test_get_merge_values_has_no_role_gate(self, monkeypatch):
        monkeypatch.setattr(campaign_analytics_api, "get_merge_values", lambda person_id: {"person_id": person_id})
        result = get_merge_values_api(SERVICE, "EMP-1", "CUST-1")
        assert result == {"person_id": "CUST-1"}

    def test_render_personalized_errors_when_template_missing(self, monkeypatch):
        monkeypatch.setattr(campaign_analytics_api, "get_template", lambda template_id: None)
        result = render_personalized_api(ADMIN, "EMP-1", "TMPL-missing", "CUST-1")
        assert result == {"error": "Template not found"}

    def test_render_personalized_denied_to_non_creator_non_manager(self, monkeypatch):
        monkeypatch.setattr(campaign_analytics_api, "get_template", lambda template_id: _FakeTemplate("EMP-other"))
        result = render_personalized_api(SALES, "EMP-1", "TMPL-1", "CUST-1")
        assert result == {"error": "You don't have access to this template"}

    def test_render_personalized_allowed_for_creator(self, monkeypatch):
        monkeypatch.setattr(campaign_analytics_api, "get_template", lambda template_id: _FakeTemplate("EMP-1"))
        monkeypatch.setattr(
            campaign_analytics_api, "render_personalized",
            lambda template_id, person_id: {"html": f"<p>Hi {person_id}</p>"},
        )
        result = render_personalized_api(SALES, "EMP-1", "TMPL-1", "CUST-1")
        assert result == {"html": "<p>Hi CUST-1</p>"}


# ---------------------------------------------------------------------------
# event_planning_api.py
# ---------------------------------------------------------------------------

import core.event_planning_api as event_planning_api
from core.event_planning_api import (
    list_task_statuses_api,
    create_task_api,
    update_task_api,
    update_task_status_api,
    delete_task_api,
    list_tasks_for_event_api,
    get_project_management_summary_api,
    get_event_war_room_api,
)


class _FakeEventTask:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class TestEventPlanningApi:

    def test_list_task_statuses_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(event_planning_api, "TASK_STATUSES", ("open", "done"))
        assert list_task_statuses_api() == ["open", "done"]

    @pytest.mark.parametrize("role", [SERVICE, FINANCE, OPERATIONS])
    def test_create_task_denied_for_non_act_roles(self, role):
        result = create_task_api(role, "EMP-1", "EVT-1", "Book venue")
        assert result == {"error": "Only admin/marketing/sales can create event planning tasks"}

    @pytest.mark.parametrize("role", [ADMIN, MARKETING, SALES])
    def test_create_task_allowed(self, monkeypatch, role):
        monkeypatch.setattr(
            event_planning_api, "create_task",
            lambda event_id, employee_id, title, assignee, due_date, notes: _FakeEventTask(
                "ETASK-1", event_id=event_id, title=title,
            ),
        )
        result = create_task_api(role, "EMP-1", "EVT-1", "Book venue")
        assert result == {"id": "ETASK-1", "event_id": "EVT-1", "title": "Book venue"}

    def test_create_task_passes_through_a_real_error(self, monkeypatch):
        monkeypatch.setattr(
            event_planning_api, "create_task",
            lambda event_id, employee_id, title, assignee, due_date, notes: {"error": "Event not found"},
        )
        result = create_task_api(ADMIN, "EMP-1", "EVT-missing", "Book venue")
        assert result == {"error": "Event not found"}

    def test_update_task_denied(self):
        result = update_task_api(SERVICE, "EMP-1", "ETASK-1", {"title": "New"})
        assert result == {"error": "Only admin/marketing/sales can edit event planning tasks"}

    def test_update_task_allowed(self, monkeypatch):
        monkeypatch.setattr(
            event_planning_api, "update_task",
            lambda task_id, patch: _FakeEventTask("ETASK-1", **patch),
        )
        result = update_task_api(ADMIN, "EMP-1", "ETASK-1", {"title": "New"})
        assert result == {"id": "ETASK-1", "title": "New"}

    def test_update_task_status_denied(self):
        result = update_task_status_api(FINANCE, "EMP-1", "ETASK-1", "done")
        assert result == {"error": "Only admin/marketing/sales can update a task's status"}

    def test_update_task_status_allowed(self, monkeypatch):
        monkeypatch.setattr(
            event_planning_api, "update_task_status",
            lambda task_id, status: _FakeEventTask(task_id, status=status),
        )
        result = update_task_status_api(SALES, "EMP-1", "ETASK-1", "done")
        assert result == {"id": "ETASK-1", "status": "done"}

    def test_delete_task_denied(self):
        result = delete_task_api(SERVICE, "EMP-1", "ETASK-1")
        assert result == {"error": "Only admin/marketing/sales can delete an event planning task"}

    def test_delete_task_allowed_returns_raw_result(self, monkeypatch):
        monkeypatch.setattr(event_planning_api, "delete_task", lambda task_id: {"deleted": task_id})
        result = delete_task_api(MARKETING, "EMP-1", "ETASK-1")
        assert result == {"deleted": "ETASK-1"}

    def test_list_tasks_for_event_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(
            event_planning_api, "list_tasks_for_event",
            lambda event_id, status: [_FakeEventTask("ETASK-1", title="a"), _FakeEventTask("ETASK-2", title="b")],
        )
        result = list_tasks_for_event_api(SERVICE, "EVT-1")
        assert result == [{"id": "ETASK-1", "title": "a"}, {"id": "ETASK-2", "title": "b"}]

    def test_get_project_management_summary_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(
            event_planning_api, "get_project_management_summary",
            lambda event_id: {"event_id": event_id, "completion_pct": 50},
        )
        result = get_project_management_summary_api(FINANCE, "EVT-1")
        assert result == {"event_id": "EVT-1", "completion_pct": 50}

    def test_get_event_war_room_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(event_planning_api, "get_event_war_room", lambda event_id: {"event_id": event_id})
        result = get_event_war_room_api(SERVICE, "EVT-1")
        assert result == {"event_id": "EVT-1"}


# ---------------------------------------------------------------------------
# workflow_automation_api.py
# ---------------------------------------------------------------------------

import core.workflow_automation_api as workflow_automation_api
from core.workflow_automation_api import (
    get_automation_dashboard_api,
    get_automation_catalog_api,
    list_rules_api,
    create_rule_api,
    get_rule_api,
    set_rule_active_api,
    update_rule_api,
    delete_rule_api,
    list_executions_api,
    run_rules_now_api,
)


class _FakeAutomationRule:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


_WFA_DENIED_ROLES = [SALES, MARKETING, SERVICE, FINANCE]


class TestWorkflowAutomationApi:

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_get_dashboard_denied(self, role):
        assert get_automation_dashboard_api(role) == _ADMIN_ONLY_ERROR

    def test_get_dashboard_delegates(self, monkeypatch):
        monkeypatch.setattr(workflow_automation_api, "get_automation_dashboard", lambda run_now: {"run_now": run_now})
        assert get_automation_dashboard_api(ADMIN, run_now=False) == {"run_now": False}

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_get_catalog_denied(self, role):
        assert get_automation_catalog_api(role) == _ADMIN_ONLY_ERROR

    def test_get_catalog_returns_real_constants(self, monkeypatch):
        monkeypatch.setattr(workflow_automation_api, "TRIGGER_CATALOG", {"t1": {}})
        monkeypatch.setattr(workflow_automation_api, "ACTION_CATALOG", {"a1": {}})
        result = get_automation_catalog_api(OPERATIONS)
        assert result == {"triggers": {"t1": {}}, "actions": {"a1": {}}}

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_list_rules_denied(self, role):
        assert list_rules_api(role) == _ADMIN_ONLY_ERROR

    def test_list_rules_serializes_dict_and_entity(self, monkeypatch):
        monkeypatch.setattr(
            workflow_automation_api, "list_rules",
            lambda active_only: [{"id": "AUTOR-1", "active": True}, _FakeAutomationRule("AUTOR-2", active=False)],
        )
        result = list_rules_api(ADMIN, active_only=True)
        assert result == {"rules": [{"id": "AUTOR-1", "active": True}, {"id": "AUTOR-2", "active": False}]}

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_create_rule_denied(self, role):
        assert create_rule_api(role, "EMP-1", "n", "t", {}, "a", {}) == _ADMIN_ONLY_ERROR

    def test_create_rule_delegates_with_kwargs(self, monkeypatch):
        captured = {}

        def fake_create(name, trigger_type, trigger_params, action_type, action_params, created_by, description):
            captured.update(
                name=name, trigger_type=trigger_type, trigger_params=trigger_params,
                action_type=action_type, action_params=action_params, created_by=created_by, description=description,
            )
            return _FakeAutomationRule("AUTOR-1", name=name)

        monkeypatch.setattr(workflow_automation_api, "create_rule", fake_create)
        result = create_rule_api(
            ADMIN, "EMP-1", "My Rule", "deal_stage_stalled", {"days": 3},
            "create_operations_task", {"priority": "high"}, description="desc",
        )
        assert result == {"id": "AUTOR-1", "name": "My Rule"}
        assert captured["created_by"] == "EMP-1"
        assert captured["description"] == "desc"

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_get_rule_denied(self, role):
        assert get_rule_api(role, "AUTOR-1") == _ADMIN_ONLY_ERROR

    def test_get_rule_not_found(self, monkeypatch):
        monkeypatch.setattr(workflow_automation_api, "get_rule", lambda rule_id: None)
        assert get_rule_api(ADMIN, "AUTOR-missing") == {"error": "Rule not found"}

    def test_get_rule_found(self, monkeypatch):
        monkeypatch.setattr(workflow_automation_api, "get_rule", lambda rule_id: _FakeAutomationRule(rule_id, active=True))
        assert get_rule_api(OPERATIONS, "AUTOR-1") == {"id": "AUTOR-1", "active": True}

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_set_rule_active_denied(self, role):
        assert set_rule_active_api(role, "EMP-1", "AUTOR-1", False) == _ADMIN_ONLY_ERROR

    def test_set_rule_active_delegates(self, monkeypatch):
        monkeypatch.setattr(
            workflow_automation_api, "set_rule_active",
            lambda rule_id, is_active, employee_id: _FakeAutomationRule(rule_id, active=is_active),
        )
        result = set_rule_active_api(ADMIN, "EMP-1", "AUTOR-1", False)
        assert result == {"id": "AUTOR-1", "active": False}

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_update_rule_denied(self, role):
        assert update_rule_api(role, "EMP-1", "AUTOR-1") == _ADMIN_ONLY_ERROR

    def test_update_rule_delegates(self, monkeypatch):
        monkeypatch.setattr(
            workflow_automation_api, "update_rule",
            lambda rule_id, employee_id, name, description, trigger_params, action_params: _FakeAutomationRule(
                rule_id, name=name,
            ),
        )
        result = update_rule_api(ADMIN, "EMP-1", "AUTOR-1", name="Renamed")
        assert result == {"id": "AUTOR-1", "name": "Renamed"}

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_delete_rule_denied(self, role):
        assert delete_rule_api(role, "AUTOR-1") == _ADMIN_ONLY_ERROR

    def test_delete_rule_returns_raw_result(self, monkeypatch):
        monkeypatch.setattr(workflow_automation_api, "delete_rule", lambda rule_id: {"deleted": rule_id})
        assert delete_rule_api(ADMIN, "AUTOR-1") == {"deleted": "AUTOR-1"}

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_list_executions_denied(self, role):
        assert list_executions_api(role) == _ADMIN_ONLY_ERROR

    def test_list_executions_serializes(self, monkeypatch):
        monkeypatch.setattr(
            workflow_automation_api, "list_executions",
            lambda rule_id, limit: [_FakeAutomationRule("AUTOX-1", outcome="matched")],
        )
        result = list_executions_api(OPERATIONS, rule_id="AUTOR-1", limit=10)
        assert result == {"executions": [{"id": "AUTOX-1", "outcome": "matched"}]}

    @pytest.mark.parametrize("role", _WFA_DENIED_ROLES)
    def test_run_rules_now_denied(self, role):
        assert run_rules_now_api(role) == _ADMIN_ONLY_ERROR

    def test_run_rules_now_delegates(self, monkeypatch):
        monkeypatch.setattr(workflow_automation_api, "evaluate_rules", lambda rule_id: {"rule_id": rule_id, "matched": 2})
        result = run_rules_now_api(ADMIN, rule_id="AUTOR-1")
        assert result == {"rule_id": "AUTOR-1", "matched": 2}


# ---------------------------------------------------------------------------
# operations_tasks_api.py
# ---------------------------------------------------------------------------

import core.operations_tasks_api as operations_tasks_api
from core.operations_tasks_api import (
    get_catalog_api,
    create_task_api as ot_create_task_api,
    get_task_api,
    update_task_api as ot_update_task_api,
    close_task_api,
    escalate_task_api,
    list_tasks_api,
    get_stats_api,
    bulk_assign_api,
    bulk_close_api,
    bulk_reprioritize_api,
    sync_derived_tasks_api,
)


class _FakeOpsTask:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


_OT_DENIED = {"error": "You don't have access to Operations Tasks"}
_OT_MUTATE_DENIED_ROLES = [SALES, MARKETING, FINANCE]


class TestOperationsTasksApi:

    def test_get_catalog_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(operations_tasks_api, "TASK_TYPES", ["t1"])
        monkeypatch.setattr(operations_tasks_api, "STATUSES", ["open"])
        monkeypatch.setattr(operations_tasks_api, "PRIORITIES", ["high"])
        monkeypatch.setattr(operations_tasks_api, "OWNER_BUCKETS", ["Unassigned"])
        result = get_catalog_api()
        assert result == {
            "task_types": ["t1"], "statuses": ["open"], "priorities": ["high"], "owner_buckets": ["Unassigned"],
        }

    @pytest.mark.parametrize("role", _OT_MUTATE_DENIED_ROLES)
    def test_create_task_denied(self, role):
        assert ot_create_task_api(role, "EMP-1", "custom", "detail") == _OT_DENIED

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SERVICE])
    def test_create_task_allowed(self, monkeypatch, role):
        monkeypatch.setattr(
            operations_tasks_api, "create_task",
            lambda task_type, detail, employee_id, priority, owner_bucket, assigned_to, linked_entity_id: _FakeOpsTask(
                "OTASK-1", task_type=task_type, detail=detail,
            ),
        )
        result = ot_create_task_api(role, "EMP-1", "custom", "Something to do")
        assert result == {"id": "OTASK-1", "task_type": "custom", "detail": "Something to do"}

    def test_create_task_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            operations_tasks_api, "create_task",
            lambda task_type, detail, employee_id, priority, owner_bucket, assigned_to, linked_entity_id: {
                "error": "bad task type",
            },
        )
        result = ot_create_task_api(ADMIN, "EMP-1", "bogus", "detail")
        assert result == {"error": "bad task type"}

    def test_get_task_denied_for_unknown_role(self):
        assert get_task_api("UNKNOWN", "OTASK-1") == _OT_DENIED

    def test_get_task_not_found(self, monkeypatch):
        monkeypatch.setattr(operations_tasks_api, "get_task", lambda task_id: None)
        assert get_task_api(ADMIN, "OTASK-missing") == {"error": "Task not found"}

    def test_get_task_found(self, monkeypatch):
        monkeypatch.setattr(operations_tasks_api, "get_task", lambda task_id: _FakeOpsTask(task_id, status="open"))
        result = get_task_api(SALES, "OTASK-1")
        assert result == {"id": "OTASK-1", "status": "open"}

    @pytest.mark.parametrize("role", _OT_MUTATE_DENIED_ROLES)
    def test_update_task_denied(self, role):
        assert ot_update_task_api(role, "EMP-1", "OTASK-1") == _OT_DENIED

    def test_update_task_allowed(self, monkeypatch):
        monkeypatch.setattr(
            operations_tasks_api, "update_task",
            lambda task_id, employee_id, status, priority, owner_bucket, assigned_to: _FakeOpsTask(
                task_id, status=status,
            ),
        )
        result = ot_update_task_api(OPERATIONS, "EMP-1", "OTASK-1", status="in_progress")
        assert result == {"id": "OTASK-1", "status": "in_progress"}

    @pytest.mark.parametrize("role", _OT_MUTATE_DENIED_ROLES)
    def test_close_task_denied(self, role):
        assert close_task_api(role, "EMP-1", "OTASK-1") == _OT_DENIED

    def test_close_task_allowed(self, monkeypatch):
        monkeypatch.setattr(
            operations_tasks_api, "close_task",
            lambda task_id, employee_id, resolution_notes: _FakeOpsTask(task_id, status="closed"),
        )
        result = close_task_api(SERVICE, "EMP-1", "OTASK-1", resolution_notes="done")
        assert result == {"id": "OTASK-1", "status": "closed"}

    @pytest.mark.parametrize("role", _OT_MUTATE_DENIED_ROLES)
    def test_escalate_task_denied(self, role):
        assert escalate_task_api(role, "EMP-1", "OTASK-1") == _OT_DENIED

    def test_escalate_task_allowed(self, monkeypatch):
        monkeypatch.setattr(
            operations_tasks_api, "escalate_task",
            lambda task_id, employee_id, notes: _FakeOpsTask(task_id, priority="urgent"),
        )
        result = escalate_task_api(ADMIN, "EMP-1", "OTASK-1", notes="going stale")
        assert result == {"id": "OTASK-1", "priority": "urgent"}

    def test_list_tasks_denied_for_unknown_role(self):
        assert list_tasks_api("BOGUS") == _OT_DENIED

    def test_list_tasks_serializes_and_counts(self, monkeypatch):
        monkeypatch.setattr(
            operations_tasks_api, "list_tasks",
            lambda status, owner_bucket, assigned_to, priority, overdue_only: [
                _FakeOpsTask("OTASK-1", status="open"), _FakeOpsTask("OTASK-2", status="open"),
            ],
        )
        result = list_tasks_api(FINANCE, status="open")
        assert result == {
            "tasks": [{"id": "OTASK-1", "status": "open"}, {"id": "OTASK-2", "status": "open"}],
            "count": 2,
        }

    def test_get_stats_denied_for_unknown_role(self):
        assert get_stats_api("BOGUS") == _OT_DENIED

    def test_get_stats_delegates(self, monkeypatch):
        monkeypatch.setattr(operations_tasks_api, "get_stats", lambda: {"open": 3, "closed": 10})
        assert get_stats_api(MARKETING) == {"open": 3, "closed": 10}

    @pytest.mark.parametrize("role", _OT_MUTATE_DENIED_ROLES)
    def test_bulk_assign_denied(self, role):
        assert bulk_assign_api(role, "EMP-1", ["OTASK-1"], "EMP-2", "Recon") == _OT_DENIED

    def test_bulk_assign_mixed_results_pass_through(self, monkeypatch):
        monkeypatch.setattr(
            operations_tasks_api, "bulk_assign",
            lambda task_ids, assigned_to, owner_bucket, employee_id: [
                _FakeOpsTask("OTASK-1", assigned_to=assigned_to), {"error": "not found"},
            ],
        )
        result = bulk_assign_api(ADMIN, "EMP-1", ["OTASK-1", "OTASK-missing"], "EMP-2", "Recon")
        assert result == {"results": [{"id": "OTASK-1", "assigned_to": "EMP-2"}, {"error": "not found"}]}

    @pytest.mark.parametrize("role", _OT_MUTATE_DENIED_ROLES)
    def test_bulk_close_denied(self, role):
        assert bulk_close_api(role, "EMP-1", ["OTASK-1"]) == _OT_DENIED

    def test_bulk_close_allowed(self, monkeypatch):
        monkeypatch.setattr(
            operations_tasks_api, "bulk_close",
            lambda task_ids, employee_id, resolution_notes: [_FakeOpsTask("OTASK-1", status="closed")],
        )
        result = bulk_close_api(SERVICE, "EMP-1", ["OTASK-1"], resolution_notes="batch done")
        assert result == {"results": [{"id": "OTASK-1", "status": "closed"}]}

    @pytest.mark.parametrize("role", _OT_MUTATE_DENIED_ROLES)
    def test_bulk_reprioritize_denied(self, role):
        assert bulk_reprioritize_api(role, "EMP-1", ["OTASK-1"], "urgent") == _OT_DENIED

    def test_bulk_reprioritize_allowed(self, monkeypatch):
        monkeypatch.setattr(
            operations_tasks_api, "bulk_reprioritize",
            lambda task_ids, priority, employee_id: [_FakeOpsTask("OTASK-1", priority=priority)],
        )
        result = bulk_reprioritize_api(OPERATIONS, "EMP-1", ["OTASK-1"], "urgent")
        assert result == {"results": [{"id": "OTASK-1", "priority": "urgent"}]}

    @pytest.mark.parametrize("role", _OT_MUTATE_DENIED_ROLES)
    def test_sync_derived_tasks_denied(self, role):
        assert sync_derived_tasks_api(role) == _OT_DENIED

    def test_sync_derived_tasks_allowed(self, monkeypatch):
        monkeypatch.setattr(operations_tasks_api, "sync_derived_tasks", lambda role: {"created": 5, "role": role})
        result = sync_derived_tasks_api(ADMIN)
        assert result == {"created": 5, "role": ADMIN}


# ---------------------------------------------------------------------------
# appointments_api.py
# ---------------------------------------------------------------------------

import core.appointments_api as appointments_api
from core.appointments_api import (
    list_appointment_types_api,
    list_appointment_statuses_api,
    create_appointment_api,
    get_appointment_api,
    update_appointment_status_api,
    reschedule_appointment_api,
    list_appointments_api,
    list_service_employees_api,
)


class _FakeAppointment:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class TestAppointmentsApi:

    def test_list_appointment_types_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(appointments_api, "APPOINTMENT_TYPES", ["service", "test_drive"])
        assert list_appointment_types_api() == ["service", "test_drive"]

    def test_list_appointment_statuses_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(appointments_api, "STATUSES", ["scheduled", "confirmed"])
        assert list_appointment_statuses_api() == ["scheduled", "confirmed"]

    def test_create_appointment_denied(self):
        result = create_appointment_api(FINANCE, "EMP-1", "Sales", "test_drive", "2026-08-01T10:00:00")
        assert result == {"error": "You don't have access to schedule appointments"}

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING])
    def test_create_appointment_allowed(self, monkeypatch, role):
        monkeypatch.setattr(
            appointments_api, "create_appointment",
            lambda department, appointment_type, scheduled_start, employee_id, assigned_to, customer_id, lead_id, vehicle_id, scheduled_end, notes: _FakeAppointment(
                "APPT-1", department=department, appointment_type=appointment_type,
            ),
        )
        result = create_appointment_api(role, "EMP-1", "Sales", "test_drive", "2026-08-01T10:00:00")
        assert result == {"id": "APPT-1", "department": "Sales", "appointment_type": "test_drive"}

    def test_create_appointment_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            appointments_api, "create_appointment",
            lambda department, appointment_type, scheduled_start, employee_id, assigned_to, customer_id, lead_id, vehicle_id, scheduled_end, notes: {
                "error": "bad appointment type",
            },
        )
        result = create_appointment_api(ADMIN, "EMP-1", "Sales", "bogus", "2026-08-01T10:00:00")
        assert result == {"error": "bad appointment type"}

    def test_get_appointment_denied(self):
        assert get_appointment_api(FINANCE, "APPT-1") == {"error": "You don't have access to appointments"}

    def test_get_appointment_not_found(self, monkeypatch):
        monkeypatch.setattr(appointments_api, "get_appointment", lambda appointment_id: None)
        assert get_appointment_api(ADMIN, "APPT-missing") == {"error": "Appointment not found"}

    def test_get_appointment_found(self, monkeypatch):
        monkeypatch.setattr(
            appointments_api, "get_appointment", lambda appointment_id: _FakeAppointment(appointment_id, status="scheduled"),
        )
        result = get_appointment_api(SALES, "APPT-1")
        assert result == {"id": "APPT-1", "status": "scheduled"}

    def test_update_status_denied(self):
        result = update_appointment_status_api(FINANCE, "EMP-1", "APPT-1", "confirmed")
        assert result == {"error": "You don't have access to update appointments"}

    def test_update_status_allowed(self, monkeypatch):
        monkeypatch.setattr(
            appointments_api, "update_status",
            lambda appointment_id, new_status, employee_id: _FakeAppointment(appointment_id, status=new_status),
        )
        result = update_appointment_status_api(SERVICE, "EMP-1", "APPT-1", "confirmed")
        assert result == {"id": "APPT-1", "status": "confirmed"}

    def test_reschedule_denied(self):
        result = reschedule_appointment_api(FINANCE, "EMP-1", "APPT-1", "2026-08-02T10:00:00")
        assert result == {"error": "You don't have access to reschedule appointments"}

    def test_reschedule_allowed(self, monkeypatch):
        monkeypatch.setattr(
            appointments_api, "reschedule_appointment",
            lambda appointment_id, new_start, employee_id, new_end: _FakeAppointment(appointment_id, scheduled_start=new_start),
        )
        result = reschedule_appointment_api(MARKETING, "EMP-1", "APPT-1", "2026-08-02T10:00:00")
        assert result == {"id": "APPT-1", "scheduled_start": "2026-08-02T10:00:00"}

    def test_list_appointments_denied(self):
        assert list_appointments_api(FINANCE) == {"error": "You don't have access to appointments"}

    def test_list_appointments_default_scope_delegates_to_list_appointments(self, monkeypatch):
        monkeypatch.setattr(
            appointments_api, "list_appointments",
            lambda department, assigned_to, status, appointment_type, linked_entity_id, date: [
                _FakeAppointment("APPT-1"),
            ],
        )
        result = list_appointments_api(ADMIN, department="Sales")
        assert result == [{"id": "APPT-1"}]

    def test_list_appointments_scope_today(self, monkeypatch):
        captured = {}

        def fake_today(department, assigned_to):
            captured["department"] = department
            return [_FakeAppointment("APPT-today")]

        monkeypatch.setattr(appointments_api, "list_todays", fake_today)
        result = list_appointments_api(SALES, department="Sales", scope="today")
        assert result == [{"id": "APPT-today"}]
        assert captured["department"] == "Sales"

    def test_list_appointments_scope_this_week(self, monkeypatch):
        monkeypatch.setattr(
            appointments_api, "list_this_week",
            lambda department, assigned_to: [_FakeAppointment("APPT-week")],
        )
        result = list_appointments_api(SERVICE, scope="this_week")
        assert result == [{"id": "APPT-week"}]

    def test_list_appointments_scope_upcoming_defaults_hours_to_2(self, monkeypatch):
        captured = {}

        def fake_upcoming(hours, department, assigned_to):
            captured["hours"] = hours
            return [_FakeAppointment("APPT-soon")]

        monkeypatch.setattr(appointments_api, "list_upcoming_within", fake_upcoming)
        result = list_appointments_api(MARKETING, scope="upcoming")
        assert result == [{"id": "APPT-soon"}]
        assert captured["hours"] == 2

    def test_list_appointments_scope_upcoming_honors_explicit_hours(self, monkeypatch):
        captured = {}

        def fake_upcoming(hours, department, assigned_to):
            captured["hours"] = hours
            return []

        monkeypatch.setattr(appointments_api, "list_upcoming_within", fake_upcoming)
        list_appointments_api(OPERATIONS, scope="upcoming", hours=6)
        assert captured["hours"] == 6

    def test_list_service_employees_denied(self):
        assert list_service_employees_api(SALES) == {"error": "You don't have access to the employee roster"}
        assert list_service_employees_api(MARKETING) == {"error": "You don't have access to the employee roster"}
        assert list_service_employees_api(FINANCE) == {"error": "You don't have access to the employee roster"}

    def test_list_service_employees_filters_by_department(self):
        ledger.add_entity(Entity(
            id="EMP-1", entity_type="Employee",
            attributes={"FirstName": "Jane", "LastName": "Tech", "Title": "Technician", "Department": " Service "},
        ))
        ledger.add_entity(Entity(
            id="EMP-2", entity_type="Employee",
            attributes={"FirstName": "Bob", "LastName": "Sales", "Title": "Salesperson", "Department": "Sales"},
        ))
        result = list_service_employees_api(ADMIN)
        assert result == [{"id": "EMP-1", "name": "Jane Tech", "title": "Technician"}]


# ---------------------------------------------------------------------------
# social_posts_api.py
# ---------------------------------------------------------------------------

import core.social_posts_api as social_posts_api
from core.social_posts_api import (
    list_platforms_api,
    create_post_api,
    get_post_api,
    update_post_api,
    publish_post_api,
    cancel_post_api,
    list_posts_api,
    get_calendar_api,
    search_inventory_for_post_api,
    generate_caption_api,
)


class _FakePost:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class TestSocialPostsApi:

    def test_list_platforms_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "list_platforms", lambda: ["instagram", "facebook"])
        assert list_platforms_api() == ["instagram", "facebook"]

    def test_create_post_has_no_role_param_and_delegates(self, monkeypatch):
        captured = {}

        def fake_create(employee_id, platform, content, media_url, linked_vehicle_ids, scheduled_time, target_date):
            captured.update(employee_id=employee_id, platform=platform, content=content)
            return _FakePost("SP-1", platform=platform)

        monkeypatch.setattr(social_posts_api, "create_post", fake_create)
        result = create_post_api("EMP-1", "instagram", "Check out this truck!")
        assert result == {"id": "SP-1", "platform": "instagram"}
        assert captured["employee_id"] == "EMP-1"

    def test_create_post_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(
            social_posts_api, "create_post",
            lambda employee_id, platform, content, media_url, linked_vehicle_ids, scheduled_time, target_date: {
                "error": "bad platform",
            },
        )
        result = create_post_api("EMP-1", "bogus", "content")
        assert result == {"error": "bad platform"}

    def test_get_post_not_found(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: None)
        assert get_post_api(SALES, "EMP-1", "SP-missing") == {"error": "Post not found"}

    def test_get_post_found_includes_linked_vehicles(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: _FakePost(post_id, content="hi"))
        monkeypatch.setattr(social_posts_api, "resolve_linked_vehicles", lambda post_id: [{"id": "VEH-1"}])
        result = get_post_api(SALES, "EMP-1", "SP-1")
        assert result == {"id": "SP-1", "content": "hi", "linked_vehicles": [{"id": "VEH-1"}]}

    def test_update_post_not_found(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: None)
        assert update_post_api(ADMIN, "EMP-1", "SP-missing", {}) == {"error": "Post not found"}

    def test_update_post_denied_to_non_creator_non_marketing_admin(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: _FakePost(post_id, created_by="EMP-owner"))
        result = update_post_api(SALES, "EMP-other", "SP-1", {"content": "edited"})
        assert result == {"error": "Only the creator (or marketing/admin) can edit this post"}

    def test_update_post_allowed_to_creator(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: _FakePost(post_id, created_by="EMP-owner"))
        monkeypatch.setattr(
            social_posts_api, "update_post",
            lambda post_id, patch: _FakePost(post_id, created_by="EMP-owner", content=patch.get("content")),
        )
        result = update_post_api(SALES, "EMP-owner", "SP-1", {"content": "edited"})
        assert result == {"id": "SP-1", "created_by": "EMP-owner", "content": "edited"}

    def test_update_post_allowed_to_marketing_even_if_not_creator(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: _FakePost(post_id, created_by="EMP-owner"))
        monkeypatch.setattr(social_posts_api, "update_post", lambda post_id, patch: _FakePost(post_id, content="edited"))
        result = update_post_api(MARKETING, "EMP-other", "SP-1", {"content": "edited"})
        assert result == {"id": "SP-1", "content": "edited"}

    def test_update_post_defaults_none_patch_to_empty_dict(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: _FakePost(post_id, created_by="EMP-1"))

        def fake_update(post_id, patch):
            captured["patch"] = patch
            return _FakePost(post_id)

        monkeypatch.setattr(social_posts_api, "update_post", fake_update)
        update_post_api(SALES, "EMP-1", "SP-1", None)
        assert captured["patch"] == {}

    def test_publish_post_denied_before_lookup(self, monkeypatch):
        # role gate must fire before get_post is even called
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: (_ for _ in ()).throw(AssertionError("should not be called")))
        result = publish_post_api(SALES, "EMP-1", "SP-1")
        assert result == {"error": "Only marketing/admin can publish a post"}

    def test_publish_post_not_found(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: None)
        assert publish_post_api(ADMIN, "EMP-1", "SP-missing") == {"error": "Post not found"}

    @pytest.mark.parametrize("role", [ADMIN, MARKETING])
    def test_publish_post_allowed(self, monkeypatch, role):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: _FakePost(post_id))
        monkeypatch.setattr(social_posts_api, "publish_post", lambda post_id: _FakePost(post_id, status="published"))
        result = publish_post_api(role, "EMP-1", "SP-1")
        assert result == {"id": "SP-1", "status": "published"}

    def test_publish_post_real_error_passes_through(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: _FakePost(post_id))
        monkeypatch.setattr(social_posts_api, "publish_post", lambda post_id: {"error": "already published"})
        result = publish_post_api(ADMIN, "EMP-1", "SP-1")
        assert result == {"error": "already published"}

    def test_cancel_post_not_found(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: None)
        assert cancel_post_api(ADMIN, "EMP-1", "SP-missing") == {"error": "Post not found"}

    def test_cancel_post_denied_to_non_creator_non_marketing_admin(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: _FakePost(post_id, created_by="EMP-owner"))
        result = cancel_post_api(SALES, "EMP-other", "SP-1")
        assert result == {"error": "Only the creator (or marketing/admin) can cancel this post"}

    def test_cancel_post_allowed_to_creator(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_post", lambda post_id: _FakePost(post_id, created_by="EMP-owner"))
        monkeypatch.setattr(social_posts_api, "cancel_post", lambda post_id: _FakePost(post_id, status="cancelled"))
        result = cancel_post_api(SALES, "EMP-owner", "SP-1")
        assert result == {"id": "SP-1", "status": "cancelled"}

    def test_list_posts_has_no_gate_and_scopes_mine_only(self, monkeypatch):
        captured = {}

        def fake_list(platform, status, created_by):
            captured.update(platform=platform, status=status, created_by=created_by)
            return [_FakePost("SP-1")]

        monkeypatch.setattr(social_posts_api, "list_posts", fake_list)
        result = list_posts_api(SERVICE, "EMP-1", mine_only=True)
        assert result == [{"id": "SP-1"}]
        assert captured["created_by"] == "EMP-1"

    def test_list_posts_not_mine_only_passes_none_created_by(self, monkeypatch):
        captured = {}

        def fake_list(platform, status, created_by):
            captured["created_by"] = created_by
            return []

        monkeypatch.setattr(social_posts_api, "list_posts", fake_list)
        list_posts_api(FINANCE, "EMP-1", mine_only=False)
        assert captured["created_by"] is None

    def test_get_calendar_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "get_calendar", lambda start_date, end_date: {"days": []})
        assert get_calendar_api(SALES, "EMP-1") == {"days": []}

    def test_search_inventory_for_post_has_no_gate(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "search_inventory_for_post", lambda query: [{"id": "VEH-1"}])
        assert search_inventory_for_post_api(MARKETING, "EMP-1", query="truck") == [{"id": "VEH-1"}]

    def test_generate_caption_unknown_platform_rejected(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "list_platforms", lambda: ["instagram"])
        result = generate_caption_api(SALES, "EMP-1", "bogus_platform")
        assert result == {"error": "Unknown platform 'bogus_platform'"}

    def test_generate_caption_real_ai_result(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "list_platforms", lambda: ["instagram"])
        monkeypatch.setattr(
            social_posts_api, "generate_caption",
            lambda platform, goal, tone, vehicle: {"caption": "Real AI caption"},
        )
        result = generate_caption_api(MARKETING, "EMP-1", "instagram", goal="drive traffic")
        assert result == {"caption": "Real AI caption", "ai_generated": True}

    def test_generate_caption_falls_back_on_ai_error(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "list_platforms", lambda: ["instagram"])
        monkeypatch.setattr(social_posts_api, "generate_caption", lambda platform, goal, tone, vehicle: {"error": "no network"})
        monkeypatch.setattr(
            social_posts_api, "fallback_caption",
            lambda platform, goal, vehicle: {"caption": "Fallback caption"},
        )
        result = generate_caption_api(ADMIN, "EMP-1", "instagram")
        assert result == {"caption": "Fallback caption", "ai_generated": False}

    def test_generate_caption_resolves_vehicle_when_id_given(self, monkeypatch):
        monkeypatch.setattr(social_posts_api, "list_platforms", lambda: ["instagram"])
        monkeypatch.setattr(social_posts_api, "get_vehicle_brief", lambda vehicle_id: {"id": vehicle_id, "make": "Ford"})
        captured = {}

        def fake_generate(platform, goal, tone, vehicle):
            captured["vehicle"] = vehicle
            return {"caption": "grounded caption"}

        monkeypatch.setattr(social_posts_api, "generate_caption", fake_generate)
        generate_caption_api(SALES, "EMP-1", "instagram", vehicle_id="VEH-1")
        assert captured["vehicle"] == {"id": "VEH-1", "make": "Ford"}


# ---------------------------------------------------------------------------
# permissions_registry_api.py
# ---------------------------------------------------------------------------

import core.permissions_registry_api as permissions_registry_api
from core.permissions_registry_api import (
    list_permission_catalog_api,
    get_effective_permissions_api,
    list_overrides_for_employee_api,
    list_all_overrides_api,
    set_override_api,
    revoke_override_api,
    list_approval_chains_api,
    create_approval_request_api,
    approve_step_api,
    reject_step_api,
    cancel_request_api,
    get_approval_request_api,
    list_approval_requests_api,
    get_tier_distribution_api,
)

_PR_ADMIN_ONLY_ERROR = {"error": "Admin/Operations role required."}
_PR_FORBIDDEN = {"error": "You don't have access to this action."}
_PR_NON_ADMIN_ROLES = [SALES, MARKETING, SERVICE, FINANCE]


class TestPermissionsRegistryApi:

    @pytest.mark.parametrize("role", _PR_NON_ADMIN_ROLES)
    def test_list_permission_catalog_denied(self, role):
        assert list_permission_catalog_api(role) == _PR_ADMIN_ONLY_ERROR

    def test_list_permission_catalog_allowed(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "list_permission_catalog", lambda: {"deals.fund": {}})
        assert list_permission_catalog_api(OPERATIONS) == {"deals.fund": {}}

    def test_get_effective_permissions_self_view_always_allowed(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "get_effective_permissions", lambda role, target: ["deals.view"])
        result = get_effective_permissions_api(SALES, "EMP-1")
        assert result == {"employee_id": "EMP-1", "permissions": ["deals.view"]}

    @pytest.mark.parametrize("role", _PR_NON_ADMIN_ROLES)
    def test_get_effective_permissions_other_employee_denied_for_non_admin(self, role):
        result = get_effective_permissions_api(role, "EMP-1", target_employee_id="EMP-2")
        assert result == _PR_ADMIN_ONLY_ERROR

    def test_get_effective_permissions_other_employee_allowed_for_admin(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "get_effective_permissions", lambda role, target: ["deals.fund"])
        result = get_effective_permissions_api(ADMIN, "EMP-1", target_employee_id="EMP-2")
        assert result == {"employee_id": "EMP-2", "permissions": ["deals.fund"]}

    def test_list_overrides_for_employee_self_view_allowed(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "list_overrides_for_employee", lambda target: [{"id": "PERM-1"}])
        result = list_overrides_for_employee_api(SALES, "EMP-1")
        assert result == {"employee_id": "EMP-1", "overrides": [{"id": "PERM-1"}]}

    @pytest.mark.parametrize("role", _PR_NON_ADMIN_ROLES)
    def test_list_overrides_for_employee_other_denied_for_non_admin(self, role):
        result = list_overrides_for_employee_api(role, "EMP-1", target_employee_id="EMP-2")
        assert result == _PR_ADMIN_ONLY_ERROR

    def test_list_overrides_for_employee_other_allowed_for_operations(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "list_overrides_for_employee", lambda target: [])
        result = list_overrides_for_employee_api(OPERATIONS, "EMP-1", target_employee_id="EMP-2")
        assert result == {"employee_id": "EMP-2", "overrides": []}

    @pytest.mark.parametrize("role", _PR_NON_ADMIN_ROLES)
    def test_list_all_overrides_denied(self, role):
        assert list_all_overrides_api(role) == _PR_ADMIN_ONLY_ERROR

    def test_list_all_overrides_allowed(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "list_all_overrides", lambda: [{"id": "PERM-1"}])
        assert list_all_overrides_api(ADMIN) == {"overrides": [{"id": "PERM-1"}]}

    @pytest.mark.parametrize("role", [OPERATIONS] + _PR_NON_ADMIN_ROLES)
    def test_set_override_denied_to_everyone_but_admin(self, role):
        # note: OPERATIONS is in _ADMIN_ROLES for viewing but NOT for this stricter
        # ADMIN-only mutate gate -- confirms the narrower check.
        result = set_override_api(role, "EMP-1", "EMP-2", "deals.fund", True)
        assert result == {"error": "Only ADMIN can grant or revoke a permission override."}

    def test_set_override_allowed_for_admin(self, monkeypatch):
        monkeypatch.setattr(
            permissions_registry_api, "set_override",
            lambda target, key, granted, granted_by, reason: {"id": "PERM-1", "granted": granted},
        )
        result = set_override_api(ADMIN, "EMP-1", "EMP-2", "deals.fund", True, reason="temp coverage")
        assert result == {"id": "PERM-1", "granted": True}

    @pytest.mark.parametrize("role", [OPERATIONS] + _PR_NON_ADMIN_ROLES)
    def test_revoke_override_denied_to_everyone_but_admin(self, role):
        result = revoke_override_api(role, "EMP-1", "PERM-1")
        assert result == {"error": "Only ADMIN can grant or revoke a permission override."}

    def test_revoke_override_allowed_for_admin(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "revoke_override", lambda override_id, actor: {"id": override_id, "active": False})
        result = revoke_override_api(ADMIN, "EMP-1", "PERM-1")
        assert result == {"id": "PERM-1", "active": False}

    def test_list_approval_chains_denied_for_unknown_role(self):
        assert list_approval_chains_api("BOGUS") == _PR_FORBIDDEN

    def test_list_approval_chains_allowed_for_every_real_role(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "list_approval_chains", lambda: {"expense_request": {}})
        for role in _ALL_REAL_ROLES:
            assert list_approval_chains_api(role) == {"chains": {"expense_request": {}}}

    def test_create_approval_request_denied_for_unknown_role(self):
        assert create_approval_request_api("BOGUS", "EMP-1", "expense_request", "subj") == _PR_FORBIDDEN

    def test_create_approval_request_delegates(self, monkeypatch):
        monkeypatch.setattr(
            permissions_registry_api, "create_approval_request",
            lambda chain_key, employee_id, subject, details, entity_id: {"id": "APPR-1", "subject": subject},
        )
        result = create_approval_request_api(SALES, "EMP-1", "expense_request", "New laptop")
        assert result == {"id": "APPR-1", "subject": "New laptop"}

    def test_approve_step_denied_for_unknown_role(self):
        assert approve_step_api("BOGUS", "EMP-1", "APPR-1") == _PR_FORBIDDEN

    def test_approve_step_delegates(self, monkeypatch):
        monkeypatch.setattr(
            permissions_registry_api, "approve_step",
            lambda request_id, employee_id, note: {"id": request_id, "status": "approved"},
        )
        result = approve_step_api(OPERATIONS, "EMP-1", "APPR-1", note="looks good")
        assert result == {"id": "APPR-1", "status": "approved"}

    def test_reject_step_denied_for_unknown_role(self):
        assert reject_step_api("BOGUS", "EMP-1", "APPR-1", "reason") == _PR_FORBIDDEN

    def test_reject_step_delegates(self, monkeypatch):
        monkeypatch.setattr(
            permissions_registry_api, "reject_step",
            lambda request_id, employee_id, reason: {"id": request_id, "status": "rejected", "reason": reason},
        )
        result = reject_step_api(FINANCE, "EMP-1", "APPR-1", "over budget")
        assert result == {"id": "APPR-1", "status": "rejected", "reason": "over budget"}

    def test_cancel_request_denied_for_unknown_role(self):
        assert cancel_request_api("BOGUS", "EMP-1", "APPR-1") == _PR_FORBIDDEN

    def test_cancel_request_delegates(self, monkeypatch):
        monkeypatch.setattr(
            permissions_registry_api, "cancel_request",
            lambda request_id, employee_id: {"id": request_id, "status": "cancelled"},
        )
        result = cancel_request_api(MARKETING, "EMP-1", "APPR-1")
        assert result == {"id": "APPR-1", "status": "cancelled"}

    def test_get_approval_request_denied_for_unknown_role(self):
        assert get_approval_request_api("BOGUS", "APPR-1") == _PR_FORBIDDEN

    def test_get_approval_request_delegates(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "get_approval_request", lambda request_id: {"id": request_id})
        assert get_approval_request_api(SERVICE, "APPR-1") == {"id": "APPR-1"}

    def test_list_approval_requests_denied_for_unknown_role(self):
        assert list_approval_requests_api("BOGUS", "EMP-1") == _PR_FORBIDDEN

    def test_list_approval_requests_admin_default_sees_everything(self, monkeypatch):
        captured = {}

        def fake_list(status=None, requested_by=None, pending_for_employee=None):
            captured.update(status=status, requested_by=requested_by, pending_for_employee=pending_for_employee)
            return [{"id": "APPR-1"}]

        monkeypatch.setattr(permissions_registry_api, "list_approval_requests", fake_list)
        result = list_approval_requests_api(ADMIN, "EMP-1")
        assert result == {"requests": [{"id": "APPR-1"}]}
        assert captured == {"status": None, "requested_by": None, "pending_for_employee": None}

    def test_list_approval_requests_admin_with_mine_only_scopes_by_requester(self, monkeypatch):
        captured = {}

        def fake_list(status=None, requested_by=None, pending_for_employee=None):
            captured.update(requested_by=requested_by, pending_for_employee=pending_for_employee)
            return []

        monkeypatch.setattr(permissions_registry_api, "list_approval_requests", fake_list)
        list_approval_requests_api(ADMIN, "EMP-1", mine_only=True)
        assert captured == {"requested_by": "EMP-1", "pending_for_employee": None}

    def test_list_approval_requests_non_admin_scopes_by_pending_for_me(self, monkeypatch):
        captured = {}

        def fake_list(status=None, requested_by=None, pending_for_employee=None):
            captured.update(requested_by=requested_by, pending_for_employee=pending_for_employee)
            return []

        monkeypatch.setattr(permissions_registry_api, "list_approval_requests", fake_list)
        list_approval_requests_api(SALES, "EMP-1", pending_for_me=True)
        assert captured == {"requested_by": None, "pending_for_employee": "EMP-1"}

    @pytest.mark.parametrize("role", _PR_NON_ADMIN_ROLES)
    def test_get_tier_distribution_denied(self, role):
        assert get_tier_distribution_api(role) == _PR_ADMIN_ONLY_ERROR

    def test_get_tier_distribution_allowed(self, monkeypatch):
        monkeypatch.setattr(permissions_registry_api, "get_tier_distribution", lambda: {"staff": 40, "manager": 5})
        assert get_tier_distribution_api(OPERATIONS) == {"staff": 40, "manager": 5}


_ALL_REAL_ROLES = [ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE]


# ---------------------------------------------------------------------------
# marketing_lists_api.py
# ---------------------------------------------------------------------------

import core.marketing_lists_api as marketing_lists_api
from core.marketing_lists_api import (
    create_list_api,
    build_list_from_pool_api,
    get_list_api,
    list_lists_api,
    get_list_members_api,
    update_list_api,
    add_members_api,
    remove_members_api,
    delete_list_api,
)


class _FakeMarketingList:
    def __init__(self, id, **attrs):
        self.id = id
        self.attributes = attrs


class TestMarketingListsApi:

    def test_create_list_has_no_role_param_and_delegates(self, monkeypatch):
        captured = {}

        def fake_create(name, employee_id, description):
            captured.update(name=name, employee_id=employee_id, description=description)
            return _FakeMarketingList("MLIST-1", name=name)

        monkeypatch.setattr(marketing_lists_api, "create_list", fake_create)
        result = create_list_api("EMP-1", "  Hot Leads  ", description="warm prospects")
        assert result == {"id": "MLIST-1", "name": "Hot Leads"}
        assert captured["name"] == "Hot Leads"

    def test_create_list_empty_name_rejected(self):
        assert create_list_api("EMP-1", "") == {"error": "A list needs a name."}

    def test_create_list_whitespace_only_name_rejected(self):
        assert create_list_api("EMP-1", "   ") == {"error": "A list needs a name."}

    def test_create_list_none_name_rejected(self):
        assert create_list_api("EMP-1", None) == {"error": "A list needs a name."}

    def test_build_list_from_pool_has_no_role_param(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_campaign_type", lambda key: {"key": key})
        monkeypatch.setattr(
            marketing_lists_api, "build_list_from_pool",
            lambda name, employee_id, campaign_type_key, params, description: _FakeMarketingList(
                "MLIST-1", name=name, campaign_type_key=campaign_type_key,
            ),
        )
        result = build_list_from_pool_api("EMP-1", "  Retention Pool  ", "retention", {"days": 90})
        assert result == {"id": "MLIST-1", "name": "Retention Pool", "campaign_type_key": "retention"}

    def test_build_list_from_pool_empty_name_rejected(self):
        assert build_list_from_pool_api("EMP-1", "", "retention", {}) == {"error": "A list needs a name."}

    def test_build_list_from_pool_unknown_campaign_type_rejected(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_campaign_type", lambda key: None)
        result = build_list_from_pool_api("EMP-1", "My List", "bogus_type", {})
        assert result == {"error": "Unknown campaign type 'bogus_type'"}

    def test_build_list_from_pool_none_params_defaults_to_empty_dict(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(marketing_lists_api, "get_campaign_type", lambda key: {"key": key})

        def fake_build(name, employee_id, campaign_type_key, params, description):
            captured["params"] = params
            return _FakeMarketingList("MLIST-1")

        monkeypatch.setattr(marketing_lists_api, "build_list_from_pool", fake_build)
        build_list_from_pool_api("EMP-1", "Name", "retention", None)
        assert captured["params"] == {}

    def test_get_list_not_found(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: None)
        assert get_list_api(SALES, "EMP-1", "MLIST-missing") == {"error": "List not found"}

    def test_get_list_found_no_ownership_gate(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, name="X"))
        # any real role can view, regardless of who created it
        result = get_list_api(SERVICE, "EMP-other", "MLIST-1")
        assert result == {"id": "MLIST-1", "name": "X"}

    def test_list_lists_has_no_gate_and_scopes_mine_only(self, monkeypatch):
        captured = {}

        def fake_list_lists(created_by=None):
            captured["created_by"] = created_by
            return [_FakeMarketingList("MLIST-1")]

        monkeypatch.setattr(marketing_lists_api, "list_lists", fake_list_lists)
        result = list_lists_api(FINANCE, "EMP-1", mine_only=True)
        assert result == [{"id": "MLIST-1"}]
        assert captured["created_by"] == "EMP-1"

    def test_get_list_members_not_found(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: None)
        assert get_list_members_api(SALES, "EMP-1", "MLIST-missing") == {"error": "List not found"}

    def test_get_list_members_found_delegates(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id))
        monkeypatch.setattr(
            marketing_lists_api, "get_list_members",
            lambda list_id, page, page_size, entity_type_filter: {"members": [], "page": page, "page_size": page_size},
        )
        result = get_list_members_api(MARKETING, "EMP-1", "MLIST-1", page=2, page_size=10)
        assert result == {"members": [], "page": 2, "page_size": 10}

    def test_update_list_not_found(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: None)
        assert update_list_api(ADMIN, "EMP-1", "MLIST-missing", {}) == {"error": "List not found"}

    def test_update_list_denied_to_non_creator_non_marketing_admin(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        result = update_list_api(SALES, "EMP-other", "MLIST-1", {"name": "New Name"})
        assert result == {"error": "Only the creator (or marketing/admin) can edit this list"}

    def test_update_list_allowed_to_creator(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        monkeypatch.setattr(
            marketing_lists_api, "update_list",
            lambda list_id, patch: _FakeMarketingList(list_id, created_by="EMP-owner", name=patch.get("name")),
        )
        result = update_list_api(SALES, "EMP-owner", "MLIST-1", {"name": "New Name"})
        assert result == {"id": "MLIST-1", "created_by": "EMP-owner", "name": "New Name"}

    def test_update_list_allowed_to_marketing_even_if_not_creator(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        monkeypatch.setattr(marketing_lists_api, "update_list", lambda list_id, patch: _FakeMarketingList(list_id, name="Edited"))
        result = update_list_api(MARKETING, "EMP-other", "MLIST-1", {"name": "Edited"})
        assert result == {"id": "MLIST-1", "name": "Edited"}

    def test_add_members_not_found(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: None)
        assert add_members_api(ADMIN, "EMP-1", "MLIST-missing", []) == {"error": "List not found"}

    def test_add_members_denied_to_non_creator_non_marketing_admin(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        result = add_members_api(SALES, "EMP-other", "MLIST-1", ["CUST-1"])
        assert result == {"error": "Only the creator (or marketing/admin) can edit this list"}

    def test_add_members_allowed_returns_list_and_added(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        monkeypatch.setattr(
            marketing_lists_api, "add_members",
            lambda list_id, entity_ids: {"list": _FakeMarketingList(list_id, member_count=3), "added": entity_ids},
        )
        result = add_members_api(ADMIN, "EMP-1", "MLIST-1", ["CUST-1", "CUST-2"])
        assert result == {"list": {"id": "MLIST-1", "member_count": 3}, "added": ["CUST-1", "CUST-2"]}

    def test_add_members_defaults_none_entity_ids_to_empty_list(self, monkeypatch):
        captured = {}
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-1"))

        def fake_add(list_id, entity_ids):
            captured["entity_ids"] = entity_ids
            return {"list": _FakeMarketingList(list_id), "added": []}

        monkeypatch.setattr(marketing_lists_api, "add_members", fake_add)
        add_members_api(ADMIN, "EMP-1", "MLIST-1", None)
        assert captured["entity_ids"] == []

    def test_remove_members_not_found(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: None)
        assert remove_members_api(ADMIN, "EMP-1", "MLIST-missing", []) == {"error": "List not found"}

    def test_remove_members_denied_to_non_creator_non_marketing_admin(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        result = remove_members_api(SALES, "EMP-other", "MLIST-1", ["CUST-1"])
        assert result == {"error": "Only the creator (or marketing/admin) can edit this list"}

    def test_remove_members_allowed(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        monkeypatch.setattr(
            marketing_lists_api, "remove_members",
            lambda list_id, entity_ids: _FakeMarketingList(list_id, member_count=1),
        )
        result = remove_members_api(SALES, "EMP-owner", "MLIST-1", ["CUST-2"])
        assert result == {"id": "MLIST-1", "member_count": 1}

    def test_delete_list_not_found(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: None)
        assert delete_list_api(ADMIN, "EMP-1", "MLIST-missing") == {"error": "List not found"}

    def test_delete_list_denied_to_non_creator_non_marketing_admin(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        result = delete_list_api(SALES, "EMP-other", "MLIST-1")
        assert result == {"error": "Only the creator (or marketing/admin) can archive this list"}

    def test_delete_list_allowed_to_creator(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        monkeypatch.setattr(marketing_lists_api, "delete_list", lambda list_id: _FakeMarketingList(list_id, status="archived"))
        result = delete_list_api(SALES, "EMP-owner", "MLIST-1")
        assert result == {"id": "MLIST-1", "status": "archived"}

    def test_delete_list_allowed_to_admin_even_if_not_creator(self, monkeypatch):
        monkeypatch.setattr(marketing_lists_api, "get_list", lambda list_id: _FakeMarketingList(list_id, created_by="EMP-owner"))
        monkeypatch.setattr(marketing_lists_api, "delete_list", lambda list_id: _FakeMarketingList(list_id, status="archived"))
        result = delete_list_api(ADMIN, "EMP-other", "MLIST-1")
        assert result == {"id": "MLIST-1", "status": "archived"}
