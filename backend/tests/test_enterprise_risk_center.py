"""
Tests for core/enterprise_risk_center.py / core/enterprise_risk_center_api.py --
Readiness's reimagined "Exceptions" Top Menu item, also Sam's separately-named
"Enterprise Risk Center" capstone. A pure composition engine over 8 already-real
sub-signals (compliance alerts, data connections, operations overview/alerts/
scheduling, lot control, shop control, deals) plus one genuinely new real
per-deal computation (negative_gross_deals).

Most sub-signal functions are tested at the composition boundary -- monkeypatched
at the module level (core.enterprise_risk_center.<dependency>) to verify the
wiring/severity-bucketing/category-grouping logic THIS module owns, since each
underlying dependency (operations_overview, operations_alerts, lot_control,
shop_control, operations_scheduling) already has its own dedicated test file
elsewhere in this suite. _unfunded_contracts and _negative_gross_deals get real
ledger fixtures instead, since they compute directly off real Deal/Vehicle
entities with no intermediate composed dependency to mock. _data_sync_failures
and _open_compliance_issues use the REAL underlying list_connections_api/
list_alerts_api (both pure reads, no save_graph call) to also prove out the real
role-gate denial passthrough for a SALES-role caller.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import DEAL, VEHICLE
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import enterprise_risk_center
from core import enterprise_risk_center_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


def _vehicle(vehicle_id, price, cost):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={
        "Price": str(price),
        "Cost": str(cost),
        "Year": "2024",
        "Make": "Ford",
        "Model": "F-150",
    }))


def _deal(deal_id, status, vehicle_id=None, financing_type=None):
    attrs = {"status": status}
    if vehicle_id:
        attrs["vehicle_id"] = vehicle_id
    if financing_type:
        attrs["financing_type"] = financing_type
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes=attrs))


# ---------------------------------------------------------------------------
# Pure severity-bucketing / mapping helpers
# ---------------------------------------------------------------------------

class TestCountSeverity:

    def test_zero_or_none_is_none(self):
        assert enterprise_risk_center._count_severity(0) is None
        assert enterprise_risk_center._count_severity(None) is None

    def test_negative_is_none(self):
        assert enterprise_risk_center._count_severity(-3) is None

    def test_one_to_two_is_low(self):
        assert enterprise_risk_center._count_severity(1) == "low"
        assert enterprise_risk_center._count_severity(2) == "low"

    def test_three_to_nine_is_medium(self):
        assert enterprise_risk_center._count_severity(3) == "medium"
        assert enterprise_risk_center._count_severity(9) == "medium"

    def test_ten_to_twentyfour_is_high(self):
        assert enterprise_risk_center._count_severity(10) == "high"
        assert enterprise_risk_center._count_severity(24) == "high"

    def test_twentyfive_plus_is_critical(self):
        assert enterprise_risk_center._count_severity(25) == "critical"
        assert enterprise_risk_center._count_severity(1000) == "critical"


class TestDollarSeverity:

    def test_zero_or_none_is_none(self):
        assert enterprise_risk_center._dollar_severity(0) is None
        assert enterprise_risk_center._dollar_severity(None) is None

    def test_under_1000_is_low(self):
        assert enterprise_risk_center._dollar_severity(999.99) == "low"

    def test_under_5000_is_medium(self):
        assert enterprise_risk_center._dollar_severity(1000) == "medium"
        assert enterprise_risk_center._dollar_severity(4999.99) == "medium"

    def test_under_15000_is_high(self):
        assert enterprise_risk_center._dollar_severity(5000) == "high"
        assert enterprise_risk_center._dollar_severity(14999.99) == "high"

    def test_15000_plus_is_critical(self):
        assert enterprise_risk_center._dollar_severity(15000) == "critical"
        assert enterprise_risk_center._dollar_severity(500000) == "critical"


class TestTwoTierToFourTier:

    def test_red_maps_to_critical(self):
        assert enterprise_risk_center._twotier_to_fourtier("red") == "critical"

    def test_high_maps_to_critical(self):
        assert enterprise_risk_center._twotier_to_fourtier("high") == "critical"

    def test_yellow_maps_to_high(self):
        assert enterprise_risk_center._twotier_to_fourtier("yellow") == "high"

    def test_medium_maps_to_high(self):
        assert enterprise_risk_center._twotier_to_fourtier("medium") == "high"

    def test_anything_unrecognized_maps_to_high(self):
        assert enterprise_risk_center._twotier_to_fourtier("bogus") == "high"
        assert enterprise_risk_center._twotier_to_fourtier(None) == "high"


class TestWorstSeverity:

    def test_empty_is_none(self):
        assert enterprise_risk_center._worst_severity([]) is None

    def test_all_none_is_none(self):
        assert enterprise_risk_center._worst_severity([None, None]) is None

    def test_returns_the_real_worst_present(self):
        assert enterprise_risk_center._worst_severity(["low", "critical", "medium"]) == "critical"
        assert enterprise_risk_center._worst_severity(["low", None, "high"]) == "high"


# ---------------------------------------------------------------------------
# Critical Issues -- composition-boundary tests via monkeypatch
# ---------------------------------------------------------------------------

class TestVehiclesMissingTitles:

    def test_real_zero_case_reports_no_severity(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_operations_overview_api", lambda role: {
            "action_center": {"vehicles_missing_titles": {"count": 0, "vehicles": []}}
        })

        result = enterprise_risk_center._vehicles_missing_titles(ADMIN)

        assert result["count"] == 0
        assert result["severity"] is None
        assert result["category"] == "critical"
        assert result["resolve"] == {
            "department": "Operations", "item_key": "documents",
            "hint": "Request the missing Title document.",
        }

    def test_composes_real_count_and_items_with_correct_severity(self, monkeypatch):
        vehicles = [{"vehicle_id": f"VEH-{i}", "vin": f"VIN{i}", "stock_number": f"S{i}"} for i in range(12)]
        monkeypatch.setattr(enterprise_risk_center, "get_operations_overview_api", lambda role: {
            "action_center": {"vehicles_missing_titles": {"count": 12, "vehicles": vehicles}}
        })

        result = enterprise_risk_center._vehicles_missing_titles(ADMIN)

        assert result["count"] == 12
        assert result["severity"] == "high"
        assert len(result["items"]) == 12
        assert result["items"][0]["id"] == "VEH-0"

    def test_items_are_capped_at_25(self, monkeypatch):
        vehicles = [{"vehicle_id": f"VEH-{i}", "vin": f"VIN{i}", "stock_number": f"S{i}"} for i in range(40)]
        monkeypatch.setattr(enterprise_risk_center, "get_operations_overview_api", lambda role: {
            "action_center": {"vehicles_missing_titles": {"count": 40, "vehicles": vehicles}}
        })

        result = enterprise_risk_center._vehicles_missing_titles(ADMIN)

        assert result["count"] == 40
        assert len(result["items"]) == 25


class TestContractsMissingDocuments:

    def test_denied_role_degrades_to_a_real_denied_item(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_alert_feed_api", lambda role: {"error": "denied for this role"})

        result = enterprise_risk_center._contracts_missing_documents(SALES)

        assert result["key"] == "contracts_missing_documents"
        assert result["severity"] is None
        assert result["count"] is None
        assert result["access_error"] == "denied for this role"
        assert result["items"] == []

    def test_filters_only_missing_deal_jacket_alert_type(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_alert_feed_api", lambda role: {"alerts": [
            {"alert_type": "missing_deal_jacket", "source_id": "DEAL-1", "detail": "no jacket"},
            {"alert_type": "stalled_deal", "source_id": "DEAL-2", "detail": "stalled"},
        ]})

        result = enterprise_risk_center._contracts_missing_documents(ADMIN)

        assert result["count"] == 1
        assert result["items"] == [{"id": "DEAL-1", "label": "no jacket"}]
        assert result["severity"] == "low"


class TestInventoryNotLocated:

    def test_denied_role_degrades_to_a_real_denied_item(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_key_board_api", lambda role: {"error": "denied"})

        result = enterprise_risk_center._inventory_not_located(SALES)

        assert result["access_error"] == "denied"
        assert result["severity"] is None
        assert result["count"] is None
        assert result["items"] == []
        assert result["resolve"] == {
            "department": "Inventory", "item_key": "lot_management",
            "hint": "Open the Key Management tab and resolve the missing key.",
        }

    def test_composes_real_missing_key_count(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_key_board_api", lambda role: {
            "missing": [{"vehicle_id": "VEH-1", "vin": "VIN1"}]
        })

        result = enterprise_risk_center._inventory_not_located(ADMIN)

        assert result["count"] == 1
        assert result["severity"] == "low"


class TestDataSyncFailures:

    def test_real_denial_passthrough_for_a_denied_role(self):
        result = enterprise_risk_center._data_sync_failures(SALES)

        assert result["access_error"] == (
            "You don't have access to data connections with your current role -- "
            "Admin or Operations can configure integrations."
        )
        assert result["count"] is None

    def test_real_zero_connections_case_for_an_allowed_role(self):
        result = enterprise_risk_center._data_sync_failures(ADMIN)

        assert result["count"] == 0
        assert result["severity"] is None
        assert "error" not in result

    def test_composes_real_error_status_connections(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "list_connections_api", lambda role: {
            "connections": [
                {"id": "CONN-1", "name": "OEM Feed", "department": "sales", "status": "error"},
                {"id": "CONN-2", "name": "Fine", "department": "service", "status": "active"},
            ]
        })

        result = enterprise_risk_center._data_sync_failures(ADMIN)

        assert result["count"] == 1
        assert result["items"] == [{"id": "CONN-1", "label": "OEM Feed (sales)"}]


# ---------------------------------------------------------------------------
# Financial Exceptions
# ---------------------------------------------------------------------------

class TestUnfundedContracts:

    def test_real_zero_case(self):
        result = enterprise_risk_center._unfunded_contracts(ADMIN)

        assert result["count"] == 0
        assert result["severity"] is None

    def test_only_contract_status_deals_count(self):
        _deal("DEAL-1", status="contract", financing_type="in_house")
        _deal("DEAL-2", status="funded", financing_type="in_house")
        _deal("DEAL-3", status="desking")

        result = enterprise_risk_center._unfunded_contracts(ADMIN)

        assert result["count"] == 1
        assert result["items"] == [{"id": "DEAL-1", "label": "DEAL-1 -- in_house"}]

    def test_missing_financing_type_falls_back_to_honest_label(self):
        _deal("DEAL-1", status="contract")

        result = enterprise_risk_center._unfunded_contracts(ADMIN)

        assert result["items"][0]["label"] == "DEAL-1 -- unknown financing"


class TestFundingDelays:

    def test_denied_role_degrades_to_a_real_denied_item(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_alert_feed_api", lambda role: {"error": "denied"})

        result = enterprise_risk_center._funding_delays(SALES)

        assert result["access_error"] == "denied"
        assert result["basis"] == "real"  # _denied_item's own shape, not the happy-path "heuristic"
        assert result["severity"] is None
        assert result["count"] is None

    def test_filters_stalled_deal_and_maps_severity_correctly(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_alert_feed_api", lambda role: {"alerts": [
            {"alert_type": "stalled_deal", "source_id": "DEAL-1", "title": "Stalled 1", "severity": "red"},
            {"alert_type": "stalled_deal", "source_id": "DEAL-2", "title": "Stalled 2", "severity": "yellow"},
            {"alert_type": "missing_deal_jacket", "source_id": "DEAL-3", "title": "Not this one", "severity": "red"},
        ]})

        result = enterprise_risk_center._funding_delays(ADMIN)

        assert result["count"] == 2
        assert result["severity"] == "critical"  # worst of critical/high
        assert result["items"][0]["severity"] == "critical"
        assert result["items"][1]["severity"] == "high"


class TestNegativeGrossDeals:

    def test_real_zero_case(self):
        result = enterprise_risk_center._negative_gross_deals(ADMIN)

        assert result["count"] == 0
        assert result["severity"] is None
        assert result["total_loss"] == 0.0

    def test_flags_only_funded_deals_with_price_below_cost(self):
        _vehicle("VEH-1", price=25000, cost=27500)  # negative gross -2500
        _deal("DEAL-1", status="funded", vehicle_id="VEH-1")

        _vehicle("VEH-2", price=30000, cost=25000)  # positive gross, not flagged
        _deal("DEAL-2", status="funded", vehicle_id="VEH-2")

        # A contract-status (not funded) deal with negative gross should NOT count.
        _vehicle("VEH-3", price=10000, cost=15000)
        _deal("DEAL-3", status="contract", vehicle_id="VEH-3")

        result = enterprise_risk_center._negative_gross_deals(ADMIN)

        assert result["count"] == 1
        assert result["total_loss"] == 2500.0
        assert result["items"][0]["id"] == "DEAL-1"
        assert result["items"][0]["gross"] == -2500.0
        assert result["severity"] == "medium"  # $2500 loss -> <$5000 bucket

    def test_severity_matches_the_real_dollar_bucket(self):
        # A real $600 loss should land in the "low" bucket (<$1000).
        _vehicle("VEH-1", price=10000, cost=10600)
        _deal("DEAL-1", status="funded", vehicle_id="VEH-1")

        result = enterprise_risk_center._negative_gross_deals(ADMIN)

        assert result["total_loss"] == 600.0
        assert result["severity"] == "low"

    def test_deals_with_no_matching_vehicle_are_skipped_not_crashed(self):
        _deal("DEAL-1", status="funded", vehicle_id="VEH-DOES-NOT-EXIST")

        result = enterprise_risk_center._negative_gross_deals(ADMIN)

        assert result["count"] == 0

    def test_results_sorted_worst_loss_first(self):
        _vehicle("VEH-1", price=9000, cost=9500)  # -500
        _deal("DEAL-1", status="funded", vehicle_id="VEH-1")
        _vehicle("VEH-2", price=9000, cost=12000)  # -3000
        _deal("DEAL-2", status="funded", vehicle_id="VEH-2")

        result = enterprise_risk_center._negative_gross_deals(ADMIN)

        assert [item["id"] for item in result["items"]] == ["DEAL-2", "DEAL-1"]


# ---------------------------------------------------------------------------
# Operational Exceptions
# ---------------------------------------------------------------------------

class TestReconDelays:

    def test_denied_role_degrades_to_a_real_denied_item(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_recon_schedule_api", lambda role: {"error": "denied"})

        result = enterprise_risk_center._recon_delays(SALES)

        assert result["access_error"] == "denied"

    def test_composes_real_backlog_count(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_recon_schedule_api", lambda role: {
            "used_unsold_count": 5,
            "vehicles": [{"vehicle_id": "VEH-1", "vin": "VIN1", "year": "2020", "make": "Ford", "model": "F-150", "lot": "Main"}],
        })

        result = enterprise_risk_center._recon_delays(ADMIN)

        assert result["count"] == 5
        assert result["severity"] == "medium"  # 5 -> the 3-9 bucket
        assert len(result["items"]) == 1


class TestServiceDelays:

    def test_denied_role_degrades_to_a_real_denied_item(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_bottlenecks_api", lambda role: {"error": "denied"})

        result = enterprise_risk_center._service_delays(SALES)

        assert result["access_error"] == "denied"

    def test_composes_and_sums_all_three_bottleneck_types(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "get_bottlenecks_api", lambda role: {
            "parts_delays": {"count": 2, "repair_orders": [{"id": "RO-1"}]},
            "approval_delays": {"count": 1, "repair_orders": [{"id": "RO-2", "hours_open": 30}]},
            "technician_delays": {"count": 0, "repair_orders": []},
        })

        result = enterprise_risk_center._service_delays(ADMIN)

        assert result["count"] == 3
        assert result["severity"] == "medium"  # 3 -> the 3-9 bucket
        assert any("parts backordered" in item["label"] for item in result["items"])
        assert any("awaiting customer approval" in item["label"] for item in result["items"])


class TestOpenComplianceIssues:

    def test_real_denial_passthrough_for_a_denied_role(self):
        result = enterprise_risk_center._open_compliance_issues(SALES)

        assert "Admin or Operations" in result["access_error"]
        assert result["count"] is None

    def test_real_zero_alerts_case_for_an_allowed_role(self):
        result = enterprise_risk_center._open_compliance_issues(ADMIN)

        assert result["count"] == 0
        assert result["severity"] is None

    def test_severity_is_critical_when_any_alert_is_high(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "list_alerts_api", lambda role, status=None: {
            "alerts": [
                {"id": "CA-1", "law": "TILA", "severity": "high"},
                {"id": "CA-2", "law": "ECOA", "severity": "medium"},
            ]
        })

        result = enterprise_risk_center._open_compliance_issues(ADMIN)

        assert result["count"] == 2
        assert result["severity"] == "critical"

    def test_severity_is_high_when_no_alert_is_high(self, monkeypatch):
        monkeypatch.setattr(enterprise_risk_center, "list_alerts_api", lambda role, status=None: {
            "alerts": [{"id": "CA-1", "law": "GLBA", "severity": "medium"}]
        })

        result = enterprise_risk_center._open_compliance_issues(ADMIN)

        assert result["severity"] == "high"


# ---------------------------------------------------------------------------
# Overview + per-category drill-down
# ---------------------------------------------------------------------------

class TestGetRiskCenterOverview:

    def test_real_all_clear_baseline_has_no_active_exceptions(self):
        result = enterprise_risk_center.get_risk_center_overview(ADMIN)

        assert result["kpi"]["total_exception_types_active"] == 0
        assert result["kpi"]["total_exception_types"] == 10
        assert result["kpi"]["total_affected_entities"] == 0
        assert result["kpi"]["by_severity"] == {"low": 0, "medium": 0, "high": 0, "critical": 0}
        assert result["overall_risk_score"] is None
        assert "no single blended" in result["overall_risk_score_note"].lower()

    def test_real_exception_lands_in_the_correct_category_and_contributes_to_kpis(self):
        # NOTE: VEH-1/DEAL-1 (a funded deal with no Title/Deal-Jacket document on
        # file) genuinely, correctly ALSO trips the real, independently-composed
        # vehicles_missing_titles/contracts_missing_documents signals -- confirmed
        # by direct inspection, not a test bug -- so this only asserts on the two
        # exception types this test deliberately targets, rather than an exact
        # total count that would be brittle against that real cascading behavior.
        _vehicle("VEH-1", price=9000, cost=15000)  # -6000 gross -> $15000 total_loss -> high bucket
        _deal("DEAL-1", status="funded", vehicle_id="VEH-1")
        _deal("DEAL-2", status="contract")  # unfunded contract, count=1 -> low bucket

        result = enterprise_risk_center.get_risk_center_overview(ADMIN)

        financial_keys = {item["key"] for item in result["categories"]["financial_exceptions"]}
        assert "negative_gross_deals" in financial_keys
        assert "unfunded_contracts" in financial_keys

        neg_gross = next(i for i in result["categories"]["financial_exceptions"] if i["key"] == "negative_gross_deals")
        assert neg_gross["severity"] == "high"
        assert neg_gross["total_loss"] == 6000.0

        unfunded = next(i for i in result["categories"]["financial_exceptions"] if i["key"] == "unfunded_contracts")
        assert unfunded["severity"] == "low"
        assert unfunded["count"] == 1

        assert result["kpi"]["total_exception_types_active"] >= 2
        assert result["kpi"]["by_severity"]["high"] >= 1
        assert result["kpi"]["by_severity"]["low"] >= 1

    def test_all_ten_exception_types_are_always_present_even_when_clear(self):
        result = enterprise_risk_center.get_risk_center_overview(ADMIN)

        all_keys = set()
        for bucket in result["categories"].values():
            all_keys |= {item["key"] for item in bucket}

        assert all_keys == set(enterprise_risk_center._EXCEPTION_FUNCTIONS.keys())

    def test_categories_are_grouped_exactly_as_documented(self):
        result = enterprise_risk_center.get_risk_center_overview(ADMIN)

        critical_keys = {item["key"] for item in result["categories"]["critical_issues"]}
        financial_keys = {item["key"] for item in result["categories"]["financial_exceptions"]}
        operational_keys = {item["key"] for item in result["categories"]["operational_exceptions"]}

        assert critical_keys == {
            "vehicles_missing_titles", "contracts_missing_documents",
            "inventory_not_located", "data_sync_failures",
        }
        assert financial_keys == {"unfunded_contracts", "funding_delays", "negative_gross_deals"}
        assert operational_keys == {"recon_delays", "service_delays", "open_compliance_issues"}

    def test_runs_cleanly_for_every_real_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            result = enterprise_risk_center.get_risk_center_overview(role)
            assert "categories" in result


class TestGetRiskCenterCategory:

    def test_rejects_an_unknown_category(self):
        result = enterprise_risk_center.get_risk_center_category(ADMIN, "bogus")

        assert result == {"error": "Unknown category 'bogus' -- expected one of ['critical', 'financial', 'operational']."}

    def test_critical_category_returns_the_correct_four_items(self):
        result = enterprise_risk_center.get_risk_center_category(ADMIN, "critical")

        assert result["category"] == "critical"
        assert {item["key"] for item in result["items"]} == {
            "vehicles_missing_titles", "contracts_missing_documents",
            "inventory_not_located", "data_sync_failures",
        }

    def test_financial_category_returns_the_correct_three_items(self):
        result = enterprise_risk_center.get_risk_center_category(ADMIN, "financial")

        assert {item["key"] for item in result["items"]} == {
            "unfunded_contracts", "funding_delays", "negative_gross_deals",
        }

    def test_operational_category_returns_the_correct_three_items(self):
        result = enterprise_risk_center.get_risk_center_category(ADMIN, "operational")

        assert {item["key"] for item in result["items"]} == {
            "recon_delays", "service_delays", "open_compliance_issues",
        }

    def test_category_lookup_is_case_and_whitespace_insensitive(self):
        result = enterprise_risk_center.get_risk_center_category(ADMIN, "  CRITICAL  ")

        assert result["category"] == "critical"


# ---------------------------------------------------------------------------
# core/enterprise_risk_center_api.py -- the deliberately-broad ACL gate.
# ---------------------------------------------------------------------------

class TestEnterpriseRiskCenterApi:

    def test_overview_denies_an_unknown_role(self):
        result = enterprise_risk_center_api.get_risk_center_overview_api("NOT_A_REAL_ROLE")

        assert result == {"error": "You don't have access to the Enterprise Risk Center."}

    def test_overview_succeeds_for_every_real_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            result = enterprise_risk_center_api.get_risk_center_overview_api(role)
            assert "error" not in result
            assert "categories" in result

    def test_category_denies_an_unknown_role_before_dispatching(self):
        result = enterprise_risk_center_api.get_risk_center_category_api("NOT_A_REAL_ROLE", "critical")

        assert result == {"error": "You don't have access to the Enterprise Risk Center."}

    def test_category_dispatches_correctly_for_an_allowed_role(self):
        result = enterprise_risk_center_api.get_risk_center_category_api(ADMIN, "financial")

        assert result["category"] == "financial"

    def test_a_denied_sub_signal_still_degrades_gracefully_end_to_end(self):
        # SALES is a real role (passes the module's own broad gate) but is denied
        # by Compliance/Data Connections' own narrower, real ACL underneath --
        # confirms the "no second redundant gate" design holds through the full
        # overview_api -> get_risk_center_overview -> the two real sub-calls chain.
        result = enterprise_risk_center_api.get_risk_center_overview_api(SALES)

        assert "error" not in result  # the whole response does NOT fail
        compliance_item = next(i for i in result["categories"]["operational_exceptions"] if i["key"] == "open_compliance_issues")
        assert "access_error" in compliance_item
        sync_item = next(i for i in result["categories"]["critical_issues"] if i["key"] == "data_sync_failures")
        assert "access_error" in sync_item
