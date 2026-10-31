"""
core/collections_api.py -- ACL layer for core/collections.py. Same narrow role set
as core/loan_servicing_api.py/core/payments_api.py (ADMIN/OPERATIONS/FINANCE) for
both viewing and mutating -- collections work touches the same sensitive borrower/
balance detail those modules already gate this way.
"""

from core.permissions import ADMIN, OPERATIONS, FINANCE
from core.collections import (
    get_collection_queue,
    get_agent_workspace,
    get_collection_stage,
    advance_collection_stage,
    compute_risk_score,
    get_priority_recommendation,
    log_contact,
    get_contact_history,
    get_collections_dashboard,
)

_VIEW_ROLES = (ADMIN, OPERATIONS, FINANCE)
_MUTATE_ROLES = (ADMIN, OPERATIONS, FINANCE)


def _denied():
    return {"error": "You don't have access to Collections"}


def get_collection_queue_api(role, bucket=None):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_collection_queue(bucket=bucket)


def get_agent_workspace_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_agent_workspace(loan_id)


def get_collection_stage_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    stage = get_collection_stage(loan_id)
    if isinstance(stage, dict) and "error" in stage:
        return stage
    return {"loan_id": loan_id, "collection_stage": stage}


def advance_collection_stage_api(role, employee_id, loan_id, stage, reason=""):
    if role not in _MUTATE_ROLES:
        return _denied()
    return advance_collection_stage(loan_id, stage, employee_id, reason=reason)


def compute_risk_score_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return compute_risk_score(loan_id)


def get_priority_recommendation_api(role, loan_id):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_priority_recommendation(loan_id)


def log_contact_api(role, employee_id, loan_id, channel, notes):
    if role not in _MUTATE_ROLES:
        return _denied()
    result = log_contact(loan_id, channel, notes, employee_id)
    if isinstance(result, dict) and "error" in result:
        return result
    return {"id": result.id, **result.attributes}


def get_contact_history_api(role, loan_id, limit=50):
    if role not in _VIEW_ROLES:
        return _denied()
    notes = get_contact_history(loan_id, limit=limit)
    return {"loan_id": loan_id, "count": len(notes), "history": [{"id": n.id, **n.attributes} for n in notes]}


def get_collections_dashboard_api(role):
    if role not in _VIEW_ROLES:
        return _denied()
    return get_collections_dashboard()
