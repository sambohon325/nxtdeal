"""
Tests for a third batch of small `_api.py` wrapper modules -- each is a thin
pass-through / ACL layer over its own already-larger delegate module, same
"batch several thin wrappers into one combined test file" precedent as
test_routing_api.py / test_opportunities_api.py / test_thin_wrapper_batch_2.py
(task #220). Every delegate function is monkeypatched at its own importing
module's namespace (top-level `from X import Y` binding), matching this
codebase's established top-level-vs-deferred-import monkeypatch targeting
rule -- no real ledger fixtures are needed for most of these, since they
contain no business logic of their own beyond validation/role-gating and
delegation. core/lead_pipeline_api.py is the one exception with real branching
logic (role denial, lead-not-found, missing-pipeline-state auto-creation,
same-state no-op, successful advance, ValueError-caught-and-reshaped) and
gets a real ledger fixture + a real Lead entity.

Covers:
    core/ai_management_api.py
    core/marketing_attribution_api.py
    core/data_backup_api.py
    core/readiness_overview_api.py
    core/inventory_syndication_api.py
    core/network_overview_api.py
    core/lead_pipeline_api.py
    core/bank_reconciliation_api.py
    core/marketing_studio_api.py
    core/appointment_scheduling_api.py
    core/asset_management_api.py
    core/reputation_api.py
    core/operations_scheduling_api.py

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE
from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD

import core.ai_management_api as ai_management_api
from core.ai_management_api import (
    get_ai_management_overview_api,
    get_ai_feature_catalog_api,
    get_ai_call_stats_api,
    set_ai_feature_enabled_api,
)

import core.marketing_attribution_api as marketing_attribution_api
from core.marketing_attribution_api import (
    get_channel_mix_api,
    get_marketing_roi_dashboard_api,
    get_vehicle_attribution_api,
)

import core.data_backup_api as data_backup_api
from core.data_backup_api import (
    list_exportable_entity_types_api,
    export_entity_type_csv_api,
    create_backup_api,
    list_backups_api,
    restore_backup_api,
)

import core.readiness_overview_api as readiness_overview_api
from core.readiness_overview_api import (
    get_enterprise_readiness_overview_api,
    get_department_heatmap_api,
    regenerate_executive_summary_api,
)

import core.inventory_syndication_api as inventory_syndication_api
from core.inventory_syndication_api import (
    get_catalog_api as get_syndication_catalog_api,
    get_syndication_overview_api,
    get_feed_health_rollup_api,
    get_syndication_lead_performance_api,
    republish_platform_api,
)

import core.network_overview_api as network_overview_api
from core.network_overview_api import (
    get_dollar_gaps_api,
    get_department_dollar_opportunities_api,
    get_total_identified_opportunity_api,
    get_largest_opportunities_api,
    regenerate_network_summary_api,
)

import core.lead_pipeline_api as lead_pipeline_api
from core.lead_pipeline_api import list_pipeline_states_api, advance_lead_pipeline_api

import core.bank_reconciliation_api as bank_reconciliation_api
from core.bank_reconciliation_api import (
    generate_simulated_bank_feed_api,
    get_reconciliation_status_api,
    confirm_match_api,
    mark_transaction_reviewed_api,
    list_transactions_api,
)

import core.marketing_studio_api as marketing_studio_api
from core.marketing_studio_api import (
    get_studio_overview_api,
    list_content_drafts_api,
    generate_content_api,
    mark_applied_api,
    mark_discarded_api,
)

import core.appointment_scheduling_api as appointment_scheduling_api
from core.appointment_scheduling_api import (
    get_capacity_planning_api,
    suggest_assignee_api,
    send_appointment_reminder_api,
    get_reminder_history_api,
    generate_checkin_link_api,
    get_checkin_link_status_api,
    revoke_checkin_link_api,
)

import core.asset_management_api as asset_management_api
from core.asset_management_api import (
    get_lien_status_api,
    update_lienholder_api,
    release_lien_api,
    get_insurance_status_api,
    update_insurance_api,
    get_collateral_valuation_api,
    get_asset_summary_api,
    get_asset_portfolio_dashboard_api,
)

import core.reputation_api as reputation_api
from core.reputation_api import (
    get_reputation_summary_api,
    list_reviews_api,
    list_bad_review_alerts_api,
    respond_to_review_api,
    auto_respond_review_api,
    get_competitor_tracking_api,
)

import core.operations_scheduling_api as operations_scheduling_api
from core.operations_scheduling_api import (
    get_recon_schedule_api,
    schedule_recon_api,
    get_delivery_risk_board_api,
    schedule_delivery_api,
    get_transport_schedule_api,
    update_transport_status_api,
)


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


# ---------------------------------------------------------------------------
# core/ai_management_api.py -- ADMIN/OPERATIONS-only throughout
# ---------------------------------------------------------------------------

class TestAiManagementApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS])
    def test_overview_allowed_roles(self, monkeypatch, role):
        monkeypatch.setattr(ai_management_api, "get_ai_management_overview", lambda r: {"ok": True, "role": r})
        result = get_ai_management_overview_api(role)
        assert result == {"ok": True, "role": role}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE, FINANCE])
    def test_overview_denied_roles(self, role):
        result = get_ai_management_overview_api(role)
        assert result == {"error": "Admin/Operations role required."}

    def test_feature_catalog_denied_for_sales(self):
        result = get_ai_feature_catalog_api(SALES)
        assert "error" in result

    def test_feature_catalog_allowed_for_admin(self):
        result = get_ai_feature_catalog_api(ADMIN)
        assert "features" in result

    def test_call_stats_denied_for_marketing(self):
        result = get_ai_call_stats_api(MARKETING)
        assert "error" in result

    def test_call_stats_allowed_for_operations(self, monkeypatch):
        monkeypatch.setattr(ai_management_api, "get_call_stats", lambda feature_key=None: {"feature_key": feature_key})
        result = get_ai_call_stats_api(OPERATIONS, feature_key="ai_assistant")
        assert result == {"stats": {"feature_key": "ai_assistant"}}

    def test_set_feature_enabled_denied_for_finance(self):
        result = set_ai_feature_enabled_api(FINANCE, "EMP-1", "ai_assistant", True)
        assert "error" in result

    def test_set_feature_enabled_delegates_for_admin(self, monkeypatch):
        monkeypatch.setattr(
            ai_management_api, "set_feature_enabled",
            lambda feature_key, enabled, employee_id: {"feature_key": feature_key, "enabled": enabled, "by": employee_id},
        )
        result = set_ai_feature_enabled_api(ADMIN, "EMP-1", "ai_assistant", False)
        assert result == {"feature_key": "ai_assistant", "enabled": False, "by": "EMP-1"}


# ---------------------------------------------------------------------------
# core/marketing_attribution_api.py -- ADMIN/OPERATIONS/MARKETING
# ---------------------------------------------------------------------------

class TestMarketingAttributionApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, MARKETING])
    def test_channel_mix_allowed_roles(self, monkeypatch, role):
        monkeypatch.setattr(marketing_attribution_api, "get_channel_mix", lambda: {"ok": True})
        assert get_channel_mix_api(role) == {"ok": True}

    @pytest.mark.parametrize("role", [SALES, SERVICE, FINANCE])
    def test_channel_mix_denied_roles(self, role):
        result = get_channel_mix_api(role)
        assert "error" in result
        assert "attribution data" in result["error"]

    def test_roi_dashboard_delegates(self, monkeypatch):
        monkeypatch.setattr(marketing_attribution_api, "get_marketing_roi_dashboard", lambda: {"roi": 1.5})
        assert get_marketing_roi_dashboard_api(ADMIN) == {"roi": 1.5}

    def test_roi_dashboard_denied(self):
        assert "error" in get_marketing_roi_dashboard_api(SALES)

    def test_vehicle_attribution_delegates(self, monkeypatch):
        monkeypatch.setattr(marketing_attribution_api, "get_vehicle_attribution", lambda: {"vehicles": []})
        assert get_vehicle_attribution_api(MARKETING) == {"vehicles": []}

    def test_vehicle_attribution_denied(self):
        assert "error" in get_vehicle_attribution_api(FINANCE)


# ---------------------------------------------------------------------------
# core/data_backup_api.py -- ADMIN/OPERATIONS, restore is ADMIN-only
# ---------------------------------------------------------------------------

class TestDataBackupApi:

    def test_list_exportable_types_denied(self):
        result = list_exportable_entity_types_api(SALES)
        assert result == {"error": "Admin/Operations role required."}

    def test_list_exportable_types_allowed(self, monkeypatch):
        monkeypatch.setattr(data_backup_api, "list_exportable_entity_types", lambda: ["Vehicle", "Lead"])
        result = list_exportable_entity_types_api(OPERATIONS)
        assert result == {"entity_types": ["Vehicle", "Lead"]}

    def test_export_csv_denied_returns_two_tuple(self):
        content, error = export_entity_type_csv_api(SALES, "Vehicle")
        assert content is None
        assert error == {"error": "Admin/Operations role required."}

    def test_export_csv_allowed_delegates(self, monkeypatch):
        monkeypatch.setattr(data_backup_api, "export_entity_type_csv", lambda entity_type: ("csv,data", None))
        result = export_entity_type_csv_api(ADMIN, "Vehicle")
        assert result == ("csv,data", None)

    def test_create_backup_denied(self):
        result = create_backup_api(SALES, "EMP-1", label="test")
        assert "error" in result

    def test_create_backup_allowed(self, monkeypatch):
        monkeypatch.setattr(data_backup_api, "create_backup", lambda employee_id, label="": {"employee_id": employee_id, "label": label})
        result = create_backup_api(OPERATIONS, "EMP-1", label="nightly")
        assert result == {"employee_id": "EMP-1", "label": "nightly"}

    def test_list_backups_denied(self):
        assert "error" in list_backups_api(FINANCE)

    def test_list_backups_allowed(self, monkeypatch):
        monkeypatch.setattr(data_backup_api, "list_backups", lambda: [{"id": "BAK-1"}])
        assert list_backups_api(ADMIN) == {"backups": [{"id": "BAK-1"}]}

    def test_restore_backup_denied_for_operations(self):
        # restore is ADMIN-only, stricter than every other function in this module
        result = restore_backup_api(OPERATIONS, "EMP-1", "BAK-1")
        assert result == {"error": "Only ADMIN can restore a backup."}

    def test_restore_backup_allowed_for_admin(self, monkeypatch):
        monkeypatch.setattr(data_backup_api, "restore_backup", lambda backup_id, employee_id: {"restored": backup_id, "by": employee_id})
        result = restore_backup_api(ADMIN, "EMP-1", "BAK-1")
        assert result == {"restored": "BAK-1", "by": "EMP-1"}


# ---------------------------------------------------------------------------
# core/readiness_overview_api.py -- open to all 6 roles
# ---------------------------------------------------------------------------

class TestReadinessOverviewApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_overview_allowed_for_every_role(self, monkeypatch, role):
        monkeypatch.setattr(readiness_overview_api, "get_enterprise_readiness_overview", lambda r, polish_summary=True: {"role": r})
        assert get_enterprise_readiness_overview_api(role) == {"role": role}

    def test_overview_denied_for_unknown_role(self):
        result = get_enterprise_readiness_overview_api("NOT_A_ROLE")
        assert result == {"error": "You don't have access to the Readiness Overview."}

    def test_heatmap_delegates(self, monkeypatch):
        monkeypatch.setattr(readiness_overview_api, "get_department_heatmap", lambda: {"sales": 90})
        assert get_department_heatmap_api(SALES) == {"sales": 90}

    def test_regenerate_summary_defaults_polish_true(self, monkeypatch):
        captured = {}

        def fake_generate(role, polish=True):
            captured["role"] = role
            captured["polish"] = polish
            return {"summary": "ok"}

        monkeypatch.setattr(readiness_overview_api, "generate_executive_summary", fake_generate)
        result = regenerate_executive_summary_api(ADMIN)
        assert result == {"summary": "ok"}
        assert captured["polish"] is True

    def test_regenerate_summary_polish_false_forwarded(self, monkeypatch):
        captured = {}

        def fake_generate(role, polish=True):
            captured["polish"] = polish
            return {}

        monkeypatch.setattr(readiness_overview_api, "generate_executive_summary", fake_generate)
        regenerate_executive_summary_api(ADMIN, polish=False)
        assert captured["polish"] is False

    def test_regenerate_summary_denied(self):
        result = regenerate_executive_summary_api("BOGUS")
        assert "error" in result


# ---------------------------------------------------------------------------
# core/inventory_syndication_api.py
# ---------------------------------------------------------------------------

class TestInventorySyndicationApi:

    def test_catalog_no_role_gate_returns_real_platforms(self):
        # imports FEED_PLATFORMS directly from core.merchandising -- real constant
        result = get_syndication_catalog_api()
        assert "feed_platforms" in result
        assert isinstance(result["feed_platforms"], list)
        assert len(result["feed_platforms"]) > 0

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE])
    def test_overview_allowed_for_every_role(self, monkeypatch, role):
        monkeypatch.setattr(inventory_syndication_api, "get_syndication_overview", lambda: {"ok": True})
        assert get_syndication_overview_api(role) == {"ok": True}

    def test_overview_denied_for_unknown_role(self):
        result = get_syndication_overview_api("BOGUS")
        assert result == {"error": "You don't have access to Inventory Syndication"}

    def test_feed_health_delegates(self, monkeypatch):
        monkeypatch.setattr(inventory_syndication_api, "get_feed_health_rollup", lambda: {"platforms": []})
        assert get_feed_health_rollup_api(ADMIN) == {"platforms": []}

    def test_lead_performance_delegates(self, monkeypatch):
        monkeypatch.setattr(inventory_syndication_api, "get_syndication_lead_performance", lambda: {"leads": 0})
        assert get_syndication_lead_performance_api(SERVICE) == {"leads": 0}

    def test_republish_denied_for_sales(self):
        result = republish_platform_api(SALES, "EMP-1", "Cars.com")
        assert "error" in result

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, MARKETING])
    def test_republish_allowed_roles(self, monkeypatch, role):
        monkeypatch.setattr(
            inventory_syndication_api, "republish_platform",
            lambda platform, employee_id: {"platform": platform, "by": employee_id},
        )
        result = republish_platform_api(role, "EMP-1", "Cars.com")
        assert result == {"platform": "Cars.com", "by": "EMP-1"}


# ---------------------------------------------------------------------------
# core/network_overview_api.py -- ADMIN/OPERATIONS/FINANCE
# ---------------------------------------------------------------------------

class TestNetworkOverviewApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, FINANCE])
    def test_dollar_gaps_allowed(self, monkeypatch, role):
        monkeypatch.setattr(network_overview_api, "get_dollar_denominated_gaps", lambda r: {"role": r})
        assert get_dollar_gaps_api(role) == {"role": role}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE])
    def test_dollar_gaps_denied(self, role):
        result = get_dollar_gaps_api(role)
        assert "error" in result
        assert "Admin, Operations, or Finance" in result["error"]

    def test_department_dollar_opportunities_delegates(self, monkeypatch):
        monkeypatch.setattr(network_overview_api, "get_department_dollar_opportunities", lambda r: {"dept": "sales"})
        assert get_department_dollar_opportunities_api(FINANCE) == {"dept": "sales"}

    def test_total_identified_opportunity_delegates(self, monkeypatch):
        monkeypatch.setattr(network_overview_api, "get_total_identified_opportunity", lambda r: {"total": 100000})
        assert get_total_identified_opportunity_api(ADMIN) == {"total": 100000}

    def test_largest_opportunities_default_limit(self, monkeypatch):
        captured = {}

        def fake_largest(role, limit=5):
            captured["limit"] = limit
            return []

        monkeypatch.setattr(network_overview_api, "get_largest_opportunities", fake_largest)
        get_largest_opportunities_api(OPERATIONS)
        assert captured["limit"] == 5

    def test_largest_opportunities_custom_limit_forwarded(self, monkeypatch):
        captured = {}

        def fake_largest(role, limit=5):
            captured["limit"] = limit
            return []

        monkeypatch.setattr(network_overview_api, "get_largest_opportunities", fake_largest)
        get_largest_opportunities_api(OPERATIONS, limit=10)
        assert captured["limit"] == 10

    def test_regenerate_summary_defaults_polish_true(self, monkeypatch):
        captured = {}

        def fake_generate(role, polish=True):
            captured["polish"] = polish
            return {}

        monkeypatch.setattr(network_overview_api, "generate_executive_summary", fake_generate)
        regenerate_network_summary_api(ADMIN)
        assert captured["polish"] is True

    def test_regenerate_summary_denied(self):
        result = regenerate_network_summary_api(SALES)
        assert "error" in result


# ---------------------------------------------------------------------------
# core/lead_pipeline_api.py -- real branching logic, real ledger fixture
# ---------------------------------------------------------------------------

class TestLeadPipelineApi:

    def test_list_pipeline_states_returns_real_workflow_keys(self):
        result = list_pipeline_states_api()
        assert isinstance(result, list)
        assert "NEW" in result
        assert "CONTACTED" in result

    @pytest.mark.parametrize("role", [SERVICE, FINANCE])
    def test_advance_denied_for_disallowed_roles(self, role):
        result = advance_lead_pipeline_api(role, "EMP-1", "LEAD-00001", "CONTACTED")
        assert result == {"error": "You don't have access to move leads through the pipeline"}

    def test_advance_lead_not_found(self):
        result = advance_lead_pipeline_api(ADMIN, "EMP-1", "LEAD-DOES-NOT-EXIST", "CONTACTED")
        assert result == {"error": "Lead not found"}

    def test_advance_wrong_entity_type_rejected(self):
        ledger.add_entity(Entity(id="VEH-00001", entity_type="Vehicle", attributes={}))
        result = advance_lead_pipeline_api(ADMIN, "EMP-1", "VEH-00001", "CONTACTED")
        assert result == {"error": "Lead not found"}

    def test_advance_creates_pipeline_state_when_missing(self, monkeypatch):
        ledger.add_entity(Entity(id="LEAD-00001", entity_type=LEAD, attributes={}))

        monkeypatch.setattr(lead_pipeline_api, "get_pipeline_state", lambda lead_id: None)
        monkeypatch.setattr(lead_pipeline_api, "create_lead_workflow", lambda lead_id: "NEW")
        monkeypatch.setattr(lead_pipeline_api, "advance_lead_workflow", lambda lead_id, next_state: "CONTACTED")

        result = advance_lead_pipeline_api(SALES, "EMP-1", "LEAD-00001", "CONTACTED")
        assert result == {"lead_id": "LEAD-00001", "previous_state": "NEW", "state": "CONTACTED"}

    def test_advance_same_state_is_a_noop(self, monkeypatch):
        ledger.add_entity(Entity(id="LEAD-00002", entity_type=LEAD, attributes={}))
        monkeypatch.setattr(lead_pipeline_api, "get_pipeline_state", lambda lead_id: "CONTACTED")

        result = advance_lead_pipeline_api(MARKETING, "EMP-1", "LEAD-00002", "CONTACTED")
        assert result == {"lead_id": "LEAD-00002", "previous_state": "CONTACTED", "state": "CONTACTED"}

    def test_advance_successful_transition(self, monkeypatch):
        ledger.add_entity(Entity(id="LEAD-00003", entity_type=LEAD, attributes={}))
        monkeypatch.setattr(lead_pipeline_api, "get_pipeline_state", lambda lead_id: "NEW")
        monkeypatch.setattr(lead_pipeline_api, "advance_lead_workflow", lambda lead_id, next_state: "CONTACTED")

        result = advance_lead_pipeline_api(OPERATIONS, "EMP-1", "LEAD-00003", "CONTACTED")
        assert result == {"lead_id": "LEAD-00003", "previous_state": "NEW", "state": "CONTACTED"}

    def test_advance_invalid_transition_reshapes_value_error(self, monkeypatch):
        ledger.add_entity(Entity(id="LEAD-00004", entity_type=LEAD, attributes={}))
        monkeypatch.setattr(lead_pipeline_api, "get_pipeline_state", lambda lead_id: "NEW")

        def raise_value_error(lead_id, next_state):
            raise ValueError("cannot skip states")

        monkeypatch.setattr(lead_pipeline_api, "advance_lead_workflow", raise_value_error)

        result = advance_lead_pipeline_api(ADMIN, "EMP-1", "LEAD-00004", "SOLD")
        assert result["error"] == "cannot skip states"
        assert result["current_state"] == "NEW"
        # get_next_states is the real function -- NEW's real real next state is CONTACTED
        assert result["valid_next_states"] == ["CONTACTED"]


# ---------------------------------------------------------------------------
# core/bank_reconciliation_api.py -- ADMIN/OPERATIONS/FINANCE
# ---------------------------------------------------------------------------

class TestBankReconciliationApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, FINANCE])
    def test_generate_feed_allowed(self, monkeypatch, role):
        monkeypatch.setattr(bank_reconciliation_api, "generate_simulated_bank_feed", lambda by, start, end: {"by": by})
        result = generate_simulated_bank_feed_api(role, "EMP-1")
        assert result == {"by": "EMP-1"}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE])
    def test_generate_feed_denied(self, role):
        result = generate_simulated_bank_feed_api(role, "EMP-1")
        assert "error" in result

    def test_reconciliation_status_delegates(self, monkeypatch):
        monkeypatch.setattr(bank_reconciliation_api, "get_reconciliation_status", lambda start, end: {"matched": 5})
        assert get_reconciliation_status_api(FINANCE) == {"matched": 5}

    def test_confirm_match_delegates(self, monkeypatch):
        monkeypatch.setattr(
            bank_reconciliation_api, "confirm_match",
            lambda txn_id, gl_id, by: {"txn": txn_id, "gl": gl_id, "by": by},
        )
        result = confirm_match_api(ADMIN, "TXN-1", "GLE-1", "EMP-1")
        assert result == {"txn": "TXN-1", "gl": "GLE-1", "by": "EMP-1"}

    def test_confirm_match_denied(self):
        assert "error" in confirm_match_api(SALES, "TXN-1", "GLE-1", "EMP-1")

    def test_mark_reviewed_default_note(self, monkeypatch):
        captured = {}

        def fake_mark(txn_id, by, note):
            captured["note"] = note
            return {}

        monkeypatch.setattr(bank_reconciliation_api, "mark_transaction_reviewed", fake_mark)
        mark_transaction_reviewed_api(OPERATIONS, "TXN-1", "EMP-1")
        assert captured["note"] == ""

    def test_list_transactions_delegates(self, monkeypatch):
        monkeypatch.setattr(bank_reconciliation_api, "list_transactions", lambda status, start, end: [{"id": "TXN-1"}])
        result = list_transactions_api(FINANCE, status="unmatched")
        assert result == {"transactions": [{"id": "TXN-1"}]}


# ---------------------------------------------------------------------------
# core/marketing_studio_api.py -- ADMIN/MARKETING
# ---------------------------------------------------------------------------

class TestMarketingStudioApi:

    @pytest.mark.parametrize("role", [ADMIN, MARKETING])
    def test_overview_allowed(self, monkeypatch, role):
        monkeypatch.setattr(marketing_studio_api, "get_studio_overview", lambda: {"drafts": 0})
        assert get_studio_overview_api(role) == {"drafts": 0}

    @pytest.mark.parametrize("role", [SALES, OPERATIONS, SERVICE, FINANCE])
    def test_overview_denied(self, role):
        result = get_studio_overview_api(role)
        assert "error" in result
        assert "AI Marketing Studio" in result["error"]

    def test_list_drafts_serializes_each_via_draft_brief(self, monkeypatch):
        monkeypatch.setattr(marketing_studio_api, "list_content_drafts", lambda content_type=None, status=None, created_by=None: ["raw1", "raw2"])
        monkeypatch.setattr(marketing_studio_api, "_draft_brief", lambda d: {"brief": d})
        result = list_content_drafts_api(ADMIN)
        assert result == {"drafts": [{"brief": "raw1"}, {"brief": "raw2"}]}

    def test_list_drafts_denied(self):
        assert "error" in list_content_drafts_api(SALES)

    def test_generate_content_denied(self):
        result = generate_content_api(SALES, "email_copy", {}, "EMP-1")
        assert "error" in result
        assert "Admin or Marketing" in result["error"]

    def test_generate_content_serializes_via_draft_brief(self, monkeypatch):
        monkeypatch.setattr(marketing_studio_api, "generate_content", lambda content_type, params, created_by: "raw_draft")
        monkeypatch.setattr(marketing_studio_api, "_draft_brief", lambda d: {"content_type": "email_copy", "raw": d})
        result = generate_content_api(MARKETING, "email_copy", {"tone": "friendly"}, "EMP-1")
        assert result == {"content_type": "email_copy", "raw": "raw_draft"}

    def test_generate_content_error_passthrough_skips_draft_brief(self, monkeypatch):
        monkeypatch.setattr(marketing_studio_api, "generate_content", lambda content_type, params, created_by: {"error": "unsupported content type"})
        monkeypatch.setattr(marketing_studio_api, "_draft_brief", lambda d: pytest.fail("should not be called on an error result"))
        result = generate_content_api(ADMIN, "bogus_type", {}, "EMP-1")
        assert result == {"error": "unsupported content type"}

    def test_mark_applied_denied(self):
        assert "error" in mark_applied_api(SALES, "MCD-1", "EMP-1")

    def test_mark_applied_serializes(self, monkeypatch):
        monkeypatch.setattr(marketing_studio_api, "mark_applied", lambda draft_id, by: "raw")
        monkeypatch.setattr(marketing_studio_api, "_draft_brief", lambda d: {"status": "applied"})
        result = mark_applied_api(ADMIN, "MCD-1", "EMP-1")
        assert result == {"status": "applied"}

    def test_mark_discarded_denied(self):
        assert "error" in mark_discarded_api(OPERATIONS, "MCD-1", "EMP-1")

    def test_mark_discarded_serializes(self, monkeypatch):
        monkeypatch.setattr(marketing_studio_api, "mark_discarded", lambda draft_id, by: "raw")
        monkeypatch.setattr(marketing_studio_api, "_draft_brief", lambda d: {"status": "discarded"})
        result = mark_discarded_api(MARKETING, "MCD-1", "EMP-1")
        assert result == {"status": "discarded"}


# ---------------------------------------------------------------------------
# core/appointment_scheduling_api.py
# ---------------------------------------------------------------------------

class TestAppointmentSchedulingApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, SERVICE, FINANCE])
    def test_capacity_planning_allowed(self, monkeypatch, role):
        monkeypatch.setattr(appointment_scheduling_api, "get_capacity_planning", lambda dept, date=None: {"dept": dept})
        assert get_capacity_planning_api(role, "Sales") == {"dept": "Sales"}

    def test_capacity_planning_denied_for_marketing(self):
        # MARKETING is excluded entirely from _VIEW_ROLES in this module
        result = get_capacity_planning_api(MARKETING, "Sales")
        assert "error" in result

    def test_suggest_assignee_delegates(self, monkeypatch):
        monkeypatch.setattr(appointment_scheduling_api, "suggest_assignee", lambda dept, date=None: {"suggested": "EMP-1"})
        assert suggest_assignee_api(SERVICE, "Service") == {"suggested": "EMP-1"}

    def test_send_reminder_denied_for_finance(self):
        # FINANCE can view but not mutate in this module
        result = send_appointment_reminder_api(FINANCE, "EMP-1", "APPT-1", "sms")
        assert "error" in result

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, SERVICE])
    def test_send_reminder_allowed(self, monkeypatch, role):
        monkeypatch.setattr(
            appointment_scheduling_api, "send_appointment_reminder",
            lambda appt_id, channel, sent_by: {"appt": appt_id, "channel": channel, "by": sent_by},
        )
        result = send_appointment_reminder_api(role, "EMP-1", "APPT-1", "sms")
        assert result == {"appt": "APPT-1", "channel": "sms", "by": "EMP-1"}

    def test_reminder_history_delegates(self, monkeypatch):
        monkeypatch.setattr(appointment_scheduling_api, "get_reminder_history", lambda appt_id: [{"channel": "email"}])
        assert get_reminder_history_api(ADMIN, "APPT-1") == [{"channel": "email"}]

    def test_generate_checkin_link_denied(self):
        result = generate_checkin_link_api(FINANCE, "EMP-1", "APPT-1")
        assert "error" in result

    def test_generate_checkin_link_allowed(self, monkeypatch):
        monkeypatch.setattr(appointment_scheduling_api, "generate_checkin_link", lambda appt_id, created_by: {"token": "abc123"})
        result = generate_checkin_link_api(SALES, "EMP-1", "APPT-1")
        assert result == {"token": "abc123"}

    def test_checkin_link_status_delegates(self, monkeypatch):
        monkeypatch.setattr(appointment_scheduling_api, "get_checkin_link_status", lambda appt_id: {"revoked": False})
        assert get_checkin_link_status_api(SERVICE, "APPT-1") == {"revoked": False}

    def test_revoke_checkin_link_denied(self):
        result = revoke_checkin_link_api(MARKETING, "EMP-1", "APPT-1")
        assert "error" in result

    def test_revoke_checkin_link_allowed(self, monkeypatch):
        monkeypatch.setattr(appointment_scheduling_api, "revoke_checkin_link", lambda appt_id, revoked_by: {"revoked": True})
        result = revoke_checkin_link_api(OPERATIONS, "EMP-1", "APPT-1")
        assert result == {"revoked": True}


# ---------------------------------------------------------------------------
# core/asset_management_api.py -- ADMIN/OPERATIONS/FINANCE throughout
# ---------------------------------------------------------------------------

class TestAssetManagementApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, FINANCE])
    def test_lien_status_allowed(self, monkeypatch, role):
        monkeypatch.setattr(asset_management_api, "get_lien_status", lambda loan_id: {"loan_id": loan_id})
        assert get_lien_status_api(role, "FIN-00001") == {"loan_id": "FIN-00001"}

    @pytest.mark.parametrize("role", [SALES, MARKETING, SERVICE])
    def test_lien_status_denied(self, role):
        result = get_lien_status_api(role, "FIN-00001")
        assert "error" in result

    def test_update_lienholder_delegates(self, monkeypatch):
        monkeypatch.setattr(
            asset_management_api, "update_lienholder",
            lambda loan_id, name, by: {"loan_id": loan_id, "lienholder": name, "by": by},
        )
        result = update_lienholder_api(ADMIN, "EMP-1", "FIN-00001", "Chase Auto")
        assert result == {"loan_id": "FIN-00001", "lienholder": "Chase Auto", "by": "EMP-1"}

    def test_update_lienholder_denied(self):
        assert "error" in update_lienholder_api(SALES, "EMP-1", "FIN-00001", "Chase Auto")

    def test_release_lien_default_reason(self, monkeypatch):
        captured = {}

        def fake_release(loan_id, by, reason=""):
            captured["reason"] = reason
            return {}

        monkeypatch.setattr(asset_management_api, "release_lien", fake_release)
        release_lien_api(OPERATIONS, "EMP-1", "FIN-00001")
        assert captured["reason"] == ""

    def test_release_lien_denied(self):
        assert "error" in release_lien_api(SERVICE, "EMP-1", "FIN-00001")

    def test_insurance_status_delegates(self, monkeypatch):
        monkeypatch.setattr(asset_management_api, "get_insurance_status", lambda loan_id: {"carrier": "Geico"})
        assert get_insurance_status_api(FINANCE, "FIN-00001") == {"carrier": "Geico"}

    def test_update_insurance_full_args_forwarded(self, monkeypatch):
        captured = {}

        def fake_update(loan_id, carrier, policy_number, expiration_date, loss_payee_confirmed, employee_id):
            captured.update(locals())
            return {"ok": True}

        monkeypatch.setattr(asset_management_api, "update_insurance", fake_update)
        result = update_insurance_api(ADMIN, "EMP-1", "FIN-00001", "Geico", "POL-1", "2027-01-01", True)
        assert result == {"ok": True}
        assert captured["loan_id"] == "FIN-00001"
        assert captured["carrier"] == "Geico"
        assert captured["employee_id"] == "EMP-1"

    def test_update_insurance_denied(self):
        result = update_insurance_api(MARKETING, "EMP-1", "FIN-00001", "Geico", "POL-1", "2027-01-01", True)
        assert "error" in result

    def test_collateral_valuation_delegates(self, monkeypatch):
        monkeypatch.setattr(asset_management_api, "get_collateral_valuation", lambda loan_id: {"ltv": 0.85})
        assert get_collateral_valuation_api(ADMIN, "FIN-00001") == {"ltv": 0.85}

    def test_asset_summary_delegates(self, monkeypatch):
        monkeypatch.setattr(asset_management_api, "get_asset_summary", lambda loan_id: {"title": "on_file"})
        assert get_asset_summary_api(OPERATIONS, "FIN-00001") == {"title": "on_file"}

    def test_portfolio_dashboard_delegates(self, monkeypatch):
        monkeypatch.setattr(asset_management_api, "get_asset_portfolio_dashboard", lambda: {"loans": 315})
        assert get_asset_portfolio_dashboard_api(FINANCE) == {"loans": 315}

    def test_portfolio_dashboard_denied(self):
        assert "error" in get_asset_portfolio_dashboard_api(SALES)


# ---------------------------------------------------------------------------
# core/reputation_api.py -- broad viewing, ADMIN/MARKETING for responding
# ---------------------------------------------------------------------------

class TestReputationApi:

    def test_summary_no_role_gate(self, monkeypatch):
        monkeypatch.setattr(reputation_api, "get_reputation_summary", lambda role: {"role": role})
        assert get_reputation_summary_api(SALES) == {"role": SALES}

    def test_list_reviews_no_role_gate_and_serializes(self, monkeypatch):
        class FakeReview:
            def __init__(self, rid, rating):
                self.id = rid
                self.attributes = {"rating": rating}

        monkeypatch.setattr(
            reputation_api, "list_reviews",
            lambda platform=None, responded=None, max_rating=None: [FakeReview("REV-1", 2)],
        )
        result = list_reviews_api(SERVICE)
        assert result == [{"id": "REV-1", "rating": 2}]

    def test_list_reviews_responded_string_true_converted_to_bool(self, monkeypatch):
        captured = {}

        def fake_list(platform=None, responded=None, max_rating=None):
            captured["responded"] = responded
            return []

        monkeypatch.setattr(reputation_api, "list_reviews", fake_list)
        list_reviews_api(ADMIN, responded="true")
        assert captured["responded"] is True

    def test_list_reviews_responded_string_false_converted_to_bool(self, monkeypatch):
        captured = {}

        def fake_list(platform=None, responded=None, max_rating=None):
            captured["responded"] = responded
            return []

        monkeypatch.setattr(reputation_api, "list_reviews", fake_list)
        list_reviews_api(ADMIN, responded="false")
        assert captured["responded"] is False

    def test_list_reviews_responded_none_stays_none(self, monkeypatch):
        captured = {}

        def fake_list(platform=None, responded=None, max_rating=None):
            captured["responded"] = responded
            return []

        monkeypatch.setattr(reputation_api, "list_reviews", fake_list)
        list_reviews_api(ADMIN)
        assert captured["responded"] is None

    def test_bad_review_alerts_no_role_gate(self, monkeypatch):
        monkeypatch.setattr(reputation_api, "list_bad_review_alerts", lambda role: [{"id": "REV-1"}])
        assert list_bad_review_alerts_api(FINANCE) == [{"id": "REV-1"}]

    def test_respond_to_review_denied_for_sales(self):
        result = respond_to_review_api(SALES, "EMP-1", "REV-1", "Thanks for the feedback")
        assert result == {"error": "Only marketing/admin can respond to a review"}

    def test_respond_to_review_allowed_serializes(self, monkeypatch):
        class FakeReview:
            id = "REV-1"
            attributes = {"response": "Thanks!"}

        monkeypatch.setattr(reputation_api, "respond_to_review", lambda review_id, employee_id, text: FakeReview())
        result = respond_to_review_api(MARKETING, "EMP-1", "REV-1", "Thanks!")
        assert result == {"id": "REV-1", "response": "Thanks!"}

    def test_respond_to_review_error_passthrough(self, monkeypatch):
        monkeypatch.setattr(reputation_api, "respond_to_review", lambda review_id, employee_id, text: {"error": "review not found"})
        result = respond_to_review_api(ADMIN, "EMP-1", "REV-BOGUS", "Thanks!")
        assert result == {"error": "review not found"}

    def test_auto_respond_denied_for_operations(self):
        result = auto_respond_review_api(OPERATIONS, "EMP-1", "REV-1")
        assert result == {"error": "Only marketing/admin can trigger the auto-respond bot"}

    def test_auto_respond_allowed_serializes(self, monkeypatch):
        class FakeReview:
            id = "REV-2"
            attributes = {"response": "AI-drafted reply"}

        monkeypatch.setattr(reputation_api, "auto_respond_review", lambda review_id: FakeReview())
        result = auto_respond_review_api(ADMIN, "EMP-1", "REV-2")
        assert result == {"id": "REV-2", "response": "AI-drafted reply"}

    def test_competitor_tracking_no_role_gate(self, monkeypatch):
        monkeypatch.setattr(reputation_api, "get_competitor_tracking", lambda role: {"basis": "simulated_peer_data"})
        assert get_competitor_tracking_api(SERVICE) == {"basis": "simulated_peer_data"}


# ---------------------------------------------------------------------------
# core/operations_scheduling_api.py
# ---------------------------------------------------------------------------

class TestOperationsSchedulingApi:

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, SERVICE, MARKETING, FINANCE])
    def test_recon_schedule_view_allowed_for_every_role(self, monkeypatch, role):
        monkeypatch.setattr(operations_scheduling_api, "get_recon_schedule", lambda r: {"role": r})
        assert get_recon_schedule_api(role) == {"role": role}

    def test_recon_schedule_denied_for_unknown_role(self):
        result = get_recon_schedule_api("BOGUS")
        assert result == {"error": "You don't have access to Operations Scheduling"}

    def test_schedule_recon_denied_for_service(self):
        # SERVICE can view scheduling but not mutate it (mutate is ADMIN/OPERATIONS/SALES only)
        result = schedule_recon_api(SERVICE, "EMP-1", "VEH-1", "2026-08-01")
        assert "error" in result

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES])
    def test_schedule_recon_allowed_serializes_via_serialize_task(self, monkeypatch, role):
        monkeypatch.setattr(operations_scheduling_api, "schedule_recon", lambda vehicle_id, date, by, notes="": "raw_task")
        monkeypatch.setattr(operations_scheduling_api, "serialize_task", lambda t: {"task": t})
        result = schedule_recon_api(role, "EMP-1", "VEH-1", "2026-08-01")
        assert result == {"task": "raw_task"}

    def test_schedule_recon_error_passthrough_skips_serialize(self, monkeypatch):
        monkeypatch.setattr(operations_scheduling_api, "schedule_recon", lambda vehicle_id, date, by, notes="": {"error": "vehicle not found"})
        monkeypatch.setattr(operations_scheduling_api, "serialize_task", lambda t: pytest.fail("should not be called on error"))
        result = schedule_recon_api(ADMIN, "EMP-1", "VEH-BOGUS", "2026-08-01")
        assert result == {"error": "vehicle not found"}

    def test_delivery_risk_board_delegates(self, monkeypatch):
        monkeypatch.setattr(operations_scheduling_api, "get_delivery_risk_board", lambda r: {"overdue": 0, "no_delivery_scheduled": 0})
        assert get_delivery_risk_board_api(SALES) == {"overdue": 0, "no_delivery_scheduled": 0}

    def test_schedule_delivery_denied_for_marketing(self):
        result = schedule_delivery_api(MARKETING, "EMP-1", "DEAL-1", "2026-08-05T10:00:00")
        assert "error" in result

    def test_schedule_delivery_allowed_flattens_entity(self, monkeypatch):
        class FakeAppointment:
            id = "APPT-1"
            attributes = {"department": "Sales", "status": "scheduled"}

        monkeypatch.setattr(
            operations_scheduling_api, "schedule_delivery",
            lambda deal_id, scheduled_start, by, assigned_to=None, notes="": FakeAppointment(),
        )
        result = schedule_delivery_api(SALES, "EMP-1", "DEAL-1", "2026-08-05T10:00:00")
        assert result == {"id": "APPT-1", "department": "Sales", "status": "scheduled"}

    def test_schedule_delivery_error_passthrough(self, monkeypatch):
        monkeypatch.setattr(
            operations_scheduling_api, "schedule_delivery",
            lambda deal_id, scheduled_start, by, assigned_to=None, notes="": {"error": "deal not found"},
        )
        result = schedule_delivery_api(OPERATIONS, "EMP-1", "DEAL-BOGUS", "2026-08-05T10:00:00")
        assert result == {"error": "deal not found"}

    def test_transport_schedule_delegates(self, monkeypatch):
        monkeypatch.setattr(operations_scheduling_api, "get_transport_schedule", lambda r: {"shipments": []})
        assert get_transport_schedule_api(FINANCE) == {"shipments": []}

    def test_update_transport_status_denied_for_service(self):
        result = update_transport_status_api(SERVICE, "EMP-1", "AUC-1", "at_auction_yard")
        assert "error" in result

    def test_update_transport_status_allowed_no_serialization(self, monkeypatch):
        # unlike schedule_recon/schedule_delivery, this one has no serialization step at all
        monkeypatch.setattr(
            operations_scheduling_api, "update_transport_status",
            lambda txn_id, status, by: {"transaction_id": txn_id, "status": status},
        )
        result = update_transport_status_api(SALES, "EMP-1", "AUC-1", "at_auction_yard")
        assert result == {"transaction_id": "AUC-1", "status": "at_auction_yard"}
