"""
Tests for core/event_campaign_generator.py / core/event_campaign_generator_api.py --
the Marketing Growth Platform's Event Campaign Generator (the third of the "War Room,
Project Management, Campaign Generator" items closed out for Events, session 84
follow-up). Run from backend/ with `pytest`.

Composes three real modules (core/dealership_events.py's Event, core/campaigns.py's
"event_promo" Campaign type, core/email_templates.py's EmailTemplate) with the
OpenAI-backed core/email_wizard.py functions mocked directly on this module's own
namespace (generate_email_copy/generate_sms_copy/fallback_copy were imported by name
into event_campaign_generator.py, so the correct mock target is that name on THIS
module, not two layers deep into email_wizard's own OpenAI client) -- the same
dependency-injection-via-monkeypatch pattern already proven for
core/network_snapshot.py's compute_department/get_or_create_pseudonym.

Covers: _event_brief()'s goal/audience_description construction (name/event_type/
location/start_time present-or-defaulted, event_type underscore replacement);
generate_event_campaign_draft()'s event-not-found and unknown-channel errors, the
sms-vs-email copy-generation branching, and the "falsy or error copy -> fall back"
behavior on both channels (draft-only, confirms nothing is persisted);
create_event_campaign()'s same two validations, real EmailTemplate creation, the sms
branch's sms_body update, the email branch's block assembly (heading/body/button/
footer with each field's own real fallback chain), the real "event_promo" Campaign
creation with correct params/linked_template_id, campaign-creation-error passthrough,
the template<->campaign cross-link, and the final {"campaign": ..., "template": ...}
shape; and list_campaigns_for_event()'s campaign_type + params.event_id filtering.
Also covers event_campaign_generator_api.py's ACL layer: generate_event_campaign_
draft_api has no role gate at all (any role can preview), create_event_campaign_api
is scoped to ADMIN/MARKETING/SALES, and list_campaigns_for_event_api has no role
gate either.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core import event_campaign_generator
from core import event_campaign_generator_api
from core import dealership_events
from core import campaigns
from core import email_templates
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, FINANCE, SERVICE


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(dealership_events, "save_graph", lambda filepath: None)
    monkeypatch.setattr(campaigns, "save_graph", lambda filepath: None)
    monkeypatch.setattr(email_templates, "save_graph", lambda filepath: None)


def _make_event(name="Fall VIP Sale", event_type="vip_sale", start_time="2026-09-15T10:00:00", location="Main Showroom"):
    return dealership_events.create_event("EMP-1", name, event_type, start_time, location=location)


class TestEventBrief:

    def test_goal_includes_name_type_when_and_where(self):
        event = _make_event(name="Fall VIP Sale", event_type="vip_sale", start_time="2026-09-15T10:00:00", location="Main Showroom")
        goal, audience_description = event_campaign_generator._event_brief(event)

        assert "Fall VIP Sale" in goal
        assert "vip sale" in goal  # underscore replaced with a space
        assert "on 2026-09-15" in goal
        assert "at Main Showroom" in goal

    def test_goal_omits_when_and_where_when_not_supplied(self):
        event = dealership_events.create_event("EMP-1", "Community Day", "community", None, location="")
        goal, _ = event_campaign_generator._event_brief(event)

        assert " on " not in goal
        assert " at " not in goal

    def test_event_type_underscores_replaced_with_spaces(self):
        event = _make_event(event_type="product_launch")
        goal, _ = event_campaign_generator._event_brief(event)
        assert "product launch" in goal

    def test_audience_description_references_event_name(self):
        event = _make_event(name="Spring Test Drive Weekend")
        _, audience_description = event_campaign_generator._event_brief(event)
        assert "Spring Test Drive Weekend" in audience_description
        assert "dealership event" in audience_description

    def test_missing_name_falls_back_to_generic_phrase(self):
        # create_event() itself defaults name to "New Event" when falsy, so simulate a
        # genuinely empty name attribute directly on the entity to exercise
        # _event_brief()'s own `or "our upcoming event"` fallback.
        event = _make_event()
        event.attributes["name"] = ""
        goal, _ = event_campaign_generator._event_brief(event)
        assert "our upcoming event" in goal

    def test_missing_event_type_falls_back_to_generic_event(self):
        event = _make_event()
        event.attributes["event_type"] = ""
        goal, _ = event_campaign_generator._event_brief(event)
        assert "a event" in goal


class TestGenerateEventCampaignDraft:

    def test_event_not_found(self):
        result = event_campaign_generator.generate_event_campaign_draft("EVT-BOGUS")
        assert result == {"error": "Event not found"}

    def test_unknown_channel_rejected(self):
        event = _make_event()
        result = event_campaign_generator.generate_event_campaign_draft(event.id, channel="carrier_pigeon")
        assert "error" in result

    def test_email_channel_calls_generate_email_copy_with_full_brief(self, monkeypatch):
        event = _make_event()
        captured = {}

        def _fake_generate_email_copy(brief):
            captured["brief"] = brief
            return {"subject": "Come to our event!", "body": "Details inside.", "heading": "Big News", "cta_text": "RSVP", "preheader": "preview"}

        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", _fake_generate_email_copy)

        result = event_campaign_generator.generate_event_campaign_draft(event.id, channel="email", tone="excited")

        assert result["event_id"] == event.id
        assert result["channel"] == "email"
        assert result["copy"]["subject"] == "Come to our event!"
        assert captured["brief"]["tone"] == "excited"
        assert captured["brief"]["goal"] == result["goal"]
        assert "audience_description" in captured["brief"]

    def test_sms_channel_calls_generate_sms_copy(self, monkeypatch):
        event = _make_event()

        monkeypatch.setattr(event_campaign_generator, "generate_sms_copy", lambda brief: {"sms_body": "Come to our event!"})

        result = event_campaign_generator.generate_event_campaign_draft(event.id, channel="sms")

        assert result["channel"] == "sms"
        assert result["copy"] == {"sms_body": "Come to our event!"}

    def test_email_falls_back_when_copy_has_error_key(self, monkeypatch):
        event = _make_event()

        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"error": "disabled", "disabled": True})
        monkeypatch.setattr(event_campaign_generator, "fallback_copy", lambda brief, channel: {"subject": "FALLBACK", "channel_used": channel})

        result = event_campaign_generator.generate_event_campaign_draft(event.id, channel="email")

        assert result["copy"] == {"subject": "FALLBACK", "channel_used": "email"}

    def test_email_falls_back_when_copy_is_falsy(self, monkeypatch):
        event = _make_event()

        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: None)
        monkeypatch.setattr(event_campaign_generator, "fallback_copy", lambda brief, channel: {"subject": "FALLBACK2"})

        result = event_campaign_generator.generate_event_campaign_draft(event.id, channel="email")
        assert result["copy"] == {"subject": "FALLBACK2"}

    def test_sms_falls_back_when_copy_has_error_key(self, monkeypatch):
        event = _make_event()

        monkeypatch.setattr(event_campaign_generator, "generate_sms_copy", lambda brief: {"error": "boom"})
        monkeypatch.setattr(event_campaign_generator, "fallback_copy", lambda brief, channel: {"sms_body": "SMS FALLBACK"})

        result = event_campaign_generator.generate_event_campaign_draft(event.id, channel="sms")
        assert result["copy"] == {"sms_body": "SMS FALLBACK"}

    def test_draft_creates_no_real_campaign_or_template(self, monkeypatch):
        event = _make_event()
        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"subject": "x"})

        event_campaign_generator.generate_event_campaign_draft(event.id, channel="email")

        assert campaigns.list_campaigns() == []
        assert email_templates.list_templates() == []


class TestCreateEventCampaign:

    def test_event_not_found(self):
        result = event_campaign_generator.create_event_campaign("EVT-BOGUS", "email", "EMP-1")
        assert result == {"error": "Event not found"}

    def test_unknown_channel_rejected(self):
        event = _make_event()
        result = event_campaign_generator.create_event_campaign(event.id, "carrier_pigeon", "EMP-1")
        assert "error" in result

    def test_email_creates_real_template_and_campaign_with_correct_blocks(self, monkeypatch):
        event = _make_event(name="Fall VIP Sale")

        monkeypatch.setattr(
            event_campaign_generator, "generate_email_copy",
            lambda brief: {
                "subject": "Join us!", "preheader": "preview text",
                "heading": "You're Invited", "body": "Come see us.", "cta_text": "RSVP Now",
            },
        )

        result = event_campaign_generator.create_event_campaign(event.id, "email", "EMP-9", tone="excited")

        campaign = result["campaign"]
        template = result["template"]

        assert campaign.attributes["campaign_type"] == "event_promo"
        assert campaign.attributes["name"] == "Fall VIP Sale Promotion"
        assert campaign.attributes["channel"] == "email"
        assert campaign.attributes["created_by"] == "EMP-9"
        assert campaign.attributes["params"] == {"event_id": event.id}
        assert campaign.attributes["linked_template_id"] == template.id

        assert template.attributes["channel"] == "email"
        assert template.attributes["name"] == "Fall VIP Sale Promo"
        assert template.attributes["ai_generated"] is True
        assert template.attributes["subject"] == "Join us!"
        assert template.attributes["preheader"] == "preview text"
        # The second update_template() call cross-links the template back to the
        # campaign, since the campaign didn't exist yet when the template was created.
        assert template.attributes["linked_campaign_id"] == campaign.id

        blocks = template.attributes["blocks"]
        assert blocks[0] == {"block_key": "heading", "fields": {"text": "You're Invited"}}
        assert blocks[1] == {"block_key": "paragraph", "fields": {"text": "Come see us."}}
        assert blocks[2] == {"block_key": "button", "fields": {"text": "RSVP Now", "url": ""}}
        assert blocks[3]["block_key"] == "footer"
        assert blocks[3]["fields"]["text"] == email_templates.BLOCK_TYPES["footer"]["fields"][0]["default"]

    def test_email_heading_falls_back_to_subject_then_event_name(self, monkeypatch):
        event = _make_event(name="Fall VIP Sale")

        # No "heading" key at all -- should fall back to "subject".
        monkeypatch.setattr(
            event_campaign_generator, "generate_email_copy",
            lambda brief: {"subject": "Subject Only", "body": "body text"},
        )

        result = event_campaign_generator.create_event_campaign(event.id, "email", "EMP-1")
        blocks = result["template"].attributes["blocks"]
        assert blocks[0]["fields"]["text"] == "Subject Only"

    def test_email_heading_falls_back_to_event_name_when_neither_heading_nor_subject(self, monkeypatch):
        event = _make_event(name="Fall VIP Sale")

        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"body": "body text"})

        result = event_campaign_generator.create_event_campaign(event.id, "email", "EMP-1")
        blocks = result["template"].attributes["blocks"]
        assert blocks[0]["fields"]["text"] == "Fall VIP Sale"

    def test_email_cta_text_defaults_to_rsvp_now_when_absent(self, monkeypatch):
        event = _make_event()

        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"subject": "x", "body": "y"})

        result = event_campaign_generator.create_event_campaign(event.id, "email", "EMP-1")
        blocks = result["template"].attributes["blocks"]
        assert blocks[2]["fields"]["text"] == "RSVP Now"

    def test_email_subject_falls_back_to_event_name_when_copy_has_no_subject(self, monkeypatch):
        event = _make_event(name="Fall VIP Sale")

        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"body": "y"})

        result = event_campaign_generator.create_event_campaign(event.id, "email", "EMP-1")
        assert result["template"].attributes["subject"] == "Fall VIP Sale"

    def test_email_falls_back_to_fallback_copy_on_error(self, monkeypatch):
        event = _make_event()

        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"error": "disabled"})
        monkeypatch.setattr(
            event_campaign_generator, "fallback_copy",
            lambda brief, channel: {"subject": "FB Subject", "body": "FB Body", "heading": "FB Heading", "cta_text": "FB CTA", "preheader": "FB Pre"},
        )

        result = event_campaign_generator.create_event_campaign(event.id, "email", "EMP-1")
        assert result["template"].attributes["subject"] == "FB Subject"
        blocks = result["template"].attributes["blocks"]
        assert blocks[0]["fields"]["text"] == "FB Heading"
        assert blocks[1]["fields"]["text"] == "FB Body"
        assert blocks[2]["fields"]["text"] == "FB CTA"

    def test_sms_updates_sms_body_only(self, monkeypatch):
        event = _make_event()

        monkeypatch.setattr(event_campaign_generator, "generate_sms_copy", lambda brief: {"sms_body": "Hi there!"})

        result = event_campaign_generator.create_event_campaign(event.id, "sms", "EMP-1")

        template = result["template"]
        assert template.attributes["channel"] == "sms"
        assert template.attributes["sms_body"] == "Hi there!"
        # Only sms_body should be touched -- subject/preheader/blocks stay at their
        # create_template() defaults for an sms channel template.
        assert template.attributes["subject"] is None
        assert template.attributes["blocks"] == []

    def test_sms_falls_back_to_fallback_copy_on_falsy_result(self, monkeypatch):
        event = _make_event()

        monkeypatch.setattr(event_campaign_generator, "generate_sms_copy", lambda brief: None)
        monkeypatch.setattr(event_campaign_generator, "fallback_copy", lambda brief, channel: {"sms_body": "SMS FB"})

        result = event_campaign_generator.create_event_campaign(event.id, "sms", "EMP-1")
        assert result["template"].attributes["sms_body"] == "SMS FB"

    def test_campaign_creation_error_is_passed_through(self, monkeypatch):
        event = _make_event()

        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"subject": "x"})
        monkeypatch.setattr(event_campaign_generator, "create_campaign", lambda *a, **k: {"error": "campaign creation failed"})

        result = event_campaign_generator.create_event_campaign(event.id, "email", "EMP-1")
        assert result == {"error": "campaign creation failed"}

    def test_repeated_calls_produce_distinct_campaigns_and_templates(self, monkeypatch):
        event = _make_event()
        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"subject": "x"})

        first = event_campaign_generator.create_event_campaign(event.id, "email", "EMP-1")
        second = event_campaign_generator.create_event_campaign(event.id, "email", "EMP-1")

        assert first["campaign"].id != second["campaign"].id
        assert first["template"].id != second["template"].id


class TestListCampaignsForEvent:

    def test_returns_only_event_promo_campaigns_matching_the_event_id(self, monkeypatch):
        event_a = _make_event(name="Event A")
        event_b = _make_event(name="Event B")

        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"subject": "x"})

        result_a = event_campaign_generator.create_event_campaign(event_a.id, "email", "EMP-1")
        event_campaign_generator.create_event_campaign(event_b.id, "email", "EMP-1")

        # An unrelated non-event_promo campaign for the same imaginary params.
        campaigns.create_campaign("general", "Unrelated General Campaign", "email", "EMP-1", {})

        results = event_campaign_generator.list_campaigns_for_event(event_a.id)

        assert len(results) == 1
        assert results[0].id == result_a["campaign"].id

    def test_no_matching_campaigns_returns_empty_list(self):
        event = _make_event()
        assert event_campaign_generator.list_campaigns_for_event(event.id) == []


class TestEventCampaignGeneratorApiAcl:

    _ALLOWED_CREATE = [ADMIN, MARKETING, SALES]
    _DENIED_CREATE = [OPERATIONS, FINANCE, SERVICE]

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, MARKETING, FINANCE, SERVICE])
    def test_generate_draft_api_has_no_role_gate(self, role, monkeypatch):
        event = _make_event()
        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"subject": "x"})

        result = event_campaign_generator_api.generate_event_campaign_draft_api(role, event.id, channel="email")

        assert "error" not in result
        assert result["event_id"] == event.id

    @pytest.mark.parametrize("role", _ALLOWED_CREATE)
    def test_create_event_campaign_api_allowed_roles(self, role, monkeypatch):
        event = _make_event()
        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"subject": "x"})

        result = event_campaign_generator_api.create_event_campaign_api(role, "EMP-1", event.id, "email")

        assert "error" not in result
        assert "campaign" in result
        assert "template" in result
        # Serialized shape -- plain dicts, not raw Entity objects.
        assert isinstance(result["campaign"], dict)
        assert "id" in result["campaign"]
        assert isinstance(result["template"], dict)
        assert "id" in result["template"]

    @pytest.mark.parametrize("role", _DENIED_CREATE)
    def test_create_event_campaign_api_denied_roles(self, role):
        result = event_campaign_generator_api.create_event_campaign_api(role, "EMP-1", "EVT-BOGUS", "email")
        assert result == {"error": "Only admin/marketing/sales can generate a real event campaign"}

    def test_create_event_campaign_api_error_from_core_passed_through_unwrapped(self):
        result = event_campaign_generator_api.create_event_campaign_api(ADMIN, "EMP-1", "EVT-BOGUS", "email")
        assert result == {"error": "Event not found"}

    @pytest.mark.parametrize("role", [ADMIN, OPERATIONS, SALES, MARKETING, FINANCE, SERVICE])
    def test_list_campaigns_for_event_api_has_no_role_gate(self, role, monkeypatch):
        event = _make_event()
        monkeypatch.setattr(event_campaign_generator, "generate_email_copy", lambda brief: {"subject": "x"})
        event_campaign_generator.create_event_campaign(event.id, "email", "EMP-1")

        result = event_campaign_generator_api.list_campaigns_for_event_api(role, event.id)

        assert isinstance(result, list)
        assert len(result) == 1
        assert "id" in result[0]
