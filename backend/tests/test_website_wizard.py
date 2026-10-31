"""
Test coverage for core/website_wizard.py -- the website setup wizard's AI content
generation: 4 real, isolated OpenAI-backed drafting functions (whole-site wizard
copy, per-section regeneration, per-page SEO meta copy, per-vehicle VDP
description), each kill-switched via core.ai_management.is_feature_enabled and
each with its own real, non-AI fallback function used when the AI call is
disabled, unreachable, or returns something unusable.

Run from backend/ with `pytest`.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import core.website_wizard as ww


class _FakeCompletions:
    def __init__(self, response_content=None, raise_exc=None):
        self._response_content = response_content
        self._raise_exc = raise_exc
        self.last_kwargs = None

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        if self._raise_exc is not None:
            raise self._raise_exc
        return _FakeResponse(self._response_content)


class _FakeResponse:
    def __init__(self, content):
        self.choices = [_FakeChoice(content)]


class _FakeChoice:
    def __init__(self, content):
        self.message = _FakeMessage(content)


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChat:
    def __init__(self, completions):
        self.completions = completions


class _FakeClient:
    def __init__(self, response_content=None, raise_exc=None):
        self.chat = _FakeChat(_FakeCompletions(response_content, raise_exc))


def _user_content(fake_client):
    return fake_client.chat.completions.last_kwargs["messages"][1]["content"]


class TestGenerateWizardCopy:

    def test_feature_disabled_returns_error_and_records_blocked(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: False)
        calls = []
        monkeypatch.setattr(ww, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))

        result = ww.generate_wizard_copy({"dealership_name": "Sam's Autos"})

        assert result == {"error": "AI website wizard is currently disabled by your administrator.", "disabled": True}
        assert calls == [("website_wizard", "blocked")]

    def test_success_returns_parsed_json_and_records_succeeded(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        calls = []
        monkeypatch.setattr(ww, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))
        fake = _FakeClient(response_content=json.dumps({"hero_headline": "Welcome!"}))
        monkeypatch.setattr(ww, "client", fake)

        result = ww.generate_wizard_copy({"dealership_name": "Sam's Autos"})

        assert result == {"hero_headline": "Welcome!"}
        assert calls == [("website_wizard", "succeeded")]

    def test_exception_returns_error_dict_and_records_fell_back(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        calls = []
        monkeypatch.setattr(ww, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome, detail)))
        monkeypatch.setattr(ww, "client", _FakeClient(raise_exc=ConnectionError("no network")))

        result = ww.generate_wizard_copy({"dealership_name": "Sam's Autos"})

        assert result == {"error": "no network"}
        assert calls[0][1] == "fell_back"
        assert calls[0][2] == "no network"

    def test_none_dealership_info_uses_defaults(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.generate_wizard_copy(None)

        content = _user_content(fake)
        assert "the dealership" in content
        assert "friendly and local" in content
        assert "Independent dealership" in content

    def test_oem_branding_included_in_user_content(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.generate_wizard_copy({"dealership_name": "Sam's Autos", "branding_mode": "oem", "oem_name": "Ford"})

        content = _user_content(fake)
        assert "OEM-affiliated (Ford)" in content

    def test_dealer_gpt_mode_included_in_user_content(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.generate_wizard_copy({"dealership_name": "Sam's Autos"}, mode="dealer_gpt")

        content = _user_content(fake)
        assert "DealerGPT stripped-down build-your-car configurator" in content

    def test_traditional_mode_included_in_user_content(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.generate_wizard_copy({"dealership_name": "Sam's Autos"}, mode="traditional")

        content = _user_content(fake)
        assert "traditional full dealership site" in content


class TestRegenerateSectionCopy:

    def test_no_fields_returns_error_before_checking_feature_flag(self, monkeypatch):
        called = []
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: called.append(key) or True)

        result = ww.regenerate_section_copy("hero_banner", [])

        assert result == {"error": "No AI-writable fields on this section"}
        assert called == []

    def test_none_fields_returns_error(self):
        result = ww.regenerate_section_copy("hero_banner", None)
        assert result == {"error": "No AI-writable fields on this section"}

    def test_feature_disabled_returns_error_and_records_blocked(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: False)
        calls = []
        monkeypatch.setattr(ww, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))

        result = ww.regenerate_section_copy("hero_banner", [{"key": "headline", "label": "Headline", "current_value": "Hi"}])

        assert result == {"error": "AI website wizard is currently disabled by your administrator.", "disabled": True}
        assert calls == [("website_wizard", "blocked")]

    def test_success_returns_parsed_dict(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({"headline": "New Headline"}))
        monkeypatch.setattr(ww, "client", fake)

        result = ww.regenerate_section_copy(
            "hero_banner", [{"key": "headline", "label": "Headline", "current_value": "Hi"}], dealership_name="Sam's Autos"
        )

        assert result == {"headline": "New Headline"}

    def test_exception_returns_error_dict(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        monkeypatch.setattr(ww, "client", _FakeClient(raise_exc=RuntimeError("boom")))

        result = ww.regenerate_section_copy("hero_banner", [{"key": "headline", "label": "Headline", "current_value": "Hi"}])

        assert result == {"error": "boom"}

    def test_missing_current_value_shows_empty_placeholder(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.regenerate_section_copy("hero_banner", [{"key": "headline", "label": "Headline", "current_value": None}])

        content = _user_content(fake)
        assert "(empty)" in content

    def test_instructions_included_when_given(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.regenerate_section_copy(
            "hero_banner", [{"key": "headline", "label": "Headline", "current_value": "Hi"}], instructions="Make it punchier"
        )

        content = _user_content(fake)
        assert "Extra instructions: Make it punchier" in content

    def test_instructions_omitted_when_not_given(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.regenerate_section_copy("hero_banner", [{"key": "headline", "label": "Headline", "current_value": "Hi"}])

        content = _user_content(fake)
        assert "Extra instructions" not in content

    def test_default_dealership_name_and_tone_used_when_omitted(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.regenerate_section_copy("hero_banner", [{"key": "headline", "label": "Headline", "current_value": "Hi"}])

        content = _user_content(fake)
        assert "the dealership" in content
        assert "friendly and local" in content


class TestGeneratePageSeoCopy:

    def test_feature_disabled_returns_error_and_records_blocked(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: False)
        calls = []
        monkeypatch.setattr(ww, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))

        result = ww.generate_page_seo_copy("Sam's Autos", "home")

        assert result == {"error": "AI website wizard is currently disabled by your administrator.", "disabled": True}
        assert calls == [("website_wizard", "blocked")]

    def test_success_returns_parsed_dict(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({"meta_title": "T", "meta_description": "D"}))
        monkeypatch.setattr(ww, "client", fake)

        result = ww.generate_page_seo_copy("Sam's Autos", "home")

        assert result == {"meta_title": "T", "meta_description": "D"}

    def test_exception_returns_error_dict(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        monkeypatch.setattr(ww, "client", _FakeClient(raise_exc=RuntimeError("boom")))

        result = ww.generate_page_seo_copy("Sam's Autos", "home")

        assert result == {"error": "boom"}

    def test_page_summary_defaults_when_none(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.generate_page_seo_copy("Sam's Autos", "inventory")

        content = _user_content(fake)
        assert "the inventory page of a car dealership website" in content

    def test_page_summary_used_when_given(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.generate_page_seo_copy("Sam's Autos", "home", page_summary="Real hero copy about trucks.")

        content = _user_content(fake)
        assert "Real hero copy about trucks." in content


class TestFallbackSeoCopy:

    def test_name_and_page_key_formatted_into_title(self):
        result = ww.fallback_seo_copy("Sam's Autos", "our_team")
        assert result["meta_title"] == "Our Team | Sam's Autos"

    def test_name_none_defaults_to_our_dealership(self):
        result = ww.fallback_seo_copy(None, "home")
        assert "Our Dealership" in result["meta_title"]

    def test_meta_title_truncated_to_60_chars(self):
        result = ww.fallback_seo_copy("A" * 100, "home")
        assert len(result["meta_title"]) <= 60

    def test_meta_description_truncated_to_158_chars(self):
        result = ww.fallback_seo_copy("Sam's Autos", "home")
        assert len(result["meta_description"]) <= 158

    def test_meta_description_mentions_page_and_name(self):
        result = ww.fallback_seo_copy("Sam's Autos", "financing")
        assert "Financing" in result["meta_description"]
        assert "Sam's Autos" in result["meta_description"]


class TestGenerateVehicleDescription:

    def test_feature_disabled_returns_error_and_records_blocked(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: False)
        calls = []
        monkeypatch.setattr(ww, "record_call_attempt", lambda feature, outcome, detail=None: calls.append((feature, outcome)))

        result = ww.generate_vehicle_description("Sam's Autos", {"Year": 2022, "Make": "Ford"})

        assert result == {"error": "AI website wizard is currently disabled by your administrator.", "disabled": True}
        assert calls == [("website_wizard", "blocked")]

    def test_success_returns_parsed_dict(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({"description": "A great truck."}))
        monkeypatch.setattr(ww, "client", fake)

        result = ww.generate_vehicle_description("Sam's Autos", {"Year": 2022, "Make": "Ford"})

        assert result == {"description": "A great truck."}

    def test_exception_returns_error_dict(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        monkeypatch.setattr(ww, "client", _FakeClient(raise_exc=RuntimeError("boom")))

        result = ww.generate_vehicle_description("Sam's Autos", {"Year": 2022})

        assert result == {"error": "boom"}

    def test_only_present_attrs_included_in_fact_lines(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.generate_vehicle_description("Sam's Autos", {"Year": 2022, "Make": "Ford"})

        content = _user_content(fake)
        assert "- Year: 2022" in content
        assert "- Make: Ford" in content
        assert "- Model:" not in content

    def test_none_vehicle_attrs_produces_no_fact_lines(self, monkeypatch):
        monkeypatch.setattr(ww, "is_feature_enabled", lambda key: True)
        monkeypatch.setattr(ww, "record_call_attempt", lambda *a, **k: None)
        fake = _FakeClient(response_content=json.dumps({}))
        monkeypatch.setattr(ww, "client", fake)

        ww.generate_vehicle_description("Sam's Autos", None)

        content = _user_content(fake)
        assert "Vehicle attributes:\n\n" in content


class TestFallbackVehicleDescription:

    def test_full_attrs_all_sentences_present(self):
        result = ww.fallback_vehicle_description({
            "Year": 2022, "Make": "Ford", "Model": "F-150", "Trim": "XLT",
            "Condition": "Used", "Mileage": 15000, "Color": "Blue",
        })
        assert "2022 Ford F-150 XLT is available now." in result
        assert "Condition: Used." in result
        assert "15,000 miles." in result
        assert "Exterior color: Blue." in result
        assert "Contact us for full details and to schedule a test drive." in result

    def test_missing_attrs_produce_generic_title(self):
        result = ww.fallback_vehicle_description({})
        assert result.startswith("This vehicle is available now.")

    def test_none_attrs_produce_generic_title(self):
        result = ww.fallback_vehicle_description(None)
        assert result.startswith("This vehicle is available now.")

    def test_string_mileage_uses_plain_format(self):
        result = ww.fallback_vehicle_description({"Mileage": "unknown"})
        assert "Mileage: unknown." in result

    def test_missing_optional_fields_are_skipped(self):
        result = ww.fallback_vehicle_description({"Year": 2022, "Make": "Ford"})
        assert "Condition:" not in result
        assert "Exterior color:" not in result
        assert "miles" not in result


class TestFallbackCopy:

    def test_name_included_in_headline_and_body(self):
        result = ww.fallback_copy({"dealership_name": "Sam's Autos"})
        assert result["hero_headline"] == "Welcome to Sam's Autos"
        assert "Sam's Autos" in result["about_body"]

    def test_none_dealership_info_defaults_to_our_dealership(self):
        result = ww.fallback_copy(None)
        assert result["hero_headline"] == "Welcome to Our Dealership"

    def test_missing_name_key_defaults_to_our_dealership(self):
        result = ww.fallback_copy({})
        assert result["hero_headline"] == "Welcome to Our Dealership"

    def test_returns_all_expected_keys(self):
        result = ww.fallback_copy({"dealership_name": "Sam's Autos"})
        assert set(result.keys()) == {
            "hero_headline", "hero_subheadline", "about_heading", "about_body",
            "financing_heading", "financing_body", "testimonials", "contact_heading",
        }

    def test_testimonials_has_exactly_3_lines(self):
        result = ww.fallback_copy({"dealership_name": "Sam's Autos"})
        assert len(result["testimonials"].split("\n")) == 3
