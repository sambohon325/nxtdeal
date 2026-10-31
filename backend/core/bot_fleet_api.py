"""
core/bot_fleet_api.py — role-gated API layer for the agentic-bot FLEET
(2026-07-23, Pillar 4 slice 1). Same split every *_api.py module in this codebase
follows: api/app.py imports these thin wrappers, which apply the role gate and delegate
to core/bot_fleet.py.

Gate posture, matching the existing bot surfaces:
  * Fleet management — activating/deactivating a team agent — is ADMIN-only, exactly like
    core/bot_api.py's coverage management (start/end/list_coverage_api). Auto mode is
    additionally gated inside core/bot_fleet.activate_agent() by the same default-deny
    bot.coverage.auto_mode capability core/bot_coverage.py uses.
  * Viewing the fleet and a team's recognized workflows is open to any authenticated role
    — read-only, non-sensitive operational insight (how a team works), the same reasoning
    core/data_connections_api.py's readiness_predictions_api() uses for predictions.
  * Recording a workflow step is open to any authenticated employee — it's a real signal
    about their own team's work, the direct analogue of core/bot_api.py's
    record_feedback_api() (which any authenticated user can call for their own bot tasks).
"""

from core.permissions import ADMIN
from core.bot_fleet import (
    list_fleet,
    fleet_summary,
    activate_agent,
    deactivate_agent,
    record_workflow_step,
    get_team_workflows,
    run_recognized_workflow,
)


def get_fleet_api(role):
    return {"fleet": list_fleet(), "summary": fleet_summary()}


def get_team_workflows_api(role, section):
    return get_team_workflows(section)


def record_workflow_step_api(employee_id, section, action_key, step_label=None, workflow_key=None):
    return record_workflow_step(
        section, employee_id, action_key, step_label=step_label, workflow_key=workflow_key
    )


def activate_agent_api(admin_role, admin_id, section, mode):
    if admin_role != ADMIN:
        return {"error": "Admin role required to activate a team agent"}
    return activate_agent(section, mode, admin_id)


def deactivate_agent_api(admin_role, admin_id, section):
    if admin_role != ADMIN:
        return {"error": "Admin role required to deactivate a team agent"}
    return deactivate_agent(section, admin_id)


def run_recognized_workflow_api(admin_role, admin_id, section):
    """ADMIN-only, matching activate/deactivate -- running a recognized workflow is a
    management action. Whether any step actually EXECUTES (vs drafts) is still decided
    inside core/bot_fleet by the auto-mode + kill-switch + bot.fleet.auto_execute gates and
    the (empty by default) FLEET_SAFE_ACTIONS whitelist."""

    if admin_role != ADMIN:
        return {"error": "Admin role required to run a team agent's workflow"}
    return run_recognized_workflow(section, admin_id)
