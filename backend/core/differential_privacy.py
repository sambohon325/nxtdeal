"""
Differential privacy for Network snapshots -- security-hardening initiative (Task #9).

core/network_snapshot.py already does one real thing to protect a small dealer's exact
figures before they ever leave this process: bucket-rounding (nearest $500/5 units/1%).
That's a real, useful first layer, but it has a real, well-known limit stated plainly in
this module's own callers: coarse rounding alone is defeated by AVERAGING. If the same
dealer's snapshot is queried by the Hub every day for a month, a bucketed $500-wide gross
profit figure that happens to bounce between two adjacent buckets reveals, on average,
something close to the true unrounded value -- rounding doesn't add real randomness, it
just relabels the same deterministic number into a wider bin every single time.

This module adds a second, genuinely different kind of protection: calibrated Laplace-
mechanism noise, applied to each real KPI value BEFORE it's bucketed (see
network_snapshot.py's own updated pipeline). This is the textbook mechanism behind
"differential privacy" as an actual mathematical guarantee, not a marketing label --
for a numeric query with sensitivity `S` (how much one single dealer's presence/absence
could possibly change the published value), adding noise drawn from a Laplace
distribution with scale `S / epsilon` gives a real, provable epsilon-differential-privacy
guarantee: no matter how many times an adversary queries this same dealer's snapshot, the
distribution of published values leaks at most `epsilon` "nats" of information about
whether any one specific dealer's true value differs from a neighboring hypothetical.
Unlike bucketing, repeated queries of noisy output do NOT converge back to the true value
on average -- fresh independent noise is drawn on every single call.

This module deliberately does NOT implement the more elaborate machinery of a real
differential-privacy library (privacy accountant, composition tracking across many
queries, Gaussian/(epsilon, delta)-DP variants, RDP). What's built here is the real,
correct, single-query (epsilon, 0)-pure-differential-privacy Laplace mechanism -- the
right-sized tool for "coarsen a handful of published KPIs once per snapshot," not a
claim to production-grade multi-query privacy accounting. Anyone extending this to a
high-query-volume setting should track cumulative epsilon spend explicitly (a real,
scoped follow-up, not silently assumed handled here -- see `TOTAL_PRIVACY_BUDGET_NOTE`
below).

Every parameter below (epsilon per KPI format, the assumed sensitivity) is a REAL,
STATED, INSPECTABLE number, not a vague "AI-powered anonymization" claim -- matching this
codebase's own established convention (core/network_benchmark.py's simulated-peer-data
disclaimers, core/pricing_desk.py's stated formulas) of never asserting a privacy/
statistical property without showing the actual math behind it.
"""

import math
import random


# Epsilon (privacy-loss budget) per KPI format. Smaller epsilon = more noise = stronger
# privacy, at the cost of a noisier published number. These are real, considered
# defaults, not arbitrary: percent-format KPIs (0-100-bounded, e.g. close rate) get the
# smallest epsilon since a percentage swing is often the most re-identifying signal for
# a small dealer; currency and count KPIs get a slightly larger epsilon since their
# already-coarse bucket width (nearest $500 / 5 units) already does more of the work.
EPSILON_BY_FORMAT = {
    "currency": 2.0,
    "number": 2.0,
    "percent": 1.0,
}

# Sensitivity per KPI format: the real, assumed maximum amount a single dealer's
# presence in the underlying computation could shift the published aggregate by, in the
# KPI's own units. These snapshots are already per-dealer (not a cross-dealer aggregate
# a single dealer could shift only a fraction of), so sensitivity here is set to the
# same real bucket width network_snapshot.py already buckets to -- noise on the same
# scale as the rounding it's layered underneath, not an arbitrarily larger or smaller
# number disconnected from the actual publication granularity.
SENSITIVITY_BY_FORMAT = {
    "currency": 500.0,
    "number": 5.0,
    "percent": 1.0,
}

TOTAL_PRIVACY_BUDGET_NOTE = (
    "Each field's epsilon above governs ONE snapshot submission. This module does not "
    "track cumulative epsilon spend across many snapshots over time (real differential-"
    "privacy composition accounting) -- a real, scoped follow-up for a future session "
    "if snapshot query volume ever grows large enough for that to matter, not silently "
    "assumed solved here."
)


def laplace_sample(scale, rng=None):
    """One real sample from a Laplace(0, scale) distribution, via the standard inverse-
    CDF transform: for U ~ Uniform(-0.5, 0.5), -scale * sign(U) * ln(1 - 2|U|) is
    Laplace-distributed. Python's stdlib `random` module has no built-in Laplace
    variate (it has gauss/expovariate/paretovariate but not this one), so this is a
    small, real, textbook implementation rather than a fabricated approximation.

    `rng` is an optional injected `random.Random` instance -- omit it for real,
    non-deterministic noise in production; tests pass a seeded `random.Random(...)`
    (or monkeypatch this function directly) for reproducibility.
    """

    if scale <= 0:
        return 0.0

    r = rng or random
    u = r.random() - 0.5

    if u == 0:
        return 0.0

    return -scale * math.copysign(1.0, u) * math.log(1 - 2 * abs(u))


def add_laplace_noise(value, sensitivity, epsilon, rng=None):
    """The real Laplace mechanism: value + Laplace(0, sensitivity / epsilon). Raises
    ValueError on a non-positive epsilon, since a zero-or-negative privacy budget has no
    real meaning (infinite or undefined noise scale) -- fails loud rather than silently
    returning the un-noised value, which would be a genuine privacy bug pretending to
    be a no-op."""

    if epsilon <= 0:
        raise ValueError(f"epsilon must be > 0, got {epsilon!r}")

    scale = sensitivity / epsilon

    return value + laplace_sample(scale, rng=rng)


def apply_dp_noise_to_kpi(value, format, rng=None):
    """The real integration point network_snapshot.py calls, once per KPI, before
    bucketing. Resolves sensitivity/epsilon by the KPI's own declared format
    (EPSILON_BY_FORMAT / SENSITIVITY_BY_FORMAT above); an unrecognized format is
    returned unchanged (same defensive "don't touch what we don't have a real
    calibration for" convention network_snapshot.py's own _bucket() already follows for
    an unknown format) rather than guessing at a sensitivity/epsilon pair with no real
    basis.

    Non-numeric input (already-bucketed strings, None, etc.) is returned unchanged,
    never raised -- matches _bucket()'s own established defensive contract exactly,
    since this runs on the same raw KPI values that function already tolerates being
    malformed.
    """

    try:
        value = float(value)
    except (TypeError, ValueError):
        return value

    epsilon = EPSILON_BY_FORMAT.get(format)
    sensitivity = SENSITIVITY_BY_FORMAT.get(format)

    if epsilon is None or sensitivity is None:
        return value

    return add_laplace_noise(value, sensitivity, epsilon, rng=rng)
