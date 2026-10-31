"""
Email / SMS builder engine (2026-07-15, session 79) -- Sam: "add an Email/SMS dash
with a fully functional email builder (for mass and individual campaigns). It should
have an Ai build an email wizard as well as a traditional drag and drop modual /
mailchimp builder. it should have a toggle to switch to a texting / sms builder. Both
pull from the CRM."

Same graph-native rule as everything else here: an EmailTemplate is one ordinary
Entity in the same core.dealeros.ledger every other entity type lives in. Two channels
share one entity type (distinguished by `channel`) rather than a parallel SmsTemplate
type -- an SMS "template" is just a plain-text body with no blocks, same "one engine,
not two near-identical ones" discipline core/workflow_tab_data.py's REAL_SOURCES /
core/menu_data.py's MENU_SOURCES already follow.

BLOCK_TYPES is a fixed starter catalog for the drag-and-drop email builder, mirroring
core/websites.py's SECTION_TEMPLATES shape exactly (fixed catalog + a small `fields`
schema the frontend renders as a form) -- template-fill blocks, not a freeform canvas,
same scoping decision already made for website sections and marketing assets.

update_template() takes a whole-object patch (name/subject/preheader/blocks/sms_body)
rather than core/websites.py's granular per-section add/remove/lock calls -- a
drag-and-drop block canvas naturally manages its full ordered list client-side and
saves it in one call, the same "whole-array replace" shape
core/dashboard_layouts.py's save_layout(modules) already established for another
drag-and-drop grid builder in this codebase.

No real send integration exists (no email/SMS provider wired up) -- same honest
non-integration as core/campaigns.py's activate_campaign() (SIMULATES a send). A
template becomes a real send only once it's attached to a Campaign via
linked_template_id and that Campaign is activated (core/campaigns_api.py).
"""

import re
from datetime import datetime, timezone

from core.dealeros import ledger, id_generator
from core.entities import Entity
from core.entity_types import EMAIL_TEMPLATE
from core.storage import save_graph
from core.storage_paths import GRAPH_PATH

# Real, pre-existing data-loss bug found and fixed (2026-07-18, Marketing Growth
# Platform, Email/SMS upgrades slice) -- the same missing-save_graph bug class
# found in core/deals.py/core/marketing_lists.py (session 105) and
# core/campaigns.py (this same slice, moments earlier): create_template()/
# update_template() had never once called save_graph() since this module
# shipped (session 79). Every real EmailTemplate ever created through the live
# app was silently discarded on server restart. Fixed below.


CHANNELS = ["email", "sms"]

# Fixed starter catalog -- one entry per drag-and-drop building block, mirrors
# core/websites.py's SECTION_TEMPLATES. Email-only (SMS has no blocks -- it's a single
# plain-text body, see sms_segment_info()).
BLOCK_TYPES = {
    "heading": {
        "key": "heading",
        "name": "Heading",
        "description": "A large headline.",
        "fields": [
            {"key": "text", "label": "Heading Text", "type": "text", "required": True},
        ],
    },
    "paragraph": {
        "key": "paragraph",
        "name": "Paragraph",
        "description": "A block of body text.",
        "fields": [
            {"key": "text", "label": "Body Text", "type": "textarea", "required": True},
        ],
    },
    "image": {
        "key": "image",
        "name": "Image",
        "description": "A single image, full-width.",
        "fields": [
            {"key": "image_url", "label": "Image URL", "type": "text", "required": True},
            {"key": "alt_text", "label": "Alt Text", "type": "text", "required": False},
        ],
    },
    "button": {
        "key": "button",
        "name": "Button / CTA",
        "description": "A call-to-action button.",
        "fields": [
            {"key": "text", "label": "Button Text", "type": "text", "required": True, "default": "Shop Now"},
            {"key": "url", "label": "Link URL", "type": "text", "required": True},
        ],
    },
    "divider": {
        "key": "divider",
        "name": "Divider",
        "description": "A thin horizontal rule.",
        "fields": [],
    },
    "spacer": {
        "key": "spacer",
        "name": "Spacer",
        "description": "Blank vertical space.",
        "fields": [
            {"key": "height", "label": "Height (px)", "type": "text", "required": False, "default": "24"},
        ],
    },
    "footer": {
        "key": "footer",
        "name": "Footer",
        "description": "Legal / unsubscribe footer text.",
        "fields": [
            {
                "key": "text",
                "label": "Footer Text",
                "type": "textarea",
                "required": False,
                "default": "You are receiving this email because you're a valued customer. Reply STOP to unsubscribe.",
            },
        ],
    },
    # Raw HTML drop-in (2026-07-23) -- Sam: "if you have claude design an email, you
    # can just drop in the HTML and it's there." A single textarea whose contents are
    # rendered verbatim (NOT escaped) by render_email_html, so an externally-designed
    # email block pastes straight in. One html block on its own template = "drop the
    # whole email in"; mixed with the other blocks = an embed.
    "html": {
        "key": "html",
        "name": "Custom HTML",
        "description": "Paste in your own HTML (e.g. an email Claude designed). Rendered exactly as written.",
        "fields": [
            {"key": "html", "label": "HTML", "type": "textarea", "required": True},
        ],
    },
}


def list_block_types():
    return list(BLOCK_TYPES.values())


def get_block_type(block_key):
    return BLOCK_TYPES.get(block_key)


def list_channels():
    return CHANNELS


def _now():
    return datetime.now(timezone.utc).isoformat()


def _all_templates():
    return [e for e in ledger.get_all().values() if e.entity_type == EMAIL_TEMPLATE]


def create_template(channel, name, created_by, ai_generated=False):

    if channel not in CHANNELS:
        channel = "email"

    template_id = id_generator.generate("TMPL")

    entity = Entity(
        id=template_id,
        entity_type=EMAIL_TEMPLATE,
        attributes={
            "channel": channel,
            "name": name or ("New Email" if channel == "email" else "New Text Message"),
            "subject": None,
            "preheader": None,
            "blocks": [],
            "sms_body": None,
            "ai_generated": bool(ai_generated),
            "linked_campaign_id": None,
            "created_by": created_by,
            "created_at": _now(),
            "updated_at": _now(),
        },
    )

    ledger.add_entity(entity)

    save_graph(GRAPH_PATH)

    return entity


_EDITABLE_FIELDS = {"name", "subject", "preheader", "blocks", "sms_body", "linked_campaign_id"}


def get_template(template_id):

    entity = ledger.get_entity(template_id)

    if entity and entity.entity_type == EMAIL_TEMPLATE:
        return entity

    return None


def update_template(template_id, patch, by=None):
    """Whole-field patch, not a granular per-block call -- see module docstring. Only
    keys in _EDITABLE_FIELDS are ever written; channel/created_by/created_at/id are
    immutable once a template exists."""

    template = get_template(template_id)

    if not template:
        return None

    for key, value in (patch or {}).items():
        if key in _EDITABLE_FIELDS:
            template.attributes[key] = value

    template.attributes["updated_at"] = _now()

    save_graph(GRAPH_PATH)

    return template


def list_templates(created_by=None, channel=None):

    templates = _all_templates()

    if created_by:
        templates = [t for t in templates if t.attributes.get("created_by") == created_by]

    if channel:
        templates = [t for t in templates if t.attributes.get("channel") == channel]

    templates.sort(key=lambda t: (t.attributes.get("updated_at", ""), t.id), reverse=True)

    return templates


def _esc(value):
    """Minimal HTML-escape for the preview renderer -- this is a template preview, not
    a general-purpose HTML sanitizer, so it only guards the handful of characters that
    would break the simple markup render_email_html() produces."""

    return (
        str(value or "")
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def render_email_html(template):
    """Real, deterministic block-to-HTML rendering -- not an AI call, not a canned
    string. Simple inline-styled markup (no external stylesheet, matching how most
    email clients actually need styles delivered) good enough for an in-app preview
    pane, not a production-grade email-client-compatibility renderer."""

    if template.attributes.get("channel") != "email":
        return None

    parts = ['<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;">']

    for block in template.attributes.get("blocks", []):

        key = block.get("block_key")
        fields = block.get("fields", {}) or {}

        if key == "heading":
            parts.append(f'<h2 style="margin:16px 0;">{_esc(fields.get("text"))}</h2>')
        elif key == "paragraph":
            text = _esc(fields.get("text")).replace("\n", "<br/>")
            parts.append(f'<p style="margin:12px 0;line-height:1.5;">{text}</p>')
        elif key == "image":
            parts.append(
                f'<img src="{_esc(fields.get("image_url"))}" alt="{_esc(fields.get("alt_text"))}" '
                f'style="max-width:100%;display:block;margin:12px 0;"/>'
            )
        elif key == "button":
            parts.append(
                f'<div style="margin:16px 0;"><a href="{_esc(fields.get("url"))}" '
                f'style="background:#2B68AB;color:#fff;padding:10px 20px;border-radius:6px;'
                f'text-decoration:none;display:inline-block;">{_esc(fields.get("text"))}</a></div>'
            )
        elif key == "divider":
            parts.append('<hr style="border:none;border-top:1px solid #ddd;margin:16px 0;"/>')
        elif key == "spacer":
            height = fields.get("height") or "24"
            parts.append(f'<div style="height:{_esc(height)}px;"></div>')
        elif key == "footer":
            parts.append(f'<p style="margin-top:24px;font-size:11px;color:#888;">{_esc(fields.get("text"))}</p>')
        elif key == "html":
            # Verbatim, deliberately NOT escaped -- this block IS raw HTML the user
            # dropped in (e.g. an email Claude designed). Same trust model as any
            # WYSIWYG "source" mode: the author is pasting their own markup.
            parts.append(str(fields.get("html") or ""))

    parts.append("</div>")

    return "".join(parts)


def render_email_text(template):
    """Plain-text fallback rendering of the same blocks -- real multipart-email
    practice (HTML + plain-text alternative), not just an HTML-only preview."""

    if template.attributes.get("channel") != "email":
        return None

    lines = []

    for block in template.attributes.get("blocks", []):

        key = block.get("block_key")
        fields = block.get("fields", {}) or {}

        if key == "heading":
            lines.append(str(fields.get("text") or "").upper())
        elif key == "paragraph":
            lines.append(str(fields.get("text") or ""))
        elif key == "image":
            lines.append(f"[image: {fields.get('image_url') or ''}]")
        elif key == "button":
            lines.append(f"{fields.get('text') or ''} -> {fields.get('url') or ''}")
        elif key == "divider":
            lines.append("----------")
        elif key == "spacer":
            lines.append("")
        elif key == "footer":
            lines.append(str(fields.get("text") or ""))
        elif key == "html":
            # Plain-text alternative of a raw-HTML block: strip tags to their text so
            # the multipart text/plain part isn't empty. Crude but honest -- real
            # tag-stripping, not a fabricated summary.
            raw = str(fields.get("html") or "")
            text = re.sub(r"<[^>]+>", " ", raw)
            text = re.sub(r"\s+", " ", text).strip()
            if text:
                lines.append(text)

        lines.append("")

    return "\n".join(lines).strip()


def sms_segment_info(body):
    """Real SMS segmentation math, not a fabricated estimate: GSM-7 (160 chars for a
    single segment / 153 per segment once concatenated across multiple) if every
    character fits the GSM-7 basic set, otherwise UCS-2 (70 / 67) the moment any
    character (emoji, most accented characters outside the GSM-7 set, etc.) forces
    Unicode encoding -- the same real rule carriers apply. Simplified GSM-7 detection
    (a plain ASCII check) is good enough to flag "this will fall back to Unicode SMS,"
    not a byte-perfect carrier implementation."""

    text = body or ""
    length = len(text)

    is_gsm7 = all(ord(c) < 128 for c in text)

    single_limit = 160 if is_gsm7 else 70
    multi_limit = 153 if is_gsm7 else 67

    if length == 0:
        segments = 0
    elif length <= single_limit:
        segments = 1
    else:
        segments = -(-length // multi_limit)  # ceil division

    return {
        "length": length,
        "encoding": "GSM-7" if is_gsm7 else "UCS-2 (Unicode)",
        "segments": segments,
        "chars_per_segment": single_limit if segments <= 1 else multi_limit,
    }
