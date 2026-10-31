"""Tests for core/system_config.py's brand settings + prompt templates (AI
Management dashboard, 2026-07-23) plus the core/system_config_api.py ACL layer.

Follows tests/test_system_config.py's own established conventions
(fresh_ledger + no_real_persistence autouse fixtures, class-grouped tests,
direct asserts). Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.permissions import ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE

import core.system_config as system_config
from core.system_config import (
    get_brand_settings,
    update_brand_settings,
    list_prompt_templates,
    add_prompt_template,
    remove_prompt_template,
    BRAND_TONES,
)
from core.system_config_api import (
    get_brand_settings_api,
    update_brand_settings_api,
    list_prompt_templates_api,
    add_prompt_template_api,
    remove_prompt_template_api,
)


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(system_config, "save_graph", lambda filepath: None)


# ---------------------------------------------------------------------------
# Brand settings
# ---------------------------------------------------------------------------

class TestBrandSettings:

    def test_defaults_are_professional_and_empty_free_text(self):
        settings = get_brand_settings()
        assert settings["brand_tone"] == "Professional"
        assert settings["brand_voice"] == ""
        assert settings["style_guidelines"] == ""

    def test_update_patches_only_provided_keys(self):
        update_brand_settings({"brand_voice": "Warm and local."}, "EMP-1")
        settings = get_brand_settings()
        assert settings["brand_voice"] == "Warm and local."
        # Untouched keys keep their defaults.
        assert settings["brand_tone"] == "Professional"
        assert settings["style_guidelines"] == ""

    def test_update_all_three_fields(self):
        result = update_brand_settings(
            {
                "brand_tone": "Friendly",
                "brand_voice": "Approachable.",
                "style_guidelines": "Short sentences.",
            },
            "EMP-1",
        )
        assert result["brand_tone"] == "Friendly"
        assert result["brand_voice"] == "Approachable."
        assert result["style_guidelines"] == "Short sentences."

    def test_every_valid_tone_is_accepted(self):
        for tone in BRAND_TONES:
            result = update_brand_settings({"brand_tone": tone}, "EMP-1")
            assert result["brand_tone"] == tone

    def test_an_invalid_tone_is_rejected(self):
        result = update_brand_settings({"brand_tone": "Sarcastic"}, "EMP-1")
        assert "error" in result
        # The stored tone is unchanged.
        assert get_brand_settings()["brand_tone"] == "Professional"


# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

class TestPromptTemplates:

    def test_list_is_empty_by_default(self):
        assert list_prompt_templates() == []

    def test_add_returns_a_template_with_a_prompt_id(self):
        template = add_prompt_template("Service Reminder", "Write a friendly service reminder.", "EMP-1")
        assert template["id"].startswith("PROMPT-")
        assert template["name"] == "Service Reminder"
        assert template["body"] == "Write a friendly service reminder."
        assert template["created_by"] == "EMP-1"
        assert template["created_at"]

    def test_added_templates_appear_in_the_list(self):
        add_prompt_template("A", "body a", "EMP-1")
        add_prompt_template("B", "body b", "EMP-1")
        templates = list_prompt_templates()
        assert {t["name"] for t in templates} == {"A", "B"}

    def test_add_rejects_empty_name(self):
        result = add_prompt_template("  ", "some body", "EMP-1")
        assert "error" in result
        assert list_prompt_templates() == []

    def test_add_rejects_empty_body(self):
        result = add_prompt_template("Name", "   ", "EMP-1")
        assert "error" in result
        assert list_prompt_templates() == []

    def test_remove_deletes_the_template(self):
        template = add_prompt_template("Removable", "body", "EMP-1")
        result = remove_prompt_template(template["id"])
        assert result == {"removed": template["id"]}
        assert list_prompt_templates() == []

    def test_remove_unknown_id_errors(self):
        result = remove_prompt_template("PROMPT-99999")
        assert "error" in result

    def test_ids_are_unique_across_adds(self):
        t1 = add_prompt_template("One", "b", "EMP-1")
        t2 = add_prompt_template("Two", "b", "EMP-1")
        assert t1["id"] != t2["id"]


# ---------------------------------------------------------------------------
# API ACL layer
# ---------------------------------------------------------------------------

class TestBrandAndTemplateApiAcl:

    _ALL_ROLES = (ADMIN, OPERATIONS, SALES, MARKETING, SERVICE, FINANCE)
    _WRITE_ROLES = (ADMIN, OPERATIONS)
    _READ_ONLY_ROLES = (SALES, MARKETING, SERVICE, FINANCE)

    def test_every_role_can_read_brand_settings(self):
        for role in self._ALL_ROLES:
            result = get_brand_settings_api(role)
            assert "error" not in result
            assert "brand_settings" in result
            assert set(BRAND_TONES) == set(result["tones"])

    def test_only_admin_ops_can_update_brand_settings(self):
        for role in self._WRITE_ROLES:
            result = update_brand_settings_api(role, "EMP-1", {"brand_tone": "Direct"})
            assert "error" not in result
        for role in self._READ_ONLY_ROLES:
            result = update_brand_settings_api(role, "EMP-1", {"brand_tone": "Direct"})
            assert "error" in result

    def test_every_role_can_list_prompt_templates(self):
        add_prompt_template("Seed", "body", "EMP-1")
        for role in self._ALL_ROLES:
            result = list_prompt_templates_api(role)
            assert "error" not in result
            assert len(result["prompt_templates"]) == 1

    def test_only_admin_ops_can_add_and_remove_prompt_templates(self):
        for role in self._READ_ONLY_ROLES:
            result = add_prompt_template_api(role, "EMP-1", "Nope", "body")
            assert "error" in result

        created = add_prompt_template_api(ADMIN, "EMP-1", "Yes", "body")
        assert created["id"].startswith("PROMPT-")

        for role in self._READ_ONLY_ROLES:
            result = remove_prompt_template_api(role, "EMP-1", created["id"])
            assert "error" in result

        removed = remove_prompt_template_api(OPERATIONS, "EMP-1", created["id"])
        assert removed == {"removed": created["id"]}

    def test_unknown_role_is_denied_reads(self):
        assert "error" in get_brand_settings_api("BOGUS")
        assert "error" in list_prompt_templates_api("BOGUS")
