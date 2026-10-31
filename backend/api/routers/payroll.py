"""
Payroll router (Phase 5, 2026-07-25): time clock, pay plans, payroll runs, pay statements.
Clock in/out is self-service; pay plans + runs are ADMIN/OPERATIONS.
"""

from fastapi import APIRouter, Header
from pydantic import BaseModel

from api.deps import _authenticate

from core.payroll_api import (
    set_pay_plan_api,
    get_pay_plan_api,
    clock_in_api,
    clock_out_api,
    get_open_entry_api,
    run_payroll_api,
    list_payroll_runs_api,
    list_pay_statements_api,
    get_pay_statement_api,
)


router = APIRouter()


class SetPayPlanRequest(BaseModel):

    plan_type: str
    hourly_rate: float = 0.0
    annual_salary: float = 0.0
    per_deal_commission: float = 0.0
    pct_front_gross: float = 0.0
    state: str = "TX"


class RunPayrollRequest(BaseModel):

    period_start: str
    period_end: str
    employee_ids: list | None = None


@router.post("/payroll/clock-in")
def payroll_clock_in(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return clock_in_api(payload["role"], payload["employee_id"])


@router.post("/payroll/clock-out")
def payroll_clock_out(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return clock_out_api(payload["role"], payload["employee_id"])


@router.get("/payroll/clock")
def payroll_clock_status(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return {"open_entry": get_open_entry_api(payload["role"], payload["employee_id"])}


@router.post("/payroll/plans/{target_employee_id}")
def payroll_set_plan(target_employee_id: str, request: SetPayPlanRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return set_pay_plan_api(
        payload["role"], target_employee_id, request.plan_type,
        hourly_rate=request.hourly_rate, annual_salary=request.annual_salary,
        per_deal_commission=request.per_deal_commission, pct_front_gross=request.pct_front_gross, state=request.state,
    )


@router.get("/payroll/plans/{target_employee_id}")
def payroll_get_plan(target_employee_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_pay_plan_api(payload["role"], target_employee_id)


@router.post("/payroll/runs")
def payroll_run(request: RunPayrollRequest, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return run_payroll_api(payload["role"], payload["employee_id"], request.period_start, request.period_end, request.employee_ids)


@router.get("/payroll/runs")
def payroll_list_runs(authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_payroll_runs_api(payload["role"])


@router.get("/payroll/statements")
def payroll_list_statements(employee_id: str = None, run_id: str = None, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return list_pay_statements_api(payload["role"], payload["employee_id"], target_employee_id=employee_id, run_id=run_id)


@router.get("/payroll/statements/{statement_id}")
def payroll_get_statement(statement_id: str, authorization: str = Header(None)):

    payload, error = _authenticate(authorization)
    if error:
        return error

    return get_pay_statement_api(payload["role"], payload["employee_id"], statement_id)
