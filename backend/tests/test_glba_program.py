"""
Tests for core/glba_program.py + core/glba_program_api.py -- the GLBA Safeguards Rule
Information Security Program tracker (security-hardening pass, 2026-07-20, Task #11
"Add GLBA + PCI-DSS readiness controls," half 2 of 2).

Covers: the real computed-default-then-real-value behavior of get_component_status()
(an un-touched component honestly reports not_started, never fabricated as
compliant), list_program_items()'s real 7-component catalog in a stable order,
set_component_status()'s real upsert behavior (create on first call, update the same
record in place on a second call rather than accumulating a history list -- unlike
core/lending_compliance.py's own append-only cash-payment log, this is a genuine,
deliberate design difference this module's own docstring states explicitly),
component_key/status validation, get_glba_readiness_summary()'s real percentage math
(including the "never entered counts as not_started in the denominator" rule, so a
fresh program honestly reports 0%, not 100% or an undefined result), and
core/glba_program_api.py's real role gate -- SALES can view but not update the
program, MARKETING/SERVICE can do neither.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import glba_program
from core import glba_program_api
from core.dealeros import ledger
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


class TestProgramComponentsCatalog:

    def test_catalog_has_exactly_the_7_real_16_cfr_314_4_components(self):
        assert set(glba_program.PROGRAM_COMPONENTS.keys()) == {
            "qualified_individual",
            "risk_assessment",
            "safeguards_implementation",
            "staff_training",
            "service_provider_oversight",
            "incident_response_plan",
            "board_reporting",
        }

    def test_every_component_carries_a_real_citation_and_label(self):
        for key, entry in glba_program.PROGRAM_COMPONENTS.items():
            assert entry["citation"].startswith("16 CFR 314.4")
            assert entry["label"]
            assert entry["description"]


class TestGetComponentStatus:

    def test_an_untouched_component_honestly_reports_not_started(self):
        status = glba_program.get_component_status("risk_assessment")
        assert status["status"] == "not_started"
        assert status["owner_employee_id"] is None
        assert status["updated_by"] is None
        assert status["updated_at"] is None

    def test_an_untouched_component_still_carries_its_real_catalog_fields(self):
        status = glba_program.get_component_status("qualified_individual")
        assert status["label"] == "Qualified Individual Designated"
        assert status["citation"] == "16 CFR 314.4(a)"

    def test_an_unknown_component_key_returns_an_error(self):
        result = glba_program.get_component_status("not_a_real_component")
        assert "error" in result


class TestListProgramItems:

    def test_returns_all_7_components(self):
        items = glba_program.list_program_items()
        assert len(items) == 7

    def test_is_in_stable_catalog_order(self):
        items = glba_program.list_program_items()
        keys = [i["component_key"] for i in items]
        assert keys == list(glba_program.PROGRAM_COMPONENTS.keys())

    def test_a_fresh_never_touched_program_reports_every_component_not_started(self):
        items = glba_program.list_program_items()
        assert all(i["status"] == "not_started" for i in items)


class TestSetComponentStatus:

    def test_rejects_an_unknown_component_key(self):
        result = glba_program.set_component_status(
            "not_a_real_component", "complete", "EMP-00001", "", "EMP-00001",
        )
        assert "error" in result

    def test_rejects_an_invalid_status(self):
        result = glba_program.set_component_status(
            "risk_assessment", "somewhat_done", "EMP-00001", "", "EMP-00001",
        )
        assert "error" in result

    def test_a_real_update_is_reflected_immediately_on_read(self):
        glba_program.set_component_status(
            "risk_assessment", "complete", "EMP-00001", "Reviewed 2026 Q3", "EMP-00001",
        )
        status = glba_program.get_component_status("risk_assessment")
        assert status["status"] == "complete"
        assert status["owner_employee_id"] == "EMP-00001"
        assert status["notes"] == "Reviewed 2026 Q3"
        assert status["updated_by"] == "EMP-00001"
        assert status["updated_at"] is not None

    def test_a_second_call_upserts_the_same_record_rather_than_creating_a_second_one(self):
        glba_program.set_component_status(
            "staff_training", "in_progress", "EMP-00001", "Scheduling vendor", "EMP-00001",
        )
        glba_program.set_component_status(
            "staff_training", "complete", "EMP-00002", "Completed for all staff", "EMP-00002",
        )

        from core.entity_types import GLBA_PROGRAM_ITEM
        matching = [
            e for e in ledger.get_all().values()
            if e.entity_type == GLBA_PROGRAM_ITEM
            and e.attributes.get("component_key") == "staff_training"
        ]
        assert len(matching) == 1
        assert matching[0].attributes["status"] == "complete"
        assert matching[0].attributes["owner_employee_id"] == "EMP-00002"

    def test_notes_defaults_to_empty_string_when_falsy(self):
        glba_program.set_component_status(
            "incident_response_plan", "not_started", "EMP-00001", None, "EMP-00001",
        )
        status = glba_program.get_component_status("incident_response_plan")
        assert status["notes"] == ""

    def test_updating_one_component_does_not_affect_another(self):
        glba_program.set_component_status(
            "board_reporting", "complete", "EMP-00001", "", "EMP-00001",
        )
        other = glba_program.get_component_status("service_provider_oversight")
        assert other["status"] == "not_started"


class TestGlbaReadinessSummary:

    def test_a_fresh_program_reports_zero_percent_not_undefined(self):
        summary = glba_program.get_glba_readiness_summary()
        assert summary["readiness_pct"] == 0.0
        assert summary["total_components"] == 7
        assert summary["complete"] == 0
        assert summary["not_started"] == 7

    def test_partial_completion_computes_a_real_percentage(self):
        glba_program.set_component_status("qualified_individual", "complete", "EMP-00001", "", "EMP-00001")
        glba_program.set_component_status("risk_assessment", "complete", "EMP-00001", "", "EMP-00001")

        summary = glba_program.get_glba_readiness_summary()
        assert summary["complete"] == 2
        assert summary["not_started"] == 5
        assert summary["readiness_pct"] == round((2 / 7) * 100, 1)

    def test_in_progress_and_needs_review_are_counted_but_not_as_complete(self):
        glba_program.set_component_status("staff_training", "in_progress", "EMP-00001", "", "EMP-00001")
        glba_program.set_component_status("board_reporting", "needs_review", "EMP-00001", "", "EMP-00001")

        summary = glba_program.get_glba_readiness_summary()
        assert summary["in_progress"] == 1
        assert summary["needs_review"] == 1
        assert summary["complete"] == 0
        assert summary["readiness_pct"] == 0.0

    def test_full_completion_reports_100_percent(self):
        for key in glba_program.PROGRAM_COMPONENTS:
            glba_program.set_component_status(key, "complete", "EMP-00001", "", "EMP-00001")

        summary = glba_program.get_glba_readiness_summary()
        assert summary["readiness_pct"] == 100.0
        assert summary["complete"] == 7

    def test_summary_carries_a_real_items_list_and_a_not_legal_advice_notice(self):
        summary = glba_program.get_glba_readiness_summary()
        assert len(summary["items"]) == 7
        assert "not_legal_or_compliance_advice" in summary
        assert summary["not_legal_or_compliance_advice"]


class TestGlbaProgramApiAcl:

    def test_admin_can_view_the_readiness_summary(self):
        result = glba_program_api.get_glba_readiness_summary_api(ADMIN)
        assert "error" not in result

    def test_sales_can_view_but_not_update(self):
        view_result = glba_program_api.get_glba_readiness_summary_api(SALES)
        assert "error" not in view_result

        update_result = glba_program_api.set_glba_component_status_api(
            SALES, "risk_assessment", "complete", "EMP-00001", "", "EMP-00001",
        )
        assert "error" in update_result

    def test_operations_and_finance_can_both_view_and_update(self):
        for role in (OPERATIONS, FINANCE):
            update_result = glba_program_api.set_glba_component_status_api(
                role, "risk_assessment", "complete", "EMP-00001", "", "EMP-00001",
            )
            assert "error" not in update_result

    def test_marketing_and_service_are_denied_viewing_entirely(self):
        for role in (MARKETING, SERVICE):
            result = glba_program_api.get_glba_readiness_summary_api(role)
            assert "error" in result

    def test_marketing_and_service_are_denied_updating(self):
        for role in (MARKETING, SERVICE):
            result = glba_program_api.set_glba_component_status_api(
                role, "risk_assessment", "complete", "EMP-00001", "", "EMP-00001",
            )
            assert "error" in result

    def test_list_program_items_api_honors_the_same_view_gate(self):
        assert isinstance(glba_program_api.list_glba_program_items_api(ADMIN), list)
        assert "error" in glba_program_api.list_glba_program_items_api(MARKETING)

    def test_get_component_status_api_honors_the_same_view_gate(self):
        result = glba_program_api.get_glba_component_status_api(SALES, "risk_assessment")
        assert "error" not in result
        result = glba_program_api.get_glba_component_status_api(SERVICE, "risk_assessment")
        assert "error" in result
