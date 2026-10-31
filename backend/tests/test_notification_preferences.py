"""
Tests for core/notification_preferences.py / core/notification_preferences_api.py --
per-employee notification toggles (session 74). Run from backend/ with `pytest`.

Covers: get_preferences()'s "no saved record yet -> real defaults, not an error"
convention; save_preferences()'s full-replace-of-known-keys behavior (unknown keys
silently dropped, missing/None keys fall back to the real default, non-dict input
degrades to all defaults, truthy/falsy coercion via bool()); the single-entity-per-
employee upsert (a second save updates the same entity rather than creating a
second one, updated_at is stamped on every save); and the notification_preferences_api.py
thin pass-through layer (no ACL beyond authentication, matching its own docstring).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entity_types import NOTIFICATION_PREFERENCE
from core import notification_preferences
from core import notification_preferences_api


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


@pytest.fixture(autouse=True)
def no_real_persistence(monkeypatch):
    monkeypatch.setattr(notification_preferences, "save_graph", lambda filepath: None)


class TestGetPreferences:

    def test_no_saved_record_returns_real_defaults_not_an_error(self):
        result = notification_preferences.get_preferences("EMP-1")

        assert "error" not in result
        assert result["updated_at"] is None
        assert result["preferences"] == {
            "compliance_alerts": True,
            "workflow_updates": True,
            "direct_messages": True,
            "channel_messages": True,
            "bot_suggestions": True,
        }

    def test_get_reflects_a_prior_save(self):
        notification_preferences.save_preferences("EMP-1", {"compliance_alerts": False})

        result = notification_preferences.get_preferences("EMP-1")
        assert result["preferences"]["compliance_alerts"] is False
        assert result["updated_at"] is not None

    def test_different_employees_have_independent_preferences(self):
        notification_preferences.save_preferences("EMP-1", {"bot_suggestions": False})

        result = notification_preferences.get_preferences("EMP-2")
        assert result["preferences"]["bot_suggestions"] is True


class TestSavePreferences:

    def test_full_replace_of_known_keys(self):
        result = notification_preferences.save_preferences(
            "EMP-1",
            {
                "compliance_alerts": False,
                "workflow_updates": False,
                "direct_messages": True,
                "channel_messages": False,
                "bot_suggestions": True,
            },
        )

        assert result["preferences"] == {
            "compliance_alerts": False,
            "workflow_updates": False,
            "direct_messages": True,
            "channel_messages": False,
            "bot_suggestions": True,
        }

    def test_unknown_keys_silently_dropped(self):
        result = notification_preferences.save_preferences(
            "EMP-1", {"compliance_alerts": False, "sms_alerts": True}
        )
        assert "sms_alerts" not in result["preferences"]
        assert set(result["preferences"].keys()) == set(notification_preferences.PREFERENCE_KEYS)

    def test_missing_key_falls_back_to_default(self):
        # Only one key supplied -- every other key should still resolve to its default.
        result = notification_preferences.save_preferences("EMP-1", {"channel_messages": False})
        assert result["preferences"]["channel_messages"] is False
        assert result["preferences"]["compliance_alerts"] is True
        assert result["preferences"]["bot_suggestions"] is True

    def test_none_value_falls_back_to_default(self):
        result = notification_preferences.save_preferences("EMP-1", {"compliance_alerts": None})
        assert result["preferences"]["compliance_alerts"] is True

    def test_non_dict_input_degrades_to_all_defaults(self):
        result = notification_preferences.save_preferences("EMP-1", "not-a-dict")
        assert result["preferences"] == dict(notification_preferences.DEFAULTS)

    def test_truthy_falsy_coercion(self):
        result = notification_preferences.save_preferences(
            "EMP-1", {"compliance_alerts": 1, "workflow_updates": 0}
        )
        assert result["preferences"]["compliance_alerts"] is True
        # 0 is falsy but not None -- bool(0) is False, so this stays False, not the default.
        assert result["preferences"]["workflow_updates"] is False

    def test_second_save_updates_the_same_entity_not_a_duplicate(self):
        notification_preferences.save_preferences("EMP-1", {"compliance_alerts": False})
        notification_preferences.save_preferences("EMP-1", {"direct_messages": False})

        matches = [
            e for e in ledger.get_all().values()
            if e.entity_type == NOTIFICATION_PREFERENCE and e.attributes.get("employee_id") == "EMP-1"
        ]
        assert len(matches) == 1
        # The second save's full-replace means compliance_alerts reverts to its default
        # since it wasn't included in the second call's dict.
        assert matches[0].attributes["compliance_alerts"] is True
        assert matches[0].attributes["direct_messages"] is False

    def test_updated_at_stamped_on_every_save(self):
        first = notification_preferences.save_preferences("EMP-1", {"compliance_alerts": False})
        assert first["updated_at"] is not None

        second = notification_preferences.save_preferences("EMP-1", {"compliance_alerts": True})
        assert second["updated_at"] is not None

    def test_entity_id_is_generated_with_notif_prefix(self):
        notification_preferences.save_preferences("EMP-1", {})
        entity = notification_preferences._find("EMP-1")
        assert entity.id.startswith("NOTIF")
        assert entity.attributes["employee_id"] == "EMP-1"


class TestApi:

    def test_get_api_is_a_thin_passthrough(self):
        result = notification_preferences_api.get_notification_preferences_api("EMP-1")
        assert result["preferences"]["compliance_alerts"] is True

    def test_save_api_is_a_thin_passthrough(self):
        result = notification_preferences_api.save_notification_preferences_api(
            "EMP-1", {"bot_suggestions": False}
        )
        assert result["preferences"]["bot_suggestions"] is False

        # Confirm it actually persisted through the real module, not just echoed input.
        fetched = notification_preferences_api.get_notification_preferences_api("EMP-1")
        assert fetched["preferences"]["bot_suggestions"] is False
