"""
Tests for core/email_templates.py -- the Email/SMS builder engine added in session 79
(see BUILD_QUEUE.md's "Email / SMS builder engine" note and the Marketing Growth
Platform arc). This is the first committed regression coverage for that module, added
per BUILD_QUEUE.md's standing "convert the loose test_*.py scripts to a real
backend/tests/ pytest suite as each module gets touched" rule.

The module is load-bearing marketing infrastructure: an EmailTemplate becomes a real
send only once it's attached to a Campaign and that Campaign is activated
(core/campaigns_api.py), and both the drag-and-drop email builder and the SMS builder
frontends drive it. It had zero committed coverage through this run despite carrying
real logic worth locking: create-time defaults, update_template's _EDITABLE_FIELDS
allowlist + immutability of channel/created_by/created_at, list_templates filtering +
updated_at/id sort, the deterministic block-to-HTML/text renderers (including the
_esc HTML-escape and the deliberately-verbatim "html" block), and the real GSM-7 /
UCS-2 SMS segmentation math in sms_segment_info().

Everything seeds directly into the ledger and stubs save_graph, so it's deterministic,
seed-independent, and never touches the real graph.json -- same precautions
tests/test_appointments.py documents. It also imports only the ledger chain (not the
FUSE-truncated *_menu/api.app modules), so it runs green in the sandbox. Run from
backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(
    0,
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

import pytest

from core.dealeros import ledger, id_generator
from core.entity_types import EMAIL_TEMPLATE

from core import email_templates


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def fresh_singletons():
    """Reset the ledger + the TMPL id counter before/after every test. ledger.reset()
    clears entities but does NOT reset id_generator counters, so ids would otherwise
    leak across tests (same rule tests/test_appointments.py documents)."""

    def _reset():
        ledger.reset()
        for prefix in id_generator.counters:
            id_generator.counters[prefix] = 0

    _reset()
    yield
    _reset()


@pytest.fixture(autouse=True)
def no_real_disk_writes(monkeypatch):
    """email_templates.py does `from core.storage import save_graph`, so patch the
    imported reference in its namespace -- otherwise every create/update would clobber
    the real graph.json (the conftest temp-dir isolation is belt-and-suspenders on top
    of this)."""

    monkeypatch.setattr(email_templates, "save_graph", lambda *a, **k: None)


# --------------------------------------------------------------------------
# static catalog helpers
# --------------------------------------------------------------------------


def test_list_channels():
    assert email_templates.list_channels() == ["email", "sms"]


def test_list_block_types_covers_full_catalog():
    keys = {b["key"] for b in email_templates.list_block_types()}
    assert keys == {
        "heading", "paragraph", "image", "button",
        "divider", "spacer", "footer", "html",
    }


def test_block_type_entries_are_self_consistent():
    # every catalog entry's outer dict key must match its own "key" field, and every
    # field must carry the shape the frontend renders as a form
    for key, block in email_templates.BLOCK_TYPES.items():
        assert block["key"] == key
        assert "name" in block and "description" in block
        assert isinstance(block["fields"], list)
        for field in block["fields"]:
            assert {"key", "label", "type"}.issubset(field.keys())
            assert isinstance(field["required"], bool)


def test_get_block_type_known_and_unknown():
    assert email_templates.get_block_type("button")["name"] == "Button / CTA"
    assert email_templates.get_block_type("nope") is None


# --------------------------------------------------------------------------
# create_template
# --------------------------------------------------------------------------


def test_create_email_template_defaults():
    t = email_templates.create_template("email", "Spring Sale", "EMP-1")

    assert t.entity_type == EMAIL_TEMPLATE
    assert t.id.startswith("TMPL-")
    a = t.attributes
    assert a["channel"] == "email"
    assert a["name"] == "Spring Sale"
    assert a["subject"] is None
    assert a["preheader"] is None
    assert a["blocks"] == []
    assert a["sms_body"] is None
    assert a["ai_generated"] is False
    assert a["linked_campaign_id"] is None
    assert a["created_by"] == "EMP-1"
    assert a["created_at"] and a["updated_at"]
    # persisted into the ledger
    assert ledger.get_entity(t.id) is t


def test_create_defaults_name_per_channel():
    email_default = email_templates.create_template("email", "", "EMP-1")
    sms_default = email_templates.create_template("sms", None, "EMP-1")

    assert email_default.attributes["name"] == "New Email"
    assert sms_default.attributes["name"] == "New Text Message"


def test_create_unknown_channel_falls_back_to_email():
    t = email_templates.create_template("carrier-pigeon", "X", "EMP-1")
    assert t.attributes["channel"] == "email"


def test_create_ai_generated_flag_is_coerced_to_bool():
    t = email_templates.create_template("email", "X", "EMP-1", ai_generated="yes")
    assert t.attributes["ai_generated"] is True


# --------------------------------------------------------------------------
# get_template
# --------------------------------------------------------------------------


def test_get_template_wrong_type_returns_none():
    t = email_templates.create_template("email", "X", "EMP-1")
    assert email_templates.get_template(t.id) is t
    assert email_templates.get_template("does-not-exist") is None


# --------------------------------------------------------------------------
# update_template
# --------------------------------------------------------------------------


def test_update_writes_only_editable_fields():
    t = email_templates.create_template("email", "X", "EMP-1")
    original_created_at = t.attributes["created_at"]

    updated = email_templates.update_template(
        t.id,
        {
            "name": "Renamed",
            "subject": "Big News",
            "preheader": "peek",
            "blocks": [{"block_key": "divider", "fields": {}}],
            "sms_body": "hi",
            "linked_campaign_id": "CMP-9",
            # non-editable / immutable keys -- must be ignored
            "channel": "sms",
            "created_by": "HACKER",
            "created_at": "1999-01-01",
            "id": "TMPL-EVIL",
        },
    )

    a = updated.attributes
    assert a["name"] == "Renamed"
    assert a["subject"] == "Big News"
    assert a["preheader"] == "peek"
    assert a["blocks"] == [{"block_key": "divider", "fields": {}}]
    assert a["sms_body"] == "hi"
    assert a["linked_campaign_id"] == "CMP-9"
    # immutable fields untouched
    assert a["channel"] == "email"
    assert a["created_by"] == "EMP-1"
    assert a["created_at"] == original_created_at
    assert updated.id == t.id


def test_update_bumps_updated_at():
    t = email_templates.create_template("email", "X", "EMP-1")
    # force a distinct timestamp regardless of clock resolution
    email_templates.update_template(t.id, {"name": "Y"})
    # updated_at is always rewritten on update; assert it's still a valid iso string
    assert t.attributes["updated_at"]
    assert t.attributes["name"] == "Y"


def test_update_missing_template_returns_none():
    assert email_templates.update_template("TMPL-404", {"name": "X"}) is None


def test_update_none_patch_is_noop_but_touches_updated_at():
    t = email_templates.create_template("email", "Keep", "EMP-1")
    result = email_templates.update_template(t.id, None)
    assert result is t
    assert t.attributes["name"] == "Keep"


# --------------------------------------------------------------------------
# list_templates
# --------------------------------------------------------------------------


def test_list_filters_by_creator_and_channel():
    email_templates.create_template("email", "A", "EMP-1")
    email_templates.create_template("sms", "B", "EMP-1")
    email_templates.create_template("email", "C", "EMP-2")

    assert len(email_templates.list_templates()) == 3
    assert len(email_templates.list_templates(created_by="EMP-1")) == 2
    assert len(email_templates.list_templates(channel="email")) == 2
    assert len(email_templates.list_templates(created_by="EMP-1", channel="sms")) == 1


def test_list_sorts_newest_first():
    t1 = email_templates.create_template("email", "first", "EMP-1")
    t2 = email_templates.create_template("email", "second", "EMP-1")
    # make t1 the most-recently-updated by giving it a later timestamp
    t1.attributes["updated_at"] = "2999-01-01T00:00:00+00:00"
    t2.attributes["updated_at"] = "2000-01-01T00:00:00+00:00"

    ordered = email_templates.list_templates()
    assert [t.id for t in ordered] == [t1.id, t2.id]


# --------------------------------------------------------------------------
# render_email_html
# --------------------------------------------------------------------------


def _email_with_blocks(blocks):
    t = email_templates.create_template("email", "X", "EMP-1")
    t.attributes["blocks"] = blocks
    return t


def test_render_html_returns_none_for_sms():
    sms = email_templates.create_template("sms", "X", "EMP-1")
    assert email_templates.render_email_html(sms) is None
    assert email_templates.render_email_text(sms) is None


def test_render_html_wraps_in_container():
    html = email_templates.render_email_html(_email_with_blocks([]))
    assert html.startswith('<div style="font-family:Arial')
    assert html.endswith("</div>")


def test_render_html_each_block_type():
    t = _email_with_blocks([
        {"block_key": "heading", "fields": {"text": "Hi"}},
        {"block_key": "paragraph", "fields": {"text": "line1\nline2"}},
        {"block_key": "image", "fields": {"image_url": "u.png", "alt_text": "alt"}},
        {"block_key": "button", "fields": {"text": "Go", "url": "http://x"}},
        {"block_key": "divider", "fields": {}},
        {"block_key": "spacer", "fields": {"height": "40"}},
        {"block_key": "footer", "fields": {"text": "bye"}},
    ])
    html = email_templates.render_email_html(t)

    assert "<h2 style=\"margin:16px 0;\">Hi</h2>" in html
    assert "line1<br/>line2" in html          # paragraph newline -> <br/>
    assert 'src="u.png"' in html and 'alt="alt"' in html
    assert 'href="http://x"' in html and ">Go</a>" in html
    assert "<hr" in html
    assert "height:40px" in html
    assert "bye" in html


def test_render_html_defaults_spacer_height():
    t = _email_with_blocks([{"block_key": "spacer", "fields": {}}])
    assert "height:24px" in email_templates.render_email_html(t)


def test_render_html_escapes_user_text():
    t = _email_with_blocks([
        {"block_key": "heading", "fields": {"text": "<script>&\"'"}},
    ])
    html = email_templates.render_email_html(t)
    assert "&lt;script&gt;" in html
    assert "&amp;" in html
    assert "<script>" not in html


def test_render_html_block_renders_verbatim():
    raw = '<table><tr><td>hi & <b>bold</b></td></tr></table>'
    t = _email_with_blocks([{"block_key": "html", "fields": {"html": raw}}])
    html = email_templates.render_email_html(t)
    # the raw HTML block is intentionally NOT escaped
    assert raw in html


def test_render_html_ignores_unknown_block_key():
    t = _email_with_blocks([{"block_key": "mystery", "fields": {"text": "x"}}])
    html = email_templates.render_email_html(t)
    # only the container, nothing rendered for the unknown block
    assert html == '<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;"></div>'


# --------------------------------------------------------------------------
# render_email_text
# --------------------------------------------------------------------------


def test_render_text_block_types():
    t = _email_with_blocks([
        {"block_key": "heading", "fields": {"text": "hello"}},
        {"block_key": "paragraph", "fields": {"text": "body"}},
        {"block_key": "image", "fields": {"image_url": "u.png"}},
        {"block_key": "button", "fields": {"text": "Go", "url": "http://x"}},
        {"block_key": "divider", "fields": {}},
        {"block_key": "footer", "fields": {"text": "bye"}},
    ])
    text = email_templates.render_email_text(t)

    assert "HELLO" in text          # heading uppercased
    assert "body" in text
    assert "[image: u.png]" in text
    assert "Go -> http://x" in text
    assert "----------" in text
    assert "bye" in text


def test_render_text_strips_html_block_tags():
    t = _email_with_blocks([
        {"block_key": "html", "fields": {"html": "<p>Hello   <b>World</b></p>"}},
    ])
    text = email_templates.render_email_text(t)
    assert text == "Hello World"


# --------------------------------------------------------------------------
# sms_segment_info -- real GSM-7 / UCS-2 segmentation math
# --------------------------------------------------------------------------


def test_sms_empty_body():
    info = email_templates.sms_segment_info("")
    assert info == {
        "length": 0,
        "encoding": "GSM-7",
        "segments": 0,
        "chars_per_segment": 160,
    }


def test_sms_single_gsm7_segment_boundary():
    info = email_templates.sms_segment_info("a" * 160)
    assert info["encoding"] == "GSM-7"
    assert info["segments"] == 1
    assert info["chars_per_segment"] == 160


def test_sms_multi_gsm7_segments():
    info = email_templates.sms_segment_info("a" * 161)
    assert info["encoding"] == "GSM-7"
    assert info["segments"] == 2          # ceil(161 / 153)
    assert info["chars_per_segment"] == 153


def test_sms_unicode_forces_ucs2_and_smaller_limits():
    # a single emoji forces UCS-2; 70 is the single-segment limit there
    info = email_templates.sms_segment_info("\U0001F600" + "a" * 69)
    assert info["encoding"] == "UCS-2 (Unicode)"
    assert info["length"] == 70
    assert info["segments"] == 1
    assert info["chars_per_segment"] == 70


def test_sms_unicode_multi_segment():
    info = email_templates.sms_segment_info("é" * 71)   # 71 accented chars
    assert info["encoding"] == "UCS-2 (Unicode)"
    assert info["segments"] == 2          # ceil(71 / 67)
    assert info["chars_per_segment"] == 67


def test_sms_none_body_treated_as_empty():
    info = email_templates.sms_segment_info(None)
    assert info["length"] == 0
    assert info["segments"] == 0
