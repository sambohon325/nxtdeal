"""
core/performance_readiness.py -- Readiness' "Performance Readiness" item
(2026-07-19, this same reframe session), item #4 of Sam's own 10-item
proposed structure. Sam's own words: "This is where scores become useful."
Goal Tracking against real pace:

  Sales:      Monthly Sales Goal 120 Units, Current Pace 134 Units, Readiness 112%
  Service:    Goal $250,000 Labor, Projected $262,000, Readiness 105%
  Marketing:  Goal 900 Leads, Forecast 1,120 Leads, Readiness 124%

Honest-gap check done BEFORE writing any of this: this whole feature needs a
real GOAL to compare pace against, and no goal/quota/target-setting mechanism
existed anywhere in this codebase before this slice -- core/business_health.py's
own Pipeline Coverage note had already flagged this exact gap explicitly ("No
sales quota/target concept exists anywhere in this codebase"). Two honest
choices existed: (a) build a real goal-setting mechanism now, or (b) leave
goal comparison as a stated not_yet_tracked gap pending the separately-scoped
"Strategic Planning" item (Sam's #9, objectives/initiatives/budgets). Chose
(a) -- a simple, real, ADMIN/OPERATIONS-editable flat monthly numeric target
per department (core/system_config.py's new department_goals dict,
GOAL_TRACKED_DEPARTMENTS = sales/service/marketing, matching Sam's own 3
worked examples exactly) is a small, honest, valuable thing to build, not a
fabrication -- and it's deliberately narrow enough that it won't collide with
Strategic Planning: that item is a much richer objectives/initiatives/budget
system, and this flat single-number-per-department mechanism is a genuine,
working stopgap it may supersede or extend later, not a competing model.

The Current Pace / Projected / Forecast half is two real, distinct numbers,
composed rather than a single fabricated one:

  1. current_month_pace -- a real linear run-rate projection: actual-to-date
     THIS calendar month (real Vehicle.DateSold count for Sales, real
     ServiceRecord Cost-PartsCost labor revenue for Service -- the same real
     labor-revenue proxy core/service_reporting.py's technician scorecard
     already established -- real Lead.CreatedDate count for Marketing),
     divided by days elapsed in the month, multiplied by days in the month.
     This is the literal math behind every one of Sam's own worked examples.

  2. ledger_forecast -- core/prediction.py's own real, already-built
     month-horizon predict() reused DIRECTLY (per the standing instruction to
     reuse the existing forecast engine rather than build a second one), for
     sales/marketing only. Service is deliberately excluded here: core/
     prediction.py's Service metric is repair_orders (a count), not $ labor
     revenue -- a genuine unit mismatch against this feature's $-denominated
     goal, so showing it side by side would misrepresent it as a real
     cross-check when it isn't one.

Readiness % = (current_month_pace, or ledger_forecast when pace can't be
computed) / goal x 100 -- computed ONLY when both a real goal and a real
pace/forecast exist. An unset goal or missing pace/forecast data is reported
honestly (goal_set: false, readiness_pct: null), never defaulted to a
fabricated 100%.
"""

import calendar
from datetime import date

from core.dealeros import ledger
from core.entity_types import VEHICLE, SERVICE_RECORD, LEAD
from core.prediction import predict, DEPARTMENTS as PREDICTION_DEPARTMENTS
from core.system_config import get_department_goals


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(raw):
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


# The 3 departments Sam's own worked examples name a goal metric for, and the
# real label/unit each one's number is denominated in.
GOAL_METRIC_CATALOG = {
    "sales": {"label": "Monthly Sales Goal", "unit": "units", "metric_name": "units_sold"},
    "service": {"label": "Monthly Service Labor Goal", "unit": "$", "metric_name": "labor_revenue"},
    "marketing": {"label": "Monthly Lead Goal", "unit": "leads", "metric_name": "leads_generated"},
}


def _current_month_actual(department, today):
    """Real actual-to-date total for the CURRENT calendar month against the
    one department-specific metric GOAL_METRIC_CATALOG names -- real data,
    real calendar-month filter, no simulation, no fabrication."""

    if department == "sales":
        total = 0
        for v in _entities(VEHICLE):
            d = _parse_date(v.attributes.get("DateSold"))
            if d and d.year == today.year and d.month == today.month:
                total += 1
        return float(total)

    if department == "service":
        total = 0.0
        for r in _entities(SERVICE_RECORD):
            d = _parse_date(r.attributes.get("ServiceDate"))
            if d and d.year == today.year and d.month == today.month:
                total += _safe_float(r.attributes.get("Cost")) - _safe_float(r.attributes.get("PartsCost"))
        return round(total, 2)

    if department == "marketing":
        total = 0
        for lead in _entities(LEAD):
            d = _parse_date(lead.attributes.get("CreatedDate"))
            if d and d.year == today.year and d.month == today.month:
                total += 1
        return float(total)

    return None


def get_current_month_pace(department, today=None):
    """Real linear run-rate projection for the CURRENT calendar month: actual-
    to-date / days elapsed x days in month. This is the actual math behind
    every one of Sam's own worked examples (134 units, $262,000, 1,120
    leads)."""

    if department not in GOAL_METRIC_CATALOG:
        return None

    today = today or date.today()
    days_elapsed = today.day
    days_in_month = calendar.monthrange(today.year, today.month)[1]

    actual_to_date = _current_month_actual(department, today)
    if actual_to_date is None or not days_elapsed:
        return None

    projected_month_total = round((actual_to_date / days_elapsed) * days_in_month, 2)

    return {
        "department": department,
        "actual_to_date": actual_to_date,
        "days_elapsed": days_elapsed,
        "days_in_month": days_in_month,
        "projected_month_total": projected_month_total,
        "basis": "real",
        "note": "Linear run-rate: actual-to-date this calendar month, divided by days elapsed, multiplied by days in month.",
    }


def get_ledger_forecast(department):
    """core/prediction.py's own real month-horizon predict(), reused directly
    -- a genuinely different (blended real-vs-industry-baseline, trailing
    ~180-day window) computation from get_current_month_pace()'s literal
    calendar-month run-rate, kept alongside as a real cross-check rather than
    folded into or replacing it. Service is deliberately excluded -- see this
    module's own docstring for the unit-mismatch reasoning (repair_orders
    count vs. $ labor revenue)."""

    if department not in PREDICTION_DEPARTMENTS or department == "service":
        return None

    p = predict(department, "month")
    if not p:
        return None

    return {
        "department": department,
        "metric": p["metric"],
        "unit": p["unit"],
        "predicted_value": p["predicted_value"],
        "confidence_pct": p["confidence_pct"],
        "basis": p["basis"],
        "note": p["note"],
    }


def get_department_performance_readiness(department, today=None):
    """One department's real Goal vs Pace vs Readiness % -- computed only when
    both a real goal (core/system_config.py's department_goals) and a real
    pace/forecast exist. Never defaults an unset goal or missing data to a
    fabricated 100%."""

    department = (department or "").lower()

    if department not in GOAL_METRIC_CATALOG:
        return {"error": f"Unknown department '{department}' for Performance Readiness -- expected one of {sorted(GOAL_METRIC_CATALOG.keys())}."}

    catalog = GOAL_METRIC_CATALOG[department]
    goal = get_department_goals().get(department)

    pace = get_current_month_pace(department, today=today)
    forecast = get_ledger_forecast(department)

    pace_value = pace["projected_month_total"] if pace else None
    forecast_value = forecast["predicted_value"] if forecast else None

    readiness_pct = None
    readiness_source = None

    if goal:
        if pace_value is not None:
            readiness_pct = round((pace_value / goal) * 100, 1)
            readiness_source = "current_month_pace"
        elif forecast_value is not None:
            readiness_pct = round((forecast_value / goal) * 100, 1)
            readiness_source = "ledger_forecast"

    if goal is None:
        status = "No goal set -- an ADMIN/OPERATIONS user must set one before readiness can be scored."
    elif readiness_pct is None:
        status = "Not enough real data yet to compute a pace or forecast."
    elif readiness_pct >= 100:
        status = "At/Above Goal"
    else:
        status = "Below Goal"

    return {
        "department": department,
        "label": catalog["label"],
        "unit": catalog["unit"],
        "goal": goal,
        "goal_set": goal is not None,
        "current_month_pace": pace,
        "ledger_forecast": forecast,
        "readiness_pct": readiness_pct,
        "readiness_source": readiness_source,
        "status": status,
    }


def get_performance_readiness_overview(today=None):
    return {
        "departments": [get_department_performance_readiness(d, today=today) for d in GOAL_METRIC_CATALOG],
        "tracked_departments": list(GOAL_METRIC_CATALOG.keys()),
        "not_yet_tracked": {
            "finance_goal": "No Finance goal metric is tracked here -- Sam's own worked examples covered Sales/Service/Marketing only. A Finance $ goal (e.g. funded contracts or gross) could be added the same way if Sam wants it.",
            "inventory_goal": "No Inventory goal metric is tracked here, same reasoning as Finance.",
        },
    }
