"""
Tests for core/business_health.py / core/business_health_api.py -- Readiness'
"Business Health" composition layer: 5 real per-department KPI sections (Sales,
Service, Finance, Marketing, Inventory) built entirely from already-real functions
in other modules, plus business_health_api.py's own deliberately-broad ACL gate
("is this a real role at all") that lets each composed sub-signal's own, narrower
ACL (Collections/Portfolio Quality, Marketing ROI) degrade gracefully underneath it.

This module makes zero graph mutations of its own -- it's a pure read/composition
layer. The one dependency that DOES mutate (core.appointments.create_appointment/
update_status, used here only as a real fixture-builder for Sales' show_rate) is
patched not to persist, same "patch save_graph at the module that actually calls
it" convention every other cross-module test file in this suite already follows.

Run from backend/ with `pytest`.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import LEAD, DEAL, VEHICLE, WEBSITE, WEBSITE_ANALYTICS_EVENT
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

from core import appointments as appointments_mod
from core.appointments import create_appointment, update_status

from core import business_health
from core import business_health_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(appointments_mod, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------

def _lead(lead_id):
    ledger.add_entity(Entity(id=lead_id, entity_type=LEAD, attributes={}))


def _vehicle(vehicle_id, price, cost):
    ledger.add_entity(Entity(id=vehicle_id, entity_type=VEHICLE, attributes={
        "Price": str(price),
        "Cost": str(cost),
    }))


def _funded_deal(deal_id, vehicle_id):
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes={
        "status": "funded",
        "vehicle_id": vehicle_id,
    }))


def _submitted_deal(deal_id, days_ago):
    updated_at = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()
    ledger.add_entity(Entity(id=deal_id, entity_type=DEAL, attributes={
        "financing_status": "submitted",
        "updated_at": updated_at,
    }))


def _sales_appointment(scheduled_start, shown=False):
    appt = create_appointment(
        department="Sales",
        appointment_type="showroom_visit",
        scheduled_start=scheduled_start,
        created_by="EMP-1",
        customer_id=None,
        lead_id=None,
    )
    if shown:
        update_status(appt.id, "arrived", "EMP-1")
    return appt.id


def _website(site_id):
    ledger.add_entity(Entity(id=site_id, entity_type=WEBSITE, attributes={
        "created_at": "2026-01-01T00:00:00",
        "status": "draft",
    }))


def _analytics_event(event_id, website_id, is_bot=False):
    ledger.add_entity(Entity(id=event_id, entity_type=WEBSITE_ANALYTICS_EVENT, attributes={
        "WebsiteID": website_id,
        "PageKey": "home",
        "Timestamp": "2026-01-01T00:00:00",
        "IsBot": is_bot,
        "BotName": "GPTBot" if is_bot else None,
    }))


# ---------------------------------------------------------------------------
# Sales Health
# ---------------------------------------------------------------------------

class TestSalesHealth:

    def test_empty_ledger_returns_sensible_defaults_with_no_crash(self):
        result = business_health.sales_health(ADMIN)

        assert result["lead_volume"] == {"value": 0, "basis": "real"}
        assert result["show_rate"]["value"] is None
        assert result["show_rate"]["appointments_scheduled"] == 0
        assert result["show_rate"]["appointments_shown"] == 0
        assert result["close_rate"]["value"] is None
        assert result["gross_profit"]["value"] == 0.0
        assert result["pipeline_coverage"]["active_pipeline_count"] == 0
        assert "coverage_ratio" in result["pipeline_coverage"]["not_yet_tracked"]

    def test_lead_volume_counts_every_real_lead(self):
        _lead("LEAD-1")
        _lead("LEAD-2")
        _lead("LEAD-3")

        result = business_health.sales_health(ADMIN)

        assert result["lead_volume"]["value"] == 3

    def test_show_rate_counts_arrived_and_completed_appointments_as_shown(self):
        _sales_appointment("2026-01-01T10:00:00", shown=True)
        _sales_appointment("2026-01-02T10:00:00", shown=False)

        result = business_health.sales_health(ADMIN)

        assert result["show_rate"]["appointments_scheduled"] == 2
        assert result["show_rate"]["appointments_shown"] == 1
        assert result["show_rate"]["value"] == 0.5

    def test_show_rate_completed_status_also_counts_as_shown(self):
        appt_id = _sales_appointment("2026-01-01T10:00:00", shown=False)
        update_status(appt_id, "arrived", "EMP-1")
        update_status(appt_id, "completed", "EMP-1")

        result = business_health.sales_health(ADMIN)

        assert result["show_rate"]["appointments_shown"] == 1
        assert result["show_rate"]["value"] == 1.0

    def test_gross_profit_sums_price_minus_cost_across_funded_deals_only(self):
        _vehicle("VEH-1", price=30000, cost=25000)
        _funded_deal("DEAL-1", "VEH-1")

        _vehicle("VEH-2", price=20000, cost=19000)
        # Unfunded deal -- should NOT contribute to gross profit.
        ledger.add_entity(Entity(id="DEAL-2", entity_type=DEAL, attributes={
            "status": "desking",
            "vehicle_id": "VEH-2",
        }))

        result = business_health.sales_health(ADMIN)

        assert result["gross_profit"]["value"] == 5000.0

    def test_service_appointments_are_not_counted_toward_sales_show_rate(self):
        create_appointment(
            department="Service",
            appointment_type="service",
            scheduled_start="2026-01-01T10:00:00",
            created_by="EMP-1",
            customer_id=None,
            lead_id=None,
        )

        result = business_health.sales_health(ADMIN)

        assert result["show_rate"]["appointments_scheduled"] == 0
        assert result["show_rate"]["value"] is None

    def test_runs_cleanly_for_every_real_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            result = business_health.sales_health(role)
            assert "lead_volume" in result


# ---------------------------------------------------------------------------
# Service Health
# ---------------------------------------------------------------------------

class TestServiceHealth:

    def test_empty_ledger_returns_sensible_defaults_with_no_crash(self):
        result = business_health.service_health(ADMIN)

        assert result["ro_volume"]["total"] == 0
        assert result["ro_volume"]["basis"] == "real"
        assert result["technician_utilization"]["basis"] == "heuristic"
        assert "ASSUMED 8-hour/day capacity" in result["technician_utilization"]["note"]
        assert result["customer_retention"]["basis"] == "real"
        assert result["shop_capacity"]["basis"] == "real"

    def test_composes_real_ro_volume_from_service_overview(self, monkeypatch):
        monkeypatch.setattr(business_health, "service_overview", lambda role: {
            "repair_orders_total": 42,
            "repair_orders_open": 7,
            "repair_orders_by_status": {"Completed": 35, "Open": 7},
        })

        result = business_health.service_health(ADMIN)

        assert result["ro_volume"] == {
            "total": 42,
            "open": 7,
            "by_status": {"Completed": 35, "Open": 7},
            "basis": "real",
        }

    def test_composes_real_technician_utilization_and_shop_capacity_from_one_shared_call(self, monkeypatch):
        capacity = {
            "technician_count": 5,
            "open_ro_count": 12,
            "unassigned_ro_count": 2,
            "avg_open_ros_per_technician": 2.4,
            "avg_utilization_pct_today": 63.5,
            "overloaded_technician_count": 1,
        }
        monkeypatch.setattr(business_health, "get_shop_capacity", lambda: capacity)

        result = business_health.service_health(ADMIN)

        assert result["technician_utilization"]["avg_utilization_pct_today"] == 63.5
        assert result["technician_utilization"]["overloaded_technician_count"] == 1
        assert result["technician_utilization"]["technician_count"] == 5
        # shop_capacity carries the whole real dict through, spread, plus its own note.
        assert result["shop_capacity"]["technician_count"] == 5
        assert result["shop_capacity"]["open_ro_count"] == 12
        assert result["shop_capacity"]["basis"] == "real"

    def test_composes_real_customer_retention(self, monkeypatch):
        monkeypatch.setattr(business_health, "get_customer_retention_reporting", lambda: {
            "customers_with_service_history": 120,
            "avg_visits_per_year": 1.8,
            "lost_customers": {"count": 9},
            "declined_services": {"count": 3, "total_value": 4500.0},
        })

        result = business_health.service_health(ADMIN)

        assert result["customer_retention"]["customers_with_service_history"] == 120
        assert result["customer_retention"]["avg_visits_per_year"] == 1.8
        assert result["customer_retention"]["lost_customers"] == {"count": 9}

    def test_runs_cleanly_for_every_real_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            result = business_health.service_health(role)
            assert "ro_volume" in result


# ---------------------------------------------------------------------------
# Finance Health
# ---------------------------------------------------------------------------

class TestFinanceHealth:

    def test_empty_ledger_returns_sensible_defaults_with_no_crash(self):
        result = business_health.finance_health(ADMIN)

        assert result["funding_time"]["avg_days_in_transit"] is None
        assert result["funding_time"]["contracts_in_transit"] == 0
        assert result["funding_time"]["basis"] == "heuristic"
        assert "no distinct submitted-to-lender timestamp" in result["funding_time"]["note"]
        assert "contract_accuracy" in result["contract_accuracy"]["not_yet_tracked"]

    def test_funding_time_is_a_real_heuristic_off_submitted_deal_aging(self):
        _submitted_deal("DEAL-1", days_ago=10)
        _submitted_deal("DEAL-2", days_ago=20)

        result = business_health.finance_health(ADMIN)

        assert result["funding_time"]["contracts_in_transit"] == 2
        # Real day-count math -- within a tolerance for wall-clock drift during the test run.
        assert 14.0 <= result["funding_time"]["avg_days_in_transit"] <= 16.0

    def test_only_submitted_deals_count_toward_funding_time(self):
        _submitted_deal("DEAL-1", days_ago=10)
        ledger.add_entity(Entity(id="DEAL-2", entity_type=DEAL, attributes={
            "financing_status": "approved",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }))

        result = business_health.finance_health(ADMIN)

        assert result["funding_time"]["contracts_in_transit"] == 1

    def test_collections_and_portfolio_quality_pass_through_real_denial_for_a_denied_role(self):
        result = business_health.finance_health(SALES)

        assert result["collections"] == {"error": "You don't have access to Collections"}
        assert result["portfolio_quality"] == {"error": "You don't have access to Loan Servicing / Portfolio"}

    def test_collections_and_portfolio_quality_succeed_for_an_allowed_role(self):
        result = business_health.finance_health(ADMIN)

        assert "error" not in result["collections"]
        assert "total_in_queue" in result["collections"]
        assert "error" not in result["portfolio_quality"]
        assert "total_loans" in result["portfolio_quality"]

    def test_runs_cleanly_for_every_real_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            result = business_health.finance_health(role)
            assert "funding_time" in result


# ---------------------------------------------------------------------------
# Marketing Health
# ---------------------------------------------------------------------------

class TestMarketingHealth:

    def test_empty_ledger_returns_sensible_defaults_with_no_crash(self):
        result = business_health.marketing_health(ADMIN)

        assert result["lead_volume"] == {
            "value": 0,
            "basis": "real",
            "note": "Same real Lead population Sales Health's lead_volume counts.",
        }
        assert result["website_traffic"]["total_page_views"] == 0
        assert result["website_traffic"]["site_count"] == 0
        assert result["website_traffic"]["sites_with_recorded_traffic"] == 0

    def test_lead_volume_matches_sales_healths_own_lead_volume(self):
        _lead("LEAD-1")
        _lead("LEAD-2")

        marketing = business_health.marketing_health(ADMIN)
        sales = business_health.sales_health(ADMIN)

        assert marketing["lead_volume"]["value"] == sales["lead_volume"]["value"] == 2

    def test_website_traffic_aggregates_real_analytics_events_across_every_site(self):
        _website("SITE-1")
        _analytics_event("EVT-1", "SITE-1", is_bot=False)
        _analytics_event("EVT-2", "SITE-1", is_bot=True)

        _website("SITE-2")
        _analytics_event("EVT-3", "SITE-2", is_bot=False)

        result = business_health.marketing_health(ADMIN)
        traffic = result["website_traffic"]

        assert traffic["site_count"] == 2
        assert traffic["total_page_views"] == 3
        assert traffic["human_views"] == 2
        assert traffic["bot_views"] == 1
        assert traffic["sites_with_recorded_traffic"] == 2

    def test_a_site_with_zero_events_is_not_counted_as_having_traffic(self):
        _website("SITE-1")
        _website("SITE-2")
        _analytics_event("EVT-1", "SITE-1", is_bot=False)

        result = business_health.marketing_health(ADMIN)
        traffic = result["website_traffic"]

        assert traffic["site_count"] == 2
        assert traffic["total_page_views"] == 1
        assert traffic["sites_with_recorded_traffic"] == 1

    def test_roi_passes_through_real_denial_for_a_denied_role(self):
        result = business_health.marketing_health(SERVICE)

        assert result["roi"] == {"error": "You don't have access to marketing attribution data"}

    def test_roi_succeeds_for_an_allowed_role(self):
        result = business_health.marketing_health(ADMIN)

        assert "error" not in result["roi"]
        assert "channel_mix" in result["roi"]

    def test_campaign_performance_is_composed_from_marketing_menus_campaigns(self, monkeypatch):
        monkeypatch.setattr(business_health, "_marketing_campaigns", lambda role: {"stub": "campaign-data"})

        result = business_health.marketing_health(ADMIN)

        assert result["campaign_performance"] == {"stub": "campaign-data"}

    def test_runs_cleanly_for_every_real_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            result = business_health.marketing_health(role)
            assert "lead_volume" in result


# ---------------------------------------------------------------------------
# Inventory Health
# ---------------------------------------------------------------------------

class TestInventoryHealth:

    def test_empty_ledger_returns_sensible_defaults_with_no_crash(self):
        result = business_health.inventory_health(ADMIN)

        assert "turn_rate" in result
        assert "aging" in result
        assert "recon_time" in result
        assert "days_supply" in result
        assert result["recon_time"]["basis"] == "real"

    def test_composes_real_aging_and_feeds_its_average_into_turn_rate(self, monkeypatch):
        aging = {"average_days_in_stock": 73.0, "aged_buckets": {"91+ days": 2}}
        turn_rate = {"annualized_turn_rate": 5.0, "basis": "simulated"}
        days_supply = {"market_days_supply": 61.2, "basis": "simulated"}

        captured = {}

        def fake_get_simulated_turn_rate(avg_days_in_stock=None):
            captured["avg_days_in_stock"] = avg_days_in_stock
            return turn_rate

        monkeypatch.setattr(business_health, "get_simulated_aging_summary", lambda: aging)
        monkeypatch.setattr(business_health, "get_simulated_turn_rate", fake_get_simulated_turn_rate)
        monkeypatch.setattr(business_health, "get_simulated_market_days_supply", lambda: days_supply)

        result = business_health.inventory_health(ADMIN)

        assert result["aging"] == aging
        assert result["turn_rate"] == turn_rate
        assert result["days_supply"] == days_supply
        # Confirms inventory_health() actually threads aging's own average through
        # to the turn-rate call, rather than letting it recompute independently.
        assert captured["avg_days_in_stock"] == 73.0

    def test_composes_real_recon_time_from_operations_menus_recon_reporting(self, monkeypatch):
        monkeypatch.setattr(business_health, "_recon_reporting", lambda: {
            "avg_checklist_completion_pct": 42.5,
            "vehicles_fully_recon_complete": 3,
            "vehicles_with_zero_recon_progress": 11,
            "used_unsold_count": 20,
            "note": "a real recon note",
        })

        result = business_health.inventory_health(ADMIN)

        assert result["recon_time"]["avg_checklist_completion_pct"] == 42.5
        assert result["recon_time"]["vehicles_fully_recon_complete"] == 3
        assert result["recon_time"]["vehicles_with_zero_recon_progress"] == 11
        assert result["recon_time"]["used_unsold_count"] == 20
        assert result["recon_time"]["note"] == "a real recon note"
        assert result["recon_time"]["basis"] == "real"

    def test_runs_cleanly_for_every_real_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            result = business_health.inventory_health(role)
            assert "turn_rate" in result


# ---------------------------------------------------------------------------
# Overview -- composes all 5, no fabricated blended score
# ---------------------------------------------------------------------------

class TestGetBusinessHealthOverview:

    def test_composes_all_five_departments_with_no_blended_score(self):
        result = business_health.get_business_health_overview(ADMIN)

        assert set(result.keys()) == {
            "sales", "service", "finance", "marketing", "inventory",
            "overall_score", "overall_score_note", "generated_at",
        }
        assert result["overall_score"] is None
        assert "no single blended health score" in result["overall_score_note"].lower()

    def test_each_department_section_matches_its_own_direct_function_call(self):
        _lead("LEAD-1")

        result = business_health.get_business_health_overview(ADMIN)

        assert result["sales"]["lead_volume"]["value"] == business_health.sales_health(ADMIN)["lead_volume"]["value"]
        assert result["marketing"]["lead_volume"]["value"] == business_health.marketing_health(ADMIN)["lead_volume"]["value"]

    def test_generated_at_is_a_real_iso_timestamp(self):
        result = business_health.get_business_health_overview(ADMIN)

        # Should parse cleanly as a real ISO-8601 timestamp.
        datetime.fromisoformat(result["generated_at"])

    def test_runs_cleanly_for_every_real_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            result = business_health.get_business_health_overview(role)
            assert result["overall_score"] is None


# ---------------------------------------------------------------------------
# core/business_health_api.py -- the deliberately-broad "is this a real role"
# gate, on top of each sub-signal's own real, narrower ACL.
# ---------------------------------------------------------------------------

class TestBusinessHealthApi:

    def test_get_overview_api_denies_an_unknown_role(self):
        result = business_health_api.get_business_health_overview_api("NOT_A_REAL_ROLE")

        assert result == {"error": "You don't have access to Business Health data."}

    def test_get_overview_api_succeeds_for_every_real_role(self):
        for role in (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE):
            result = business_health_api.get_business_health_overview_api(role)
            assert "error" not in result
            assert "sales" in result

    def test_get_department_api_denies_an_unknown_role_before_dispatching(self):
        result = business_health_api.get_business_health_department_api("NOT_A_REAL_ROLE", "sales")

        assert result == {"error": "You don't have access to Business Health data."}

    def test_get_department_api_dispatches_to_every_real_department(self):
        expected_first_keys = {
            "sales": "lead_volume",
            "service": "ro_volume",
            "finance": "funding_time",
            "marketing": "lead_volume",
            "inventory": "turn_rate",
        }
        for department, first_key in expected_first_keys.items():
            result = business_health_api.get_business_health_department_api(ADMIN, department)
            assert first_key in result

    def test_get_department_api_dispatch_is_case_insensitive(self):
        upper = business_health_api.get_business_health_department_api(ADMIN, "SALES")
        mixed = business_health_api.get_business_health_department_api(ADMIN, "SaLeS")

        assert "lead_volume" in upper
        assert "lead_volume" in mixed

    def test_get_department_api_rejects_an_unknown_department_with_the_real_message(self):
        result = business_health_api.get_business_health_department_api(ADMIN, "bogus")

        assert result == {
            "error": "Unknown department 'bogus' -- expected one of "
                     "['finance', 'inventory', 'marketing', 'sales', 'service']."
        }

    def test_get_department_api_handles_a_none_department_gracefully(self):
        result = business_health_api.get_business_health_department_api(ADMIN, None)

        assert "error" in result
        assert "Unknown department 'None'" in result["error"]
