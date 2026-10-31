"""Tests for core/finance_menu.py -- Finance's 8-item Top Menu dispatcher
(overview/deals/funding/compliance/accounting/floorplan/portfolio/payments/
collections/repossessions/gps_devices/starter_interrupt/assets/
lender_intelligence/commissions/reporting).

`_entities()`/`_funded_deal_gross()` read `core.dealeros.ledger` (the module-
level singleton bound via `from core.dealeros import ledger`) -- exercised here
against a lightweight fake ledger object rather than mocked away entirely, so
the real filtering/aggregation logic in `_entities()`/`_funded_deal_gross()`
gets genuine coverage, not just a stubbed return value.

`reporting()` calls this module's OWN `_bhph_finance_company_reports()` (a
same-module function, resolved via a bare-name call at call time) -- tested
the same way `core/network_menu.py`'s `reporting()`/`forecasts()` composition
tests were, by monkeypatching `fm._bhph_finance_company_reports` directly for
`reporting()`'s own tests, with `_bhph_finance_company_reports()` covered
separately by its own dedicated test class exercising its real math.
"""

import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.finance_menu as fm


# ---------------------------------------------------------------------------
# Fake ledger / entity helpers
# ---------------------------------------------------------------------------


class _FakeEntity:
    def __init__(self, entity_type, id, attributes=None):
        self.entity_type = entity_type
        self.id = id
        self.attributes = attributes or {}


class _FakeLedger:
    def __init__(self, entities=None):
        self._entities = {e.id: e for e in (entities or [])}

    def get_all(self):
        return self._entities


def _use_ledger(monkeypatch, entities):
    monkeypatch.setattr(fm, "ledger", _FakeLedger(entities))


def _deal(id, status=None, financing_status=None, financing_type=None,
          trade_in=None, updated_at=None, vehicle_id=None, funded_at=None):
    attrs = {
        "status": status,
        "financing_status": financing_status,
        "financing_type": financing_type,
        "trade_in": trade_in,
        "updated_at": updated_at,
        "vehicle_id": vehicle_id,
        "funded_at": funded_at,
    }
    return _FakeEntity(fm.DEAL, id, attrs)


def _vehicle(id, price=0.0, cost=0.0):
    return _FakeEntity(fm.VEHICLE, id, {"Price": price, "Cost": cost})


def _document(id, entity_id, entity_type, doc_type):
    return _FakeEntity(fm.DOCUMENT, id, {"EntityID": entity_id, "EntityType": entity_type, "DocumentType": doc_type})


# ---------------------------------------------------------------------------
# _safe_float
# ---------------------------------------------------------------------------


class TestSafeFloat:

    def test_valid_float_string(self):
        assert fm._safe_float("12.5") == 12.5

    def test_valid_int(self):
        assert fm._safe_float(7) == 7.0

    def test_none_returns_default(self):
        assert fm._safe_float(None) == 0.0

    def test_invalid_string_returns_default(self):
        assert fm._safe_float("not-a-number") == 0.0

    def test_custom_default(self):
        assert fm._safe_float(None, default=-1.0) == -1.0


# ---------------------------------------------------------------------------
# _entities
# ---------------------------------------------------------------------------


class TestEntities:

    def test_filters_by_entity_type(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _deal("DEAL-1"),
            _vehicle("VEH-1"),
            _deal("DEAL-2"),
        ])

        result = fm._entities(fm.DEAL)

        assert {e.id for e in result} == {"DEAL-1", "DEAL-2"}

    def test_empty_ledger(self, monkeypatch):
        _use_ledger(monkeypatch, [])

        assert fm._entities(fm.DEAL) == []


# ---------------------------------------------------------------------------
# _submitted_deal_aging
# ---------------------------------------------------------------------------


class TestSubmittedDealAging:

    def test_no_updated_at_skipped(self):
        deals = [_deal("DEAL-1", updated_at=None)]

        assert fm._submitted_deal_aging(deals) == []

    def test_unparseable_updated_at_skipped(self):
        deals = [_deal("DEAL-1", updated_at="not-a-timestamp")]

        assert fm._submitted_deal_aging(deals) == []

    def test_real_age_computed_from_iso_timestamp(self):
        five_days_ago = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()
        deals = [_deal("DEAL-1", updated_at=five_days_ago)]

        ages = fm._submitted_deal_aging(deals)

        assert ages == [5]

    def test_naive_timestamp_treated_as_utc(self):
        five_days_ago_naive = (datetime.now(timezone.utc) - timedelta(days=5)).replace(tzinfo=None).isoformat()
        deals = [_deal("DEAL-1", updated_at=five_days_ago_naive)]

        ages = fm._submitted_deal_aging(deals)

        assert ages == [5]

    def test_multiple_deals(self):
        now = datetime.now(timezone.utc)
        deals = [
            _deal("DEAL-1", updated_at=(now - timedelta(days=2)).isoformat()),
            _deal("DEAL-2", updated_at=(now - timedelta(days=10)).isoformat()),
        ]

        assert fm._submitted_deal_aging(deals) == [2, 10]


# ---------------------------------------------------------------------------
# _funded_deal_gross
# ---------------------------------------------------------------------------


class TestFundedDealGross:

    def test_sums_price_minus_cost_across_linked_vehicles(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _vehicle("VEH-1", price=20000.0, cost=17000.0),
            _vehicle("VEH-2", price=15000.0, cost=13500.0),
        ])
        deals = [
            _deal("DEAL-1", vehicle_id="VEH-1"),
            _deal("DEAL-2", vehicle_id="VEH-2"),
        ]

        assert fm._funded_deal_gross(deals) == pytest.approx(4500.0)

    def test_deal_with_no_matching_vehicle_contributes_zero(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        deals = [_deal("DEAL-1", vehicle_id="VEH-MISSING")]

        assert fm._funded_deal_gross(deals) == 0.0

    def test_empty_deals(self, monkeypatch):
        _use_ledger(monkeypatch, [])

        assert fm._funded_deal_gross([]) == 0.0


# ---------------------------------------------------------------------------
# overview()
# ---------------------------------------------------------------------------


class TestOverview:

    def test_full_path(self, monkeypatch):
        now = datetime.now(timezone.utc)
        deals = [
            _deal("DEAL-1", status="financing", financing_status="submitted", updated_at=(now - timedelta(days=4)).isoformat()),
            _deal("DEAL-2", status="contract", trade_in={"appraised_value": 1000}),
            _deal("DEAL-3", status="funded", trade_in={"appraised_value": 500}),
            _deal("DEAL-4", status="desking"),
        ]
        _use_ledger(monkeypatch, deals)
        monkeypatch.setattr(fm, "finance_floorplan_payoff", lambda role: {"total_exposure": 500000.0})
        monkeypatch.setattr(fm, "list_alerts_api", lambda role, status=None: {"alerts": [{"id": "a1"}, {"id": "a2"}]})

        result = fm.overview("ADMIN")

        assert result["contracts_in_transit"]["count"] == 1
        assert result["unfunded_deals"]["count"] == 1
        assert result["funding_aging_days_avg"] == 4.0
        assert result["floorplan_balance"] == 500000.0
        # DEAL-2 has a trade_in and status != funded -> counted
        # DEAL-3 has a trade_in but status == funded -> not counted
        assert result["outstanding_trade_payoffs"]["count"] == 1
        assert result["open_compliance_issues"] == 2
        assert result["compliance_access_error"] is None
        assert result["cash_flow_pipeline"] == {
            "desking": 1, "financing": 1, "contract": 1, "funded": 1, "posted": None,
        }
        assert result["finance_health"]["funding_delays_avg_days"] == 4.0
        assert result["finance_health"]["compliance_exceptions"] == 2
        assert "not_yet_tracked" in result

    def test_no_submitted_deals_gives_none_aging(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        monkeypatch.setattr(fm, "finance_floorplan_payoff", lambda role: {"total_exposure": 0.0})
        monkeypatch.setattr(fm, "list_alerts_api", lambda role, status=None: {"alerts": []})

        result = fm.overview("ADMIN")

        assert result["funding_aging_days_avg"] is None
        assert result["finance_health"]["funding_delays_avg_days"] is None

    def test_alerts_access_error_degrades_gracefully(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        monkeypatch.setattr(fm, "finance_floorplan_payoff", lambda role: {"total_exposure": 0.0})
        monkeypatch.setattr(fm, "list_alerts_api", lambda role, status=None: {"error": "denied"})

        result = fm.overview("SALES")

        assert result["open_compliance_issues"] is None
        assert result["compliance_access_error"] == "denied"
        assert result["finance_health"]["compliance_exceptions"] is None


# ---------------------------------------------------------------------------
# deals()
# ---------------------------------------------------------------------------


class TestDeals:

    def test_no_query_returns_grouped_boards(self, monkeypatch):
        _use_ledger(monkeypatch, [
            _vehicle("VEH-1", price=20000.0, cost=18000.0),
            _deal("DEAL-1", status="funded", financing_status="approved", vehicle_id="VEH-1"),
        ])
        monkeypatch.setattr(fm, "list_deals", lambda status=None: {
            "desking": [], "funded": [_FakeEntity(fm.DEAL, "DEAL-1", {"status": "funded", "vehicle_id": "VEH-1"})],
            "contract": [],
        }.get(status, []))

        result = fm.deals("ADMIN")

        assert result["funded_deals"]["count"] == 1
        assert result["funded_deals"]["deals"][0]["id"] == "DEAL-1"
        assert result["gross_analysis"]["funded_deal_gross_total"] == 2000.0
        assert "not_yet_tracked" in result

    def test_query_deal_id_prefix_returns_entity_and_related(self, monkeypatch):
        calls = {}

        def fake_get_entity_by_id(role, q):
            calls["entity_id"] = q
            return {"id": "DEAL-00001"}

        def fake_get_related_entities(role, q):
            calls["related_id"] = q
            return [{"id": "CUST-1"}]

        monkeypatch.setattr(fm, "get_entity_by_id", fake_get_entity_by_id)
        monkeypatch.setattr(fm, "get_related_entities", fake_get_related_entities)

        result = fm.deals("ADMIN", query="deal-00001")

        assert calls["entity_id"] == "DEAL-00001"
        assert calls["related_id"] == "DEAL-00001"
        assert result == {"deal": {"id": "DEAL-00001"}, "related_entities": [{"id": "CUST-1"}]}

    def test_query_deal_id_prefix_error_short_circuits(self, monkeypatch):
        related_called = []
        monkeypatch.setattr(fm, "get_entity_by_id", lambda role, q: {"error": "not found"})
        monkeypatch.setattr(fm, "get_related_entities", lambda role, q: related_called.append(q) or [])

        result = fm.deals("ADMIN", query="DEAL-99999")

        assert result == {"error": "not found"}
        assert related_called == []

    def test_free_text_query_filters_by_entity_type(self, monkeypatch):
        monkeypatch.setattr(fm, "search_entities", lambda role, query: [
            {"entity_type": fm.DEAL, "id": "DEAL-1"},
            {"entity_type": fm.VEHICLE, "id": "VEH-1"},
        ])

        result = fm.deals("ADMIN", query="some customer name")

        assert result["count"] == 1
        assert result["results"] == [{"entity_type": fm.DEAL, "id": "DEAL-1"}]


# ---------------------------------------------------------------------------
# funding()
# ---------------------------------------------------------------------------


class TestFunding:

    def test_full_path(self, monkeypatch):
        today_iso = fm._today()
        deals = [
            _deal("DEAL-1", financing_status="approved"),
            _deal("DEAL-2", financing_status="declined"),
            _deal("DEAL-3", financing_status="countered"),
            _deal("DEAL-4", financing_status="approved"),
            _deal("DEAL-5", status="funded", funded_at=f"{today_iso}T10:00:00Z"),
            _deal("DEAL-6", status="funded", funded_at="2020-01-01T10:00:00Z"),
            _deal("DEAL-7", financing_status="submitted", updated_at=(datetime.now(timezone.utc) - timedelta(days=3)).isoformat()),
        ]
        _use_ledger(monkeypatch, deals)
        monkeypatch.setattr(fm, "sales_fi_turnover_queue", lambda role: {"queue": ["DEAL-7"]})

        result = fm.funding("ADMIN")

        assert result["cit_queue"] == {"queue": ["DEAL-7"]}
        assert result["lender_responses"] == {"approved": 2, "declined": 1, "countered": 1}
        assert result["daily_funding_activity"]["count"] == 1
        assert result["funding_delays"]["submitted_count"] == 1
        assert result["funding_delays"]["avg_days_since_last_update"] == 3.0
        assert "not_yet_tracked" in result

    def test_no_submitted_deals_gives_none_avg(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        monkeypatch.setattr(fm, "sales_fi_turnover_queue", lambda role: {})

        result = fm.funding("ADMIN")

        assert result["funding_delays"]["submitted_count"] == 0
        assert result["funding_delays"]["avg_days_since_last_update"] is None


# ---------------------------------------------------------------------------
# compliance()
# ---------------------------------------------------------------------------


class TestCompliance:

    def test_full_path(self, monkeypatch):
        entities = [
            _deal("DEAL-1", status="funded"),
            _deal("DEAL-2", status="funded"),
            _deal("DEAL-3", status="desking"),
            _document("DOC-1", "DEAL-1", fm.DEAL, "Deal Jacket"),
            _document("DOC-2", "DEAL-2", fm.DEAL, "Title"),  # wrong doc type, ignored
            _document("DOC-3", "DEAL-3", fm.DEAL, "Deal Jacket"),  # not-funded deal, irrelevant to the diff
        ]
        _use_ledger(monkeypatch, entities)
        monkeypatch.setattr(fm, "list_rules_api", lambda: {"rules": [{"key": "ofac_screening"}]})
        monkeypatch.setattr(fm, "list_alerts_api", lambda role, status=None: {"alerts": [{"id": "a1"}]})
        monkeypatch.setattr(fm, "get_lending_compliance_dashboard_api", lambda role: {
            "ofac": {"unscreened_or_potential_match_count": 3},
            "form_8300": {"overdue_count": 1},
        })

        result = fm.compliance("ADMIN")

        assert result["compliance_exceptions"] == {"alerts": [{"id": "a1"}]}
        assert result["deal_jacket_audits"]["count"] == 1
        assert result["deal_jacket_audits"]["deal_ids"] == ["DEAL-2"]
        assert result["rule_catalog"] == {"rules": [{"key": "ofac_screening"}]}
        assert result["ofac_verification"] == {"unscreened_or_potential_match_count": 3}
        assert result["irs_form_8300"] == {"overdue_count": 1}

    def test_lending_compliance_non_dict_returned_verbatim_for_both_fields(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        monkeypatch.setattr(fm, "list_rules_api", lambda: {})
        monkeypatch.setattr(fm, "list_alerts_api", lambda role, status=None: {"alerts": []})
        monkeypatch.setattr(fm, "get_lending_compliance_dashboard_api", lambda role: None)

        result = fm.compliance("SALES")

        assert result["ofac_verification"] is None
        assert result["irs_form_8300"] is None

    def test_no_funded_deals_gives_empty_audit(self, monkeypatch):
        _use_ledger(monkeypatch, [_deal("DEAL-1", status="desking")])
        monkeypatch.setattr(fm, "list_rules_api", lambda: {})
        monkeypatch.setattr(fm, "list_alerts_api", lambda role, status=None: {"alerts": []})
        monkeypatch.setattr(fm, "get_lending_compliance_dashboard_api", lambda role: {})

        result = fm.compliance("ADMIN")

        assert result["deal_jacket_audits"] == {"count": 0, "deal_ids": []}


# ---------------------------------------------------------------------------
# accounting()
# ---------------------------------------------------------------------------


class TestAccounting:

    def test_full_path(self, monkeypatch):
        monkeypatch.setattr(fm, "inventory_lot_audit", lambda role: {
            "sold_without_purchase_relationship": 2, "discrepancies": ["VEH-1", "VEH-2"],
        })
        monkeypatch.setattr(fm, "get_loan_accounting_summary_api", lambda role: {"interest_income_recognized": 1000.0})
        monkeypatch.setattr(fm, "get_unposted_payments_api", lambda role: {"count": 5})
        monkeypatch.setattr(fm, "list_periods_api", lambda role: {"periods": []})
        monkeypatch.setattr(fm, "get_trial_balance_api", lambda role: {"balanced": True})
        monkeypatch.setattr(fm, "get_income_statement_api", lambda role: {"net_income": 5000.0})
        monkeypatch.setattr(fm, "get_balance_sheet_api", lambda role: {"total_assets": 10000.0})
        monkeypatch.setattr(fm, "get_reconciliation_status_api", lambda role: {"book_balance": 50000.0})

        result = fm.accounting("ADMIN")

        assert result["open_exceptions"]["count"] == 2
        assert result["open_exceptions"]["discrepancies"] == ["VEH-1", "VEH-2"]
        assert result["loan_accounting_summary"] == {"interest_income_recognized": 1000.0}
        assert result["unposted_payments"] == {"count": 5}
        assert result["accounting_periods"] == {"periods": []}
        assert result["general_ledger"]["trial_balance"] == {"balanced": True}
        assert result["general_ledger"]["income_statement"] == {"net_income": 5000.0}
        assert result["general_ledger"]["balance_sheet"] == {"total_assets": 10000.0}
        assert result["bank_reconciliation"] == {"book_balance": 50000.0}
        assert "not_yet_tracked" in result


# ---------------------------------------------------------------------------
# floorplan()
# ---------------------------------------------------------------------------


class TestFloorplan:

    def test_full_path(self, monkeypatch):
        monkeypatch.setattr(fm, "finance_floorplan_payoff", lambda role: {"total_exposure": 250000.0, "unit_count": 12})

        result = fm.floorplan("ADMIN")

        assert result["active_floorplan_units"] == {"total_exposure": 250000.0, "unit_count": 12}
        assert "not_yet_tracked" in result
        assert "curtailments" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# portfolio()
# ---------------------------------------------------------------------------


class TestPortfolio:

    def test_no_query_returns_dashboard(self, monkeypatch):
        monkeypatch.setattr(fm, "get_portfolio_dashboard_api", lambda role: {"total_loans": 315})

        assert fm.portfolio("ADMIN") == {"total_loans": 315}

    def test_fin_prefixed_query_returns_loan_detail_directly(self, monkeypatch):
        calls = []
        monkeypatch.setattr(fm, "get_loan_detail_api", lambda role, q: calls.append((role, q)) or {"loan_id": q})

        result = fm.portfolio("ADMIN", query="fin-00001")

        assert calls == [("ADMIN", "FIN-00001")]
        assert result == {"loan_id": "FIN-00001"}

    def test_free_text_query_filters_by_finance_contract_type(self, monkeypatch):
        monkeypatch.setattr(fm, "search_entities", lambda role, query: [
            {"entity_type": fm.FINANCE_CONTRACT, "id": "FIN-1"},
            {"entity_type": fm.DEAL, "id": "DEAL-1"},
        ])

        result = fm.portfolio("ADMIN", query="Smith")

        assert result["count"] == 1
        assert result["results"] == [{"entity_type": fm.FINANCE_CONTRACT, "id": "FIN-1"}]


# ---------------------------------------------------------------------------
# payments() / collections() / repossessions() / gps_devices() /
# starter_interrupt() / assets() / lender_intelligence() -- thin pass-throughs
# ---------------------------------------------------------------------------


class TestThinPassthroughItems:

    def test_payments(self, monkeypatch):
        monkeypatch.setattr(fm, "get_payments_dashboard_api", lambda role: {"total_payments": 379})
        assert fm.payments("ADMIN") == {"total_payments": 379}

    def test_collections(self, monkeypatch):
        monkeypatch.setattr(fm, "get_collections_dashboard_api", lambda role: {"total_in_queue": 65})
        assert fm.collections("ADMIN") == {"total_in_queue": 65}

    def test_repossessions(self, monkeypatch):
        monkeypatch.setattr(fm, "get_repossessions_dashboard_api", lambda role: {"referral_queue": []})
        assert fm.repossessions("ADMIN") == {"referral_queue": []}

    def test_gps_devices(self, monkeypatch):
        monkeypatch.setattr(fm, "get_device_management_dashboard_api", lambda role: {"devices": []})
        assert fm.gps_devices("ADMIN") == {"devices": []}

    def test_starter_interrupt(self, monkeypatch):
        monkeypatch.setattr(fm, "get_starter_interrupt_dashboard_api", lambda role: {"pending_warning": []})
        assert fm.starter_interrupt("ADMIN") == {"pending_warning": []}

    def test_assets(self, monkeypatch):
        monkeypatch.setattr(fm, "get_asset_portfolio_dashboard_api", lambda role: {"missing_title_count": 315})
        assert fm.assets("ADMIN") == {"missing_title_count": 315}

    def test_lender_intelligence(self, monkeypatch):
        monkeypatch.setattr(fm, "get_lender_intelligence_overview_api", lambda role: {"scorecards": []})
        assert fm.lender_intelligence("ADMIN") == {"scorecards": []}


# ---------------------------------------------------------------------------
# commissions()
# ---------------------------------------------------------------------------


class TestCommissions:

    def test_calls_with_lowercase_department_keys(self, monkeypatch):
        calls = []

        def fake(role, department=None):
            calls.append((role, department))
            return {"employees": [], "department": department}

        monkeypatch.setattr(fm, "list_employee_values_api", fake)

        result = fm.commissions("ADMIN")

        assert calls == [("ADMIN", "sales"), ("ADMIN", "finance"), ("ADMIN", "service")]
        assert result["sales_commissions_estimate"]["department"] == "sales"
        assert result["finance_commissions_estimate"]["department"] == "finance"
        assert result["service_commissions_estimate"]["department"] == "service"
        assert "note" in result
        assert "not_yet_tracked" in result


# ---------------------------------------------------------------------------
# _bhph_finance_company_reports()
# ---------------------------------------------------------------------------


class TestBhphFinanceCompanyReports:

    def _patch(self, monkeypatch, portfolio=None, accounting_summary=None, repo=None, collections=None, compliance=None):
        monkeypatch.setattr(fm, "get_portfolio_dashboard_api", lambda role: portfolio)
        monkeypatch.setattr(fm, "get_loan_accounting_summary_api", lambda role: accounting_summary)
        monkeypatch.setattr(fm, "get_repossessions_dashboard_api", lambda role: repo)
        monkeypatch.setattr(fm, "get_collections_dashboard_api", lambda role: collections)
        monkeypatch.setattr(fm, "get_lending_compliance_dashboard_api", lambda role: compliance)

    def test_full_math(self, monkeypatch):
        self._patch(
            monkeypatch,
            portfolio={
                "total_loans": 100,
                "active_loans": 90,
                "payoffs": 5,
                "delinquency_buckets": {"30_day": 5, "60_day": 3, "90_day": 2, "charged_off": 1, "repossessed": 4},
                "total_outstanding_balance": 900000.0,
                "total_amount_past_due": 15000.0,
                "disclaimer": "real, custom disclaimer text",
            },
            accounting_summary={
                "interest_income_recognized": 20000.0, "principal_reduction": 80000.0,
                "cash_collected": 100000.0, "payment_count": 365,
            },
            repo={"disposed_count": 3, "redeemed_count": 2, "total_deficiency_outstanding": 4500.0},
            collections={"total_in_queue": 65, "bucket_counts": {"7_day": 5}, "stage_counts": {}, "recovery_risk_count": 19, "contact_today_count": 4},
            compliance={
                "ofac": {"unscreened_or_potential_match_count": 46},
                "form_8300": {"overdue_count": 1, "pending_count": 0, "filed_count": 3},
            },
        )

        result = fm._bhph_finance_company_reports("ADMIN")

        pp = result["bhph_portfolio_performance_report"]
        assert pp["total_loans"] == 100
        assert pp["delinquency_rate_pct"] == 10.0
        assert pp["basis_note"] == "real, custom disclaimer text"

        yr = result["bhph_yield_report"]
        assert yr["interest_income_recognized"] == 20000.0
        assert yr["cash_collected"] == 100000.0

        col = result["charge_off_and_loss_report"]
        assert col["charged_off_loans"] == 1
        assert col["repossessed_loans"] == 4
        assert col["recovery_rate_pct"] == 40.0

        ce = result["collections_effectiveness_report"]
        assert ce["total_in_queue"] == 65
        assert ce["recovery_risk_count"] == 19

        cs = result["compliance_summary_report"]
        assert cs["ofac_unscreened_or_potential_match_count"] == 46
        assert cs["form_8300_overdue_count"] == 1

        sc = result["servicing_company_scorecard"]
        assert sc["portfolio_value"] == 900000.0
        assert sc["delinquency_rate_pct"] == 10.0
        assert sc["recovery_rate_pct"] == 40.0
        assert sc["open_compliance_items"] == 47  # 46 + 1

    def test_zero_loans_gives_none_delinquency_rate(self, monkeypatch):
        self._patch(monkeypatch, portfolio={"total_loans": 0, "delinquency_buckets": {}},
                    accounting_summary={}, repo={"disposed_count": 0, "redeemed_count": 0},
                    collections={}, compliance={})

        result = fm._bhph_finance_company_reports("ADMIN")

        assert result["bhph_portfolio_performance_report"]["delinquency_rate_pct"] is None
        assert result["charge_off_and_loss_report"]["recovery_rate_pct"] is None

    def test_missing_disclaimer_uses_default_basis_note(self, monkeypatch):
        self._patch(monkeypatch, portfolio={"total_loans": 0, "delinquency_buckets": {}},
                    accounting_summary={}, repo={"disposed_count": 0, "redeemed_count": 0},
                    collections={}, compliance={})

        result = fm._bhph_finance_company_reports("ADMIN")

        assert "may be SIMULATED or real" in result["bhph_portfolio_performance_report"]["basis_note"]

    def test_non_dict_sources_fall_back_via_num_helper(self, monkeypatch):
        self._patch(monkeypatch, portfolio=None, accounting_summary=None, repo=None, collections=None, compliance=None)

        result = fm._bhph_finance_company_reports("ADMIN")

        assert result["bhph_portfolio_performance_report"]["total_loans"] == 0
        assert result["compliance_summary_report"]["ofac_unscreened_or_potential_match_count"] == 0
        assert result["servicing_company_scorecard"]["open_compliance_items"] == 0


# ---------------------------------------------------------------------------
# reporting()
# ---------------------------------------------------------------------------


class TestReporting:

    def _patch_bhph(self, monkeypatch, value=None):
        monkeypatch.setattr(fm, "_bhph_finance_company_reports", lambda role: value if value is not None else {})

    def test_full_path(self, monkeypatch):
        vehicles = [_vehicle("VEH-1", price=20000.0, cost=17000.0)]
        deals = [
            _deal("DEAL-1", status="funded", financing_type="in_house", vehicle_id="VEH-1"),
            _deal("DEAL-2", status="funded", financing_type=None, vehicle_id=None),
            _deal("DEAL-3", financing_status="submitted", updated_at=(datetime.now(timezone.utc) - timedelta(days=6)).isoformat()),
        ]
        _use_ledger(monkeypatch, vehicles + deals)
        monkeypatch.setattr(fm, "finance_floorplan_payoff", lambda role: {"total_exposure": 100000.0})
        monkeypatch.setattr(fm, "inventory_lot_audit", lambda role: {"sold_without_purchase_relationship": 3})
        monkeypatch.setattr(fm, "readiness_predictions_api", lambda: {"departments": [
            {"department": "sales", "contracts_funded": {"tomorrow": 1}},
            {"department": "finance", "contracts_funded": {"tomorrow": 2}},
        ]})
        monkeypatch.setattr(fm, "get_department_api", lambda role, key: {"department_key": key})
        self._patch_bhph(monkeypatch, {"bhph_yield_report": {"cash_collected": 100.0}})

        result = fm.reporting("ADMIN")

        assert result["funding_reports"]["cit_count"] == 1
        assert result["funding_reports"]["avg_funding_delay_days"] == 6.0
        assert result["fi_reports"]["financing_type_breakdown"] == {"in_house": 1, "unknown": 1}
        assert result["fi_reports"]["funded_contracts_total"] == 2
        assert result["accounting_reports"]["open_variances"] == 3
        assert result["floorplan_reports"]["inventory_financing_exposure"] == 100000.0
        assert result["executive_financial_reports"]["department_gross_total"] == 3000.0
        assert result["forecasting"] == {"department": "finance", "contracts_funded": {"tomorrow": 2}}
        assert result["department_intelligence"] == {"department_key": "fi"}
        assert result["bhph_yield_report"] == {"cash_collected": 100.0}
        assert "not_yet_tracked" in result

    def test_no_finance_forecast_entry_gives_none(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        monkeypatch.setattr(fm, "finance_floorplan_payoff", lambda role: {})
        monkeypatch.setattr(fm, "inventory_lot_audit", lambda role: {})
        monkeypatch.setattr(fm, "readiness_predictions_api", lambda: {"departments": [{"department": "sales"}]})
        monkeypatch.setattr(fm, "get_department_api", lambda role, key: {})
        self._patch_bhph(monkeypatch)

        result = fm.reporting("ADMIN")

        assert result["forecasting"] is None

    def test_no_submitted_deals_gives_none_funding_delay(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        monkeypatch.setattr(fm, "finance_floorplan_payoff", lambda role: {})
        monkeypatch.setattr(fm, "inventory_lot_audit", lambda role: {})
        monkeypatch.setattr(fm, "readiness_predictions_api", lambda: {"departments": []})
        monkeypatch.setattr(fm, "get_department_api", lambda role, key: {})
        self._patch_bhph(monkeypatch)

        result = fm.reporting("ADMIN")

        assert result["funding_reports"]["cit_count"] == 0
        assert result["funding_reports"]["avg_funding_delay_days"] is None

    def test_bhph_reports_spread_into_top_level_result(self, monkeypatch):
        _use_ledger(monkeypatch, [])
        monkeypatch.setattr(fm, "finance_floorplan_payoff", lambda role: {})
        monkeypatch.setattr(fm, "inventory_lot_audit", lambda role: {})
        monkeypatch.setattr(fm, "readiness_predictions_api", lambda: {"departments": []})
        monkeypatch.setattr(fm, "get_department_api", lambda role, key: {})
        self._patch_bhph(monkeypatch, {"bhph_portfolio_performance_report": {"total_loans": 42}, "servicing_company_scorecard": {"open_compliance_items": 1}})

        result = fm.reporting("ADMIN")

        assert result["bhph_portfolio_performance_report"] == {"total_loans": 42}
        assert result["servicing_company_scorecard"] == {"open_compliance_items": 1}
