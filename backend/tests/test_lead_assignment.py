"""
Tests for core/lead_assignment.py — the graph-backed replacement for the old flat
`assignments = {lead_id: employee_id}` dict (assignment now lives as ASSIGNED_TO
relationships on the graph, see CLAUDE.md's "one graph" note, 2026-07-13). Monkeypatches
save_graph so these tests don't touch real disk. Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger

from core import lead_assignment
from core.lead_assignment import (
    assign_lead,
    get_assigned_employee,
    get_employee_leads,
    get_assigned_employee_ids,
)


@pytest.fixture(autouse=True)
def fresh_ledger_no_disk(monkeypatch):

    ledger.reset()

    monkeypatch.setattr(lead_assignment, "save_graph", lambda filepath: None)

    yield

    ledger.reset()


def test_assign_lead_creates_relationship():

    assign_lead("LEAD-1", "EMP-1")

    assert get_assigned_employee("LEAD-1") == "EMP-1"


def test_get_employee_leads_returns_all_currently_assigned():

    assign_lead("LEAD-1", "EMP-1")
    assign_lead("LEAD-2", "EMP-1")
    assign_lead("LEAD-3", "EMP-2")

    assert sorted(get_employee_leads("EMP-1")) == ["LEAD-1", "LEAD-2"]
    assert get_employee_leads("EMP-2") == ["LEAD-3"]


def test_reassignment_moves_lead_to_new_employee():
    """Relationships are append-only — reassigning must not leave the lead showing up
    for both the old and new employee."""

    assign_lead("LEAD-1", "EMP-1")
    assign_lead("LEAD-1", "EMP-2")

    assert get_assigned_employee("LEAD-1") == "EMP-2"
    assert get_employee_leads("EMP-1") == []
    assert get_employee_leads("EMP-2") == ["LEAD-1"]


def test_get_assigned_employee_ids_only_includes_current_assignees():

    assign_lead("LEAD-1", "EMP-1")
    assign_lead("LEAD-1", "EMP-2")  # EMP-1 no longer has any active leads

    assert get_assigned_employee_ids() == {"EMP-2"}


def test_unassigned_lead_returns_none():

    assert get_assigned_employee("LEAD-NOPE") is None
    assert get_employee_leads("EMP-NOPE") == []
