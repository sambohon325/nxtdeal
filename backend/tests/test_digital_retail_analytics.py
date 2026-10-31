"""
Tests for the Digital Retail KPI dashboard (core/digital_retail_analytics.py, DR-8,
2026-07-24). Run from backend/ with `pytest`.

Covers: digital deals are those created by the customer (CUSTOMER_SENTINEL), not staff;
digital gross is computed from real Vehicle Cost/Price on funded digital deals; the journey
funnel counts each stage and its drop-off; AI performance rolls up; and the composed dashboard
carries every block.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, DEAL, DELIVERY

from core.digital_retail import CUSTOMER_SENTINEL
from core import digital_retail_analytics as dra


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _vehicle(vid, price, cost):
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes={"Make": "Ford", "Price": price, "Cost": cost}))


def _deal(did, vid, status, created_by, sale_price=None):
    attrs = {"customer_id": "CUST-1", "vehicle_id": vid, "status": status, "created_by": created_by,
             "scenarios": [], "selected_scenario_id": None}
    if sale_price is not None:
        attrs["scenarios"] = [{"id": "scn-1", "sale_price": sale_price}]
        attrs["selected_scenario_id"] = "scn-1"
    ledger.add_entity(Entity(id=did, entity_type=DEAL, attributes=attrs))


def test_only_customer_created_deals_count_as_digital():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    _vehicle("VEH-1", 40000, 34000)
    _vehicle("VEH-2", 30000, 26000)
    _deal("DEAL-1", "VEH-1", "funded", CUSTOMER_SENTINEL, sale_price=39000)
    _deal("DEAL-2", "VEH-2", "funded", "EMP-7")  # staff deal, not digital
    k = dra.digital_deal_kpis()
    assert k["digital_deals"] == 1
    assert k["digital_closings"] == 1
    assert k["digital_gross"] == 5000  # 39000 sale - 34000 cost


def test_digital_gross_only_counts_funded():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    _vehicle("VEH-1", 40000, 34000)
    _deal("DEAL-1", "VEH-1", "financing", CUSTOMER_SENTINEL, sale_price=39000)  # not funded
    k = dra.digital_deal_kpis()
    assert k["digital_deals"] == 1 and k["digital_closings"] == 0
    assert k["digital_gross"] == 0


def test_journey_funnel_counts_and_dropoff():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    _vehicle("VEH-1", 40000, 34000)
    _vehicle("VEH-2", 30000, 26000)
    _deal("DEAL-1", "VEH-1", "funded", CUSTOMER_SENTINEL)      # made it all the way
    _deal("DEAL-2", "VEH-2", "desking", CUSTOMER_SENTINEL)     # stalled early
    funnel = dra.journey_funnel()
    stages = {s["stage"]: s["count"] for s in funnel["stages"]}
    assert stages["deal"] == 2
    assert stages["finance"] == 1        # only the funded one reached financing+
    assert stages["contracting"] == 1
    # drop-off from deal(2) -> finance(1) is 1
    fin = next(s for s in funnel["stages"] if s["stage"] == "finance")
    assert fin["dropped_from_prev"] == 1


def test_digital_deliveries_tie_to_digital_deals():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    _vehicle("VEH-1", 40000, 34000)
    _deal("DEAL-1", "VEH-1", "funded", CUSTOMER_SENTINEL)
    ledger.add_entity(Entity(id="DLVR-1", entity_type=DELIVERY,
                             attributes={"deal_id": "DEAL-1", "status": "completed", "mode": "home_delivery"}))
    ledger.add_entity(Entity(id="DLVR-2", entity_type=DELIVERY,
                             attributes={"deal_id": "DEAL-OTHER", "status": "scheduled", "mode": "store_pickup"}))
    dk = dra.digital_delivery_kpis()
    assert dk["digital_deliveries"] == 1 and dk["completed"] == 1


def test_ai_performance_and_dashboard_compose():
    ledger.add_entity(Entity(id="CUST-1", entity_type=CUSTOMER, attributes={"Name": "P"}))
    _vehicle("VEH-1", 40000, 34000)
    _deal("DEAL-1", "VEH-1", "funded", CUSTOMER_SENTINEL, sale_price=39000)
    perf = dra.ai_performance()
    assert perf["deals_assisted"] == 1
    assert perf["deals_closed"] == 1
    assert perf["revenue_influenced"] == 5000

    dash = dra.get_digital_retail_dashboard()
    for block in ("kpis", "ai_performance", "funnel", "verifications", "negotiations",
                  "deliveries", "try_before_you_buy"):
        assert block in dash
    assert dash["kpis"]["digital_closings"] == 1
