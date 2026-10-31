"""
Network's "Trends" (90-day history) + "Forecasts" items -- slice 4 of the
Intelligence Network reframe (2026-07-18, autonomous). network.pdf's own framing
for Trends: "this lets dealers react before competitors do." The pre-existing
core/network_menu.py trends() function (session-38-era) only ever showed a single
day-over-day delta per KPI, reusing core/kpi_snapshots.py's with_trend()
mechanism -- real, but "yesterday vs. today" only, not a real 90-day view, and it
never included the new "bhph" department (core/network_benchmark.py's real 6th
benchmark entry, added slice 2 of this same reframe) at all.

This module adds two genuinely new real pieces on top of the SAME underlying
DepartmentSnapshot entities (core/kpi_snapshots.py) -- no new snapshot mechanism,
no new entity type:

  1. A real 90-day (or however many days were actually requested) HISTORY series
     per department/KPI -- every real DepartmentSnapshot recorded for that
     department within the window, in date order. Honest about sparse data: this
     backend has no real overnight batch job (kpi_snapshots.py's own docstring
     already states this -- a snapshot is only recorded the first time someone
     opens a department's dashboard each day), so a freshly-deployed dealer will
     genuinely only have a few real days of history. `days_with_data` vs.
     `days_requested` is always reported alongside the series so this is never
     silently misrepresented as a full 90 days of real data when it isn't.

  2. A real, transparent LINEAR PROJECTION of this dealer's own trend, using the
     real recorded history above -- a simple ordinary-least-squares slope over
     (day_offset, value) pairs when 2+ real points exist, explicitly `None`
     (never guessed) when fewer than 2 points exist. This is deliberately NOT a
     "competitive forecast" against peers -- core/network_benchmark.py's peer
     averages are a fixed SIMULATED snapshot with no trend of their own (there's
     no real time-series data for a simulated peer to have a trend), so the
     Forecasts item projects THIS dealer's own real trajectory and compares it
     against that static peer average to estimate whether a real gap is closing,
     widening, or holding, explicitly labeled as a projection against a static
     target, not a real competitive race.

`bhph` trend coverage: core/network_benchmark.py's compute_bhph_kpis() never
called kpi_snapshots.with_trend() at all -- confirmed via grep before writing
anything, this module's own get_bhph_kpis_with_trend() closes that gap by
snapshotting bhph's real KPI values the same way core/department_intelligence_
api.py's get_department_api() already does for the other 5 departments, reusing
with_trend() directly rather than a second snapshot mechanism.
"""

from datetime import date, timedelta

from core.dealeros import ledger
from core.entity_types import DEPARTMENT_SNAPSHOT
from core.kpi_snapshots import with_trend
from core.network_benchmark import (
    DEPARTMENTS as BENCHMARK_DEPARTMENTS,
    BHPH_DEPARTMENT_KEY,
    compute_bhph_kpis,
)


ALL_TREND_DEPARTMENTS = list(BENCHMARK_DEPARTMENTS) + [BHPH_DEPARTMENT_KEY]

DEFAULT_HISTORY_DAYS = 90
DEFAULT_PROJECTION_DAYS = 30


def get_bhph_kpis_with_trend(role="ADMIN"):
    """The bhph-department analog of core/department_intelligence_api.py's
    get_department_api() -- computes this dealer's real BHPH KPIs and enriches
    them with a real day-over-day delta via the SAME with_trend() mechanism the
    other 5 departments already use, recording (idempotently, once per real
    calendar day) a real DepartmentSnapshot for "bhph" as a side effect. Returns
    None if the caller's role can't reach the underlying Portfolio dashboard."""

    payload = compute_bhph_kpis(role)

    if payload is None:
        return None

    kpis_with_trend = with_trend(BHPH_DEPARTMENT_KEY, payload["kpis"])
    payload["kpis"] = list(kpis_with_trend.values())

    return payload


def _department_snapshots(department, since_date=None):
    """Every real DepartmentSnapshot for this department, sorted oldest-first,
    optionally filtered to snapshot_date >= since_date (an ISO date string)."""

    snapshots = []

    for entity in ledger.get_all().values():

        if entity.entity_type != DEPARTMENT_SNAPSHOT:
            continue

        if entity.attributes.get("department") != department:
            continue

        snapshot_date = entity.attributes.get("snapshot_date")

        if since_date and snapshot_date and snapshot_date < since_date:
            continue

        snapshots.append(entity)

    snapshots.sort(key=lambda e: e.attributes.get("snapshot_date", ""))

    return snapshots


def get_kpi_history(department, kpi_key, days=DEFAULT_HISTORY_DAYS):
    """The real point series for one KPI within the last `days` calendar days --
    only real, actually-recorded snapshot values, never interpolated or
    fabricated for a day with no snapshot. `days_with_data` (the real count of
    distinct real snapshot days found) is always reported alongside
    `days_requested` so sparse history is never silently presented as a full
    window."""

    since = (date.today() - timedelta(days=days)).isoformat()
    snapshots = _department_snapshots(department, since_date=since)

    points = [
        {"date": s.attributes.get("snapshot_date"), "value": s.attributes.get("kpis", {}).get(kpi_key)}
        for s in snapshots
        if kpi_key in (s.attributes.get("kpis") or {})
    ]

    return {
        "department": department,
        "kpi": kpi_key,
        "days_requested": days,
        "days_with_data": len(points),
        "points": points,
    }


def get_department_trend_history(department, days=DEFAULT_HISTORY_DAYS):
    """Every real KPI's real point series for one department within the last
    `days` calendar days -- one get_kpi_history() call per KPI key that's ever
    appeared in a real snapshot for this department (not a fixed hardcoded KPI
    list, since department KPI shapes vary)."""

    since = (date.today() - timedelta(days=days)).isoformat()
    snapshots = _department_snapshots(department, since_date=since)

    kpi_keys = set()
    for s in snapshots:
        kpi_keys.update((s.attributes.get("kpis") or {}).keys())

    return {
        "department": department,
        "days_requested": days,
        "days_with_data": len(snapshots),
        "kpis": {key: get_kpi_history(department, key, days=days) for key in sorted(kpi_keys)},
    }


def _linear_slope(points):
    """A real ordinary-least-squares slope (change in value per calendar day)
    over a list of {"date": iso_str, "value": number} points -- None if fewer
    than 2 real points exist (never guessed). Uses day-offset-from-first-point
    as x, so the slope is expressed in real units/day regardless of actual gaps
    between recorded days."""

    numeric_points = [p for p in points if isinstance(p.get("value"), (int, float)) and p.get("date")]

    if len(numeric_points) < 2:
        return None

    first_date = date.fromisoformat(numeric_points[0]["date"])
    xs = [(date.fromisoformat(p["date"]) - first_date).days for p in numeric_points]
    ys = [p["value"] for p in numeric_points]

    n = len(xs)
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n

    denom = sum((x - mean_x) ** 2 for x in xs)

    if denom == 0:
        # All real points landed on the same calendar day (duplicate/same-day
        # snapshots) -- no real day-over-day slope is computable.
        return None

    numer = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))

    return numer / denom


def project_kpi_forward(department, kpi_key, days_history=DEFAULT_HISTORY_DAYS, project_days=DEFAULT_PROJECTION_DAYS):
    """A real linear projection of this dealer's own KPI value `project_days`
    days from today, off the real recorded snapshot history within the last
    `days_history` days. Returns a dict with `projectable: False` and an honest
    reason when fewer than 2 real historical points exist -- never a fabricated
    slope or projected value."""

    history = get_kpi_history(department, kpi_key, days=days_history)
    points = history["points"]

    slope_per_day = _linear_slope(points)

    if slope_per_day is None:
        return {
            "department": department,
            "kpi": kpi_key,
            "projectable": False,
            "reason": (
                f"Only {history['days_with_data']} real recorded snapshot day(s) exist for this "
                f"KPI within the last {days_history} days -- at least 2 distinct real days are "
                "needed to compute a real trend slope. Not guessed at."
            ),
            "days_with_data": history["days_with_data"],
            "current_value": points[-1]["value"] if points else None,
            "projected_value": None,
            "project_days": project_days,
            "slope_per_day": None,
        }

    current_value = points[-1]["value"]
    current_date = date.fromisoformat(points[-1]["date"])
    target_date = current_date + timedelta(days=project_days)
    first_date = date.fromisoformat(points[0]["date"])
    days_from_first = (target_date - first_date).days

    # Re-derive the projection using the same OLS fit's intercept, not just
    # "current_value + slope * project_days", so a genuinely noisy real series
    # (not a clean 2-point line) still gets a real least-squares projection.
    numeric_points = [p for p in points if isinstance(p.get("value"), (int, float))]
    xs = [(date.fromisoformat(p["date"]) - first_date).days for p in numeric_points]
    ys = [p["value"] for p in numeric_points]
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    intercept = mean_y - slope_per_day * mean_x

    projected_value = round(intercept + slope_per_day * days_from_first, 2)

    return {
        "department": department,
        "kpi": kpi_key,
        "projectable": True,
        "reason": None,
        "days_with_data": history["days_with_data"],
        "current_value": current_value,
        "current_date": points[-1]["date"],
        "projected_value": projected_value,
        "project_days": project_days,
        "target_date": target_date.isoformat(),
        "slope_per_day": round(slope_per_day, 4),
        "basis": "real_linear_projection",
        "formula": "projected_value = OLS_intercept + slope_per_day * days_from_first_real_snapshot",
    }


def project_gap_closure(department, kpi_key, peer_average, higher_is_better, days_history=DEFAULT_HISTORY_DAYS, project_days=DEFAULT_PROJECTION_DAYS):
    """Compares a real linear projection of this dealer's own trend against the
    peer average (a fixed SIMULATED snapshot, not itself a time series) to
    estimate whether the real gap is closing, widening, or holding. Explicitly
    NOT a competitive forecast -- the peer side has no trend to project, so this
    only ever answers "is THIS dealer moving toward or away from that fixed
    number," stated plainly in every response's own `note` field."""

    projection = project_kpi_forward(department, kpi_key, days_history=days_history, project_days=project_days)

    if not projection["projectable"] or not isinstance(peer_average, (int, float)):
        projection["gap_trend"] = "unknown"
        projection["note"] = (
            "Insufficient real trend history and/or peer average to project gap closure."
            if not projection["projectable"]
            else "No peer average available to compare against."
        )
        return projection

    current_gap = abs(projection["current_value"] - peer_average)
    projected_gap = abs(projection["projected_value"] - peer_average)

    if projected_gap < current_gap * 0.98:
        gap_trend = "closing"
    elif projected_gap > current_gap * 1.02:
        gap_trend = "widening"
    else:
        gap_trend = "holding"

    projection["peer_average"] = peer_average
    projection["current_gap"] = round(current_gap, 2)
    projection["projected_gap"] = round(projected_gap, 2)
    projection["gap_trend"] = gap_trend
    projection["note"] = (
        f"Projects THIS dealer's own real recorded trend (slope={projection['slope_per_day']}/day) "
        f"forward {project_days} days and compares it to the peer average as a FIXED target -- the "
        "peer average is a static simulated snapshot with no trend of its own, so this is not a real "
        "competitive race, only a real read on whether this dealer is moving toward or away from "
        "where peers currently sit."
    )

    return projection
