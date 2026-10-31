"""
Thin API-layer functions for Lost Sale Recovery (session 105 follow-up), imported
directly into api/app.py's route handlers -- same convention as every other
`*_api.py` module in this codebase.

Role rule: viewing/logging/reactivating is ADMIN/OPERATIONS/SALES -- desking-adjacent
work, the same role set core/deals_api.py grants for the desking half of a Deal and
core/credit_app_api.py grants for credit applications. MARKETING is also allowed to
view the queues and save a recovery pool as a MarketingList (but not mark a lead lost,
record a deal's cancel reason, or reactivate a lead) -- win-back campaigns are exactly
the kind of thing Marketing's CRM already builds against real Lists, and
core/marketing_lists_api.py already grants MARKETING+SALES+ADMIN+OPERATIONS broad read
access to lists themselves.
"""

from core.lost_sale_recovery import (
    get_lost_leads,
    get_cancelled_deals,
    mark_lead_lost,
    record_deal_lost_reason,
    reactivate_lost_lead,
    log_recovery_attempt,
    list_recovery_attempts,
    save_recovery_pool_as_list,
    get_lost_sale_stats,
    LOST_REASON_CODES,
)
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING


_ACTION_ROLES = (ADMIN, OPERATIONS, SALES)
_VIEW_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING)


def get_lost_reason_codes_api(role):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lost Sale Recovery"}

    return LOST_REASON_CODES


def get_lost_leads_api(role, limit=50):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lost Sale Recovery"}

    return get_lost_leads(limit=limit)


def get_cancelled_deals_api(role, limit=50):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lost Sale Recovery"}

    return get_cancelled_deals(limit=limit)


def mark_lead_lost_api(role, employee_id, lead_id, reason):

    if role not in _ACTION_ROLES:
        return {"error": "Only Sales/Operations/Admin can mark a lead lost"}

    return mark_lead_lost(lead_id, reason, employee_id)


def record_deal_lost_reason_api(role, employee_id, deal_id, reason):

    if role not in _ACTION_ROLES:
        return {"error": "Only Sales/Operations/Admin can record a cancelled deal's lost-sale reason"}

    return record_deal_lost_reason(deal_id, reason, employee_id)


def reactivate_lost_lead_api(role, employee_id, lead_id, note=None):

    if role not in _ACTION_ROLES:
        return {"error": "Only Sales/Operations/Admin can reactivate a lost lead"}

    return reactivate_lost_lead(lead_id, employee_id, note=note)


def log_recovery_attempt_api(role, employee_id, entity_id, entity_type, note):

    if role not in _ACTION_ROLES:
        return {"error": "Only Sales/Operations/Admin can log a recovery attempt"}

    return log_recovery_attempt(entity_id, entity_type, note, employee_id)


def list_recovery_attempts_api(role, entity_id):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lost Sale Recovery"}

    return list_recovery_attempts(entity_id)


def save_recovery_pool_as_list_api(role, employee_id, name, source, description=""):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lost Sale Recovery"}

    return save_recovery_pool_as_list(name, employee_id, source, description=description)


def get_lost_sale_stats_api(role):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to Lost Sale Recovery reporting"}

    return get_lost_sale_stats()


def get_lost_sale_recovery_dashboard_api(role):

    if role not in _VIEW_ROLES:
        return {"error": "You don't have access to the Lost Sale Recovery dashboard"}

    return {
        "reason_codes": LOST_REASON_CODES,
        "lost_leads": get_lost_leads(limit=25),
        "cancelled_deals": get_cancelled_deals(limit=25),
        "stats": get_lost_sale_stats(),
    }
