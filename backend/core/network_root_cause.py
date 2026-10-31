"""
core/network_root_cause.py -- Root Cause Analysis for Network's Gap Analysis
item (2026-07-18, "NXTDeal Intelligence Network" reframe, slice 3). Sam's
own spec: instead of just "Gap Exists," show "Likely Causes: Slow Lead
Response, Low SMS Utilization, Poor Follow-Up Compliance."

Every cause below is a real, transparent, threshold-based diagnostic check
over an already-built engine elsewhere in this codebase -- never a
fabricated plausible-sounding sentence, matching the "real rules, not fake
AI" convention core/network_audit.py/core/collections.py's risk scoring/
core/readiness_recommendations.py already established. A diagnostic
function returns None when its own real signal doesn't indicate a problem
(so a KPI's causes list can legitimately come back empty even when a
diagnostic IS mapped to it -- that's a real "checked, nothing found"
result, not a missing mapping), or a real, numbered finding when it does.

_ROOT_CAUSE_MAP is a small, explicit (department, kpi_key) -> [diagnostic
function, ...] catalog, built only from real signals this codebase already
computes elsewhere:

  - Sales: core/bdc.py's real speed-to-lead measurement and untouched-lead
    queue, core/follow_up_dashboard.py's real stale-follow-up queue, and a
    new (this module) real Appointment-reminder-usage check off
    core/appointments.py's real `reminders_sent` records.
  - Service: core/shop_control.py's real technician-utilization/stalled-RO
    checks, and a new (this module) real DVI-completion-rate check off
    core/vehicle_inspection.py's real per-RO `dvi` state.
  - Parts: core/parts_desk.py's real understocked-fast-mover reorder signal.
  - F&I: core/fi_products.py's real "deals with no F&I menu presented yet"
    queue.
  - BHPH: a new (this module) real "delinquent loans with no collection
    stage ever explicitly worked" check and a real broken-promise-to-pay
    count, both off core/collections.py's real Work Queue.

A KPI with no entry (or an entry whose every diagnostic returns None) gets
an honest "no specific root-cause diagnostic available for this KPI yet"
note -- never a guessed cause. Executive department KPIs are cross-department
rollups (core/department_intelligence.py's compute_executive_kpis()) and are
handled specially -- pointing back at the real per-department root causes
already surfaced above, rather than a duplicate diagnostic pass.

This module makes ZERO graph mutations -- every diagnostic here is a pure,
read-only calculation over already-real data (or, for reminder sends, a
real count of a SIMULATED-labeled staff action -- see
core/appointment_scheduling.py's own module docstring; the SEND is
simulated, but whether staff actually triggered one is a real, checkable
fact about this dealer's own behavior, not fabricated).
"""

from core.dealeros import ledger
from core.entity_types import SERVICE_RECORD
from core.bdc import get_response_time_stats, get_untouched_queue, URGENT_MINUTES
from core.follow_up_dashboard import get_follow_up_dashboard
from core.appointments import list_appointments
from core.shop_control import get_technician_utilization, get_stalled_ros
from core.repair_orders import _stage_of


# --- thresholds -- reasonable rule-of-thumb figures, same "not sourced from
# a specific citation" honesty bar as core/prediction.py's
# INDUSTRY_BASELINES / core/network_benchmark.py's BASELINE_PRIMARY_KPI_VALUE.
# ---------------------------------------------------------------------------

_SLOW_RESPONSE_MINUTES = 60.0
_LOW_UNDER_TARGET_PCT = 50.0
_MIN_RESPONSE_SAMPLE = 3
_UNTOUCHED_LEAD_MIN_COUNT = 10
_LOW_REMINDER_USAGE_PCT = 40.0
_LOW_SMS_USAGE_PCT = 25.0
_MIN_APPOINTMENT_SAMPLE = 5
_STALE_FOLLOWUP_DAYS = 3
_HIGH_STALE_FOLLOWUP_PCT = 30.0
_MIN_FOLLOWUP_SAMPLE = 10
_OVERLOADED_UTILIZATION_PCT = 100.0
_MIN_TECH_SAMPLE = 2
_LOW_DVI_COMPLETION_PCT = 50.0
_MIN_LIVE_RO_SAMPLE = 5
_HIGH_UNWORKED_DELINQUENT_PCT = 50.0
_MIN_DELINQUENT_SAMPLE = 5


# --- Sales diagnostics ------------------------------------------------------

def _diag_slow_lead_response():

    stats = get_response_time_stats()
    avg = stats.get("average_minutes")
    sample = stats.get("sample_size", 0)

    if avg is None or sample < _MIN_RESPONSE_SAMPLE:
        return None

    under_target = stats.get("under_target_pct")

    if avg > _SLOW_RESPONSE_MINUTES or (under_target is not None and under_target < _LOW_UNDER_TARGET_PCT):
        return {
            "key": "slow_lead_response",
            "label": "Slow Lead Response",
            "finding": (
                f"Average speed-to-lead is {avg} minute(s) across {sample} real "
                f"contacted internet lead(s) (only {under_target}% under the real "
                f"{URGENT_MINUTES}-minute urgent-response target)."
            ),
            "basis": "real",
            "supporting_data": stats,
        }

    return None


def _diag_untouched_leads():

    queue = get_untouched_queue()
    count = len(queue)

    if count >= _UNTOUCHED_LEAD_MIN_COUNT:
        return {
            "key": "untouched_lead_backlog",
            "label": "Untouched Lead Backlog",
            "finding": (
                f"{count} real internet lead(s) are still untouched (PipelineState="
                "NEW -- nobody has made first contact yet)."
            ),
            "basis": "real",
            "supporting_data": {"untouched_count": count},
        }

    return None


def _diag_follow_up_compliance():

    queue = get_follow_up_dashboard()
    total = len(queue)

    if total < _MIN_FOLLOWUP_SAMPLE:
        return None

    stale = [
        q for q in queue
        if isinstance(q.get("days_in_state"), (int, float)) and q["days_in_state"] >= _STALE_FOLLOWUP_DAYS
    ]
    pct_stale = round(100 * len(stale) / total, 1) if total else 0.0

    if pct_stale >= _HIGH_STALE_FOLLOWUP_PCT:
        return {
            "key": "poor_follow_up_compliance",
            "label": "Poor Follow-Up Compliance",
            "finding": (
                f"{len(stale)} of {total} real open lead(s) ({pct_stale}%) have sat in "
                f"their current pipeline state for {_STALE_FOLLOWUP_DAYS}+ day(s) -- a "
                "real signal that follow-up cadence isn't keeping leads moving."
            ),
            "basis": "real",
            "supporting_data": {"total_open_leads": total, "stale_count": len(stale), "pct_stale": pct_stale},
        }

    return None


def _reminder_usage(department):

    appts = list_appointments(department=department)

    if len(appts) < _MIN_APPOINTMENT_SAMPLE:
        return None

    with_any = [a for a in appts if a.attributes.get("reminders_sent")]
    with_sms = [
        a for a in appts
        if any(r.get("channel") == "sms" for r in (a.attributes.get("reminders_sent") or []))
    ]

    pct_any = round(100 * len(with_any) / len(appts), 1)
    pct_sms = round(100 * len(with_sms) / len(appts), 1)

    return {
        "appointment_count": len(appts),
        "with_any_reminder": len(with_any),
        "pct_any_reminder": pct_any,
        "with_sms_reminder": len(with_sms),
        "pct_sms_reminder": pct_sms,
    }


def _diag_low_reminder_usage(department):

    stats = _reminder_usage(department)

    if stats is None or stats["pct_any_reminder"] >= _LOW_REMINDER_USAGE_PCT:
        return None

    return {
        "key": "low_appointment_reminder_usage",
        "label": "Low Appointment Reminder Usage",
        "finding": (
            f"Only {stats['pct_any_reminder']}% of {stats['appointment_count']} real "
            f"{department} appointment(s) have any reminder logged (SMS/email/call "
            "combined, core/appointment_scheduling.py's real, per-appointment "
            "reminder record)."
        ),
        "basis": "real_staff_action_count",
        "supporting_data": stats,
    }


def _diag_low_sms_utilization(department):

    stats = _reminder_usage(department)

    if stats is None or stats["pct_sms_reminder"] >= _LOW_SMS_USAGE_PCT:
        return None

    return {
        "key": "low_sms_utilization",
        "label": "Low SMS Utilization",
        "finding": (
            f"Only {stats['pct_sms_reminder']}% of {stats['appointment_count']} real "
            f"{department} appointment(s) have an SMS reminder logged specifically "
            f"(vs. {stats['pct_any_reminder']}% via any channel)."
        ),
        "basis": "real_staff_action_count",
        "supporting_data": stats,
    }


def _diag_low_reminder_usage_sales():
    return _diag_low_reminder_usage("Sales")


def _diag_low_sms_utilization_sales():
    return _diag_low_sms_utilization("Sales")


def _diag_low_reminder_usage_service():
    return _diag_low_reminder_usage("Service")


# --- Service diagnostics ----------------------------------------------------

def _diag_technician_overload():

    util = get_technician_utilization()
    techs = util.get("technicians") or []

    if len(techs) < _MIN_TECH_SAMPLE:
        return None

    avg_pct = round(sum(t["utilization_pct"] for t in techs) / len(techs), 1)
    overloaded = [t for t in techs if t.get("overloaded")]

    if avg_pct > _OVERLOADED_UTILIZATION_PCT or len(overloaded) >= max(1, len(techs) // 2):
        return {
            "key": "technician_overcapacity",
            "label": "Technician Overcapacity",
            "finding": (
                f"Average technician utilization today is {avg_pct}% of the assumed "
                f"{techs[0]['assumed_capacity_hours']}-hour/day capacity across "
                f"{len(techs)} real technician(s) ({len(overloaded)} over capacity) -- "
                "a real shop-throughput bottleneck signal."
            ),
            "basis": "real_heuristic_capacity",
            "supporting_data": {
                "avg_utilization_pct": avg_pct,
                "technician_count": len(techs),
                "overloaded_count": len(overloaded),
            },
        }

    return None


def _diag_low_dvi_completion():

    records = [e for e in ledger.get_all().values() if e.entity_type == SERVICE_RECORD]
    live = [r for r in records if _stage_of(r) != "Follow-Up"]

    if len(live) < _MIN_LIVE_RO_SAMPLE:
        return None

    started = [r for r in live if (r.attributes.get("dvi") or {}).get("status") in ("in_progress", "completed")]
    completed = [r for r in live if (r.attributes.get("dvi") or {}).get("status") == "completed"]
    pct_completed = round(100 * len(completed) / len(live), 1)

    if pct_completed < _LOW_DVI_COMPLETION_PCT:
        return {
            "key": "low_dvi_completion",
            "label": "Low DVI Completion Rate",
            "finding": (
                f"Only {pct_completed}% of {len(live)} real live repair order(s) have "
                f"a completed Digital Vehicle Inspection ({len(started)} started, "
                f"{len(completed)} completed) -- fewer real inspection-driven upsell "
                "opportunities are being surfaced (core/vehicle_inspection.py)."
            ),
            "basis": "real",
            "supporting_data": {
                "live_ro_count": len(live),
                "started_count": len(started),
                "completed_count": len(completed),
                "pct_completed": pct_completed,
            },
        }

    return None


def _diag_stalled_ros():

    stalled = get_stalled_ros()
    count = stalled.get("count", 0)

    if count > 0:
        return {
            "key": "stalled_repair_orders",
            "label": "Repair Order Bottlenecks",
            "finding": (
                f"{count} real repair order(s) have been open "
                f"{stalled['hours_threshold']}+ hour(s) with zero labor posted."
            ),
            "basis": "real",
            "supporting_data": {"stalled_count": count, "hours_threshold": stalled["hours_threshold"]},
        }

    return None


# --- Parts diagnostics -------------------------------------------------------

def _diag_parts_understocked():

    from core.parts_desk import get_inventory_recommendations

    result = get_inventory_recommendations(limit=1000)
    count = result.get("count", 0)

    if count > 0:
        return {
            "key": "understocked_fast_moving_parts",
            "label": "Understocked Fast-Moving Parts",
            "finding": (
                f"{count} real part(s) with active real sales velocity are at or "
                "near stockout (core/parts_desk.py's reorder signal, "
                "PartSale velocity vs. Part.QuantityOnHand) -- likely lost parts "
                "sales."
            ),
            "basis": "real",
            "supporting_data": {"understocked_part_count": count},
        }

    return None


# --- F&I diagnostics ---------------------------------------------------------

def _diag_fi_menu_not_presented():

    from core.fi_products import list_deals_needing_fi_menu

    deals = list_deals_needing_fi_menu(limit=1000)
    count = len(deals)

    if count > 0:
        return {
            "key": "fi_menu_not_presented",
            "label": "F&I Menu Not Presented",
            "finding": (
                f"{count} real deal(s) currently in financing/contract status have "
                "no F&I product menu on file yet (core/fi_products.py)."
            ),
            "basis": "real",
            "supporting_data": {"deals_missing_menu": count},
        }

    return None


# --- BHPH diagnostics ---------------------------------------------------------

def _diag_unworked_delinquent_accounts():

    from core.collections import get_collection_queue

    queue = get_collection_queue()
    loans = queue.get("loans") or []
    total = len(loans)

    if total < _MIN_DELINQUENT_SAMPLE:
        return None

    unworked = 0
    for row in loans:
        loan = ledger.get_entity(row["loan_id"])
        if loan and not loan.attributes.get("collection_stage"):
            unworked += 1

    pct_unworked = round(100 * unworked / total, 1) if total else 0.0

    if pct_unworked >= _HIGH_UNWORKED_DELINQUENT_PCT:
        return {
            "key": "unworked_delinquent_accounts",
            "label": "Unworked Delinquent Accounts",
            "finding": (
                f"{unworked} of {total} real delinquent loan(s) in the Work Queue "
                f"({pct_unworked}%) have no collection stage ever explicitly "
                "advanced by staff (core/collections.py's real "
                "advance_collection_stage()) -- a real gap in active collections "
                "outreach."
            ),
            "basis": "real",
            "supporting_data": {
                "delinquent_loan_count": total,
                "unworked_count": unworked,
                "pct_unworked": pct_unworked,
            },
        }

    return None


def _diag_broken_promises():

    from core.collections import get_collection_queue, _broken_promises_count

    queue = get_collection_queue()
    loans = queue.get("loans") or []

    if len(loans) < _MIN_DELINQUENT_SAMPLE:
        return None

    broken_loans = [row for row in loans if _broken_promises_count(row["loan_id"]) > 0]
    count = len(broken_loans)

    if count > 0:
        return {
            "key": "broken_promises_to_pay",
            "label": "Broken Promises To Pay",
            "finding": (
                f"{count} of {len(loans)} real delinquent loan(s) in the Work Queue "
                "have at least one broken promise-to-pay on file "
                "(core/payments.py's PromiseToPay records)."
            ),
            "basis": "real",
            "supporting_data": {"broken_promise_loan_count": count, "delinquent_loan_count": len(loans)},
        }

    return None


# --- Catalog -----------------------------------------------------------------

_ROOT_CAUSE_MAP = {
    ("sales", "total_gross_profit"): [_diag_slow_lead_response, _diag_untouched_leads, _diag_follow_up_compliance],
    ("sales", "gross_profit_per_unit"): [_diag_slow_lead_response, _diag_follow_up_compliance],
    ("sales", "units_sold"): [_diag_slow_lead_response, _diag_untouched_leads, _diag_follow_up_compliance],
    ("sales", "avg_sale_price"): [],
    ("sales", "projected_month_end_units"): [_diag_slow_lead_response, _diag_untouched_leads, _diag_follow_up_compliance],
    ("sales", "close_rate"): [_diag_slow_lead_response, _diag_follow_up_compliance, _diag_low_reminder_usage_sales],
    ("sales", "show_rate"): [_diag_low_reminder_usage_sales, _diag_low_sms_utilization_sales],
    ("sales", "lead_response_time_minutes"): [],

    ("service", "total_gross"): [_diag_technician_overload, _diag_low_dvi_completion, _diag_stalled_ros],
    ("service", "avg_repair_order"): [_diag_low_dvi_completion],
    ("service", "ro_count"): [_diag_technician_overload, _diag_stalled_ros, _diag_low_reminder_usage_service],
    ("service", "hours_per_ro"): [_diag_technician_overload, _diag_stalled_ros],
    ("service", "customer_pay_pct"): [],
    ("service", "effective_labor_rate"): [],

    ("parts", "net_profit"): [_diag_parts_understocked],
    ("parts", "parts_sales"): [_diag_parts_understocked],
    ("parts", "gross_profit_per_unit"): [_diag_parts_understocked],
    ("parts", "inventory_turns"): [],
    ("parts", "obsolete_inventory_pct"): [],

    ("fi", "reserve_income"): [_diag_fi_menu_not_presented],
    ("fi", "income_per_contract"): [_diag_fi_menu_not_presented],
    ("fi", "reserve_per_vehicle"): [_diag_fi_menu_not_presented],
    ("fi", "deals_financed"): [_diag_fi_menu_not_presented],
    ("fi", "avg_apr"): [],

    ("bhph", "delinquency_rate_pct"): [_diag_unworked_delinquent_accounts, _diag_broken_promises],
    ("bhph", "repo_rate_pct"): [_diag_unworked_delinquent_accounts, _diag_broken_promises],
    ("bhph", "charge_off_rate_pct"): [_diag_unworked_delinquent_accounts, _diag_broken_promises],
    ("bhph", "recovery_rate_pct"): [],
    ("bhph", "yield_pct"): [],
}

_NO_DIAGNOSTIC_NOTE = "No specific root-cause diagnostic available for this KPI yet -- not guessed at."

_CLEAN_CHECK_NOTE = (
    "Real diagnostics were checked for this KPI and found no issue against "
    "their stated thresholds right now."
)

_EXECUTIVE_NOTE_TEMPLATE = (
    "'{label}' is a cross-department rollup (core/department_intelligence.py's "
    "compute_executive_kpis()) -- see the matching gap already surfaced under "
    "Sales/Service/Parts/F&I for the department(s) actually driving this, "
    "rather than a duplicate diagnostic pass here."
)


def get_root_causes(department, kpi_key, kpi_label=None):
    """Real, checked root causes for one (department, kpi_key) gap -- see
    module docstring for the full diagnostic catalog. Always returns a dict
    with `causes` (a list, possibly empty), `diagnostics_available` (whether
    ANY diagnostic is even mapped to this KPI), and `note` (an honest
    explanation when `causes` is empty, else None)."""

    if department == "executive":
        return {
            "causes": [],
            "diagnostics_available": False,
            "note": _EXECUTIVE_NOTE_TEMPLATE.format(label=kpi_label or kpi_key),
        }

    checks = _ROOT_CAUSE_MAP.get((department, kpi_key))

    if checks is None:
        return {"causes": [], "diagnostics_available": False, "note": _NO_DIAGNOSTIC_NOTE}

    if not checks:
        return {
            "causes": [],
            "diagnostics_available": False,
            "note": _NO_DIAGNOSTIC_NOTE,
        }

    causes = []
    for check in checks:
        result = check()
        if result:
            causes.append(result)

    if not causes:
        return {"causes": [], "diagnostics_available": True, "note": _CLEAN_CHECK_NOTE}

    return {"causes": causes, "diagnostics_available": True, "note": None}
