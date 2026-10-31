"""
Tests for core/email_personalization.py -- real Dynamic Personalization for the
Email/SMS builder. A real merge-field engine: first_name/last_name/full_name/city/
state resolve off the recipient's own real Customer/Lead attributes;
vehicle_year/vehicle_make/vehicle_model resolve off the recipient's real
OWNS-linked vehicle (Customers only); trade_equity_pct reuses
core/smart_audiences.py's real get_equity_candidate_for_customer() (Customers
only). A field with no real data resolves to "" (an honest blank), never a
fabricated placeholder.

get_merge_values() imports get_equity_candidate_for_customer INSIDE the function
body (a deferred import, matching this codebase's own established
circular-import-avoidance convention) -- monkeypatching that name is therefore
done on its true origin, core.smart_audiences, not on email_personalization
itself, since the deferred import re-binds fresh on every call.

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, LEAD, VEHICLE, EMAIL_TEMPLATE
from core.relationships import Relationship
from core.relationship_types import OWNS
from core import email_personalization
from core import smart_audiences


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


def _make_customer(customer_id, **attrs):
    entity = Entity(id=customer_id, entity_type=CUSTOMER, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _make_lead(lead_id, **attrs):
    entity = Entity(id=lead_id, entity_type=LEAD, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _make_vehicle(vehicle_id, **attrs):
    entity = Entity(id=vehicle_id, entity_type=VEHICLE, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _link_owns(customer_id, vehicle_id):
    ledger.add_relationship(Relationship(source_id=customer_id, target_id=vehicle_id, relationship_type=OWNS))


def _make_template(template_id, channel="email", **attrs):
    defaults = {
        "channel": channel,
        "name": "Test Template",
        "subject": None,
        "preheader": None,
        "blocks": [],
        "sms_body": None,
    }
    defaults.update(attrs)
    entity = Entity(id=template_id, entity_type=EMAIL_TEMPLATE, attributes=defaults)
    ledger.add_entity(entity)
    return entity


class TestListMergeFields:

    def test_returns_the_real_merge_field_catalog(self):
        result = email_personalization.list_merge_fields()
        assert result is email_personalization.MERGE_FIELDS
        keys = {f["key"] for f in result}
        assert "first_name" in keys
        assert "trade_equity_pct" in keys


class TestFirstOwnedVehicle:

    def test_returns_the_real_owned_vehicle_entity(self):
        _make_customer("CUST-1")
        _make_vehicle("VEH-1", Make="Jeep")
        _link_owns("CUST-1", "VEH-1")

        result = email_personalization._first_owned_vehicle("CUST-1")

        assert result is not None
        assert result.id == "VEH-1"

    def test_returns_none_when_no_owns_relationship_exists(self):
        _make_customer("CUST-1")

        result = email_personalization._first_owned_vehicle("CUST-1")

        assert result is None

    def test_ignores_relationships_pointing_at_a_non_vehicle_entity(self):
        _make_customer("CUST-1")
        _make_customer("CUST-2")
        ledger.add_relationship(Relationship(source_id="CUST-1", target_id="CUST-2", relationship_type=OWNS))

        result = email_personalization._first_owned_vehicle("CUST-1")

        assert result is None

    def test_ignores_owns_relationships_from_a_different_source(self):
        _make_customer("CUST-1")
        _make_customer("CUST-2")
        _make_vehicle("VEH-1")
        _link_owns("CUST-2", "VEH-1")

        result = email_personalization._first_owned_vehicle("CUST-1")

        assert result is None


class TestGetMergeValues:

    def test_unknown_person_id_returns_all_blank_values(self):
        result = email_personalization.get_merge_values("CUST-BOGUS")

        assert all(v == "" for v in result.values())
        assert set(result.keys()) == {f["key"] for f in email_personalization.MERGE_FIELDS}

    def test_a_non_customer_non_lead_entity_returns_all_blank_values(self):
        _make_vehicle("VEH-1")

        result = email_personalization.get_merge_values("VEH-1")

        assert all(v == "" for v in result.values())

    def test_customer_basic_fields_resolve_from_real_attributes(self):
        _make_customer("CUST-1", FirstName="Joseph", LastName="King", City="Austin", State="TX")

        result = email_personalization.get_merge_values("CUST-1")

        assert result["first_name"] == "Joseph"
        assert result["last_name"] == "King"
        assert result["full_name"] == "Joseph King"
        assert result["city"] == "Austin"
        assert result["state"] == "TX"

    def test_customer_with_missing_first_or_last_name_produces_a_trimmed_full_name(self):
        _make_customer("CUST-1", FirstName="Joseph")

        result = email_personalization.get_merge_values("CUST-1")

        assert result["first_name"] == "Joseph"
        assert result["last_name"] == ""
        assert result["full_name"] == "Joseph"

    def test_lead_basic_fields_resolve_but_vehicle_and_equity_fields_stay_blank(self):
        _make_lead("LEAD-1", FirstName="Ann", LastName="Zed", City="Dallas", State="TX")

        result = email_personalization.get_merge_values("LEAD-1")

        assert result["first_name"] == "Ann"
        assert result["full_name"] == "Ann Zed"
        assert result["vehicle_year"] == ""
        assert result["vehicle_make"] == ""
        assert result["vehicle_model"] == ""
        assert result["trade_equity_pct"] == ""

    def test_customer_with_no_owned_vehicle_leaves_vehicle_fields_blank(self, monkeypatch):
        monkeypatch.setattr(smart_audiences, "get_equity_candidate_for_customer", lambda customer_id: None)
        _make_customer("CUST-1", FirstName="Joseph")

        result = email_personalization.get_merge_values("CUST-1")

        assert result["vehicle_year"] == ""
        assert result["vehicle_make"] == ""
        assert result["vehicle_model"] == ""

    def test_customer_with_an_owned_vehicle_resolves_real_vehicle_fields(self, monkeypatch):
        monkeypatch.setattr(smart_audiences, "get_equity_candidate_for_customer", lambda customer_id: None)
        _make_customer("CUST-1")
        _make_vehicle("VEH-1", Year=2018, Make="Jeep", Model="Compass")
        _link_owns("CUST-1", "VEH-1")

        result = email_personalization.get_merge_values("CUST-1")

        assert result["vehicle_year"] == "2018"
        assert result["vehicle_make"] == "Jeep"
        assert result["vehicle_model"] == "Compass"

    def test_customer_with_a_real_equity_candidate_resolves_trade_equity_pct(self, monkeypatch):
        monkeypatch.setattr(
            smart_audiences,
            "get_equity_candidate_for_customer",
            lambda customer_id: {"pct_term_elapsed": 0.62},
        )
        _make_customer("CUST-1")

        result = email_personalization.get_merge_values("CUST-1")

        assert result["trade_equity_pct"] == "62%"

    def test_customer_with_no_equity_candidate_leaves_trade_equity_pct_blank(self, monkeypatch):
        monkeypatch.setattr(smart_audiences, "get_equity_candidate_for_customer", lambda customer_id: None)
        _make_customer("CUST-1")

        result = email_personalization.get_merge_values("CUST-1")

        assert result["trade_equity_pct"] == ""

    def test_equity_candidate_with_none_pct_term_elapsed_leaves_trade_equity_pct_blank(self, monkeypatch):
        monkeypatch.setattr(
            smart_audiences,
            "get_equity_candidate_for_customer",
            lambda customer_id: {"pct_term_elapsed": None},
        )
        _make_customer("CUST-1")

        result = email_personalization.get_merge_values("CUST-1")

        assert result["trade_equity_pct"] == ""


class TestSubstitute:

    def test_replaces_a_single_known_token(self):
        result = email_personalization._substitute("Hi {{first_name}}!", {"first_name": "Joseph"})
        assert result == "Hi Joseph!"

    def test_replaces_multiple_tokens(self):
        result = email_personalization._substitute(
            "{{first_name}} {{last_name}} in {{city}}",
            {"first_name": "Joseph", "last_name": "King", "city": "Austin"},
        )
        assert result == "Joseph King in Austin"

    def test_tolerates_internal_whitespace_inside_braces(self):
        result = email_personalization._substitute("Hi {{ first_name }}!", {"first_name": "Joseph"})
        assert result == "Hi Joseph!"

    def test_unknown_token_resolves_to_an_empty_string(self):
        result = email_personalization._substitute("Hi {{not_a_real_field}}!", {})
        assert result == "Hi !"

    def test_none_text_returns_none(self):
        assert email_personalization._substitute(None, {"first_name": "Joseph"}) is None

    def test_empty_text_returns_empty(self):
        assert email_personalization._substitute("", {"first_name": "Joseph"}) == ""

    def test_text_with_no_tokens_is_unchanged(self):
        result = email_personalization._substitute("Plain text, no tokens.", {"first_name": "Joseph"})
        assert result == "Plain text, no tokens."


class TestRenderPersonalized:

    def test_unknown_template_returns_an_error(self):
        _make_customer("CUST-1", FirstName="Joseph")

        result = email_personalization.render_personalized("TMPL-BOGUS", "CUST-1")

        assert result == {"error": "Template not found"}

    def test_sms_template_returns_the_sms_shape_with_substituted_body(self, monkeypatch):
        monkeypatch.setattr(smart_audiences, "get_equity_candidate_for_customer", lambda customer_id: None)
        _make_customer("CUST-1", FirstName="Joseph")
        _make_template("TMPL-1", channel="sms", sms_body="Hi {{first_name}}, come test drive today!")

        result = email_personalization.render_personalized("TMPL-1", "CUST-1")

        assert result["channel"] == "sms"
        assert result["sms_body"] == "Hi Joseph, come test drive today!"
        assert "segment_info" in result
        assert result["merge_values"]["first_name"] == "Joseph"

    def test_email_template_returns_the_email_shape_with_substituted_content(self, monkeypatch):
        monkeypatch.setattr(smart_audiences, "get_equity_candidate_for_customer", lambda customer_id: None)
        _make_customer("CUST-1", FirstName="Joseph", LastName="King")
        _make_template(
            "TMPL-1",
            channel="email",
            subject="Hi {{first_name}}!",
            preheader="A message for {{full_name}}",
            blocks=[
                {"block_key": "heading", "fields": {"text": "Welcome, {{first_name}}!"}},
                {"block_key": "spacer", "fields": {"height": 24}},
            ],
        )

        result = email_personalization.render_personalized("TMPL-1", "CUST-1")

        assert result["channel"] == "email"
        assert result["subject"] == "Hi Joseph!"
        assert result["preheader"] == "A message for Joseph King"
        assert "Welcome, Joseph!" in result["html"]
        assert "WELCOME, JOSEPH!" in result["text"]
        assert result["merge_values"]["full_name"] == "Joseph King"

    def test_non_string_block_field_values_are_left_untouched(self, monkeypatch):
        monkeypatch.setattr(smart_audiences, "get_equity_candidate_for_customer", lambda customer_id: None)
        _make_customer("CUST-1", FirstName="Joseph")
        _make_template(
            "TMPL-1",
            channel="email",
            blocks=[{"block_key": "spacer", "fields": {"height": 24}}],
        )

        result = email_personalization.render_personalized("TMPL-1", "CUST-1")

        assert "height:24px" in result["html"]

    def test_the_stored_template_is_never_mutated_by_personalization(self, monkeypatch):
        monkeypatch.setattr(smart_audiences, "get_equity_candidate_for_customer", lambda customer_id: None)
        _make_customer("CUST-1", FirstName="Joseph")
        template = _make_template("TMPL-1", channel="email", subject="Hi {{first_name}}!")

        email_personalization.render_personalized("TMPL-1", "CUST-1")

        stored = ledger.get_entity("TMPL-1")
        assert stored.attributes["subject"] == "Hi {{first_name}}!"

    def test_two_different_recipients_render_different_personalized_content(self, monkeypatch):
        monkeypatch.setattr(smart_audiences, "get_equity_candidate_for_customer", lambda customer_id: None)
        _make_customer("CUST-1", FirstName="Joseph")
        _make_customer("CUST-2", FirstName="Ann")
        _make_template("TMPL-1", channel="email", subject="Hi {{first_name}}!")

        result_1 = email_personalization.render_personalized("TMPL-1", "CUST-1")
        result_2 = email_personalization.render_personalized("TMPL-1", "CUST-2")

        assert result_1["subject"] == "Hi Joseph!"
        assert result_2["subject"] == "Hi Ann!"
