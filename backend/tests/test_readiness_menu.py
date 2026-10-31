"""Tests for core/readiness_menu.py -- Readiness's Top Menu dispatcher
(overview/business_health/data_health/readiness/forecasts/simulations/exceptions/
recommendations/strategic_planning/reporting).

Almost every function is a thin pass-through to a dedicated `*_api.py` module
(mocked at module level, same convention as every prior *_menu.py test file), with
real orchestration logic concentrated in `_connections()`, `data_health()`,
`readiness()`, `forecasts()`, `exceptions()`, `recommendations()`, and especially
`reporting()` -- which composes FIVE same-module functions (`data_health`/
`readiness`/`forecasts`/`recommendations`/`exceptions`) plus `_all_readiness()`, all
isolated here by monkeypatching them directly on the module alias (the same
"extract and isolate the composing function" pattern already used for `crm()` in
test_marketing_menu.py)."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.readiness_menu as rm


def _stub_engines(monkeypatch, **overrides):
    defaults = {
        "list_connections_api": lambda role: {"connections": []},
        "readiness_predictions_api": lambda: {"departments": []},
        "get_network_audit_api": lambda role: {"recommendations": []},
        "get_business_health_overview_api": lambda role: {},
        "get_risk_center_overview_api": lambda role: {"categories": {}},
        "get_recommendations_overview_api": lambda role: {},
        "get_enterprise_readiness_overview_api": lambda role: {},
        "get_integration_monitoring_api": lambda role: {},
        "get_data_completeness_api": lambda role: {},
        "get_data_accuracy_api": lambda role: {},
        "get_data_freshness_api": lambda role: {},
        "get_performance_readiness_overview_api": lambda role: {},
        "get_forecasts_overview_api": lambda role: {},
        "get_scenario_catalog_api": lambda role: {},
        "get_strategic_planning_overview_api": lambda role: {},
        "get_income_statement_api": lambda role: {"error": "denied"},
        "get_balance_sheet_api": lambda role: {"error": "denied"},
        "get_reconciliation_status_api": lambda role: {"error": "denied"},
        "all_departments_readiness": lambda: [],
        "department_readiness": lambda department: None,
        "predict": lambda department, horizon: None,
    }
    defaults.update(overrides)
    for name, value in defaults.items():
        monkeypatch.setattr(rm, name, value)


# ---------------------------------------------------------------------------
# _connections() / _all_readiness()
# ---------------------------------------------------------------------------


class TestConnections:

    def test_unwraps_connections_list(self, monkeypatch):
        _stub_engines(monkeypatch, list_connections_api=lambda role: {"connections": [{"id": "CONN-1"}]})

        assert rm._connections("ADMIN") == [{"id": "CONN-1"}]

    def test_returns_none_when_forbidden(self, monkeypatch):
        _stub_engines(monkeypatch, list_connections_api=lambda role: {"error": "Forbidden"})

        assert rm._connections("SALES") is None


class TestAllReadiness:

    def test_filters_falsy_entries(self, monkeypatch):
        _stub_engines(monkeypatch, all_departments_readiness=lambda: [{"department": "sales"}, None, {"department": "service"}])

        assert rm._all_readiness() == [{"department": "sales"}, {"department": "service"}]


# ---------------------------------------------------------------------------
# overview() / business_health() / strategic_planning() / simulations()
# ---------------------------------------------------------------------------


class TestOverview:

    def test_thin_passthrough(self, monkeypatch):
        _stub_engines(monkeypatch, get_enterprise_readiness_overview_api=lambda role: {"heatmap": []})

        assert rm.overview("ADMIN") == {"heatmap": []}


class TestBusinessHealth:

    def test_thin_passthrough(self, monkeypatch):
        _stub_engines(monkeypatch, get_business_health_overview_api=lambda role: {"sales": {}})

        assert rm.business_health("ADMIN") == {"sales": {}}


class TestStrategicPlanning:

    def test_thin_passthrough(self, monkeypatch):
        _stub_engines(monkeypatch, get_strategic_planning_overview_api=lambda role: {"objectives": []})

        assert rm.strategic_planning("ADMIN") == {"objectives": []}


class TestSimulations:

    def test_full_path(self, monkeypatch):
        _stub_engines(monkeypatch, get_scenario_catalog_api=lambda role: {"scenarios": ["marketing_lead_volume"]})

        result = rm.simulations("ADMIN")

        assert result["scenario_catalog"] == {"scenarios": ["marketing_lead_volume"]}
        assert "POST /readiness-scenarios/" in result["note"]


# ---------------------------------------------------------------------------
# data_health()
# ---------------------------------------------------------------------------


class TestDataHealth:

    def test_forbidden_short_circuits(self, monkeypatch):
        _stub_engines(monkeypatch, list_connections_api=lambda role: {"error": "Forbidden"})

        assert rm.data_health("SALES") == {"error": "Forbidden"}

    def test_full_path(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            list_connections_api=lambda role: {"connections": [
                {"id": "CONN-1", "name": "DMS Feed", "connection_type": "api", "department": "sales", "status": "connected", "last_synced_at": "t1", "last_test_at": "t2", "error_message": None},
                {"id": "CONN-2", "name": "Bad Feed", "connection_type": "csv", "department": "service", "status": "error", "error_message": "timeout"},
                {"id": "CONN-3", "name": "Pending Feed", "connection_type": "api", "department": "finance", "status": "pending"},
            ]},
            get_integration_monitoring_api=lambda role: {"by_category": {}},
            get_data_completeness_api=lambda role: {"missing_vin": 0},
            get_data_accuracy_api=lambda role: {"duplicates": 0},
            get_data_freshness_api=lambda role: {"last_sync": None},
            predict=lambda department, horizon: {
                "sales": {"factors": {"completeness": 0.85}, "sample_size": 120, "basis": "ledger"},
                "service": None,
            }.get(department),
        )
        monkeypatch.setattr(rm, "PREDICTION_DEPARTMENTS", ["sales", "service"])

        result = rm.data_health("ADMIN")

        assert result["connected_systems"]["count"] == 3
        assert result["api_status"] == {"connected": 1, "error": 1, "pending": 1}
        assert result["sync_health"] == {"error_count": 1, "connected_count": 1, "pending_count": 1}
        assert len(result["data_integrity"]["connections_with_errors"]) == 1
        assert result["data_integrity"]["connections_with_errors"][0]["id"] == "CONN-2"
        assert result["historical_coverage"] == {"sales": {"completeness_pct": 85.0, "sample_size": 120, "basis": "ledger"}}
        assert result["integration_monitoring"] == {"by_category": {}}
        assert result["data_completeness"] == {"missing_vin": 0}
        assert result["data_accuracy"] == {"duplicates": 0}
        assert result["data_freshness"] == {"last_sync": None}
        assert "operations" in result["not_yet_tracked"]["missing_data"]


# ---------------------------------------------------------------------------
# readiness()
# ---------------------------------------------------------------------------


class TestReadiness:

    def test_full_path(self, monkeypatch):
        monkeypatch.setattr(rm, "PREDICTION_DEPARTMENTS", ["sales", "service", "finance"])
        _stub_engines(
            monkeypatch,
            department_readiness=lambda department: {
                "sales": {"confidence_pct": 95.0, "threshold": 90, "ready": True, "basis": "ledger"},
                "service": {"confidence_pct": 70.0, "threshold": 90, "ready": False, "basis": "blended"},
                "finance": None,
            }.get(department),
            get_performance_readiness_overview_api=lambda role: {"sales": {"goal": 120}},
        )

        result = rm.readiness("ADMIN")

        assert result["goal_tracking"] == {"sales": {"goal": 120}}
        scores = result["data_confidence_scores"]
        assert len(scores) == 2  # finance skipped -- department_readiness returned None
        assert scores[0] == {
            "department": "sales", "current_score_pct": 95.0, "target_score_pct": 90,
            "variance_pct": 5.0, "status": "At/Above Target", "risk_factors": [],
        }
        assert scores[1]["status"] == "Below Target"
        assert scores[1]["variance_pct"] == -20.0
        assert "blended" in scores[1]["risk_factors"][0]
        assert "uncovered_departments" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# forecasts()
# ---------------------------------------------------------------------------


class TestForecasts:

    def test_full_path(self, monkeypatch):
        monkeypatch.setattr(rm, "HORIZONS", ["tomorrow", "week"])
        _stub_engines(
            monkeypatch,
            readiness_predictions_api=lambda: {"departments": [
                {"department": "sales", "predictions": [
                    {"department": "sales", "horizon": "tomorrow", "metric": "units_sold", "predicted_value": 2, "unit": "units", "confidence_pct": 90, "basis": "ledger"},
                    {"department": "sales", "horizon": "week", "metric": "units_sold", "predicted_value": 10, "unit": "units", "confidence_pct": 85, "basis": "ledger"},
                ]},
            ]},
            get_forecasts_overview_api=lambda role: {"sales": {}},
        )

        result = rm.forecasts("ADMIN")

        assert result["forecasts_by_horizon"]["tomorrow"] == [{
            "department": "sales", "metric": "units_sold", "predicted_value": 2,
            "unit": "units", "confidence_pct": 90, "basis": "ledger",
        }]
        assert len(result["forecasts_by_horizon"]["week"]) == 1
        assert result["department_forecasts"] == {"sales": {}}
        assert "marketing_forecast" in result["not_yet_tracked"]

    def test_setdefault_handles_horizon_not_in_initial_list(self, monkeypatch):
        monkeypatch.setattr(rm, "HORIZONS", ["tomorrow"])
        _stub_engines(monkeypatch, readiness_predictions_api=lambda: {"departments": [
            {"department": "sales", "predictions": [
                {"department": "sales", "horizon": "quarter", "metric": "units_sold", "predicted_value": 40, "unit": "units", "confidence_pct": 70, "basis": "industry_estimate"},
            ]},
        ]})

        result = rm.forecasts("ADMIN")

        assert result["forecasts_by_horizon"]["quarter"][0]["predicted_value"] == 40


# ---------------------------------------------------------------------------
# exceptions()
# ---------------------------------------------------------------------------


class TestExceptions:

    def test_full_path(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            all_departments_readiness=lambda: [
                {"department": "sales", "ready": True},
                {"department": "service", "ready": False},
                None,
            ],
            get_risk_center_overview_api=lambda role: {"categories": {"critical": []}},
        )

        result = rm.exceptions("ADMIN")

        assert result["risk_center"] == {"categories": {"critical": []}}
        assert result["readiness_drops"]["count"] == 1
        assert result["readiness_drops"]["departments"] == [{"department": "service", "ready": False}]
        assert "forecast_variances" in result["not_yet_tracked"]


# ---------------------------------------------------------------------------
# recommendations()
# ---------------------------------------------------------------------------


class TestRecommendations:

    def test_network_audit_success(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            get_recommendations_overview_api=lambda role: {
                "categories": {"sales": []}, "executive_recommendations": [{"id": 1}],
                "kpi": {}, "overall_recommendation_score": 80, "overall_recommendation_score_note": "note",
                "generated_at": "t",
            },
            get_network_audit_api=lambda role: {"recommendations": [{"id": "rec1"}]},
        )

        result = rm.recommendations("ADMIN")

        assert result["categories"] == {"sales": []}
        assert result["executive_recommendations"] == [{"id": 1}]
        assert result["overall_recommendation_score"] == 80
        assert result["network_audit_recommendations"] == [{"id": "rec1"}]
        assert result["network_audit_note"] is None

    def test_network_audit_denied(self, monkeypatch):
        _stub_engines(
            monkeypatch,
            get_recommendations_overview_api=lambda role: {},
            get_network_audit_api=lambda role: {"error": "Forbidden"},
        )

        result = rm.recommendations("SALES")

        assert result["network_audit_recommendations"] == []
        assert result["network_audit_note"] == "Forbidden"


# ---------------------------------------------------------------------------
# reporting()
# ---------------------------------------------------------------------------


class TestReporting:

    def _compose(self, monkeypatch, reconciliation_ok=True, income_statement_ok=True):
        monkeypatch.setattr(rm, "data_health", lambda role: {
            "connected_systems": {"count": 5}, "historical_coverage": {"sales": {}},
        })
        monkeypatch.setattr(rm, "readiness", lambda role: {"data_confidence_scores": [
            {"department": "sales", "status": "At/Above Target"},
            {"department": "service", "status": "Below Target"},
        ]})
        monkeypatch.setattr(rm, "forecasts", lambda role: {
            "department_forecasts": {"sales": {}}, "forecasts_by_horizon": {"tomorrow": []},
        })
        monkeypatch.setattr(rm, "recommendations", lambda role: {
            "executive_recommendations": [{"id": f"R{i}"} for i in range(1, 7)],
            "categories": {"sales": [
                {"triggered": True, "severity": "medium", "id": "G1"},
                {"triggered": True, "severity": "low", "id": "G2"},
                {"triggered": False, "severity": "high", "id": "G3"},
                {"triggered": True, "severity": "high", "id": "G4"},
            ]},
        })
        monkeypatch.setattr(rm, "exceptions", lambda role: {"risk_center": {"categories": {
            "critical": [{"count": 5, "id": "E1"}, {"count": 0, "id": "E2"}],
            "financial": [{"count": 3, "id": "E3"}],
        }}})
        monkeypatch.setattr(rm, "_all_readiness", lambda: [
            {"confidence_pct": 90.0, "ready": True},
            {"confidence_pct": 70.0, "ready": False},
        ])

        income_statement = (
            {"revenue": {"total": 500000.0}, "net_income": 80000.0}
            if income_statement_ok else {"error": "Forbidden"}
        )
        reconciliation = {"book_balance": 42000.0} if reconciliation_ok else {"error": "Forbidden"}
        _stub_engines(
            monkeypatch,
            get_income_statement_api=lambda role: income_statement,
            get_balance_sheet_api=lambda role: {"assets": {"lines": [{"account": "Cash", "balance": 40000.0}]}},
            get_reconciliation_status_api=lambda role: reconciliation,
        )

    def test_full_path(self, monkeypatch):
        self._compose(monkeypatch)

        result = rm.reporting("ADMIN")

        assert result["readiness_reports"]["target_achievement"] == {"at_or_above_target": 1, "below_target": 1}
        dashboard = result["dealer_principal_dashboard"]
        assert dashboard["revenue"] == 500000.0
        assert dashboard["net_profit"] == 80000.0
        assert dashboard["cash_position"] == 42000.0  # reconciliation's book_balance, not the balance-sheet fallback
        assert dashboard["readiness_score_pct"] == 80.0
        assert "not_applicable" in result["group_dashboard"]

        board = result["board_investor_report"]
        assert board["forecasts"] == {"sales": {}}
        assert [e["id"] for e in board["top_exceptions"]] == ["E1", "E3"]
        assert len(board["top_recommendations"]) == 5
        assert [g["id"] for g in board["growth_opportunities"]["items"]] == ["G1", "G2"]
        assert board["growth_opportunities"]["count"] == 2
        assert board["overall_readiness_pct"] == 80.0

        assert result["data_quality_reports"] == {"connected_systems_count": 5, "historical_coverage": {"sales": {}}}
        assert result["forecast_reports"]["future_outlook"] == {"tomorrow": []}
        assert result["risk_reports"]["operational_deficits"] == [{"confidence_pct": 70.0, "ready": False}]
        assert result["executive_reports"] == {"business_readiness_pct": 80.0, "forecast_confidence_pct": 80.0}
        assert result["department_intelligence"] == rm._DI_GAP_NOTE

    def test_income_statement_error_and_balance_sheet_fallback(self, monkeypatch):
        self._compose(monkeypatch, reconciliation_ok=False, income_statement_ok=False)

        result = rm.reporting("SALES")

        dashboard = result["dealer_principal_dashboard"]
        assert dashboard["revenue"] is None
        assert dashboard["net_profit"] is None
        assert dashboard["cash_position"] == 40000.0  # falls back to the balance sheet's Cash line
