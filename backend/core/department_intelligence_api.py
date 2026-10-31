"""
ACL layer for Department Intelligence (2026-07-13, session 35; renamed from
core/bumper_bi_api.py session 68 -- Sam: "i want to take out the term 'bumper bi'").
Sam's access decision: ADMIN, OPERATIONS, and FINANCE can open every Department
Intelligence dashboard -- broader than the roster/audit/compliance admin panels this was
asked to sit alongside (those stay ADMIN-only, see api/app.py's _require_admin),
narrower than ASSET/CAMPAIGN/WEBSITE/DEAL's broad internal read visibility, since this
is cross-department profit/margin data. Same three roles for every department --
Department Intelligence's whole pitch is cross-department visibility, so there's no
reason Finance should see the F&I dashboard but not Sales, unlike DASHBOARD_ACCESS's
narrower per-department splits elsewhere in core/permissions.py.
"""

from core.department_intelligence import (
    compute_department,
    list_departments,
    DEPARTMENTS
)

from core.kpi_snapshots import with_trend

from core.permissions import ADMIN, OPERATIONS, FINANCE


DEPT_INTEL_ROLES = (ADMIN, OPERATIONS, FINANCE)

_FORBIDDEN = {
    "error": "You don't have access to Department Intelligence with your current role — Admin, Operations, or Finance can open it."
}


def can_view_department_intelligence(role):

    return role in DEPT_INTEL_ROLES


def list_departments_api(role):

    if not can_view_department_intelligence(role):
        return _FORBIDDEN

    return list_departments()


def get_department_api(role, department):

    if not can_view_department_intelligence(role):
        return _FORBIDDEN

    if department not in DEPARTMENTS:
        return {"error": f"Unknown Department Intelligence department '{department}'"}

    payload = compute_department(department)

    kpis_with_trend = with_trend(department, payload["kpis"])

    # Frontend renders KPIs as an ordered list of cards, not a dict -- simpler than
    # requiring a fixed key order client-side.
    payload["kpis"] = list(kpis_with_trend.values())

    return payload
