"""
Tests for core/readiness_recommendations.py / core/readiness_recommendations_api.py
-- Readiness' "Recommendations" item, a real 12-rule composition engine (not a
fabricated LLM narrative) spanning Sales/Service/Finance/Inventory/Marketing.

Ten of the twelve rules compose an already-real signal from another module
(core/business_health.py's sales_health/service_health/finance_health, core/
enterprise_risk_center.py's get_risk_center_overview, core/workflow_tab_data.py's
inventory_wholesale_disposition, core/inventory_aging.py's get_aging_board, core/
marketing_attribution.py's get_channel_mix) -- those ten are tested at the
composition boundary here (monkeypatching the dependency function bound into
core.readiness_recommendations's own namespace via `from X import Y`), since the
underlying computations already have their own dedicated test coverage elsewhere.

Two rules (_service_type_trend/_service_type_underperformance) are genuinely new
computations with no upstream module to monkeypatch away -- those are tested with
real ServiceRecord ledger fixtures instead.

This module makes zero graph mutations of its own -- pure read/composition, no
save_graph anywhere in the file.

Run from backend/ with `pytest`.
"""

import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import SERVICE_RECORD
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import readiness_recommendations
from core.readiness_recommendations import (
    CATEGORIES,
    WHOLESALE_MIN_COUNT,
    PRICE_BAND_MIN_COUNT,
    UNFUNDED_CONTRACTS_MIN_COUNT,
    COLLECTIONS_RISK_MIN_COUNT,
    OVERLOADED_TECH_MIN,
    SERVICE_DELAYS_MIN_COUNT,
    SHOW_RATE_MIN_APPTS,
    SHOW_RATE_THRESHOLD,
    SERVICE_TYPE_MIN_PRIOR_COUNT,
    SERVICE_TYPE_DECLINE_PCT,
    MARKETING_MIN_LEAD_COUNT,
    MARKETING_OVERPERFORM_RATIO,
    MARKETING_UNDERPERFORM_RATIO,
    _now,
    _safe_float,
    _item,
    _access_denied_item,
    _inventory_aging_action,
    _recon_delays,
    _finance_funding_delays,
    _finance_unfunded_contracts,
    _finance_negative_gross,
    _finance_collections_risk,
    _finance_compliance_risk,
    _all_service_records,
    _service_type_trend,
    _service_type_underperformance,
    _service_shop_overload,
    _service_delays,
    _sales_show_rate,
    _marketing_channel_performance,
    get_recommendations_overview,
    get_recommendations_category,
)
from core import readiness_recommendations_api
from core.readiness_recommendations_api import (
    get_recommendations_overview_api,
    get_recommendations_category_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)


# ---------------------------------------------------------------------------
# Fixture builders (only needed for the two genuinely-new real computations)
# ---------------------------------------------------------------------------

def _service_record(record_id, service_date, description, cost, parts_cost=0):
    ledger.add_entity(Entity(id=record_id, entity_type=SERVICE_RECORD, attributes={
        "ServiceDate": service_date,
        "Description": description,
        "Cost": str(cost),
        "PartsCost": str(parts_cost),
    }))


def _risk_item(key, category_key, count=0, severity=None, access_error=None, total_loss=None):
    """Builds one item shaped like core/enterprise_risk_center.py's own
    per-exception dict, for monkeypatching get_risk_center_overview."""
    out = {"key": key, "count": count, "severity": severity}
    if access_error is not None:
        out["access_error"] = access_error
    if total_loss is not None:
        out["total_loss"] = total_loss
    return out


def _risk_overview(critical=None, financial=None, operational=None):
    return {
        "categories": {
            "critical_issues": critical or [],
            "financial_exceptions": financial or [],
            "operational_exceptions": operational or [],
        }
    }


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------

class TestNow:

    def test_returns_an_iso_string(self):
        value = _now()
        assert isinstance(value, str)
        assert "T" in value


class TestSafeFloat:

    def test_parses_a_numeric_string(self):
        assert _safe_float("42.5") == 42.5

    def test_returns_default_on_none(self):
        assert _safe_float(None) == 0.0

    def test_returns_default_on_garbage(self):
        assert _safe_float("not-a-number") == 0.0

    def test_returns_custom_default(self):
        assert _safe_float(None, default=7.0) == 7.0


class TestItemHelper:

    def test_not_triggered_nulls_severity_and_recommendation(self):
        item = _item("k", "sales", "Title", False, "high", "finding text", "rec text", "real", {"department": "Sales"})
        assert item["triggered"] is False
        assert item["severity"] is None
        assert item["recommendation"] is None
        assert item["finding"] == "finding text"

    def test_triggered_keeps_severity_and_recommendation(self):
        item = _item("k", "sales", "Title", True, "high", "finding text", "rec text", "real", {"department": "Sales"})
        assert item["triggered"] is True
        assert item["severity"] == "high"
        assert item["recommendation"] == "rec text"

    def test_extra_kwargs_are_merged_in(self):
        item = _item("k", "sales", "Title", True, "high", "f", "r", "real", {}, actions=[1, 2, 3])
        assert item["actions"] == [1, 2, 3]

    def test_default_signal_type_is_risk(self):
        item = _item("k", "sales", "Title", False, None, "f", None, "real", {})
        assert item["signal_type"] == "risk"


class TestAccessDeniedItem:

    def test_shape(self):
        item = _access_denied_item("k", "finance", "Title", {"department": "Finance"}, "no access message")
        assert item["triggered"] is False
        assert item["severity"] is None
        assert item["basis"] == "real"
        assert item["access_error"] == "no access message"
        assert item["finding"] == "no access message"


# ---------------------------------------------------------------------------
# Inventory: _inventory_aging_action
# ---------------------------------------------------------------------------

class TestInventoryAgingAction:

    def _patch(self, monkeypatch, wholesale_count, price_band_count):
        candidates = [
            {"vehicle_id": f"VEH-{i:03d}", "vin": f"VIN{i}", "margin_pct": 0.03}
            for i in range(wholesale_count)
        ]
        monkeypatch.setattr(readiness_recommendations, "inventory_wholesale_disposition",
                             lambda role: {"count": wholesale_count, "candidates": candidates})

        high_band = [
            {"vehicle_id": f"VEH-H{i:03d}", "vin": f"VINH{i}", "price": 45000.0}
            for i in range(price_band_count)
        ]
        monkeypatch.setattr(readiness_recommendations, "get_aging_board",
                             lambda: {"by_price_band": {"40k_plus": high_band}})

    def test_not_triggered_below_both_thresholds(self, monkeypatch):
        self._patch(monkeypatch, wholesale_count=WHOLESALE_MIN_COUNT - 1, price_band_count=PRICE_BAND_MIN_COUNT - 1)
        item = _inventory_aging_action(ADMIN)
        assert item["triggered"] is False
        assert item["severity"] is None
        assert item["actions"] == []
        assert item["recommendation"] is None

    def test_triggered_by_wholesale_threshold_alone(self, monkeypatch):
        self._patch(monkeypatch, wholesale_count=WHOLESALE_MIN_COUNT, price_band_count=0)
        item = _inventory_aging_action(ADMIN)
        assert item["triggered"] is True
        assert len(item["actions"]) == 1
        assert "Wholesale review" in item["actions"][0]["action"]
        assert item["recommendation"] is not None

    def test_triggered_by_price_band_threshold_alone(self, monkeypatch):
        self._patch(monkeypatch, wholesale_count=0, price_band_count=PRICE_BAND_MIN_COUNT)
        item = _inventory_aging_action(ADMIN)
        assert item["triggered"] is True
        assert len(item["actions"]) == 1
        assert "Price reduction" in item["actions"][0]["action"]

    def test_triggered_by_both_produces_two_actions(self, monkeypatch):
        self._patch(monkeypatch, wholesale_count=WHOLESALE_MIN_COUNT + 2, price_band_count=PRICE_BAND_MIN_COUNT + 5)
        item = _inventory_aging_action(ADMIN)
        assert item["triggered"] is True
        assert len(item["actions"]) == 2

    def test_severity_is_count_severity_of_the_max(self, monkeypatch):
        # max(25, 0) -> 25+ -> critical
        self._patch(monkeypatch, wholesale_count=25, price_band_count=0)
        item = _inventory_aging_action(ADMIN)
        assert item["severity"] == "critical"

    def test_key_and_category(self, monkeypatch):
        self._patch(monkeypatch, wholesale_count=0, price_band_count=0)
        item = _inventory_aging_action(ADMIN)
        assert item["key"] == "inventory_aging_action"
        assert item["category"] == "inventory"
        assert item["basis"] == "heuristic"
        assert item["resolve"] == {"department": "Inventory", "item_key": "wholesale", "hint": "Open Wholesale Desk and submit an offer on the flagged units."}


# ---------------------------------------------------------------------------
# Inventory: _recon_delays
# ---------------------------------------------------------------------------

class TestReconDelays:

    def test_no_match_returns_honest_no_data(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview", lambda role: _risk_overview())
        item = _recon_delays(ADMIN)
        assert item["triggered"] is False
        assert item["finding"] == "No recon backlog data available."
        assert item["category"] == "inventory"

    def test_access_denied_degrades_gracefully(self, monkeypatch):
        match = _risk_item("recon_delays", "operational", access_error="You don't have access.")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(operational=[match]))
        item = _recon_delays(SALES)
        assert item["access_error"] == "You don't have access."
        assert item["triggered"] is False

    def test_zero_severity_is_not_triggered(self, monkeypatch):
        match = _risk_item("recon_delays", "operational", count=0, severity=None)
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(operational=[match]))
        item = _recon_delays(ADMIN)
        assert item["triggered"] is False
        assert item["recommendation"] is None

    def test_real_severity_triggers(self, monkeypatch):
        match = _risk_item("recon_delays", "operational", count=12, severity="high")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(operational=[match]))
        item = _recon_delays(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "high"
        assert "12" in item["finding"]
        assert item["recommendation"] is not None


# ---------------------------------------------------------------------------
# Finance: _finance_funding_delays
# ---------------------------------------------------------------------------

class TestFinanceFundingDelays:

    def test_no_match(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview", lambda role: _risk_overview())
        item = _finance_funding_delays(ADMIN)
        assert item["triggered"] is False
        assert item["finding"] == "No funding-delay data available."

    def test_access_denied(self, monkeypatch):
        match = _risk_item("funding_delays", "financial", access_error="denied")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(financial=[match]))
        item = _finance_funding_delays(SALES)
        assert item["access_error"] == "denied"

    def test_triggered_by_severity_presence(self, monkeypatch):
        match = _risk_item("funding_delays", "financial", count=9, severity="medium")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(financial=[match]))
        item = _finance_funding_delays(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "medium"
        assert "9" in item["finding"]


# ---------------------------------------------------------------------------
# Finance: _finance_unfunded_contracts
# ---------------------------------------------------------------------------

class TestFinanceUnfundedContracts:

    def test_no_match(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview", lambda role: _risk_overview())
        item = _finance_unfunded_contracts(ADMIN)
        assert item["triggered"] is False
        assert item["basis"] == "real"

    def test_access_denied(self, monkeypatch):
        match = _risk_item("unfunded_contracts", "financial", access_error="denied")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(financial=[match]))
        item = _finance_unfunded_contracts(SALES)
        assert item["access_error"] == "denied"

    def test_below_threshold_not_triggered_even_with_severity(self, monkeypatch):
        # this rule uses its OWN count threshold, not bool(severity)
        match = _risk_item("unfunded_contracts", "financial", count=UNFUNDED_CONTRACTS_MIN_COUNT - 1, severity="low")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(financial=[match]))
        item = _finance_unfunded_contracts(ADMIN)
        assert item["triggered"] is False
        assert item["severity"] is None

    def test_at_threshold_triggers(self, monkeypatch):
        match = _risk_item("unfunded_contracts", "financial", count=UNFUNDED_CONTRACTS_MIN_COUNT, severity="medium")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(financial=[match]))
        item = _finance_unfunded_contracts(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "medium"


# ---------------------------------------------------------------------------
# Finance: _finance_negative_gross
# ---------------------------------------------------------------------------

class TestFinanceNegativeGross:

    def test_no_match(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview", lambda role: _risk_overview())
        item = _finance_negative_gross(ADMIN)
        assert item["triggered"] is False

    def test_access_denied(self, monkeypatch):
        match = _risk_item("negative_gross_deals", "financial", access_error="denied")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(financial=[match]))
        item = _finance_negative_gross(SALES)
        assert item["access_error"] == "denied"

    def test_zero_count_not_triggered(self, monkeypatch):
        match = _risk_item("negative_gross_deals", "financial", count=0, severity=None, total_loss=0)
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(financial=[match]))
        item = _finance_negative_gross(ADMIN)
        assert item["triggered"] is False

    def test_positive_count_triggers_and_reports_total_loss(self, monkeypatch):
        match = _risk_item("negative_gross_deals", "financial", count=2, severity="high", total_loss=1500.55)
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(financial=[match]))
        item = _finance_negative_gross(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "high"
        assert "1,500.55" in item["finding"]


# ---------------------------------------------------------------------------
# Finance: _finance_collections_risk
# ---------------------------------------------------------------------------

class TestFinanceCollectionsRisk:

    def test_access_denied_dict_with_error_key(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "finance_health",
                             lambda role: {"collections": {"error": "no access"}})
        item = _finance_collections_risk(SALES)
        assert item["access_error"] == "no access"
        assert item["triggered"] is False

    def test_non_dict_collections_reports_no_data(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "finance_health",
                             lambda role: {"collections": None})
        item = _finance_collections_risk(ADMIN)
        assert item["triggered"] is False
        assert item["finding"] == "No collections data available."

    def test_below_threshold_not_triggered(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "finance_health",
                             lambda role: {"collections": {"recovery_risk_count": COLLECTIONS_RISK_MIN_COUNT - 1, "total_in_queue": 40}})
        item = _finance_collections_risk(ADMIN)
        assert item["triggered"] is False
        assert item["severity"] is None

    def test_at_threshold_triggers_with_count_severity(self, monkeypatch):
        # count=5 -> _count_severity bucket 3-9 -> "medium"
        monkeypatch.setattr(readiness_recommendations, "finance_health",
                             lambda role: {"collections": {"recovery_risk_count": COLLECTIONS_RISK_MIN_COUNT, "total_in_queue": 40}})
        item = _finance_collections_risk(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "medium"
        assert f"{COLLECTIONS_RISK_MIN_COUNT} of 40" in item["finding"]


# ---------------------------------------------------------------------------
# Finance: _finance_compliance_risk
# ---------------------------------------------------------------------------

class TestFinanceComplianceRisk:

    def test_no_match(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview", lambda role: _risk_overview())
        item = _finance_compliance_risk(ADMIN)
        assert item["triggered"] is False

    def test_access_denied(self, monkeypatch):
        match = _risk_item("open_compliance_issues", "operational", access_error="denied")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(operational=[match]))
        item = _finance_compliance_risk(SALES)
        assert item["access_error"] == "denied"

    def test_triggered_by_severity_presence(self, monkeypatch):
        match = _risk_item("open_compliance_issues", "operational", count=4, severity="high")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(operational=[match]))
        item = _finance_compliance_risk(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "high"
        assert "4" in item["finding"]


# ---------------------------------------------------------------------------
# Service: _service_type_trend / _service_type_underperformance
# (real ServiceRecord ledger fixtures -- no upstream module to monkeypatch)
# ---------------------------------------------------------------------------

class TestServiceTypeTrend:

    def test_no_records_returns_empty(self):
        assert _service_type_trend() == []

    def test_a_25_percent_plus_decline_is_flagged(self):
        max_date = date(2026, 6, 1)
        recent_date = (max_date - timedelta(days=10)).isoformat()
        prior_date = (max_date - timedelta(days=200)).isoformat()

        # Prior window: 3 real "Brake Pad Replacement" records at $100 revenue each = $300.
        for i in range(SERVICE_TYPE_MIN_PRIOR_COUNT):
            _service_record(f"SRV-P{i}", prior_date, "Brake Pad Replacement", cost=100, parts_cost=0)

        # Recent window: 1 record at $50 revenue -- a real (50-300)/300 = -83.3% decline.
        _service_record("SRV-R1", recent_date, "Brake Pad Replacement", cost=50, parts_cost=0)

        flagged = _service_type_trend()
        assert len(flagged) == 1
        assert flagged[0]["service_type"] == "Brake Pad Replacement"
        assert flagged[0]["prior_count"] == SERVICE_TYPE_MIN_PRIOR_COUNT
        assert flagged[0]["recent_count"] == 1
        assert flagged[0]["delta_pct"] <= SERVICE_TYPE_DECLINE_PCT

    def test_a_mild_decline_below_threshold_is_not_flagged(self):
        max_date = date(2026, 6, 1)
        recent_date = (max_date - timedelta(days=10)).isoformat()
        prior_date = (max_date - timedelta(days=200)).isoformat()

        for i in range(SERVICE_TYPE_MIN_PRIOR_COUNT):
            _service_record(f"SRV-P{i}", prior_date, "Oil Change", cost=100, parts_cost=0)
        # A mild 10% decline -- $270 vs $300.
        _service_record("SRV-R1", recent_date, "Oil Change", cost=90, parts_cost=0)
        _service_record("SRV-R2", recent_date, "Oil Change", cost=90, parts_cost=0)
        _service_record("SRV-R3", recent_date, "Oil Change", cost=90, parts_cost=0)

        assert _service_type_trend() == []

    def test_too_few_prior_records_is_not_flagged_even_with_a_huge_decline(self):
        max_date = date(2026, 6, 1)
        recent_date = (max_date - timedelta(days=10)).isoformat()
        prior_date = (max_date - timedelta(days=200)).isoformat()

        # Only 2 prior records -- below SERVICE_TYPE_MIN_PRIOR_COUNT (3), avoids noise.
        _service_record("SRV-P1", prior_date, "Wheel Alignment", cost=100, parts_cost=0)
        _service_record("SRV-P2", prior_date, "Wheel Alignment", cost=100, parts_cost=0)
        _service_record("SRV-R1", recent_date, "Wheel Alignment", cost=1, parts_cost=0)

        assert _service_type_trend() == []

    def test_records_missing_service_date_are_excluded(self):
        ledger.add_entity(Entity(id="SRV-NODATE", entity_type=SERVICE_RECORD, attributes={
            "Description": "Oil Change", "Cost": "100",
        }))
        assert _service_type_trend() == []

    def test_flagged_list_is_sorted_worst_first(self):
        max_date = date(2026, 6, 1)
        recent_date = (max_date - timedelta(days=10)).isoformat()
        prior_date = (max_date - timedelta(days=200)).isoformat()

        # Type A: a -90% decline.
        for i in range(3):
            _service_record(f"SRV-PA{i}", prior_date, "Type A", cost=100, parts_cost=0)
        _service_record("SRV-RA1", recent_date, "Type A", cost=10, parts_cost=0)

        # Type B: a -30% decline (smaller magnitude, still flagged).
        for i in range(3):
            _service_record(f"SRV-PB{i}", prior_date, "Type B", cost=100, parts_cost=0)
        _service_record("SRV-RB1", recent_date, "Type B", cost=70 * 3, parts_cost=0)

        flagged = _service_type_trend()
        assert len(flagged) == 2
        # Most negative delta_pct first.
        assert flagged[0]["service_type"] == "Type A"
        assert flagged[0]["delta_pct"] < flagged[1]["delta_pct"]


class TestServiceTypeUnderperformance:

    def test_not_triggered_when_no_type_flagged(self):
        item = _service_type_underperformance(ADMIN)
        assert item["triggered"] is False
        assert "No real service type" in item["finding"]
        assert item["category"] == "service"

    def test_triggered_reports_the_worst_flagged_type(self):
        max_date = date(2026, 6, 1)
        recent_date = (max_date - timedelta(days=10)).isoformat()
        prior_date = (max_date - timedelta(days=200)).isoformat()
        for i in range(3):
            _service_record(f"SRV-P{i}", prior_date, "Brake Pad Replacement", cost=100, parts_cost=0)
        _service_record("SRV-R1", recent_date, "Brake Pad Replacement", cost=10, parts_cost=0)

        item = _service_type_underperformance(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "medium"
        assert "Brake Pad Replacement" in item["finding"]
        assert "Brake Pad Replacement" in item["recommendation"]
        assert len(item["all_flagged"]) == 1


# ---------------------------------------------------------------------------
# Service: _service_shop_overload
# ---------------------------------------------------------------------------

class TestServiceShopOverload:

    def test_zero_overloaded_not_triggered(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "service_health",
                             lambda role: {"technician_utilization": {"overloaded_technician_count": 0}})
        item = _service_shop_overload(ADMIN)
        assert item["triggered"] is False

    def test_at_minimum_threshold_triggers(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "service_health",
                             lambda role: {"technician_utilization": {"overloaded_technician_count": OVERLOADED_TECH_MIN}})
        item = _service_shop_overload(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "low"  # _count_severity(1) -> "low"

    def test_missing_technician_utilization_key_defaults_gracefully(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "service_health", lambda role: {})
        item = _service_shop_overload(ADMIN)
        assert item["triggered"] is False


# ---------------------------------------------------------------------------
# Service: _service_delays
# ---------------------------------------------------------------------------

class TestServiceDelays:

    def test_no_match(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview", lambda role: _risk_overview())
        item = _service_delays(ADMIN)
        assert item["triggered"] is False

    def test_access_denied(self, monkeypatch):
        match = _risk_item("service_delays", "operational", access_error="denied")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(operational=[match]))
        item = _service_delays(SALES)
        assert item["access_error"] == "denied"

    def test_below_threshold_not_triggered_even_with_severity(self, monkeypatch):
        match = _risk_item("service_delays", "operational", count=SERVICE_DELAYS_MIN_COUNT - 1, severity="low")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(operational=[match]))
        item = _service_delays(ADMIN)
        assert item["triggered"] is False

    def test_at_threshold_triggers(self, monkeypatch):
        match = _risk_item("service_delays", "operational", count=SERVICE_DELAYS_MIN_COUNT, severity="medium")
        monkeypatch.setattr(readiness_recommendations, "get_risk_center_overview",
                             lambda role: _risk_overview(operational=[match]))
        item = _service_delays(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "medium"


# ---------------------------------------------------------------------------
# Sales: _sales_show_rate
# ---------------------------------------------------------------------------

class TestSalesShowRate:

    def test_no_appointments_reports_honest_no_data(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "sales_health",
                             lambda role: {"show_rate": {"value": None, "appointments_scheduled": 0, "appointments_shown": 0}})
        item = _sales_show_rate(ADMIN)
        assert item["triggered"] is False
        assert "No scheduled appointments" in item["finding"]

    def test_below_min_appointments_not_triggered_even_with_low_rate(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "sales_health",
                             lambda role: {"show_rate": {"value": 0.2, "appointments_scheduled": SHOW_RATE_MIN_APPTS - 1, "appointments_shown": 2}})
        item = _sales_show_rate(ADMIN)
        assert item["triggered"] is False

    def test_at_or_above_threshold_not_triggered(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "sales_health",
                             lambda role: {"show_rate": {"value": SHOW_RATE_THRESHOLD, "appointments_scheduled": SHOW_RATE_MIN_APPTS, "appointments_shown": 8}})
        item = _sales_show_rate(ADMIN)
        assert item["triggered"] is False

    def test_below_threshold_with_enough_appointments_triggers(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "sales_health",
                             lambda role: {"show_rate": {"value": 0.5, "appointments_scheduled": SHOW_RATE_MIN_APPTS, "appointments_shown": 5}})
        item = _sales_show_rate(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "medium"
        assert "50.0%" in item["finding"]
        assert item["recommendation"] is not None


# ---------------------------------------------------------------------------
# Marketing: _marketing_channel_performance
# ---------------------------------------------------------------------------

class TestMarketingChannelPerformance:

    def test_no_qualifying_channel_not_triggered(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "get_channel_mix",
                             lambda: {"channels": [{"source": "Tiny", "lead_count": 1, "sold_count": 0, "conversion_rate": 0.0}]})
        item = _marketing_channel_performance(ADMIN)
        assert item["triggered"] is False
        assert str(MARKETING_MIN_LEAD_COUNT) in item["finding"]

    def test_no_over_or_under_performers_when_all_near_average(self, monkeypatch):
        channels = [
            {"source": "A", "lead_count": 20, "sold_count": 4, "conversion_rate": 20.0},
            {"source": "B", "lead_count": 20, "sold_count": 4, "conversion_rate": 20.0},
        ]
        monkeypatch.setattr(readiness_recommendations, "get_channel_mix", lambda: {"channels": channels})
        item = _marketing_channel_performance(ADMIN)
        assert item["triggered"] is False
        assert item["over_performers"] == []
        assert item["under_performers"] == []
        assert item["fleet_average_conversion_pct"] == 20.0

    def test_overperformer_flagged_above_ratio(self, monkeypatch):
        # Avg conversion = (4+4+13)/(20+20+20) *100 = 21/60*100 = 35.0
        # Channel C at 13/20=65% conversion is >= 35*1.3=45.5 -> flagged over.
        channels = [
            {"source": "A", "lead_count": 20, "sold_count": 4, "conversion_rate": 20.0},
            {"source": "B", "lead_count": 20, "sold_count": 4, "conversion_rate": 20.0},
            {"source": "C", "lead_count": 20, "sold_count": 13, "conversion_rate": 65.0},
        ]
        monkeypatch.setattr(readiness_recommendations, "get_channel_mix", lambda: {"channels": channels})
        item = _marketing_channel_performance(ADMIN)
        assert item["triggered"] is True
        assert item["severity"] == "medium"
        assert len(item["over_performers"]) == 1
        assert item["over_performers"][0]["source"] == "C"
        assert "C" in item["finding"]
        assert "Increase marketing focus/spend on C" in item["recommendation"]

    def test_underperformer_flagged_below_ratio(self, monkeypatch):
        # Avg = (4+4+0)/(20+20+20)*100 = 8/60*100 = 13.33
        # Channel C at 0% is <= 13.33*0.6 = 8.0 -> flagged under.
        channels = [
            {"source": "A", "lead_count": 20, "sold_count": 4, "conversion_rate": 20.0},
            {"source": "B", "lead_count": 20, "sold_count": 4, "conversion_rate": 20.0},
            {"source": "C", "lead_count": 20, "sold_count": 0, "conversion_rate": 0.0},
        ]
        monkeypatch.setattr(readiness_recommendations, "get_channel_mix", lambda: {"channels": channels})
        item = _marketing_channel_performance(ADMIN)
        assert item["triggered"] is True
        assert len(item["under_performers"]) == 1
        assert item["under_performers"][0]["source"] == "C"
        assert "Review or reduce spend on C" in item["recommendation"]

    def test_flagged_lists_are_capped_at_max_flagged(self, monkeypatch):
        channels = [{"source": "Base", "lead_count": 20, "sold_count": 4, "conversion_rate": 20.0}]
        for i in range(6):
            channels.append({"source": f"Over{i}", "lead_count": 20, "sold_count": 20, "conversion_rate": 100.0})
        monkeypatch.setattr(readiness_recommendations, "get_channel_mix", lambda: {"channels": channels})
        item = _marketing_channel_performance(ADMIN)
        assert len(item["over_performers"]) <= 3


# ---------------------------------------------------------------------------
# get_recommendations_overview / get_recommendations_category
# (composition-boundary testing: monkeypatch _RULE_FUNCTIONS/_RULE_CATEGORY
# directly to isolate the composition logic itself)
# ---------------------------------------------------------------------------

def _fake_rule(key, category, triggered, severity):
    def _fn(role):
        return _item(key, category, key.title(), triggered, severity,
                      f"finding for {key}", f"recommendation for {key}" if triggered else None,
                      "real", {"department": category.title()})
    return _fn


class TestGetRecommendationsOverview:

    def test_groups_items_by_category(self, monkeypatch):
        fake_functions = {
            "sales_rule": _fake_rule("sales_rule", "sales", False, None),
            "service_rule": _fake_rule("service_rule", "service", False, None),
        }
        monkeypatch.setattr(readiness_recommendations, "_RULE_FUNCTIONS", fake_functions)
        overview = get_recommendations_overview(ADMIN)
        assert set(overview["categories"].keys()) == set(CATEGORIES)
        assert len(overview["categories"]["sales"]) == 1
        assert len(overview["categories"]["service"]) == 1
        assert overview["categories"]["finance"] == []

    def test_executive_recommendations_only_high_or_critical_triggered(self, monkeypatch):
        fake_functions = {
            "low_rule": _fake_rule("low_rule", "sales", True, "low"),
            "medium_rule": _fake_rule("medium_rule", "sales", True, "medium"),
            "high_rule": _fake_rule("high_rule", "sales", True, "high"),
            "critical_rule": _fake_rule("critical_rule", "sales", True, "critical"),
            "not_triggered_rule": _fake_rule("not_triggered_rule", "sales", False, None),
        }
        monkeypatch.setattr(readiness_recommendations, "_RULE_FUNCTIONS", fake_functions)
        overview = get_recommendations_overview(ADMIN)
        exec_keys = [i["key"] for i in overview["executive_recommendations"]]
        assert "high_rule" in exec_keys
        assert "critical_rule" in exec_keys
        assert "low_rule" not in exec_keys
        assert "medium_rule" not in exec_keys
        assert "not_triggered_rule" not in exec_keys

    def test_executive_recommendations_ranked_critical_first(self, monkeypatch):
        fake_functions = {
            "high_rule": _fake_rule("high_rule", "sales", True, "high"),
            "critical_rule": _fake_rule("critical_rule", "service", True, "critical"),
        }
        monkeypatch.setattr(readiness_recommendations, "_RULE_FUNCTIONS", fake_functions)
        overview = get_recommendations_overview(ADMIN)
        exec_keys = [i["key"] for i in overview["executive_recommendations"]]
        assert exec_keys[0] == "critical_rule"
        assert exec_keys[1] == "high_rule"

    def test_kpi_counts(self, monkeypatch):
        fake_functions = {
            "a": _fake_rule("a", "sales", True, "critical"),
            "b": _fake_rule("b", "sales", True, "high"),
            "c": _fake_rule("c", "sales", True, "medium"),
            "d": _fake_rule("d", "sales", True, "low"),
            "e": _fake_rule("e", "sales", False, None),
        }
        monkeypatch.setattr(readiness_recommendations, "_RULE_FUNCTIONS", fake_functions)
        overview = get_recommendations_overview(ADMIN)
        assert overview["kpi"]["total_rules"] == 5
        assert overview["kpi"]["triggered_count"] == 4
        assert overview["kpi"]["by_severity"] == {"critical": 1, "high": 1, "medium": 1, "low": 1}

    def test_no_blended_score_is_ever_computed(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "_RULE_FUNCTIONS", {})
        overview = get_recommendations_overview(ADMIN)
        assert overview["overall_recommendation_score"] is None
        assert "no real methodology" in overview["overall_recommendation_score_note"].lower()

    def test_generated_at_is_present(self, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "_RULE_FUNCTIONS", {})
        overview = get_recommendations_overview(ADMIN)
        assert "generated_at" in overview


class TestGetRecommendationsCategory:

    def test_unknown_category_returns_error(self):
        result = get_recommendations_category(ADMIN, "bogus")
        assert "error" in result
        assert "bogus" in result["error"]

    def test_case_and_whitespace_insensitive(self, monkeypatch):
        fake_functions = {"sales_rule": _fake_rule("sales_rule", "sales", False, None)}
        fake_categories = {"sales_rule": "sales"}
        monkeypatch.setattr(readiness_recommendations, "_RULE_FUNCTIONS", fake_functions)
        monkeypatch.setattr(readiness_recommendations, "_RULE_CATEGORY", fake_categories)
        result = get_recommendations_category(ADMIN, "  SALES  ")
        assert result["category"] == "sales"
        assert len(result["items"]) == 1

    def test_filters_to_only_the_matching_category(self, monkeypatch):
        fake_functions = {
            "sales_rule": _fake_rule("sales_rule", "sales", False, None),
            "service_rule": _fake_rule("service_rule", "service", False, None),
        }
        fake_categories = {"sales_rule": "sales", "service_rule": "service"}
        monkeypatch.setattr(readiness_recommendations, "_RULE_FUNCTIONS", fake_functions)
        monkeypatch.setattr(readiness_recommendations, "_RULE_CATEGORY", fake_categories)
        result = get_recommendations_category(ADMIN, "sales")
        keys = [i["key"] for i in result["items"]]
        assert keys == ["sales_rule"]

    def test_every_real_category_is_a_valid_lookup(self):
        for category in CATEGORIES:
            result = get_recommendations_category(ADMIN, category)
            assert "error" not in result
            assert result["category"] == category


# ---------------------------------------------------------------------------
# ACL layer
# ---------------------------------------------------------------------------

class TestGetRecommendationsOverviewApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_is_allowed(self, role, monkeypatch):
        monkeypatch.setattr(readiness_recommendations, "_RULE_FUNCTIONS", {})
        result = get_recommendations_overview_api(role)
        assert "error" not in result

    def test_unknown_role_denied(self):
        result = get_recommendations_overview_api("NOT_A_REAL_ROLE")
        assert result == {"error": "You don't have access to Readiness Recommendations."}

    def test_none_role_denied(self):
        result = get_recommendations_overview_api(None)
        assert "error" in result


class TestGetRecommendationsCategoryApi:

    @pytest.mark.parametrize("role", ALL_ROLES)
    def test_every_real_role_is_allowed(self, role):
        result = get_recommendations_category_api(role, "sales")
        assert "error" not in result
        assert result["category"] == "sales"

    def test_unknown_role_denied(self):
        result = get_recommendations_category_api("NOT_A_REAL_ROLE", "sales")
        assert result == {"error": "You don't have access to Readiness Recommendations."}

    def test_bad_category_from_an_allowed_role_still_errors_on_category(self):
        result = get_recommendations_category_api(ADMIN, "bogus")
        assert "error" in result
        assert "bogus" in result["error"]
