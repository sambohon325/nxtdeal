"""
core/workspace_board.py -- per-employee OneNote-style Workspace board persistence
(session 76). Sam: "the workspace needs to be dynamic in the sense that yes you can add
graphs, but what other knowledge do you want to add?... it needs a feature where you can
add in ai generated content explaining the graph... You should be able to prompt 'in the
workspace window'... and be able to add in a paragraph. The idea is something like
microsoft OneNote in that its a very dynamic workspace to add information in, and should
be able to pull from dashes, reporting and from input on the chat."

Mirrors core/dashboard_layouts.py's pattern almost exactly (same module author, same
session's sibling feature) with one real difference: a WorkspaceBoard is keyed by
employee_id ALONE, not (employee_id, department) -- "your workspace" is one personal
canvas that can mix items pulled from any department, not a per-department dashboard.

Two item kinds, both ordinary dicts inside one `items` list on the board entity:
  - "chart": a live reference (department/item_key/field_path/chart_type/etc, the same
    shape frontend/lib/useVisualizationWorkspace.ts's VisualizationDraft already used)
    -- re-fetched live from the graph at render time, never a frozen snapshot, same
    "always reflects the current graph" rule dashboard_layouts.py follows.
  - "note": freeform or AI-generated text -- title + body + an optional source_context
    label (e.g. "From chat", or the sourceLabel of whatever chart it was written about).
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import WORKSPACE_BOARD
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 76) --
# every real personal Workspace board (charts, notes, canvas positions) an employee
# ever saved had been silently discarded on server restart. Fixed below.

ITEM_KINDS = ("chart", "note", "snapshot")
CHART_TYPES = ("bar", "line", "pie")

# "snapshot" (2026-07-23, Workspace grab-all) -- Sam: "All framable data (reporting
# modules, individual details, etc) need to be grabbable and be able to pull into or be
# added to workspace... across the entire platform / all dashes / all relevant detail."
# Unlike a "chart" item (a LIVE department+item_key reference re-fetched from /menu/data),
# a snapshot is a FROZEN capture of whatever data the user was looking at anywhere in the
# app -- a report table, a detail record, a KPI row -- so it works for every surface, not
# just menu-board data. Honest by construction: it carries captured_at and is rendered as
# "captured <when>", never presented as live. Two shapes: a "table" (columns + rows) or
# "text". Bounded so one grab can't bloat the board entity.
SNAPSHOT_DATA_KINDS = ("table", "text")
_SNAPSHOT_MAX_COLUMNS = 30
_SNAPSHOT_MAX_ROWS = 100
_SNAPSHOT_MAX_TEXT = 20000
_SNAPSHOT_MAX_CELL = 2000


def _coerce_cell(value):
    """A snapshot cell must be a JSON-safe primitive. Anything else (a nested dict/list
    from a rich report row) is stringified and length-capped so the board entity stays
    small and always serializes."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:_SNAPSHOT_MAX_CELL]


def _now():
    return datetime.now(timezone.utc).isoformat()


def _find_board(employee_id):
    for entity in ledger.get_all().values():
        if (
            entity.entity_type == WORKSPACE_BOARD
            and entity.attributes.get("employee_id") == employee_id
        ):
            return entity
    return None


def _clean_item(raw, fallback_order):
    if not isinstance(raw, dict):
        return None

    kind = raw.get("kind")
    if kind not in ITEM_KINDS:
        return None

    item_id = raw.get("id")
    if not item_id or not isinstance(item_id, str):
        item_id = id_generator.generate("WITEM")

    span = raw.get("span")
    span = 2 if span == 2 else 1

    order = raw.get("order")
    order = order if isinstance(order, int) else fallback_order

    created_at = raw.get("created_at")
    if not isinstance(created_at, str):
        created_at = _now()

    # Free-form canvas position (session 76 follow-up -- Sam: "I want to be able to add
    # notes inside of workspace... and to be able to drag those around the canvas
    # similar to OneNote"). Plain numeric px offsets within the board's canvas area;
    # unlike everything else on a chart item these aren't a "live reference" to
    # anything -- just where the user last dropped the box -- so no re-fetch/resolution
    # is needed, only basic type/range cleaning. Missing/invalid values fall back to 0,0
    # rather than erroring -- the frontend already assigns a cascading default position
    # to brand new items before they're ever saved, so 0,0 here only shows up for
    # malformed input.
    x = raw.get("x")
    x = float(x) if isinstance(x, (int, float)) else 0
    y = raw.get("y")
    y = float(y) if isinstance(y, (int, float)) else 0

    item = {
        "id": item_id,
        "kind": kind,
        "span": span,
        "order": order,
        "created_at": created_at,
        "x": x,
        "y": y,
    }

    if kind == "chart":
        department = raw.get("department")
        item_key = raw.get("item_key")
        if not isinstance(department, str) or not isinstance(item_key, str):
            return None

        field_path = raw.get("field_path")
        field_path = [str(p) for p in field_path] if isinstance(field_path, list) else []

        chart_type = raw.get("chart_type")
        if chart_type not in CHART_TYPES:
            chart_type = "bar"

        selected_columns = raw.get("selected_columns")
        selected_columns = (
            [c for c in selected_columns if isinstance(c, str)]
            if isinstance(selected_columns, list)
            else []
        )

        item.update({
            "department": department,
            "item_key": item_key,
            "field_path": field_path,
            "source_label": raw.get("source_label") if isinstance(raw.get("source_label"), str) else "",
            "label_column": raw.get("label_column") if isinstance(raw.get("label_column"), str) else "",
            "chart_type": chart_type,
            "selected_columns": selected_columns,
            # Session 76 second follow-up -- Sam: "create a chart, and then create a
            # note under it explaining what it is, and save that as one single piece of
            # knowledge." A chart's explanatory note now lives ON the chart item itself
            # (not as a second, separately-positioned board item) so the pair is always
            # one record -- one card on the canvas, one pin when saved to Knowledge.
            "note_text": raw.get("note_text") if isinstance(raw.get("note_text"), str) else "",
            "note_ai_generated": bool(raw.get("note_ai_generated")),
        })

    elif kind == "snapshot":
        data_kind = raw.get("data_kind")
        if data_kind not in SNAPSHOT_DATA_KINDS:
            data_kind = "table"

        captured_at = raw.get("captured_at")
        if not isinstance(captured_at, str):
            captured_at = created_at

        # Columns: strings only, capped.
        raw_cols = raw.get("columns")
        columns = (
            [str(c) for c in raw_cols][:_SNAPSHOT_MAX_COLUMNS]
            if isinstance(raw_cols, list)
            else []
        )

        # Rows: list of dicts keyed by column -> coerced primitive, capped in both
        # dimensions. Non-dict rows are dropped rather than guessed at.
        rows = []
        raw_rows = raw.get("rows")
        if isinstance(raw_rows, list):
            for r in raw_rows[:_SNAPSHOT_MAX_ROWS]:
                if not isinstance(r, dict):
                    continue
                if columns:
                    rows.append({c: _coerce_cell(r.get(c)) for c in columns})
                else:
                    rows.append({str(k): _coerce_cell(v) for k, v in list(r.items())[:_SNAPSHOT_MAX_COLUMNS]})

        text = raw.get("text")
        item.update({
            "title": raw.get("title") if isinstance(raw.get("title"), str) else "",
            "source_label": raw.get("source_label") if isinstance(raw.get("source_label"), str) else "",
            "source_context": raw.get("source_context") if isinstance(raw.get("source_context"), str) else "",
            "captured_at": captured_at,
            "data_kind": data_kind,
            "columns": columns,
            "rows": rows,
            "text": (text[:_SNAPSHOT_MAX_TEXT] if isinstance(text, str) else ""),
            "note_text": raw.get("note_text") if isinstance(raw.get("note_text"), str) else "",
            "note_ai_generated": bool(raw.get("note_ai_generated")),
        })

    else:  # note
        text = raw.get("text")
        item.update({
            "title": raw.get("title") if isinstance(raw.get("title"), str) else "",
            "text": text if isinstance(text, str) else "",
            "source_context": raw.get("source_context") if isinstance(raw.get("source_context"), str) else "",
            "ai_generated": bool(raw.get("ai_generated")),
        })

    return item


def _clean_items(items):
    if not isinstance(items, list):
        return []

    cleaned = [_clean_item(i, idx) for idx, i in enumerate(items)]
    cleaned = [i for i in cleaned if i is not None]
    cleaned.sort(key=lambda i: i["order"])

    return cleaned


def _serialize(entity):
    attrs = entity.attributes
    return {
        "id": entity.id,
        "items": attrs.get("items") or [],
        "updated_at": attrs.get("updated_at"),
    }


def get_board(employee_id):
    """An empty board (`items: []`) is a valid, expected state for anyone who's never
    added anything yet -- same "empty is fine, not an error" convention as
    dashboard_layouts.get_layout()."""

    entity = _find_board(employee_id)

    if not entity:
        return {"id": None, "items": [], "updated_at": None}

    return _serialize(entity)


def save_board(employee_id, items):
    """Full replace, not a patch -- the frontend already holds the whole board in memory
    to render it, same convention as dashboard_layouts.save_layout()."""

    entity = _find_board(employee_id)
    clean = _clean_items(items)

    if entity:
        entity.attributes["items"] = clean
        entity.attributes["updated_at"] = _now()
    else:
        entity = Entity(
            id=id_generator.generate("WBOARD"),
            entity_type=WORKSPACE_BOARD,
            attributes={
                "employee_id": employee_id,
                "items": clean,
                "updated_at": _now(),
            },
        )
        ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return _serialize(entity)


def add_workspace_item(employee_id, item):
    """Append ONE item to the employee's board (creating the board if needed) and
    persist. Unlike save_board()'s full replace, this is for the "grab this into my
    workspace" affordance fired from ANYWHERE in the app -- the caller (a report table,
    a detail view) doesn't hold the whole board in memory, it just hands over the one
    frame it wants captured. The new item is appended after the current last item's
    order. Returns the full updated board, or a real {"error": ...} if the item is
    malformed."""

    if not isinstance(item, dict):
        return {"error": "A workspace item must be an object."}

    entity = _find_board(employee_id)
    existing = list(entity.attributes.get("items")) if entity else []

    next_order = (max((i.get("order", 0) for i in existing), default=-1) + 1)
    cleaned = _clean_item(item, next_order)
    if cleaned is None:
        return {"error": "That item could not be added (unknown kind or missing required fields)."}
    # Force it to the end regardless of any order the caller passed.
    cleaned["order"] = next_order

    if entity:
        entity.attributes["items"] = existing + [cleaned]
        entity.attributes["updated_at"] = _now()
    else:
        entity = Entity(
            id=id_generator.generate("WBOARD"),
            entity_type=WORKSPACE_BOARD,
            attributes={
                "employee_id": employee_id,
                "items": [cleaned],
                "updated_at": _now(),
            },
        )
        ledger.add_entity(entity)

    save_graph(GRAPH_PATH)
    return _serialize(entity)
