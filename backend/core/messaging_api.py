"""
Thin API-layer functions for Communications (session 28), imported directly into
api/app.py's route handlers -- same "no service layer indirection" convention every
other `*_api.py` module in this codebase follows. ACL checks live here, not in
core/messaging.py, mirroring how core/security.py's can_access_dashboard/can_access_entity
are called from api/app.py rather than from core/queries.py itself.
"""

from core.messaging import (
    list_channels_for_role,
    can_access_channel,
    send_channel_message,
    get_channel_messages,
    send_direct_message,
    get_direct_messages,
    list_recent_conversations,
    list_directory,
)


def _serialize_message(entity):

    return {
        "id": entity.id,
        **entity.attributes,
    }


def list_channels(role):

    return [
        # `roles` added session 72 -- backs the Shared Knowledge drag-into-a-channel
        # confirmation flow ("share this with #sales" needs to know #sales really means
        # OPERATIONS/SALES/MARKETING, not a guess mirrored on the frontend).
        {"key": definition["key"], "name": definition["name"], "roles": definition["roles"]}
        for definition in list_channels_for_role(role)
    ]


def get_channel_messages_api(channel_key, role):

    if not can_access_channel(role, channel_key):

        return {
            "error": f"Forbidden: your role cannot access the '{channel_key}' channel"
        }

    return [
        _serialize_message(entity)
        for entity in get_channel_messages(channel_key)
    ]


def post_channel_message_api(channel_key, role, sender_id, content, attached_pin=None):

    if not can_access_channel(role, channel_key):

        return {
            "error": f"Forbidden: your role cannot access the '{channel_key}' channel"
        }

    if not content or not content.strip():

        return {"error": "Message content cannot be empty"}

    entity = send_channel_message(channel_key, sender_id, content, attached_pin)

    return _serialize_message(entity)


def get_direct_messages_api(requester_id, other_employee_id):

    return [
        _serialize_message(entity)
        for entity in get_direct_messages(requester_id, other_employee_id)
    ]


def post_direct_message_api(requester_id, other_employee_id, content, attached_pin=None):

    if not content or not content.strip():

        return {"error": "Message content cannot be empty"}

    entity = send_direct_message(requester_id, other_employee_id, content, attached_pin)

    return _serialize_message(entity)


def list_conversations_api(employee_id):

    return list_recent_conversations(employee_id)


def list_directory_api():

    return list_directory()
