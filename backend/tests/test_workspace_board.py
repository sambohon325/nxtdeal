"""
Tests for core/workspace_board.py / core/workspace_board_api.py -- per-employee
OneNote-style Workspace board persistence (chart items + note items), plus the
shared-board viewing ACL layer built on top of core/knowledge_pins.py.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entity_types import WORKSPACE_BOARD
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

import core.workspace_board as workspace_board
import core.knowledge_pins as knowledge_pins
from core.workspace_board import get_board, save_board, ITEM_KINDS, CHART_TYPES
from core.workspace_board import add_workspace_item
from core.workspace_board_api import (
    get_workspace_board_api,
    save_workspace_board_api,
    add_workspace_item_api,
    get_shared_workspace_board_api,
)
from core.knowledge_pins import create_pin


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(workspace_board, "save_graph", lambda filepath: None)
    monkeypatch.setattr(knowledge_pins, "save_graph", lambda filepath: None)


def _chart_item(department="Sales", item_key="overview", chart_type="bar",
                 field_path=None, selected_columns=None, source_label="",
                 label_column="", note_text="", note_ai_generated=False,
                 span=1, order=0, item_id=None, x=None, y=None):
    return {
        "id": item_id,
        "kind": "chart",
        "span": span,
        "order": order,
        "x": x,
        "y": y,
        "department": department,
        "item_key": item_key,
        "field_path": field_path if field_path is not None else [],
        "source_label": source_label,
        "label_column": label_column,
        "chart_type": chart_type,
        "selected_columns": selected_columns if selected_columns is not None else [],
        "note_text": note_text,
        "note_ai_generated": note_ai_generated,
    }


def _note_item(title="My Note", text="Body text", source_context="From chat",
               ai_generated=False, span=1, order=0, item_id=None, x=None, y=None):
    return {
        "id": item_id,
        "kind": "note",
        "span": span,
        "order": order,
        "x": x,
        "y": y,
        "title": title,
        "text": text,
        "source_context": source_context,
        "ai_generated": ai_generated,
    }


# ---------------------------------------------------------------------------
# get_board()
# ---------------------------------------------------------------------------

class TestGetBoard:

    def test_returns_empty_shape_when_nothing_saved(self):
        result = get_board("EMP-1")
        assert result == {"id": None, "items": [], "updated_at": None}

    def test_returns_saved_board(self):
        save_board("EMP-1", [_note_item()])
        result = get_board("EMP-1")
        assert result["id"] is not None
        assert len(result["items"]) == 1

    def test_board_is_scoped_per_employee(self):
        save_board("EMP-1", [_note_item()])
        result = get_board("EMP-2")
        assert result["id"] is None


# ---------------------------------------------------------------------------
# save_board() -- item cleaning / validation
# ---------------------------------------------------------------------------

class TestSaveBoardCleaning:

    def test_creates_a_new_board_entity(self):
        result = save_board("EMP-1", [_note_item()])
        assert result["id"] is not None
        entity = ledger.get_entity(result["id"])
        assert entity.entity_type == WORKSPACE_BOARD
        assert entity.attributes["employee_id"] == "EMP-1"

    def test_full_replace_not_a_patch(self):
        save_board("EMP-1", [_note_item(title="A"), _note_item(title="B")])
        result = save_board("EMP-1", [_note_item(title="C")])
        assert len(result["items"]) == 1
        assert result["items"][0]["title"] == "C"

    def test_reuses_the_same_entity_on_repeat_saves(self):
        first = save_board("EMP-1", [_note_item()])
        second = save_board("EMP-1", [_note_item(title="second")])
        assert first["id"] == second["id"]
        assert len(ledger.get_all()) == 1

    def test_non_dict_item_dropped(self):
        result = save_board("EMP-1", ["not-a-dict", _note_item()])
        assert len(result["items"]) == 1

    def test_items_not_a_list_yields_empty(self):
        result = save_board("EMP-1", "not-a-list")
        assert result["items"] == []

    def test_unknown_kind_dropped(self):
        bad = _note_item()
        bad["kind"] = "not-a-real-kind"
        result = save_board("EMP-1", [bad])
        assert result["items"] == []

    def test_missing_id_generates_one(self):
        result = save_board("EMP-1", [_note_item(item_id=None)])
        assert result["items"][0]["id"] is not None
        assert result["items"][0]["id"].startswith("WITEM")

    def test_existing_id_preserved(self):
        result = save_board("EMP-1", [_note_item(item_id="WITEM-KEEP")])
        assert result["items"][0]["id"] == "WITEM-KEEP"

    def test_span_other_than_2_falls_back_to_1(self):
        result = save_board("EMP-1", [_note_item(span=99)])
        assert result["items"][0]["span"] == 1

    def test_span_2_preserved(self):
        result = save_board("EMP-1", [_note_item(span=2)])
        assert result["items"][0]["span"] == 2

    def test_order_falls_back_to_enumeration_index_when_not_an_int(self):
        items = [_note_item(order="bad", title="a"), _note_item(order="bad", title="b")]
        result = save_board("EMP-1", items)
        orders = sorted(i["order"] for i in result["items"])
        assert orders == [0, 1]

    def test_items_sorted_by_order(self):
        items = [
            _note_item(title="third", order=2),
            _note_item(title="first", order=0),
            _note_item(title="second", order=1),
        ]
        result = save_board("EMP-1", items)
        titles = [i["title"] for i in result["items"]]
        assert titles == ["first", "second", "third"]

    def test_created_at_defaults_when_missing(self):
        item = _note_item()
        assert "created_at" not in item
        result = save_board("EMP-1", [item])
        assert result["items"][0]["created_at"] is not None

    def test_created_at_preserved_when_a_string(self):
        item = _note_item()
        item["created_at"] = "2020-01-01T00:00:00+00:00"
        result = save_board("EMP-1", [item])
        assert result["items"][0]["created_at"] == "2020-01-01T00:00:00+00:00"

    def test_x_y_default_to_zero_when_missing_or_invalid(self):
        result = save_board("EMP-1", [_note_item(x=None, y=None)])
        assert result["items"][0]["x"] == 0
        assert result["items"][0]["y"] == 0

    def test_x_y_preserved_when_numeric(self):
        result = save_board("EMP-1", [_note_item(x=125, y=300.5)])
        assert result["items"][0]["x"] == 125.0
        assert result["items"][0]["y"] == 300.5

    def test_x_y_invalid_type_falls_back_to_zero(self):
        item = _note_item()
        item["x"] = "not-a-number"
        result = save_board("EMP-1", [item])
        assert result["items"][0]["x"] == 0

    def test_updated_at_is_set(self):
        result = save_board("EMP-1", [_note_item()])
        assert result["updated_at"] is not None

    def test_saving_empty_item_list_clears_the_board(self):
        save_board("EMP-1", [_note_item()])
        result = save_board("EMP-1", [])
        assert result["items"] == []


class TestChartItemCleaning:

    def test_missing_department_dropped(self):
        item = _chart_item()
        item["department"] = None
        result = save_board("EMP-1", [item])
        assert result["items"] == []

    def test_missing_item_key_dropped(self):
        item = _chart_item()
        item["item_key"] = None
        result = save_board("EMP-1", [item])
        assert result["items"] == []

    def test_department_not_a_string_dropped(self):
        item = _chart_item()
        item["department"] = 123
        result = save_board("EMP-1", [item])
        assert result["items"] == []

    def test_valid_chart_item_preserved(self):
        result = save_board("EMP-1", [_chart_item(department="Sales", item_key="overview")])
        item = result["items"][0]
        assert item["kind"] == "chart"
        assert item["department"] == "Sales"
        assert item["item_key"] == "overview"

    def test_invalid_chart_type_falls_back_to_bar(self):
        result = save_board("EMP-1", [_chart_item(chart_type="not-a-type")])
        assert result["items"][0]["chart_type"] == "bar"

    @pytest.mark.parametrize("chart_type", CHART_TYPES)
    def test_valid_chart_types_preserved(self, chart_type):
        result = save_board("EMP-1", [_chart_item(chart_type=chart_type)])
        assert result["items"][0]["chart_type"] == chart_type

    def test_field_path_coerced_to_strings(self):
        item = _chart_item(field_path=["a", 1, "b"])
        result = save_board("EMP-1", [item])
        assert result["items"][0]["field_path"] == ["a", "1", "b"]

    def test_field_path_not_a_list_becomes_empty(self):
        item = _chart_item()
        item["field_path"] = "not-a-list"
        result = save_board("EMP-1", [item])
        assert result["items"][0]["field_path"] == []

    def test_selected_columns_filters_non_strings(self):
        item = _chart_item(selected_columns=["ok", 123, "also-ok"])
        result = save_board("EMP-1", [item])
        assert result["items"][0]["selected_columns"] == ["ok", "also-ok"]

    def test_source_label_defaults_to_empty_string(self):
        item = _chart_item()
        item["source_label"] = 999
        result = save_board("EMP-1", [item])
        assert result["items"][0]["source_label"] == ""

    def test_label_column_defaults_to_empty_string(self):
        item = _chart_item()
        item["label_column"] = 999
        result = save_board("EMP-1", [item])
        assert result["items"][0]["label_column"] == ""

    def test_note_text_and_ai_generated_preserved_on_chart_item(self):
        result = save_board("EMP-1", [_chart_item(note_text="Explains the chart", note_ai_generated=True)])
        item = result["items"][0]
        assert item["note_text"] == "Explains the chart"
        assert item["note_ai_generated"] is True

    def test_note_text_defaults_to_empty_string_when_not_a_string(self):
        item = _chart_item()
        item["note_text"] = 123
        result = save_board("EMP-1", [item])
        assert result["items"][0]["note_text"] == ""

    def test_note_ai_generated_coerced_to_bool(self):
        result = save_board("EMP-1", [_chart_item(note_ai_generated=1)])
        assert result["items"][0]["note_ai_generated"] is True


class TestNoteItemCleaning:

    def test_valid_note_item_preserved(self):
        result = save_board("EMP-1", [_note_item(title="Title", text="Body", source_context="From chat")])
        item = result["items"][0]
        assert item["kind"] == "note"
        assert item["title"] == "Title"
        assert item["text"] == "Body"
        assert item["source_context"] == "From chat"

    def test_title_defaults_to_empty_string_when_not_a_string(self):
        item = _note_item()
        item["title"] = 123
        result = save_board("EMP-1", [item])
        assert result["items"][0]["title"] == ""

    def test_text_defaults_to_empty_string_when_not_a_string(self):
        item = _note_item()
        item["text"] = None
        result = save_board("EMP-1", [item])
        assert result["items"][0]["text"] == ""

    def test_source_context_defaults_to_empty_string_when_not_a_string(self):
        item = _note_item()
        item["source_context"] = 123
        result = save_board("EMP-1", [item])
        assert result["items"][0]["source_context"] == ""

    def test_ai_generated_coerced_to_bool(self):
        result = save_board("EMP-1", [_note_item(ai_generated=1)])
        assert result["items"][0]["ai_generated"] is True

    def test_note_item_has_no_chart_only_fields(self):
        result = save_board("EMP-1", [_note_item()])
        item = result["items"][0]
        assert "department" not in item
        assert "chart_type" not in item


# ---------------------------------------------------------------------------
# ACL layer -- get_workspace_board_api / save_workspace_board_api
# ---------------------------------------------------------------------------

class TestOwnBoardApi:

    def test_get_matches_direct_call(self):
        assert get_workspace_board_api("EMP-1") == get_board("EMP-1")

    def test_save_matches_direct_call(self):
        result = save_workspace_board_api("EMP-1", [_note_item()])
        assert result["items"][0]["kind"] == "note"


# ---------------------------------------------------------------------------
# ACL layer -- get_shared_workspace_board_api
# ---------------------------------------------------------------------------

class TestSharedWorkspaceBoardApi:

    def test_owner_viewing_their_own_board_always_works(self):
        save_board("EMP-1", [_note_item()])
        result = get_shared_workspace_board_api("EMP-1", SALES, "EMP-1")
        assert result["items"]

    def test_owner_viewing_own_board_works_even_with_no_pin_shared(self):
        result = get_shared_workspace_board_api("EMP-1", SALES, "EMP-1")
        assert "error" not in result

    def test_non_owner_denied_without_any_shared_pin(self):
        save_board("EMP-1", [_note_item()])
        result = get_shared_workspace_board_api("EMP-2", SALES, "EMP-1")
        assert result == {"error": "Forbidden: this Workspace hasn't been shared with you."}

    def test_non_owner_denied_when_pin_is_a_different_kind(self):
        save_board("EMP-1", [_note_item()])
        create_pin("EMP-1", kind="dashboard", ref_id="EMP-1", label="Not the board", tag=None, visibility="all")
        result = get_shared_workspace_board_api("EMP-2", SALES, "EMP-1")
        assert "error" in result

    def test_non_owner_denied_when_pin_ref_id_is_a_different_employee(self):
        save_board("EMP-1", [_note_item()])
        create_pin("EMP-1", kind="workspace_board", ref_id="EMP-999", label="Wrong owner", tag=None, visibility="all")
        result = get_shared_workspace_board_api("EMP-2", SALES, "EMP-1")
        assert "error" in result

    def test_non_owner_allowed_when_pin_shared_with_all(self):
        save_board("EMP-1", [_note_item()])
        create_pin("EMP-1", kind="workspace_board", ref_id="EMP-1", label="My Workspace", tag=None, visibility="all")
        result = get_shared_workspace_board_api("EMP-2", SALES, "EMP-1")
        assert "error" not in result
        assert len(result["items"]) == 1

    def test_non_owner_allowed_when_shared_with_their_specific_role(self):
        save_board("EMP-1", [_note_item()])
        create_pin("EMP-1", kind="workspace_board", ref_id="EMP-1", label="My Workspace", tag=None,
                   visibility="roles", roles=[SALES])
        result = get_shared_workspace_board_api("EMP-2", SALES, "EMP-1")
        assert "error" not in result

    def test_non_owner_denied_when_shared_with_a_different_role(self):
        save_board("EMP-1", [_note_item()])
        create_pin("EMP-1", kind="workspace_board", ref_id="EMP-1", label="My Workspace", tag=None,
                   visibility="roles", roles=[FINANCE])
        result = get_shared_workspace_board_api("EMP-2", SALES, "EMP-1")
        assert "error" in result

    def test_admin_denied_when_no_pin_exists_at_all(self):
        # get_shared_workspace_board_api only ever grants access through a real,
        # existing pin (via list_pins_for_role) -- ADMIN's "sees everything" rule
        # only affects visibility of pins that actually exist, it is not a blanket
        # bypass of "a pin must exist naming this owner's board" in the first place.
        save_board("EMP-1", [_note_item()])
        result = get_shared_workspace_board_api("EMP-2", ADMIN, "EMP-1")
        assert "error" in result

    def test_admin_sees_a_pin_shared_with_a_different_role_that_sales_could_not(self):
        save_board("EMP-1", [_note_item()])
        create_pin("EMP-1", kind="workspace_board", ref_id="EMP-1", label="My Workspace", tag=None,
                   visibility="roles", roles=[FINANCE])

        denied = get_shared_workspace_board_api("EMP-2", SALES, "EMP-1")
        assert "error" in denied

        allowed = get_shared_workspace_board_api("EMP-3", ADMIN, "EMP-1")
        assert "error" not in allowed

    def test_returns_an_empty_board_shape_when_owner_has_never_saved_one(self):
        create_pin("EMP-1", kind="workspace_board", ref_id="EMP-1", label="Empty share", tag=None, visibility="all")
        result = get_shared_workspace_board_api("EMP-2", SALES, "EMP-1")
        assert result == {"id": None, "items": [], "updated_at": None}


# ---------------------------------------------------------------------------
# snapshot item kind (Workspace grab-all, 2026-07-23)
# ---------------------------------------------------------------------------

def _snapshot(**kw):
    base = {
        "id": None, "kind": "snapshot", "order": 0, "title": "Q3 Sales",
        "data_kind": "table", "columns": ["Rep", "Units"],
        "rows": [{"Rep": "Sam", "Units": 12}, {"Rep": "Lee", "Units": 9}],
        "text": "", "source_label": "Sales · Reporting", "source_context": "",
    }
    base.update(kw)
    return base


class TestSnapshotCleaning:
    def test_snapshot_is_a_valid_kind_and_round_trips(self):
        board = save_board("EMP-1", [_snapshot()])
        item = board["items"][0]
        assert item["kind"] == "snapshot"
        assert item["data_kind"] == "table"
        assert item["columns"] == ["Rep", "Units"]
        assert item["rows"] == [{"Rep": "Sam", "Units": 12}, {"Rep": "Lee", "Units": 9}]
        assert item["title"] == "Q3 Sales"
        assert item["source_label"] == "Sales · Reporting"
        assert item["captured_at"]  # stamped

    def test_rows_are_projected_onto_declared_columns(self):
        board = save_board("EMP-1", [_snapshot(columns=["Rep"], rows=[{"Rep": "Sam", "Units": 12, "Extra": "x"}])])
        assert board["items"][0]["rows"] == [{"Rep": "Sam"}]

    def test_non_primitive_cells_are_stringified(self):
        board = save_board("EMP-1", [_snapshot(columns=["A"], rows=[{"A": {"nested": 1}}])])
        assert isinstance(board["items"][0]["rows"][0]["A"], str)

    def test_rows_capped_at_100(self):
        rows = [{"Rep": f"R{i}", "Units": i} for i in range(250)]
        board = save_board("EMP-1", [_snapshot(rows=rows)])
        assert len(board["items"][0]["rows"]) == 100

    def test_columns_capped_at_30(self):
        cols = [f"c{i}" for i in range(60)]
        board = save_board("EMP-1", [_snapshot(columns=cols, rows=[])])
        assert len(board["items"][0]["columns"]) == 30

    def test_unknown_data_kind_defaults_to_table(self):
        board = save_board("EMP-1", [_snapshot(data_kind="bogus")])
        assert board["items"][0]["data_kind"] == "table"

    def test_text_snapshot(self):
        board = save_board("EMP-1", [_snapshot(data_kind="text", text="A captured paragraph.")])
        assert board["items"][0]["data_kind"] == "text"
        assert board["items"][0]["text"] == "A captured paragraph."

    def test_text_capped(self):
        board = save_board("EMP-1", [_snapshot(data_kind="text", text="x" * 50000)])
        assert len(board["items"][0]["text"]) == 20000


class TestAddWorkspaceItem:
    def test_add_creates_a_board_when_none_exists(self):
        result = add_workspace_item("EMP-1", _snapshot())
        assert len(result["items"]) == 1
        assert result["items"][0]["kind"] == "snapshot"

    def test_add_appends_after_existing_items_with_next_order(self):
        save_board("EMP-1", [_note_item(order=0), _note_item(order=1)])
        result = add_workspace_item("EMP-1", _snapshot())
        assert len(result["items"]) == 3
        assert result["items"][-1]["order"] == 2
        assert result["items"][-1]["kind"] == "snapshot"

    def test_add_forces_order_to_end_even_if_caller_passes_zero(self):
        save_board("EMP-1", [_note_item(order=0)])
        result = add_workspace_item("EMP-1", _snapshot(order=0))
        # appended item wins the highest order, not a collision at 0
        orders = sorted(i["order"] for i in result["items"])
        assert orders == [0, 1]

    def test_add_rejects_non_dict(self):
        assert "error" in add_workspace_item("EMP-1", "nope")

    def test_add_rejects_unknown_kind(self):
        assert "error" in add_workspace_item("EMP-1", {"kind": "bogus"})

    def test_add_api_delegates(self):
        result = add_workspace_item_api("EMP-1", _snapshot())
        assert len(result["items"]) == 1

    def test_added_snapshot_persists_and_is_readable(self):
        add_workspace_item("EMP-1", _snapshot(title="Grabbed"))
        board = get_board("EMP-1")
        assert board["items"][0]["title"] == "Grabbed"
