"""
Reconditioning cycle-time + SLA analytics -- competitive roadmap Phase 6 (2026-07-25).
core/vehicle_lifecycle.py already models the recon pipeline (Acquired -> ... -> Front Line
Ready) with a real per-vehicle status history. What the competitive analysis flagged as
missing vs. Reynolds' recon tracker is the ANALYTICS layer on top: time-in-stage, recon
cycle time (acquired -> front-line-ready), and SLA/aging alerts so no vehicle silently
stalls. This module computes exactly that from the existing lifecycle_status_history --
no new state, no new entity, just measurement.

Cycle time and time-in-stage are derived from the real status-history timestamps. A vehicle
with no history (its status is the computed default, never explicitly set) is excluded from
cycle-time stats rather than fabricating a start time.
"""

from datetime import datetime, timezone

from core.dealeros import ledger
from core.entity_types import VEHICLE
from core.vehicle_lifecycle import LIFECYCLE_STAGES


FRONT_LINE_READY = "Front Line Ready"

# The recon pipeline (everything up to and including Front Line Ready). Sold/Delivered are
# post-recon and excluded from recon cycle-time.
RECON_PIPELINE = LIFECYCLE_STAGES[:LIFECYCLE_STAGES.index(FRONT_LINE_READY) + 1]

# Per-stage SLA in days -- how long a unit should spend in each stage before it's "aging".
# Business-reasonable defaults; a dealer would tune these.
STAGE_SLA_DAYS = {
    "Acquired": 2,
    "In Transit": 5,
    "Received": 1,
    "Inspection": 2,
    "Recon": 5,
    "Photo": 1,
    "Merchandising": 1,
}


def _now():
    return datetime.now(timezone.utc)


def _parse(ts):
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _history(vehicle):
    hist = vehicle.attributes.get("lifecycle_status_history") or []
    parsed = [(h.get("status"), _parse(h.get("at"))) for h in hist]
    return [(s, t) for s, t in parsed if t is not None]


def _stage_durations(vehicle):
    """Days spent in each stage, from consecutive history entries; the current (last) stage
    runs to now. Returns (list of {stage, entered_at, days}, reached_flr_at)."""
    hist = _history(vehicle)
    if not hist:
        return [], None
    durations = []
    reached_flr_at = None
    for i, (stage, at) in enumerate(hist):
        end = hist[i + 1][1] if i + 1 < len(hist) else _now()
        days = round((end - at).total_seconds() / 86400, 2)
        durations.append({"stage": stage, "entered_at": at.isoformat(), "days": days, "current": i == len(hist) - 1})
        if stage == FRONT_LINE_READY and reached_flr_at is None:
            reached_flr_at = at
    return durations, reached_flr_at


def _recon_vehicles():
    return [e for e in ledger.get_all().values() if e.entity_type == VEHICLE and (e.attributes.get("lifecycle_status_history"))]


def get_vehicle_recon_timeline(vehicle_id):
    """Per-vehicle stage-by-stage recon timeline + cycle time to front-line-ready."""
    vehicle = ledger.get_entity(vehicle_id)
    if not vehicle or vehicle.entity_type != VEHICLE:
        return {"error": "Vehicle not found"}
    durations, flr_at = _stage_durations(vehicle)
    if not durations:
        return {"vehicle_id": vehicle_id, "stages": [], "cycle_time_days": None, "note": "No recon history on this vehicle yet."}

    start = _parse(vehicle.attributes["lifecycle_status_history"][0].get("at"))
    cycle_time = round((flr_at - start).total_seconds() / 86400, 2) if (flr_at and start) else None
    current = durations[-1]
    sla = STAGE_SLA_DAYS.get(current["stage"])
    breaching = sla is not None and current["days"] > sla

    return {
        "vehicle_id": vehicle_id,
        "current_stage": current["stage"],
        "days_in_current_stage": current["days"],
        "current_stage_sla_days": sla,
        "sla_breaching": breaching,
        "reached_front_line_ready": flr_at is not None,
        "cycle_time_days": cycle_time,
        "stages": durations,
    }


def get_recon_sla_alerts():
    """Vehicles currently sitting in a recon stage past its SLA, worst overage first."""
    alerts = []
    for v in _recon_vehicles():
        durations, flr_at = _stage_durations(v)
        if not durations:
            continue
        current = durations[-1]
        if current["stage"] not in STAGE_SLA_DAYS:
            continue  # terminal / post-recon stage
        sla = STAGE_SLA_DAYS[current["stage"]]
        if current["days"] > sla:
            alerts.append({
                "vehicle_id": v.id,
                "vehicle": f"{v.attributes.get('Year', '')} {v.attributes.get('Make', '')} {v.attributes.get('Model', '')}".strip(),
                "stage": current["stage"],
                "days_in_stage": current["days"],
                "sla_days": sla,
                "days_over": round(current["days"] - sla, 2),
            })
    alerts.sort(key=lambda a: a["days_over"], reverse=True)
    return {"count": len(alerts), "alerts": alerts}


def get_recon_metrics():
    """Aggregate recon health: how many units in each stage, average time in each stage,
    average cycle time to front-line-ready, and how many are breaching SLA."""
    stage_counts = {s: 0 for s in RECON_PIPELINE}
    stage_days = {s: [] for s in STAGE_SLA_DAYS}
    cycle_times = []
    breaching = 0
    total = 0

    for v in _recon_vehicles():
        durations, flr_at = _stage_durations(v)
        if not durations:
            continue
        total += 1
        current = durations[-1]
        if current["stage"] in stage_counts:
            stage_counts[current["stage"]] += 1
        if current["stage"] in STAGE_SLA_DAYS and current["days"] > STAGE_SLA_DAYS[current["stage"]]:
            breaching += 1
        # accumulate completed stage durations (all but possibly-open current)
        for d in durations:
            if d["stage"] in stage_days and not d["current"]:
                stage_days[d["stage"]].append(d["days"])
        start = _parse(v.attributes["lifecycle_status_history"][0].get("at"))
        if flr_at and start:
            cycle_times.append(round((flr_at - start).total_seconds() / 86400, 2))

    def _avg(xs):
        return round(sum(xs) / len(xs), 2) if xs else None

    return {
        "vehicles_tracked": total,
        "in_stage": stage_counts,
        "avg_days_in_stage": {s: _avg(v) for s, v in stage_days.items()},
        "avg_cycle_time_days": _avg(cycle_times),
        "front_line_ready_count": len(cycle_times),
        "sla_breaching_count": breaching,
        "stage_sla_days": STAGE_SLA_DAYS,
    }
