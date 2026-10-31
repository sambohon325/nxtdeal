"""
Tests for core/dashboard_layouts.py / core/dashboard_layouts_api.py -- per-employee,
per-department, per-board (reporting/overview) custom dashboard layouts, plus the
overview-board auto-seeding behavior.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entity_types import DASHBOARD_LAYOUT
import core.report_modules as report_modules

import core.dashboard_layouts as dashboard_layouts
from core.dashboard_layouts import get_layout, save_layout, MODES, CHART_TYPES, BOARDS, DEFAULT_BOARD
from core.dashboard_layouts_api import get_dashboard_layout_api, save_dashboard_layout_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(dashboard_layouts, "save_graph", lambda filepath: None)


def _module(module_key="kpi_leads", mode="graph", chart_type="bar", color="#FF0000",
            span=1, order=0, fields=None, show_in_overview=False, instance_id=None):
    return {
        "id": instance_id,
        "module_key": module_key,
        "mode": mode,
        "chart_type": chart_type,
        "color": color,
        "span": span,
        "order": order,
        "fields": fields or [],
        "show_in_overview": show_in_overview,
    }


# ---------------------------------------------------------------------------
# get_layout()
# ---------------------------------------------------------------------------

class TestGetLayout:

    def test_returns_empty_shape_when_nothing_saved(self):
        result = get_layout("EMP-1", "Sales")
        assert result == {"id": None, "department": "Sales", "board": "reporting", "modules": [], "updated_at": None}

    def test_defaults_to_reporting_board(self):
        result = get_layout("EMP-1", "Sales")
        assert result["board"] == "reporting"

    def test_unknown_board_falls_back_to_default(self):
        result = get_layout("EMP-1", "Sales", board="not-a-real-board")
        assert result["board"] == DEFAULT_BOARD

    def test_returns_saved_layout(self):
        save_layout("EMP-1", "Sales", [_module()])
        result = get_layout("EMP-1", "Sales")
        assert result["id"] is not None
        assert len(result["modules"]) == 1

    def test_layout_is_scoped_per_employee(self):
        save_layout("EMP-1", "Sales", [_module()])
        result = get_layout("EMP-2", "Sales")
        assert result["id"] is None
        assert result["modules"] == []

    def test_layout_is_scoped_per_department(self):
        save_layout("EMP-1", "Sales", [_module()])
        result = get_layout("EMP-1", "Service")
        assert result["id"] is None

    def test_layout_is_scoped_per_board(self):
        save_layout("EMP-1", "Sales", [_module()], board="reporting")
        result = get_layout("EMP-1", "Sales", board="overview")
        assert result["id"] is None
        assert result["modules"] == []

    def test_pre_session_77_layout_with_no_board_attribute_treated_as_reporting(self):
        # Simulate a layout saved before the "board" dimension existed.
        save_layout("EMP-1", "Sales", [_module()])
        entity = ledger.get_entity(get_layout("EMP-1", "Sales")["id"])
        del entity.attributes["board"]

        result = get_layout("EMP-1", "Sales", board="reporting")
        assert result["id"] == entity.id
        assert len(result["modules"]) == 1


# ---------------------------------------------------------------------------
# save_layout() -- module cleaning / validation
# ---------------------------------------------------------------------------

class TestSaveLayoutCleaning:

    def test_creates_a_new_layout_entity(self):
        result = save_layout("EMP-1", "Sales", [_module()])
        assert result["id"] is not None
        entity = ledger.get_entity(result["id"])
        assert entity.entity_type == DASHBOARD_LAYOUT
        assert entity.attributes["employee_id"] == "EMP-1"

    def test_full_replace_not_a_patch(self):
        save_layout("EMP-1", "Sales", [_module(module_key="kpi_a"), _module(module_key="kpi_b")])
        result = save_layout("EMP-1", "Sales", [_module(module_key="kpi_c")])
        assert len(result["modules"]) == 1
        assert result["modules"][0]["module_key"] == "kpi_c"

    def test_reuses_the_same_entity_on_repeat_saves(self):
        first = save_layout("EMP-1", "Sales", [_module()])
        second = save_layout("EMP-1", "Sales", [_module(module_key="kpi_2")])
        assert first["id"] == second["id"]
        assert len(ledger.get_all()) == 1

    def test_module_missing_module_key_dropped(self):
        bad = _module()
        bad["module_key"] = None
        result = save_layout("EMP-1", "Sales", [bad])
        assert result["modules"] == []

    def test_module_key_not_a_string_dropped(self):
        bad = _module()
        bad["module_key"] = 123
        result = save_layout("EMP-1", "Sales", [bad])
        assert result["modules"] == []

    def test_non_dict_module_dropped(self):
        result = save_layout("EMP-1", "Sales", ["not-a-dict", _module()])
        assert len(result["modules"]) == 1

    def test_modules_not_a_list_yields_empty(self):
        result = save_layout("EMP-1", "Sales", "not-a-list")
        assert result["modules"] == []

    def test_missing_id_generates_one(self):
        result = save_layout("EMP-1", "Sales", [_module(instance_id=None)])
        assert result["modules"][0]["id"] is not None
        assert result["modules"][0]["id"].startswith("DASH")

    def test_existing_id_preserved(self):
        result = save_layout("EMP-1", "Sales", [_module(instance_id="DASH-KEEP-ME")])
        assert result["modules"][0]["id"] == "DASH-KEEP-ME"

    def test_invalid_mode_falls_back_to_graph(self):
        result = save_layout("EMP-1", "Sales", [_module(mode="not-a-mode")])
        assert result["modules"][0]["mode"] == "graph"

    @pytest.mark.parametrize("mode", MODES)
    def test_valid_modes_preserved(self, mode):
        result = save_layout("EMP-1", "Sales", [_module(mode=mode)])
        assert result["modules"][0]["mode"] == mode

    def test_invalid_chart_type_falls_back_to_bar(self):
        result = save_layout("EMP-1", "Sales", [_module(chart_type="scatter")])
        assert result["modules"][0]["chart_type"] == "bar"

    @pytest.mark.parametrize("chart_type", CHART_TYPES)
    def test_valid_chart_types_preserved(self, chart_type):
        result = save_layout("EMP-1", "Sales", [_module(chart_type=chart_type)])
        assert result["modules"][0]["chart_type"] == chart_type

    def test_invalid_color_falls_back_to_default(self):
        result = save_layout("EMP-1", "Sales", [_module(color="not-a-hex-color")])
        assert result["modules"][0]["color"] == "#3FBCC4"

    def test_valid_hex_color_preserved(self):
        result = save_layout("EMP-1", "Sales", [_module(color="#123456")])
        assert result["modules"][0]["color"] == "#123456"

    def test_span_other_than_2_falls_back_to_1(self):
        result = save_layout("EMP-1", "Sales", [_module(span=99)])
        assert result["modules"][0]["span"] == 1

    def test_span_2_preserved(self):
        result = save_layout("EMP-1", "Sales", [_module(span=2)])
        assert result["modules"][0]["span"] == 2

    def test_order_falls_back_to_enumeration_index_when_not_an_int(self):
        modules = [_module(order="not-an-int"), _module(order="also-not-an-int", module_key="second")]
        result = save_layout("EMP-1", "Sales", modules)
        orders = sorted(m["order"] for m in result["modules"])
        assert orders == [0, 1]

    def test_explicit_int_order_preserved(self):
        result = save_layout("EMP-1", "Sales", [_module(order=5)])
        assert result["modules"][0]["order"] == 5

    def test_modules_sorted_by_order(self):
        modules = [
            _module(module_key="third", order=2),
            _module(module_key="first", order=0),
            _module(module_key="second", order=1),
        ]
        result = save_layout("EMP-1", "Sales", modules)
        keys = [m["module_key"] for m in result["modules"]]
        assert keys == ["first", "second", "third"]

    def test_fields_not_a_list_becomes_empty(self):
        result = save_layout("EMP-1", "Sales", [_module(fields="not-a-list")])
        assert result["modules"][0]["fields"] == []

    def test_fields_filters_non_strings(self):
        module = _module()
        module["fields"] = ["ok", 123, "also-ok", None]
        result = save_layout("EMP-1", "Sales", [module])
        assert result["modules"][0]["fields"] == ["ok", "also-ok"]

    def test_show_in_overview_coerced_to_bool(self):
        result = save_layout("EMP-1", "Sales", [_module(show_in_overview=1)])
        assert result["modules"][0]["show_in_overview"] is True

    def test_unknown_board_falls_back_to_default_on_save(self):
        result = save_layout("EMP-1", "Sales", [_module()], board="not-a-real-board")
        assert result["board"] == DEFAULT_BOARD

    def test_updated_at_is_set(self):
        result = save_layout("EMP-1", "Sales", [_module()])
        assert result["updated_at"] is not None

    def test_saving_empty_module_list_clears_the_board(self):
        save_layout("EMP-1", "Sales", [_module()])
        result = save_layout("EMP-1", "Sales", [])
        assert result["modules"] == []


# ---------------------------------------------------------------------------
# ACL layer (get_dashboard_layout_api / save_dashboard_layout_api)
# ---------------------------------------------------------------------------

class TestDashboardLayoutApi:

    def test_get_matches_direct_call_when_nothing_saved(self):
        result = get_dashboard_layout_api("EMP-1", "Sales")
        assert result == get_layout("EMP-1", "Sales")

    def test_get_defaults_board_to_reporting(self):
        result = get_dashboard_layout_api("EMP-1", "Sales")
        assert result["board"] == "reporting"

    def test_save_matches_direct_call(self):
        result = save_dashboard_layout_api("EMP-1", "Sales", [_module()])
        assert result["modules"][0]["module_key"] == "kpi_leads"

    def test_reporting_board_never_seeds_even_when_role_supplied(self):
        result = get_dashboard_layout_api("EMP-1", "Sales", board="reporting", role="SALES")
        assert result["modules"] == []

    def test_overview_board_does_not_seed_without_a_role(self):
        result = get_dashboard_layout_api("EMP-1", "Sales", board="overview", role=None)
        assert result["modules"] == []

    def test_overview_board_seeds_from_default_overview_modules_when_role_supplied(self, monkeypatch):
        seeded = [_module(module_key="seeded_kpi", instance_id=None)]
        monkeypatch.setattr(report_modules, "default_overview_modules", lambda role, employee_id, department: seeded)

        result = get_dashboard_layout_api("EMP-1", "Sales", board="overview", role="SALES")

        assert result["modules"] == seeded
        assert result["id"] is None  # not persisted just from seeding

    def test_overview_board_seeding_does_not_persist(self, monkeypatch):
        seeded = [_module(module_key="seeded_kpi", instance_id=None)]
        monkeypatch.setattr(report_modules, "default_overview_modules", lambda role, employee_id, department: seeded)

        get_dashboard_layout_api("EMP-1", "Sales", board="overview", role="SALES")

        assert ledger.get_all() == {}

    def test_overview_board_does_not_seed_once_a_real_layout_already_exists(self, monkeypatch):
        save_layout("EMP-1", "Sales", [_module(module_key="real_module")], board="overview")

        seeded = [_module(module_key="seeded_kpi")]
        monkeypatch.setattr(report_modules, "default_overview_modules", lambda role, employee_id, department: seeded)

        result = get_dashboard_layout_api("EMP-1", "Sales", board="overview", role="SALES")

        assert len(result["modules"]) == 1
        assert result["modules"][0]["module_key"] == "real_module"

    def test_overview_seeding_returns_empty_when_seed_function_returns_nothing(self, monkeypatch):
        monkeypatch.setattr(report_modules, "default_overview_modules", lambda role, employee_id, department: [])

        result = get_dashboard_layout_api("EMP-1", "Sales", board="overview", role="SALES")

        assert result["modules"] == []
