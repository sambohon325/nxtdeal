"""
Bumper-parity Leads Configuration (2026-07-25): named lead-distribution rules --
match by source/geography, route to a team via round-robin / least-busy / a specific rep,
priority ordering, non-destructive preview, and the ADF/HTTP endpoint (simulated). Run
from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, LEAD, LEAD_ROUTING_RULE
from core.relationships import Relationship
from core.relationship_types import ASSIGNED_TO
from core import lead_routing_rules as lrr
from core import lead_routing_rules_api as lrr_api
from core.lead_assignment import get_assigned_employee


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def _emp(emp_id, department="Sales", first="A"):
    ledger.add_entity(Entity(id=emp_id, entity_type=EMPLOYEE,
                             attributes={"EmployeeID": emp_id, "FirstName": first, "LastName": "X", "Department": department}))


def _lead(lead_id, source="Website", state="TX", city="Austin", pipeline="NEW"):
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={
        "LeadID": lead_id, "Source": source, "State": state, "City": city, "PipelineState": pipeline,
    }))


# --- CRUD + validation ---

def test_create_validates_strategy_and_targets():
    assert "error" in lrr.create_routing_rule("R", "EMP-A", "telepathy")
    assert "error" in lrr.create_routing_rule("R", "EMP-A", "round_robin")            # no department
    assert "error" in lrr.create_routing_rule("R", "EMP-A", "specific_employee")      # no employee
    _emp("EMP-1")
    rule = lrr.create_routing_rule("Website team", "EMP-A", "round_robin", target_department="Sales",
                                   match_sources=["Website"])
    assert rule.entity_type == LEAD_ROUTING_RULE
    assert rule.attributes["is_active"] is False        # created inactive


def test_specific_employee_target_must_exist():
    assert "error" in lrr.create_routing_rule("R", "EMP-A", "specific_employee", target_employee_id="EMP-NOPE")
    _emp("EMP-7")
    rule = lrr.create_routing_rule("Jane's leads", "EMP-A", "specific_employee", target_employee_id="EMP-7")
    assert rule.attributes["target_employee_id"] == "EMP-7"


# --- matching ---

def test_route_matches_on_source_and_geography():
    _emp("EMP-1")
    rule = lrr.create_routing_rule("TX website", "EMP-A", "specific_employee", target_employee_id="EMP-1",
                                   match_sources=["Website"], match_states=["TX"])
    lrr.set_routing_rule_active(rule.id, True)
    # A CA website lead does NOT match (state mismatch)...
    _lead("LEAD-CA", source="Website", state="CA")
    assert lrr.route_lead("LEAD-CA")["routed"] is False
    # ...a TX website lead does.
    _lead("LEAD-TX", source="Website", state="TX")
    result = lrr.route_lead("LEAD-TX")
    assert result["routed"] is True and result["assigned_to"] == "EMP-1"


def test_empty_conditions_match_any():
    _emp("EMP-1")
    rule = lrr.create_routing_rule("Catch-all", "EMP-A", "specific_employee", target_employee_id="EMP-1")
    lrr.set_routing_rule_active(rule.id, True)
    _lead("LEAD-1", source="Referral", state="NY")
    assert lrr.route_lead("LEAD-1")["assigned_to"] == "EMP-1"


# --- strategies ---

def test_round_robin_rotates_across_department_roster():
    for e in ("EMP-1", "EMP-2", "EMP-3"):
        _emp(e)
    rule = lrr.create_routing_rule("RR", "EMP-A", "round_robin", target_department="Sales")
    lrr.set_routing_rule_active(rule.id, True)
    picks = []
    for i in range(4):
        _lead(f"LEAD-{i}")
        picks.append(lrr.route_lead(f"LEAD-{i}")["assigned_to"])
    # roster sorted -> EMP-1, EMP-2, EMP-3, then wraps back to EMP-1
    assert picks == ["EMP-1", "EMP-2", "EMP-3", "EMP-1"]


def test_least_busy_picks_lightest_roster_member():
    _emp("EMP-1")
    _emp("EMP-2")
    # EMP-1 already carries an active lead; EMP-2 is free.
    _lead("LEAD-EXIST")
    ledger.add_relationship(Relationship(source_id="EMP-1", target_id="LEAD-EXIST", relationship_type=ASSIGNED_TO))
    rule = lrr.create_routing_rule("LB", "EMP-A", "least_busy", target_department="Sales")
    lrr.set_routing_rule_active(rule.id, True)
    _lead("LEAD-NEW")
    assert lrr.route_lead("LEAD-NEW")["assigned_to"] == "EMP-2"


# --- priority ordering ---

def test_lower_priority_number_wins():
    _emp("EMP-1")
    _emp("EMP-2")
    broad = lrr.create_routing_rule("Broad", "EMP-A", "specific_employee", target_employee_id="EMP-1", priority=100)
    narrow = lrr.create_routing_rule("Narrow", "EMP-A", "specific_employee", target_employee_id="EMP-2",
                                     match_sources=["Website"], priority=10)
    lrr.set_routing_rule_active(broad.id, True)
    lrr.set_routing_rule_active(narrow.id, True)
    _lead("LEAD-1", source="Website")
    # both match, but the narrow (priority 10) rule fires first
    assert lrr.route_lead("LEAD-1")["assigned_to"] == "EMP-2"


# --- assignment writes both relationship and attribute ---

def test_route_writes_relationship_and_attribute_mirror():
    _emp("EMP-1")
    rule = lrr.create_routing_rule("R", "EMP-A", "specific_employee", target_employee_id="EMP-1")
    lrr.set_routing_rule_active(rule.id, True)
    _lead("LEAD-1")
    lrr.route_lead("LEAD-1")
    assert get_assigned_employee("LEAD-1") == "EMP-1"                       # relationship
    assert ledger.get_entity("LEAD-1").attributes["AssignedSalesperson"] == "EMP-1"  # mirror


# --- preview is non-destructive ---

def test_preview_does_not_assign_or_advance_rotation():
    _emp("EMP-1")
    _emp("EMP-2")
    rule = lrr.create_routing_rule("RR", "EMP-A", "round_robin", target_department="Sales")
    lrr.set_routing_rule_active(rule.id, True)
    p1 = lrr.preview_route({"Source": "Website"})
    p2 = lrr.preview_route({"Source": "Website"})
    assert p1["matched"] is True and p1["would_assign_to"] == "EMP-1"
    assert p2["would_assign_to"] == "EMP-1"          # pointer did NOT advance
    # And nothing was assigned.
    assert lrr.get_routing_rule(rule.id).attributes["next_index"] == 0


# --- inactive rules never fire ---

def test_inactive_rule_is_ignored():
    _emp("EMP-1")
    lrr.create_routing_rule("R", "EMP-A", "specific_employee", target_employee_id="EMP-1")  # left inactive
    _lead("LEAD-1")
    assert lrr.route_lead("LEAD-1")["routed"] is False


# --- ADF/HTTP endpoint dispatch is reported as simulated ---

def test_endpoint_dispatch_is_simulated():
    _emp("EMP-1")
    rule = lrr.create_routing_rule("R", "EMP-A", "specific_employee", target_employee_id="EMP-1",
                                   endpoint={"type": "adf", "url": "https://crm.example.com/adf"})
    lrr.set_routing_rule_active(rule.id, True)
    _lead("LEAD-1")
    result = lrr.route_lead("LEAD-1")
    assert result["endpoint_dispatch"]["delivered"] is False
    assert result["endpoint_dispatch"]["simulated"] is True


# --- API role gating ---

def test_api_manage_requires_admin_ops():
    from core.permissions import ADMIN, SALES
    _emp("EMP-1")
    assert "error" in lrr_api.create_routing_rule_api(SALES, "EMP-A", "R", "specific_employee", target_employee_id="EMP-1")
    ok = lrr_api.create_routing_rule_api(ADMIN, "EMP-A", "R", "specific_employee", target_employee_id="EMP-1")
    assert "id" in ok
    # Routing/preview are open to any authed role.
    lrr_api.set_routing_rule_active_api(ADMIN, "EMP-A", ok["id"], True)
    _lead("LEAD-1")
    assert lrr_api.route_lead_api(SALES, "EMP-B", "LEAD-1")["routed"] is True
