"""
Website live chat (2026-07-15/16, session 85) -- the 'live chat functionality (wired
into the crm)' piece of Sam's Website Builder overhaul.

Scoping decision, made autonomously after an AskUserQuestion tool call failed
(AbortError) and was not retried -- documented here rather than silently assumed: this
is REST + polling (start a session, post messages, poll for new ones), not a new public
WebSocket endpoint. core/messaging.py's real-time system (core/ws_manager.py's
/ws/messaging) was deliberately NOT extended to cover this: that whole system's design
assumes both participants are authenticated Employees (fixed department channels,
employee-to-employee DMs) -- a website visitor is anonymous, a fundamentally different
trust boundary. Opening a second, unauthenticated public WebSocket surface into this
codebase's real-time infrastructure is a bigger security/complexity commitment than a
short-poll REST loop, and the frontend can poll GET .../messages every few seconds for
a "live enough" experience without it. If Sam wants true push-based real-time chat
later, that's a deliberate follow-up, not something to assume here.

The actual CRM tie, matching the exact 'one-click promote' precedent
core/trigger_alerts.py's promote_alert() and core/dealership_events.py's
promote_rsvp_to_lead() already established (session 84): promote_session_to_lead()
creates a real Lead via core/lead_intake.py's create_lead() (source='Website'),
assigned directly to whichever employee claimed/is promoting the chat.

Real data-loss bug found and fixed (2026-07-18, Marketing Growth Platform data-gap-
fill follow-up, the 10th confirmed instance of this exact bug class this session --
see core/lead_conversion.py's docstring for the running list) -- this module had ZERO
save_graph() calls anywhere since it shipped (session 85). Every real chat session,
every visitor/employee message, every claim/close, and every promote-to-lead had been
silently discarded on server restart. Fixed below: every mutating function now saves
directly (unlike core/trigger_alerts.py's run_scan(), a human typing in a live chat
can't plausibly generate calls fast enough for a per-action save to be a real
performance problem the way a single scan creating 439 alerts was).

Omnichannel/AI-receptionist upgrades (2026-07-18, Marketing Growth Platform "Live
Chat" item, session 113 follow-up). Two real, scoped pieces, plus one honest gap:

1. Department Routing -- a visitor picks a real DEPARTMENTS value (sales/service/
   finance/general) at session start, stored on the session. This is the literal,
   honestly-buildable reading of "omnichannel" for a single real-time widget this
   codebase actually has: every department reachable through one chat, routed
   correctly, rather than a fabricated second communication medium.

2. list_unified_inbox() -- a cross-site session listing (list_sessions() already
   supported website_id=None internally; this just exposes that as a real "every site
   at once" inbox, the actual gap the old per-site-only ChatTab had -- an employee
   managing several dealership sites previously had to check each one separately).

3. AI Receptionist -- ai_respond_to_session() is a real, isolated (no tool-calling
   access) OpenAI call, same isolation pattern as core/email_wizard.py/
   core/website_wizard.py/core/reputation.py's auto-respond bot, grounded in this
   site's own real live inventory (core/websites.get_live_inventory()) rather than
   inventing vehicle details. When a site's admin_settings["ai_receptionist_enabled"]
   is True, an unclaimed session with no employee reply yet gets a real, AUTO-APPLIED
   response the moment a visitor messages -- same auto-apply precedent
   core/reputation.py's auto_respond_review() already established (not just a
   proposed draft an employee has to approve first). Employees can also trigger it
   manually at any time via generate_ai_reply(). Every AI message is stored with
   sender="ai" (a new, distinct sender value from "visitor"/"employee") so a bot
   reply is never mistaken for a human one, matching reputation.py's own
   auto_responded flag convention. A plain templated fallback covers an OpenAI
   failure, so the receptionist never goes silent even if the API call fails.

Honest gap, deliberately not built here: true multi-channel unification (inbound
SMS/social DMs landing in this same inbox) -- this sandbox has no live SMS/social
messaging gateway to receive real inbound messages on (core/advertising.py's/
core/social_posts.py's own "launch"/"publish" actions are already honestly labeled
SIMULATED for the same reason), and fabricating a whole second real-time channel
would be a much bigger, more speculative build than the market-data-gap class of
thing session 110's "simulate when blocked" policy was scoped around. Flagged for a
future session if Sam wants to pursue it.
"""

import json
import os
from uuid import uuid4
from core.website_revisions import has_public_version, public_version
from datetime import datetime, timezone

from dotenv import load_dotenv
from core.optional_ai_client import LazyOpenAI

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import WEBSITE_CHAT_SESSION, WEBSITE_CHAT_MESSAGE, WEBSITE
from core.lead_intake import create_lead
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH
from core.ai_management import is_feature_enabled, record_call_attempt

load_dotenv()

client = LazyOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SESSION_STATUSES = ["open", "claimed", "closed"]

DEPARTMENTS = ["sales", "service", "finance", "general"]

SENDER_TYPES = ("visitor", "employee", "ai")

RECEPTIONIST_SYSTEM_PROMPT = (
    "You are a friendly, helpful car dealership receptionist responding in a live "
    "website chat widget. Keep replies short (1-3 sentences), warm, and genuinely "
    "helpful. If the visitor asks about a specific vehicle (make/model/price), use "
    "ONLY the real inventory details provided below -- never invent a price, VIN, or "
    "vehicle that isn't listed. If nothing matches or no inventory was provided, say "
    "so honestly and offer to have a team member follow up. Never quote a specific "
    "APR, discount, or financing term that wasn't given to you. Return ONLY a JSON "
    "object with one key: reply_text."
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def _all_sessions():
    return [e for e in ledger.get_all().values() if e.entity_type == WEBSITE_CHAT_SESSION]


def _all_messages():
    return [e for e in ledger.get_all().values() if e.entity_type == WEBSITE_CHAT_MESSAGE]


def list_departments():
    return list(DEPARTMENTS)


def start_chat_session(website_id, visitor_name=None, visitor_email=None, initial_message=None, department=None):
    """PUBLIC entry point (called with no auth from the site's chat widget). Only
    allowed on a 'published' site -- a draft site has no real visitors.

    `department` is the real routing signal (session 113 follow-up, "omnichannel")
    -- a visitor's own pick of sales/service/finance/general, so the right team's
    unified-inbox filter surfaces the right conversation. Defaults to "general" for
    any missing/unrecognized value rather than rejecting the session start."""

    website = ledger.get_entity(website_id)

    if not website or website.entity_type != WEBSITE or not has_public_version(website):
        return {"error": "Site not found"}

    if department not in DEPARTMENTS:
        department = "general"

    session_id = "WCS-" + uuid4().hex

    session = Entity(
        id=session_id,
        entity_type=WEBSITE_CHAT_SESSION,
        attributes={
            "website_id": website_id,
            "visitor_name": visitor_name,
            "visitor_email": visitor_email,
            "department": department,
            "status": "open",
            "claimed_by": None,
            "lead_id": None,
            "created_at": _now(),
            "updated_at": _now(),
            "last_message_at": None,
            "last_ai_reply_at": None,
        },
    )

    ledger.add_entity(session)

    save_graph(GRAPH_PATH)

    if initial_message:
        send_visitor_message(session_id, initial_message)

    return session


def get_session(session_id):

    entity = ledger.get_entity(session_id)

    if entity and entity.entity_type == WEBSITE_CHAT_SESSION:
        return entity

    return None


def send_visitor_message(session_id, body):

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    if not (body or "").strip():
        return {"error": "Message body is required"}

    if session.attributes.get("status") == "closed":
        session.attributes["status"] = "open"

    message_id = id_generator.generate("WCM")

    message = Entity(
        id=message_id,
        entity_type=WEBSITE_CHAT_MESSAGE,
        attributes={
            "session_id": session_id,
            "sender": "visitor",
            "sender_id": None,
            "body": body.strip(),
            "created_at": _now(),
        },
    )

    ledger.add_entity(message)

    session.attributes["last_message_at"] = message.attributes["created_at"]
    session.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    # AI Receptionist auto-trigger (session 113 follow-up) -- only when this site has
    # explicitly opted in (admin_settings["ai_receptionist_enabled"]), the session is
    # still unclaimed (a human hasn't taken it over), and no employee has ever replied
    # yet -- the receptionist covers a visitor until a real person is available, same
    # auto-apply precedent core/reputation.py's auto_respond_review() already
    # established, never overriding a human who's already engaged.
    if session.attributes.get("status") == "open" and not _has_employee_reply(session_id):
        website = public_version(ledger.get_entity(session.attributes.get("website_id")))
        if website and (website.attributes.get("admin_settings") or {}).get("ai_receptionist_enabled"):
            ai_respond_to_session(session_id)

    return message


def send_employee_message(session_id, employee_id, body):
    """An employee replying auto-claims an unclaimed session -- the first person to
    respond owns the conversation, same 'first responder claims it' pattern this
    codebase already uses informally elsewhere (e.g. bot task feedback)."""

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    if not (body or "").strip():
        return {"error": "Message body is required"}

    if session.attributes.get("status") == "open":
        session.attributes["status"] = "claimed"
        session.attributes["claimed_by"] = employee_id

    if session.attributes.get("status") == "closed":
        session.attributes["status"] = "claimed"
        session.attributes["claimed_by"] = employee_id

    message_id = id_generator.generate("WCM")

    message = Entity(
        id=message_id,
        entity_type=WEBSITE_CHAT_MESSAGE,
        attributes={
            "session_id": session_id,
            "sender": "employee",
            "sender_id": employee_id,
            "body": body.strip(),
            "created_at": _now(),
        },
    )

    ledger.add_entity(message)

    session.attributes["last_message_at"] = message.attributes["created_at"]
    session.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return message


def _has_employee_reply(session_id):
    return any(
        m.attributes.get("session_id") == session_id and m.attributes.get("sender") == "employee"
        for m in _all_messages()
    )


def _draft_ai_reply(session):
    """Isolated, no-tool-calling OpenAI call (same isolation pattern as
    core/email_wizard.py/core/website_wizard.py/core/reputation.py's auto-respond
    bot) grounded in this site's own real live inventory -- never invents a vehicle,
    price, or financing term. Falls back to a plain, honest templated reply on any
    OpenAI/network/parse failure, so the receptionist never goes silent.

    AI Management: checks the real 'website_ai_receptionist' PLATFORM-WIDE kill
    switch (core/ai_management.py, ai_receptionist_platform_enabled flag) before
    attempting -- distinct from this site's own per-site
    admin_settings['ai_receptionist_enabled'] toggle (session 113), which the caller
    already checks before ever reaching this function. Both must be true for a real
    AI reply to fire. When this platform flag is off, skips straight to the same
    templated fallback an OpenAI/network failure already falls back to."""

    from core.websites import get_website, get_live_inventory

    website = public_version(get_website(session.attributes.get("website_id")))
    site_name = (((website.attributes.get("studio_config") or {}).get("approved_template") or (website.attributes.get("studio_config") or {}).get("lone_star") or {}).get("name") if website else None) or (website.attributes.get("name") if website else None) or "our dealership"

    history = list_messages(session.id)
    conversation = "\n".join(
        f"{m.attributes.get('sender')}: {m.attributes.get('body')}" for m in history
    ) or "(no messages yet)"

    latest_visitor_text = ""
    for m in reversed(history):
        if m.attributes.get("sender") == "visitor":
            latest_visitor_text = m.attributes.get("body") or ""
            break

    inventory = get_live_inventory(limit=5) if latest_visitor_text else []
    inventory_context = (
        "\n".join(
            f"- {v['year']} {v['make']} {v['model']} {v.get('trim') or ''} -- ${v.get('price')}"
            for v in inventory
        )
        if inventory
        else "(no specific inventory context available)"
    )

    fallback = (
        f"Thanks for reaching out to {site_name}! A team member will be with you "
        "shortly -- in the meantime, feel free to share what you're looking for."
    )

    if not is_feature_enabled("website_ai_receptionist"):
        record_call_attempt("website_ai_receptionist", "blocked")
        return fallback

    try:
        from core.website_ai_credentials import completion
        response = completion(session.attributes["website_id"],
            messages=[
                {"role": "system", "content": RECEPTIONIST_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Dealership: {site_name}\nCustomer-selected department: {session.attributes.get('department', 'general')}\n"
                        "For service questions, offer team follow-up; do not invent repair status or appointments.\n"
                        f"Conversation so far:\n{conversation}\n\n"
                        f"A sample of real current inventory (only reference these, never "
                        f"invent one):\n{inventory_context}"
                    ),
                },
            ],
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content)
        draft = (parsed.get("reply_text") or "").strip()
        record_call_attempt("website_ai_receptionist", "succeeded" if draft else "fell_back")
        return draft or fallback

    except Exception as exc:  # noqa: BLE001 -- any OpenAI/network/parse failure falls back
        record_call_attempt("website_ai_receptionist", "fell_back", detail="Dealer provider unavailable")
        return fallback


def ai_respond_to_session(session_id):
    """The real AI Receptionist action -- drafts and immediately posts a real,
    sender='ai' message (auto-applied, same precedent as
    core/reputation.py's auto_respond_review(), not just proposed). Safe to call on a
    session that's already claimed/closed (an employee can still manually trigger a
    suggested reply at any time), but the auto-trigger in send_visitor_message() only
    ever calls this while a session is genuinely unclaimed."""

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    draft = _draft_ai_reply(session)

    message_id = id_generator.generate("WCM")

    message = Entity(
        id=message_id,
        entity_type=WEBSITE_CHAT_MESSAGE,
        attributes={
            "session_id": session_id,
            "sender": "ai",
            "sender_id": None,
            "body": draft,
            "ai_generated": True,
            "created_at": _now(),
        },
    )

    ledger.add_entity(message)

    session.attributes["last_message_at"] = message.attributes["created_at"]
    session.attributes["last_ai_reply_at"] = message.attributes["created_at"]
    session.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return message


def list_unified_inbox(website_ids=None, status=None, department=None):
    """The real 'omnichannel' upgrade -- every chat session across every site an
    employee manages, in one call, instead of the old per-site-only inbox.
    `website_ids=None` means every site in the graph (the ADMIN/MARKETING view);
    passing a real list restricts to just those sites (a non-privileged site
    owner/builder's own view -- see core/website_chat_api.py's ACL layer)."""

    sessions = _all_sessions()

    if website_ids is not None:
        allowed = set(website_ids)
        sessions = [s for s in sessions if s.attributes.get("website_id") in allowed]

    if status:
        sessions = [s for s in sessions if s.attributes.get("status") == status]

    if department:
        sessions = [s for s in sessions if s.attributes.get("department", "general") == department]

    sessions.sort(key=lambda s: (s.attributes.get("last_message_at") or s.attributes.get("created_at", "")), reverse=True)

    return sessions


def list_messages(session_id, since=None):
    """`since` is an ISO timestamp string (a prior message's created_at) -- the
    polling loop's 'give me anything newer than the last message I already have'
    query. Returns ALL messages, oldest first, when since is None (initial load)."""

    messages = [m for m in _all_messages() if m.attributes.get("session_id") == session_id]

    if since:
        messages = [m for m in messages if m.attributes.get("created_at", "") > since]

    messages.sort(key=lambda m: (m.attributes.get("created_at", ""), m.id))

    return messages


def claim_session(session_id, employee_id):

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    session.attributes["status"] = "claimed"
    session.attributes["claimed_by"] = employee_id
    session.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return session


def close_session(session_id, by=None):

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    session.attributes["status"] = "closed"
    session.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return session


def list_sessions(website_id=None, status=None):

    sessions = _all_sessions()

    if website_id:
        sessions = [s for s in sessions if s.attributes.get("website_id") == website_id]

    if status:
        sessions = [s for s in sessions if s.attributes.get("status") == status]

    sessions.sort(key=lambda s: (s.attributes.get("last_message_at") or s.attributes.get("created_at", "")), reverse=True)

    return sessions


def promote_session_to_lead(session_id, employee_id, name=None, email=None, phone=None):
    """The actual 'wired into the crm' mechanism -- one-click promote, same precedent
    as core/trigger_alerts.py's promote_alert()/core/dealership_events.py's
    promote_rsvp_to_lead() (session 84). The visitor's name/email captured at session
    start are the defaults; the promoting employee can supply/override name/email/phone
    at promote time since a chat visitor often never typed a phone number."""

    session = get_session(session_id)

    if not session:
        return {"error": "Chat session not found"}

    if session.attributes.get("lead_id"):
        return {"error": f"This chat is already linked to lead {session.attributes['lead_id']}"}

    final_name = name or session.attributes.get("visitor_name") or "Website Chat Visitor"
    final_email = email or session.attributes.get("visitor_email")

    if not (final_email or phone):
        return {"error": "An email or phone number is required to create a lead"}

    parts = final_name.strip().split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    lead = create_lead(
        created_by=employee_id,
        first_name=first_name,
        last_name=last_name,
        source="Website",
        phone=phone,
        email=final_email,
    )

    lead.attributes["WebsiteChatSessionID"] = session_id
    lead.attributes["WebsiteInquiryIntent"] = "assistant"
    lead.attributes["WebsiteID"] = session.attributes.get("website_id")

    session.attributes["lead_id"] = lead.id
    session.attributes["status"] = "claimed"
    session.attributes["claimed_by"] = employee_id
    session.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return {"lead_id": lead.id, "assigned_to": employee_id}
