"""
Test coverage for core/operations_scheduling.py -- Operations' Scheduling item
(Recon Scheduling, Delivery Scheduling with automatic risk detection, Transport
Scheduling).

Reuses already-independently-tested dependencies (core/workflow_tab_data.py's
operations_recon_queue()/inventory_auction_acquisition(), core/operations_tasks.py's
create_task(), core/appointments.py's create_appointment()/list_appointments()) --
these tests focus on this module's own real logic: the delivery-risk
categorization (on_track / no_delivery_scheduled / overdue) and the two real
mutation actions (schedule_recon, schedule_delivery, update_transport_status).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity

import core.operations_scheduling as sched
from core.appointments import create_appointment


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


def _vehicle(vid, **attrs):
    ledger.add_entity(Entity(id=vid, entity_type="Vehicle", attributes=attrs))


def _customer(cid, **attrs):
    ledger.add_entity(Entity(id=cid, entity_type="Customer", attributes=attrs))


def _deal(did, **attrs):
    ledger.add_entity(Entity(id=did, entity_type="Deal", attributes=attrs))


def _auction_transaction(aid, **attrs):
    ledger.add_entity(Entity(id=aid, entity_type="AuctionTransaction", attributes=attrs))


FUTURE = "2099-01-01T00:00:00+00:00"
PAST = "2020-01-01T00:00:00+00:00"


class TestEmptyLedgerSanity:

    def test_get_recon_schedule_empty(self):
        result = sched.get_recon_schedule("ADMIN")
        assert result["used_unsold_count"] == 0
        assert result["vehicles"] == []

    def test_get_delivery_risk_board_empty(self):
        result = sched.get_delivery_risk_board("ADMIN")
        assert result["total_pending_delivery"] == 0
        assert result["on_track"]["count"] == 0
        assert result["no_delivery_scheduled"]["count"] == 0
        assert result["overdue"]["count"] == 0

    def test_get_transport_schedule_empty(self):
        result = sched.get_transport_schedule("ADMIN")
        assert set(result.keys()) == {"count", "by_transport_status", "transactions"}


class TestScheduleRecon:

    def test_schedule_recon_missing_vehicle_returns_error(self):
        result = sched.schedule_recon("VEH-99999", "2026-08-01", "EMP-1")
        assert "error" in result

    def test_schedule_recon_missing_target_date_returns_error(self):
        _vehicle("VEH-00001", Year="2022", Make="Ford", Model="F-150")
        result = sched.schedule_recon("VEH-00001", "", "EMP-1")
        assert "error" in result

    def test_schedule_recon_success_creates_real_operations_task(self):
        _vehicle("VEH-00001", Year="2022", Make="Ford", Model="F-150")
        result = sched.schedule_recon("VEH-00001", "2026-08-01", "EMP-1", notes="needs bumper")
        assert result.attributes["task_type"] == "recon_followup"
        assert result.attributes["target_date"] == "2026-08-01"
        assert result.attributes["linked_entity_id"] == "VEH-00001"
        assert result.attributes["created_by"] == "EMP-1"
        assert "2022 Ford F-150" in result.attributes["detail"]
        assert "needs bumper" in result.attributes["detail"]


class TestDeliveryRiskBoard:

    def test_only_contract_and_funded_deals_are_counted(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="contract", customer_id="CUST-00001")
        _deal("DEAL-00002", status="desking", customer_id="CUST-00001")  # excluded
        _deal("DEAL-00003", status="funded", customer_id="CUST-00001")
        result = sched.get_delivery_risk_board("ADMIN")
        assert result["total_pending_delivery"] == 2

    def test_no_delivery_scheduled_when_no_open_appointment_exists(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="contract", customer_id="CUST-00001", vehicle_id="VEH-00001")
        result = sched.get_delivery_risk_board("ADMIN")
        assert result["no_delivery_scheduled"]["count"] == 1
        assert result["no_delivery_scheduled"]["deals"][0]["deal_id"] == "DEAL-00001"

    def test_on_track_when_a_future_delivery_appointment_exists(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="contract", customer_id="CUST-00001", vehicle_id="VEH-00001")
        create_appointment(
            department="Sales", appointment_type="delivery", scheduled_start=FUTURE,
            created_by="EMP-1", customer_id="CUST-00001", vehicle_id="VEH-00001",
        )
        result = sched.get_delivery_risk_board("ADMIN")
        assert result["on_track"]["count"] == 1
        assert result["no_delivery_scheduled"]["count"] == 0

    def test_overdue_when_a_past_delivery_appointment_exists_and_not_completed(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="funded", customer_id="CUST-00001", vehicle_id="VEH-00001")
        create_appointment(
            department="Sales", appointment_type="delivery", scheduled_start=PAST,
            created_by="EMP-1", customer_id="CUST-00001", vehicle_id="VEH-00001",
        )
        result = sched.get_delivery_risk_board("ADMIN")
        assert result["overdue"]["count"] == 1
        assert result["on_track"]["count"] == 0
        assert result["no_delivery_scheduled"]["count"] == 0

    def test_a_customer_only_match_counts_when_deal_has_no_vehicle_recorded(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="contract", customer_id="CUST-00001")  # no vehicle_id on the deal
        create_appointment(
            department="Sales", appointment_type="delivery", scheduled_start=FUTURE,
            created_by="EMP-1", customer_id="CUST-00001",
        )
        result = sched.get_delivery_risk_board("ADMIN")
        assert result["on_track"]["count"] == 1

    def test_deal_with_no_customer_id_is_treated_as_no_delivery_scheduled(self):
        _deal("DEAL-00001", status="contract")
        result = sched.get_delivery_risk_board("ADMIN")
        assert result["no_delivery_scheduled"]["count"] == 1


class TestScheduleDelivery:

    def test_schedule_delivery_missing_deal_returns_error(self):
        result = sched.schedule_delivery("DEAL-99999", FUTURE, "EMP-1")
        assert "error" in result

    def test_schedule_delivery_wrong_status_returns_error(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="desking", customer_id="CUST-00001")
        result = sched.schedule_delivery("DEAL-00001", FUTURE, "EMP-1")
        assert "error" in result
        assert "desking" in result["error"]

    def test_schedule_delivery_missing_scheduled_start_returns_error(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="contract", customer_id="CUST-00001")
        result = sched.schedule_delivery("DEAL-00001", "", "EMP-1")
        assert "error" in result

    def test_schedule_delivery_success_creates_real_appointment(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="contract", customer_id="CUST-00001", vehicle_id="VEH-00001")
        result = sched.schedule_delivery("DEAL-00001", FUTURE, "EMP-1", assigned_to="EMP-2")
        assert result.attributes["department"] == "Sales"
        assert result.attributes["appointment_type"] == "delivery"
        assert result.attributes["customer_id"] == "CUST-00001"
        assert result.attributes["vehicle_id"] == "VEH-00001"
        assert result.attributes["assigned_to"] == "EMP-2"
        assert result.attributes["scheduled_start"] == FUTURE

    def test_schedule_delivery_resolves_the_real_risk(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="contract", customer_id="CUST-00001", vehicle_id="VEH-00001")
        before = sched.get_delivery_risk_board("ADMIN")
        assert before["no_delivery_scheduled"]["count"] == 1
        sched.schedule_delivery("DEAL-00001", FUTURE, "EMP-1")
        after = sched.get_delivery_risk_board("ADMIN")
        assert after["no_delivery_scheduled"]["count"] == 0
        assert after["on_track"]["count"] == 1

    def test_schedule_delivery_funded_status_also_allowed(self):
        _customer("CUST-00001", FirstName="Joe", LastName="King")
        _deal("DEAL-00001", status="funded", customer_id="CUST-00001")
        result = sched.schedule_delivery("DEAL-00001", FUTURE, "EMP-1")
        assert result.attributes["status"] == "scheduled"


class TestUpdateTransportStatus:

    def test_bad_status_returns_error(self):
        result = sched.update_transport_status("AUCT-00001", "not_a_status", "EMP-1")
        assert "error" in result

    def test_missing_transaction_returns_error(self):
        result = sched.update_transport_status("AUCT-00001", "in_transit", "EMP-1")
        assert "error" in result

    def test_wrong_entity_type_returns_error(self):
        _vehicle("VEH-00001")
        result = sched.update_transport_status("VEH-00001", "in_transit", "EMP-1")
        assert "error" in result

    def test_success_updates_attributes_and_returns_old_and_new_status(self):
        _auction_transaction("AUCT-00001", vehicle_id="VEH-00001", transport_status="at_auction_yard")
        result = sched.update_transport_status("AUCT-00001", "in_transit", "EMP-1")
        assert result == {
            "id": "AUCT-00001",
            "vehicle_id": "VEH-00001",
            "old_status": "at_auction_yard",
            "new_status": "in_transit",
        }

    def test_success_actually_persists_on_the_entity(self):
        _auction_transaction("AUCT-00001", vehicle_id="VEH-00001", transport_status="at_auction_yard")
        sched.update_transport_status("AUCT-00001", "delivered", "EMP-1")
        entity = ledger.get_entity("AUCT-00001")
        assert entity.attributes["transport_status"] == "delivered"
        assert entity.attributes["transport_status_updated_by"] == "EMP-1"

    def test_every_real_transport_status_is_accepted(self):
        _auction_transaction("AUCT-00001", transport_status="at_auction_yard")
        for status in ("at_auction_yard", "in_transit", "delivered"):
            result = sched.update_transport_status("AUCT-00001", status, "EMP-1")
            assert result["new_status"] == status
