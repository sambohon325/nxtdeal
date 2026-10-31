"""
Thin ACL layer for core/website_chat.py (session 85), imported directly into
api/app.py.

Two very different callers hit this module: an anonymous website visitor (no auth at
all -- start_chat_session_api/send_visitor_message_api/list_messages_api are safe to
call with just a session_id, which acts as its own unguessable-enough capability token
the same way a support-chat widget session typically works) and an authenticated
employee working the inbox (list_open_sessions_api/send_employee_reply_api/
claim_session_api/close_session_api/promote_session_api, all gated to the site's
builder/owners or MARKETING/ADMIN, same access line as core/websites_api.py's
_can_edit_content/_can_review)."""

from core.website_chat import (
    start_chat_session,
    get_session,
    send_visitor_message,
    send_employee_message,
    list_messages,
    claim_session,
    close_session,
    list_sessions,
    promote_session_to_lead,
    list_departments,
    list_unified_inbox,
    ai_respond_to_session,
)
from core.websites import get_website, is_owner, list_websites
from core.permissions import ADMIN, MARKETING


def _serialize_session(entity):
    return {"id": entity.id, **entity.attributes}


def _serialize_message(entity):
    return {"id": entity.id, **entity.attributes}


def _can_work_chat(role, employee_id, website_id):

    if role in (ADMIN, MARKETING):
        return True

    website = get_website(website_id)

    if not website:
        return False

    return website.attributes.get("requested_by") == employee_id or is_owner(website, employee_id)


def start_chat_session_api(website_id, visitor_name=None, visitor_email=None, initial_message=None, department=None):
    """PUBLIC -- an anonymous visitor opening the chat widget. `department` (session
    113 follow-up) is the visitor's own pick of sales/service/finance/general."""

    result = start_chat_session(
        website_id,
        visitor_name=visitor_name,
        visitor_email=visitor_email,
        initial_message=initial_message,
        department=department,
    )

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_session(result)


def list_departments_api():
    """PUBLIC -- the real department options the chat widget's picker renders."""

    return list_departments()


def send_visitor_message_api(session_id, body):
    """PUBLIC -- the visitor's own reply."""

    result = send_visitor_message(session_id, body)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_message(result)


def list_messages_api(session_id, since=None):
    """PUBLIC (for the visitor's own widget to poll) as well as used by the
    authenticated employee inbox -- a session_id alone reveals nothing beyond that one
    conversation."""

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    return [_serialize_message(m) for m in list_messages(session_id, since=since)]


def get_session_api(session_id):
    """PUBLIC -- lets the visitor widget re-fetch its own session status (e.g. to show
    'an agent has joined the chat')."""

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    return _serialize_session(session)


def list_open_sessions_api(role, employee_id, website_id):

    if not _can_work_chat(role, employee_id, website_id):
        return {"error": "You don't have access to this site's chat inbox"}

    return [_serialize_session(s) for s in list_sessions(website_id=website_id)]


def send_employee_reply_api(role, employee_id, session_id, body):

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    if not _can_work_chat(role, employee_id, session.attributes.get("website_id")):
        return {"error": "You don't have access to this site's chat inbox"}

    result = send_employee_message(session_id, employee_id, body)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_message(result)


def claim_session_api(role, employee_id, session_id):

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    if not _can_work_chat(role, employee_id, session.attributes.get("website_id")):
        return {"error": "You don't have access to this site's chat inbox"}

    result = claim_session(session_id, employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_session(result)


def close_session_api(role, employee_id, session_id):

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    if not _can_work_chat(role, employee_id, session.attributes.get("website_id")):
        return {"error": "You don't have access to this site's chat inbox"}

    result = close_session(session_id, by=employee_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_session(result)


def promote_session_api(role, employee_id, session_id, name=None, email=None, phone=None):
    """The one-click 'wired into the crm' promote action."""

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    if not _can_work_chat(role, employee_id, session.attributes.get("website_id")):
        return {"error": "You don't have access to this site's chat inbox"}

    return promote_session_to_lead(session_id, employee_id, name=name, email=email, phone=phone)


def _managed_website_ids(role, employee_id):
    """Every site this caller can work chat for -- ADMIN/MARKETING manage every site
    (None means 'no filter' to list_unified_inbox()); anyone else only their own
    (requested_by or an explicit owner), matching _can_work_chat()'s own per-site
    rule generalized across every site instead of checked one at a time."""

    if role in (ADMIN, MARKETING):
        return None

    return [
        w.id for w in list_websites()
        if w.attributes.get("requested_by") == employee_id or is_owner(w, employee_id)
    ]


def list_unified_inbox_api(role, employee_id, status=None, department=None):
    """The real 'omnichannel' upgrade (session 113 follow-up) -- every chat session
    across every site this employee can manage, in one call, filterable by status/
    department, instead of the old one-website-at-a-time inbox."""

    website_ids = _managed_website_ids(role, employee_id)

    if website_ids is not None and not website_ids:
        return []

    sessions = list_unified_inbox(website_ids=website_ids, status=status, department=department)

    enriched = []
    for s in sessions:
        website = get_website(s.attributes.get("website_id"))
        row = _serialize_session(s)
        row["website_name"] = website.attributes.get("name") if website else None
        enriched.append(row)

    return enriched


def generate_ai_reply_api(role, employee_id, session_id):
    """Explicit manual trigger -- an employee can ask the AI Receptionist to draft (and
    immediately post, same auto-apply-once-triggered behavior as the automatic path)
    a reply at any time, not just while a session is unclaimed. Same ACL as every
    other chat-inbox action."""

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    if not _can_work_chat(role, employee_id, session.attributes.get("website_id")):
        return {"error": "You don't have access to this site's chat inbox"}

    result = ai_respond_to_session(session_id)

    if isinstance(result, dict) and "error" in result:
        return result

    return _serialize_message(result)
