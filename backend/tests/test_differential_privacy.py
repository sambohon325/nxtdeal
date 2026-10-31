"""
Tests for core/differential_privacy.py -- the real, calibrated Laplace-mechanism noise
layer added to Network snapshots (security-hardening pass, 2026-07-20, Task #9), sitting
UNDER core/network_snapshot.py's pre-existing bucketing step (see
test_network_snapshot.py's TestDifferentialPrivacyIsWired for proof the two are
genuinely connected -- this file covers only the noise math itself in isolation).

Covers: laplace_sample()'s real inverse-CDF sampling (deterministic under a seeded rng,
the scale<=0 short-circuit, the u==0 edge case, and a real statistical sanity check that
its mean converges toward zero); add_laplace_noise()'s epsilon<=0 fail-loud behavior, its
real scale = sensitivity/epsilon relationship (smaller epsilon -> more noise, checked
against the same underlying uniform draws so it's a real comparison, not two unrelated
random samples), and determinism under a seeded rng; apply_dp_noise_to_kpi()'s per-format
sensitivity/epsilon resolution, its "unrecognized format -> unchanged" and "non-numeric
input -> unchanged, never raise" defensive contracts (matching network_snapshot.py's own
_bucket() conventions exactly, since this runs on the same raw values), and its numeric-
string coercion; and the EPSILON_BY_FORMAT/SENSITIVITY_BY_FORMAT catalogs themselves
(real, non-empty, covering every format network_snapshot.py actually publishes).

Run from backend/ with `pytest`.
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core import differential_privacy as dp


class TestCatalogs:

    def test_epsilon_and_sensitivity_cover_every_real_kpi_format(self):
        # network_snapshot.py's own BUCKET_SIZE_BY_FORMAT covers exactly these three --
        # the DP layer sitting underneath it must cover the same set, or a real KPI
        # would silently skip noise entirely.
        real_formats = {"currency", "number", "percent"}
        assert real_formats <= set(dp.EPSILON_BY_FORMAT.keys())
        assert real_formats <= set(dp.SENSITIVITY_BY_FORMAT.keys())

    def test_every_epsilon_is_a_real_positive_number(self):
        for format, epsilon in dp.EPSILON_BY_FORMAT.items():
            assert epsilon > 0, format

    def test_every_sensitivity_is_a_real_positive_number(self):
        for format, sensitivity in dp.SENSITIVITY_BY_FORMAT.items():
            assert sensitivity > 0, format


class TestLaplaceSample:

    def test_non_positive_scale_returns_zero(self):
        assert dp.laplace_sample(0, rng=random.Random(1)) == 0.0
        assert dp.laplace_sample(-5, rng=random.Random(1)) == 0.0

    def test_seeded_rng_is_deterministic(self):
        first = dp.laplace_sample(100, rng=random.Random(42))
        second = dp.laplace_sample(100, rng=random.Random(42))
        assert first == second

    def test_different_seeds_produce_different_samples(self):
        first = dp.laplace_sample(100, rng=random.Random(1))
        second = dp.laplace_sample(100, rng=random.Random(2))
        assert first != second

    def test_u_equals_zero_edge_case_returns_zero_without_raising(self):
        # A fake rng whose random() always returns exactly 0.5 makes u = 0.5 - 0.5 = 0,
        # the one input laplace_sample's own docstring calls out as a real edge case
        # (math.log(1 - 0) = math.log(1) = 0, so this must be short-circuited rather
        # than naturally falling out of the general formula, since copysign(1, 0) is
        # well-defined but the general path is still worth a dedicated guard).
        class _FixedRng:
            def random(self):
                return 0.5

        assert dp.laplace_sample(100, rng=_FixedRng()) == 0.0

    def test_mean_of_many_samples_converges_toward_zero(self):
        # Laplace(0, scale) has a true mean of 0 -- a real statistical sanity check
        # that this isn't secretly biased in one direction. Uses a fixed seed so the
        # test itself is deterministic even though it's exercising randomness.
        rng = random.Random(7)
        samples = [dp.laplace_sample(50, rng=rng) for _ in range(5000)]
        mean = sum(samples) / len(samples)
        # A generous tolerance -- this is a sanity check against a real bug (e.g. a
        # sign error), not a tight statistical claim.
        assert abs(mean) < 5, f"mean drifted too far from 0: {mean}"


class TestAddLaplaceNoise:

    def test_non_positive_epsilon_raises_value_error(self):
        with pytest.raises(ValueError):
            dp.add_laplace_noise(100, sensitivity=10, epsilon=0)
        with pytest.raises(ValueError):
            dp.add_laplace_noise(100, sensitivity=10, epsilon=-1)

    def test_seeded_rng_is_deterministic(self):
        first = dp.add_laplace_noise(100, sensitivity=10, epsilon=1, rng=random.Random(42))
        second = dp.add_laplace_noise(100, sensitivity=10, epsilon=1, rng=random.Random(42))
        assert first == second

    def test_result_is_value_plus_real_noise_not_the_raw_value(self):
        result = dp.add_laplace_noise(100, sensitivity=10, epsilon=0.5, rng=random.Random(3))
        assert result != 100

    def test_smaller_epsilon_produces_larger_average_noise_magnitude(self):
        # scale = sensitivity / epsilon -- a smaller epsilon means a larger scale,
        # which means larger-magnitude noise on average (more privacy, less precision).
        # Compared as a real statistical average across many independent draws (each
        # epsilon gets its own freshly-seeded rng sequence) rather than a single sample,
        # since any one Laplace draw can land anywhere.
        small_epsilon_magnitudes = [
            abs(dp.add_laplace_noise(0, sensitivity=10, epsilon=0.1, rng=random.Random(i)))
            for i in range(500)
        ]
        large_epsilon_magnitudes = [
            abs(dp.add_laplace_noise(0, sensitivity=10, epsilon=10, rng=random.Random(i)))
            for i in range(500)
        ]
        avg_small_epsilon = sum(small_epsilon_magnitudes) / len(small_epsilon_magnitudes)
        avg_large_epsilon = sum(large_epsilon_magnitudes) / len(large_epsilon_magnitudes)
        assert avg_small_epsilon > avg_large_epsilon


class TestApplyDpNoiseToKpi:

    def test_unrecognized_format_returns_value_unchanged(self, monkeypatch):
        # Neuter the two catalogs so "count" (a real format elsewhere in this codebase,
        # e.g. network_snapshot's own _bucket() fallback) is genuinely unrecognized here
        # too, without depending on it staying absent from the real catalogs forever.
        monkeypatch.setitem(dp.EPSILON_BY_FORMAT, "count", None)
        monkeypatch.delitem(dp.EPSILON_BY_FORMAT, "count", raising=False)
        assert "count" not in dp.EPSILON_BY_FORMAT
        assert dp.apply_dp_noise_to_kpi(1234, "count", rng=random.Random(1)) == 1234.0

    def test_non_numeric_value_returned_unchanged_never_raises(self):
        assert dp.apply_dp_noise_to_kpi(None, "currency") is None
        assert dp.apply_dp_noise_to_kpi("not-a-number", "currency") == "not-a-number"

    def test_numeric_string_is_coerced_before_noising(self):
        result = dp.apply_dp_noise_to_kpi("100", "currency", rng=random.Random(1))
        assert isinstance(result, float)

    def test_real_noise_is_actually_applied_for_every_real_format(self):
        for format in ("currency", "number", "percent"):
            with_noise = dp.apply_dp_noise_to_kpi(1000, format, rng=random.Random(9))
            assert with_noise != 1000, format

    def test_seeded_rng_makes_result_deterministic(self):
        first = dp.apply_dp_noise_to_kpi(1000, "currency", rng=random.Random(42))
        second = dp.apply_dp_noise_to_kpi(1000, "currency", rng=random.Random(42))
        assert first == second

    def test_omitting_rng_uses_real_randomness_not_a_fixed_default(self):
        # No seed injected -- across many independent calls, real (non-deterministic)
        # noise should not always produce the exact same output.
        results = {dp.apply_dp_noise_to_kpi(1000, "currency") for _ in range(20)}
        assert len(results) > 1
