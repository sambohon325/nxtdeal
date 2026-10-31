"""
Payroll processing -- competitive roadmap Phase 5 (2026-07-25). Tekion and Reynolds bundle
payroll/HR; NXTDeal's Workforce module (core/workforce.py) did scheduling + time-off but
had no time-clock, no pay plans, and no pay computation (its own docstring says so). This
module is the missing payroll engine, built on the existing Employee roster and funded-deal
data:

  * Time clock: clock_in / clock_out produce real TimeEntry punches -> actual hours worked
    (Workforce only had SCHEDULED shifts, which can't produce a paycheck).
  * Pay plans: per-employee hourly / salary / commission / hybrid, stored on the Employee.
  * Deal commissions: a funded Deal is attributed to its `created_by` salesperson; commission
    is a flat per-deal amount and/or a percent of front gross (sale price - vehicle cost).
  * Payroll run: for a pay period, compute each employee's gross (hours x rate + prorated
    salary + commissions), withhold taxes, and generate a PayStatement (paycheck), all
    grouped under a PayrollRun.

Honest scope: tax withholding is a SIMPLIFIED flat-rate model (federal + a per-state rate
table + FICA), not a real payroll-tax engine (no W-4 allowances, no YTD brackets, no local
taxes). Every statement is stamped `tax_model: "simplified"`. This computes real, auditable
paychecks from real hours + real deals; a production deployment would swap the withholding
function for a real tax provider. Nothing is fabricated -- an employee with no pay plan or
no hours/commissions simply isn't paid.
"""

from datetime import datetime, timezone, date

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import EMPLOYEE, TIME_ENTRY, PAY_STATEMENT, PAYROLL_RUN, DEAL, VEHICLE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH


PLAN_TYPES = ("hourly", "salary", "commission", "hybrid")

# Simplified flat withholding. Federal + FICA are national; state comes from the table.
FEDERAL_RATE = 0.12
FICA_RATE = 0.0765
DEFAULT_STATE_RATE = 0.05
STATE_TAX_RATES = {
    "TX": 0.0, "FL": 0.0, "WA": 0.0, "NV": 0.0, "TN": 0.0, "SD": 0.0, "WY": 0.0, "AK": 0.0, "NH": 0.0,
    "CA": 0.093, "NY": 0.0685, "IL": 0.0495, "PA": 0.0307, "OH": 0.035, "GA": 0.0549, "NC": 0.045,
    "MI": 0.0425, "AZ": 0.025, "CO": 0.044, "NJ": 0.0637, "VA": 0.0575, "MA": 0.05,
}


def _now():
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def _parse_date(value):
    dt = _parse_dt(value)
    return dt.date() if dt else None


def _get_employee(employee_id):
    e = ledger.get_entity(employee_id)
    return e if e and e.entity_type == EMPLOYEE else None


# ---------------------------------------------------------------------------
# Pay plans
# ---------------------------------------------------------------------------

def set_pay_plan(employee_id, plan_type, hourly_rate=0.0, annual_salary=0.0,
                 per_deal_commission=0.0, pct_front_gross=0.0, state="TX"):
    emp = _get_employee(employee_id)
    if not emp:
        return {"error": "Employee not found"}
    if plan_type not in PLAN_TYPES:
        return {"error": f"plan_type must be one of {PLAN_TYPES}"}
    plan = {
        "plan_type": plan_type,
        "hourly_rate": float(hourly_rate or 0),
        "annual_salary": float(annual_salary or 0),
        "per_deal_commission": float(per_deal_commission or 0),
        "pct_front_gross": float(pct_front_gross or 0),
        "state": (state or "TX").upper(),
        "updated_at": _now(),
    }
    emp.attributes["pay_plan"] = plan
    save_graph(GRAPH_PATH)
    return plan


def get_pay_plan(employee_id):
    emp = _get_employee(employee_id)
    if not emp:
        return {"error": "Employee not found"}
    return emp.attributes.get("pay_plan")


# ---------------------------------------------------------------------------
# Time clock
# ---------------------------------------------------------------------------

def _open_entry(employee_id):
    for e in ledger.get_all().values():
        if e.entity_type == TIME_ENTRY and e.attributes.get("employee_id") == employee_id and not e.attributes.get("clock_out_at"):
            return e
    return None


def clock_in(employee_id, at=None):
    if not _get_employee(employee_id):
        return {"error": "Employee not found"}
    if _open_entry(employee_id):
        return {"error": "Already clocked in -- clock out first"}
    entry = Entity(
        id=id_generator.generate("TENT"),
        entity_type=TIME_ENTRY,
        attributes={"employee_id": employee_id, "clock_in_at": at or _now(), "clock_out_at": None, "hours": None},
    )
    ledger.add_entity(entry)
    save_graph(GRAPH_PATH)
    return {"id": entry.id, **entry.attributes}


def clock_out(employee_id, at=None):
    entry = _open_entry(employee_id)
    if not entry:
        return {"error": "Not currently clocked in"}
    out = at or _now()
    start = _parse_dt(entry.attributes["clock_in_at"])
    end = _parse_dt(out)
    hours = round(max(0.0, (end - start).total_seconds() / 3600), 2) if (start and end) else 0.0
    entry.attributes["clock_out_at"] = out
    entry.attributes["hours"] = hours
    save_graph(GRAPH_PATH)
    return {"id": entry.id, **entry.attributes}


def get_open_entry(employee_id):
    e = _open_entry(employee_id)
    return {"id": e.id, **e.attributes} if e else None


def _worked_hours(employee_id, start_date, end_date):
    total = 0.0
    for e in ledger.get_all().values():
        if e.entity_type != TIME_ENTRY or e.attributes.get("employee_id") != employee_id:
            continue
        h = e.attributes.get("hours")
        d = _parse_date(e.attributes.get("clock_in_at"))
        if h and d and start_date <= d <= end_date:
            total += h
    return round(total, 2)


# ---------------------------------------------------------------------------
# Commissions from funded deals
# ---------------------------------------------------------------------------

def _to_float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _front_gross(deal):
    contract = deal.attributes.get("contract") or {}
    sale = _to_float(contract.get("sale_price"))
    if sale is None:
        scn = deal.attributes.get("scenarios") or []
        sel = deal.attributes.get("selected_scenario_id")
        s = next((x for x in scn if x.get("id") == sel), None) or (scn[0] if scn else None)
        sale = _to_float(s.get("sale_price")) if s else None
    if sale is None:
        return None
    vehicle = ledger.get_entity(deal.attributes.get("vehicle_id"))
    cost = None
    if vehicle:
        cost = _to_float(vehicle.attributes.get("Cost") or vehicle.attributes.get("UnitCost") or vehicle.attributes.get("InvoiceCost"))
    if cost is None:
        return None
    return round(sale - cost, 2)


def _deal_commissions(employee_id, plan, start_date, end_date):
    """Commission for funded deals this employee closed in the period."""
    per_deal = plan.get("per_deal_commission", 0.0)
    pct = plan.get("pct_front_gross", 0.0)
    detail = []
    total = 0.0
    for d in ledger.get_all().values():
        if d.entity_type != DEAL:
            continue
        if d.attributes.get("status") != "funded" or d.attributes.get("created_by") != employee_id:
            continue
        fd = _parse_date(d.attributes.get("funded_at"))
        if not fd or not (start_date <= fd <= end_date):
            continue
        amt = per_deal
        fg = _front_gross(d)
        gross_comm = round(pct * fg, 2) if (pct and fg is not None) else 0.0
        amt = round(amt + gross_comm, 2)
        if amt > 0:
            total += amt
            detail.append({"deal_id": d.id, "amount": amt, "front_gross": fg})
    return round(total, 2), detail


# ---------------------------------------------------------------------------
# Payroll run
# ---------------------------------------------------------------------------

def _state_rate(state):
    return STATE_TAX_RATES.get((state or "TX").upper(), DEFAULT_STATE_RATE)


def _compute_gross(employee_id, plan, start_date, end_date):
    pt = plan.get("plan_type")
    hours = 0.0
    hourly_gross = 0.0
    salary_gross = 0.0
    commission_gross = 0.0
    comm_detail = []

    if pt in ("hourly", "hybrid"):
        hours = _worked_hours(employee_id, start_date, end_date)
        hourly_gross = round(hours * plan.get("hourly_rate", 0.0), 2)
    if pt in ("salary", "hybrid"):
        days = (end_date - start_date).days + 1
        salary_gross = round(plan.get("annual_salary", 0.0) * (days / 365), 2)
    if pt in ("commission", "hybrid"):
        commission_gross, comm_detail = _deal_commissions(employee_id, plan, start_date, end_date)

    gross = round(hourly_gross + salary_gross + commission_gross, 2)
    return {
        "hours": hours,
        "hourly_gross": hourly_gross,
        "salary_gross": salary_gross,
        "commission_gross": commission_gross,
        "commission_detail": comm_detail,
        "gross": gross,
    }


def _withhold(gross, state):
    federal = round(gross * FEDERAL_RATE, 2)
    fica = round(gross * FICA_RATE, 2)
    state_tax = round(gross * _state_rate(state), 2)
    total = round(federal + fica + state_tax, 2)
    return {"federal": federal, "fica": fica, "state": state_tax, "state_rate": _state_rate(state), "total": total}


def run_payroll(period_start, period_end, created_by, employee_ids=None):
    """Generate paychecks for a pay period. Any employee with a pay plan is included (or the
    given employee_ids). Returns the run summary; each PayStatement is a real entity."""
    start = _parse_date(period_start)
    end = _parse_date(period_end)
    if not start or not end:
        return {"error": "period_start and period_end must be valid ISO dates"}
    if end < start:
        return {"error": "period_end cannot be before period_start"}

    if employee_ids:
        employees = [_get_employee(eid) for eid in employee_ids]
        employees = [e for e in employees if e]
    else:
        employees = [e for e in ledger.get_all().values() if e.entity_type == EMPLOYEE and e.attributes.get("pay_plan")]

    run_id = id_generator.generate("PRUN")
    statements = []
    total_gross = 0.0
    total_net = 0.0

    for emp in employees:
        plan = emp.attributes.get("pay_plan")
        if not plan:
            continue
        comp = _compute_gross(emp.id, plan, start, end)
        if comp["gross"] <= 0:
            continue  # nobody is paid $0 -- no fabricated paycheck
        taxes = _withhold(comp["gross"], plan.get("state"))
        net = round(comp["gross"] - taxes["total"], 2)

        stmt = Entity(
            id=id_generator.generate("PAYS"),
            entity_type=PAY_STATEMENT,
            attributes={
                "run_id": run_id,
                "employee_id": emp.id,
                "employee_name": f"{emp.attributes.get('FirstName', '')} {emp.attributes.get('LastName', '')}".strip() or emp.id,
                "period_start": start.isoformat(),
                "period_end": end.isoformat(),
                "plan_type": plan.get("plan_type"),
                "state": plan.get("state"),
                "hours": comp["hours"],
                "earnings": {
                    "hourly": comp["hourly_gross"],
                    "salary": comp["salary_gross"],
                    "commission": comp["commission_gross"],
                },
                "commission_detail": comp["commission_detail"],
                "gross_pay": comp["gross"],
                "taxes": taxes,
                "net_pay": net,
                "tax_model": "simplified",
                "created_by": created_by,
                "created_at": _now(),
            },
        )
        ledger.add_entity(stmt)
        statements.append({"id": stmt.id, "employee_id": emp.id, "gross_pay": comp["gross"], "net_pay": net})
        total_gross += comp["gross"]
        total_net += net

    run = Entity(
        id=run_id,
        entity_type=PAYROLL_RUN,
        attributes={
            "period_start": start.isoformat(),
            "period_end": end.isoformat(),
            "statement_count": len(statements),
            "total_gross": round(total_gross, 2),
            "total_net": round(total_net, 2),
            "created_by": created_by,
            "created_at": _now(),
        },
    )
    ledger.add_entity(run)
    save_graph(GRAPH_PATH)

    return {
        "run_id": run_id,
        "period_start": start.isoformat(),
        "period_end": end.isoformat(),
        "statement_count": len(statements),
        "total_gross": round(total_gross, 2),
        "total_net": round(total_net, 2),
        "statements": statements,
        "tax_model": "simplified",
    }


def get_pay_statement(statement_id):
    e = ledger.get_entity(statement_id)
    if not e or e.entity_type != PAY_STATEMENT:
        return {"error": "Pay statement not found"}
    return {"id": e.id, **e.attributes}


def list_pay_statements(employee_id=None, run_id=None):
    out = [e for e in ledger.get_all().values() if e.entity_type == PAY_STATEMENT]
    if employee_id:
        out = [e for e in out if e.attributes.get("employee_id") == employee_id]
    if run_id:
        out = [e for e in out if e.attributes.get("run_id") == run_id]
    out.sort(key=lambda e: e.attributes.get("created_at", ""), reverse=True)
    return [{"id": e.id, **e.attributes} for e in out]


def list_payroll_runs():
    runs = [e for e in ledger.get_all().values() if e.entity_type == PAYROLL_RUN]
    runs.sort(key=lambda e: e.attributes.get("created_at", ""), reverse=True)
    return [{"id": e.id, **e.attributes} for e in runs]
