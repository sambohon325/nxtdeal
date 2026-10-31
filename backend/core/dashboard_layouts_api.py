"""
core/dashboard_layouts_api.py -- thin API layer over core/dashboard_layouts.py, imported
directly into api/app.py's GET/POST /dashboard-layout route handlers, matching this
codebase's established core/*.py (business logic) + core/*_api.py (thin route layer)
convention. No extra ACL beyond "must be authenticated" (already enforced by
api/app.py's _authenticate before these are ever called) -- a dashboard layout is
purely personal, per-employee data, so every role manages its own freely.

Session 77: `board` threaded through both functions (defaults to "reporting" so every
existing frontend call site is unaffected). get_dashboard_layout_api also gained a
`role` param, used only when board="overview" and nothing has ever been saved for that
employee/department -- in that one case it auto-seeds the response from
core/report_modules.default_overview_modules() (Sam's own choice, "Auto-populate real
KPIs," when asked what a department's Overview should show before anyone customizes
it) rather than returning an empty board. The seeded response is NOT persisted here --
it stays unsaved (id=None) until the employee's first real edit triggers
ReportDashboardBuilder's existing debounced save, same as any other fresh board.
"""

from core.dashboard_layouts import get_layout, save_layout


def get_dashboard_layout_api(employee_id, department, board="reporting", role=None):
    layout = get_layout(employee_id, department, board)

    if board == "overview" and layout.get("id") is None and role is not None:
        from core.report_modules import default_overview_modules

        seeded = default_overview_modules(role, employee_id, department)
        if seeded:
            layout = {**layout, "modules": seeded}

    return layout


def save_dashboard_layout_api(employee_id, department, modules, board="reporting"):
    return save_layout(employee_id, department, modules, board)
