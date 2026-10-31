"""
Tests for NXTDeal execution modes (core/execution_modes.py + _api.py) -- 2026-07-24, DR-2.
Run from backend/ with `pytest`.

Covers: the workflow catalog and its per-workflow supported modes (Lead Management omits
Customer); defaults are Human everywhere; setting a mode (and rejecting an unsupported one);
the allowed-actors matrix (human is never locked out; hybrid opens all three); the
require_actor gate other modules call (incl. fail-closed on unknown workflow/actor); and the
ADMIN gate on changing a mode.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.permissions import ADMIN, SALES

from core import execution_modes as xm
from core import execution_modes_api as xm_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def test_catalog_defaults_to_human_everywhere():
    data = xm.list_workflows()
    assert len(data["workflows"]) == len(xm.WORKFLOW_CATALOG)
    assert all(w["active_mode"] == "human" for w in data["workflows"])
    # Human mode permits only a human actor.
    lead = next(w for w in data["workflows"] if w["key"] == "lead_management")
    assert lead["allowed_actors"] == ["human"]
    assert lead["ai_enabled"] is False and lead["customer_enabled"] is False


def test_lead_management_omits_customer_mode():
    assert "customer" not in xm.supported_modes("lead_management")
    assert set(xm.supported_modes("desking")) == {"human", "ai", "customer", "hybrid"}


def test_set_mode_and_allowed_actors():
    xm.set_execution_mode("desking", "hybrid", "EMP-1")
    got = xm.get_workflow("desking")
    assert got["active_mode"] == "hybrid"
    assert set(got["allowed_actors"]) == {"human", "ai", "customer"}
    # AI mode: human + ai, not customer.
    xm.set_execution_mode("credit", "ai", "EMP-1")
    assert set(xm.allowed_actors("credit")) == {"human", "ai"}
    # Customer mode: human + customer, not ai.
    xm.set_execution_mode("fi", "customer", "EMP-1")
    assert set(xm.allowed_actors("fi")) == {"human", "customer"}


def test_set_rejects_unsupported_mode():
    res = xm.set_execution_mode("lead_management", "customer", "EMP-1")
    assert "error" in res and "does not support" in res["error"]
    # unchanged
    assert xm.get_workflow("lead_management")["active_mode"] == "human"


def test_set_rejects_unknown_workflow_and_mode():
    assert "error" in xm.set_execution_mode("nope", "human", "EMP-1")
    assert "error" in xm.set_execution_mode("desking", "banana", "EMP-1")


def test_require_actor_gate():
    # default human mode -> ai and customer blocked, human ok
    ok, err = xm.require_actor("desking", "customer")
    assert ok is False and "Human mode" in err
    ok, _ = xm.require_actor("desking", "human")
    assert ok is True
    # open it to customers
    xm.set_execution_mode("desking", "customer", "EMP-1")
    ok, err = xm.require_actor("desking", "customer")
    assert ok is True and err is None


def test_require_actor_fails_closed():
    ok, err = xm.require_actor("desking", "robot")
    assert ok is False and "Unknown actor" in err
    ok, err = xm.require_actor("no_such_workflow", "human")
    assert ok is False and "Unknown workflow" in err


def test_summary_counts():
    xm.set_execution_mode("desking", "hybrid", "EMP-1")
    xm.set_execution_mode("credit", "ai", "EMP-1")
    s = xm.execution_summary()
    assert s["total_workflows"] == len(xm.WORKFLOW_CATALOG)
    assert s["by_mode"]["hybrid"] == 1
    assert s["by_mode"]["ai"] == 1
    assert s["ai_enabled_workflows"] == 2          # hybrid + ai both enable AI
    assert s["customer_enabled_workflows"] == 1    # only the hybrid one


def test_singleton_policy_is_reused():
    xm.set_execution_mode("desking", "ai", "EMP-1")
    xm.set_execution_mode("credit", "hybrid", "EMP-2")
    policies = [e for e in ledger.get_all().values() if e.entity_type == "ExecutionPolicy"]
    assert len(policies) == 1


def test_api_view_open_and_set_admin_only():
    # view open to any role
    dash = xm_api.get_execution_modes_api(SALES)
    assert "workflows" in dash and "summary" in dash
    # non-admin cannot set
    assert "error" in xm_api.set_execution_mode_api(SALES, "EMP-9", "desking", "ai")
    # admin can
    got = xm_api.set_execution_mode_api(ADMIN, "EMP-1", "desking", "ai")
    assert got["workflow"]["active_mode"] == "ai"
