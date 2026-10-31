"""
Phase 6 (2026-07-25): reconditioning cycle-time + SLA analytics over the existing vehicle
lifecycle history. Run from backend/ with `pytest`.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import VEHICLE
from core import recon_analytics as ra


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def _iso(dt):
    return dt.isoformat()


def _vehicle(vid, history):
    """history: list of (stage, datetime)."""
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes={
        "Year": 2022, "Make": "X", "Model": "Y",
        "lifecycle_status": history[-1][0],
        "lifecycle_status_history": [{"status": s, "at": _iso(t), "by": "EMP-1"} for s, t in history],
    }))


def test_cycle_time_computed_to_front_line_ready():
    now = datetime.now(timezone.utc)
    _vehicle("VEH-1", [
        ("Acquired", now - timedelta(days=10)),
        ("Inspection", now - timedelta(days=8)),
        ("Recon", now - timedelta(days=6)),
        ("Front Line Ready", now - timedelta(days=2)),
    ])
    tl = ra.get_vehicle_recon_timeline("VEH-1")
    assert tl["reached_front_line_ready"] is True
    assert 7.9 <= tl["cycle_time_days"] <= 8.1  # acquired 10d ago -> FLR 2d ago = 8 days
    assert tl["current_stage"] == "Front Line Ready"


def test_sla_breach_detected_for_stalled_stage():
    now = datetime.now(timezone.utc)
    # Sitting in Recon (SLA 5 days) for 9 days.
    _vehicle("VEH-STALL", [
        ("Acquired", now - timedelta(days=11)),
        ("Recon", now - timedelta(days=9)),
    ])
    alerts = ra.get_recon_sla_alerts()
    assert alerts["count"] == 1
    a = alerts["alerts"][0]
    assert a["vehicle_id"] == "VEH-STALL" and a["stage"] == "Recon"
    assert a["days_over"] >= 3.9  # 9 - 5 = 4


def test_within_sla_not_alerted():
    now = datetime.now(timezone.utc)
    _vehicle("VEH-OK", [("Recon", now - timedelta(days=2))])  # 2d < 5d SLA
    assert ra.get_recon_sla_alerts()["count"] == 0


def test_metrics_aggregate():
    now = datetime.now(timezone.utc)
    _vehicle("VEH-1", [
        ("Acquired", now - timedelta(days=10)),
        ("Recon", now - timedelta(days=8)),
        ("Front Line Ready", now - timedelta(days=3)),
    ])
    _vehicle("VEH-2", [("Recon", now - timedelta(days=9))])  # stalled in Recon
    m = ra.get_recon_metrics()
    assert m["vehicles_tracked"] == 2
    assert m["front_line_ready_count"] == 1
    assert m["avg_cycle_time_days"] is not None
    assert m["sla_breaching_count"] == 1
    assert m["in_stage"]["Front Line Ready"] == 1
    assert m["in_stage"]["Recon"] == 1


def test_vehicle_without_history_excluded():
    ledger.add_entity(Entity(id="VEH-NOHIST", entity_type=VEHICLE, attributes={"Year": 2022}))
    m = ra.get_recon_metrics()
    assert m["vehicles_tracked"] == 0
    tl = ra.get_vehicle_recon_timeline("VEH-NOHIST")
    assert tl["cycle_time_days"] is None
