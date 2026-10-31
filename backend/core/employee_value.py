"""
core/employee_value.py — per-employee monetary value/effectiveness scoring
(2026-07-13, session 37). Sam: "I want to as part of the analytics (users) begin to
assign monetary value to each employee that they're actively bringing in / affecting
with their work input or lack of. This would initially be based off of industry
averages against known data, and then be filled in by the ledger's own data as it
becomes available... admin can measure the live employee over time against the bot and
see who is more effective and what duties to move to who to increase efficiencies, and
what efficiencies can be increased by simply increasing the bandwidth of the bots
versus headcount. Our job is not to reduce human headcount, its simply to supply admin
with data for them to make the call to move the human workforce to where they will be
more effective in the dealership."

Same honest-blend pattern as core/prediction.py: every employee's $ value estimate
separates a real, ledger-derived component from an industry-baseline component
(INDUSTRY_MONTHLY_VALUE below -- generic, commonly-cited per-role dealership
benchmarks, NOT a specific cited source, since this environment has no live access to
verify one), blended by how much real attributed data exists for that employee, and
labeled "ledger", "industry_estimate", or "blended" so admin always knows which is
which.

Scope, honestly stated: only Sales (via Deal.created_by) and Service (via
ServiceRecord.Technician -- already-existing seed data attribution, no schema change
needed) have a real per-employee $ attribution path in the ledger today.
Finance/Marketing/Operations/Administration roles have no clean per-employee revenue
link yet (FinanceContract has no F&I-actor field; a Campaign's $ impact isn't cleanly
separable per person from what's modeled today) -- those roles report
industry_estimate only, clearly marked, rather than a fabricated attribution.

The "measure against the bot" piece: automation_coverage() reads real
core/bot_learning.py BotTaskEvent history for an employee -- of the distinct bot task
types they've ever had an event for, how many are in core/bot_actions.py's
auto-execute whitelist. That's a real, non-fabricated "how much of this role's
suggested work is already automatable" signal admin can weigh against the $ value
figure -- exactly the bot-bandwidth-vs-headcount question Sam asked for. It is
explicitly NOT a headcount-reduction score -- see EFFECTIVENESS_DISCLAIMER, surfaced
verbatim in the UI.
"""

from datetime import date, timedelta

from core.dealeros import ledger
from core.entity_types import EMPLOYEE, DEAL, SERVICE_RECORD, BOT_TASK_EVENT
from core.bot_tasks import infer_tier, TIER_STAFF, TIER_MANAGER, TIER_EXECUTIVE
from core.bot_actions import ACTION_HANDLERS


EFFECTIVENESS_DISCLAIMER = (
    "This is a decision-support figure for moving duties to where people are most "
    "effective -- not a tool for reducing headcount."
)

# Generic, commonly-cited monthly $ value benchmarks per department/tier -- NOT sourced
# from a specific citation (no live source access in this environment). Used only when
# an employee doesn't yet have enough real ledger-attributed output, and always shown
# alongside a "industry_estimate"/"blended" label, never silently as if real.
INDUSTRY_MONTHLY_VALUE = {
    ("sales", TIER_STAFF): 3500.0,
    ("sales", TIER_MANAGER): 6000.0,
    ("sales", TIER_EXECUTIVE): 9000.0,
    ("service", TIER_STAFF): 4000.0,
    ("service", TIER_MANAGER): 6500.0,
    ("service", TIER_EXECUTIVE): 9000.0,
    ("finance", TIER_STAFF): 5000.0,
    ("finance", TIER_MANAGER): 8000.0,
    ("finance", TIER_EXECUTIVE): 11000.0,
    ("marketing", TIER_STAFF): 2500.0,
    ("marketing", TIER_MANAGER): 4500.0,
    ("marketing", TIER_EXECUTIVE): 7000.0,
    ("operations", TIER_STAFF): 3000.0,
    ("operations", TIER_MANAGER): 5500.0,
    ("operations", TIER_EXECUTIVE): 10000.0,
}

DEFAULT_BASELINE = 4000.0

# Fewer than core/prediction.py's VOLUME_TARGET_SAMPLES (30) on purpose -- one
# employee's own monthly output is naturally a much smaller sample than a whole
# department's.
VOLUME_TARGET_RECORDS = 10

WINDOW_DAYS = 30


def _today():
    return date.today()


def _f(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _department_of(employee):

    if not employee:
        return None

    return (employee.attributes.get("Department") or "").strip().lower() or None


def _display_name(employee):

    attrs = employee.attributes or {}

    if attrs.get("FirstName") and attrs.get("LastName"):
        return f"{attrs['FirstName']} {attrs['LastName']}"

    return employee.id


def _real_sales_value(employee_id, window_days=WINDOW_DAYS):
    """Real gross profit (Price - Cost) on vehicles this employee funded a deal for,
    within the trailing window -- reuses Deal.created_by, the same real attribution
    core/deals.py already establishes when a deal is desked."""

    cutoff = _today() - timedelta(days=window_days)
    total = 0.0
    count = 0

    for entity in ledger.get_all().values():

        if entity.entity_type != DEAL:
            continue

        if entity.attributes.get("created_by") != employee_id:
            continue

        if entity.attributes.get("status") != "funded":
            continue

        updated_at = entity.attributes.get("updated_at") or ""

        try:
            updated_date = date.fromisoformat(updated_at[:10])
        except ValueError:
            continue

        if updated_date < cutoff:
            continue

        vehicle = ledger.get_entity(entity.attributes.get("vehicle_id"))

        if vehicle:
            total += _f(vehicle.attributes.get("Price")) - _f(vehicle.attributes.get("Cost"))

        count += 1

    return total, count


def _real_service_value(employee_id, window_days=WINDOW_DAYS):
    """Real gross profit (Cost - PartsCost) on repair orders attributed to this
    employee via ServiceRecord.Technician, within the trailing window."""

    cutoff = _today() - timedelta(days=window_days)
    total = 0.0
    count = 0

    for entity in ledger.get_all().values():

        if entity.entity_type != SERVICE_RECORD:
            continue

        if entity.attributes.get("Technician") != employee_id:
            continue

        service_date_raw = entity.attributes.get("ServiceDate") or ""

        try:
            service_date = date.fromisoformat(service_date_raw[:10])
        except ValueError:
            continue

        if service_date < cutoff:
            continue

        total += _f(entity.attributes.get("Cost")) - _f(entity.attributes.get("PartsCost"))
        count += 1

    return total, count


# department -> real-value function. Departments not listed here have no real
# per-employee attribution path in the ledger yet -- see module docstring.
_REAL_VALUE_FUNCTIONS = {
    "sales": _real_sales_value,
    "service": _real_service_value,
}


def automation_coverage(employee_id):
    """Of the distinct bot task types this employee has ever had a recorded event for
    (core/bot_learning.py's BotTaskEvent), what fraction are in
    core/bot_actions.py's auto-execute whitelist. Returns None (not zero -- zero would
    imply "definitely not automatable", which isn't known either way) if there's no
    bot task history yet."""

    task_keys = set()

    for entity in ledger.get_all().values():

        if entity.entity_type != BOT_TASK_EVENT:
            continue

        if entity.attributes.get("employee_id") != employee_id:
            continue

        task_keys.add(entity.attributes.get("task_key"))

    if not task_keys:
        return None

    automatable = sum(1 for key in task_keys if key in ACTION_HANDLERS)

    return {
        "distinct_task_types": len(task_keys),
        "automatable_task_types": automatable,
        "automation_pct": round(100 * automatable / len(task_keys), 1),
    }


def _value_note(basis, sample_count, department, has_real_path):

    if not has_real_path:
        return (
            f"No direct per-employee $ attribution exists in the ledger yet for the "
            f"'{department}' department -- showing an industry rule-of-thumb estimate "
            "only, not a cited source."
        )

    if basis == "ledger":
        return f"Based on {sample_count} real attributed record(s) from the ledger this month."

    if basis == "industry_estimate":
        return (
            f"Not enough real attributed output yet ({sample_count} record(s)) -- "
            "using an industry rule-of-thumb estimate, not a cited source."
        )

    return f"Blended: {sample_count} real attributed record(s) plus an industry estimate."


def compute_employee_value(employee_id):
    """Returns a full $ value/effectiveness dict for one employee, or None if no
    Employee entity exists for this id."""

    employee = ledger.get_entity(employee_id)

    if not employee or employee.entity_type != EMPLOYEE:
        return None

    title = employee.attributes.get("Title")
    department = _department_of(employee)
    tier = infer_tier(title)

    baseline = INDUSTRY_MONTHLY_VALUE.get((department, tier), DEFAULT_BASELINE)

    real_fn = _REAL_VALUE_FUNCTIONS.get(department)

    if real_fn:
        real_value, sample_count = real_fn(employee_id)
    else:
        real_value, sample_count = 0.0, 0

    volume = min(1.0, sample_count / VOLUME_TARGET_RECORDS)

    blended_value = (volume * real_value) + ((1 - volume) * baseline)

    if not real_fn:
        basis = "industry_estimate"
    elif volume >= 0.9:
        basis = "ledger"
    elif volume <= 0.1:
        basis = "industry_estimate"
    else:
        basis = "blended"

    return {
        "employee_id": employee_id,
        "name": _display_name(employee),
        "department": department,
        "title": title,
        "tier": tier,
        "monthly_value_estimate": round(blended_value, 2),
        "sample_size": sample_count,
        "basis": basis,
        "automation_coverage": automation_coverage(employee_id),
        "note": _value_note(basis, sample_count, department, real_fn is not None),
        "disclaimer": EFFECTIVENESS_DISCLAIMER,
    }


def list_employee_values(department=None):

    results = []

    for entity in ledger.get_all().values():

        if entity.entity_type != EMPLOYEE:
            continue

        value = compute_employee_value(entity.id)

        if not value:
            continue

        if department and value["department"] != department:
            continue

        results.append(value)

    results.sort(key=lambda v: v["monthly_value_estimate"], reverse=True)

    return results
