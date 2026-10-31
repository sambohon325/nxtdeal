"""
Tests for core/data_health.py / core/data_health_api.py -- Readiness' expanded
Data Health item. Four real sections composed on top of the graph:

  1. Integration Monitoring -- re-surfaces core/data_connections.py's real
     Connection records, grouped by an honest department->Sam-category mapping.
  2. Data Completeness -- a real field-presence scan across Vehicle/Customer/
     ServiceRecord/FinanceContract for the fields each entity type needs.
  3. Data Accuracy -- real duplicate-customer/duplicate-vehicle detection
     (normalized email/phone/VIN), an honestly-unfabricated Pricing
     Discrepancies gap (always {"checked": False, ...}), and Inventory
     Mismatches (a verbatim reuse of core/workflow_tab_data.inventory_lot_audit()).
  4. Data Freshness -- real per-connection last-sync data, a real "records
     updated in the last 24h" scan across Deal/Vehicle/ServiceRecord (Customer/
     FinanceContract are deliberately excluded -- no update-timestamp field
     exists on either anywhere in this codebase), and Pending Changes (a real
     reuse of the same cross-department pending-approval queue functions
     core/administration_menu.py's own _approval_queue() already established).

core/data_connections.create_connection() itself never calls save_graph() (only
ingest_csv() does, at the very end of a real CSV import) -- so no persistence
patching is needed anywhere in this file; every Connection/Vehicle/Customer/
ServiceRecord/FinanceContract/Deal fixture here is a plain, unsaved, in-memory
ledger entity, exactly matching how every test in this file needs it to behave.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE, SERVICE_RECORD, FINANCE_CONTRACT, DEAL
from core.relationships import Relationship
from core.relationship_types import PURCHASED

from core.data_connections import create_connection

from core import data_health
from core import data_health_api

from core.permissions import ADMIN, OPERATIONS, SALES, FINANCE, MARKETING, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


# -----------------------------------------------------------------------
# Fixture builders -- match the real, plain-string CSV-import attribute
# shapes (imports/finance_import.py etc. always store row values as plain
# strings via csv.DictReader). Native record numeric fields are covered below.
# -----------------------------------------------------------------------


def _customer(cid, email="", phone="", first="", last=""):
    ledger.add_entity(Entity(
        id=cid, entity_type=CUSTOMER,
        attributes={"Email": email, "Phone": phone, "FirstName": first, "LastName": last},
    ))
    return cid


def _vehicle(vid, vin="", date_sold=None, description_updated_at=None,
             featured_updated_at=None, price_history=None):
    attrs = {"VIN": vin, "DateSold": date_sold}
    if description_updated_at is not None:
        attrs["description_updated_at"] = description_updated_at
    if featured_updated_at is not None:
        attrs["featured_updated_at"] = featured_updated_at
    if price_history is not None:
        attrs["price_history"] = price_history
    ledger.add_entity(Entity(id=vid, entity_type=VEHICLE, attributes=attrs))
    return vid


def _service_record(rid, vin="", technician="", description="", service_date="",
                     customer_id="", ro_stage_history=None):
    attrs = {
        "VIN": vin, "Technician": technician, "Description": description,
        "ServiceDate": service_date, "CustomerID": customer_id,
    }
    if ro_stage_history is not None:
        attrs["ro_stage_history"] = ro_stage_history
    ledger.add_entity(Entity(id=rid, entity_type=SERVICE_RECORD, attributes=attrs))
    return rid


def _finance_contract(fid, vin="", apr="", amount_financed="", lender_name="", term_months=""):
    ledger.add_entity(Entity(
        id=fid, entity_type=FINANCE_CONTRACT,
        attributes={
            "VIN": vin, "APR": apr, "AmountFinanced": amount_financed,
            "LenderName": lender_name, "TermMonths": term_months,
        },
    ))
    return fid


def _deal(did, updated_at=None):
    ledger.add_entity(Entity(id=did, entity_type=DEAL, attributes={"updated_at": updated_at}))
    return did


def _purchased(customer_id, vehicle_id):
    ledger.add_relationship(Relationship(
        source_id=customer_id, target_id=vehicle_id, relationship_type=PURCHASED,
    ))


def _connection(name="Vin Feed", connection_type="csv", department="sales", created_by="EMP-1"):
    endpoint_url = "https://example.com/feed" if connection_type == "api" else None
    result = create_connection(name, connection_type, department, created_by, endpoint_url=endpoint_url)
    return result["connection"]["id"]


# ===========================================================================
# 1. Integration Monitoring
# ===========================================================================

class TestIntegrationMonitoring:

    def test_no_connections_returns_an_empty_real_baseline(self):
        result = data_health.integration_monitoring(ADMIN)

        assert result["total_connections"] == 0
        assert result["by_sam_category"] == {}
        assert result["by_connection_type"] == {}
        assert result["accounting_connections_count"] == 0

    def test_a_denied_role_propagates_the_real_underlying_denial(self):
        result = data_health.integration_monitoring(SALES)

        assert "error" in result

    def test_groups_by_the_real_honest_department_to_sam_category_mapping(self):
        _connection(name="Inventory CSV", department="sales")
        _connection(name="Parts CSV", department="parts")
        _connection(name="Lender API", department="finance", connection_type="api")
        _connection(name="Lead Feed", department="marketing")
        _connection(name="Service DMS", department="service")

        result = data_health.integration_monitoring(ADMIN)

        assert result["total_connections"] == 5
        assert {c["name"] for c in result["by_sam_category"]["Inventory Feed"]} == {"Inventory CSV", "Parts CSV"}
        assert {c["name"] for c in result["by_sam_category"]["Lender Integrations"]} == {"Lender API"}
        assert {c["name"] for c in result["by_sam_category"]["Website APIs"]} == {"Lead Feed"}
        assert {c["name"] for c in result["by_sam_category"]["OEM Systems"]} == {"Service DMS"}

    def test_by_connection_type_counts_are_real(self):
        _connection(department="sales", connection_type="csv")
        _connection(department="service", connection_type="csv")
        _connection(department="finance", connection_type="api")

        result = data_health.integration_monitoring(ADMIN)

        assert result["by_connection_type"] == {"csv": 2, "api": 1}

    def test_a_grouped_connection_carries_its_real_status_and_sync_fields(self):
        cid = _connection(department="sales")

        result = data_health.integration_monitoring(ADMIN)

        row = result["by_sam_category"]["Inventory Feed"][0]
        assert row["id"] == cid
        assert row["status"] == "pending"
        assert row["last_synced_at"] is None
        assert row["error_message"] is None


class TestIntegrationMonitoringApi:

    def test_denied_role_gets_the_real_denial_message(self):
        result = data_health_api.get_integration_monitoring_api(SALES)

        assert result["error"].startswith("You don't have access to Data Health")

    def test_operations_is_allowed_through(self):
        result = data_health_api.get_integration_monitoring_api(OPERATIONS)

        assert "error" not in result
        assert result["total_connections"] == 0


# ===========================================================================
# 2. Data Completeness
# ===========================================================================

class TestDataCompleteness:

    def test_an_empty_ledger_reports_zero_totals_and_no_pct(self):
        result = data_health.data_completeness()

        assert result["missing_vin_data"]["vehicles"]["total_count"] == 0
        assert result["missing_vin_data"]["vehicles"]["missing_count"] == 0
        assert result["missing_vin_data"]["vehicles"]["missing_pct"] is None

    def test_real_missing_vin_detection_across_all_three_entity_types(self):
        _vehicle("VEH-1", vin="1FT7X2B69ABC12345")
        _vehicle("VEH-2", vin="")
        _service_record("SRV-1", vin="")
        _service_record("SRV-2", vin="1FT7X2B69ABC12345")
        _finance_contract("FIN-1", vin="")

        result = data_health.data_completeness()

        assert result["missing_vin_data"]["vehicles"]["missing_count"] == 1
        assert result["missing_vin_data"]["vehicles"]["sample_ids"] == ["VEH-2"]
        assert result["missing_vin_data"]["repair_orders"]["missing_count"] == 1
        assert result["missing_vin_data"]["repair_orders"]["sample_ids"] == ["SRV-1"]
        assert result["missing_vin_data"]["finance_contracts"]["missing_count"] == 1

    def test_real_missing_customer_data_across_all_four_fields(self):
        _customer("CUST-1", email="a@b.com", phone="5551234567", first="Jane", last="Doe")
        _customer("CUST-2", email="", phone="", first="", last="")

        result = data_health.data_completeness()

        missing = result["missing_customer_data"]
        assert missing["email"]["missing_count"] == 1
        assert missing["email"]["sample_ids"] == ["CUST-2"]
        assert missing["phone"]["missing_count"] == 1
        assert missing["first_name"]["missing_count"] == 1
        assert missing["last_name"]["missing_count"] == 1
        assert missing["email"]["missing_pct"] == 50.0

    def test_real_missing_ro_data_across_all_four_fields(self):
        _service_record("SRV-1", technician="Nate", description="Oil change", service_date="2026-01-01", customer_id="CUST-1")
        _service_record("SRV-2", technician="", description="", service_date="", customer_id="")

        result = data_health.data_completeness()

        missing = result["missing_ro_data"]
        assert missing["technician"]["missing_count"] == 1
        assert missing["description"]["missing_count"] == 1
        assert missing["service_date"]["missing_count"] == 1
        assert missing["customer_id"]["missing_count"] == 1

    def test_real_missing_contract_data_across_all_four_fields(self):
        _finance_contract("FIN-1", apr="6.9", amount_financed="25000", lender_name="Chrysler Capital", term_months="72")
        _finance_contract("FIN-2", apr="", amount_financed="", lender_name="", term_months="")

        result = data_health.data_completeness()

        missing = result["missing_contract_data"]
        assert missing["apr"]["missing_count"] == 1
        assert missing["amount_financed"]["missing_count"] == 1
        assert missing["lender_name"]["missing_count"] == 1
        assert missing["term_months"]["missing_count"] == 1

    @pytest.mark.parametrize("apr,amount,term", [(0, 0, 0), (6.9, 25000, 72)])
    def test_native_numeric_finance_fields_are_present(self, apr, amount, term):
        _finance_contract("FIN-NATIVE", apr=apr, amount_financed=amount,
                          term_months=term, lender_name="Synthetic lender")
        _finance_contract("FIN-MISSING", apr=None, amount_financed=" ", term_months="")
        result = data_health_api.get_data_completeness_api(ADMIN)
        for field in ("apr", "amount_financed", "term_months"):
            assert result["missing_contract_data"][field]["missing_count"] == 1
            assert result["missing_contract_data"][field]["sample_ids"] == ["FIN-MISSING"]

    def test_a_field_with_only_whitespace_counts_as_missing(self):
        _customer("CUST-1", email="   ", phone="5551234567", first="Jane", last="Doe")

        result = data_health.data_completeness()

        assert result["missing_customer_data"]["email"]["missing_count"] == 1


class TestDataCompletenessApi:

    def test_denied_role_gets_the_real_denial_message(self):
        result = data_health_api.get_data_completeness_api(MARKETING)

        assert result["error"].startswith("You don't have access to Data Health")

    def test_admin_is_allowed_through(self):
        result = data_health_api.get_data_completeness_api(ADMIN)

        assert "error" not in result
        assert "missing_vin_data" in result


# ===========================================================================
# 3. Data Accuracy
# ===========================================================================

class TestDuplicateCustomers:

    def test_no_customers_returns_no_groups(self):
        result = data_health.duplicate_customers()

        assert result["duplicate_groups_by_email"] == []
        assert result["duplicate_groups_by_phone"] == []
        assert result["total_customers_affected"] == 0

    def test_two_customers_sharing_a_real_normalized_email_form_a_group(self):
        _customer("CUST-1", email="Jane.Doe@Example.com", phone="5550001111", first="Jane", last="Doe")
        _customer("CUST-2", email="jane.doe@example.com", phone="5559998888", first="J", last="D")
        _customer("CUST-3", email="unique@example.com", phone="5551112222")

        result = data_health.duplicate_customers()

        assert len(result["duplicate_groups_by_email"]) == 1
        group = result["duplicate_groups_by_email"][0]
        assert group["count"] == 2
        assert {m["id"] for m in group["members"]} == {"CUST-1", "CUST-2"}
        assert result["total_customers_affected"] == 2

    def test_two_customers_sharing_a_real_normalized_phone_despite_different_formatting(self):
        _customer("CUST-1", email="a@example.com", phone="(555) 000-1111")
        _customer("CUST-2", email="b@example.com", phone="555.000.1111")

        result = data_health.duplicate_customers()

        assert len(result["duplicate_groups_by_phone"]) == 1
        assert result["duplicate_groups_by_phone"][0]["count"] == 2

    def test_a_customer_affected_by_both_an_email_and_a_phone_match_is_only_counted_once(self):
        _customer("CUST-1", email="dup@example.com", phone="5550001111")
        _customer("CUST-2", email="dup@example.com", phone="5550001111")

        result = data_health.duplicate_customers()

        assert result["total_customers_affected"] == 2

    def test_empty_email_and_phone_values_never_form_a_false_group(self):
        _customer("CUST-1", email="", phone="")
        _customer("CUST-2", email="", phone="")

        result = data_health.duplicate_customers()

        assert result["duplicate_groups_by_email"] == []
        assert result["duplicate_groups_by_phone"] == []

    def test_groups_are_sorted_largest_first(self):
        _customer("CUST-1", email="triple@example.com")
        _customer("CUST-2", email="triple@example.com")
        _customer("CUST-3", email="triple@example.com")
        _customer("CUST-4", email="pair@example.com")
        _customer("CUST-5", email="pair@example.com")

        result = data_health.duplicate_customers()

        counts = [g["count"] for g in result["duplicate_groups_by_email"]]
        assert counts == [3, 2]


class TestDuplicateVehicles:

    def test_no_vehicles_returns_no_groups(self):
        result = data_health.duplicate_vehicles()

        assert result["duplicate_groups_by_vin"] == []
        assert result["total_vehicles_affected"] == 0

    def test_two_vehicles_sharing_a_real_normalized_vin_form_a_group(self):
        _vehicle("VEH-1", vin=" 1ft7x2b69abc12345 ")
        _vehicle("VEH-2", vin="1FT7X2B69ABC12345")
        _vehicle("VEH-3", vin="2GKALMEK5G6123456")

        result = data_health.duplicate_vehicles()

        assert len(result["duplicate_groups_by_vin"]) == 1
        group = result["duplicate_groups_by_vin"][0]
        assert group["count"] == 2
        assert {m["id"] for m in group["members"]} == {"VEH-1", "VEH-2"}
        assert result["total_vehicles_affected"] == 2

    def test_a_blank_vin_never_forms_a_false_group(self):
        _vehicle("VEH-1", vin="")
        _vehicle("VEH-2", vin="")

        result = data_health.duplicate_vehicles()

        assert result["duplicate_groups_by_vin"] == []


class TestPricingDiscrepancies:

    def test_always_reports_the_real_honest_unfabricated_gap(self):
        result = data_health.pricing_discrepancies()

        assert result == {
            "checked": False,
            "count": None,
            "note": data_health.pricing_discrepancies()["note"],
        }
        assert "148 of 343" in result["note"]

    def test_the_gap_is_reported_regardless_of_any_real_data_on_the_graph(self):
        _vehicle("VEH-1")
        _finance_contract("FIN-1")

        result = data_health.pricing_discrepancies()

        assert result["checked"] is False
        assert result["count"] is None


class TestInventoryMismatches:

    def test_a_sold_vehicle_with_no_purchased_relationship_is_a_real_discrepancy(self):
        _vehicle("VEH-1", date_sold="2026-01-01")

        result = data_health.inventory_mismatches(ADMIN)

        assert result["sold_without_purchase_relationship"] == 1
        assert result["discrepancies"][0]["vehicle_id"] == "VEH-1"

    def test_a_sold_vehicle_with_a_real_purchased_relationship_is_not_a_discrepancy(self):
        _customer("CUST-1")
        _vehicle("VEH-1", date_sold="2026-01-01")
        _purchased("CUST-1", "VEH-1")

        result = data_health.inventory_mismatches(ADMIN)

        assert result["sold_without_purchase_relationship"] == 0
        assert result["discrepancies"] == []

    def test_the_result_is_a_verbatim_reuse_of_the_real_workflow_tab_data_source(self):
        result = data_health.inventory_mismatches(ADMIN)

        assert result["source"].startswith("core/workflow_tab_data.py")
        assert result["note"] is not None

    def test_discrepancies_are_capped_at_25(self):
        for i in range(30):
            _vehicle(f"VEH-{i}", date_sold="2026-01-01")

        result = data_health.inventory_mismatches(ADMIN)

        assert result["sold_without_purchase_relationship"] == 30
        assert len(result["discrepancies"]) == 25


class TestDataAccuracy:

    def test_composes_all_four_real_sub_sections(self):
        result = data_health.data_accuracy(ADMIN)

        assert set(result.keys()) == {
            "duplicate_customers", "duplicate_vehicles",
            "pricing_discrepancies", "inventory_mismatches",
        }
        assert result["pricing_discrepancies"]["checked"] is False


class TestDataAccuracyApi:

    def test_denied_role_gets_the_real_denial_message(self):
        result = data_health_api.get_data_accuracy_api(SERVICE)

        assert result["error"].startswith("You don't have access to Data Health")

    def test_admin_is_allowed_through(self):
        result = data_health_api.get_data_accuracy_api(ADMIN)

        assert "error" not in result
        assert "duplicate_customers" in result


# ===========================================================================
# 4. Data Freshness
# ===========================================================================

class TestDataFreshness:

    def test_a_denied_role_propagates_the_real_underlying_connections_denial(self):
        result = data_health.data_freshness(SALES)

        assert "error" in result

    def test_no_connections_returns_a_real_empty_baseline(self):
        result = data_health.data_freshness(ADMIN)

        assert result["last_sync"]["connections"] == []
        assert result["last_sync"]["never_synced_count"] == 0

    def test_a_never_synced_connection_is_counted(self):
        _connection(department="sales")

        result = data_health.data_freshness(ADMIN)

        assert result["last_sync"]["never_synced_count"] == 1

    def test_last_sync_rows_are_sorted_most_recently_synced_first(self):
        old_id = _connection(name="Old", department="sales")
        new_id = _connection(name="New", department="service")

        ledger.get_entity(old_id).attributes["last_synced_at"] = "2026-01-01T00:00:00+00:00"
        ledger.get_entity(new_id).attributes["last_synced_at"] = "2026-07-01T00:00:00+00:00"

        result = data_health.data_freshness(ADMIN)

        ids_in_order = [r["id"] for r in result["last_sync"]["connections"]]
        assert ids_in_order == [new_id, old_id]

    def test_records_updated_last_24h_counts_a_real_recent_deal(self):
        from datetime import datetime, timezone

        recent = datetime.now(timezone.utc).isoformat()
        _deal("DEAL-1", updated_at=recent)

        result = data_health.data_freshness(ADMIN)

        assert result["records_updated_last_24h"]["by_entity_type"]["deals"] == 1
        assert result["records_updated_last_24h"]["total"] == 1

    def test_records_updated_last_24h_excludes_an_old_deal(self):
        _deal("DEAL-1", updated_at="2020-01-01T00:00:00+00:00")

        result = data_health.data_freshness(ADMIN)

        assert result["records_updated_last_24h"]["by_entity_type"]["deals"] == 0

    def test_records_updated_last_24h_counts_a_vehicle_via_description_updated_at(self):
        from datetime import datetime, timezone

        recent = datetime.now(timezone.utc).isoformat()
        _vehicle("VEH-1", description_updated_at=recent)

        result = data_health.data_freshness(ADMIN)

        assert result["records_updated_last_24h"]["by_entity_type"]["vehicles"] == 1

    def test_records_updated_last_24h_counts_a_vehicle_via_a_recent_price_history_entry(self):
        from datetime import datetime, timezone

        recent = datetime.now(timezone.utc).isoformat()
        _vehicle("VEH-1", price_history=[{"old_price": 20000, "new_price": 19000, "updated_at": recent}])

        result = data_health.data_freshness(ADMIN)

        assert result["records_updated_last_24h"]["by_entity_type"]["vehicles"] == 1

    def test_records_updated_last_24h_counts_a_repair_order_via_a_recent_stage_history_entry(self):
        from datetime import datetime, timezone

        recent = datetime.now(timezone.utc).isoformat()
        _service_record("SRV-1", ro_stage_history=[{"stage": "Estimate", "at": recent}])

        result = data_health.data_freshness(ADMIN)

        assert result["records_updated_last_24h"]["by_entity_type"]["repair_orders"] == 1

    def test_records_updated_last_24h_honestly_excludes_customers_and_finance_contracts(self):
        result = data_health.data_freshness(ADMIN)

        assert "customers" in result["records_updated_last_24h"]["not_yet_tracked"]
        assert "finance_contracts" in result["records_updated_last_24h"]["not_yet_tracked"]

    def test_pending_changes_composes_all_four_real_queues_for_admin(self):
        result = data_health.data_freshness(ADMIN)

        pending = result["pending_changes"]
        assert pending["campaigns"] == {"count": 0, "items": []}
        assert pending["assets"] == {"count": 0, "items": []}
        assert pending["websites"] == {"count": 0, "items": []}
        assert pending["financing"] == {"count": 0, "items": []}

    def test_pending_changes_honestly_reports_a_real_role_denial_per_queue(self):
        # OPERATIONS is allowed through data_health_api's own ADMIN/OPERATIONS
        # gate, but campaigns/assets/websites' own narrower _can_review /
        # _can_activate gates (ADMIN or MARKETING only) still deny it --
        # financing's own _can_do_financing gate (ADMIN/OPERATIONS/FINANCE)
        # allows it through. A real, in-the-wild mixed result, not a
        # fabricated test-only scenario.
        result = data_health.data_freshness(OPERATIONS)

        pending = result["pending_changes"]
        assert pending["campaigns"]["count"] is None
        assert "error" in pending["campaigns"]
        assert pending["assets"]["count"] is None
        assert pending["websites"]["count"] is None
        assert pending["financing"] == {"count": 0, "items": []}


class TestDataFreshnessApi:

    def test_denied_role_gets_the_real_denial_message(self):
        result = data_health_api.get_data_freshness_api(FINANCE)

        assert result["error"].startswith("You don't have access to Data Health")

    def test_operations_is_allowed_through(self):
        result = data_health_api.get_data_freshness_api(OPERATIONS)

        assert "error" not in result
        assert "last_sync" in result


# ===========================================================================
# Composition
# ===========================================================================

class TestGetDataHealthOverview:

    def test_composes_all_four_real_sections_plus_a_timestamp(self):
        result = data_health.get_data_health_overview(ADMIN)

        assert set(result.keys()) == {
            "integration_monitoring", "data_completeness",
            "data_accuracy", "data_freshness", "generated_at",
        }
        assert result["generated_at"]


class TestGetDataHealthOverviewApi:

    def test_denied_role_gets_the_real_denial_message(self):
        result = data_health_api.get_data_health_overview_api(SALES)

        assert result["error"].startswith("You don't have access to Data Health")

    def test_admin_is_allowed_through_to_the_full_real_composition(self):
        result = data_health_api.get_data_health_overview_api(ADMIN)

        assert "error" not in result
        assert "integration_monitoring" in result
        assert "data_completeness" in result
        assert "data_accuracy" in result
        assert "data_freshness" in result
