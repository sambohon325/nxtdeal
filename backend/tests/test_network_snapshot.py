"""
Tests for core/network_snapshot.py / core/network_snapshot_api.py -- the anonymous,
noised, bucketed, per-department KPI snapshot a dealer instance sends to the NXTDeal
Hub (2026-07-16, differential-privacy noise layer added 2026-07-20, security-hardening
Task #9). Run from backend/ with `pytest`.

Covers: _bucket()'s currency/number/percent rounding, its "unknown format -> return the
float-coerced value unchanged" fallback, and its "non-numeric input -> return raw value
unchanged, never raise" defensive path; build_anonymous_snapshot()'s real bucketing
behavior against a faked compute_department()/DEPARTMENTS (deterministic -- with the new
DP-noise step monkeypatched to a no-op passthrough so these assertions keep isolating
bucketing specifically, matching this file's own long-established one-thing-at-a-time
testing convention; core/differential_privacy.py has its own dedicated test file for the
real noise math), its "a department with no compute result is skipped, never raises"
defensiveness, the real pseudonym/submitted_at/note fields, and one real end-to-end smoke
test against the actual core/department_intelligence.py + an empty ledger (confirms the
real KPI engine never blows up on a fresh graph); a new class proving the DP-noise layer
is genuinely wired into the real pipeline (not just present as an unused import) and that
a seeded `rng` produces deterministic, reproducible noise; and network_snapshot_api.py's
shared-secret gate (check_network_key / get_anonymous_snapshot_api).
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import network_snapshot
from core import network_snapshot_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


class TestBucket:

    def test_currency_rounds_to_nearest_500(self):
        assert network_snapshot._bucket(1234, "currency") == 1000
        assert network_snapshot._bucket(1750, "currency") == 2000

    def test_number_rounds_to_nearest_5(self):
        assert network_snapshot._bucket(1234, "number") == 1235
        assert network_snapshot._bucket(2, "number") == 0

    def test_percent_rounds_to_nearest_1(self):
        assert network_snapshot._bucket(37.6, "percent") == 38
        assert network_snapshot._bucket(37.4, "percent") == 37

    def test_unknown_format_returns_float_coerced_value_unchanged(self):
        result = network_snapshot._bucket(1234, "count")
        assert result == 1234.0
        assert isinstance(result, float)

    def test_non_numeric_value_returned_unchanged_never_raises(self):
        assert network_snapshot._bucket("not-a-number", "currency") == "not-a-number"
        assert network_snapshot._bucket(None, "currency") is None

    def test_numeric_string_is_coerced_and_bucketed(self):
        assert network_snapshot._bucket("42", "currency") == 0


class TestBuildAnonymousSnapshot:

    def _fake_compute_department(self, results):
        return lambda department_key: results.get(department_key)

    def test_real_kpis_get_bucketed_with_label_and_format_preserved(self, monkeypatch):
        fake_result = {
            "kpis": {
                "gross_profit": {"label": "Gross Profit", "value": 12345, "format": "currency"},
                "units_sold": {"label": "Units Sold", "value": 47, "format": "number"},
                "close_rate": {"label": "Close Rate", "value": 22.7, "format": "percent"},
            }
        }
        monkeypatch.setattr(network_snapshot, "DEPARTMENTS", ["sales"])
        monkeypatch.setattr(
            network_snapshot, "compute_department", self._fake_compute_department({"sales": fake_result})
        )
        monkeypatch.setattr(network_snapshot, "get_or_create_pseudonym", lambda: "fake-pseudonym-123")
        # DP noise is real, random-by-design (see core/differential_privacy.py) --
        # neutered here to an exact passthrough so this test can keep isolating
        # bucketing behavior specifically, matching this file's own established
        # one-thing-at-a-time convention. The real noise math has its own dedicated
        # test file (test_differential_privacy.py); TestDifferentialPrivacyIsWired
        # below proves the two are genuinely connected.
        monkeypatch.setattr(network_snapshot, "apply_dp_noise_to_kpi", lambda value, format, rng=None: value)

        snapshot = network_snapshot.build_anonymous_snapshot()

        sales_kpis = snapshot["departments"]["sales"]
        assert sales_kpis["gross_profit"] == {"label": "Gross Profit", "value": 12500, "format": "currency"}
        assert sales_kpis["units_sold"] == {"label": "Units Sold", "value": 45, "format": "number"}
        assert sales_kpis["close_rate"] == {"label": "Close Rate", "value": 23, "format": "percent"}

    def test_department_with_no_compute_result_is_skipped_not_raised(self, monkeypatch):
        monkeypatch.setattr(network_snapshot, "DEPARTMENTS", ["sales", "missing_dept"])
        monkeypatch.setattr(
            network_snapshot,
            "compute_department",
            self._fake_compute_department({"sales": {"kpis": {}}}),
        )
        monkeypatch.setattr(network_snapshot, "get_or_create_pseudonym", lambda: "fake-pseudonym")

        snapshot = network_snapshot.build_anonymous_snapshot()

        assert "sales" in snapshot["departments"]
        assert "missing_dept" not in snapshot["departments"]

    def test_pseudonym_field_matches_the_real_helper(self, monkeypatch):
        monkeypatch.setattr(network_snapshot, "DEPARTMENTS", [])
        monkeypatch.setattr(network_snapshot, "get_or_create_pseudonym", lambda: "a-specific-token")

        snapshot = network_snapshot.build_anonymous_snapshot()
        assert snapshot["pseudonym"] == "a-specific-token"

    def test_submitted_at_is_present(self, monkeypatch):
        monkeypatch.setattr(network_snapshot, "DEPARTMENTS", [])
        monkeypatch.setattr(network_snapshot, "get_or_create_pseudonym", lambda: "x")

        snapshot = network_snapshot.build_anonymous_snapshot()
        assert snapshot["submitted_at"]

    def test_note_field_states_the_privacy_guarantee(self, monkeypatch):
        monkeypatch.setattr(network_snapshot, "DEPARTMENTS", [])
        monkeypatch.setattr(network_snapshot, "get_or_create_pseudonym", lambda: "x")

        snapshot = network_snapshot.build_anonymous_snapshot()
        assert "coarse bucket" in snapshot["note"]
        assert "Never joinable back to a specific dealer" in snapshot["note"]

    def test_real_end_to_end_against_an_empty_ledger_never_raises(self):
        # No monkeypatching -- exercises the real core/department_intelligence.py
        # compute functions against a genuinely empty, freshly reset ledger, confirming
        # the whole real snapshot pipeline is defensive against a fresh graph.
        snapshot = network_snapshot.build_anonymous_snapshot()

        assert set(snapshot["departments"].keys()) == set(network_snapshot.DEPARTMENTS)
        assert snapshot["pseudonym"]
        assert snapshot["submitted_at"]


class TestDifferentialPrivacyIsWired:
    """Proves core/differential_privacy.py is genuinely called by the real snapshot
    pipeline, not just imported and unused -- and that an injected rng makes the whole
    thing deterministic/reproducible, the real property a caller needs to test against
    without waiting on statistics."""

    def _fake_compute_department(self, results):
        return lambda department_key: results.get(department_key)

    def test_apply_dp_noise_to_kpi_is_actually_called_once_per_kpi(self, monkeypatch):
        fake_result = {
            "kpis": {
                "gross_profit": {"label": "Gross Profit", "value": 12345, "format": "currency"},
                "units_sold": {"label": "Units Sold", "value": 47, "format": "number"},
            }
        }
        monkeypatch.setattr(network_snapshot, "DEPARTMENTS", ["sales"])
        monkeypatch.setattr(
            network_snapshot, "compute_department", self._fake_compute_department({"sales": fake_result})
        )
        monkeypatch.setattr(network_snapshot, "get_or_create_pseudonym", lambda: "x")

        calls = []

        def _tracked_noise(value, format, rng=None):
            calls.append((value, format))
            return value

        monkeypatch.setattr(network_snapshot, "apply_dp_noise_to_kpi", _tracked_noise)

        network_snapshot.build_anonymous_snapshot()

        assert calls == [(12345, "currency"), (47, "number")]

    def test_noise_is_genuinely_applied_by_default_values_differ_from_raw_bucketing(self, monkeypatch):
        # No monkeypatching of apply_dp_noise_to_kpi here -- this proves the real,
        # default (non-injected-rng) code path actually perturbs the value before
        # bucketing, not just that the function exists. A value picked far from any
        # bucket boundary (12345 currency, bucket size 500) means real Laplace noise
        # landing it on the SAME bucket as the un-noised value on every single one of
        # many trials would be a strong (though not logically airtight) sign noise
        # isn't really being applied -- so this asserts noise causes at least one
        # different bucket across a real sample of independent snapshot builds.
        fake_result = {
            "kpis": {"gross_profit": {"label": "Gross Profit", "value": 12345, "format": "currency"}}
        }
        monkeypatch.setattr(network_snapshot, "DEPARTMENTS", ["sales"])
        monkeypatch.setattr(
            network_snapshot, "compute_department", self._fake_compute_department({"sales": fake_result})
        )
        monkeypatch.setattr(network_snapshot, "get_or_create_pseudonym", lambda: "x")

        observed_values = set()
        for _ in range(30):
            snapshot = network_snapshot.build_anonymous_snapshot()
            observed_values.add(snapshot["departments"]["sales"]["gross_profit"]["value"])

        assert len(observed_values) > 1, (
            "30 independent snapshot builds of the same raw KPI all bucketed to the "
            "exact same value -- differential-privacy noise does not appear to be "
            "genuinely applied by the default (real, non-injected) rng path."
        )

    def test_injected_seeded_rng_makes_the_whole_snapshot_deterministic(self, monkeypatch):
        fake_result = {
            "kpis": {"gross_profit": {"label": "Gross Profit", "value": 12345, "format": "currency"}}
        }
        monkeypatch.setattr(network_snapshot, "DEPARTMENTS", ["sales"])
        monkeypatch.setattr(
            network_snapshot, "compute_department", self._fake_compute_department({"sales": fake_result})
        )
        monkeypatch.setattr(network_snapshot, "get_or_create_pseudonym", lambda: "x")

        first = network_snapshot.build_anonymous_snapshot(rng=random.Random(42))
        second = network_snapshot.build_anonymous_snapshot(rng=random.Random(42))

        assert first["departments"] == second["departments"]


class TestNetworkSnapshotApi:

    def test_check_network_key_refuses_dev_fallback_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("DEALEROS_NETWORK_KEY", raising=False)

        assert network_snapshot_api.check_network_key("dev-only-insecure-network-key-change-me") == {"error": "invalid or missing X-NXTDeal-Network-Key"}
        error = network_snapshot_api.check_network_key("wrong-key")
        assert error == {"error": "invalid or missing X-NXTDeal-Network-Key"}

    def test_check_network_key_honors_a_configured_env_var(self, monkeypatch):
        monkeypatch.setenv("DEALEROS_NETWORK_KEY", "synthetic-shared-network-secret-for-tests-only")

        assert network_snapshot_api.check_network_key("synthetic-shared-network-secret-for-tests-only") is None
        error = network_snapshot_api.check_network_key("dev-only-insecure-network-key-change-me")
        assert error == {"error": "invalid or missing X-NXTDeal-Network-Key"}

    def test_get_anonymous_snapshot_api_rejects_bad_key_without_building_snapshot(self, monkeypatch):
        monkeypatch.setenv("DEALEROS_NETWORK_KEY", "synthetic-shared-network-secret-for-tests-only")
        called = {"count": 0}

        def _tracked_build():
            called["count"] += 1
            return {}

        monkeypatch.setattr(network_snapshot_api, "build_anonymous_snapshot", _tracked_build)

        result = network_snapshot_api.get_anonymous_snapshot_api("wrong-key")

        assert result == {"error": "invalid or missing X-NXTDeal-Network-Key"}
        assert called["count"] == 0

    def test_get_anonymous_snapshot_api_returns_real_snapshot_on_valid_key(self, monkeypatch):
        monkeypatch.setenv("DEALEROS_NETWORK_KEY", "synthetic-shared-network-secret-for-tests-only")
        monkeypatch.setattr(
            network_snapshot_api, "build_anonymous_snapshot", lambda: {"pseudonym": "x", "departments": {}}
        )

        result = network_snapshot_api.get_anonymous_snapshot_api("synthetic-shared-network-secret-for-tests-only")

        assert result == {"pseudonym": "x", "departments": {}}

    def test_get_anonymous_snapshot_api_converts_a_pii_block_into_a_clean_error_dict(self, monkeypatch):
        # core/pii_scan.py's Task #10 blocking check raises PiiDetectedError from inside
        # build_anonymous_snapshot() -- confirms get_anonymous_snapshot_api() catches it
        # and returns this codebase's usual {"error": ...} shape, rather than letting an
        # unhandled exception surface as a raw 500 through api/app.py's route handler.
        from core.pii_scan import PiiDetectedError

        monkeypatch.setenv("DEALEROS_NETWORK_KEY", "synthetic-shared-network-secret-for-tests-only")

        def _blocked_build():
            raise PiiDetectedError(
                findings=[
                    {
                        "type": "email",
                        "confidence": "high",
                        "path": "root.departments.sales.some_kpi.label",
                        "value_excerpt": "jane@dealer.com",
                    }
                ],
                context="network anonymous snapshot",
            )

        monkeypatch.setattr(network_snapshot_api, "build_anonymous_snapshot", _blocked_build)

        result = network_snapshot_api.get_anonymous_snapshot_api("synthetic-shared-network-secret-for-tests-only")

        assert result["error"] == "network snapshot blocked: potential PII detected"
        assert result["findings"] == [
            {
                "type": "email",
                "confidence": "high",
                "path": "root.departments.sales.some_kpi.label",
            }
        ]
        # The real leaked text must never be re-transmitted in the API-facing error --
        # only its type/confidence/structural path.
        assert "jane@dealer.com" not in str(result)
