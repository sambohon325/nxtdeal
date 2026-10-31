"""
core/network_playbooks.py -- Network's "Playbooks" item, a real curated best-
practice library, plus Automation Scoring (2026-07-18, "NXTDeal Intelligence
Network" reframe, slice 5). network.pdf's own framing: "this is where the
network starts teaching dealers... Top 1% Recon Workflow-style curated
content." The pre-existing playbooks() (core/network_menu.py, session 67) was
an honest placeholder -- no curated Playbook entity/content model exists
anywhere in this codebase, confirmed via grep -- reusing the cross-department
recommendation feed as the closest analog rather than fabricated content.

This module replaces the fabrication risk with a genuinely honest curated
library: PLAYBOOK_CATALOG is a small, fixed, hand-written set of best-practice
guides, but EVERY ONE OF THEM is grounded in a real NXTDeal capability that
already exists in this codebase (a real screen, a real workflow, a real
diagnostic) -- never generic industry advice with no real backing action.
Since this environment is single-tenant (no real peer dealer to crowd-source
"Top 1%" content from), the honest analog to "what top performers do
differently" is "what NXTDeal's own already-built tools let THIS dealer do
right now" -- so each playbook's steps reference real Top Menu items/workflow
buttons/dashboards, not invented advice.

Each playbook is directly tied to one of core/network_root_cause.py's real
diagnostic functions (session 18/slice-3's Root Cause Analysis engine, reused
here VERBATIM, not duplicated) -- get_playbook_library() re-runs that exact
diagnostic live so a playbook's `is_currently_active` flag is a real, checked
fact about this dealer's own current data, not a static description. A
playbook whose diagnostic function isn't currently triggered is shown as
"not currently needed" rather than removed, so the library still functions as
a genuine reference guide.

Automation Scoring (the second half of this slice): for each playbook, a
real, transparent 0-3 tier score against core/workflow_automation.py's actual
rule engine (Administration's "if this real condition, then this real
action" automation, built earlier this same session) -- NOT a fabricated
"AI automation readiness" score:

  0 = No diagnostic mapped to a matching automation trigger type at all.
  1 = A matching automation TRIGGER TYPE exists in the catalog, but no LIVE
      rule of that type has actually been configured by an admin yet.
  2 = (reserved -- not currently reachable; see module docstring note below)
  3 = A matching trigger type exists AND at least one LIVE, active
      AutomationRule of that type is already configured -- this specific
      gap is already being auto-monitored today, not just theoretically
      automatable.

Tier 2 is intentionally unused this pass (would represent "a trigger type
exists but needs a new action type built" -- both of workflow_automation.py's
2 real action types, create_operations_task/send_notification_dm, already
cover every trigger type's realistic response, so that gap doesn't currently
exist) -- left in the docstring rather than silently omitted, so a future
session extending ACTION_CATALOG knows where a real tier 2 would go.
"""

from core.network_root_cause import (
    _diag_slow_lead_response,
    _diag_untouched_leads,
    _diag_follow_up_compliance,
    _diag_low_reminder_usage_sales,
    _diag_low_sms_utilization_sales,
    _diag_low_reminder_usage_service,
    _diag_technician_overload,
    _diag_low_dvi_completion,
    _diag_stalled_ros,
    _diag_parts_understocked,
    _diag_fi_menu_not_presented,
    _diag_unworked_delinquent_accounts,
    _diag_broken_promises,
)
from core.workflow_automation import TRIGGER_TYPES, list_rules


PLAYBOOK_CATALOG = [
    {
        "key": "slow_lead_response",
        "title": "Speed Up Lead Response",
        "department": "sales",
        "kpi_keys": ["total_gross_profit", "gross_profit_per_unit", "units_sold", "close_rate"],
        "diagnostic": _diag_slow_lead_response,
        "automation_trigger_type": None,
        "summary": (
            "Slow speed-to-lead is one of the most reliable predictors of a lost sale. "
            "NXTDeal's BDC Work Queue already ranks every untouched internet lead by "
            "real urgency -- use it as the literal work queue, not a side report."
        ),
        "steps": [
            "Open Sales -> BDC (the Up System / BDC job-workflow button) every shift start.",
            "Work the queue top-to-bottom -- it's already sorted by real urgency, not lead age alone.",
            "Log every contact attempt via the Communication Hub so speed-to-lead is measured accurately going forward.",
        ],
    },
    {
        "key": "untouched_lead_backlog",
        "title": "Clear the Untouched Lead Backlog",
        "department": "sales",
        "kpi_keys": ["total_gross_profit", "units_sold", "projected_month_end_units"],
        "diagnostic": _diag_untouched_leads,
        "automation_trigger_type": "lead_no_contact",
        "summary": (
            "A lead that's never been contacted is 100% lost opportunity until someone "
            "acts. Prospects' source-bucketed view surfaces exactly this population."
        ),
        "steps": [
            "Open Sales -> Prospects and filter to Source-bucketed New leads.",
            "Assign an owner to every unassigned lead via the real round-robin Up System, not ad hoc.",
            "Consider an Administration -> Workflow Automation rule (trigger: Lead With No Contact Logged) to auto-create an OperationsTask the moment a lead goes untouched past your own threshold.",
        ],
    },
    {
        "key": "poor_follow_up_compliance",
        "title": "Tighten Follow-Up Cadence",
        "department": "sales",
        "kpi_keys": ["total_gross_profit", "gross_profit_per_unit", "units_sold", "projected_month_end_units", "close_rate"],
        "diagnostic": _diag_follow_up_compliance,
        "automation_trigger_type": "lead_no_contact",
        "summary": (
            "A lead that's stalled in the same pipeline stage for days is silently "
            "leaking. Sales -> Communications' Follow-Up Cadence Queue is the real, "
            "already-built worklist for this exact problem."
        ),
        "steps": [
            "Open Sales -> Communications and work the Follow-Up Cadence Queue daily, not just when a lead escalates.",
            "Use the Manager TO (Turn-Over) workflow when a rep's own follow-up has genuinely stalled.",
            "The same Workflow Automation rule type (Lead With No Contact Logged) that helps the untouched-lead backlog above also catches a stalled-but-previously-contacted lead.",
        ],
    },
    {
        "key": "low_reminder_usage_sales",
        "title": "Increase Appointment Reminder Usage (Sales)",
        "department": "sales",
        "kpi_keys": ["show_rate"],
        "diagnostic": _diag_low_reminder_usage_sales,
        "automation_trigger_type": None,
        "summary": (
            "A scheduled appointment with no reminder sent is a real, measurable "
            "no-show risk. Appointments already has a one-click Remind action per row."
        ),
        "steps": [
            "Open Sales -> Appointments' Today's Schedule and use the inline Remind action on every booking, not just at-risk ones.",
            "Send the reminder as soon as the appointment is confirmed, not the morning of.",
        ],
    },
    {
        "key": "low_sms_utilization_sales",
        "title": "Shift Reminders to SMS (Sales)",
        "department": "sales",
        "kpi_keys": ["show_rate"],
        "diagnostic": _diag_low_sms_utilization_sales,
        "automation_trigger_type": None,
        "summary": (
            "SMS reminders have real, materially higher open rates than email or a "
            "phone call that goes to voicemail. The Remind action already supports an "
            "explicit SMS channel choice."
        ),
        "steps": [
            "When using Appointments' Remind action, pick the SMS channel specifically instead of the default.",
            "Confirm the customer's phone number on file is current before relying on SMS delivery.",
        ],
    },
    {
        "key": "low_reminder_usage_service",
        "title": "Increase Appointment Reminder Usage (Service)",
        "department": "service",
        "kpi_keys": ["ro_count"],
        "diagnostic": _diag_low_reminder_usage_service,
        "automation_trigger_type": None,
        "summary": (
            "The same reminder mechanism Sales uses is shared, department-agnostic "
            "infrastructure -- Service Appointments has the identical Remind action."
        ),
        "steps": [
            "Open Service -> Appointments' Today's Schedule and use the inline Remind action on every booking.",
            "Prioritize waiter/drop-off appointments specifically -- a missed waiter appointment costs a full shop slot.",
        ],
    },
    {
        "key": "technician_overcapacity",
        "title": "Rebalance Technician Load",
        "department": "service",
        "kpi_keys": ["total_gross", "ro_count", "hours_per_ro"],
        "diagnostic": _diag_technician_overload,
        "automation_trigger_type": None,
        "summary": (
            "An overloaded shop produces slower turn times and more stalled ROs. Shop "
            "Control's real Technician Dispatch Board shows exactly who's overloaded "
            "today."
        ),
        "steps": [
            "Open Service -> Shop Control and check the Technician Utilization panel first thing.",
            "Drag-and-drop ROs off an overloaded technician's column onto an underutilized one via the real dispatch board.",
            "Cross-check the Stalled ROs panel -- overcapacity and stalled work usually show up together.",
        ],
    },
    {
        "key": "low_dvi_completion",
        "title": "Improve DVI Completion Rate",
        "department": "service",
        "kpi_keys": ["avg_repair_order"],
        "diagnostic": _diag_low_dvi_completion,
        "automation_trigger_type": None,
        "summary": (
            "A completed Digital Vehicle Inspection is the real source of upsell "
            "opportunities -- an RO with no DVI is a real missed-revenue signal, not "
            "just a process miss."
        ),
        "steps": [
            "Make the Inspection (DVI) tab a required step in the RO Workspace before moving a repair order to Estimate.",
            "Use the DVI's 'Create Concern(s) From Selected Finding(s)' action every time a flagged item is found -- it's a one-click path into the real Estimate & Approval flow.",
        ],
    },
    {
        "key": "stalled_repair_orders",
        "title": "Clear Stalled Repair Orders",
        "department": "service",
        "kpi_keys": ["total_gross", "hours_per_ro"],
        "diagnostic": _diag_stalled_ros,
        "automation_trigger_type": None,
        "summary": (
            "An RO open for hours with zero labor posted is either forgotten or "
            "blocked. Shop Control's Stalled ROs panel already surfaces this exact "
            "population."
        ),
        "steps": [
            "Check Service -> Shop Control's Stalled ROs panel at least twice per shift.",
            "For each stalled RO, either assign/reassign a technician via the dispatch board or escalate via Shop Bottlenecks if it's a parts/approval delay, not a staffing one.",
        ],
    },
    {
        "key": "understocked_fast_moving_parts",
        "title": "Reorder Fast-Moving Parts Before Stockout",
        "department": "parts",
        "kpi_keys": ["net_profit", "parts_sales", "gross_profit_per_unit"],
        "diagnostic": _diag_parts_understocked,
        "automation_trigger_type": None,
        "summary": (
            "A part with real, active sales velocity that's at or near zero on hand is "
            "a real lost-sale risk. Parts Desk's Inventory Recommendations panel is "
            "already the real reorder signal for this."
        ),
        "steps": [
            "Open Service -> Parts and review the Inventory Recommendations list weekly, not just when a counter person notices a stockout.",
            "Prioritize the highest-velocity SKUs on that list first -- they're ranked by real recent sales volume against real on-hand quantity.",
        ],
    },
    {
        "key": "fi_menu_not_presented",
        "title": "Present the F&I Menu on Every Deal",
        "department": "fi",
        "kpi_keys": ["reserve_income", "income_per_contract", "reserve_per_vehicle", "deals_financed"],
        "diagnostic": _diag_fi_menu_not_presented,
        "automation_trigger_type": None,
        "summary": (
            "A financed deal with no F&I menu on file is real, uncaptured product "
            "penetration. Sales -> F&I Products' own queue already lists every "
            "financing/contract-stage deal missing a menu."
        ),
        "steps": [
            "Open Sales -> F&I Products' Product Menu tab and clear the 'no menu yet' queue before end of day.",
            "Present all 6 catalog products on every deal, even ones you expect to be declined -- Product Penetration is measured against deals actually taken through F&I, so a presented-and-declined product still counts as real coverage.",
        ],
    },
    {
        "key": "unworked_delinquent_accounts",
        "title": "Work Every Delinquent Account",
        "department": "bhph",
        "kpi_keys": ["delinquency_rate_pct", "repo_rate_pct", "charge_off_rate_pct"],
        "diagnostic": _diag_unworked_delinquent_accounts,
        "automation_trigger_type": None,
        "summary": (
            "A delinquent loan with no collection stage ever advanced is a real gap in "
            "active outreach, not just a risk metric. Finance -> Collections' real "
            "priority-ranked Work Queue is built specifically for this."
        ),
        "steps": [
            "Open Finance -> Collections and work the queue by real risk score, not just days-past-due.",
            "Advance every touched account's Collection Stage explicitly (Friendly Reminder -> Late Notice -> Demand Notice -> ...) so this diagnostic itself can tell the account is being worked.",
        ],
    },
    {
        "key": "broken_promises_to_pay",
        "title": "Follow Up on Broken Promises to Pay",
        "department": "bhph",
        "kpi_keys": ["delinquency_rate_pct", "repo_rate_pct", "charge_off_rate_pct"],
        "diagnostic": _diag_broken_promises,
        "automation_trigger_type": None,
        "summary": (
            "A broken promise-to-pay is a real, strong signal that an account needs "
            "escalation, not another routine reminder. Finance -> Collections' Agent "
            "Workspace shows real promise history per loan."
        ),
        "steps": [
            "Open the loan's Agent Workspace in Finance -> Collections and review its Promise-to-Pay history before the next contact attempt.",
            "Escalate a loan with 2+ broken promises toward the Repossession Referral collection stage rather than repeating the same outreach.",
        ],
    },
]


def _automation_score(trigger_type):
    """A real 0/1/3 tier (see module docstring for why 2 is unused) against
    core/workflow_automation.py's actual TRIGGER_TYPES and any LIVE
    AutomationRule already configured of that type."""

    if trigger_type is None or trigger_type not in TRIGGER_TYPES:
        return {
            "tier": 0,
            "label": "No Automation Path Yet",
            "note": (
                "No matching Workflow Automation trigger type exists in "
                "core/workflow_automation.py's current 3-type catalog for this "
                "specific condition -- manual monitoring only."
            ),
        }

    rules = list_rules(active_only=True)
    matching_active_rules = [r for r in rules if r.attributes.get("trigger_type") == trigger_type]

    if matching_active_rules:
        return {
            "tier": 3,
            "label": "Already Automated",
            "note": (
                f"{len(matching_active_rules)} live AutomationRule(s) of trigger type "
                f"'{trigger_type}' are currently active -- this condition is already "
                "being auto-monitored (Administration -> Workflow Automation)."
            ),
            "active_rule_count": len(matching_active_rules),
        }

    return {
        "tier": 1,
        "label": "Automatable Today",
        "note": (
            f"A matching Workflow Automation trigger type ('{trigger_type}') already "
            "exists -- an Admin can set up a live rule in Administration -> Workflow "
            "Automation right now, no new code needed. No such rule is configured yet."
        ),
    }


def get_playbook_library(role="ADMIN"):
    """The real curated playbook library, each entry annotated with a live-
    checked `is_currently_active` flag (re-runs the same core/network_root_
    cause.py diagnostic that backs Gap Analysis's Root Cause Analysis, not a
    separate check) and a real automation_score tier. `role` is accepted for
    signature symmetry with every other Network function but this module makes
    no role-gated calls of its own -- every diagnostic it reuses is a plain
    graph read, not ACL-gated."""

    entries = []

    for pb in PLAYBOOK_CATALOG:

        finding = pb["diagnostic"]()
        automation = _automation_score(pb["automation_trigger_type"])

        entries.append({
            "key": pb["key"],
            "title": pb["title"],
            "department": pb["department"],
            "kpi_keys": pb["kpi_keys"],
            "summary": pb["summary"],
            "steps": pb["steps"],
            "is_currently_active": finding is not None,
            "active_finding": finding,
            "automation_score": automation,
        })

    active_count = sum(1 for e in entries if e["is_currently_active"])

    return {
        "playbooks": entries,
        "playbook_count": len(entries),
        "currently_active_count": active_count,
        "note": (
            "Every playbook here references a real NXTDeal screen/workflow already "
            "built in this codebase -- no generic industry advice with no real backing "
            "action. `is_currently_active` re-runs the exact same real diagnostic "
            "Gap Analysis's Root Cause Analysis uses (core/network_root_cause.py), so "
            "this list doubles as a live-checked worklist, not a static reference. No "
            "curated Playbook entity/content-authoring model exists yet -- this catalog "
            "is a fixed, hand-written set, not dealer-submittable or crowd-sourced "
            "(this environment is single-tenant, so there's no real peer dealer to "
            "crowd-source 'Top 1%' content from)."
        ),
    }
