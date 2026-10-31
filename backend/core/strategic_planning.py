"""
core/strategic_planning.py -- Readiness reframe, item #9 of Sam's own 10-item
proposed structure: Strategic Planning. Sam's own words: "A completely new
area." Covers Quarterly Planning (Objectives, Goals, Budgets, Initiatives),
Department Planning (Sales Goal, Inventory Target, Service Growth, Marketing
Budget), and Initiative Tracking (New Website Launch, New Service Center, New
BHPH Program, GPS Rollout -- "Monitor performance").

Confirmed via a full grep for "Objective"/"Initiative"/"quarterly" across
core/*.py BEFORE writing anything: nothing like this exists yet. This is a
genuinely new, first-class entity model -- two new entity types
(StrategicObjective/StrategicInitiative), not a dict bolted onto something
else, same "own lifecycle" reasoning OperationsTask/DamageReport/Payment/
AutomationExecution already established in this codebase (see
core/entity_types.py's own docstring for both).

RELATIONSHIP TO core/system_config.py's department_goals (Performance
Readiness, item #4, built earlier this same reframe session) -- read that
module's own docstring first, which explicitly named this exact question:
"a genuine, small, working stopgap that Strategic Planning may supersede or
extend later, not a duplicate of it." Decision made here: EXTEND, don't
replace or silently duplicate. department_goals stays the one real source
Performance Readiness reads for its monthly pace-vs-goal comparison -- this
module does NOT introduce a second, competing monthly-goal store. Instead,
a quarterly StrategicObjective for one of the 3 GOAL_TRACKED_DEPARTMENTS
(sales/service/marketing) can be explicitly PUSHED down into that same
monthly slot via sync_objective_to_monthly_goal() -- a real, one-way,
ADMIN/OPERATIONS-triggered action (never automatic/silent) that divides the
objective's own quarterly target_value by 3 and calls
core/system_config.py's set_department_goal() directly. The objective
records whether/when this happened (synced_monthly_goal/synced_monthly_
target/synced_at) so the UI can show the coupling honestly, but the two
stay independently editable afterward -- syncing again re-pushes the current
math, it doesn't lock the monthly figure to the quarterly one forever.

STATUS COMPUTATION -- live, not stored, matching core/performance_
readiness.py's own readiness_pct/status convention exactly (computed fresh
on every read, never a manually-set field divorced from reality):

  - For Sales/Service/Marketing objectives (the same 3 departments core/
    performance_readiness.py's GOAL_METRIC_CATALOG already covers), this
    module generalizes that module's exact real signal sources (Vehicle.
    DateSold for Sales, ServiceRecord Cost-PartsCost for Service, Lead.
    CreatedDate for Marketing) from a CALENDAR-MONTH window to a full
    CALENDAR-QUARTER window -- the same real linear-run-rate-projection
    math, just a wider date range. This is an honest generalization of an
    already-real signal, not a second, different computation.
  - For every other department (Finance, Inventory, Operations,
    Administration, Company-Wide) -- and for Sales/Service/Marketing
    objectives with no target_value set -- there is no real ledger signal
    this codebase can compute a quarterly pace from (confirmed: core/
    performance_readiness.py's own GOAL_METRIC_CATALOG covers only those
    3 departments, and its own not_yet_tracked note already flags Finance/
    Inventory as gaps). Status instead falls back to an owner's own
    manual_progress_pct self-report, compared against a real, honest
    "expected pct" (how far through the quarter today is), and is clearly
    labeled current_value_basis="manual" rather than "real" -- never
    fabricated to look like a live ledger signal.

INITIATIVE PROGRESS TRACKING -- the same real-vs-honest-manual split, per
Sam's own named examples:

  - "New Website Launch" -> tracking_type="website_launch": links to a real
    core/websites.py Website by id. Progress is derived from that site's own
    real, already-tracked status (draft/pending_approval/published/
    rejected) -- a real, already-existing signal, not invented for this
    slice.
  - "GPS Rollout" -> tracking_type="gps_rollout": counts real
    core/device_management.py InstalledDevice entities system-wide against
    a real, dealer-entered target_metric_value (e.g. "roll out to 50
    vehicles") -- real device count, real target, real ratio.
  - "New Service Center" / "New BHPH Program" and any other free-text
    initiative -> tracking_type="manual": no real graph signal exists for
    either of these (no ServiceCenter entity anywhere in this codebase;
    BHPH is already this dealership's default in-house financing type on
    every Deal, not something that gets "launched" as a trackable project)
    -- confirmed via grep before assuming otherwise. Progress is a plain,
    honestly-labeled manual_progress_pct an owner records themselves.

Budgets: budget_allocated/budget_spent are real numeric fields on both
Objective and Initiative, but budget_spent is ALWAYS manually entered --
stated explicitly, not implied -- since no expense-ledger-per-objective/
initiative concept exists anywhere in this codebase (core/loan_accounting.py's
real GL posting engine tracks loan-payment cash flow, not project/initiative
spend). No automatic spend tracking is fabricated here.
"""

import calendar
from datetime import date, datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import (
    STRATEGIC_OBJECTIVE,
    STRATEGIC_INITIATIVE,
    VEHICLE,
    SERVICE_RECORD,
    LEAD,
)
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

from core.performance_readiness import GOAL_METRIC_CATALOG
from core.system_config import GOAL_TRACKED_DEPARTMENTS, set_department_goal
from core.websites import get_website, get_website_analytics
from core.device_management import list_devices


QUARTERS = ("Q1", "Q2", "Q3", "Q4")

# Sam's own department list, Title Case to match every other *_menu.py's
# department-name convention. "Company-Wide" covers a dealership-level
# objective that isn't any one department's alone.
STRATEGIC_DEPARTMENTS = (
    "Sales", "Service", "Marketing", "Finance", "Inventory",
    "Operations", "Administration", "Company-Wide",
)

OBJECTIVE_STATUSES = (
    "not_started", "on_track", "at_risk", "behind", "achieved", "missed",
    "no_target", "no_data", "cancelled",
)

INITIATIVE_STATUSES = ("planned", "in_progress", "completed", "cancelled")
_INITIATIVE_TERMINAL = {"completed", "cancelled"}
_INITIATIVE_TRANSITIONS = {
    "planned": {"in_progress", "cancelled"},
    "in_progress": {"completed", "cancelled"},
    "completed": set(),
    "cancelled": set(),
}

# Sam's own named initiative examples, mapped onto exactly what this codebase
# can honestly track for real vs. what needs a manual self-report -- see this
# module's own docstring for the full reasoning on each.
TRACKING_TYPE_CATALOG = {
    "website_launch": {
        "label": "New Website Launch",
        "linked_entity_type": "Website",
        "requires_linked_entity_id": True,
        "requires_target_metric": False,
        "basis": "real_website_publish_status",
        "note": "Progress derives from the linked site's own real status (draft/pending_approval/published/rejected).",
    },
    "gps_rollout": {
        "label": "GPS Rollout",
        "linked_entity_type": "GpsDeviceRollout",
        "requires_linked_entity_id": False,
        "requires_target_metric": True,
        "basis": "real_installed_device_count",
        "note": "Progress = real InstalledDevice count / a dealer-entered target device count.",
    },
    "manual": {
        "label": "Manual Progress Tracking (e.g. New Service Center, New BHPH Program)",
        "linked_entity_type": None,
        "requires_linked_entity_id": False,
        "requires_target_metric": False,
        "basis": "manual",
        "note": "No real graph signal exists for this initiative type -- an owner records progress manually.",
    },
}

_WEBSITE_STATUS_PROGRESS = {"draft": 10.0, "pending_approval": 50.0, "published": 100.0, "rejected": 25.0}


def _now():
    return datetime.now(timezone.utc)


def _now_iso():
    return _now().isoformat()


def _entities(entity_type):
    return [e for e in ledger.get_all().values() if e.entity_type == entity_type]


def _safe_float(value, default=None):
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


def _quarter_month_range(quarter):
    return {"Q1": (1, 3), "Q2": (4, 6), "Q3": (7, 9), "Q4": (10, 12)}[quarter]


def _quarter_of(d):
    return f"Q{(d.month - 1) // 3 + 1}"


def _quarter_bounds(quarter, year):
    start_month, end_month = _quarter_month_range(quarter)
    start = date(year, start_month, 1)
    end_day = calendar.monthrange(year, end_month)[1]
    end = date(year, end_month, end_day)
    return start, end


def _current_quarter_year(today=None):
    today = today or date.today()
    return _quarter_of(today), today.year


# ---------------------------------------------------------------------------
# Quarter-window real pace -- an honest generalization of core/
# performance_readiness.py's exact same real signal sources (Vehicle.
# DateSold/ServiceRecord Cost-PartsCost/Lead.CreatedDate) from a calendar
# MONTH window to a calendar QUARTER window.
# ---------------------------------------------------------------------------

def get_quarter_pace(department, quarter, year, today=None):
    if department not in GOAL_METRIC_CATALOG:
        return None

    today = today or date.today()
    start, end = _quarter_bounds(quarter, year)
    total_days = (end - start).days + 1

    if today < start:
        return {
            "phase": "future", "actual_to_date": 0.0, "days_elapsed": 0,
            "total_days": total_days, "projected_quarter_total": None, "basis": "real",
        }

    cutoff = min(today, end)
    days_elapsed = (cutoff - start).days + 1
    actual = 0.0

    if department == "sales":
        for v in _entities(VEHICLE):
            d = _parse_date(v.attributes.get("DateSold"))
            if d and start <= d <= cutoff:
                actual += 1
    elif department == "service":
        for r in _entities(SERVICE_RECORD):
            d = _parse_date(r.attributes.get("ServiceDate"))
            if d and start <= d <= cutoff:
                actual += (_safe_float(r.attributes.get("Cost"), 0.0) - _safe_float(r.attributes.get("PartsCost"), 0.0))
        actual = round(actual, 2)
    elif department == "marketing":
        for lead in _entities(LEAD):
            d = _parse_date(lead.attributes.get("CreatedDate"))
            if d and start <= d <= cutoff:
                actual += 1

    projected = round((actual / days_elapsed) * total_days, 2) if days_elapsed else None
    phase = "complete" if today > end else "in_progress"

    return {
        "phase": phase, "actual_to_date": actual, "days_elapsed": days_elapsed,
        "total_days": total_days, "projected_quarter_total": projected, "basis": "real",
        "note": "Linear run-rate over the full calendar quarter -- the same real signal source core/performance_readiness.py uses for its monthly pace, generalized to a quarter window.",
    }


def _manual_expected_pct(quarter, year, today=None):
    today = today or date.today()
    start, end = _quarter_bounds(quarter, year)
    total_days = (end - start).days + 1
    if today < start:
        return 0.0, "future"
    if today > end:
        return 100.0, "complete"
    days_elapsed = (today - start).days + 1
    return round(days_elapsed / total_days * 100, 1), "in_progress"


def compute_objective_status(attrs, today=None):
    """Live status computation -- never stored, never manually overridden.
    See this module's own docstring for the full real-vs-manual reasoning."""

    if attrs.get("is_cancelled"):
        return {
            "status": "cancelled", "current_value": None, "current_value_basis": None,
            "pct_of_target": None, "quarter_phase": None,
        }

    department = attrs.get("department", "")
    dept_lower = department.lower()
    quarter = attrs.get("quarter")
    year = attrs.get("year")
    target = attrs.get("target_value")

    if dept_lower in GOAL_METRIC_CATALOG:
        pace = get_quarter_pace(dept_lower, quarter, year, today=today)
        if pace:
            current_value = pace["actual_to_date"]
            if pace["phase"] == "future":
                status = "not_started"
                pct_of_target = None
            elif target is None:
                status = "no_target"
                pct_of_target = None
            elif pace["phase"] == "complete":
                pct_of_target = round(current_value / target * 100, 1) if target else None
                status = "achieved" if current_value >= target else "missed"
            else:
                projected = pace["projected_quarter_total"]
                pct_of_target = round(projected / target * 100, 1) if target and projected is not None else None
                if pct_of_target is None:
                    status = "no_data"
                elif pct_of_target >= 100:
                    status = "on_track"
                elif pct_of_target >= 85:
                    status = "at_risk"
                else:
                    status = "behind"

            return {
                "status": status, "current_value": current_value, "current_value_basis": "real",
                "pct_of_target": pct_of_target, "quarter_phase": pace["phase"], "quarter_pace": pace,
            }

    # Not one of the 3 live-tracked departments (or no pace could be
    # computed) -- fall back to an honest manual self-report.
    manual_pct = attrs.get("manual_progress_pct")
    expected_pct, phase = _manual_expected_pct(quarter, year, today=today)

    if manual_pct is None:
        status = "no_data"
    elif phase == "future":
        status = "not_started"
    elif phase == "complete":
        status = "achieved" if manual_pct >= 100 else "missed"
    elif manual_pct >= expected_pct:
        status = "on_track"
    elif manual_pct >= expected_pct * 0.7:
        status = "at_risk"
    else:
        status = "behind"

    return {
        "status": status, "current_value": manual_pct,
        "current_value_basis": "manual" if manual_pct is not None else None,
        "pct_of_target": manual_pct, "quarter_phase": phase,
        "expected_pct_this_far_into_quarter": expected_pct,
        "note": "No real ledger pace signal exists for this department -- status is derived from the owner's own manual_progress_pct self-report, not a live computation." if dept_lower not in GOAL_METRIC_CATALOG else None,
    }


# ---------------------------------------------------------------------------
# Objectives
# ---------------------------------------------------------------------------

def _get_objective_entity(objective_id):
    e = ledger.get_entity(objective_id)
    if e and e.entity_type == STRATEGIC_OBJECTIVE:
        return e
    return None


def _serialize_objective(entity, today=None):
    status = compute_objective_status(entity.attributes, today=today)
    return {"id": entity.id, **entity.attributes, **status}


def create_objective(quarter, year, department, title, created_by, description="",
                      target_value=None, unit="", budget_allocated=None):

    if quarter not in QUARTERS:
        return {"error": f"quarter must be one of {QUARTERS}"}

    try:
        year = int(year)
    except (TypeError, ValueError):
        return {"error": "year must be a valid integer"}

    if department not in STRATEGIC_DEPARTMENTS:
        return {"error": f"department must be one of {STRATEGIC_DEPARTMENTS}"}

    if not title or not title.strip():
        return {"error": "title is required"}

    target_value = _safe_float(target_value, None) if target_value is not None else None
    budget_allocated = _safe_float(budget_allocated, None) if budget_allocated is not None else None

    objective_id = id_generator.generate("OBJ")
    entity = Entity(
        id=objective_id,
        entity_type=STRATEGIC_OBJECTIVE,
        attributes={
            "quarter": quarter,
            "year": year,
            "department": department,
            "title": title.strip(),
            "description": description or "",
            "target_value": target_value,
            "unit": unit or "",
            "budget_allocated": budget_allocated,
            "budget_spent": None,
            "manual_progress_pct": None,
            "is_cancelled": False,
            "synced_monthly_goal": False,
            "synced_monthly_target": None,
            "synced_at": None,
            "created_by": created_by,
            "created_at": _now_iso(),
            "updated_by": created_by,
            "updated_at": _now_iso(),
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return _serialize_objective(entity)


def get_objective(objective_id):
    entity = _get_objective_entity(objective_id)
    if not entity:
        return {"error": "Objective not found"}
    return _serialize_objective(entity)


def list_objectives(quarter=None, year=None, department=None):
    objs = _entities(STRATEGIC_OBJECTIVE)
    if quarter:
        objs = [o for o in objs if o.attributes.get("quarter") == quarter]
    if year:
        objs = [o for o in objs if o.attributes.get("year") == int(year)]
    if department:
        objs = [o for o in objs if o.attributes.get("department") == department]
    objs.sort(key=lambda o: (o.attributes.get("year", 0), o.attributes.get("quarter", ""), o.attributes.get("department", "")))
    return {"count": len(objs), "objectives": [_serialize_objective(o) for o in objs]}


_OBJECTIVE_EDITABLE = ("title", "description", "target_value", "unit", "budget_allocated")


def update_objective(objective_id, updated_by, **fields):
    entity = _get_objective_entity(objective_id)
    if not entity:
        return {"error": "Objective not found"}

    for key, value in fields.items():
        if key not in _OBJECTIVE_EDITABLE or value is None:
            continue
        if key in ("target_value", "budget_allocated"):
            value = _safe_float(value, None)
        entity.attributes[key] = value

    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)
    return _serialize_objective(entity)


def update_objective_progress(objective_id, progress_pct, updated_by):
    entity = _get_objective_entity(objective_id)
    if not entity:
        return {"error": "Objective not found"}

    pct = _safe_float(progress_pct, None)
    if pct is None or pct < 0 or pct > 100:
        return {"error": "progress_pct must be a number between 0 and 100"}

    dept_lower = entity.attributes.get("department", "").lower()
    entity.attributes["manual_progress_pct"] = pct
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)

    result = _serialize_objective(entity)
    if dept_lower in GOAL_METRIC_CATALOG:
        result["note"] = "manual_progress_pct was recorded, but this department has a real ledger pace signal, which the computed status prefers over a manual self-report."
    return result


def update_objective_budget(objective_id, updated_by, budget_allocated=None, budget_spent=None):
    entity = _get_objective_entity(objective_id)
    if not entity:
        return {"error": "Objective not found"}

    if budget_allocated is not None:
        entity.attributes["budget_allocated"] = _safe_float(budget_allocated, None)
    if budget_spent is not None:
        entity.attributes["budget_spent"] = _safe_float(budget_spent, None)

    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)
    result = _serialize_objective(entity)
    result["budget_spent_note"] = "budget_spent is manually entered -- no expense-ledger-per-objective concept exists anywhere in this codebase to compute real spend automatically."
    return result


def cancel_objective(objective_id, updated_by):
    entity = _get_objective_entity(objective_id)
    if not entity:
        return {"error": "Objective not found"}
    entity.attributes["is_cancelled"] = True
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)
    return _serialize_objective(entity)


def reopen_objective(objective_id, updated_by):
    entity = _get_objective_entity(objective_id)
    if not entity:
        return {"error": "Objective not found"}
    entity.attributes["is_cancelled"] = False
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)
    return _serialize_objective(entity)


def sync_objective_to_monthly_goal(objective_id, updated_by):
    """The real coupling with core/system_config.py's department_goals (see
    this module's own docstring). A one-way, explicit push -- never
    automatic -- of this objective's quarterly target_value (divided evenly
    by 3) into Performance Readiness's real monthly goal slot."""

    entity = _get_objective_entity(objective_id)
    if not entity:
        return {"error": "Objective not found"}

    dept_lower = entity.attributes.get("department", "").lower()
    if dept_lower not in GOAL_TRACKED_DEPARTMENTS:
        return {
            "error": (
                f"'{entity.attributes.get('department')}' isn't one of Performance Readiness's "
                f"goal-tracked departments ({', '.join(GOAL_TRACKED_DEPARTMENTS)}) -- there's no "
                f"monthly goal slot to sync to."
            )
        }

    target = entity.attributes.get("target_value")
    if target is None:
        return {"error": "This objective has no target_value set -- nothing to sync."}

    monthly_target = round(target / 3, 2)
    result = set_department_goal(dept_lower, monthly_target, updated_by)
    if isinstance(result, dict) and "error" in result:
        return result

    entity.attributes["synced_monthly_goal"] = True
    entity.attributes["synced_monthly_target"] = monthly_target
    entity.attributes["synced_at"] = _now_iso()
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)

    out = _serialize_objective(entity)
    out["note"] = (
        f"Pushed {monthly_target} (this objective's target_value / 3) into "
        f"core/system_config.py's department_goals['{dept_lower}'] -- Performance "
        f"Readiness will now compare its real monthly pace against this number. "
        f"This is a one-way push, not a live link -- re-run this action after "
        f"editing the objective's target_value to re-sync."
    )
    return out


def get_quarterly_rollup(quarter=None, year=None):
    quarter = quarter or _current_quarter_year()[0]
    year = year or _current_quarter_year()[1]

    objs = list_objectives(quarter=quarter, year=year)["objectives"]

    by_department = {}
    status_counts = {}
    for o in objs:
        by_department.setdefault(o["department"], []).append(o)
        status_counts[o["status"]] = status_counts.get(o["status"], 0) + 1

    return {
        "quarter": quarter, "year": year, "count": len(objs),
        "objectives": objs, "by_department": by_department, "status_counts": status_counts,
    }


# ---------------------------------------------------------------------------
# Initiatives
# ---------------------------------------------------------------------------

def _get_initiative_entity(initiative_id):
    e = ledger.get_entity(initiative_id)
    if e and e.entity_type == STRATEGIC_INITIATIVE:
        return e
    return None


def get_initiative_progress(attrs):
    """Real progress where a real graph signal exists (website publish
    status, installed-device count); an honest manual self-report
    otherwise. See this module's own docstring for the full reasoning."""

    tracking_type = attrs.get("tracking_type", "manual")
    catalog = TRACKING_TYPE_CATALOG.get(tracking_type, TRACKING_TYPE_CATALOG["manual"])

    if tracking_type == "website_launch":
        website_id = attrs.get("linked_entity_id")
        website = get_website(website_id) if website_id else None
        if not website:
            return {"progress_pct": None, "basis": catalog["basis"], "error": "Linked website not found."}
        status = website.attributes.get("status", "draft")
        progress_pct = _WEBSITE_STATUS_PROGRESS.get(status, 0.0)
        detail = {"website_id": website_id, "website_status": status}
        try:
            analytics = get_website_analytics(website_id)
            if isinstance(analytics, dict) and "error" not in analytics:
                detail["total_views"] = analytics.get("total_views")
        except Exception:
            pass
        return {"progress_pct": progress_pct, "basis": catalog["basis"], "detail": detail}

    if tracking_type == "gps_rollout":
        devices = list_devices()
        count = devices.get("count", 0) if isinstance(devices, dict) else 0
        target = attrs.get("target_metric_value")
        progress_pct = min(100.0, round(count / target * 100, 1)) if target else None
        return {
            "progress_pct": progress_pct, "basis": catalog["basis"],
            "detail": {"installed_device_count": count, "target_device_count": target},
        }

    # manual
    pct = attrs.get("manual_progress_pct")
    return {"progress_pct": pct, "basis": "manual", "note": catalog["note"]}


def _serialize_initiative(entity):
    progress = get_initiative_progress(entity.attributes)
    return {"id": entity.id, **entity.attributes, "progress": progress}


def create_initiative(name, department, tracking_type, created_by, description="",
                       owner_employee_id=None, start_date=None, target_completion_date=None,
                       budget_allocated=None, linked_entity_id=None, target_metric_value=None):

    if not name or not name.strip():
        return {"error": "name is required"}

    if department not in STRATEGIC_DEPARTMENTS:
        return {"error": f"department must be one of {STRATEGIC_DEPARTMENTS}"}

    if tracking_type not in TRACKING_TYPE_CATALOG:
        return {"error": f"tracking_type must be one of {list(TRACKING_TYPE_CATALOG.keys())}"}

    catalog = TRACKING_TYPE_CATALOG[tracking_type]

    if catalog["requires_linked_entity_id"] and not linked_entity_id:
        return {"error": f"tracking_type '{tracking_type}' requires a linked_entity_id."}

    if tracking_type == "website_launch":
        if not get_website(linked_entity_id):
            return {"error": f"Website '{linked_entity_id}' not found."}

    if catalog["requires_target_metric"] and target_metric_value is None:
        return {"error": f"tracking_type '{tracking_type}' requires a target_metric_value."}

    target_metric_value = _safe_float(target_metric_value, None) if target_metric_value is not None else None
    budget_allocated = _safe_float(budget_allocated, None) if budget_allocated is not None else None

    initiative_id = id_generator.generate("INIT")
    entity = Entity(
        id=initiative_id,
        entity_type=STRATEGIC_INITIATIVE,
        attributes={
            "name": name.strip(),
            "description": description or "",
            "department": department,
            "owner_employee_id": owner_employee_id,
            "status": "planned",
            "status_history": [{"status": "planned", "by": created_by, "at": _now_iso()}],
            "start_date": start_date,
            "target_completion_date": target_completion_date,
            "budget_allocated": budget_allocated,
            "budget_spent": None,
            "tracking_type": tracking_type,
            "linked_entity_type": catalog["linked_entity_type"],
            "linked_entity_id": linked_entity_id,
            "target_metric_value": target_metric_value,
            "manual_progress_pct": None,
            "created_by": created_by,
            "created_at": _now_iso(),
            "updated_by": created_by,
            "updated_at": _now_iso(),
        },
    )

    ledger.add_entity(entity)
    save_graph(GRAPH_PATH)
    return _serialize_initiative(entity)


def get_initiative(initiative_id):
    entity = _get_initiative_entity(initiative_id)
    if not entity:
        return {"error": "Initiative not found"}
    return _serialize_initiative(entity)


def list_initiatives(department=None, status=None, tracking_type=None):
    items = _entities(STRATEGIC_INITIATIVE)
    if department:
        items = [i for i in items if i.attributes.get("department") == department]
    if status:
        items = [i for i in items if i.attributes.get("status") == status]
    if tracking_type:
        items = [i for i in items if i.attributes.get("tracking_type") == tracking_type]
    items.sort(key=lambda i: i.attributes.get("created_at", ""), reverse=True)
    return {"count": len(items), "initiatives": [_serialize_initiative(i) for i in items]}


def update_initiative_status(initiative_id, new_status, updated_by):
    entity = _get_initiative_entity(initiative_id)
    if not entity:
        return {"error": "Initiative not found"}

    current = entity.attributes.get("status")
    if current in _INITIATIVE_TERMINAL:
        return {"error": f"Initiative is already '{current}' -- no further status change is allowed."}

    if new_status not in INITIATIVE_STATUSES:
        return {"error": f"status must be one of {INITIATIVE_STATUSES}"}

    if new_status not in _INITIATIVE_TRANSITIONS.get(current, set()):
        return {"error": f"Cannot move from '{current}' to '{new_status}'. Valid next steps: {sorted(_INITIATIVE_TRANSITIONS.get(current, set()))}"}

    entity.attributes["status"] = new_status
    entity.attributes.setdefault("status_history", []).append({"status": new_status, "by": updated_by, "at": _now_iso()})
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)
    return _serialize_initiative(entity)


def update_initiative_progress(initiative_id, progress_pct, updated_by):
    entity = _get_initiative_entity(initiative_id)
    if not entity:
        return {"error": "Initiative not found"}

    if entity.attributes.get("tracking_type") != "manual":
        return {
            "error": (
                f"This initiative tracks progress automatically via "
                f"'{entity.attributes.get('tracking_type')}' -- manual progress can only be "
                f"recorded on a 'manual'-tracked initiative."
            )
        }

    pct = _safe_float(progress_pct, None)
    if pct is None or pct < 0 or pct > 100:
        return {"error": "progress_pct must be a number between 0 and 100"}

    entity.attributes["manual_progress_pct"] = pct
    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)
    return _serialize_initiative(entity)


def update_initiative_budget(initiative_id, updated_by, budget_allocated=None, budget_spent=None):
    entity = _get_initiative_entity(initiative_id)
    if not entity:
        return {"error": "Initiative not found"}

    if budget_allocated is not None:
        entity.attributes["budget_allocated"] = _safe_float(budget_allocated, None)
    if budget_spent is not None:
        entity.attributes["budget_spent"] = _safe_float(budget_spent, None)

    entity.attributes["updated_by"] = updated_by
    entity.attributes["updated_at"] = _now_iso()
    save_graph(GRAPH_PATH)
    result = _serialize_initiative(entity)
    result["budget_spent_note"] = "budget_spent is manually entered -- no expense-ledger-per-initiative concept exists anywhere in this codebase to compute real spend automatically."
    return result


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

def get_strategic_planning_overview(quarter=None, year=None):
    rollup = get_quarterly_rollup(quarter=quarter, year=year)

    all_initiatives = list_initiatives()
    init_status_counts = {}
    for i in all_initiatives["initiatives"]:
        init_status_counts[i["status"]] = init_status_counts.get(i["status"], 0) + 1

    return {
        "quarterly_rollup": rollup,
        "current_quarter": _current_quarter_year()[0],
        "current_year": _current_quarter_year()[1],
        "initiatives_summary": {"count": all_initiatives["count"], "by_status": init_status_counts},
        "initiatives": all_initiatives["initiatives"],
        "department_options": list(STRATEGIC_DEPARTMENTS),
        "goal_tracked_departments": list(GOAL_TRACKED_DEPARTMENTS),
        "tracking_type_catalog": TRACKING_TYPE_CATALOG,
        "not_yet_tracked": {
            "budget_ledger": (
                "budget_spent is manually entered by an ADMIN/OPERATIONS user on both Objectives "
                "and Initiatives -- no expense-ledger-per-objective/initiative concept exists "
                "anywhere in this codebase to compute real spend automatically."
            ),
            "non_goal_department_status": (
                "Only Sales/Service/Marketing objectives get a real, live-computed status against "
                "actual ledger pace (core/performance_readiness.py's same real signal sources, "
                "generalized to a full quarter). Finance/Inventory/Operations/Administration/"
                "Company-Wide objectives -- and any Sales/Service/Marketing objective with no "
                "target_value set -- rely on an owner's own manual_progress_pct self-report, "
                "honestly labeled current_value_basis='manual' rather than fabricated as real."
            ),
        },
    }
