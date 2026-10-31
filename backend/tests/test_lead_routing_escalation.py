"""
Tests for the graph-backed lead assignment / routing / escalation cluster — the modules
that turn ASSIGNED_TO relationships (core/lead_assignment.py) plus each Lead's pipeline
state/age (core/pipeline_state.py + core/lead_aging.py) into routing decisions and the
figures behind the manager / workload / leaderboard / escalation dashboards:

    core/lead_routing.py         - get_active_workload, auto_assign_lead
    core/escalation.py           - get_escalated_leads
    core/escalation_routing.py   - reassign_escalated_lead
    core/employee_performance.py - get_employee_conversion_rate
    core/leaderboard.py          - get_sales_leaderboard
    core/workload_dashboard.py   - get_workload_dashboard

All six were rewritten 2026-07-13 in the "one graph" unification to read assignment and
pipeline state straight off the graph (see CLAUDE.md's "one graph" note) instead of the old
flat `assignments` dict + WorkflowInstance model, and back /lead/assign, /lead/escalate,
and the workload/leaderboard/escalation dashboards — but had no committed regression
coverage. This file is that coverage, added per BUILD_QUEUE.md's "convert tests
incrementally as modules get touched" standing item (sessions 46/48/49/71/72/74/75/76).

Everything seeds Lead entities + ASSIGNED_TO relationships directly into the ledger with
explicit states/timestamps, so it's fully deterministic and seed-independent (no dependency
on generate_seed_data.py, and no import of the FUSE-truncated *_menu/api.app chain).
save_graph is monkeypatched so assign_lead never touches real disk. Run from backend/ with
`pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

from datetime import datetime, timedelta

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD

from core import lead_assignment
from core.lead_assignment import assign_lead, get_assigned_employee

from core.pipeline_state import start_pipeline

from core.lead_routing import get_active_workload, auto_assign_lead
from core.escalation import get_escalated_leads
from core.escalation_routing import reassign_escalated_lead
from core.employee_performance import get_employee_conversion_rate
from core.leaderboard import get_sales_leaderboard
from core.workload_dashboard import get_workload_dashboard


@pytest.fixture(autouse=True)
def fresh_ledger_no_disk(monkeypatch):

    ledger.reset()

    # assign_lead() calls save_graph(GRAPH_PATH) on every write — stub it out.
    monkeypatch.setattr(lead_assignment, "save_graph", lambda filepath: None)

    yield

    ledger.reset()


def _add_lead(entity_id):

    ledger.add_entity(
        Entity(id=entity_id, entity_type=LEAD, attributes={})
    )


def _days_ago(n):
    """ISO timestamp exactly n days before now (matches test_lead_pipeline_analytics.py)."""

    return (datetime.now() - timedelta(days=n)).isoformat()


def _assigned_lead(lead_id, employee_id, state=None, age_days=0):
    """Seed a Lead, assign it to an employee, and optionally put it in the pipeline at
    `state`, having entered that state `age_days` ago."""

    _add_lead(lead_id)
    assign_lead(lead_id, employee_id)

    if state is not None:
        start_pipeline(lead_id, initial_state=state, timestamp=_days_ago(age_days))


# ---------------------------------------------------------------------------
# lead_routing.get_active_workload
# ---------------------------------------------------------------------------

def test_active_workload_counts_only_non_terminal_states():

    _assigned_lead("L1", "EMP-1", state="NEW")
    _assigned_lead("L2", "EMP-1", state="CONTACTED")
    _assigned_lead("L3", "EMP-1", state="SOLD")   # terminal, not counted
    _assigned_lead("L4", "EMP-1", state="LOST")   # terminal, not counted

    assert get_active_workload("EMP-1") == 2


def test_active_workload_ignores_leads_with_no_pipeline_state():

    _assigned_lead("L1", "EMP-1", state="NEW")
    _assigned_lead("L2", "EMP-1")   # assigned but never entered the pipeline -> None

    assert get_active_workload("EMP-1") == 1


def test_active_workload_zero_for_employee_with_no_leads():

    assert get_active_workload("EMP-NOBODY") == 0


# ---------------------------------------------------------------------------
# lead_routing.auto_assign_lead
# ---------------------------------------------------------------------------

def test_auto_assign_raises_when_no_employees_in_pool():

    _add_lead("NEW-LEAD")

    with pytest.raises(ValueError):
        auto_assign_lead("NEW-LEAD")


def test_auto_assign_picks_least_busy_employee():

    # EMP-1 carries two active leads, EMP-2 carries one -> new lead should go to EMP-2.
    _assigned_lead("A1", "EMP-1", state="NEW")
    _assigned_lead("A2", "EMP-1", state="CONTACTED")
    _assigned_lead("B1", "EMP-2", state="NEW")

    _add_lead("NEW-LEAD")

    chosen = auto_assign_lead("NEW-LEAD")

    assert chosen == "EMP-2"
    assert get_assigned_employee("NEW-LEAD") == "EMP-2"


def test_auto_assign_ignores_terminal_leads_when_measuring_busyness():

    # EMP-1 has 3 leads but 2 are terminal -> effective workload 1.
    # EMP-2 has 2 active leads -> workload 2. New lead should go to EMP-1.
    _assigned_lead("A1", "EMP-1", state="NEW")
    _assigned_lead("A2", "EMP-1", state="SOLD")
    _assigned_lead("A3", "EMP-1", state="LOST")
    _assigned_lead("B1", "EMP-2", state="NEW")
    _assigned_lead("B2", "EMP-2", state="CONTACTED")

    _add_lead("NEW-LEAD")

    assert auto_assign_lead("NEW-LEAD") == "EMP-1"


# ---------------------------------------------------------------------------
# escalation.get_escalated_leads
# ---------------------------------------------------------------------------

def test_escalated_flags_lead_at_or_past_default_threshold():

    _add_lead("OLD")
    start_pipeline("OLD", initial_state="CONTACTED", timestamp=_days_ago(14))  # exactly 14

    result = get_escalated_leads(["OLD"])

    assert result == [
        {
            "lead_id": "OLD",
            "current_state": "CONTACTED",
            "days_in_state": 14,
            "status": "ESCALATED",
        }
    ]


def test_escalated_excludes_lead_below_threshold():

    _add_lead("FRESH")
    start_pipeline("FRESH", initial_state="NEW", timestamp=_days_ago(5))

    assert get_escalated_leads(["FRESH"]) == []


def test_escalated_skips_sold_and_lost_regardless_of_age():

    _add_lead("SOLD-OLD")
    _add_lead("LOST-OLD")
    start_pipeline("SOLD-OLD", initial_state="SOLD", timestamp=_days_ago(90))
    start_pipeline("LOST-OLD", initial_state="LOST", timestamp=_days_ago(90))

    assert get_escalated_leads(["SOLD-OLD", "LOST-OLD"]) == []


def test_escalated_respects_custom_threshold():

    _add_lead("A")
    _add_lead("B")
    start_pipeline("A", initial_state="NEW", timestamp=_days_ago(10))
    start_pipeline("B", initial_state="NEW", timestamp=_days_ago(20))

    result = get_escalated_leads(["A", "B"], threshold_days=15)

    assert [r["lead_id"] for r in result] == ["B"]


# ---------------------------------------------------------------------------
# escalation_routing.reassign_escalated_lead
# ---------------------------------------------------------------------------

def test_reassign_raises_when_no_employees_in_pool():

    _add_lead("STUCK")

    with pytest.raises(ValueError):
        reassign_escalated_lead("STUCK")


def test_reassign_routes_to_least_busy_and_returns_status():

    _assigned_lead("A1", "EMP-1", state="NEW")
    _assigned_lead("A2", "EMP-1", state="NEW")
    _assigned_lead("B1", "EMP-2", state="NEW")

    _add_lead("STUCK")

    result = reassign_escalated_lead("STUCK")

    assert result == {
        "lead_id": "STUCK",
        "assigned_to": "EMP-2",
        "status": "REASSIGNED",
    }
    assert get_assigned_employee("STUCK") == "EMP-2"


# ---------------------------------------------------------------------------
# employee_performance.get_employee_conversion_rate
# ---------------------------------------------------------------------------

def test_conversion_rate_zero_when_no_leads():

    assert get_employee_conversion_rate("EMP-NOBODY") == 0


def test_conversion_rate_is_percentage_rounded_two_places():

    # 1 SOLD out of 3 assigned -> 33.33%
    _assigned_lead("L1", "EMP-1", state="SOLD")
    _assigned_lead("L2", "EMP-1", state="NEW")
    _assigned_lead("L3", "EMP-1", state="CONTACTED")

    assert get_employee_conversion_rate("EMP-1") == 33.33


def test_conversion_rate_zero_when_none_sold():

    _assigned_lead("L1", "EMP-1", state="NEW")
    _assigned_lead("L2", "EMP-1", state="LOST")

    assert get_employee_conversion_rate("EMP-1") == 0.0


# ---------------------------------------------------------------------------
# leaderboard.get_sales_leaderboard
# ---------------------------------------------------------------------------

def test_leaderboard_ranks_employees_by_conversion_rate_descending():

    _assigned_lead("A1", "EMP-1", state="SOLD")     # EMP-1 -> 100%
    _assigned_lead("B1", "EMP-2", state="NEW")       # EMP-2 -> 0%
    _assigned_lead("C1", "EMP-3", state="SOLD")
    _assigned_lead("C2", "EMP-3", state="NEW")       # EMP-3 -> 50%

    board = get_sales_leaderboard()

    assert [row["employee_id"] for row in board] == ["EMP-1", "EMP-3", "EMP-2"]
    assert board[0] == {"employee_id": "EMP-1", "conversion_rate": 100.0}
    assert board[1]["conversion_rate"] == 50.0
    assert board[-1]["conversion_rate"] == 0


# ---------------------------------------------------------------------------
# workload_dashboard.get_workload_dashboard
# ---------------------------------------------------------------------------

def test_workload_dashboard_sorts_ascending_by_active_workload():

    _assigned_lead("A1", "EMP-1", state="NEW")
    _assigned_lead("A2", "EMP-1", state="CONTACTED")   # EMP-1 -> 2
    _assigned_lead("B1", "EMP-2", state="NEW")          # EMP-2 -> 1

    dash = get_workload_dashboard()

    assert [row["employee_id"] for row in dash] == ["EMP-2", "EMP-1"]
    assert dash[0] == {"employee_id": "EMP-2", "active_workload": 1}
    assert dash[1] == {"employee_id": "EMP-1", "active_workload": 2}
