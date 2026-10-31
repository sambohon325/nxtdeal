"""
Anonymous network snapshot (2026-07-16, Cowork, interactive) -- what a dealer instance
actually sends to the NXTDeal Hub for cross-network intelligence.

Four privacy layers stack here, all real:

  1. Identity: every value below is tagged with this instance's local, randomly
     generated pseudonym (core/network_pseudonym.py), never dealer_id/name/contact info.
  2. Noise (added 2026-07-20, security-hardening Task #9): every raw KPI value gets real,
     calibrated Laplace-mechanism noise (core/differential_privacy.py) applied BEFORE
     bucketing -- a genuine (epsilon, 0)-differential-privacy guarantee, not just coarser
     rounding. See that module's own docstring for why bucketing alone is defeated by
     averaging repeated queries and noise isn't.
  3. Precision: every numeric KPI is then rounded to a coarse bucket (see
     BUCKET_SIZE_BY_FORMAT below) before it ever leaves this process. A small dealer's
     exact-to-the-cent gross profit is itself a quasi-identifier (there may be very few
     dealers near a specific odd number) -- bucketing to the nearest $500/1%/5-units
     trades a little precision for a real reduction in re-identification risk, the same
     logic real published aggregate statistics use, now on top of already-noised input.
  4. PII pre-flight (added 2026-07-20, security-hardening Task #10): after the noise and
     bucketing layers above run, core/pii_scan.py's assert_no_pii() re-scans the real
     department/KPI content for email/phone/SSN/VIN-shaped strings and raises
     PiiDetectedError, BLOCKING the snapshot from ever being returned, if any is found.
     This is a genuinely different kind of defense from layers 2-3 (content-shaped, not
     statistical) -- a structural bug that somehow let a raw customer/employee string
     leak into a KPI label or value would still be caught here even though it isn't a
     precision or re-identification problem noise/bucketing address. Only the
     `departments`/`note` fields are scanned -- `pseudonym` (an opaque random hex token)
     and `submitted_at` (a structural ISO timestamp) are neither derived from real
     dealership data nor able to legitimately carry PII, so scanning them would only add
     a rare, spurious false-positive risk (e.g. a long hex string coincidentally
     containing 17 consecutive digit characters, matching pii_scan's VIN shape) with zero
     real security value.

Reuses core/department_intelligence.py's compute_department() verbatim for the actual
KPI numbers -- this is not a second, parallel KPI engine, just a privacy-preserving
transform applied on top of the same real numbers every other NXTDeal dashboard reads.

Gated by a shared secret (see core/network_snapshot_api.py), not an employee session
token -- this is a server-to-server call from the Hub, not something a logged-in
employee's browser calls directly.
"""

from datetime import datetime, timezone

from core.department_intelligence import compute_department, DEPARTMENTS
from core.differential_privacy import apply_dp_noise_to_kpi
from core.network_pseudonym import get_or_create_pseudonym
from core.pii_scan import assert_no_pii

BUCKET_SIZE_BY_FORMAT = {
    "currency": 500,
    "number": 5,
    "percent": 1,
}


def _bucket(value, format):

    try:
        value = float(value)
    except (TypeError, ValueError):
        return value

    size = BUCKET_SIZE_BY_FORMAT.get(format)

    if not size:
        return value

    return round(value / size) * size


def build_anonymous_snapshot(rng=None):
    """Real KPIs, real Laplace-mechanism noise, then coarsened into a bucket, before
    ever leaving this process. Never raises on a missing department -- a department
    with no compute function (there isn't one today, but this stays defensive) is just
    skipped rather than failing the whole snapshot.

    `rng` is an optional injected `random.Random` instance, threaded straight through
    to core/differential_privacy.py's `apply_dp_noise_to_kpi()` -- omit it for real,
    non-deterministic noise (the production default); tests pass a seeded instance, or
    monkeypatch `apply_dp_noise_to_kpi` to a no-op passthrough, for deterministic
    assertions on the bucketing behavior specifically."""

    departments = {}

    for department_key in DEPARTMENTS:

        result = compute_department(department_key)

        if not result:
            continue

        bucketed_kpis = {}

        for kpi_key, kpi in result["kpis"].items():
            noised_value = apply_dp_noise_to_kpi(kpi["value"], kpi["format"], rng=rng)
            bucketed_kpis[kpi_key] = {
                "label": kpi["label"],
                "value": _bucket(noised_value, kpi["format"]),
                "format": kpi["format"],
            }

        departments[department_key] = bucketed_kpis

    note = (
        "Every value here is a real KPI with calibrated Laplace-mechanism noise "
        "applied (a genuine differential-privacy guarantee, see "
        "core/differential_privacy.py), then rounded to a coarse bucket "
        "(nearest $500/5 units/1%) before leaving this instance -- see "
        "core/network_snapshot.py's module docstring for why both layers matter. "
        "Never joinable back to a specific dealer, even by NXTDeal staff, since "
        "the pseudonym is a locally generated random token with no derivation "
        "from dealer_id."
    )

    # PII pre-flight (Task #10): re-scan the real, derived-from-actual-dealership-data
    # content -- departments/note -- for email/phone/SSN/VIN-shaped strings before this
    # snapshot is ever returned. Blocking: raises PiiDetectedError rather than letting a
    # leak silently ship. pseudonym/submitted_at are deliberately excluded -- neither is
    # derived from real dealership data, so scanning them adds no real security value,
    # only a rare spurious false-positive risk (see the module docstring above).
    assert_no_pii({"departments": departments, "note": note}, context="network anonymous snapshot")

    return {
        "pseudonym": get_or_create_pseudonym(),
        "submitted_at": datetime.now(timezone.utc).isoformat(),
        "departments": departments,
        "note": note,
    }
