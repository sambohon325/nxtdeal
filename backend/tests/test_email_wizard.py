"""
Test coverage for core/email_wizard.py -- the isolated, no-tool-calling OpenAI
wizard behind Marketing's Email/SMS CRM builder.

This sandbox has no outbound network access to the real OpenAI API (confirmed
directly here, and consistent with every other AI-wizard test file in this suite --
see e.g. test_website_wizard-style fallback coverage elsewhere) -- so
generate_email_copy()/generate_sms_copy() with the kill switch enabled genuinely hit
the real try/except network-failure path and return {"error": <connection error>},
never raising into the caller. That's real, verified sandbox behavior, not a mock.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger

import core.email_wizard as email_wizard
from core.system_config import set_feature_flag


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield
    ledger.reset()


class TestUserContent:

    def test_user_content_full_brief(self):
        brief = {
            "goal": "Sell more trucks",
            "audience_description": "Truck owners",
            "tone": "urgent",
        }
        result = email_wizard._user_content(brief)
        assert "Campaign goal: Sell more trucks" in result
        assert "Audience: Truck owners" in result
        assert "Tone: urgent" in result

    def test_user_content_empty_dict_defaults(self):
        result = email_wizard._user_content({})
        assert "a general dealership announcement" in result
        assert "our customer database" in result
        assert "friendly and professional" in result

    def test_user_content_none_brief_defaults(self):
        result = email_wizard._user_content(None)
        assert "a general dealership announcement" in result
        assert "our customer database" in result
        assert "friendly and professional" in result

    def test_user_content_partial_brief_only_overrides_given_fields(self):
        result = email_wizard._user_content({"goal": "Move aged inventory"})
        assert "Campaign goal: Move aged inventory" in result
        assert "our customer database" in result


class TestGenerateEmailCopy:

    def test_disabled_returns_disabled_error_without_network_call(self):
        set_feature_flag("ai_email_wizard_enabled", False, "EMP-TEST")
        result = email_wizard.generate_email_copy({"goal": "test"})
        assert result["disabled"] is True
        assert "disabled by your administrator" in result["error"]

    def test_enabled_but_unreachable_falls_back_to_error_dict_no_disabled_key(self):
        set_feature_flag("ai_email_wizard_enabled", True, "EMP-TEST")
        result = email_wizard.generate_email_copy({"goal": "test"})
        assert "error" in result
        assert "disabled" not in result

    def test_default_flag_state_is_enabled_on_a_fresh_ledger(self):
        # No SystemConfig entity exists yet -- is_feature_enabled() fails open,
        # so the call should reach the (unreachable, in this sandbox) OpenAI client
        # rather than short-circuiting to the disabled message.
        result = email_wizard.generate_email_copy({"goal": "test"})
        assert "disabled" not in result
        assert "error" in result


class TestGenerateSmsCopy:

    def test_disabled_returns_disabled_error_without_network_call(self):
        set_feature_flag("ai_email_wizard_enabled", False, "EMP-TEST")
        result = email_wizard.generate_sms_copy({"goal": "test"})
        assert result["disabled"] is True
        assert "disabled by your administrator" in result["error"]

    def test_enabled_but_unreachable_falls_back_to_error_dict_no_disabled_key(self):
        set_feature_flag("ai_email_wizard_enabled", True, "EMP-TEST")
        result = email_wizard.generate_sms_copy({"goal": "test"})
        assert "error" in result
        assert "disabled" not in result

    def test_email_and_sms_share_the_same_kill_switch(self):
        set_feature_flag("ai_email_wizard_enabled", False, "EMP-TEST")
        email_result = email_wizard.generate_email_copy({"goal": "test"})
        sms_result = email_wizard.generate_sms_copy({"goal": "test"})
        assert email_result["disabled"] is True
        assert sms_result["disabled"] is True


class TestFallbackCopy:

    def test_fallback_copy_sms_channel_interpolates_goal(self):
        result = email_wizard.fallback_copy({"goal": "Fall service special"}, "sms")
        assert result == {"sms_body": "Hi! Fall service special. Reply STOP to opt out."}

    def test_fallback_copy_email_channel_returns_full_shape(self):
        result = email_wizard.fallback_copy({"goal": "Fall service special"}, "email")
        assert result["subject"] == "An update from our dealership"
        assert result["preheader"] == "Fall service special"
        assert result["heading"] == "We Have News For You"
        assert "Fall service special" in result["body"]
        assert result["cta_text"] == "Learn More"

    def test_fallback_copy_any_non_sms_channel_returns_email_shape(self):
        # channel is only ever checked for equality against "sms" -- anything else
        # (including an unrecognized value) falls through to the email shape.
        result = email_wizard.fallback_copy({"goal": "x"}, "carrier_pigeon")
        assert "subject" in result
        assert "sms_body" not in result

    def test_fallback_copy_none_brief_defaults_goal(self):
        result = email_wizard.fallback_copy(None, "sms")
        assert result == {"sms_body": "Hi! an update from our dealership. Reply STOP to opt out."}

    def test_fallback_copy_empty_dict_brief_defaults_goal(self):
        result = email_wizard.fallback_copy({}, "email")
        assert result["preheader"] == "an update from our dealership"[:80]

    def test_fallback_copy_preheader_truncated_to_80_chars(self):
        long_goal = "x" * 200
        result = email_wizard.fallback_copy({"goal": long_goal}, "email")
        assert len(result["preheader"]) == 80
