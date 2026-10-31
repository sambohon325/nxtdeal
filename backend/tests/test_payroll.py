"""
Phase 5 (2026-07-25): Payroll processing -- time clock, pay plans, deal commissions, and a
payroll run that generates real paychecks with simplified gross-to-net withholding. Run from
backend/ with `pytest`.
"""

import os
import sys
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import EMPLOYEE, DEAL, VEHICLE, CUSTOMER
from core import payroll
from core import payroll_api


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def _emp(eid="EMP-1"):
    ledger.add_entity(Entity(id=eid, entity_type=EMPLOYEE, attributes={"FirstName": "Pat", "LastName": "Lee", "Department": "Sales"}))
    return eid


def _iso(dt):
    return dt.isoformat()


# --- pay plans ---

def test_set_and_get_pay_plan():
    _emp()
    plan = payroll.set_pay_plan("EMP-1", "hourly", hourly_rate=20, state="CA")
    assert plan["plan_type"] == "hourly" and plan["hourly_rate"] == 20 and plan["state"] == "CA"
    assert payroll.get_pay_plan("EMP-1")["hourly_rate"] == 20


def test_pay_plan_validates():
    _emp()
    assert "error" in payroll.set_pay_plan("EMP-1", "bogus")
    assert "error" in payroll.set_pay_plan("EMP-NOPE", "hourly")


# --- time clock ---

def test_clock_in_out_computes_hours():
    _emp()
    now = datetime.now(timezone.utc)
    payroll.clock_in("EMP-1", at=_iso(now - timedelta(hours=8)))
    out = payroll.clock_out("EMP-1", at=_iso(now))
    assert 7.9 <= out["hours"] <= 8.1


def test_double_clock_in_blocked():
    _emp()
    payroll.clock_in("EMP-1")
    assert "error" in payroll.clock_in("EMP-1")
    assert payroll.get_open_entry("EMP-1") is not None


def test_clock_out_without_in_errors():
    _emp()
    assert "error" in payroll.clock_out("EMP-1")


# --- payroll run: hourly ---

def test_hourly_payroll_run_generates_paycheck():
    _emp()
    payroll.set_pay_plan("EMP-1", "hourly", hourly_rate=25, state="TX")  # TX = 0% state
    today = datetime.now(timezone.utc)
    payroll.clock_in("EMP-1", at=_iso(today - timedelta(hours=10)))
    payroll.clock_out("EMP-1", at=_iso(today))
    result = payroll.run_payroll((today - timedelta(days=1)).date().isoformat(), today.date().isoformat(), "EMP-ADMIN")
    assert result["statement_count"] == 1
    stmt = payroll.list_pay_statements(employee_id="EMP-1")[0]
    assert 9.9 <= stmt["hours"] <= 10.1
    assert abs(stmt["gross_pay"] - 250) < 1
    # TX: federal 12% + fica 7.65% + state 0% = 19.65% withheld
    assert abs(stmt["taxes"]["state"]) < 0.01
    assert abs(stmt["net_pay"] - 250 * (1 - 0.1965)) < 1.0


def test_state_tax_applied():
    _emp()
    payroll.set_pay_plan("EMP-1", "hourly", hourly_rate=100, state="CA")
    today = datetime.now(timezone.utc)
    payroll.clock_in("EMP-1", at=_iso(today - timedelta(hours=1)))
    payroll.clock_out("EMP-1", at=_iso(today))
    payroll.run_payroll((today - timedelta(days=1)).date().isoformat(), today.date().isoformat(), "EMP-ADMIN")
    stmt = payroll.list_pay_statements(employee_id="EMP-1")[0]
    assert stmt["taxes"]["state"] > 0  # CA has state tax
    assert stmt["taxes"]["state_rate"] == payroll.STATE_TAX_RATES["CA"]


# --- payroll run: commission from funded deals ---

def _funded_deal(deal_id, salesperson, sale_price, vehicle_cost, funded_on):
    ledger.add_entity(Entity(id="CUST-D", entity_type=CUSTOMER, attributes={}))
    vid = f"VEH-{deal_id}"
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes={"Cost": vehicle_cost}))
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes={
        "customer_id": "CUST-D", "vehicle_id": vid, "created_by": salesperson, "status": "funded",
        "funded_at": funded_on, "contract": {"sale_price": sale_price},
    }))


def test_commission_from_funded_deal():
    _emp()
    payroll.set_pay_plan("EMP-1", "commission", per_deal_commission=200, pct_front_gross=0.25, state="TX")
    today = datetime.now(timezone.utc)
    # front gross = 30000 - 26000 = 4000; commission = 200 + 0.25*4000 = 1200
    _funded_deal("DEAL-1", "EMP-1", 30000, 26000, _iso(today))
    result = payroll.run_payroll(today.date().isoformat(), today.date().isoformat(), "EMP-ADMIN")
    stmt = payroll.list_pay_statements(employee_id="EMP-1")[0]
    assert abs(stmt["earnings"]["commission"] - 1200) < 1
    assert len(stmt["commission_detail"]) == 1
    assert result["total_gross"] > 0


def test_deal_outside_period_not_paid():
    _emp()
    payroll.set_pay_plan("EMP-1", "commission", per_deal_commission=200, state="TX")
    today = datetime.now(timezone.utc)
    _funded_deal("DEAL-OLD", "EMP-1", 30000, 26000, _iso(today - timedelta(days=40)))
    result = payroll.run_payroll(today.date().isoformat(), today.date().isoformat(), "EMP-ADMIN")
    assert result["statement_count"] == 0  # no earnings in-period -> no paycheck


def test_zero_earnings_no_paycheck():
    _emp()
    payroll.set_pay_plan("EMP-1", "hourly", hourly_rate=20)  # no hours clocked
    today = datetime.now(timezone.utc)
    result = payroll.run_payroll(today.date().isoformat(), today.date().isoformat(), "EMP-ADMIN")
    assert result["statement_count"] == 0


# --- API gating ---

def test_api_run_requires_admin():
    from core.permissions import ADMIN, SALES
    _emp()
    payroll.set_pay_plan("EMP-1", "hourly", hourly_rate=20)
    today = datetime.now(timezone.utc).date().isoformat()
    assert "error" in payroll_api.run_payroll_api(SALES, "EMP-9", today, today)
    ok = payroll_api.run_payroll_api(ADMIN, "EMP-9", today, today)
    assert "run_id" in ok


def test_api_employee_sees_only_own_statements():
    from core.permissions import ADMIN, SALES
    _emp("EMP-1")
    _emp("EMP-2")
    payroll.set_pay_plan("EMP-1", "hourly", hourly_rate=20)
    now = datetime.now(timezone.utc)
    payroll.clock_in("EMP-1", at=_iso(now - timedelta(hours=5)))
    payroll.clock_out("EMP-1", at=_iso(now))
    payroll_api.run_payroll_api(ADMIN, "EMP-ADMIN", (now - timedelta(days=1)).date().isoformat(), now.date().isoformat())
    # EMP-2 (non-admin) sees none of EMP-1's statements
    mine = payroll_api.list_pay_statements_api(SALES, "EMP-2")
    assert mine["statements"] == []
