"""
Tests for core/marketing_studio.py -- the AI Marketing Studio: a real, thin
dispatch table over 7 already-real, independently kill-switched OpenAI wizard
functions (core/email_wizard.py, core/website_wizard.py, core/social_caption_
wizard.py, core/advertising.py), plus a real MarketingContentDraft log
(drafted -> applied/discarded) recording whether each generated piece of
content came from a real AI call or that same wizard's own honest fallback.

Every wizard function this module dispatches to is imported INSIDE
_generate_raw (a deferred, in-function import per content_type), so each is
monkeypatched on its real SOURCE module (core.email_wizard/core.website_
wizard/core.social_caption_wizard/core.advertising), not on
core.marketing_studio's own namespace.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import MARKETING_CONTENT_DRAFT

import core.marketing_studio as ms
import core.email_wizard as email_wizard_mod
import core.website_wizard as website_wizard_mod
import core.social_caption_wizard as social_caption_wizard_mod
import core.advertising as advertising_mod


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(ms, "save_graph", lambda filepath: None)


def _draft(draft_id, content_type="email_copy", status="drafted",
           created_at="2026-01-01T00:00:00+00:00", used_fallback=False,
           created_by="EMP-1"):
    e = Entity(id=draft_id, entity_type=MARKETING_CONTENT_DRAFT, attributes={
        "content_type": content_type,
        "params": {},
        "content": {"subject": "x"},
        "used_fallback": used_fallback,
        "fallback_reason": "boom" if used_fallback else None,
        "status": status,
        "created_by": created_by,
        "created_at": created_at,
        "decided_by": None,
        "decided_at": None,
    })
    ledger.add_entity(e)
    return e


class TestGenerateRawEmailAndSmsCopy:

    def test_email_copy_success_returns_content_no_fallback(self, monkeypatch):
        monkeypatch.setattr(email_wizard_mod, "generate_email_copy", lambda brief: {"subject": "Hi"})
        called = []
        monkeypatch.setattr(email_wizard_mod, "fallback_copy", lambda brief, channel: called.append(1) or {})

        content, used_fallback, error_note = ms._generate_raw("email_copy", {"goal": "reengage"})

        assert content == {"subject": "Hi"}
        assert used_fallback is False
        assert error_note is None
        assert called == []

    def test_email_copy_error_falls_back(self, monkeypatch):
        monkeypatch.setattr(email_wizard_mod, "generate_email_copy", lambda brief: {"error": "AI disabled"})
        seen = {}

        def _fallback(brief, channel):
            seen["brief"] = brief
            seen["channel"] = channel
            return {"subject": "Fallback subject"}

        monkeypatch.setattr(email_wizard_mod, "fallback_copy", _fallback)

        content, used_fallback, error_note = ms._generate_raw(
            "email_copy", {"goal": "reengage", "audience_description": "lapsed", "tone": "friendly"}
        )

        assert content == {"subject": "Fallback subject"}
        assert used_fallback is True
        assert error_note == "AI disabled"
        assert seen["channel"] == "email"
        assert seen["brief"] == {"goal": "reengage", "audience_description": "lapsed", "tone": "friendly"}

    def test_sms_copy_success(self, monkeypatch):
        monkeypatch.setattr(email_wizard_mod, "generate_sms_copy", lambda brief: {"body": "Come back!"})

        content, used_fallback, error_note = ms._generate_raw("sms_copy", {"goal": "reengage"})

        assert content == {"body": "Come back!"}
        assert used_fallback is False

    def test_sms_copy_error_falls_back_with_sms_channel(self, monkeypatch):
        monkeypatch.setattr(email_wizard_mod, "generate_sms_copy", lambda brief: {"error": "boom"})
        seen = {}

        def _fallback(brief, channel):
            seen["channel"] = channel
            return {"body": "fallback"}

        monkeypatch.setattr(email_wizard_mod, "fallback_copy", _fallback)

        content, used_fallback, error_note = ms._generate_raw("sms_copy", {})

        assert content == {"body": "fallback"}
        assert used_fallback is True
        assert seen["channel"] == "sms"

    def test_none_params_treated_as_empty_dict(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            email_wizard_mod, "generate_email_copy",
            lambda brief: seen.setdefault("brief", brief) or {"subject": "x"},
        )

        ms._generate_raw("email_copy", None)

        assert seen["brief"] == {"goal": None, "audience_description": None, "tone": None}


class TestGenerateRawWebsiteSection:

    def test_success_returns_content_as_is(self, monkeypatch):
        seen = {}

        def _regen(section_name, text_fields, dealership_name=None, tone=None, instructions=None):
            seen.update(section_name=section_name, text_fields=text_fields,
                        dealership_name=dealership_name, tone=tone, instructions=instructions)
            return {"headline": "New headline"}

        monkeypatch.setattr(website_wizard_mod, "regenerate_section_copy", _regen)

        content, used_fallback, error_note = ms._generate_raw("website_section", {
            "section_name": "hero", "text_fields": ["headline"], "dealership_name": "Sam's Autos",
            "tone": "bold", "instructions": "punchier",
        })

        assert content == {"headline": "New headline"}
        assert used_fallback is False
        assert seen == {
            "section_name": "hero", "text_fields": ["headline"], "dealership_name": "Sam's Autos",
            "tone": "bold", "instructions": "punchier",
        }

    def test_missing_text_fields_defaults_to_empty_list(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            website_wizard_mod, "regenerate_section_copy",
            lambda section_name, text_fields, **kw: seen.setdefault("text_fields", text_fields) or {},
        )

        ms._generate_raw("website_section", {"section_name": "hero"})

        assert seen["text_fields"] == []

    def test_error_returns_empty_content_no_fallback_function_called(self, monkeypatch):
        monkeypatch.setattr(website_wizard_mod, "regenerate_section_copy", lambda *a, **kw: {"error": "AI disabled"})

        content, used_fallback, error_note = ms._generate_raw("website_section", {"section_name": "hero"})

        # No dedicated fallback exists for a per-section rewrite -- an error
        # is recorded honestly (empty content, used_fallback True) rather
        # than fabricating replacement copy.
        assert content == {}
        assert used_fallback is True
        assert error_note == "AI disabled"


class TestGenerateRawWebsiteSeo:

    def test_success(self, monkeypatch):
        monkeypatch.setattr(
            website_wizard_mod, "generate_page_seo_copy",
            lambda name, page_key, page_summary=None: {"meta_title": "Home | Sam's"},
        )

        content, used_fallback, error_note = ms._generate_raw(
            "website_seo", {"dealership_name": "Sam's", "page_key": "home"}
        )

        assert content == {"meta_title": "Home | Sam's"}
        assert used_fallback is False

    def test_error_falls_back(self, monkeypatch):
        monkeypatch.setattr(website_wizard_mod, "generate_page_seo_copy", lambda *a, **kw: {"error": "down"})
        seen = {}

        def _fallback(name, page_key):
            seen.update(name=name, page_key=page_key)
            return {"meta_title": "Fallback title"}

        monkeypatch.setattr(website_wizard_mod, "fallback_seo_copy", _fallback)

        content, used_fallback, error_note = ms._generate_raw(
            "website_seo", {"dealership_name": "Sam's", "page_key": "home"}
        )

        assert content == {"meta_title": "Fallback title"}
        assert used_fallback is True
        assert error_note == "down"
        assert seen == {"name": "Sam's", "page_key": "home"}

    def test_page_summary_passed_through(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            website_wizard_mod, "generate_page_seo_copy",
            lambda name, page_key, page_summary=None: seen.setdefault("page_summary", page_summary) or {},
        )

        ms._generate_raw("website_seo", {"page_summary": "the inventory page"})

        assert seen["page_summary"] == "the inventory page"


class TestGenerateRawVehicleDescription:

    def test_success_returns_content_as_is(self, monkeypatch):
        monkeypatch.setattr(
            website_wizard_mod, "generate_vehicle_description",
            lambda name, vehicle_attrs: {"description": "A great ride."},
        )

        content, used_fallback, error_note = ms._generate_raw(
            "vehicle_description", {"dealership_name": "Sam's", "vehicle_attrs": {"Year": 2022}}
        )

        assert content == {"description": "A great ride."}
        assert used_fallback is False

    def test_vehicle_attrs_defaults_to_empty_dict(self, monkeypatch):
        seen = {}
        monkeypatch.setattr(
            website_wizard_mod, "generate_vehicle_description",
            lambda name, vehicle_attrs: seen.setdefault("vehicle_attrs", vehicle_attrs) or {},
        )

        ms._generate_raw("vehicle_description", {"dealership_name": "Sam's"})

        assert seen["vehicle_attrs"] == {}

    def test_error_falls_back_wrapped_in_description_key(self, monkeypatch):
        monkeypatch.setattr(website_wizard_mod, "generate_vehicle_description", lambda *a, **kw: {"error": "down"})
        monkeypatch.setattr(
            website_wizard_mod, "fallback_vehicle_description",
            lambda vehicle_attrs: "This vehicle is available now.",
        )

        content, used_fallback, error_note = ms._generate_raw(
            "vehicle_description", {"vehicle_attrs": {"Year": 2022}}
        )

        assert content == {"description": "This vehicle is available now."}
        assert used_fallback is True
        assert error_note == "down"


class TestGenerateRawSocialCaption:

    def test_success(self, monkeypatch):
        seen = {}

        def _gen(platform, goal=None, tone=None, vehicle=None):
            seen.update(platform=platform, goal=goal, tone=tone, vehicle=vehicle)
            return {"caption": "Check out this ride!"}

        monkeypatch.setattr(social_caption_wizard_mod, "generate_caption", _gen)

        content, used_fallback, error_note = ms._generate_raw("social_caption", {
            "platform": "instagram", "goal": "sell", "tone": "fun", "vehicle": {"Make": "Ford"},
        })

        assert content == {"caption": "Check out this ride!"}
        assert used_fallback is False
        assert seen == {"platform": "instagram", "goal": "sell", "tone": "fun", "vehicle": {"Make": "Ford"}}

    def test_error_falls_back(self, monkeypatch):
        monkeypatch.setattr(social_caption_wizard_mod, "generate_caption", lambda *a, **kw: {"error": "boom"})
        seen = {}

        def _fallback(platform, goal=None, vehicle=None):
            seen.update(platform=platform, goal=goal, vehicle=vehicle)
            return {"caption": "Fallback caption"}

        monkeypatch.setattr(social_caption_wizard_mod, "fallback_caption", _fallback)

        content, used_fallback, error_note = ms._generate_raw(
            "social_caption", {"platform": "x", "goal": "sell", "vehicle": None}
        )

        assert content == {"caption": "Fallback caption"}
        assert used_fallback is True
        assert error_note == "boom"
        assert seen == {"platform": "x", "goal": "sell", "vehicle": None}


class TestGenerateRawAdRecommendation:

    def test_success(self, monkeypatch):
        seen = {}

        def _gen(brief):
            seen["brief"] = brief
            return {"headline": "Great deal"}

        monkeypatch.setattr(advertising_mod, "generate_ad_recommendation", _gen)

        content, used_fallback, error_note = ms._generate_raw("ad_recommendation", {
            "platform": "meta", "objective": "leads", "audience_description": "local buyers",
            "vehicle_description": "2022 Ford F-150",
        })

        assert content == {"headline": "Great deal"}
        assert used_fallback is False
        assert seen["brief"] == {
            "platform": "meta", "objective": "leads", "audience_description": "local buyers",
            "vehicle_description": "2022 Ford F-150",
        }

    def test_error_falls_back(self, monkeypatch):
        monkeypatch.setattr(advertising_mod, "generate_ad_recommendation", lambda brief: {"error": "boom"})
        seen = {}

        def _fallback(brief):
            seen["brief"] = brief
            return {"headline": "Fallback headline"}

        monkeypatch.setattr(advertising_mod, "fallback_recommendation", _fallback)

        content, used_fallback, error_note = ms._generate_raw("ad_recommendation", {"platform": "meta"})

        assert content == {"headline": "Fallback headline"}
        assert used_fallback is True
        assert error_note == "boom"
        assert seen["brief"]["platform"] == "meta"


class TestGenerateRawUnknownType:

    def test_returns_all_none(self):
        content, used_fallback, error_note = ms._generate_raw("not_a_real_type", {})
        assert content is None
        assert used_fallback is None
        assert error_note is None


class TestGenerateContent:

    def test_invalid_content_type_returns_error(self):
        result = ms.generate_content("bogus_type", {}, "EMP-1")
        assert "content_type must be one of" in result["error"]

    def test_no_dispatcher_registered_returns_error(self, monkeypatch):
        monkeypatch.setattr(ms, "_generate_raw", lambda content_type, params: (None, None, None))

        result = ms.generate_content("email_copy", {}, "EMP-1")

        assert result == {"error": "No dispatcher registered for content_type 'email_copy'"}

    def test_successful_generation_creates_persisted_entity(self, monkeypatch):
        monkeypatch.setattr(email_wizard_mod, "generate_email_copy", lambda brief: {"subject": "Hi there"})

        entity = ms.generate_content("email_copy", {"goal": "reengage"}, "EMP-1")

        assert entity.id.startswith("MCD")
        assert entity.entity_type == MARKETING_CONTENT_DRAFT
        assert entity.attributes["content_type"] == "email_copy"
        assert entity.attributes["params"] == {"goal": "reengage"}
        assert entity.attributes["content"] == {"subject": "Hi there"}
        assert entity.attributes["used_fallback"] is False
        assert entity.attributes["fallback_reason"] is None
        assert entity.attributes["status"] == "drafted"
        assert entity.attributes["created_by"] == "EMP-1"
        assert entity.attributes["created_at"]
        assert entity.attributes["decided_by"] is None
        assert entity.attributes["decided_at"] is None

        # Really persisted to the ledger, not just returned.
        assert ledger.get_entity(entity.id) is entity

    def test_none_params_stored_as_empty_dict(self, monkeypatch):
        monkeypatch.setattr(email_wizard_mod, "generate_email_copy", lambda brief: {"subject": "Hi"})

        entity = ms.generate_content("email_copy", None, "EMP-1")

        assert entity.attributes["params"] == {}

    def test_fallback_generation_records_fallback_reason(self, monkeypatch):
        monkeypatch.setattr(email_wizard_mod, "generate_email_copy", lambda brief: {"error": "AI disabled"})
        monkeypatch.setattr(email_wizard_mod, "fallback_copy", lambda brief, channel: {"subject": "Fallback"})

        entity = ms.generate_content("email_copy", {}, "EMP-1")

        assert entity.attributes["used_fallback"] is True
        assert entity.attributes["fallback_reason"] == "AI disabled"


class TestGetDraft:

    def test_returns_none_for_missing_id(self):
        assert ms._get_draft("MCD-00099") is None

    def test_returns_none_for_wrong_entity_type(self):
        from core.entity_types import LEAD
        ledger.add_entity(Entity(id="MCD-00001", entity_type=LEAD, attributes={}))
        assert ms._get_draft("MCD-00001") is None

    def test_returns_entity_for_correct_type(self):
        d = _draft("MCD-00001")
        assert ms._get_draft("MCD-00001") is d


class TestMarkAppliedAndDiscarded:

    def test_mark_applied_not_found(self):
        result = ms.mark_applied("MCD-00099", "EMP-1")
        assert result == {"error": "Content draft not found"}

    def test_mark_applied_success(self):
        _draft("MCD-00001", status="drafted")

        result = ms.mark_applied("MCD-00001", "EMP-2")

        assert result.attributes["status"] == "applied"
        assert result.attributes["decided_by"] == "EMP-2"
        assert result.attributes["decided_at"]

    def test_mark_discarded_success(self):
        _draft("MCD-00001", status="drafted")

        result = ms.mark_discarded("MCD-00001", "EMP-2")

        assert result.attributes["status"] == "discarded"

    def test_cannot_change_already_applied_draft(self):
        _draft("MCD-00001", status="applied")

        result = ms.mark_discarded("MCD-00001", "EMP-2")

        assert result == {"error": "Cannot change a draft that is already 'applied'."}

    def test_cannot_change_already_discarded_draft(self):
        _draft("MCD-00001", status="discarded")

        result = ms.mark_applied("MCD-00001", "EMP-2")

        assert result == {"error": "Cannot change a draft that is already 'discarded'."}


class TestListContentDrafts:

    def test_empty_when_none_exist(self):
        assert ms.list_content_drafts() == []

    def test_filters_by_content_type(self):
        _draft("MCD-00001", content_type="email_copy")
        _draft("MCD-00002", content_type="social_caption")

        result = ms.list_content_drafts(content_type="social_caption")

        assert [d.id for d in result] == ["MCD-00002"]

    def test_filters_by_status(self):
        _draft("MCD-00001", status="drafted")
        _draft("MCD-00002", status="applied")

        result = ms.list_content_drafts(status="applied")

        assert [d.id for d in result] == ["MCD-00002"]

    def test_filters_by_created_by(self):
        _draft("MCD-00001", created_by="EMP-1")
        _draft("MCD-00002", created_by="EMP-2")

        result = ms.list_content_drafts(created_by="EMP-2")

        assert [d.id for d in result] == ["MCD-00002"]

    def test_sorted_by_created_at_descending(self):
        _draft("MCD-00001", created_at="2026-01-01T00:00:00+00:00")
        _draft("MCD-00002", created_at="2026-03-01T00:00:00+00:00")
        _draft("MCD-00003", created_at="2026-02-01T00:00:00+00:00")

        result = ms.list_content_drafts()

        assert [d.id for d in result] == ["MCD-00002", "MCD-00003", "MCD-00001"]


class TestDraftBrief:

    def test_shape(self):
        d = _draft("MCD-00001", content_type="email_copy", status="drafted", used_fallback=True)

        brief = ms._draft_brief(d)

        assert brief == {
            "id": "MCD-00001",
            "content_type": "email_copy",
            "params": {},
            "content": {"subject": "x"},
            "used_fallback": True,
            "fallback_reason": "boom",
            "status": "drafted",
            "created_by": "EMP-1",
            "created_at": "2026-01-01T00:00:00+00:00",
            "decided_by": None,
            "decided_at": None,
        }


class TestGetStudioOverview:

    def test_empty_state(self):
        result = ms.get_studio_overview()

        assert result["total_drafts"] == 0
        assert result["by_content_type"] == {}
        assert result["by_status"] == {}
        assert result["fallback_count"] == 0
        assert result["recent_drafts"] == []
        assert result["content_type_catalog"] == ms.CONTENT_TYPE_CATALOG
        assert len(result["content_type_catalog"]) == 7

    def test_counts_aggregate_across_type_status_and_fallback(self):
        _draft("MCD-00001", content_type="email_copy", status="drafted", used_fallback=False)
        _draft("MCD-00002", content_type="email_copy", status="applied", used_fallback=True)
        _draft("MCD-00003", content_type="social_caption", status="drafted", used_fallback=True)

        result = ms.get_studio_overview()

        assert result["total_drafts"] == 3
        assert result["by_content_type"] == {"email_copy": 2, "social_caption": 1}
        assert result["by_status"] == {"drafted": 2, "applied": 1}
        assert result["fallback_count"] == 2

    def test_recent_drafts_capped_at_25_most_recent_first(self):
        for i in range(30):
            _draft(f"MCD-{i:05d}", created_at=f"2026-01-{(i % 28) + 1:02d}T00:00:{i:02d}+00:00")

        result = ms.get_studio_overview()

        assert len(result["recent_drafts"]) == 25
        full_order = [d.id for d in ms.list_content_drafts()]
        assert [b["id"] for b in result["recent_drafts"]] == full_order[:25]
