"""
Phase 7 (2026-07-25): the equity/maturity-at-service signal for service-to-sales conversion.
A customer in the service lane who carries positive equity or a maturing lease is surfaced
as an upgrade opportunity, without disturbing the existing declined/high-cost/manual queue.
Run from backend/ with `pytest`.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.relationship_types import AUTHORIZED, HAS_SERVICE_RECORD
from core.entity_types import CUSTOMER, VEHICLE, SERVICE_RECORD
from core import service_sales_handoff as ssh


@pytest.fixture(autouse=True)
def fresh():
    ledger.reset()
    yield
    ledger.reset()


def _service_customer(cid, ro_id, cost=100, **cust_attrs):
    vin = f"VIN{cid}"
    a = {"FirstName": "Jo", "LastName": "Q", "CustomerID": cid}
    a.update(cust_attrs)
    ledger.add_entity(Entity(id=cid, entity_type=CUSTOMER, attributes=a))
    vid = f"VEH-{cid}"
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes={"Year": 2022, "Make": "X", "Model": "Y", "VIN": vin}))
    ledger.add_entity(Entity(id=ro_id, entity_type=SERVICE_RECORD, attributes={"Cost": cost, "Description": "Oil", "CustomerID": cid, "VIN": vin}))
    ledger.add_relationship(Relationship(source_id=cid, target_id=ro_id, relationship_type=AUTHORIZED))
    ledger.add_relationship(Relationship(source_id=vid, target_id=ro_id, relationship_type=HAS_SERVICE_RECORD))


def test_positive_equity_customer_in_service_is_flagged():
    _service_customer("CUST-1", "RO-1", cost=100, estimated_value=25000, estimated_payoff=15000)
    cands = ssh.get_equity_service_candidates()
    assert len(cands) == 1
    assert cands[0]["opportunity_type"] == "equity_at_service"
    assert cands[0]["customer_id"] == "CUST-1"
    assert "equity" in cands[0]["reason"].lower()


def test_maturing_lease_customer_in_service_is_flagged():
    soon = (date.today() + timedelta(days=30)).isoformat()
    _service_customer("CUST-1", "RO-1", cost=100, lease_maturity_date=soon)
    cands = ssh.get_equity_service_candidates()
    assert len(cands) == 1
    assert "matures" in cands[0]["reason"]


def test_no_equity_no_maturity_not_flagged():
    _service_customer("CUST-1", "RO-1", cost=100)  # no equity attrs
    assert ssh.get_equity_service_candidates() == []


def test_one_candidate_per_customer_dedupes_visits():
    _service_customer("CUST-1", "RO-1", cost=100, estimated_value=25000, estimated_payoff=15000)
    # a second visit for the same customer
    ledger.add_entity(Entity(id="RO-2", entity_type=SERVICE_RECORD, attributes={"Cost": 100, "Description": "Tires", "CustomerID": "CUST-1", "VIN": "VINCUST-1"}))
    ledger.add_relationship(Relationship(source_id="CUST-1", target_id="RO-2", relationship_type=AUTHORIZED))
    assert len(ssh.get_equity_service_candidates()) == 1


def test_conversion_queue_combines_without_touching_base_queue():
    # High-cost repair (base queue) + a separate equity customer.
    _service_customer("CUST-HC", "RO-HC", cost=900)  # high cost -> base queue
    _service_customer("CUST-EQ", "RO-EQ", cost=100, estimated_value=30000, estimated_payoff=10000)  # equity

    base = ssh.get_opportunity_queue()
    assert base["count"] == 1  # only the high-cost one — base queue is unchanged

    conv = ssh.get_conversion_opportunities()
    assert conv["count"] == 2
    assert conv["equity_at_service_count"] == 1
    assert conv["high_cost_repair_count"] == 1


def test_promoted_equity_opportunity_drops_out():
    _service_customer("CUST-1", "RO-1", cost=100, estimated_value=25000, estimated_payoff=15000)
    assert len(ssh.get_equity_service_candidates()) == 1
    ssh.promote_to_sales("RO-1", "EMP-1", opportunity_type="equity_at_service")
    assert ssh.get_equity_service_candidates() == []  # no longer actionable
