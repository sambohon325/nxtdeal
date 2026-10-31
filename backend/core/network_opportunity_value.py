"""
core/network_opportunity_value.py -- the real, honest dollar-denomination layer
over Network's Gap Analysis math (2026-07-18, "NXTDeal Intelligence Network"
reframe, slice 1). Sam's Overview/Opportunities spec both want a real
dollar-shaped number -- "Inventory Aging $186,000 opportunity," "Sales
$340,000/yr," a "Total Identified Opportunity" of "$1.8 Million" -- but
core/network_menu.py's own pre-existing overview() only ever summed
peer-average-minus-you gaps across MIXED KPI UNITS (dollars, percentage
points, unit counts) into one number labeled potential_gross_opportunity_
monthly. That old field is left in place (network_menu.py now explicitly
documents it as a non-dollar aggregate, not deleted) -- this module is the
honest replacement built to Sam's real spec.

Every dollar figure below is either:

  1. DIRECT -- the underlying KPI is already currency-shaped
     (core/department_intelligence.py's own "format": "currency" tag). The
     gap itself (peer_average - this_store) IS the dollar amount, no formula
     needed.

  2. DERIVED, via a real, already-computed per-unit dollar value FROM THIS
     DEALER'S OWN real KPIs (never a peer's, and never an invented constant)
     -- e.g. a gap of N *units* in Sales' units_sold, times this dealer's own
     real gross_profit_per_unit, is a real, traceable dollar estimate of what
     closing that unit-volume gap would be worth at this dealer's own actual
     margin. core/readiness_scenarios.py (this same reframe's own Readiness
     rebuild) established the exact discipline copied here: show the real
     inputs and the real ratio applied alongside every output, so a caller
     can audit the math, not just trust it. See _COUNT_KPI_TO_DOLLAR_VALUE
     below for the small, explicit, real-KPI-pair mapping used -- there is no
     mapping for a KPI this codebase has no real per-unit dollar figure to
     pair it with, and none is invented.

  3. NOT CONVERTIBLE -- every percentage-point gap (Customer Pay %, Obsolete
     Inventory %, Avg APR, every Executive contribution_pct) and the one
     ratio-format gap (Parts' Inventory Turns) has NO real, already-computed
     dollar-per-point (or dollar-per-turn) multiplier anywhere in this
     codebase. Inventing one -- e.g. "each point of Customer Pay % is worth
     $X" -- would be exactly the fabrication this module exists to avoid.
     These are reported honestly with conversion_method =
     "not_convertible_to_dollars" and a stated reason, never silently
     dropped and never guessed.

Deliberately mirrors (does not call) core/network_menu.py's gap_analysis()
math in _all_gaps() below -- network_menu.py imports FROM this module for its
Overview/Opportunities enrichment, so importing gap_analysis() back would be
a circular import. Both computations are simple, deterministic derivations
of the same get_network_benchmarks_api() payload and are guaranteed to
produce identical gap/this_store/peer_average/format values.

The Executive department's total_gross_profit is a real cross-department
ROLLUP of Sales + Service + Parts + F&I gross (core/department_intelligence.py's
compute_executive_kpis()) -- its own dollar gap is shown per-KPI (informational)
but EXCLUDED from every department-total/grand-total sum here, since summing
it alongside its own four source departments would double-count the same
real dollars twice. Same "reuse an already-real ratio, never fabricate one"
discipline, and the same "state a gap honestly rather than guess" discipline,
as this reframe's own core/readiness_scenarios.py/core/readiness_recommendations.py.

This module makes ZERO graph mutations -- every function here is a pure,
read-only calculation over already-real (or, for peer figures, already
clearly SIMULATED and labeled) data. No role gate is added inside these
core functions -- get_network_benchmarks_api()/get_network_audit_api()
(core/network_api.py) already self-gate to NETWORK_ROLES (ADMIN/OPERATIONS/
FINANCE); a caller outside that role set gets that function's own real
error dict passed straight through.

Enriched 2026-07-18 (Gap Analysis root-cause/revenue-impact slice, slice 3):
`_dollar_conversion()` now computes `is_opportunity` via
core/network_benchmark.py's shared `gap_direction()` instead of a bare
`gap > 0` check -- this was a real, previously-flagged-but-not-fixed bug for
the bhph department's 3 lower-is-better rate KPIs (delinquency_rate_pct/
repo_rate_pct/charge_off_rate_pct): a positive gap there means THIS dealer's
rate is already below (better than) the peer average, not behind it, and the
old bare check would have mislabeled that as an opportunity. Every dollar
figure elsewhere in this module (Overview/Opportunities' totals, the
Executive Summary) flows through `_dollar_conversion()`, so this fix applies
everywhere in this module too, not just Gap Analysis. Also added two new,
narrowly-scoped real revenue-impact chains, both reusing this module's own
real per-unit-value discipline rather than inventing a new one:
`_sales_rate_unit_impact()` (Sales' close_rate/show_rate percentage-point
gaps chained through this dealer's own real monthly lead volume,
core/performance_readiness.py's `get_current_month_pace('marketing')`, into
a real "N more sale(s)/appointment(s) shown per month" figure -- close_rate
additionally chains into a real derived monthly dollar figure via this
dealer's own real `gross_profit_per_unit`, matching Sam's own "18 more
sales/month, $84,000 additional gross/month" framing) and
`_bhph_exposure_impact()` (the bhph department's 3 lower-is-better rate
gaps chained through this dealer's own real outstanding portfolio balance,
core/loan_servicing_api.py's `get_portfolio_dashboard_api()`, into a real
ONE-TIME dollars-at-risk reduction figure -- deliberately kept SEPARATE from
`dollar_impact_monthly`, since a portfolio-balance-scaled figure is a stock
reduction, not a recurring monthly flow, and presenting it as "/month" would
misrepresent its real time basis).
"""

from core.network_api import get_network_benchmarks_api, get_network_audit_api
from core.network_benchmark import gap_direction, get_bhph_outstanding_balance
from core.network_summary_wizard import polish_network_executive_summary


# Departments whose real cross-dealer dollar totals should be summed into one
# grand total. "executive" is deliberately excluded -- see module docstring.
EXCLUDED_FROM_GRAND_TOTAL = {"executive"}

_EXCLUDED_REASON = (
    "Executive is a real cross-department ROLLUP of Sales + Service + Parts + "
    "F&I gross profit (core/department_intelligence.py's compute_executive_kpis()) "
    "-- including its own dollar gap in the grand total would double-count the "
    "same real dollars already counted in those 4 departments."
)

# The only honest real-per-unit-dollar-value pairings this codebase has for a
# "number"-format (count) KPI gap. "direct": the value KPI is already a
# ready-made real per-unit currency figure on the SAME department's own
# kpis. "derived_ratio": the per-unit value is computed live from two other
# real KPIs already present in the same kpis dict (currency_kpi / count_kpi)
# -- e.g. Service has no standalone "gross per RO" KPI, but total_gross
# (currency) / ro_count (number) is a real, honestly-derived one.
_COUNT_KPI_TO_DOLLAR_VALUE = {
    ("sales", "units_sold"): {"mode": "direct", "value_kpi": "gross_profit_per_unit"},
    ("sales", "projected_month_end_units"): {"mode": "direct", "value_kpi": "gross_profit_per_unit"},
    ("fi", "deals_financed"): {"mode": "direct", "value_kpi": "income_per_contract"},
    ("service", "ro_count"): {"mode": "derived_ratio", "currency_kpi": "total_gross", "count_kpi": "ro_count"},
}

_NOT_CONVERTIBLE_NUMBER_REASON = (
    "No real per-unit dollar value exists on this department's own KPIs to "
    "convert this count gap into a dollar estimate."
)


def _not_convertible_reason(kpi_key, format_):

    return (
        f"'{kpi_key}' is a {format_ or 'non-currency'}-shaped metric with no "
        "real, already-computed dollar-per-point (or dollar-per-turn) "
        "multiplier anywhere in this codebase -- converting it would require "
        "an invented ratio, not a real one, so it's reported honestly instead "
        "of guessed at."
    )


def _all_gaps(role):
    """Mirrors core/network_menu.py's gap_analysis() math exactly (see module
    docstring for why this isn't a direct call) -- every numeric KPI on every
    real benchmarked department, peer_average minus this dealer's value, plus
    the department's display title and a real peer_gap_pct (gap as a % of
    the peer average, guarded against a zero peer average)."""

    result = get_network_benchmarks_api(role)

    if isinstance(result, dict) and "error" in result:
        return result

    gaps = []

    for entry in result.get("departments", []):

        department = entry["department"]
        department_title = entry.get("title", department)
        this_kpis = entry["this_dealer"]["kpis"]
        peers = entry.get("peers", [])

        for kpi_key, kpi_data in this_kpis.items():

            this_value = kpi_data.get("value")

            if not isinstance(this_value, (int, float)):
                continue

            peer_values = [p["kpis"].get(kpi_key, {}).get("value") for p in peers]
            peer_values = [v for v in peer_values if isinstance(v, (int, float))]

            if not peer_values:
                continue

            peer_avg = round(sum(peer_values) / len(peer_values), 2)
            gap = round(peer_avg - this_value, 2)
            peer_gap_pct = round(gap / peer_avg * 100, 1) if peer_avg else None

            gaps.append({
                "department": department,
                "department_title": department_title,
                "kpi": kpi_key,
                "label": kpi_data.get("label", kpi_key),
                "this_store": this_value,
                "peer_average": peer_avg,
                "gap": gap,
                "peer_gap_pct": peer_gap_pct,
                "format": kpi_data.get("format"),
            })

    return {"gaps": gaps}


def _dollar_conversion(department, kpi_key, format_, gap, this_store_lookup):
    """Returns the real/derived/not-convertible dollar conversion for one
    gap entry -- see module docstring for the 3 categories. `is_opportunity`/
    `opportunity_gap` are computed via core/network_benchmark.py's shared
    gap_direction() (not a bare `gap > 0` check) so a lower-is-better KPI
    (bhph's delinquency/repo/charge-off rates, parts' obsolete_inventory_pct,
    sales' lead_response_time_minutes) is never mislabeled -- see this
    module's own docstring for the fix."""

    direction = gap_direction(department, kpi_key, gap)
    is_opportunity = direction["is_opportunity"]
    opportunity_gap = direction["opportunity_gap"]
    common = {
        "is_opportunity": is_opportunity,
        "opportunity_gap": opportunity_gap,
        "higher_is_better": direction["higher_is_better"],
        "direction": direction["direction"],
    }

    if format_ == "currency":
        return {
            **common,
            "dollar_impact_monthly": round(opportunity_gap, 2) if is_opportunity else 0.0,
            "conversion_method": "direct_currency",
            "real_inputs_used": {"gap_dollars": gap},
            "not_convertible_reason": None,
        }

    if format_ == "number":

        mapping = _COUNT_KPI_TO_DOLLAR_VALUE.get((department, kpi_key))

        if mapping:

            if mapping["mode"] == "direct":
                per_unit_value = this_store_lookup.get((department, mapping["value_kpi"]))
                source_note = f"this dealer's own real '{mapping['value_kpi']}'"
            else:
                cur = this_store_lookup.get((department, mapping["currency_kpi"]))
                cnt = this_store_lookup.get((department, mapping["count_kpi"]))
                per_unit_value = (
                    cur / cnt
                    if isinstance(cur, (int, float)) and isinstance(cnt, (int, float)) and cnt
                    else None
                )
                source_note = (
                    f"this dealer's own real '{mapping['currency_kpi']}' / "
                    f"'{mapping['count_kpi']}'"
                )

            if isinstance(per_unit_value, (int, float)):

                dollar = round(opportunity_gap * per_unit_value, 2) if is_opportunity else 0.0

                return {
                    **common,
                    "dollar_impact_monthly": dollar,
                    "conversion_method": "derived_per_unit_real_value",
                    "real_inputs_used": {
                        "gap_units": opportunity_gap if is_opportunity else gap,
                        "per_unit_value": round(per_unit_value, 2),
                        "per_unit_value_source": source_note,
                        "formula": "dollar_impact_monthly = gap_units * per_unit_value",
                    },
                    "not_convertible_reason": None,
                }

        return {
            **common,
            "dollar_impact_monthly": None,
            "conversion_method": "not_convertible_to_dollars",
            "real_inputs_used": None,
            "not_convertible_reason": _NOT_CONVERTIBLE_NUMBER_REASON,
        }

    return {
        **common,
        "dollar_impact_monthly": None,
        "conversion_method": "not_convertible_to_dollars",
        "real_inputs_used": None,
        "not_convertible_reason": _not_convertible_reason(kpi_key, format_),
    }


# ---------------------------------------------------------------------------
# Real, narrowly-scoped revenue-impact chains (Gap Analysis root-cause/
# revenue-impact slice) -- see module docstring for the full reasoning.
# ---------------------------------------------------------------------------

_SALES_RATE_UNIT_LABELS = {
    "close_rate": "sale(s)",
    "show_rate": "appointment(s) shown",
}

_BHPH_EXPOSURE_KPIS = {"delinquency_rate_pct", "repo_rate_pct", "charge_off_rate_pct"}


def _sales_rate_unit_impact(kpi_key, opportunity_gap_pct, this_store_lookup):
    """Real 'N more sale(s)/appointment(s) shown per month' for Sales'
    close_rate/show_rate percentage-point gaps -- chain:
    additional_units_monthly = (opportunity_gap_percentage_points / 100) *
    this dealer's own real monthly lead volume
    (core/performance_readiness.py's real linear calendar-month run-rate).
    close_rate additionally chains into a real derived monthly dollar figure
    via this dealer's own real 'gross_profit_per_unit' KPI -- matching Sam's
    own '18 more sales/month, $84,000 additional gross/month' framing.
    Deliberately does NOT chain show_rate into a dollar figure -- that would
    require compounding it through close_rate too (an appointment shown
    isn't a sale), a second, unsupported assumption this module's own
    discipline avoids."""

    if kpi_key not in _SALES_RATE_UNIT_LABELS or not opportunity_gap_pct:
        return None

    from core.performance_readiness import get_current_month_pace

    pace = get_current_month_pace("marketing")
    monthly_leads = pace.get("projected_month_total") if isinstance(pace, dict) else None

    if not isinstance(monthly_leads, (int, float)) or monthly_leads <= 0:
        return None

    additional_units = round((opportunity_gap_pct / 100.0) * monthly_leads, 1)

    result = {
        "additional_units_monthly": additional_units,
        "unit_label": _SALES_RATE_UNIT_LABELS[kpi_key],
        "derived_dollar_impact_monthly": None,
        "derived_dollar_impact_annualized": None,
        "real_inputs_used": {
            "opportunity_gap_percentage_points": opportunity_gap_pct,
            "monthly_lead_volume": monthly_leads,
            "monthly_lead_volume_source": (
                "this dealer's own real monthly lead volume -- "
                "core/performance_readiness.py's linear calendar-month "
                "run-rate, get_current_month_pace('marketing')"
            ),
            "formula": "additional_units_monthly = (opportunity_gap_percentage_points / 100) * monthly_lead_volume",
        },
    }

    if kpi_key == "close_rate":

        gross_per_unit = this_store_lookup.get(("sales", "gross_profit_per_unit"))

        if isinstance(gross_per_unit, (int, float)):

            additional_gross = round(additional_units * gross_per_unit, 2)

            result["derived_dollar_impact_monthly"] = additional_gross
            result["derived_dollar_impact_annualized"] = round(additional_gross * 12, 2)
            result["real_inputs_used"]["gross_profit_per_unit"] = round(gross_per_unit, 2)
            result["real_inputs_used"]["gross_profit_per_unit_source"] = (
                "this dealer's own real 'gross_profit_per_unit' KPI"
            )
            result["real_inputs_used"]["formula_dollar"] = (
                "derived_dollar_impact_monthly = additional_units_monthly * gross_profit_per_unit"
            )

    return result


def _bhph_exposure_impact(kpi_key, opportunity_gap_pct, role):
    """Real ONE-TIME dollars-at-risk reduction for the bhph department's 3
    lower-is-better rate gaps -- chain: dollars_at_risk_reduction =
    (opportunity_gap_percentage_points / 100) * this dealer's own real
    outstanding portfolio balance (core/loan_servicing_api.py). Deliberately
    labeled a ONE-TIME reduction on the current portfolio stock, not a
    recurring monthly flow -- kept separate from dollar_impact_monthly for
    that reason (see module docstring)."""

    if kpi_key not in _BHPH_EXPOSURE_KPIS or not opportunity_gap_pct:
        return None

    outstanding = get_bhph_outstanding_balance(role)

    if not isinstance(outstanding, (int, float)) or not outstanding:
        return None

    dollars_at_risk_reduction = round((opportunity_gap_pct / 100.0) * outstanding, 2)

    return {
        "dollars_at_risk_reduction": dollars_at_risk_reduction,
        "basis": "one_time_reduction_on_current_outstanding_balance",
        "real_inputs_used": {
            "opportunity_gap_percentage_points": opportunity_gap_pct,
            "outstanding_portfolio_balance": outstanding,
            "outstanding_portfolio_balance_source": (
                "this dealer's own real total_outstanding_balance "
                "(core/loan_servicing_api.py's get_portfolio_dashboard_api())"
            ),
            "formula": "dollars_at_risk_reduction = (opportunity_gap_percentage_points / 100) * outstanding_portfolio_balance",
        },
        "note": (
            "A ONE-TIME reduction in current dollars-at-risk on the existing "
            "portfolio balance, not a recurring monthly figure -- shown "
            "separately from dollar_impact_monthly for that reason."
        ),
    }


_BASIS_NOTICE = (
    "Dollar figures are computed against SIMULATED peer benchmarks "
    "(blind-labeled Dealer B/C/D/E, core/network_benchmark.py) -- real once a "
    "second NXTDeal dealer connects and reports its own Department "
    "Intelligence KPIs the same way. Every dollar_impact_monthly is either "
    "the gap itself (already currency-shaped) or gap_units * this dealer's "
    "own real per-unit dollar value -- never peer data or an invented "
    "multiplier. 'annualized' is simply monthly * 12, a projection of the "
    "CURRENT monthly gap held steady for a year, not a guaranteed outcome."
)


def get_dollar_denominated_gaps(role):
    """Every real gap, enriched with its honest dollar conversion. Sorted by
    dollar_impact_monthly descending (None/not-convertible entries sort
    last)."""

    raw = _all_gaps(role)

    if isinstance(raw, dict) and "error" in raw:
        return raw

    gaps = raw["gaps"]
    lookup = {(g["department"], g["kpi"]): g["this_store"] for g in gaps}

    enriched = []

    for g in gaps:

        conversion = _dollar_conversion(g["department"], g["kpi"], g["format"], g["gap"], lookup)

        unit_impact = None
        portfolio_exposure_impact = None

        if conversion["is_opportunity"] and g["format"] == "percent":

            opportunity_gap_pct = conversion["opportunity_gap"]

            if g["department"] == "sales":
                unit_impact = _sales_rate_unit_impact(g["kpi"], opportunity_gap_pct, lookup)
            elif g["department"] == "bhph":
                portfolio_exposure_impact = _bhph_exposure_impact(g["kpi"], opportunity_gap_pct, role)

        # A real derived dollar figure from the unit-impact chain (close_rate
        # only) becomes the headline dollar_impact_monthly -- this is the
        # BEST real estimate available for that gap, not a second competing
        # number left buried inside unit_impact.
        if unit_impact and unit_impact.get("derived_dollar_impact_monthly") is not None:
            conversion = {
                **conversion,
                "dollar_impact_monthly": unit_impact["derived_dollar_impact_monthly"],
                "conversion_method": "derived_rate_x_volume_x_per_unit_value",
                "not_convertible_reason": None,
            }

        monthly = conversion["dollar_impact_monthly"]
        annualized = round(monthly * 12, 2) if isinstance(monthly, (int, float)) else None

        enriched.append({
            **g,
            **conversion,
            "annualized_dollar_impact": annualized,
            "excluded_from_grand_total": g["department"] in EXCLUDED_FROM_GRAND_TOTAL,
            "unit_impact": unit_impact,
            "portfolio_exposure_impact": portfolio_exposure_impact,
        })

    enriched.sort(
        key=lambda g: g["dollar_impact_monthly"] if isinstance(g["dollar_impact_monthly"], (int, float)) else -1,
        reverse=True,
    )

    return {"gaps": enriched, "basis_notice": _BASIS_NOTICE}


def get_department_dollar_opportunities(role):
    """Real per-department monthly/annualized dollar opportunity totals --
    only summing gaps this dealer is actually behind on (is_opportunity) and
    that had a real or derived dollar conversion. Executive is reported but
    excluded_from_grand_total=True, see module docstring."""

    result = get_dollar_denominated_gaps(role)

    if isinstance(result, dict) and "error" in result:
        return result

    by_dept = {}

    for g in result["gaps"]:

        d = g["department"]
        entry = by_dept.setdefault(d, {
            "department": d,
            "department_title": g["department_title"],
            "monthly_total": 0.0,
            "convertible_gap_count": 0,
            "not_convertible_gap_count": 0,
        })

        if g["dollar_impact_monthly"] is not None:
            entry["convertible_gap_count"] += 1
            if g["is_opportunity"]:
                entry["monthly_total"] += g["dollar_impact_monthly"]
        else:
            entry["not_convertible_gap_count"] += 1

    grand_total_monthly = 0.0
    departments = []

    for d, entry in by_dept.items():

        monthly = round(entry["monthly_total"], 2)
        annualized = round(monthly * 12, 2)
        excluded = d in EXCLUDED_FROM_GRAND_TOTAL

        if not excluded:
            grand_total_monthly += monthly

        departments.append({
            "department": d,
            "department_title": entry["department_title"],
            "monthly_opportunity": monthly,
            "annualized_opportunity": annualized,
            "convertible_gap_count": entry["convertible_gap_count"],
            "not_convertible_gap_count": entry["not_convertible_gap_count"],
            "excluded_from_grand_total": excluded,
            "excluded_reason": _EXCLUDED_REASON if excluded else None,
        })

    departments.sort(key=lambda d: d["annualized_opportunity"], reverse=True)

    return {
        "departments": departments,
        "grand_total_monthly_opportunity": round(grand_total_monthly, 2),
        "grand_total_annualized_opportunity": round(grand_total_monthly * 12, 2),
        "basis_notice": _BASIS_NOTICE,
    }


def get_total_identified_opportunity(role):
    """Sam's 'Total Identified Opportunity' -- a single real, annualized
    grand total across every non-excluded department."""

    dept_opps = get_department_dollar_opportunities(role)

    if isinstance(dept_opps, dict) and "error" in dept_opps:
        return dept_opps

    return {
        "total_monthly_opportunity": dept_opps["grand_total_monthly_opportunity"],
        "total_annualized_opportunity": dept_opps["grand_total_annualized_opportunity"],
        "excluded_departments": [
            d["department"] for d in dept_opps["departments"] if d["excluded_from_grand_total"]
        ],
        "basis_notice": _BASIS_NOTICE,
    }


def get_largest_opportunities(role, limit=5):
    """Sam's 'Largest Opportunities' list -- the top N real/derived-dollar
    gaps this dealer is actually behind peer average on, ranked by monthly
    dollar impact. Not-convertible gaps never appear here (they have no
    dollar figure to rank by)."""

    result = get_dollar_denominated_gaps(role)

    if isinstance(result, dict) and "error" in result:
        return result

    convertible_opportunities = [
        g for g in result["gaps"]
        if g["is_opportunity"] and isinstance(g["dollar_impact_monthly"], (int, float)) and g["dollar_impact_monthly"] > 0
    ]

    return {
        "largest_opportunities": convertible_opportunities[:limit],
        "basis_notice": result["basis_notice"],
    }


# ---------------------------------------------------------------------------
# Executive Summary -- a REAL, RULES-BASED templated narrative (same standing
# "real, transparent, no fabricated ML" convention core/network_audit.py and
# this reframe session's core/readiness_overview.py both already established),
# composed from percentile rank + the real dollar-opportunity data above +
# core/network_audit.py's own real recommendation feed. Always correct and
# complete on its own -- the optional AI polish step (core/
# network_summary_wizard.py, same isolation/fallback pattern as core/
# email_wizard.py/core/readiness_summary_wizard.py) may smooth phrasing only,
# never invent a fact, and its fallback (used whenever OpenAI can't be
# reached, which is every time in this sandbox) is this exact real template.
# ---------------------------------------------------------------------------

def _build_raw_executive_summary(role):

    benchmarks = get_network_benchmarks_api(role)

    if isinstance(benchmarks, dict) and "error" in benchmarks:
        return benchmarks

    ranks = [d["percentile_rank"] for d in benchmarks.get("departments", []) if d["percentile_rank"] is not None]
    avg_percentile = round(sum(ranks) / len(ranks), 1) if ranks else None
    top_pct = round(100 - avg_percentile, 1) if avg_percentile is not None else None

    dept_opps = get_department_dollar_opportunities(role)

    if isinstance(dept_opps, dict) and "error" in dept_opps:
        return dept_opps

    largest = get_largest_opportunities(role, limit=3)

    if isinstance(largest, dict) and "error" in largest:
        return largest

    audit = get_network_audit_api(role)
    recs = audit.get("recommendations", [])[:2] if isinstance(audit, dict) else []

    if avg_percentile is not None:
        sentence1 = (
            f"Your dealership ranks in the {avg_percentile}th percentile of the "
            f"(simulated) peer set overall"
            + (f", roughly the top {top_pct}%." if top_pct is not None else ".")
        )
    else:
        sentence1 = "Overall percentile rank could not be computed -- no covered department has a peer comparison yet."

    top_gaps = largest.get("largest_opportunities", [])[:2]

    if top_gaps:
        gap_phrases = []
        for g in top_gaps:
            pct = g.get("peer_gap_pct")
            pct_txt = f" is below peer average by {pct}%" if pct is not None else " is below peer average"
            gap_phrases.append(f"{g['department_title']} {g['label']}{pct_txt}")
        sentence2 = " ".join(f"{p}." for p in gap_phrases)
    else:
        sentence2 = "No department currently has a dollar-convertible gap behind the (simulated) peer average."

    if recs:
        cause_txt = " ".join(r["finding"] for r in recs if r.get("finding"))
        sentence3 = f"Primary causes flagged by the network audit: {cause_txt}"
    else:
        sentence3 = "No network-audit recommendations are currently triggered."

    total = dept_opps.get("grand_total_annualized_opportunity")

    if total:
        sentence4 = (
            f"Estimated annual opportunity: ${total:,.0f} -- a real, formula-derived "
            "projection (see the per-department breakdown for the exact real inputs "
            "and multipliers used), not a guaranteed outcome."
        )
    else:
        sentence4 = "No dollar-convertible opportunity is currently identified across the covered departments."

    text = f"{sentence1} {sentence2} {sentence3} {sentence4}"

    return {
        "text": text,
        "basis": "real",
        "facts": {
            "avg_percentile": avg_percentile,
            "top_pct": top_pct,
            "top_gaps": top_gaps,
            "top_recommendations": recs,
            "total_annualized_opportunity": total,
        },
    }


def generate_executive_summary(role, polish=True):
    """Always returns a real, correct summary -- polish is additive, never
    load-bearing. polish=False skips the OpenAI call entirely (used by the
    on-demand 'regenerate without AI' action)."""

    raw = _build_raw_executive_summary(role)

    if isinstance(raw, dict) and "error" in raw:
        return raw

    if not polish:
        return {**raw, "summary": raw["text"], "ai_generated": False}

    polished = polish_network_executive_summary(raw["text"])

    if not isinstance(polished, dict) or polished.get("error") or not polished.get("summary"):
        note = (
            polished.get("error") if isinstance(polished, dict) else None
        ) or "AI polish unavailable -- showing the real templated summary."
        return {**raw, "summary": raw["text"], "ai_generated": False, "ai_polish_note": note}

    return {**raw, "summary": polished["summary"], "ai_generated": True}
