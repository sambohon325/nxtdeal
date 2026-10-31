"""
core/connect_api.py — role-gated API layer for NXTDeal Connect (2026-07-24). The Connect
surface is read-only operational insight over the communications already logged, so viewing
is open to any authenticated role (same posture as the fleet/workforce views and
core/unified_communications_api.py). Thin wrappers delegating to core/connect.py.
"""

from core.connect import get_inbox, get_customer_timeline, get_analytics
from core.conversation_intelligence import get_channel_intelligence, analyze_communication


def get_connect_inbox_api(role, channel=None, direction=None, department=None,
                          linked_entity_id=None, ai_only=False, limit=100):
    return get_inbox(
        channel=channel, direction=direction, department=department,
        linked_entity_id=linked_entity_id, ai_only=ai_only, limit=limit,
    )


def get_connect_timeline_api(role, entity_id):
    return get_customer_timeline(entity_id)


def get_connect_analytics_api(role):
    return get_analytics()


def get_connect_intelligence_api(role):
    return get_channel_intelligence()


def get_connect_comm_intelligence_api(role, comm_id):
    return analyze_communication(comm_id)
