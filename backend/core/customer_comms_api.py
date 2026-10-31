"""
core/customer_comms_api.py -- API layer for the customer side of Communications (2026-07-24).
All actions are performed BY an authenticated NXTDeal user (the actor is their employee_id), so
every route is open to any authenticated staff role -- searching, calling, texting, and saving a
contact are ordinary front-line jobs. The actor id is always taken from the token, never a body.
"""

from core import customer_comms


def provider_status_api(role):
    return customer_comms.provider_status()


def search_customers_api(role, query, limit=25):
    return customer_comms.search_customers(query, limit=limit)


def save_contact_api(role, actor_id, number, name=None, email=None):
    return customer_comms.save_contact(number, name, actor_id, email=email)


def place_call_api(role, actor_id, customer_id=None, number=None, department=None):
    return customer_comms.place_call(
        actor_id, customer_id=customer_id, number=number,
        department=department or customer_comms.DEFAULT_DEPARTMENT,
    )


def end_call_api(role, actor_id, call_id, notes=None, duration_seconds=None):
    return customer_comms.end_call(call_id, actor_id, notes=notes, duration_seconds=duration_seconds)


def send_text_api(role, actor_id, body, customer_id=None, number=None, department=None):
    return customer_comms.send_text(
        actor_id, body, customer_id=customer_id, number=number,
        department=department or customer_comms.DEFAULT_DEPARTMENT,
    )


def get_conversation_api(role, customer_id):
    return customer_comms.get_conversation(customer_id)


def get_call_intelligence_api(role, comm_id):
    return customer_comms.get_call_intelligence(comm_id)


def recent_activity_api(role, department=None, limit=25):
    return customer_comms.recent_activity(department=department, limit=limit)
