"""
Operations' new "Communications" Top Menu item -- a real Unified Communications
Hub spanning every department (2026-07-19, Sam's own six-pillar spec: Operations'
"Executive Command Center, Communications/Unified Communications Hub, Workforce,
Compliance" -- Communications was one of the genuinely missing items, confirmed
absent from Operations' existing 8-item Top Menu, core/menu_catalog.py, before
writing anything).

Composes real, already-logged customer-facing touches from three separate,
department-siloed FieldNote-backed logs into one company-wide, filterable feed --
not a fourth parallel logging mechanism:

  - Sales' Communication Hub log (core/sales_menu.py's own `_unified_inbox()`,
    session 98) -- call/text/email/video FieldNotes, department="Sales",
    linked_entity_id=a Lead.
  - Service's RO Communication Center (core/repair_orders.py's
    `log_ro_communication()`) -- category="ro_communication", department=
    "Service", linked_entity_id=a ServiceRecord (RO); the channel itself is
    embedded as a `[call]`/`[text]`/`[email]` prefix on the note body rather
    than a separate attribute, parsed back out here for display only.
  - Finance's Collections contact log (core/collections.py's `log_contact()`)
    -- call/text/email FieldNotes, department="Finance", linked_entity_id=a
    FinanceContract (loan).

This module makes NO mutations of its own -- logging a new touch still happens
through each department's own dedicated screen (Sales' Communications tab,
Service's RO Workspace Communication Center, Finance's Collections Agent
Workspace); this is a real, read-only, cross-department AGGREGATION on top of
those three already-real logs, matching the same "compose, don't duplicate"
discipline the Customer Intelligence Layer (core/customer_360.py) already
established for the customer-facing side of this exact problem -- this module
is the staff-facing mirror of it: "one inbox," not "one timeline."

Honest scope note, matching core/sales_menu.py's own `communications()`
docstring precedent: every entry here is a real, staff-entered log of what
happened on a touch, not an automated call-recording/SMS/email-provider
integration -- no telephony/SMS/email-provider connection exists anywhere in
this codebase, and no message read-tracking model exists either. Marketing's own
Email/SMS CRM (core/email_templates.py) sends are a different real thing
(bulk/templated outbound campaigns, not a one-to-one logged contact) and are
surfaced here only as a real count, not folded into the merged per-touch feed.
"""

import re

from core.dealeros import ledger
from core.entity_types import LEAD, CUSTOMER, DEAL, EMAIL_TEMPLATE
from core.field_notes import list_field_notes

TOUCH_CATEGORIES = {"call", "text", "email", "video", "ro_communication"}

_RO_CHANNEL_PREFIX = re.compile(r"^\[(\w+)\]\s*(.*)$", re.DOTALL)


def _lead_or_customer_label(entity_id):
    entity = ledger.get_entity(entity_id) if entity_id else None
    if not entity:
        return None
    if entity.entity_type in (LEAD, CUSTOMER):
        name = f"{entity.attributes.get('FirstName', '')} {entity.attributes.get('LastName', '')}".strip()
        return name or entity.id
    if entity.entity_type == DEAL:
        return f"Deal {entity.id}"
    return entity.id


def _ro_label(ro_id):
    from core.repair_orders import _get_ro, _customer_for_record

    ro = _get_ro(ro_id) if ro_id else None
    if not ro:
        return ro_id

    customer = _customer_for_record(ro)
    customer_name = None
    if customer:
        customer_name = f"{customer.attributes.get('FirstName', '')} {customer.attributes.get('LastName', '')}".strip() or customer.id

    desc = ro.attributes.get("Description")
    parts = [p for p in (customer_name, desc) if p]
    return " -- ".join(parts) if parts else ro_id


def _loan_label(loan_id):
    from core.loan_servicing import _get_loan, _linked_customer_id, _customer_brief

    loan = _get_loan(loan_id) if loan_id else None
    if not loan:
        return loan_id

    customer_id = _linked_customer_id(loan)
    brief = _customer_brief(customer_id) if customer_id else None
    name = brief.get("name") if brief else None

    return f"{name} ({loan_id})" if name else loan_id


def _touch_brief(note):

    department = note.attributes.get("department")
    category = note.attributes.get("category")
    linked_id = note.attributes.get("linked_entity_id")
    body = note.attributes.get("body") or ""
    channel = category

    linked_label = None

    if category == "ro_communication":
        match = _RO_CHANNEL_PREFIX.match(body)
        if match:
            channel = match.group(1)
            body = match.group(2)
        linked_label = _ro_label(linked_id)
    elif department == "Finance":
        linked_label = _loan_label(linked_id)
    else:
        linked_label = _lead_or_customer_label(linked_id)

    return {
        "id": note.id,
        "department": department,
        "channel": channel,
        "body": body,
        "linked_entity_id": linked_id,
        "linked_entity_label": linked_label or linked_id,
        "created_by": note.attributes.get("created_by"),
        "created_at": note.attributes.get("created_at"),
    }


def get_unified_feed(department=None, channel=None, limit=200):

    notes = [
        n for n in list_field_notes(limit=5000)
        if n.attributes.get("category") in TOUCH_CATEGORIES
        and (department is None or n.attributes.get("department") == department)
    ]

    briefs = [_touch_brief(n) for n in notes]

    if channel:
        briefs = [b for b in briefs if b["channel"] == channel]

    by_department = {}
    by_channel = {}
    for b in briefs:
        by_department[b["department"]] = by_department.get(b["department"], 0) + 1
        by_channel[b["channel"]] = by_channel.get(b["channel"], 0) + 1

    return {
        "total": len(briefs),
        "by_department": by_department,
        "by_channel": by_channel,
        "items": briefs[:limit],
    }


def get_marketing_send_count():
    """A real count of Marketing's own EmailTemplate entities that have actually
    been attached to a campaign (Email/SMS CRM, session 81) -- an honest, separate
    signal, not folded into the merged per-touch feed above since a template/
    campaign is a bulk/templated send, not a one-to-one logged contact."""

    templates = [e for e in ledger.get_all().values() if e.entity_type == EMAIL_TEMPLATE]
    attached = [t for t in templates if t.attributes.get("linked_campaign_id")]

    return {"total_templates": len(templates), "attached_to_campaign": len(attached)}


def get_unified_communications_overview(role, department=None, channel=None):

    feed = get_unified_feed(department=department, channel=channel)

    return {
        "feed": feed,
        "marketing_sends": get_marketing_send_count(),
        "not_yet_tracked": {
            "read_receipts": "No message-delivery/read-tracking model exists anywhere in this codebase -- a logged touch means a staff member recorded it happened, not that a message was actually delivered or opened.",
            "live_telephony_sms_email_integration": "No telephony/SMS/email-provider connection exists anywhere in this codebase -- every entry here is a real, staff-entered log of a touch, not an automated capture.",
            "marketing_bulk_sends": "Marketing's own Email/SMS campaign sends (core/email_templates.py) are bulk/templated, not a one-to-one logged contact -- surfaced above only as a real count, not merged into the per-touch feed.",
        },
    }
