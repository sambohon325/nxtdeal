"""
NXTDeal Hub (2026-07-16) -- real aggregate statistics computed over the anonymized
snapshot registry (hub/hub_core/network_snapshot.py). This is the "provide analytics across
the entire system... the gathering truth source of dealership metrics" half of Sam's
Hub request.

Deliberately honest about sample size: with 0-1 real dealer snapshots stored (today's
actual state -- see hub/hub_core/network_collector.py's docstring on why real cross-tenant
data is still limited), an average/median/percentile over one data point isn't a
meaningful "network benchmark" yet, so `sample_size` is reported alongside every
aggregate and the Hub console is expected to show that honestly rather than presenting
a single dealer's number as if it were an industry trend. This deliberately does NOT
touch backend/core/network_benchmark.py's simulated peer data (a per-dealer feature,
unrelated to this Hub-side aggregate) -- see that module's own docstring for the
separate, larger decision (flagged, not made here) about eventually replacing its
simulated seed with real cross-tenant data.
"""

import statistics

from hub_core.network_snapshot import registry


def compute_network_analytics():

    snapshots = registry.list_all()

    departments = {}

    for snapshot in snapshots:
        for department_key, kpis in snapshot.departments.items():

            department_bucket = departments.setdefault(department_key, {})

            for kpi_key, kpi in kpis.items():

                kpi_bucket = department_bucket.setdefault(
                    kpi_key,
                    {"label": kpi["label"], "format": kpi["format"], "values": []},
                )

                if isinstance(kpi["value"], (int, float)):
                    kpi_bucket["values"].append(kpi["value"])

    result = {}

    for department_key, kpis in departments.items():

        result[department_key] = {}

        for kpi_key, bucket in kpis.items():

            values = bucket["values"]

            result[department_key][kpi_key] = {
                "label": bucket["label"],
                "format": bucket["format"],
                "sample_size": len(values),
                "average": round(statistics.mean(values), 2) if values else None,
                "median": round(statistics.median(values), 2) if values else None,
                "min": round(min(values), 2) if values else None,
                "max": round(max(values), 2) if values else None,
            }

    return {
        "dealers_contributing": len(snapshots),
        "departments": result,
        "note": (
            "Every figure here is a real aggregate over whatever anonymized dealer "
            "snapshots the Hub has collected so far -- see dealers_contributing for "
            "the real sample size behind it. With very few dealers reporting, an "
            "average/median isn't yet a meaningful network benchmark; treat this as "
            "illustrative until dealers_contributing is large enough to trust. Never "
            "joinable back to a specific dealership -- see "
            "hub/hub_core/network_collector.py's module docstring for the anonymization "
            "design."
        ),
    }
