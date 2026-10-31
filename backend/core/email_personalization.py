"""
core/email_personalization.py -- real Dynamic Personalization for the Email/SMS
builder, one of the three upgrades from Sam's Marketing Growth Platform spec
("Mailchimp+Klaviyo-level... dynamic personalization, automation builder, A/B
testing, revenue tracking") layered onto the existing real builder
(core/email_templates.py, session 79) rather than a parallel one.

A real merge-field engine, not a fabricated one: `{{first_name}}` /
`{{last_name}}` / `{{full_name}}` / `{{city}}` / `{{state}}` resolve off the
recipient's own real Customer/Lead attributes; `{{vehicle_year}}` /
`{{vehicle_make}}` / `{{vehicle_model}}` resolve off the recipient's real
OWNS-linked vehicle (Customers only -- a Lead hasn't bought yet, same honest
gap `core/purls.py`'s Trade Equity offer already draws for Leads);
`{{trade_equity_pct}}` reuses `core/smart_audiences.py`'s real
`get_equity_candidate_for_customer()` (Customers only). A field with no real
data for a given recipient resolves to an empty string rather than a
fabricated placeholder value -- an honest blank, not a made-up name.

`render_personalized()` substitutes these tokens across a template's real
subject/preheader/blocks/sms_body, reusing `core/email_templates.py`'s own
`render_email_html()`/`render_email_text()` renderers on the substituted copy
rather than a second HTML renderer.
"""

import re

from core.dealeros import ledger
from core.entity_types import CUSTOMER, LEAD, VEHICLE
from core.relationship_types import OWNS
from core.email_templates import get_template, render_email_html, render_email_text, sms_segment_info

MERGE_FIELDS = [
    {"key": "first_name", "label": "First Name", "example": "Joseph"},
    {"key": "last_name", "label": "Last Name", "example": "King"},
    {"key": "full_name", "label": "Full Name", "example": "Joseph King"},
    {"key": "city", "label": "City", "example": "Austin"},
    {"key": "state", "label": "State", "example": "TX"},
    {"key": "vehicle_year", "label": "Current Vehicle Year", "example": "2018", "customers_only": True},
    {"key": "vehicle_make", "label": "Current Vehicle Make", "example": "Jeep", "customers_only": True},
    {"key": "vehicle_model", "label": "Current Vehicle Model", "example": "Compass", "customers_only": True},
    {"key": "trade_equity_pct", "label": "Trade Equity % (loan term paid down)", "example": "62%", "customers_only": True},
]

_TOKEN_RE = re.compile(r"\{\{\s*([a-z_]+)\s*\}\}")


def list_merge_fields():
    return MERGE_FIELDS


def _first_owned_vehicle(customer_id):
    for r in ledger.get_relationships():
        if r.source_id == customer_id and r.relationship_type == OWNS:
            v = ledger.get_entity(r.target_id)
            if v and v.entity_type == VEHICLE:
                return v
    return None


def get_merge_values(person_id):
    """Real per-recipient values for a Customer or Lead id -- a field with no
    real data resolves to "" (honest blank), never a fabricated placeholder."""

    person = ledger.get_entity(person_id)
    values = {f["key"]: "" for f in MERGE_FIELDS}

    if not person or person.entity_type not in (CUSTOMER, LEAD):
        return values

    values["first_name"] = person.attributes.get("FirstName", "")
    values["last_name"] = person.attributes.get("LastName", "")
    values["full_name"] = f"{values['first_name']} {values['last_name']}".strip()
    values["city"] = person.attributes.get("City", "")
    values["state"] = person.attributes.get("State", "")

    if person.entity_type == CUSTOMER:

        vehicle = _first_owned_vehicle(person.id)
        if vehicle:
            values["vehicle_year"] = str(vehicle.attributes.get("Year") or "")
            values["vehicle_make"] = vehicle.attributes.get("Make") or ""
            values["vehicle_model"] = vehicle.attributes.get("Model") or ""

        from core.smart_audiences import get_equity_candidate_for_customer

        candidate = get_equity_candidate_for_customer(person.id)
        if candidate and candidate.get("pct_term_elapsed") is not None:
            values["trade_equity_pct"] = f"{round(candidate['pct_term_elapsed'] * 100)}%"

    return values


def _substitute(text, values):
    if not text:
        return text
    return _TOKEN_RE.sub(lambda m: str(values.get(m.group(1), "")), text)


def _personalize_copy(template, values):
    """Returns a shallow-personalized copy of the template's own text fields,
    without mutating the stored template -- personalization happens at render
    time, per recipient, the real template stays the shared source of truth."""

    class _Shim:
        pass

    shim = _Shim()
    shim.attributes = dict(template.attributes)

    if shim.attributes.get("channel") == "sms":
        shim.attributes["sms_body"] = _substitute(shim.attributes.get("sms_body"), values)
        return shim

    shim.attributes["subject"] = _substitute(shim.attributes.get("subject"), values)
    shim.attributes["preheader"] = _substitute(shim.attributes.get("preheader"), values)

    new_blocks = []
    for block in shim.attributes.get("blocks", []) or []:
        new_block = {"block_key": block.get("block_key"), "fields": dict(block.get("fields") or {})}
        for fkey, fval in new_block["fields"].items():
            if isinstance(fval, str):
                new_block["fields"][fkey] = _substitute(fval, values)
        new_blocks.append(new_block)
    shim.attributes["blocks"] = new_blocks

    return shim


def render_personalized(template_id, person_id):

    template = get_template(template_id)
    if not template:
        return {"error": "Template not found"}

    values = get_merge_values(person_id)
    personalized = _personalize_copy(template, values)

    if personalized.attributes.get("channel") == "sms":
        return {
            "channel": "sms",
            "sms_body": personalized.attributes.get("sms_body"),
            "segment_info": sms_segment_info(personalized.attributes.get("sms_body")),
            "merge_values": values,
        }

    return {
        "channel": "email",
        "subject": personalized.attributes.get("subject"),
        "preheader": personalized.attributes.get("preheader"),
        "html": render_email_html(personalized),
        "text": render_email_text(personalized),
        "merge_values": values,
    }
