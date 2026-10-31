"""
core/dashboard_layouts.py -- per-employee, per-department dashboard layouts (session
73; extended session 77 with a `board` dimension). Sam: "lets also have each report /
graph have a toggle where you can switch to text mode... They should also be able to
snap them into place to create their own dashboards, and hide the modules (deactivate)
- they still need to be listed somewhere theres available modules list, they drag what
they want into the live area, there they can create several modules (all editable as
far as what parameters they want to show, what type of graph, colors, etc)."

Session 77 (Sam: "in all overview dashes in the submenus for all departments, I'd like
that to be a very BI visual glance as a default... same as the reporting, you should be
able to drag and drop them in a grid system"): a department no longer has one board, it
has one board per `board` key -- "reporting" (session 73's original board, still the
default for backward compatibility with every layout saved before this session) and
"overview" (this session's new BI-glance board). Both are the exact same grid/module
mechanics; only which catalog feeds their "available modules" tray differs (see
core/report_modules.py's get_report_modules vs get_overview_modules).

A DashboardLayout is an ordinary graph entity, one per (employee_id, department, board)
triple -- "their own dashboards" (Sam's own words), not a shared department-wide
layout, same no-separate-store rule as every other feature in this codebase (see
core/knowledge_pins.py for the precedent this follows almost verbatim). It only ever
stores which module *instances* are currently live on that employee's board and how
each is configured -- the underlying data for each module instance is always re-fetched
live from core/report_modules.py at render time, never frozen into the layout, so a
saved dashboard always reflects the current graph.

"Available modules" is not itself persisted anywhere -- it's simply
core/report_modules.py's full catalog for that department/board, minus whatever module
instances are already active in the layout. "Hiding" a module is just removing its
instance from `modules`; the underlying catalog entry it was built from is untouched
and immediately reappears in the available list. A module instance also carries a
`show_in_overview` flag (only meaningful on the "reporting" board) -- Sam: "if you
create a report that you want to show in overview, you can select 'show in overview'
and it shows up in available modules at the bottom" -- read by
core/report_modules.py's get_overview_modules() to fold a flagged Reporting section
into the Overview board's own available-modules tray.
"""

from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import DASHBOARD_LAYOUT
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real data-loss bug found and fixed (2026-07-18, codebase-wide save_graph() audit --
# see core/lead_conversion.py's docstring for the running list of confirmed instances).
# This module had ZERO save_graph() calls anywhere since it shipped (session 73) --
# every real custom dashboard layout an employee ever saved had been silently
# discarded on server restart. Fixed below.

MODES = ("graph", "text")
CHART_TYPES = ("bar", "line", "pie")
DEFAULT_COLOR = "#3FBCC4"
BOARDS = ("reporting", "overview")
DEFAULT_BOARD = "reporting"


def _now():
    return datetime.now(timezone.utc).isoformat()


def _find_layout(employee_id, department, board=DEFAULT_BOARD):
    for entity in ledger.get_all().values():
        if (
            entity.entity_type == DASHBOARD_LAYOUT
            and entity.attributes.get("employee_id") == employee_id
            and entity.attributes.get("department") == department
            # Layouts saved before session 77 have no "board" attribute at all --
            # treat that as "reporting" (the only board that existed then) so
            # existing employee dashboards keep working unchanged.
            and (entity.attributes.get("board") or DEFAULT_BOARD) == board
        ):
            return entity
    return None


def _clean_module(raw, fallback_order):
    if not isinstance(raw, dict):
        return None

    module_key = raw.get("module_key")
    if not module_key or not isinstance(module_key, str):
        return None

    instance_id = raw.get("id")
    if not instance_id or not isinstance(instance_id, str):
        instance_id = id_generator.generate("DASH")

    mode = raw.get("mode")
    if mode not in MODES:
        mode = "graph"

    chart_type = raw.get("chart_type")
    if chart_type not in CHART_TYPES:
        chart_type = "bar"

    color = raw.get("color")
    if not isinstance(color, str) or not color.startswith("#"):
        color = DEFAULT_COLOR

    span = raw.get("span")
    span = 2 if span == 2 else 1

    order = raw.get("order")
    order = order if isinstance(order, int) else fallback_order

    fields = raw.get("fields")
    fields = [f for f in fields if isinstance(f, str)] if isinstance(fields, list) else []

    show_in_overview = bool(raw.get("show_in_overview"))

    return {
        "id": instance_id,
        "module_key": module_key,
        "mode": mode,
        "chart_type": chart_type,
        "color": color,
        "span": span,
        "order": order,
        "fields": fields,
        "show_in_overview": show_in_overview,
    }


def _clean_modules(modules):
    if not isinstance(modules, list):
        return []

    cleaned = [_clean_module(m, i) for i, m in enumerate(modules)]
    cleaned = [m for m in cleaned if m is not None]
    cleaned.sort(key=lambda m: m["order"])

    return cleaned


def _serialize(entity):
    attrs = entity.attributes
    return {
        "id": entity.id,
        "department": attrs.get("department"),
        "board": attrs.get("board") or DEFAULT_BOARD,
        "modules": attrs.get("modules") or [],
        "updated_at": attrs.get("updated_at"),
    }


def get_layout(employee_id, department, board=DEFAULT_BOARD):
    """Always returns a layout shape, even if nothing has ever been saved -- an empty
    board (`modules: []`) is a valid, expected state, not an error. `board` defaults to
    "reporting" so every pre-session-77 call site (there's no other board that ever
    existed before) keeps working unchanged."""

    if board not in BOARDS:
        board = DEFAULT_BOARD

    entity = _find_layout(employee_id, department, board)

    if not entity:
        return {"id": None, "department": department, "board": board, "modules": [], "updated_at": None}

    return _serialize(entity)


def save_layout(employee_id, department, modules, board=DEFAULT_BOARD):
    """Full replace, not a patch -- the frontend always sends the complete current
    board state (matching how it already has to hold the whole layout in memory to
    render the grid), same convention as core/websites.py's page-section saves."""

    if board not in BOARDS:
        board = DEFAULT_BOARD

    entity = _find_layout(employee_id, department, board)
    clean = _clean_modules(modules)

    if entity:
        entity.attributes["modules"] = clean
        entity.attributes["updated_at"] = _now()
    else:
        entity = Entity(
            id=id_generator.generate("DASH"),
            entity_type=DASHBOARD_LAYOUT,
            attributes={
                "employee_id": employee_id,
                "department": department,
                "board": board,
                "modules": clean,
                "updated_at": _now(),
            },
        )
        ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return _serialize(entity)
