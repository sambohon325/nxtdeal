"""
core/bot_actions.py — the whitelist of actions the bot may perform on its own when an
admin has activated "auto" mode coverage for an absent employee (core/bot_coverage.py).

Deliberately tiny and deliberately safe: nothing here moves money, sends anything to a
customer, or publishes/approves on someone else's behalf -- those already require an
explicit human click everywhere else in this codebase (deal financing/funding, campaign
activation, website publish, asset approval), and covering for someone who's out sick is
not a reason to relax that.

The one handler that exists, `_touch_overdue_leads`, resets a lead's PipelineStateSince
timestamp so it stops aging in the follow-up queue -- it logs that the bot has reviewed
the lead today, on the record via the audit log. It is NOT a claim that the customer was
actually contacted; the wording throughout this module and the audit trail it writes are
deliberately literal about that distinction.

Any bot task whose key isn't in ACTION_HANDLERS simply stays a suggestion even under
"auto" mode coverage -- core/bot_scheduler.py calls run_action() for every generated
task and only ever gets a result back for the handful of keys registered here.
"""

from core.pipeline_state import set_pipeline_state, get_pipeline_state
from core.lead_assignment import get_employee_leads
from core.follow_up_queue import get_follow_up_queue
from core.audit import audit_log


def _touch_overdue_leads(employee_id, admin_id):

    lead_ids = get_employee_leads(employee_id)
    overdue = get_follow_up_queue(lead_ids, threshold_days=1)

    touched = []

    for item in overdue:

        lead_id = item["lead_id"]
        state = get_pipeline_state(lead_id) or "NEW"
        set_pipeline_state(lead_id, state)
        touched.append(lead_id)

    if touched:

        audit_log.record(
            event_type="bot_auto_action",
            summary=(
                f"Bot (covering {employee_id}, activated by {admin_id}) reviewed "
                f"{len(touched)} overdue lead(s) and reset their follow-up clock"
            ),
            entity_id=employee_id,
            actor=f"BOT (covering {employee_id})",
            details={"lead_ids": touched, "activated_by": admin_id},
        )

    return {"touched_leads": touched}


# key -> handler(employee_id, admin_id) -> result dict. Only "sales_followup_leads"
# (core/bot_tasks.py's TASK_CATALOG) is wired to a real auto-action today -- every other
# task key intentionally has no entry here, so it stays a plain suggestion regardless of
# coverage mode.
ACTION_HANDLERS = {
    "sales_followup_leads": _touch_overdue_leads,
}


def run_action(task_key, employee_id, admin_id):
    """Returns a result dict if task_key is in the whitelist and there was something to
    do, else None -- meaning "no auto-action exists for this task, treat it as a plain
    suggestion", the same behavior "draft" mode always has.

    Security-hardening pass (2026-07-20, Task #6): gated by the real
    Bot-wide (and dealer-wide) kill switch, core/ai_kill_switch.py's
    is_bot_enabled() -- this is the single real choke point for the Bot's
    own unattended, background-scheduled mutation surface (see
    core/bot_scheduler.py's real 5-minute tick, the only real caller of
    this function outside of tests), so a killed switch correctly falls
    through to the same None "just a suggestion" contract every other
    non-whitelisted task_key already produces -- no caller needs to change
    to handle this."""

    handler = ACTION_HANDLERS.get(task_key)

    if not handler:
        return None

    from core.ai_kill_switch import is_bot_enabled
    if not is_bot_enabled():
        return None

    # Security-hardening pass (2026-07-20, Task #7 "Build Bot Permission
    # Layer"): a second, more granular, default-deny gate on top of the
    # blunt kill switch above -- re-checked on every single call (not just
    # once at coverage-start time), since a grant can be revoked mid-
    # window. core.bot_coverage.start_coverage() already checked
    # bot.coverage.auto_mode once before this window could even begin;
    # this is the standing per-action policy, checked every 5 minutes for
    # the life of the window by core.bot_scheduler.py's own tick.
    from core.bot_permissions import is_capability_granted, department_for_employee
    department = department_for_employee(employee_id)
    if not is_capability_granted(
        "bot.action.auto_touch_overdue_leads", employee_id=employee_id, department=department
    ):
        return None

    return handler(employee_id, admin_id)
