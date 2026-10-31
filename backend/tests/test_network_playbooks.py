"""
Tests for core/network_playbooks.py -- Network's real curated Playbook
library (PLAYBOOK_CATALOG) plus Automation Scoring (_automation_score).
Added per BUILD_QUEUE.md's standing "convert to a real pytest suite as each
module gets touched" rule (CAF-00123 missing_test_coverage work).

Two real, non-obvious import/binding shapes this module has, both confirmed
by direct source read before writing any test:

  1. TRIGGER_TYPES and list_rules (core.workflow_automation) are MODULE-LEVEL
     imports -- directly monkeypatchable via monkeypatch.setattr(np, "name",
     fake).

  2. PLAYBOOK_CATALOG's own "diagnostic" values are DIRECT REFERENCES to the
     real core.network_root_cause._diag_* function OBJECTS, captured at this
     module's own import time -- exactly the same "bound at import time, not
     looked up by name" gotcha test_network_root_cause.py's own
     get_root_causes() tests already had to work around for _ROOT_CAUSE_MAP.
     Monkeypatching core.network_root_cause._diag_slow_lead_response (or
     np._diag_slow_lead_response, since it isn't even imported by name here)
     has NO EFFECT on what PLAYBOOK_CATALOG's already-bound entries actually
     call. get_playbook_library()-level tests therefore monkeypatch
     np.PLAYBOOK_CATALOG itself with a small, controlled fake catalog.

By contrast, _automation_score is called by get_playbook_library() via a
plain module-level name lookup (not a captured reference stored in a data
structure) -- so real TRIGGER_TYPES/list_rules mocking is sufficient to
drive its behavior through get_playbook_library() end to end, without also
needing to monkeypatch _automation_score itself.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import core.network_playbooks as np
from core.network_playbooks import (
    PLAYBOOK_CATALOG,
    _automation_score,
    get_playbook_library,
)
from core.workflow_automation import TRIGGER_TYPES as REAL_TRIGGER_TYPES


class _FakeRule:
    def __init__(self, trigger_type):
        self.attributes = {"trigger_type": trigger_type}


# ---------------------------------------------------------------------------
# _automation_score
# ---------------------------------------------------------------------------

class TestAutomationScore:
    def test_none_trigger_type_is_tier_zero(self, monkeypatch):
        monkeypatch.setattr(np, "TRIGGER_TYPES", {"lead_no_contact"})
        result = _automation_score(None)
        assert result["tier"] == 0
        assert result["label"] == "No Automation Path Yet"

    def test_unmapped_trigger_type_is_tier_zero(self, monkeypatch):
        monkeypatch.setattr(np, "TRIGGER_TYPES", {"lead_no_contact", "vehicle_aging_price"})
        result = _automation_score("some_trigger_type_not_in_the_catalog")
        assert result["tier"] == 0

    def test_matching_type_with_no_live_rule_is_tier_one(self, monkeypatch):
        monkeypatch.setattr(np, "TRIGGER_TYPES", {"lead_no_contact"})
        monkeypatch.setattr(np, "list_rules", lambda active_only=True: [])
        result = _automation_score("lead_no_contact")
        assert result["tier"] == 1
        assert result["label"] == "Automatable Today"
        assert "lead_no_contact" in result["note"]

    def test_matching_type_with_a_live_rule_of_a_different_type_is_still_tier_one(self, monkeypatch):
        monkeypatch.setattr(np, "TRIGGER_TYPES", {"lead_no_contact", "vehicle_aging_price"})
        monkeypatch.setattr(np, "list_rules", lambda active_only=True: [_FakeRule("vehicle_aging_price")])
        result = _automation_score("lead_no_contact")
        assert result["tier"] == 1

    def test_matching_type_with_a_live_matching_rule_is_tier_three(self, monkeypatch):
        monkeypatch.setattr(np, "TRIGGER_TYPES", {"lead_no_contact"})
        monkeypatch.setattr(np, "list_rules", lambda active_only=True: [
            _FakeRule("lead_no_contact"), _FakeRule("lead_no_contact"), _FakeRule("deal_stage_stalled")
        ])
        result = _automation_score("lead_no_contact")
        assert result["tier"] == 3
        assert result["label"] == "Already Automated"
        assert result["active_rule_count"] == 2

    def test_list_rules_is_called_with_active_only_true(self, monkeypatch):
        seen = {}

        def _fake_list_rules(active_only=False):
            seen["active_only"] = active_only
            return []

        monkeypatch.setattr(np, "TRIGGER_TYPES", {"lead_no_contact"})
        monkeypatch.setattr(np, "list_rules", _fake_list_rules)
        _automation_score("lead_no_contact")
        assert seen["active_only"] is True


# ---------------------------------------------------------------------------
# get_playbook_library -- composition/integration, against a small fake
# catalog (real PLAYBOOK_CATALOG entries' diagnostics are bound function
# references captured at import time and can't be individually mocked here).
# ---------------------------------------------------------------------------

FAKE_CATALOG = [
    {
        "key": "pb_active_automatable",
        "title": "Active + Automatable",
        "department": "sales",
        "kpi_keys": ["some_kpi"],
        "diagnostic": lambda: {"key": "pb_active_automatable", "finding": "Triggered."},
        "automation_trigger_type": "lead_no_contact",
        "summary": "summary a",
        "steps": ["step a1", "step a2"],
    },
    {
        "key": "pb_inactive_no_automation",
        "title": "Inactive, No Automation Path",
        "department": "service",
        "kpi_keys": ["another_kpi"],
        "diagnostic": lambda: None,
        "automation_trigger_type": None,
        "summary": "summary b",
        "steps": ["step b1"],
    },
    {
        "key": "pb_active_already_automated",
        "title": "Active + Already Automated",
        "department": "finance",
        "kpi_keys": ["yet_another_kpi"],
        "diagnostic": lambda: {"key": "pb_active_already_automated", "finding": "Triggered too."},
        "automation_trigger_type": "vehicle_aging_price",
        "summary": "summary c",
        "steps": ["step c1"],
    },
]


def _mock_catalog_and_automation(monkeypatch):
    monkeypatch.setattr(np, "PLAYBOOK_CATALOG", FAKE_CATALOG)
    monkeypatch.setattr(np, "TRIGGER_TYPES", {"lead_no_contact", "vehicle_aging_price", "deal_stage_stalled"})
    monkeypatch.setattr(np, "list_rules", lambda active_only=True: [_FakeRule("vehicle_aging_price")])


class TestGetPlaybookLibrary:
    def test_playbook_count_matches_catalog_size(self, monkeypatch):
        _mock_catalog_and_automation(monkeypatch)
        result = get_playbook_library()
        assert result["playbook_count"] == 3

    def test_currently_active_count_only_counts_triggered_diagnostics(self, monkeypatch):
        _mock_catalog_and_automation(monkeypatch)
        result = get_playbook_library()
        # 2 of 3 fake entries have a non-None diagnostic result.
        assert result["currently_active_count"] == 2

    def test_every_field_is_passed_through_correctly(self, monkeypatch):
        _mock_catalog_and_automation(monkeypatch)
        result = get_playbook_library()
        entry = next(e for e in result["playbooks"] if e["key"] == "pb_active_automatable")
        assert entry["title"] == "Active + Automatable"
        assert entry["department"] == "sales"
        assert entry["kpi_keys"] == ["some_kpi"]
        assert entry["summary"] == "summary a"
        assert entry["steps"] == ["step a1", "step a2"]
        assert entry["is_currently_active"] is True
        assert entry["active_finding"] == {"key": "pb_active_automatable", "finding": "Triggered."}

    def test_inactive_entry_has_none_finding_and_flag_false(self, monkeypatch):
        _mock_catalog_and_automation(monkeypatch)
        result = get_playbook_library()
        entry = next(e for e in result["playbooks"] if e["key"] == "pb_inactive_no_automation")
        assert entry["is_currently_active"] is False
        assert entry["active_finding"] is None
        assert entry["automation_score"]["tier"] == 0

    def test_automatable_but_not_yet_automated_entry_is_tier_one(self, monkeypatch):
        _mock_catalog_and_automation(monkeypatch)
        result = get_playbook_library()
        entry = next(e for e in result["playbooks"] if e["key"] == "pb_active_automatable")
        assert entry["automation_score"]["tier"] == 1

    def test_already_automated_entry_is_tier_three(self, monkeypatch):
        _mock_catalog_and_automation(monkeypatch)
        result = get_playbook_library()
        entry = next(e for e in result["playbooks"] if e["key"] == "pb_active_already_automated")
        assert entry["automation_score"]["tier"] == 3
        assert entry["automation_score"]["active_rule_count"] == 1

    def test_playbook_order_matches_catalog_order(self, monkeypatch):
        _mock_catalog_and_automation(monkeypatch)
        result = get_playbook_library()
        assert [e["key"] for e in result["playbooks"]] == [
            "pb_active_automatable",
            "pb_inactive_no_automation",
            "pb_active_already_automated",
        ]

    def test_note_is_present_and_non_empty(self, monkeypatch):
        _mock_catalog_and_automation(monkeypatch)
        result = get_playbook_library()
        assert isinstance(result["note"], str)
        assert len(result["note"]) > 0

    def test_role_parameter_is_accepted_but_does_not_change_output(self, monkeypatch):
        _mock_catalog_and_automation(monkeypatch)
        default_result = get_playbook_library()
        sales_result = get_playbook_library(role="SALES")
        assert default_result == sales_result

    def test_empty_catalog_returns_empty_library(self, monkeypatch):
        monkeypatch.setattr(np, "PLAYBOOK_CATALOG", [])
        result = get_playbook_library()
        assert result["playbooks"] == []
        assert result["playbook_count"] == 0
        assert result["currently_active_count"] == 0


# ---------------------------------------------------------------------------
# Real PLAYBOOK_CATALOG -- static structural sanity checks against the real,
# hand-written data (not mocked) so a future edit that breaks the catalog's
# own shape (a duplicate key, a missing field, a stale trigger-type string
# that no longer exists in workflow_automation.py) fails loudly here.
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS = {"key", "title", "department", "kpi_keys", "diagnostic", "automation_trigger_type", "summary", "steps"}


class TestRealPlaybookCatalogShape:
    def test_catalog_is_non_empty(self):
        assert len(PLAYBOOK_CATALOG) > 0

    def test_every_entry_has_all_required_fields(self):
        for pb in PLAYBOOK_CATALOG:
            missing = _REQUIRED_FIELDS - set(pb.keys())
            assert not missing, f"{pb.get('key')} is missing fields: {missing}"

    def test_every_key_is_unique(self):
        keys = [pb["key"] for pb in PLAYBOOK_CATALOG]
        assert len(keys) == len(set(keys))

    def test_every_diagnostic_is_callable(self):
        for pb in PLAYBOOK_CATALOG:
            assert callable(pb["diagnostic"]), f"{pb['key']}'s diagnostic is not callable"

    def test_every_steps_list_is_non_empty(self):
        for pb in PLAYBOOK_CATALOG:
            assert isinstance(pb["steps"], list) and len(pb["steps"]) > 0, f"{pb['key']} has no steps"

    def test_every_kpi_keys_list_is_non_empty(self):
        for pb in PLAYBOOK_CATALOG:
            assert isinstance(pb["kpi_keys"], list) and len(pb["kpi_keys"]) > 0, f"{pb['key']} has no kpi_keys"

    def test_every_automation_trigger_type_is_none_or_a_real_trigger_type(self):
        for pb in PLAYBOOK_CATALOG:
            trig = pb["automation_trigger_type"]
            assert trig is None or trig in REAL_TRIGGER_TYPES, (
                f"{pb['key']} references automation_trigger_type={trig!r}, "
                f"which is not in the real TRIGGER_TYPES catalog"
            )

    def test_every_department_is_a_real_lowercase_department_key(self):
        # network_root_cause.py's own diagnostics span these 5 real departments.
        valid_departments = {"sales", "service", "parts", "fi", "bhph"}
        for pb in PLAYBOOK_CATALOG:
            assert pb["department"] in valid_departments, f"{pb['key']} has an unexpected department: {pb['department']}"

    def test_get_playbook_library_runs_cleanly_against_the_real_catalog(self):
        # An end-to-end smoke check with zero mocking -- confirms every real
        # diagnostic function actually runs without raising against whatever
        # this test process's real (empty, per conftest.py) graph state is,
        # and that the composed result has the right top-level shape.
        result = get_playbook_library()
        assert result["playbook_count"] == len(PLAYBOOK_CATALOG)
        assert 0 <= result["currently_active_count"] <= result["playbook_count"]
        assert len(result["playbooks"]) == len(PLAYBOOK_CATALOG)
        for entry in result["playbooks"]:
            assert entry["automation_score"]["tier"] in (0, 1, 2, 3)
