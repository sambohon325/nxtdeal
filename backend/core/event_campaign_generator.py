"""
Event Campaign Generator (2026-07-18, Marketing Growth Platform -- the third of the
"War Room, Project Management, Campaign Generator" items flagged as open at the end
of the Events dash's original build, session 84).

Deliberately NOT a new AI client or a new campaign model -- composes two engines this
codebase already has: core/email_wizard.py's real OpenAI-backed copy generation
(session 79, the exact same isolated client/model core/website_wizard.py uses) drafts
real subject/body/CTA copy from the Event's own real name/type/location/start_time,
and core/campaigns.py's new "event_promo" campaign type (added alongside this module)
resolves a real audience from the Event's own invite/RSVP roster -- never a blanket
broadcast. The result is a genuine EmailTemplate + Campaign pair, cross-linked to each
other (EmailTemplate.linked_campaign_id / Campaign.linked_template_id) and to the
Event (Campaign.params.event_id), reusing core/email_templates.py's own block-assembly
shape verbatim (the same heading/paragraph/button/footer trio
core/email_templates_api.py's create_from_wizard_api() already assembles) rather than
routing through that *_api.py layer -- a core module should depend on other core
modules, not on an ACL layer.

Same fallback contract as every other AI-backed draft in this codebase: if OpenAI
can't be reached, fallback_copy() produces a plain, usable placeholder instead of
failing the whole flow.
"""

from core.dealership_events import get_event
from core.campaigns import create_campaign, list_campaigns, list_channels
from core.email_templates import create_template, update_template, get_template, BLOCK_TYPES
from core.email_wizard import generate_email_copy, generate_sms_copy, fallback_copy


def _event_brief(event):

    name = event.attributes.get("name") or "our upcoming event"
    event_type = event.attributes.get("event_type") or "event"
    location = event.attributes.get("location") or ""
    start_time = event.attributes.get("start_time") or ""

    when = f" on {start_time[:10]}" if start_time else ""
    where = f" at {location}" if location else ""

    goal = f"Invite customers to {name}, a {event_type.replace('_', ' ')}{when}{where}."
    audience_description = f"customers and leads invited to the '{name}' dealership event"

    return goal, audience_description


def generate_event_campaign_draft(event_id, channel="email", tone="friendly and professional"):
    """Preview-only -- generates real copy but doesn't persist anything, so a marketer
    can regenerate/adjust tone before committing to a real Campaign+EmailTemplate."""

    event = get_event(event_id)

    if not event:
        return {"error": "Event not found"}

    if channel not in list_channels():
        return {"error": f"Unknown channel '{channel}'"}

    goal, audience_description = _event_brief(event)
    brief = {"goal": goal, "audience_description": audience_description, "tone": tone}

    if channel == "sms":
        copy = generate_sms_copy(brief)
        if not copy or "error" in copy:
            copy = fallback_copy(brief, "sms")
    else:
        copy = generate_email_copy(brief)
        if not copy or "error" in copy:
            copy = fallback_copy(brief, "email")

    return {"event_id": event_id, "channel": channel, "goal": goal, "copy": copy}


def create_event_campaign(event_id, channel, created_by, tone="friendly and professional"):
    """The real, persisting action -- generates copy (same draft path as
    generate_event_campaign_draft()), assembles a real EmailTemplate, creates a real
    'event_promo' Campaign whose audience resolves against the Event's own real
    invite/RSVP roster, and cross-links all three."""

    event = get_event(event_id)

    if not event:
        return {"error": "Event not found"}

    if channel not in list_channels():
        return {"error": f"Unknown channel '{channel}'"}

    goal, audience_description = _event_brief(event)
    brief = {"goal": goal, "audience_description": audience_description, "tone": tone}

    template = create_template(channel, f"{event.attributes.get('name')} Promo", created_by, ai_generated=True)

    if channel == "sms":

        copy = generate_sms_copy(brief)
        if not copy or "error" in copy:
            copy = fallback_copy(brief, "sms")

        update_template(template.id, {"sms_body": copy.get("sms_body")}, by=created_by)

    else:

        copy = generate_email_copy(brief)
        if not copy or "error" in copy:
            copy = fallback_copy(brief, "email")

        blocks = [
            {"block_key": "heading", "fields": {"text": copy.get("heading") or copy.get("subject") or event.attributes.get("name") or ""}},
            {"block_key": "paragraph", "fields": {"text": copy.get("body") or ""}},
            {"block_key": "button", "fields": {"text": copy.get("cta_text") or "RSVP Now", "url": ""}},
            {"block_key": "footer", "fields": {"text": BLOCK_TYPES["footer"]["fields"][0]["default"]}},
        ]

        update_template(
            template.id,
            {"subject": copy.get("subject") or event.attributes.get("name"), "preheader": copy.get("preheader"), "blocks": blocks},
            by=created_by,
        )

    campaign = create_campaign(
        "event_promo",
        f"{event.attributes.get('name')} Promotion",
        channel,
        created_by,
        {"event_id": event_id},
        linked_template_id=template.id,
    )

    if isinstance(campaign, dict) and "error" in campaign:
        return campaign

    # Cross-link the template back to the campaign -- Campaign.linked_template_id was
    # set at creation above, but EmailTemplate.linked_campaign_id needs a separate
    # update_template() call since the campaign didn't exist yet when the template was
    # first created.
    update_template(template.id, {"linked_campaign_id": campaign.id}, by=created_by)

    return {"campaign": campaign, "template": get_template(template.id)}


def list_campaigns_for_event(event_id):

    return [
        c for c in list_campaigns(campaign_type="event_promo")
        if (c.attributes.get("params") or {}).get("event_id") == event_id
    ]
