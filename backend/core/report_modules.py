"""
core/report_modules.py -- the report-module catalog engine behind each department's
customizable Reporting dashboard (session 73). Sam: "lets go ahead and set all the
reporting to be graph based... they should also be able to snap them into place to
create their own dashboards... We want them to have a good snapshot of that department
in a way that they can put on a full screen or print out. This is for each department."

Same one-catalog/one-engine pattern as core/workflow_tab_data.py's REAL_SOURCES and
core/menu_data.py's MENU_SOURCES -- not 9 bespoke modules. Every department's existing
"reporting" Top Menu item (core/menu_catalog.py, core/menu_data.py's MENU_SOURCES) was
already a curated, department-specific rollup dict (see e.g.
core/operations_menu.py's reporting()) -- a dict of named sections
("operational_performance", "inventory_performance", ...), each itself a dict of real
KPI fields and/or a nested list of real records. That's exactly the right grain for a
"module" in a drag-and-drop report builder: one card per section, already curated by an
earlier session to be "a good snapshot of that department," not a fresh data model.

This module does zero new data computation -- it re-calls the department's existing
reporting() fetch function (via core/menu_data.get_menu_data) and reshapes its
top-level dict into a flat list of {module_key, label, data} module definitions. Which
fields within a module's `data` are chartable (numeric scalars, or a nested
list-of-objects with numeric columns) is deliberately left for the frontend to derive --
components/MenuDashPanel.tsx's ObjectListView already has that exact
numeric-column/label-column detection logic for its Visualize toggle, so
components/ReportDashboardModule.tsx reuses the same approach instead of a second,
divergent classifier living on the backend.

Extended session 77 (Sam: "in all overview dashes in the submenus for all departments,
I'd like that to be a very BI visual glance as a default that gives the top metrics
that that department wants to see... Lets connect it to reporting in that if you
create a report that you want to show in overview, you can select 'show in overview'
and it shows up in available modules at the bottom") with get_overview_modules() and
default_overview_modules(), the Overview-board equivalents. overview()'s return shape
is NOT structurally identical to reporting()'s -- confirmed by reading
core/operations_menu.py's overview() vs reporting() directly -- it's predominantly
flat scalar KPI fields (e.g. `"units_in_recon": 12`) rather than reporting()'s nested
per-section dicts, so get_report_modules's dict-values-only reshape can't be reused
verbatim: get_overview_modules also wraps a bare scalar/list field into its own
single-KPI module (`{"value": 12}`), one module per top-level KPI, which is exactly the
"top metrics... at a glance" grain Sam described.
"""

from core.menu_catalog import get_department_menu
from core.menu_data import get_menu_data
from core.dashboard_layouts import get_layout

DEFAULT_PALETTE = ["#3FBCC4", "#2B68AB", "#FBCF09", "#EE3C25"]


def _prettify(key):
    return key.replace("_", " ").replace("-", " ").title()


def _is_chartable(data):
    values = list(data.values())
    if any(isinstance(v, (int, float)) and not isinstance(v, bool) for v in values):
        return True
    return any(
        isinstance(v, list) and len(v) > 0 and all(isinstance(item, dict) for item in v)
        for v in values
    )


def get_report_modules(role, department):
    """The Reporting dashboard's module catalog + live data for one department, in one
    call -- both come from the same underlying reporting() fetch, so there's no reason
    to make the frontend round-trip twice. Returns {"error": ...} for a department with
    no catalogued Reporting item (every department not yet rolled out into
    core/menu_catalog.py) or if the underlying fetch itself errors."""

    items = get_department_menu(department)

    if not any(item["key"] == "reporting" for item in items):
        return {"error": f"No Reporting item catalogued yet for department '{department}'."}

    data = get_menu_data(role, department, "reporting")

    if isinstance(data, dict) and set(data.keys()) == {"error"}:
        return data

    modules = []

    if isinstance(data, dict):
        for section_key, section_val in data.items():
            if not isinstance(section_val, dict) or not section_val:
                continue

            modules.append({
                "module_key": section_key,
                "label": _prettify(section_key),
                "data": section_val,
            })

    return {"department": department, "modules": modules}


def get_overview_modules(role, employee_id, department):
    """The Overview BI-glance board's module catalog for one department: one KPI
    module per top-level field of that department's existing overview() rollup
    (core/menu_data.get_menu_data(role, department, "overview")), PLUS any Reporting
    section the signed-in employee has flagged "Show in Overview" on their own
    Reporting board (core/dashboard_layouts.get_layout's show_in_overview flag).
    Returns {"error": ...} for a department with no catalogued Overview item, or if the
    underlying fetch itself errors."""

    items = get_department_menu(department)

    if not any(item["key"] == "overview" for item in items):
        return {"error": f"No Overview item catalogued yet for department '{department}'."}

    data = get_menu_data(role, department, "overview")

    if isinstance(data, dict) and set(data.keys()) == {"error"}:
        return data

    modules = []

    if isinstance(data, dict):
        for field_key, field_val in data.items():
            # "not_yet_tracked" is this codebase's established honest-gap marker
            # (core/operations_menu.py and every other *_menu.py module) -- a note
            # about missing data, not a metric itself, so it never becomes a KPI card.
            if field_key in ("error", "not_yet_tracked") or field_val is None:
                continue

            if isinstance(field_val, dict):
                if not field_val:
                    continue
                module_data = field_val
            elif isinstance(field_val, list):
                if not field_val:
                    continue
                module_data = {"items": field_val}
            else:
                # A bare scalar KPI (int/float/str/bool) -- wrap it so every module's
                # `data` stays a dict, matching get_report_modules's contract that the
                # frontend's classify()/JsonValue rendering already relies on.
                module_data = {"value": field_val}

            modules.append({
                "module_key": field_key,
                "label": _prettify(field_key),
                "data": module_data,
                "_source": "kpi",
            })

    # Fold in any Reporting-board section the employee flagged "Show in Overview."
    reporting_layout = get_layout(employee_id, department, board="reporting")
    flagged_keys = {
        m["module_key"] for m in reporting_layout.get("modules", []) if m.get("show_in_overview")
    }

    if flagged_keys:
        reporting_catalog = get_report_modules(role, department)
        if isinstance(reporting_catalog, dict) and "modules" in reporting_catalog:
            existing_keys = {m["module_key"] for m in modules}
            for entry in reporting_catalog["modules"]:
                if entry["module_key"] in flagged_keys and entry["module_key"] not in existing_keys:
                    modules.append({**entry, "_source": "reporting"})

    return {"department": department, "modules": modules}


def default_overview_modules(role, employee_id, department):
    """Auto-populates a department's Overview board the first time an employee opens
    it, before they've customized anything -- Sam's own answer when asked what Overview
    should show by default was "Auto-populate real KPIs." Seeds one module instance per
    KPI-seed catalog entry only, in the same order overview() returned them; the
    opt-in flagged-Reporting entries stay available-but-unplaced in the tray until the
    employee deliberately drags one in, same as a fresh Reporting board always starts
    empty. Returns plain module-instance dicts shaped for
    core/dashboard_layouts._clean_module to validate -- this function does not itself
    persist anything, core/dashboard_layouts_api.py decides whether/when to save it."""

    catalog = get_overview_modules(role, employee_id, department)
    if not isinstance(catalog, dict) or "modules" not in catalog:
        return []

    seeded = []
    kpi_entries = [m for m in catalog["modules"] if m.get("_source") == "kpi"]

    for i, entry in enumerate(kpi_entries):
        seeded.append({
            "id": None,
            "module_key": entry["module_key"],
            "mode": "graph" if _is_chartable(entry["data"]) else "text",
            "chart_type": "bar",
            "color": DEFAULT_PALETTE[i % len(DEFAULT_PALETTE)],
            "span": 1,
            "order": i,
            "fields": [],
            "show_in_overview": False,
        })

    return seeded
