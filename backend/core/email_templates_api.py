"""
Thin API-layer functions for the Email / SMS builder (session 79), imported directly
into api/app.py's route handlers -- same "no service layer indirection" convention
every other `*_api.py` module in this codebase follows. ACL checks live here (not in
core/email_templates.py), mirroring core/campaigns_api.py/core/websites_api.py.

Role rule: any authenticated role can create/edit their OWN templates (drafting a
one-off follow-up email is normal work for Sales/Service/Finance, not just Marketing);
MARKETING or ADMIN can additionally view and edit ANYONE's templates, the same broad
"marketing owns the messaging layer" power core/campaigns_api.py's `_can_activate`
already grants over campaign activation. There's no separate approval step here (unlike
Assets/Websites) -- a template only has real-world effect once it's attached to a
Campaign via linked_template_id and that Campaign is activated, and campaign
activation already runs the compliance gate (core/compliance.py's enforce_gate).
"""

from core.email_templates import (
    list_block_types,
    list_channels,
    create_template,
    get_template,
    update_template,
    list_templates,
    render_email_html,
    render_email_text,
    sms_segment_info,
    BLOCK_TYPES,
)
from core.email_wizard import generate_email_copy, generate_sms_copy, fallback_copy
from core.permissions import ADMIN, MARKETING


def _serialize_template(entity):

    return {
        "id": entity.id,
        **entity.attributes,
    }


def _can_manage_all(role):
    return role == ADMIN or role == MARKETING


def _can_access(role, employee_id, template):
    return _can_manage_all(role) or template.attributes.get("created_by") == employee_id


def list_block_types_api():
    return list_block_types()


def list_channels_api():
    return list_channels()


def create_template_api(employee_id, channel, name):

    if channel not in list_channels():
        return {"error": f"Unknown channel '{channel}'"}

    entity = create_template(channel, name, employee_id)

    return _serialize_template(entity)


def get_template_api(role, employee_id, template_id):

    template = get_template(template_id)

    if not template:
        return {"error": "Template not found"}

    if not _can_access(role, employee_id, template):
        return {"error": "You don't have access to this template"}

    return _serialize_template(template)


def update_template_api(role, employee_id, template_id, patch):

    template = get_template(template_id)

    if not template:
        return {"error": "Template not found"}

    if not _can_access(role, employee_id, template):
        return {"error": "You don't have access to edit this template"}

    from core.dealer_email_access import validate_email_patch
    try:
        validate_email_patch(role, employee_id, patch or {}, template.attributes)
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}
    updated = update_template(template_id, patch or {}, by=employee_id)

    return _serialize_template(updated)


def list_my_templates_api(employee_id, channel=None):
    return [_serialize_template(t) for t in list_templates(created_by=employee_id, channel=channel)]


def list_templates_api(role, employee_id, channel=None):
    """MARKETING/ADMIN see every template (the Email/SMS hub is a shared workspace for
    them); every other role sees only their own -- mirrors the "mine vs. pending queue"
    split core/campaigns_api.py already draws."""

    if _can_manage_all(role):
        return [_serialize_template(t) for t in list_templates(channel=channel)]

    return list_my_templates_api(employee_id, channel=channel)


def preview_template_api(role, employee_id, template_id):

    template = get_template(template_id)

    if not template:
        return {"error": "Template not found"}

    if not _can_access(role, employee_id, template):
        return {"error": "You don't have access to this template"}

    channel = template.attributes.get("channel")

    if channel == "sms":
        return {
            "channel": "sms",
            "sms_body": template.attributes.get("sms_body"),
            "segment_info": sms_segment_info(template.attributes.get("sms_body")),
        }

    return {
        "channel": "email",
        "subject": template.attributes.get("subject"),
        "preheader": template.attributes.get("preheader"),
        "html": render_email_html(template),
        "text": render_email_text(template),
    }


def create_from_wizard_api(employee_id, channel, goal, audience_description, tone):
    """Sam: 'Ai build an email wizard.' Drafts real copy via core/email_wizard.py
    (falling back to plain placeholder copy if OpenAI can't be reached), then assembles
    and saves a full EmailTemplate -- an email gets a heading/paragraph/button block
    trio built from the draft; an SMS gets its plain sms_body -- exactly the same
    "draft-then-assemble-a-real-entity" shape core/websites.py's
    create_website_from_wizard() already established for the website wizard."""

    if channel not in list_channels():
        return {"error": f"Unknown channel '{channel}'"}

    brief = {"goal": goal, "audience_description": audience_description, "tone": tone}

    if channel == "sms":

        copy = generate_sms_copy(brief)

        if not copy or "error" in copy:
            copy = fallback_copy(brief, "sms")

        template = create_template("sms", (goal or "New Text Message")[:60], employee_id, ai_generated=True)

        update_template(template.id, {"sms_body": copy.get("sms_body")}, by=employee_id)

        return _serialize_template(get_template(template.id))

    copy = generate_email_copy(brief)

    if not copy or "error" in copy:
        copy = fallback_copy(brief, "email")

    template = create_template("email", (goal or "New Email")[:60], employee_id, ai_generated=True)

    blocks = [
        {"block_key": "heading", "fields": {"text": copy.get("heading") or copy.get("subject") or ""}},
        {"block_key": "paragraph", "fields": {"text": copy.get("body") or ""}},
        {"block_key": "button", "fields": {"text": copy.get("cta_text") or "Learn More", "url": ""}},
        {"block_key": "footer", "fields": {"text": BLOCK_TYPES["footer"]["fields"][0]["default"]}},
    ]

    update_template(
        template.id,
        {
            "subject": copy.get("subject"),
            "preheader": copy.get("preheader"),
            "blocks": blocks,
        },
        by=employee_id,
    )

    return _serialize_template(get_template(template.id))
