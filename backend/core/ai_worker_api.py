"""
core/ai_worker_api.py — role-gated API layer for the NXTDeal AI Workforce
(2026-07-24). Same split every *_api.py module follows: api/app.py imports these thin
wrappers, which apply the role gate and delegate to core/ai_worker.py.

Gate posture mirrors the fleet (core/bot_fleet_api.py):
  * Viewing the workforce and a worker's detail is open to any authenticated role —
    read-only operational insight.
  * Activating / deactivating a worker is ADMIN-only (management action). Autonomous mode
    is additionally gated inside core/ai_worker.activate_worker() by the default-deny
    ai.worker.autonomous capability.
  * Handling an interaction is open to any authenticated caller — in production the
    telephony / SMS / chat webhook authenticates as a service account; the safety of what
    actually EXECUTES (vs drafts) is decided inside core/ai_worker by the mode + kill
    switch + capability + WORKER_SAFE_ACTIONS gates, never by who called.
"""

from core.permissions import ADMIN
from core.ai_worker import (
    list_workforce,
    workforce_summary,
    get_worker_detail,
    activate_worker,
    deactivate_worker,
    handle_interaction,
    work_queue,
)


def get_workforce_api(role):
    return {"workforce": list_workforce(), "summary": workforce_summary()}


def get_worker_detail_api(role, worker_role):
    return get_worker_detail(worker_role)


def activate_worker_api(admin_role, admin_id, worker_role, mode):
    if admin_role != ADMIN:
        return {"error": "Admin role required to activate an AI worker"}
    return activate_worker(worker_role, mode, admin_id)


def deactivate_worker_api(admin_role, admin_id, worker_role):
    if admin_role != ADMIN:
        return {"error": "Admin role required to deactivate an AI worker"}
    return deactivate_worker(worker_role, admin_id)


def handle_interaction_api(caller_id, worker_role, channel, message,
                           scheduled_start=None, linked_entity_id=None, from_number=None):
    return handle_interaction(
        worker_role, channel, message, caller_id,
        scheduled_start=scheduled_start,
        linked_entity_id=linked_entity_id,
        from_number=from_number,
    )


def run_worker_queue_api(admin_role, admin_id, worker_role):
    """ADMIN-only, mirroring the fleet's run gate -- working an outbound queue is a bulk
    operational trigger. Whether each touch actually EXECUTES (vs drafts) is still decided
    inside core/ai_worker by the mode + kill switch + capability + WORKER_SAFE_ACTIONS gate."""
    if admin_role != ADMIN:
        return {"error": "Admin role required to run an AI worker's queue"}
    return work_queue(worker_role, admin_id)
