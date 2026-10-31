"""Tests for core/platform_metrics.py -- the real, in-memory, per-process
request/error/latency counters grouped by NXTDeal service (Infrastructure
& Platform Operations rebuild).

_metrics is a bare module-level defaultdict with no reset() -- cleared in
place via an autouse fixture rather than requiring a fixture method that
doesn't exist on this module."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import pytest

import core.platform_metrics as pm


@pytest.fixture(autouse=True)
def fresh_metrics():
    pm._metrics.clear()
    yield
    pm._metrics.clear()


@pytest.fixture(autouse=True)
def fresh_ws_connections():
    from core.ws_manager import manager
    original = manager.connections
    manager.connections = {}
    yield
    manager.connections = original


# ---------------------------------------------------------------------------
# _group_for_path()
# ---------------------------------------------------------------------------


class TestGroupForPath:

    def test_root_path_is_core_platform(self):
        assert pm._group_for_path("/") == "core_platform"
        assert pm._group_for_path("") == "core_platform"

    def test_mapped_segment_resolves(self):
        assert pm._group_for_path("/deals/DEAL-1") == "sales"
        assert pm._group_for_path("/repair-orders/SRV-1") == "service"
        assert pm._group_for_path("/public/websites/SITE-1") == "public"

    def test_unmapped_segment_falls_back_to_other(self):
        assert pm._group_for_path("/some-future-thing/x") == "other"

    def test_ignores_leading_and_trailing_slashes(self):
        assert pm._group_for_path("///deals///DEAL-1///") == "sales"


# ---------------------------------------------------------------------------
# record_request()
# ---------------------------------------------------------------------------


class TestRecordRequest:

    def test_increments_request_count_for_correct_group(self):
        pm.record_request("/deals/DEAL-1", 200, 12.0)

        assert pm._metrics["sales"].request_count == 1
        assert pm._metrics["sales"].error_count == 0

    def test_error_status_increments_error_count(self):
        pm.record_request("/deals/DEAL-1", 500, 20.0)

        m = pm._metrics["sales"]
        assert m.request_count == 1
        assert m.error_count == 1
        assert m.last_error_at is not None

    def test_success_status_does_not_touch_last_error_at(self):
        pm.record_request("/deals/DEAL-1", 200, 20.0)

        assert pm._metrics["sales"].last_error_at is None

    def test_records_last_request_at(self):
        pm.record_request("/deals/DEAL-1", 200, 20.0)

        assert pm._metrics["sales"].last_request_at is not None

    def test_latency_samples_capped_at_max(self):
        for _ in range(pm._MAX_LATENCY_SAMPLES + 5):
            pm.record_request("/deals/DEAL-1", 200, 10.0)

        assert len(pm._metrics["sales"].latency_samples) == pm._MAX_LATENCY_SAMPLES
        assert pm._metrics["sales"].request_count == pm._MAX_LATENCY_SAMPLES + 5

    def test_different_paths_route_to_different_groups(self):
        pm.record_request("/deals/DEAL-1", 200, 10.0)
        pm.record_request("/repair-orders/SRV-1", 200, 10.0)

        assert pm._metrics["sales"].request_count == 1
        assert pm._metrics["service"].request_count == 1


# ---------------------------------------------------------------------------
# _derive_status()
# ---------------------------------------------------------------------------


class TestDeriveStatus:

    def test_zero_requests_is_no_traffic_yet(self):
        assert pm._derive_status(0, 0) == "no_traffic_yet"

    def test_zero_errors_is_operational(self):
        assert pm._derive_status(10, 0) == "operational"

    def test_ten_percent_or_less_is_performance_warning(self):
        assert pm._derive_status(10, 1) == "performance_warning"

    def test_above_ten_percent_is_degraded(self):
        assert pm._derive_status(10, 2) == "degraded"


# ---------------------------------------------------------------------------
# _messaging_subsystem_snapshot()
# ---------------------------------------------------------------------------


class TestMessagingSubsystemSnapshot:

    def test_no_connections_reports_zero(self):
        result = pm._messaging_subsystem_snapshot()

        assert result["employees_with_open_connection"] == 0
        assert result["open_socket_count"] == 0
        assert result["channels_configured"] > 0

    def test_reports_real_connection_counts(self):
        from core.ws_manager import manager
        manager.connections = {"EMP-1": ["ws1", "ws2"], "EMP-2": ["ws3"]}

        result = pm._messaging_subsystem_snapshot()

        assert result["employees_with_open_connection"] == 2
        assert result["open_socket_count"] == 3

    def test_import_failure_degrades_gracefully(self, monkeypatch):
        import builtins
        real_import = builtins.__import__

        def _fake_import(name, *args, **kwargs):
            if name == "core.ws_manager":
                raise ImportError("simulated failure")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _fake_import)

        result = pm._messaging_subsystem_snapshot()

        assert result["employees_with_open_connection"] == 0
        assert result["open_socket_count"] == 0
        assert result["channels_configured"] == 0
        assert "could not be loaded" in result["note"]


# ---------------------------------------------------------------------------
# get_platform_metrics_snapshot()
# ---------------------------------------------------------------------------


class TestGetPlatformMetricsSnapshot:

    def test_untouched_group_reports_no_traffic_yet(self):
        result = pm.get_platform_metrics_snapshot()

        assert result["groups"]["sales"]["status"] == "no_traffic_yet"
        assert result["groups"]["sales"]["request_count"] == 0
        assert result["groups"]["sales"]["avg_latency_ms"] is None

    def test_every_catalog_group_present(self):
        result = pm.get_platform_metrics_snapshot()

        assert set(result["groups"].keys()) == set(pm.ROUTE_GROUP_CATALOG.keys())

    def test_touched_group_reports_real_metrics(self):
        pm.record_request("/deals/DEAL-1", 200, 10.0)
        pm.record_request("/deals/DEAL-2", 200, 20.0)

        result = pm.get_platform_metrics_snapshot()

        sales = result["groups"]["sales"]
        assert sales["request_count"] == 2
        assert sales["error_count"] == 0
        assert sales["error_rate_pct"] == 0.0
        assert sales["avg_latency_ms"] == 15.0
        assert sales["sample_size"] == 2
        assert sales["status"] == "operational"
        assert sales["status_label"] == "Operational"

    def test_error_rate_computed_and_status_derived(self):
        for _ in range(9):
            pm.record_request("/deals/DEAL-1", 200, 10.0)
        pm.record_request("/deals/DEAL-1", 500, 10.0)

        result = pm.get_platform_metrics_snapshot()

        sales = result["groups"]["sales"]
        assert sales["request_count"] == 10
        assert sales["error_count"] == 1
        assert sales["error_rate_pct"] == 10.0
        assert sales["status"] == "performance_warning"

    def test_includes_uptime_and_process_start_time(self):
        result = pm.get_platform_metrics_snapshot()

        assert result["process_start_time"] == pm.PROCESS_START_TIME
        assert result["uptime_seconds"] >= 0

    def test_includes_messaging_subsystem(self):
        result = pm.get_platform_metrics_snapshot()

        assert "messaging_subsystem" in result
        assert "channels_configured" in result["messaging_subsystem"]

    def test_includes_note(self):
        result = pm.get_platform_metrics_snapshot()

        assert "IN-MEMORY ONLY" in result["note"]
