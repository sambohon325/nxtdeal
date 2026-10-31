"""
Tests for core/service_customers.py / core/service_customers_api.py -- Service's
Customer 360 (Vehicles Owned/Service History/Warranty/Recall/Declined Services),
Retention Metrics, Lost Customer Recovery, and Declined Services, plus the ACL
layer.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.relationships import Relationship
from core.entity_types import CUSTOMER, VEHICLE, SERVICE_RECORD, RECALL
from core.relationship_types import OWNS, AUTHORIZED
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core.service_customers import (
    get_customer_360,
    get_retention_metrics,
    get_lost_customer_recovery,
    get_declined_services,
    LOST_CUSTOMER_DAYS_THRESHOLD,
)
from core.service_customers_api import (
    get_customer_360_api,
    get_retention_metrics_api,
    get_lost_customer_recovery_api,
    get_declined_services_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


def _customer(customer_id="CUST-1", raw_key="C1001", first="Jordan", last="Ramirez"):
    entity = Entity(
        id=customer_id,
        entity_type=CUSTOMER,
        attributes={
            "FirstName": first, "LastName": last,
            "Email": f"{first.lower()}@example.com", "Phone": "555-0100",
            "CustomerID": raw_key,
        },
    )
    ledger.add_entity(entity)
    return entity


def _vehicle(vehicle_id="VEH-1", vin="VIN0001", condition="Used", year=2020, make="Ford", model="F-150"):
    entity = Entity(
        id=vehicle_id,
        entity_type=VEHICLE,
        attributes={"VIN": vin, "Year": year, "Make": make, "Model": model, "Condition": condition},
    )
    ledger.add_entity(entity)
    return entity


_rec_counter = [0]


def _service_record(customer_raw_key=None, vin=None, service_date=None, description="Oil change",
                     cost=100.0, pay_type="Customer Pay", estimate=None, status=None, ro_stage=None):
    _rec_counter[0] += 1
    attrs = {
        "CustomerID": customer_raw_key,
        "VIN": vin,
        "ServiceDate": service_date,
        "Description": description,
        "Cost": cost,
        "PayType": pay_type,
    }
    if estimate is not None:
        attrs["estimate"] = estimate
    if status is not None:
        attrs["Status"] = status
    if ro_stage is not None:
        attrs["ro_stage"] = ro_stage
    entity = Entity(id=f"SRV-TEST-{_rec_counter[0]:05d}", entity_type=SERVICE_RECORD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _owns(customer_id, vehicle_id):
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=vehicle_id, relationship_type=OWNS))


def _authorized(customer_id, record_id):
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=record_id, relationship_type=AUTHORIZED))


def _recall(make, model, open_=True):
    entity = Entity(
        id=f"RECALL-{make}-{model}",
        entity_type=RECALL,
        attributes={"make": make, "model": model, "open": open_, "recall_number": "R-1", "description": "Airbag", "campaign_type": "safety"},
    )
    ledger.add_entity(entity)
    return entity


# ---------------------------------------------------------------------------
# get_customer_360()
# ---------------------------------------------------------------------------

class TestGetCustomer360:

    def test_unknown_customer_returns_error(self):
        result = get_customer_360("CUST-NOPE")
        assert result == {"error": "Customer 'CUST-NOPE' not found"}

    def test_non_customer_entity_returns_error(self):
        _vehicle("VEH-1")
        result = get_customer_360("VEH-1")
        assert result == {"error": "Customer 'VEH-1' not found"}

    def test_customer_basic_fields(self):
        _customer("CUST-1", first="Jordan", last="Ramirez")
        result = get_customer_360("CUST-1")
        assert result["customer"] == {
            "id": "CUST-1", "name": "Jordan Ramirez",
            "email": "jordan@example.com", "phone": "555-0100",
        }

    def test_vehicles_owned_deduped_by_vehicle_id(self):
        _customer("CUST-1", raw_key="C1001")
        _vehicle("VEH-1", vin="VIN0001")
        _owns("CUST-1", "VEH-1")
        _owns("CUST-1", "VEH-1")  # real, pre-existing data-quality duplicate

        result = get_customer_360("CUST-1")

        assert result["vehicles_owned"]["count"] == 1
        assert len(result["vehicles_owned"]["vehicles"]) == 1

    def test_vehicles_owned_only_counts_real_vehicle_targets(self):
        _customer("CUST-1", raw_key="C1001")
        _vehicle("VEH-1", vin="VIN0001")
        rec = _service_record(customer_raw_key="C1001", vin="VIN0001", service_date="2026-01-01")
        _owns("CUST-1", "VEH-1")
        _owns("CUST-1", rec.id)  # OWNS pointed at a non-Vehicle entity, should be excluded

        result = get_customer_360("CUST-1")

        assert result["vehicles_owned"]["count"] == 1

    def test_vehicles_owned_carries_warranty_and_recall_status(self):
        _customer("CUST-1", raw_key="C1001")
        _vehicle("VEH-1", vin="VIN0001", condition="New", make="Ford", model="F-150")
        _owns("CUST-1", "VEH-1")
        _recall("Ford", "F-150", open_=True)

        result = get_customer_360("CUST-1")

        v = result["vehicles_owned"]["vehicles"][0]
        assert v["warranty_status"]["status"] == "likely_covered"
        assert v["recall_status"]["count"] == 1

    def test_service_history_sorted_descending_by_date(self):
        _customer("CUST-1", raw_key="C1001")
        r1 = _service_record(customer_raw_key="C1001", service_date="2025-01-01", description="Old")
        r2 = _service_record(customer_raw_key="C1001", service_date="2026-01-01", description="New")
        _authorized("CUST-1", r1.id)
        _authorized("CUST-1", r2.id)

        result = get_customer_360("CUST-1")

        dates = [r["service_date"] for r in result["service_history"]["records"]]
        assert dates == ["2026-01-01", "2025-01-01"]
        assert result["service_history"]["count"] == 2

    def test_service_history_includes_ro_stage(self):
        _customer("CUST-1", raw_key="C1001")
        r = _service_record(customer_raw_key="C1001", service_date="2026-01-01", ro_stage="Repair")
        _authorized("CUST-1", r.id)

        result = get_customer_360("CUST-1")

        assert result["service_history"]["records"][0]["ro_stage"] == "Repair"

    def test_declined_services_only_includes_declined_estimates(self):
        _customer("CUST-1", raw_key="C1001")
        approved = _service_record(customer_raw_key="C1001", service_date="2026-01-01", estimate={"approved": True, "amount": 200})
        declined = _service_record(customer_raw_key="C1001", service_date="2026-01-02", estimate={"approved": False, "amount": 500, "decline_reason": "Too expensive", "approved_at": "2026-01-02T10:00:00+00:00"})
        no_estimate = _service_record(customer_raw_key="C1001", service_date="2026-01-03")
        for r in (approved, declined, no_estimate):
            _authorized("CUST-1", r.id)

        result = get_customer_360("CUST-1")

        assert result["declined_services"]["count"] == 1
        rec = result["declined_services"]["records"][0]
        assert rec["ro_id"] == declined.id
        assert rec["amount"] == 500
        assert rec["decline_reason"] == "Too expensive"
        assert rec["declined_at"] == "2026-01-02T10:00:00+00:00"

    def test_customer_360_composes_real_retention_metrics(self):
        _customer("CUST-1", raw_key="C1001")
        r = _service_record(customer_raw_key="C1001", service_date="2026-01-01", cost=150.0)
        _authorized("CUST-1", r.id)

        result = get_customer_360("CUST-1")

        assert result["retention"]["visit_count"] == 1
        assert result["retention"]["average_spend"] == 150.0


# ---------------------------------------------------------------------------
# get_retention_metrics()
# ---------------------------------------------------------------------------

class TestGetRetentionMetrics:

    def test_no_records_returns_all_none(self):
        _customer("CUST-1", raw_key="C1001")
        result = get_retention_metrics("CUST-1")
        assert result == {"last_visit": None, "first_visit": None, "visit_count": 0, "average_spend": None, "visits_per_year": None}

    def test_records_with_no_service_date_are_treated_as_no_data(self):
        _customer("CUST-1", raw_key="C1001")
        r = _service_record(customer_raw_key="C1001", service_date=None)
        _authorized("CUST-1", r.id)
        result = get_retention_metrics("CUST-1")
        assert result["visit_count"] == 0

    def test_average_spend_computed_correctly(self):
        _customer("CUST-1", raw_key="C1001")
        r1 = _service_record(customer_raw_key="C1001", service_date="2026-01-01", cost=100.0)
        r2 = _service_record(customer_raw_key="C1001", service_date="2026-02-01", cost=200.0)
        _authorized("CUST-1", r1.id)
        _authorized("CUST-1", r2.id)

        result = get_retention_metrics("CUST-1")

        assert result["visit_count"] == 2
        assert result["average_spend"] == 150.0
        assert result["last_visit"] == "2026-02-01"
        assert result["first_visit"] == "2026-01-01"

    def test_single_visit_span_clamped_to_minimum_and_visits_per_year_computed(self):
        _customer("CUST-1", raw_key="C1001")
        r = _service_record(customer_raw_key="C1001", service_date="2026-01-01", cost=100.0)
        _authorized("CUST-1", r.id)

        result = get_retention_metrics("CUST-1")

        # span clamped to 1/365 year -> 1 visit / (1/365) = 365.0 visits/year
        assert result["visits_per_year"] == 365.0

    def test_malformed_date_yields_none_visits_per_year_but_keeps_other_fields(self):
        _customer("CUST-1", raw_key="C1001")
        r = _service_record(customer_raw_key="C1001", service_date="not-a-date", cost=50.0)
        _authorized("CUST-1", r.id)

        result = get_retention_metrics("CUST-1")

        assert result["visits_per_year"] is None
        assert result["visit_count"] == 1
        assert result["average_spend"] == 50.0

    def test_records_can_be_passed_in_directly(self):
        _customer("CUST-1", raw_key="C1001")
        r = _service_record(customer_raw_key="C1001", service_date="2026-01-01", cost=100.0)
        # Deliberately not linked via AUTHORIZED -- passing records= should
        # skip the graph lookup entirely.
        result = get_retention_metrics("CUST-1", records=[r])
        assert result["visit_count"] == 1


# ---------------------------------------------------------------------------
# get_lost_customer_recovery()
# ---------------------------------------------------------------------------

class TestGetLostCustomerRecovery:

    def test_customer_with_no_service_records_is_excluded(self):
        _customer("CUST-1", raw_key="C1001")
        result = get_lost_customer_recovery()
        assert result["count"] == 0

    def test_customer_with_records_but_no_service_dates_is_excluded(self):
        _customer("CUST-1", raw_key="C1001")
        r = _service_record(customer_raw_key="C1001", service_date=None)
        _authorized("CUST-1", r.id)
        result = get_lost_customer_recovery()
        assert result["count"] == 0

    def test_recent_visit_is_not_flagged_as_lost(self):
        from datetime import date, timedelta
        _customer("CUST-1", raw_key="C1001")
        recent = (date.today() - timedelta(days=10)).isoformat()
        r = _service_record(customer_raw_key="C1001", service_date=recent)
        _authorized("CUST-1", r.id)

        result = get_lost_customer_recovery()

        assert result["count"] == 0

    def test_old_visit_is_flagged_as_lost(self):
        from datetime import date, timedelta
        _customer("CUST-1", raw_key="C1001", first="Old", last="Customer")
        old = (date.today() - timedelta(days=LOST_CUSTOMER_DAYS_THRESHOLD + 5)).isoformat()
        r = _service_record(customer_raw_key="C1001", service_date=old)
        _authorized("CUST-1", r.id)

        result = get_lost_customer_recovery()

        assert result["count"] == 1
        entry = result["customers"][0]
        assert entry["customer_id"] == "CUST-1"
        assert entry["name"] == "Old Customer"
        assert entry["days_since_last_visit"] >= LOST_CUSTOMER_DAYS_THRESHOLD

    def test_sorted_by_days_since_last_visit_descending(self):
        from datetime import date, timedelta
        _customer("CUST-A", raw_key="CA")
        _customer("CUST-B", raw_key="CB")
        older = (date.today() - timedelta(days=500)).isoformat()
        newer = (date.today() - timedelta(days=400)).isoformat()
        ra = _service_record(customer_raw_key="CA", service_date=older)
        rb = _service_record(customer_raw_key="CB", service_date=newer)
        _authorized("CUST-A", ra.id)
        _authorized("CUST-B", rb.id)

        result = get_lost_customer_recovery()

        ids = [c["customer_id"] for c in result["customers"]]
        assert ids == ["CUST-A", "CUST-B"]

    def test_malformed_date_skipped_gracefully(self):
        _customer("CUST-1", raw_key="C1001")
        r = _service_record(customer_raw_key="C1001", service_date="not-a-date")
        _authorized("CUST-1", r.id)

        result = get_lost_customer_recovery()

        assert result["count"] == 0

    def test_not_yet_tracked_gaps_documented(self):
        result = get_lost_customer_recovery()
        assert "warranty_expired" in result["not_yet_tracked"]
        assert "missed_maintenance" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# get_declined_services()
# ---------------------------------------------------------------------------

class TestGetDeclinedServices:

    def test_records_with_no_estimate_are_excluded(self):
        _service_record(customer_raw_key="C1001", service_date="2026-01-01")
        result = get_declined_services()
        assert result["count"] == 0

    def test_records_with_approved_true_are_excluded(self):
        _service_record(customer_raw_key="C1001", service_date="2026-01-01", estimate={"approved": True, "amount": 100})
        result = get_declined_services()
        assert result["count"] == 0

    def test_records_with_approved_none_are_excluded(self):
        _service_record(customer_raw_key="C1001", service_date="2026-01-01", estimate={"approved": None, "amount": 100})
        result = get_declined_services()
        assert result["count"] == 0

    def test_declined_record_included_with_resolved_customer_and_vehicle(self):
        _customer("CUST-1", raw_key="C1001", first="Jordan", last="Ramirez")
        _vehicle("VEH-1", vin="VIN0001", year=2021, make="Toyota", model="Camry")
        _service_record(
            customer_raw_key="C1001", vin="VIN0001", service_date="2026-01-01",
            description="Brake pads",
            estimate={"approved": False, "amount": 450.0, "decline_reason": "Cost", "approved_at": "2026-01-01T09:00:00+00:00"},
        )

        result = get_declined_services()

        assert result["count"] == 1
        rec = result["records"][0]
        assert rec["customer_id"] == "CUST-1"
        assert rec["customer_name"] == "Jordan Ramirez"
        assert rec["vehicle"] == "2021 Toyota Camry"
        assert rec["description"] == "Brake pads"
        assert rec["amount"] == 450.0
        assert rec["decline_reason"] == "Cost"
        assert rec["days_since_declined"] is not None

    def test_declined_record_with_unresolvable_customer_and_vehicle_degrades_gracefully(self):
        _service_record(
            customer_raw_key="C-UNKNOWN", vin="VIN-UNKNOWN", service_date="2026-01-01",
            estimate={"approved": False, "amount": 100.0},
        )

        result = get_declined_services()

        rec = result["records"][0]
        assert rec["customer_id"] is None
        assert rec["customer_name"] is None
        assert rec["vehicle"] is None

    def test_malformed_approved_at_yields_none_days_since_declined(self):
        _service_record(
            customer_raw_key="C1001", service_date="2026-01-01",
            estimate={"approved": False, "amount": 100.0, "approved_at": "not-a-date"},
        )

        result = get_declined_services()

        assert result["records"][0]["days_since_declined"] is None

    def test_sorted_by_amount_descending(self):
        _service_record(customer_raw_key="C1001", service_date="2026-01-01", estimate={"approved": False, "amount": 100.0})
        _service_record(customer_raw_key="C1001", service_date="2026-01-01", estimate={"approved": False, "amount": 900.0})
        _service_record(customer_raw_key="C1001", service_date="2026-01-01", estimate={"approved": False, "amount": 500.0})

        result = get_declined_services()

        amounts = [r["amount"] for r in result["records"]]
        assert amounts == [900.0, 500.0, 100.0]

    def test_total_value_sums_all_declined_amounts(self):
        _service_record(customer_raw_key="C1001", service_date="2026-01-01", estimate={"approved": False, "amount": 100.0})
        _service_record(customer_raw_key="C1001", service_date="2026-01-01", estimate={"approved": False, "amount": 250.5})

        result = get_declined_services()

        assert result["total_value"] == 350.5

    def test_historical_records_predating_estimate_flow_are_excluded(self):
        # The 434 historical ServiceRecords predate the estimate/approval
        # flow entirely and carry no "estimate" field at all -- confirm they
        # are correctly excluded rather than fabricating a decline.
        _service_record(customer_raw_key="C1001", service_date="2020-01-01", description="Historical row")
        result = get_declined_services()
        assert result["count"] == 0


# ---------------------------------------------------------------------------
# ACL layer
# ---------------------------------------------------------------------------

class TestAclLayer:

    def test_marketing_denied_customer_360(self):
        _customer("CUST-1", raw_key="C1001")
        result = get_customer_360_api(MARKETING, "CUST-1")
        assert result == {"error": "Forbidden: insufficient role for this view."}

    def test_marketing_denied_retention_metrics(self):
        _customer("CUST-1", raw_key="C1001")
        result = get_retention_metrics_api(MARKETING, "CUST-1")
        assert result == {"error": "Forbidden: insufficient role for this view."}

    def test_marketing_denied_lost_customer_recovery(self):
        result = get_lost_customer_recovery_api(MARKETING)
        assert result == {"error": "Forbidden: insufficient role for this view."}

    def test_marketing_denied_declined_services(self):
        result = get_declined_services_api(MARKETING)
        assert result == {"error": "Forbidden: insufficient role for this view."}

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, SERVICE, FINANCE])
    def test_allowed_roles_match_direct_call(self, role):
        _customer("CUST-1", raw_key="C1001")
        direct = get_customer_360("CUST-1")
        via_api = get_customer_360_api(role, "CUST-1")
        assert via_api == direct

        direct_retention = get_retention_metrics("CUST-1")
        via_api_retention = get_retention_metrics_api(role, "CUST-1")
        assert via_api_retention == direct_retention

        direct_lost = get_lost_customer_recovery()
        via_api_lost = get_lost_customer_recovery_api(role)
        assert via_api_lost == direct_lost

        direct_declined = get_declined_services()
        via_api_declined = get_declined_services_api(role)
        assert via_api_declined == direct_declined
