"""
Tests for core/coaching.py / core/coaching_api.py -- the fourth pillar of
NXTDeal Workforce AI: Coaching Intensity Tiers, AI Performance Reviews
(data-grounded draft only, never auto-sent), and AI Career Pathing (a real
comparative $ signal, never a fabricated skills assessment).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import coaching
from core.coaching import (
    TIER_PARTICIPANT,
    TIER_PRODUCTIVE,
    TIER_AGGRESSIVE,
    VALID_INTENSITY_TIERS,
    DEFAULT_INTENSITY,
    SCOPE_GLOBAL,
    SCOPE_DEPARTMENT,
    SCOPE_ROLE,
    SCOPE_INDIVIDUAL,
    get_intensity_catalog,
    resolve_intensity,
    set_intensity_override,
    list_intensity_overrides,
    apply_intensity_to_tasks,
    REVIEW_STATUS_DRAFT,
    REVIEW_STATUS_FINALIZED,
    REVIEW_STATUS_SHARED,
    compose_review_metrics,
    create_performance_review,
    update_review_notes,
    finalize_review,
    share_review,
    discard_review,
    get_review,
    list_reviews,
    get_career_pathing_signal,
    get_career_pathing_board,
)
from core import coaching_api
from core.coaching_api import (
    get_intensity_catalog_api,
    resolve_intensity_api,
    set_intensity_override_api,
    list_intensity_overrides_api,
    preview_intensity_api,
    create_performance_review_api,
    update_review_notes_api,
    finalize_review_api,
    share_review_api,
    discard_review_api,
    get_review_api,
    list_reviews_api,
    get_career_pathing_signal_api,
    get_career_pathing_board_api,
)

import core.employee_value as employee_value_module
import core.sales_menu as sales_menu_module
import core.service_reporting as service_reporting_module


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(coaching, "save_graph", lambda filepath: None)
    monkeypatch.setattr(coaching, "save_audit_log", lambda filepath: None)


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


def _employee(employee_id, first="Jane", last="Doe", department="Sales", title="Sales Associate"):
    ledger.add_entity(Entity(id=employee_id, entity_type=EMPLOYEE, attributes={
        "FirstName": first, "LastName": last, "Department": department, "Title": title,
    }))


STAFF_EMP = "EMP-STAFF"
MANAGER_EMP = "EMP-MGR"
EXEC_EMP = "EMP-EXEC"


def _seed_tiers():
    _employee(STAFF_EMP, first="Sam", last="Staff", title="Sales Associate")
    _employee(MANAGER_EMP, first="Mia", last="Manager", title="Sales Manager")
    _employee(EXEC_EMP, first="Gary", last="GM", title="General Manager")


def _value_dict(employee_id, name="Alice", title="Sales Associate", department="sales",
                 tier="staff", monthly=3500.0, sample_size=0, basis="industry_estimate",
                 note="Industry-estimate baseline used.", automation=None):
    return {
        "employee_id": employee_id,
        "name": name,
        "department": department,
        "title": title,
        "tier": tier,
        "monthly_value_estimate": monthly,
        "sample_size": sample_size,
        "basis": basis,
        "automation_coverage": automation,
        "note": note,
        "disclaimer": "Not for headcount reduction purposes.",
    }


# ---------------------------------------------------------------------------
# 1. Coaching Intensity Tiers
# ---------------------------------------------------------------------------

class TestGetIntensityCatalog:

    def test_shape(self):
        result = get_intensity_catalog()
        keys = {t["key"] for t in result["tiers"]}
        assert keys == {"participant", "productive", "aggressive"}
        assert result["default_intensity"] == "productive"
        scope_keys = {s["key"] for s in result["scopes"]}
        assert scope_keys == {"global", "department", "role", "individual"}


class TestResolveIntensity:

    def test_no_override_falls_back_to_default(self):
        intensity, resolved_from = resolve_intensity()
        assert intensity == DEFAULT_INTENSITY
        assert resolved_from == "default"

    def test_global_override_applies(self):
        set_intensity_override(SCOPE_GLOBAL, None, TIER_AGGRESSIVE, "EMP-ADMIN")
        intensity, resolved_from = resolve_intensity()
        assert intensity == TIER_AGGRESSIVE
        assert resolved_from == "global"

    def test_department_override_beats_global(self):
        set_intensity_override(SCOPE_GLOBAL, None, TIER_AGGRESSIVE, "EMP-ADMIN")
        set_intensity_override(SCOPE_DEPARTMENT, "sales", TIER_PARTICIPANT, "EMP-ADMIN")
        intensity, resolved_from = resolve_intensity(department="Sales")
        assert intensity == TIER_PARTICIPANT
        assert resolved_from == "department"

    def test_department_scope_target_is_case_insensitive(self):
        set_intensity_override(SCOPE_DEPARTMENT, "SALES", TIER_PARTICIPANT, "EMP-ADMIN")
        intensity, resolved_from = resolve_intensity(department="sales")
        assert intensity == TIER_PARTICIPANT
        assert resolved_from == "department"

    def test_role_tier_override_beats_department(self):
        _seed_tiers()
        set_intensity_override(SCOPE_DEPARTMENT, "sales", TIER_PARTICIPANT, "EMP-ADMIN")
        set_intensity_override(SCOPE_ROLE, "staff", TIER_AGGRESSIVE, "EMP-ADMIN")
        intensity, resolved_from = resolve_intensity(employee_id=STAFF_EMP)
        assert intensity == TIER_AGGRESSIVE
        assert resolved_from == "role"

    def test_individual_override_beats_everything(self):
        _seed_tiers()
        set_intensity_override(SCOPE_GLOBAL, None, TIER_AGGRESSIVE, "EMP-ADMIN")
        set_intensity_override(SCOPE_ROLE, "staff", TIER_AGGRESSIVE, "EMP-ADMIN")
        set_intensity_override(SCOPE_INDIVIDUAL, STAFF_EMP, TIER_PARTICIPANT, "EMP-ADMIN")
        intensity, resolved_from = resolve_intensity(employee_id=STAFF_EMP)
        assert intensity == TIER_PARTICIPANT
        assert resolved_from == "individual"

    def test_unknown_employee_id_still_falls_back_gracefully(self):
        intensity, resolved_from = resolve_intensity(employee_id="EMP-GHOST")
        assert intensity == DEFAULT_INTENSITY
        assert resolved_from == "default"


class TestSetIntensityOverride:

    def test_unknown_scope_rejected(self):
        result = set_intensity_override("not_a_scope", "*", TIER_AGGRESSIVE, "EMP-ADMIN")
        assert "error" in result

    def test_unknown_intensity_rejected(self):
        result = set_intensity_override(SCOPE_GLOBAL, None, "not_an_intensity", "EMP-ADMIN")
        assert "error" in result

    def test_individual_scope_requires_real_employee(self):
        result = set_intensity_override(SCOPE_INDIVIDUAL, "EMP-GHOST", TIER_AGGRESSIVE, "EMP-ADMIN")
        assert "error" in result

    def test_individual_scope_succeeds_for_real_employee(self):
        _employee(STAFF_EMP)
        result = set_intensity_override(SCOPE_INDIVIDUAL, STAFF_EMP, TIER_AGGRESSIVE, "EMP-ADMIN")
        assert "error" not in result
        assert result["intensity"] == TIER_AGGRESSIVE

    def test_role_scope_requires_valid_tier(self):
        result = set_intensity_override(SCOPE_ROLE, "not_a_tier", TIER_AGGRESSIVE, "EMP-ADMIN")
        assert "error" in result

    def test_department_scope_requires_scope_target(self):
        result = set_intensity_override(SCOPE_DEPARTMENT, None, TIER_AGGRESSIVE, "EMP-ADMIN")
        assert "error" in result
        result = set_intensity_override(SCOPE_DEPARTMENT, "", TIER_AGGRESSIVE, "EMP-ADMIN")
        assert "error" in result

    def test_global_scope_ignores_scope_target_and_forces_wildcard(self):
        result = set_intensity_override(SCOPE_GLOBAL, "whatever", TIER_AGGRESSIVE, "EMP-ADMIN")
        assert result["scope_target"] == "*"

    def test_new_override_deactivates_prior_one_same_scope_target(self):
        first = set_intensity_override(SCOPE_GLOBAL, None, TIER_AGGRESSIVE, "EMP-ADMIN")
        second = set_intensity_override(SCOPE_GLOBAL, None, TIER_PARTICIPANT, "EMP-ADMIN")

        overrides = list_intensity_overrides()
        by_id = {o["id"]: o for o in overrides}
        assert by_id[first["id"]]["active"] is False
        assert by_id[first["id"]]["superseded_at"] is not None
        assert by_id[second["id"]]["active"] is True
        assert len(overrides) == 2


class TestListIntensityOverrides:

    def test_sorted_most_recent_first(self):
        first = set_intensity_override(SCOPE_DEPARTMENT, "sales", TIER_AGGRESSIVE, "EMP-ADMIN")
        second = set_intensity_override(SCOPE_DEPARTMENT, "service", TIER_PARTICIPANT, "EMP-ADMIN")
        overrides = list_intensity_overrides()
        assert overrides[0]["id"] == second["id"]
        assert overrides[1]["id"] == first["id"]


class TestApplyIntensity:

    def _items(self):
        return [
            {"key": "a", "priority": 1, "title": "Low priority item"},
            {"key": "b", "priority": 5, "title": "High priority item"},
            {"key": "c", "priority": 3, "title": "Mid priority item"},
        ]

    def test_productive_is_a_complete_noop(self):
        items = self._items()
        result = coaching._apply_intensity(items, TIER_PRODUCTIVE)
        assert result == items
        assert "urgency_label" not in result[0]

    def test_participant_trims_to_top_half_by_priority(self):
        items = self._items()
        result = coaching._apply_intensity(items, TIER_PARTICIPANT)
        assert len(result) == 1
        assert result[0]["key"] == "b"
        assert result[0]["urgency_label"] == "Worth a look"

    def test_participant_labels_low_priority_as_fyi(self):
        items = [{"key": "x", "priority": 1}]
        result = coaching._apply_intensity(items, TIER_PARTICIPANT)
        assert result[0]["urgency_label"] == "FYI"

    def test_aggressive_keeps_all_items_and_labels_every_one(self):
        items = self._items()
        result = coaching._apply_intensity(items, TIER_AGGRESSIVE)
        assert len(result) == 3
        labels = {r["key"]: r["urgency_label"] for r in result}
        assert labels["b"] == "Do this now"
        assert labels["a"] == "Take action"

    def test_aggressive_sorts_by_priority_descending(self):
        items = self._items()
        result = coaching._apply_intensity(items, TIER_AGGRESSIVE)
        assert [r["key"] for r in result] == ["b", "c", "a"]

    def test_original_items_never_mutated(self):
        items = self._items()
        coaching._apply_intensity(items, TIER_AGGRESSIVE)
        assert "urgency_label" not in items[0]

    def test_invalid_intensity_falls_back_to_default_productive(self):
        items = self._items()
        result = coaching._apply_intensity(items, "not_a_real_intensity")
        assert result == items

    def test_empty_list_at_participant_stays_empty(self):
        result = coaching._apply_intensity([], TIER_PARTICIPANT)
        assert result == []

    def test_apply_intensity_to_tasks_resolves_and_applies(self):
        _employee(STAFF_EMP)
        set_intensity_override(SCOPE_INDIVIDUAL, STAFF_EMP, TIER_AGGRESSIVE, "EMP-ADMIN")
        items, intensity, resolved_from = apply_intensity_to_tasks(self._items(), STAFF_EMP)
        assert intensity == TIER_AGGRESSIVE
        assert resolved_from == "individual"
        assert len(items) == 3


# ---------------------------------------------------------------------------
# 2. AI Performance Reviews
# ---------------------------------------------------------------------------

class TestComposeReviewMetrics:

    def test_unknown_employee_returns_none(self, monkeypatch):
        monkeypatch.setattr(employee_value_module, "compute_employee_value", lambda eid: None)
        assert compose_review_metrics("EMP-GHOST") is None

    def test_sales_department_with_scorecard(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="sales"),
        )
        monkeypatch.setattr(
            sales_menu_module, "_salesperson_scorecards",
            lambda: [{"employee_id": "EMP-1", "units_sold_funded": 4, "gross_profit": 12000.0,
                      "conversion_rate": 0.25, "show_rate": 0.8}],
        )
        metrics = compose_review_metrics("EMP-1")
        assert metrics["department_scorecard"]["units_sold_funded"] == 4
        assert metrics["department_scorecard_note"] is None

    def test_sales_department_with_no_matching_scorecard(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="sales"),
        )
        monkeypatch.setattr(sales_menu_module, "_salesperson_scorecards", lambda: [])
        metrics = compose_review_metrics("EMP-1")
        assert metrics["department_scorecard"] is None
        assert "sales" in metrics["department_scorecard_note"]

    def test_service_department_with_scorecard(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="service"),
        )
        monkeypatch.setattr(
            service_reporting_module, "get_technician_scorecard",
            lambda: {"technicians": [{"technician_id": "EMP-1", "ro_count": 10,
                                       "total_labor_hours": 40, "total_revenue": 5000.0,
                                       "avg_revenue_per_ro": 500.0}]},
        )
        metrics = compose_review_metrics("EMP-1")
        assert metrics["department_scorecard"]["ro_count"] == 10

    def test_other_department_gets_no_scorecard_and_a_note(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="finance"),
        )
        metrics = compose_review_metrics("EMP-1")
        assert metrics["department_scorecard"] is None
        assert "finance" in metrics["department_scorecard_note"]


class TestFactualSummarySentences:

    def test_base_sentence_includes_monthly_value_and_basis(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, name="Alice", monthly=3500.0, sample_size=0,
                                     basis="industry_estimate", department="finance",
                                     note="Real note text."),
        )
        review = create_performance_review("EMP-1", "EMP-ADMIN")
        sentences = review["factual_summary"]
        assert "Alice" in sentences[0]
        assert "3,500.00" in sentences[0]
        assert "industry_estimate" in sentences[0]
        assert sentences[-1] == "Real note text."

    def test_sales_sentence_with_show_rate(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="sales"),
        )
        monkeypatch.setattr(
            sales_menu_module, "_salesperson_scorecards",
            lambda: [{"employee_id": "EMP-1", "units_sold_funded": 4, "gross_profit": 12000.0,
                      "conversion_rate": 0.25, "show_rate": 0.8}],
        )
        review = create_performance_review("EMP-1", "EMP-ADMIN")
        joined = " ".join(review["factual_summary"])
        assert "25.0%" in joined
        assert "80.0%" in joined

    def test_sales_sentence_without_show_rate(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="sales"),
        )
        monkeypatch.setattr(
            sales_menu_module, "_salesperson_scorecards",
            lambda: [{"employee_id": "EMP-1", "units_sold_funded": 4, "gross_profit": 12000.0,
                      "conversion_rate": 0.25, "show_rate": None}],
        )
        review = create_performance_review("EMP-1", "EMP-ADMIN")
        joined = " ".join(review["factual_summary"])
        assert "conversion rate." in joined

    def test_automation_coverage_sentence_included_when_present(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="finance", automation={
                "distinct_task_types": 4, "automatable_task_types": 2, "automation_pct": 50,
            }),
        )
        review = create_performance_review("EMP-1", "EMP-ADMIN")
        joined = " ".join(review["factual_summary"])
        assert "50%" in joined
        assert "auto-executable whitelist" in joined


class TestPerformanceReviewLifecycle:

    def _new_review(self, monkeypatch, department="finance"):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department=department),
        )
        return create_performance_review("EMP-1", "EMP-ADMIN", period_label="Q3 2026")

    def test_create_unknown_employee_rejected(self, monkeypatch):
        monkeypatch.setattr(employee_value_module, "compute_employee_value", lambda eid: None)
        result = create_performance_review("EMP-GHOST", "EMP-ADMIN")
        assert "error" in result

    def test_create_success_is_a_draft(self, monkeypatch):
        review = self._new_review(monkeypatch)
        assert review["status"] == REVIEW_STATUS_DRAFT
        assert review["period_label"] == "Q3 2026"
        assert review["manager_notes"] == ""

    def test_update_notes_while_draft(self, monkeypatch):
        review = self._new_review(monkeypatch)
        result = update_review_notes(review["id"], "Great quarter overall.", "EMP-MGR")
        assert result["manager_notes"] == "Great quarter overall."

    def test_update_notes_rejected_once_finalized(self, monkeypatch):
        review = self._new_review(monkeypatch)
        finalize_review(review["id"], "EMP-MGR")
        result = update_review_notes(review["id"], "Too late", "EMP-MGR")
        assert "error" in result

    def test_finalize_from_draft_succeeds(self, monkeypatch):
        review = self._new_review(monkeypatch)
        result = finalize_review(review["id"], "EMP-MGR")
        assert result["status"] == REVIEW_STATUS_FINALIZED
        assert result["finalized_by"] == "EMP-MGR"

    def test_cannot_finalize_twice(self, monkeypatch):
        review = self._new_review(monkeypatch)
        finalize_review(review["id"], "EMP-MGR")
        result = finalize_review(review["id"], "EMP-MGR")
        assert "error" in result

    def test_share_requires_finalized_first(self, monkeypatch):
        review = self._new_review(monkeypatch)
        result = share_review(review["id"], "EMP-MGR")
        assert "error" in result

    def test_share_after_finalize_succeeds(self, monkeypatch):
        review = self._new_review(monkeypatch)
        finalize_review(review["id"], "EMP-MGR")
        result = share_review(review["id"], "EMP-MGR")
        assert result["status"] == REVIEW_STATUS_SHARED
        assert result["shared_by"] == "EMP-MGR"

    def test_discard_only_works_on_a_draft(self, monkeypatch):
        review = self._new_review(monkeypatch)
        finalize_review(review["id"], "EMP-MGR")
        result = discard_review(review["id"], "EMP-MGR")
        assert "error" in result

    def test_discard_draft_removes_it(self, monkeypatch):
        review = self._new_review(monkeypatch)
        result = discard_review(review["id"], "EMP-MGR")
        assert result["success"] is True
        assert get_review(review["id"]) is None

    def test_get_review_not_found(self):
        assert get_review("PREV-GHOST") is None

    def test_unknown_review_id_rejected_everywhere(self):
        assert "error" in update_review_notes("PREV-GHOST", "x", "y")
        assert "error" in finalize_review("PREV-GHOST", "y")
        assert "error" in share_review("PREV-GHOST", "y")
        assert "error" in discard_review("PREV-GHOST", "y")

    def test_list_reviews_filters_by_employee_and_status(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="finance"),
        )
        r1 = create_performance_review("EMP-1", "EMP-ADMIN")
        r2 = create_performance_review("EMP-2", "EMP-ADMIN")
        finalize_review(r1["id"], "EMP-ADMIN")

        assert len(list_reviews(employee_id="EMP-1")) == 1
        assert len(list_reviews(status=REVIEW_STATUS_DRAFT)) == 1
        assert len(list_reviews(status=REVIEW_STATUS_FINALIZED)) == 1
        assert len(list_reviews()) == 2


# ---------------------------------------------------------------------------
# 3. AI Career Pathing
# ---------------------------------------------------------------------------

def _fake_values():
    return {
        "EMP-A": _value_dict("EMP-A", name="Alice", department="sales", tier="staff", monthly=5000.0),
        "EMP-B": _value_dict("EMP-B", name="Bob", department="sales", tier="staff", monthly=4000.0),
        "EMP-C": _value_dict("EMP-C", name="Cara", department="sales", tier="staff", monthly=3800.0),
        "EMP-D": _value_dict("EMP-D", name="Dan", department="sales", tier="staff", monthly=2500.0),
        "EMP-SOLO": _value_dict("EMP-SOLO", name="Solo", department="finance", tier="executive", monthly=9000.0),
    }


def _patch_employee_value(monkeypatch):
    values = _fake_values()
    monkeypatch.setattr(employee_value_module, "compute_employee_value", lambda eid: values.get(eid))
    monkeypatch.setattr(
        employee_value_module, "list_employee_values",
        lambda department=None: [v for v in values.values() if department is None or v["department"] == department],
    )


class TestGetCareerPathingSignal:

    def test_unknown_employee_rejected(self, monkeypatch):
        _patch_employee_value(monkeypatch)
        result = get_career_pathing_signal("EMP-GHOST")
        assert "error" in result

    def test_no_peers_returns_insufficient_data(self, monkeypatch):
        _patch_employee_value(monkeypatch)
        result = get_career_pathing_signal("EMP-SOLO")
        assert result["signal"] == "insufficient_peer_data"
        assert result["next_tier"] is None

    def test_ready_for_more_responsibility_when_well_above_peer_average(self, monkeypatch):
        _patch_employee_value(monkeypatch)
        # EMP-A ($5000) vs peers B/C/D avg = (4000+3800+2500)/3 = 3433.33
        result = get_career_pathing_signal("EMP-A")
        assert result["signal"] == "ready_for_more_responsibility"
        assert result["next_tier"] == "manager"
        assert "manager-tier readiness" in result["finding"]
        assert result["peer_sample_size"] == 3

    def test_skill_gap_when_well_below_peer_average(self, monkeypatch):
        _patch_employee_value(monkeypatch)
        # EMP-D ($2500) vs peers A/B/C avg = (5000+4000+3800)/3 = 4266.67
        result = get_career_pathing_signal("EMP-D")
        assert result["signal"] == "skill_gap"

    def test_on_par_when_within_normal_range(self, monkeypatch):
        _patch_employee_value(monkeypatch)
        # EMP-B ($4000) vs peers A/C/D avg = (5000+3800+2500)/3 = 3766.67 -> +6.2%
        result = get_career_pathing_signal("EMP-B")
        assert result["signal"] == "on_par_with_peers"

    def test_basis_note_present(self, monkeypatch):
        _patch_employee_value(monkeypatch)
        result = get_career_pathing_signal("EMP-A")
        assert "not a fabricated skills assessment" in result["basis_note"]


class TestGetCareerPathingBoard:

    def test_counts_by_signal(self, monkeypatch):
        _patch_employee_value(monkeypatch)
        board = get_career_pathing_board(department="sales")
        assert board["count"] == 4
        assert sum(board["by_signal"].values()) == 4

    def test_signal_filter(self, monkeypatch):
        _patch_employee_value(monkeypatch)
        board = get_career_pathing_board(department="sales", signal="skill_gap")
        assert board["count"] == 1
        assert board["employees"][0]["employee_id"] == "EMP-D"


# ---------------------------------------------------------------------------
# ACL layer
# ---------------------------------------------------------------------------

class TestResolveIntensityApi:

    def test_self_view_always_allowed_regardless_of_role(self):
        _employee(STAFF_EMP)
        result = resolve_intensity_api("NOT_A_REAL_ROLE", STAFF_EMP)
        assert "error" not in result
        assert result["employee_id"] == STAFF_EMP

    def test_admin_can_view_someone_elses_intensity(self):
        _seed_tiers()
        result = resolve_intensity_api(ADMIN, "EMP-CALLER", target_employee_id=STAFF_EMP)
        assert "error" not in result

    def test_manager_tier_caller_can_view_someone_elses_intensity(self):
        _seed_tiers()
        result = resolve_intensity_api(SALES, MANAGER_EMP, target_employee_id=STAFF_EMP)
        assert "error" not in result

    def test_staff_tier_caller_denied_viewing_someone_else(self):
        _seed_tiers()
        result = resolve_intensity_api(SALES, STAFF_EMP, target_employee_id=MANAGER_EMP)
        assert "error" in result


class TestSetIntensityOverrideApi:

    def test_admin_allowed_with_no_employee(self):
        result = set_intensity_override_api(ADMIN, None, SCOPE_GLOBAL, None, TIER_AGGRESSIVE)
        assert "error" not in result

    def test_manager_tier_employee_allowed(self):
        _seed_tiers()
        result = set_intensity_override_api(SALES, MANAGER_EMP, SCOPE_GLOBAL, None, TIER_AGGRESSIVE)
        assert "error" not in result

    def test_staff_tier_employee_denied(self):
        _seed_tiers()
        result = set_intensity_override_api(SALES, STAFF_EMP, SCOPE_GLOBAL, None, TIER_AGGRESSIVE)
        assert "error" in result

    def test_no_employee_and_non_admin_role_denied(self):
        result = set_intensity_override_api(SALES, None, SCOPE_GLOBAL, None, TIER_AGGRESSIVE)
        assert "error" in result


class TestListIntensityOverridesApi:

    def test_admin_allowed(self):
        result = list_intensity_overrides_api(ADMIN, None)
        assert "error" not in result

    def test_staff_denied(self):
        _seed_tiers()
        result = list_intensity_overrides_api(SALES, STAFF_EMP)
        assert "error" in result


class TestPreviewIntensityApi:

    def test_self_preview_allowed(self):
        _employee(STAFF_EMP)
        items = [{"key": "a", "priority": 1}]
        result = preview_intensity_api(SALES, STAFF_EMP, STAFF_EMP, items)
        assert "error" not in result
        assert "intensity" in result

    def test_previewing_someone_elses_requires_manager_or_admin(self):
        _seed_tiers()
        items = [{"key": "a", "priority": 1}]
        result = preview_intensity_api(SALES, STAFF_EMP, MANAGER_EMP, items)
        assert "error" in result

    def test_admin_can_preview_anyone(self):
        _employee(STAFF_EMP)
        items = [{"key": "a", "priority": 1}]
        result = preview_intensity_api(ADMIN, "EMP-CALLER", STAFF_EMP, items)
        assert "error" not in result


class TestPerformanceReviewApiLifecycle:

    def _make_review(self, monkeypatch, role=ADMIN, caller="EMP-ADMIN"):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="finance"),
        )
        return create_performance_review_api(role, caller, "EMP-1")

    def test_create_denied_for_staff_role(self, monkeypatch):
        _seed_tiers()
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="finance"),
        )
        result = create_performance_review_api(SALES, STAFF_EMP, "EMP-1")
        assert "error" in result

    def test_create_allowed_for_manager_tier(self, monkeypatch):
        _seed_tiers()
        result = self._make_review(monkeypatch, role=SALES, caller=MANAGER_EMP)
        assert "error" not in result
        assert result["status"] == REVIEW_STATUS_DRAFT

    def test_update_notes_denied_for_staff(self, monkeypatch):
        _seed_tiers()
        review = self._make_review(monkeypatch)
        result = update_review_notes_api(SALES, STAFF_EMP, review["id"], "notes")
        assert "error" in result

    def test_update_notes_allowed_for_admin(self, monkeypatch):
        review = self._make_review(monkeypatch)
        result = update_review_notes_api(ADMIN, "EMP-ADMIN", review["id"], "Solid quarter.")
        assert result["manager_notes"] == "Solid quarter."

    def test_finalize_share_discard_gated(self, monkeypatch):
        _seed_tiers()
        review = self._make_review(monkeypatch)

        assert "error" in finalize_review_api(SALES, STAFF_EMP, review["id"])

        finalized = finalize_review_api(ADMIN, "EMP-ADMIN", review["id"])
        assert finalized["status"] == REVIEW_STATUS_FINALIZED

        assert "error" in share_review_api(SALES, STAFF_EMP, review["id"])

        shared = share_review_api(OPERATIONS, "EMP-OPS", review["id"])
        assert shared["status"] == REVIEW_STATUS_SHARED

    def test_discard_gated(self, monkeypatch):
        _seed_tiers()
        review = self._make_review(monkeypatch)
        assert "error" in discard_review_api(SALES, STAFF_EMP, review["id"])
        result = discard_review_api(ADMIN, "EMP-ADMIN", review["id"])
        assert result["success"] is True


class TestGetReviewApi:

    def _make_review(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="finance"),
        )
        return create_performance_review("EMP-1", "EMP-ADMIN")

    def test_not_found(self):
        result = get_review_api(ADMIN, "EMP-ADMIN", "PREV-GHOST")
        assert "error" in result

    def test_reviewed_employee_cannot_see_own_draft(self, monkeypatch):
        review = self._make_review(monkeypatch)
        result = get_review_api(SALES, "EMP-1", review["id"])
        assert "error" in result

    def test_reviewed_employee_can_see_own_review_once_shared(self, monkeypatch):
        review = self._make_review(monkeypatch)
        finalize_review(review["id"], "EMP-ADMIN")
        share_review(review["id"], "EMP-ADMIN")
        result = get_review_api(SALES, "EMP-1", review["id"])
        assert result["status"] == REVIEW_STATUS_SHARED

    def test_manager_can_see_someone_elses_draft(self, monkeypatch):
        _seed_tiers()
        review = self._make_review(monkeypatch)
        result = get_review_api(SALES, MANAGER_EMP, review["id"])
        assert result["status"] == REVIEW_STATUS_DRAFT

    def test_staff_denied_seeing_someone_elses_draft(self, monkeypatch):
        _seed_tiers()
        review = self._make_review(monkeypatch)
        result = get_review_api(SALES, STAFF_EMP, review["id"])
        assert "error" in result


class TestListReviewsApi:

    def test_self_query_without_manager_tier_only_sees_shared(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="finance"),
        )
        r1 = create_performance_review("EMP-1", "EMP-ADMIN")
        r2 = create_performance_review("EMP-1", "EMP-ADMIN")
        finalize_review(r2["id"], "EMP-ADMIN")
        share_review(r2["id"], "EMP-ADMIN")

        result = list_reviews_api(SALES, "EMP-1", employee_id="EMP-1")
        assert len(result["reviews"]) == 1
        assert result["reviews"][0]["status"] == REVIEW_STATUS_SHARED

    def test_admin_sees_every_status_for_any_employee(self, monkeypatch):
        monkeypatch.setattr(
            employee_value_module, "compute_employee_value",
            lambda eid: _value_dict(eid, department="finance"),
        )
        create_performance_review("EMP-1", "EMP-ADMIN")
        result = list_reviews_api(ADMIN, "EMP-ADMIN", employee_id="EMP-1")
        assert len(result["reviews"]) == 1

    def test_non_manager_querying_someone_elses_reviews_denied(self):
        _seed_tiers()
        result = list_reviews_api(SALES, STAFF_EMP, employee_id=MANAGER_EMP)
        assert "error" in result


class TestCareerPathingApi:

    def test_staff_tier_caller_denied_even_for_own_signal(self, monkeypatch):
        _seed_tiers()
        _patch_employee_value(monkeypatch)
        result = get_career_pathing_signal_api(SALES, STAFF_EMP, target_employee_id=STAFF_EMP)
        assert "error" in result

    def test_manager_tier_caller_allowed(self, monkeypatch):
        _seed_tiers()
        _patch_employee_value(monkeypatch)
        result = get_career_pathing_signal_api(SALES, MANAGER_EMP, target_employee_id="EMP-A")
        assert "error" not in result

    def test_admin_allowed_and_defaults_target_to_caller(self, monkeypatch):
        _patch_employee_value(monkeypatch)
        result = get_career_pathing_signal_api(ADMIN, "EMP-A")
        assert result["employee_id"] == "EMP-A"

    def test_board_gated_the_same_way(self, monkeypatch):
        _seed_tiers()
        _patch_employee_value(monkeypatch)
        assert "error" in get_career_pathing_board_api(SALES, STAFF_EMP)
        result = get_career_pathing_board_api(ADMIN, "EMP-ADMIN", department="sales")
        assert result["count"] == 4
