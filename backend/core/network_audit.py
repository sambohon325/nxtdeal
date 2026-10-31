"""
core/network_audit.py -- the Network page's per-dealer AI-driven self-audit
(2026-07-13, session 38). Sam: "an ai driven audit on their dealership to see where
they need to improve... this ties into the employee/bot data as well to see
recommendations... This also needs to include the prediction scales."

Rule-based, not a fabricated LLM narrative -- every recommendation below is derived
from a real, already-computed signal that lives elsewhere in this codebase: Department
Intelligence KPIs (core/department_intelligence.py -- e.g. obsolete parts inventory), the simulated-peer
percentile rank (core/network_benchmark.py), employee $-value/automation coverage
(core/employee_value.py), and department prediction confidence (core/prediction.py).
No recommendation fires without a concrete number crossing a concrete, documented
threshold -- this is a small rules engine over real data, not an LLM's opinion. Same
honesty bar as prediction.py's INDUSTRY_BASELINES: thresholds below are reasonable
rule-of-thumb cutoffs, not sourced from a specific study.
"""

from datetime import datetime, timezone

from core.department_intelligence import compute_department
from core.network_benchmark import benchmark_department, DEPARTMENTS as NETWORK_DEPARTMENTS
from core.employee_value import list_employee_values
from core.prediction import DEPARTMENTS as PREDICTION_DEPARTMENTS, department_readiness


LOW_PERCENTILE_THRESHOLD = 40.0
HIGH_AUTOMATION_PCT_THRESHOLD = 60.0
OBSOLETE_PARTS_PCT_THRESHOLD = 15.0
LOW_READINESS_CONFIDENCE_THRESHOLD = 60.0


def _now():
    return datetime.now(timezone.utc).isoformat()


def _percentile_recommendations():
    """Sam: "the network is a collection of other dealers... so that dealers can see
    area and industry trends" -- flags any department ranking in the bottom tier of
    the (simulated, honestly labeled) peer set."""

    recommendations = []

    for department in NETWORK_DEPARTMENTS:

        benchmark = benchmark_department(department)

        if not benchmark or benchmark["percentile_rank"] is None:
            continue

        if benchmark["percentile_rank"] < LOW_PERCENTILE_THRESHOLD:

            recommendations.append({
                "category": "network_benchmark",
                "department": department,
                "severity": "medium",
                "finding": (
                    f"{benchmark['title']} ranks at the {benchmark['percentile_rank']}th "
                    f"percentile of the peer set on {benchmark['primary_kpi'].replace('_', ' ')}."
                ),
                "recommendation": (
                    f"Review {department} operations against stronger peers -- this is "
                    "the department with the most room to close the gap."
                ),
                "basis": "simulated_peer_data",
            })

    return recommendations


def _obsolete_parts_recommendation():

    parts = compute_department("parts")

    if not parts:
        return []

    obsolete_pct = parts["kpis"].get("obsolete_inventory_pct", {}).get("value", 0)

    if obsolete_pct < OBSOLETE_PARTS_PCT_THRESHOLD:
        return []

    return [{
        "category": "profit_leak",
        "department": "parts",
        "severity": "high",
        "finding": f"{obsolete_pct}% of parts inventory value hasn't sold in 180+ days.",
        "recommendation": "Run a clearance or return-to-vendor push on obsolete stock -- real, addressable dead capital.",
        "basis": "ledger",
    }]


def _automation_recommendations():
    """Sam: "what efficiencies can be increased by simply increasing the bandwidth of
    the bots versus headcount" -- the concrete tie to
    core/employee_value.py's automation_coverage(). Framed the same way
    EFFECTIVENESS_DISCLAIMER frames every employee value result: a duty-reassignment
    signal, never a headcount-reduction recommendation."""

    recommendations = []

    for employee in list_employee_values():

        coverage = employee.get("automation_coverage")

        if not coverage or coverage["automation_pct"] < HIGH_AUTOMATION_PCT_THRESHOLD:
            continue

        recommendations.append({
            "category": "automation_opportunity",
            "department": employee.get("department"),
            "severity": "low",
            "finding": (
                f"{employee['name']} ({employee.get('department') or 'unassigned'}) has "
                f"{coverage['automation_pct']}% of their recurring flagged tasks already "
                "automatable by the bot."
            ),
            "recommendation": (
                "Consider shifting this employee's time toward higher-value duties and "
                "letting the bot cover the automatable tasks -- a reassignment signal, "
                "not a headcount recommendation."
            ),
            "basis": employee.get("basis", "ledger"),
        })

    return recommendations


def _readiness_recommendations():
    """Sam: "This also needs to include the prediction scales" -- surfaces any
    department whose prediction confidence is still low, with a concrete next step
    (connect more data) rather than a vague "improve your data" comment."""

    recommendations = []

    for department in PREDICTION_DEPARTMENTS:

        readiness = department_readiness(department)

        if not readiness or readiness["confidence_pct"] >= LOW_READINESS_CONFIDENCE_THRESHOLD:
            continue

        recommendations.append({
            "category": "data_readiness",
            "department": department,
            "severity": "medium",
            "finding": (
                f"{department.title()} is only {readiness['confidence_pct']}% confident "
                f"on tomorrow's prediction (target {readiness['threshold']}%)."
            ),
            "recommendation": (
                "Connect more data sources for this department on the Readiness page "
                "(CSV upload or API connection) to raise prediction confidence."
            ),
            "basis": readiness["basis"],
        })

    return recommendations


_SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def run_audit():
    """The full self-audit -- every recommendation is a real-signal derivation, tagged
    with department/category/severity/basis so the frontend can group and color-code
    them the same way every other basis-tagged feature in this codebase already does."""

    recommendations = (
        _percentile_recommendations()
        + _obsolete_parts_recommendation()
        + _automation_recommendations()
        + _readiness_recommendations()
    )

    recommendations.sort(key=lambda r: _SEVERITY_ORDER.get(r["severity"], 3))

    return {
        "generated_at": _now(),
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
    }
