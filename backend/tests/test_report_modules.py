"""
Tests for core/report_modules.py / core/report_modules_api.py -- the report-module
catalog engine behind each department's customizable Reporting/Overview dashboards
(sessions 73/77).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import core.report_modules as report_modules
from core.report_modules import (
    get_report_modules,
    get_overview_modules,
    default_overview_modules,
    _is_chartable,
    _prettify,
    DEFAULT_PALETTE,
)
import core.report_modules_api as report_modules_api
from core.report_modules_api import get_report_modules_api, get_overview_modules_api


# ---------------------------------------------------------------------------
# _prettify()
# ---------------------------------------------------------------------------

class TestPrettify:

    def test_underscores_replaced_with_spaces(self):
        assert _prettify("units_in_recon") == "Units In Recon"

    def test_dashes_replaced_with_spaces(self):
        assert _prettify("units-in-recon") == "Units In Recon"

    def test_single_word_title_cased(self):
        assert _prettify("gross") == "Gross"


# ---------------------------------------------------------------------------
# _is_chartable()
# ---------------------------------------------------------------------------

class TestIsChartable:

    def test_true_when_a_numeric_value_present(self):
        assert _is_chartable({"count": 12, "label": "units"}) is True

    def test_false_when_bools_are_the_only_numeric_looking_values(self):
        # bool is technically an int subclass -- must be explicitly excluded.
        assert _is_chartable({"active": True, "other": False}) is False

    def test_true_when_a_nonempty_list_of_dicts_present(self):
        assert _is_chartable({"rows": [{"a": 1}, {"a": 2}]}) is True

    def test_false_when_list_is_of_non_dicts(self):
        assert _is_chartable({"rows": ["a", "b"]}) is False

    def test_false_when_list_is_empty(self):
        assert _is_chartable({"rows": []}) is False

    def test_false_when_only_strings(self):
        assert _is_chartable({"label": "hello"}) is False

    def test_false_when_empty(self):
        assert _is_chartable({}) is False


# ---------------------------------------------------------------------------
# get_report_modules()
# ---------------------------------------------------------------------------

class TestGetReportModules:

    def test_no_reporting_item_catalogued_errors(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "overview"}])
        result = get_report_modules("ADMIN", "Sales")
        assert "error" in result
        assert "Sales" in result["error"]

    def test_underlying_fetch_error_passed_through(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "reporting"}])
        monkeypatch.setattr(report_modules, "get_menu_data", lambda role, dept, item: {"error": "denied"})
        result = get_report_modules("SALES", "Sales")
        assert result == {"error": "denied"}

    def test_non_dict_sections_dropped(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "reporting"}])
        monkeypatch.setattr(
            report_modules, "get_menu_data",
            lambda role, dept, item: {"a_section": "not-a-dict", "b_section": {"count": 5}},
        )
        result = get_report_modules("ADMIN", "Sales")
        keys = [m["module_key"] for m in result["modules"]]
        assert keys == ["b_section"]

    def test_empty_dict_sections_dropped(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "reporting"}])
        monkeypatch.setattr(
            report_modules, "get_menu_data",
            lambda role, dept, item: {"empty_section": {}, "real_section": {"count": 5}},
        )
        result = get_report_modules("ADMIN", "Sales")
        keys = [m["module_key"] for m in result["modules"]]
        assert keys == ["real_section"]

    def test_module_shape_includes_label_and_data(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "reporting"}])
        monkeypatch.setattr(
            report_modules, "get_menu_data",
            lambda role, dept, item: {"lead_volume": {"count": 42}},
        )
        result = get_report_modules("ADMIN", "Sales")
        assert result["department"] == "Sales"
        assert result["modules"] == [{"module_key": "lead_volume", "label": "Lead Volume", "data": {"count": 42}}]

    def test_data_not_a_dict_yields_no_modules(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "reporting"}])
        monkeypatch.setattr(report_modules, "get_menu_data", lambda role, dept, item: None)
        result = get_report_modules("ADMIN", "Sales")
        assert result["modules"] == []


# ---------------------------------------------------------------------------
# get_overview_modules()
# ---------------------------------------------------------------------------

class TestGetOverviewModules:

    def _stub_no_flags(self, monkeypatch, overview_data):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "overview"}])
        monkeypatch.setattr(report_modules, "get_menu_data", lambda role, dept, item: overview_data)
        monkeypatch.setattr(report_modules, "get_layout", lambda emp, dept, board: {"modules": []})

    def test_no_overview_item_catalogued_errors(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "reporting"}])
        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        assert "error" in result

    def test_underlying_fetch_error_passed_through(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "overview"}])
        monkeypatch.setattr(report_modules, "get_menu_data", lambda role, dept, item: {"error": "denied"})
        result = get_overview_modules("SALES", "EMP-1", "Sales")
        assert result == {"error": "denied"}

    def test_error_and_not_yet_tracked_and_none_fields_skipped(self, monkeypatch):
        self._stub_no_flags(monkeypatch, {
            "error": "should not appear as a module",
            "not_yet_tracked": {"gap": "no data"},
            "nothing_here": None,
            "real_kpi": 42,
        })
        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        keys = [m["module_key"] for m in result["modules"]]
        assert keys == ["real_kpi"]

    def test_dict_field_used_as_module_data_directly(self, monkeypatch):
        self._stub_no_flags(monkeypatch, {"gross": {"amount": 100}})
        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        assert result["modules"][0]["data"] == {"amount": 100}

    def test_empty_dict_field_skipped(self, monkeypatch):
        self._stub_no_flags(monkeypatch, {"empty": {}, "real": {"x": 1}})
        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        keys = [m["module_key"] for m in result["modules"]]
        assert keys == ["real"]

    def test_list_field_wrapped_in_items_key(self, monkeypatch):
        self._stub_no_flags(monkeypatch, {"rows": [{"a": 1}, {"a": 2}]})
        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        assert result["modules"][0]["data"] == {"items": [{"a": 1}, {"a": 2}]}

    def test_empty_list_field_skipped(self, monkeypatch):
        self._stub_no_flags(monkeypatch, {"rows": [], "real": 1})
        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        keys = [m["module_key"] for m in result["modules"]]
        assert keys == ["real"]

    def test_scalar_field_wrapped_in_value_key(self, monkeypatch):
        self._stub_no_flags(monkeypatch, {"lead_count": 17})
        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        assert result["modules"][0]["data"] == {"value": 17}

    def test_kpi_modules_tagged_with_source(self, monkeypatch):
        self._stub_no_flags(monkeypatch, {"lead_count": 17})
        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        assert result["modules"][0]["_source"] == "kpi"

    def test_flagged_reporting_section_folded_in(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "overview"}])
        monkeypatch.setattr(report_modules, "get_menu_data", lambda role, dept, item: {"lead_count": 17})
        monkeypatch.setattr(
            report_modules, "get_layout",
            lambda emp, dept, board: {"modules": [{"module_key": "custom_section", "show_in_overview": True}]},
        )
        monkeypatch.setattr(
            report_modules, "get_report_modules",
            lambda role, dept: {"modules": [{"module_key": "custom_section", "label": "Custom Section", "data": {"n": 1}}]},
        )

        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        keys = [m["module_key"] for m in result["modules"]]
        assert "custom_section" in keys
        folded = next(m for m in result["modules"] if m["module_key"] == "custom_section")
        assert folded["_source"] == "reporting"

    def test_unflagged_reporting_section_not_folded_in(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "overview"}])
        monkeypatch.setattr(report_modules, "get_menu_data", lambda role, dept, item: {"lead_count": 17})
        monkeypatch.setattr(
            report_modules, "get_layout",
            lambda emp, dept, board: {"modules": [{"module_key": "custom_section", "show_in_overview": False}]},
        )
        monkeypatch.setattr(
            report_modules, "get_report_modules",
            lambda role, dept: {"modules": [{"module_key": "custom_section", "label": "Custom Section", "data": {"n": 1}}]},
        )

        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        keys = [m["module_key"] for m in result["modules"]]
        assert "custom_section" not in keys

    def test_flagged_section_not_duplicated_when_kpi_key_already_matches(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "overview"}])
        monkeypatch.setattr(report_modules, "get_menu_data", lambda role, dept, item: {"lead_count": 17})
        monkeypatch.setattr(
            report_modules, "get_layout",
            lambda emp, dept, board: {"modules": [{"module_key": "lead_count", "show_in_overview": True}]},
        )
        monkeypatch.setattr(
            report_modules, "get_report_modules",
            lambda role, dept: {"modules": [{"module_key": "lead_count", "label": "Lead Count", "data": {"n": 1}}]},
        )

        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        matches = [m for m in result["modules"] if m["module_key"] == "lead_count"]
        assert len(matches) == 1
        assert matches[0]["_source"] == "kpi"

    def test_data_not_a_dict_yields_no_modules(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_department_menu", lambda dept: [{"key": "overview"}])
        monkeypatch.setattr(report_modules, "get_menu_data", lambda role, dept, item: None)
        monkeypatch.setattr(report_modules, "get_layout", lambda emp, dept, board: {"modules": []})
        result = get_overview_modules("ADMIN", "EMP-1", "Sales")
        assert result["modules"] == []


# ---------------------------------------------------------------------------
# default_overview_modules()
# ---------------------------------------------------------------------------

class TestDefaultOverviewModules:

    def test_returns_empty_when_catalog_not_a_dict(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_overview_modules", lambda role, emp, dept: {"error": "denied"})
        assert default_overview_modules("ADMIN", "EMP-1", "Sales") == []

    def test_returns_empty_when_no_modules_key(self, monkeypatch):
        monkeypatch.setattr(report_modules, "get_overview_modules", lambda role, emp, dept: {})
        assert default_overview_modules("ADMIN", "EMP-1", "Sales") == []

    def test_only_kpi_sourced_entries_seeded(self, monkeypatch):
        catalog = {
            "modules": [
                {"module_key": "kpi_one", "data": {"n": 1}, "_source": "kpi"},
                {"module_key": "reporting_one", "data": {"n": 2}, "_source": "reporting"},
            ]
        }
        monkeypatch.setattr(report_modules, "get_overview_modules", lambda role, emp, dept: catalog)
        seeded = default_overview_modules("ADMIN", "EMP-1", "Sales")
        assert [m["module_key"] for m in seeded] == ["kpi_one"]

    def test_seeded_modules_have_expected_defaults(self, monkeypatch):
        catalog = {"modules": [{"module_key": "kpi_one", "data": {"n": 1}, "_source": "kpi"}]}
        monkeypatch.setattr(report_modules, "get_overview_modules", lambda role, emp, dept: catalog)
        seeded = default_overview_modules("ADMIN", "EMP-1", "Sales")
        entry = seeded[0]
        assert entry["id"] is None
        assert entry["span"] == 1
        assert entry["fields"] == []
        assert entry["show_in_overview"] is False
        assert entry["chart_type"] == "bar"

    def test_mode_graph_when_chartable_else_text(self, monkeypatch):
        catalog = {
            "modules": [
                {"module_key": "numeric_kpi", "data": {"n": 1}, "_source": "kpi"},
                {"module_key": "text_kpi", "data": {"label": "hello"}, "_source": "kpi"},
            ]
        }
        monkeypatch.setattr(report_modules, "get_overview_modules", lambda role, emp, dept: catalog)
        seeded = default_overview_modules("ADMIN", "EMP-1", "Sales")
        by_key = {m["module_key"]: m for m in seeded}
        assert by_key["numeric_kpi"]["mode"] == "graph"
        assert by_key["text_kpi"]["mode"] == "text"

    def test_order_is_sequential(self, monkeypatch):
        catalog = {
            "modules": [
                {"module_key": "a", "data": {"n": 1}, "_source": "kpi"},
                {"module_key": "b", "data": {"n": 1}, "_source": "kpi"},
                {"module_key": "c", "data": {"n": 1}, "_source": "kpi"},
            ]
        }
        monkeypatch.setattr(report_modules, "get_overview_modules", lambda role, emp, dept: catalog)
        seeded = default_overview_modules("ADMIN", "EMP-1", "Sales")
        assert [m["order"] for m in seeded] == [0, 1, 2]

    def test_color_cycles_through_default_palette(self, monkeypatch):
        catalog = {
            "modules": [{"module_key": f"kpi_{i}", "data": {"n": 1}, "_source": "kpi"} for i in range(len(DEFAULT_PALETTE) + 1)]
        }
        monkeypatch.setattr(report_modules, "get_overview_modules", lambda role, emp, dept: catalog)
        seeded = default_overview_modules("ADMIN", "EMP-1", "Sales")
        assert seeded[0]["color"] == DEFAULT_PALETTE[0]
        assert seeded[len(DEFAULT_PALETTE)]["color"] == DEFAULT_PALETTE[0]  # wraps around


# ---------------------------------------------------------------------------
# ACL layer (core/report_modules_api.py)
# ---------------------------------------------------------------------------

class TestReportModulesApi:

    def test_get_report_modules_api_delegates(self, monkeypatch):
        monkeypatch.setattr(
            report_modules_api, "get_report_modules",
            lambda role, department: {"role": role, "department": department},
        )
        result = get_report_modules_api("SALES", "Sales")
        assert result == {"role": "SALES", "department": "Sales"}

    def test_get_overview_modules_api_delegates(self, monkeypatch):
        monkeypatch.setattr(
            report_modules_api, "get_overview_modules",
            lambda role, employee_id, department: {"role": role, "employee_id": employee_id, "department": department},
        )
        result = get_overview_modules_api("ADMIN", "EMP-1", "Sales")
        assert result == {"role": "ADMIN", "employee_id": "EMP-1", "department": "Sales"}
