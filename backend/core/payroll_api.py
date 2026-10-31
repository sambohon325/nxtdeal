"""
ACL for payroll (Phase 5, 2026-07-25). Pay plans, payroll runs, and viewing the full roster
of statements are ADMIN/OPERATIONS (payroll is a management function). Clocking in/out is
self-service (any authenticated employee punches their own clock). An employee can view
their own pay statements.
"""

from core import payroll
from core.permissions import ADMIN, OPERATIONS

_ADMIN_ROLES = (ADMIN, OPERATIONS)


def _is_admin(role):
    return role in _ADMIN_ROLES


def set_pay_plan_api(role, employee_id, plan_type, hourly_rate=0.0, annual_salary=0.0,
                     per_deal_commission=0.0, pct_front_gross=0.0, state="TX"):
    if not _is_admin(role):
        return {"error": "Admin/Operations role required to set pay plans"}
    return payroll.set_pay_plan(employee_id, plan_type, hourly_rate=hourly_rate, annual_salary=annual_salary,
                                per_deal_commission=per_deal_commission, pct_front_gross=pct_front_gross, state=state)


def get_pay_plan_api(role, employee_id):
    if not _is_admin(role):
        return {"error": "Admin/Operations role required to view pay plans"}
    return payroll.get_pay_plan(employee_id)


def clock_in_api(role, employee_id):
    # Self-service: the caller clocks their own id.
    return payroll.clock_in(employee_id)


def clock_out_api(role, employee_id):
    return payroll.clock_out(employee_id)


def get_open_entry_api(role, employee_id):
    return payroll.get_open_entry(employee_id)


def run_payroll_api(role, employee_id, period_start, period_end, employee_ids=None):
    if not _is_admin(role):
        return {"error": "Admin/Operations role required to run payroll"}
    return payroll.run_payroll(period_start, period_end, employee_id, employee_ids=employee_ids)


def list_payroll_runs_api(role):
    if not _is_admin(role):
        return {"error": "Admin/Operations role required to view payroll runs"}
    return {"runs": payroll.list_payroll_runs()}


def list_pay_statements_api(role, employee_id, target_employee_id=None, run_id=None):
    # Admin can see everyone; a non-admin can only see their own statements.
    if not _is_admin(role):
        return {"statements": payroll.list_pay_statements(employee_id=employee_id)}
    return {"statements": payroll.list_pay_statements(employee_id=target_employee_id, run_id=run_id)}


def get_pay_statement_api(role, employee_id, statement_id):
    stmt = payroll.get_pay_statement(statement_id)
    if isinstance(stmt, dict) and stmt.get("error"):
        return stmt
    if not _is_admin(role) and stmt.get("employee_id") != employee_id:
        return {"error": "You can only view your own pay statements"}
    return stmt
