"""
Tests for core/entity_mentions.py -- turns a free-text entity-ID mention (e.g. "check
on CUS-00042 before you call") into a REAL graph relationship, not just a client-side
link (session 76 fourth follow-up).

extract_mentioned_entity_ids() is deliberately conservative: an ID-shaped substring
only counts if it resolves to a real, currently-existing entity in the ledger --
anything that merely matches the regex shape but isn't a real entity is silently
dropped, never linked. link_entity_mentions() is the multi-target scanner (used for
Message text); link_entity_reference() is the single-target version (used for
KnowledgePin's already-known ref_id).

Run from backend/ with `pytest`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from core.dealeros import ledger
from core.entities import Entity
from core.entity_types import CUSTOMER, VEHICLE
from core.relationship_types import MENTIONS, REFERENCES
from core import entity_mentions


@pytest.fixture(autouse=True)
def fresh_ledger():
    ledger.reset()
    yield


def _make_entity(entity_id, entity_type=CUSTOMER, **attrs):
    entity = Entity(id=entity_id, entity_type=entity_type, attributes=attrs)
    ledger.add_entity(entity)
    return entity


def _relationships_from(source_id):
    return [r for r in ledger.relationships if r.source_id == source_id]


class TestExtractMentionedEntityIds:

    def test_finds_a_single_real_entity_id_in_text(self):
        _make_entity("CUS-00042")

        result = entity_mentions.extract_mentioned_entity_ids("check on CUS-00042 before you call")

        assert result == ["CUS-00042"]

    def test_ignores_an_id_shaped_string_that_does_not_resolve_to_a_real_entity(self):
        result = entity_mentions.extract_mentioned_entity_ids("check on VEH-99999 please")

        assert result == []

    def test_finds_multiple_real_entity_ids_in_text(self):
        _make_entity("CUS-00042")
        _make_entity("VEH-00017", entity_type=VEHICLE)

        result = entity_mentions.extract_mentioned_entity_ids(
            "linking CUS-00042 to VEH-00017 for the trade-in"
        )

        assert set(result) == {"CUS-00042", "VEH-00017"}

    def test_duplicate_mentions_of_the_same_id_are_deduped(self):
        _make_entity("CUS-00042")

        result = entity_mentions.extract_mentioned_entity_ids(
            "CUS-00042 called about CUS-00042 again"
        )

        assert result == ["CUS-00042"]

    def test_empty_string_returns_empty_list(self):
        assert entity_mentions.extract_mentioned_entity_ids("") == []

    def test_none_text_returns_empty_list(self):
        assert entity_mentions.extract_mentioned_entity_ids(None) == []

    def test_text_with_no_id_shaped_substrings_returns_empty_list(self):
        _make_entity("CUS-00042")

        result = entity_mentions.extract_mentioned_entity_ids("just a plain message, nothing special")

        assert result == []

    def test_mixed_real_and_fake_ids_only_returns_the_real_one(self):
        _make_entity("CUS-00042")

        result = entity_mentions.extract_mentioned_entity_ids(
            "CUS-00042 is real but XYZ-12345 is not"
        )

        assert result == ["CUS-00042"]

    def test_lowercase_id_shaped_text_is_not_matched(self):
        _make_entity("CUS-00042")

        result = entity_mentions.extract_mentioned_entity_ids("cus-00042 lowercase should not match")

        assert result == []


class TestLinkEntityMentions:

    def test_creates_a_real_relationship_to_every_mentioned_entity(self):
        _make_entity("CUS-00042")
        _make_entity("VEH-00017", entity_type=VEHICLE)

        linked = entity_mentions.link_entity_mentions(
            "MSG-1", "CUS-00042 wants to trade in VEH-00017", created_by="EMP-1"
        )

        assert set(linked) == {"CUS-00042", "VEH-00017"}
        rels = _relationships_from("MSG-1")
        assert len(rels) == 2
        target_ids = {r.target_id for r in rels}
        assert target_ids == {"CUS-00042", "VEH-00017"}
        for r in rels:
            assert r.relationship_type == MENTIONS
            assert r.created_by == "EMP-1"
            assert r.created_at is not None

    def test_uses_a_custom_relationship_type_when_given(self):
        _make_entity("CUS-00042")

        entity_mentions.link_entity_mentions("PIN-1", "about CUS-00042", relationship_type=REFERENCES)

        rels = _relationships_from("PIN-1")
        assert len(rels) == 1
        assert rels[0].relationship_type == REFERENCES

    def test_no_mentions_creates_no_relationships_and_returns_empty_list(self):
        linked = entity_mentions.link_entity_mentions("MSG-1", "nothing to see here")

        assert linked == []
        assert _relationships_from("MSG-1") == []

    def test_empty_text_is_a_safe_no_op(self):
        linked = entity_mentions.link_entity_mentions("MSG-1", "")

        assert linked == []
        assert _relationships_from("MSG-1") == []

    def test_none_text_is_a_safe_no_op(self):
        linked = entity_mentions.link_entity_mentions("MSG-1", None)

        assert linked == []
        assert _relationships_from("MSG-1") == []

    def test_a_self_mention_is_skipped_not_linked(self):
        _make_entity("MSG-1")

        linked = entity_mentions.link_entity_mentions("MSG-1", "referencing MSG-1 itself")

        assert linked == []
        assert _relationships_from("MSG-1") == []

    def test_a_self_mention_among_other_real_mentions_only_skips_itself(self):
        _make_entity("MSG-1")
        _make_entity("CUS-00042")

        linked = entity_mentions.link_entity_mentions(
            "MSG-1", "MSG-1 notes that CUS-00042 called"
        )

        assert linked == ["CUS-00042"]

    def test_a_fake_id_shaped_mention_is_not_linked(self):
        linked = entity_mentions.link_entity_mentions("MSG-1", "about VEH-99999")

        assert linked == []
        assert _relationships_from("MSG-1") == []

    def test_created_by_defaults_to_none_when_not_given(self):
        _make_entity("CUS-00042")

        entity_mentions.link_entity_mentions("MSG-1", "about CUS-00042")

        rels = _relationships_from("MSG-1")
        assert rels[0].created_by is None


class TestLinkEntityReference:

    def test_creates_a_real_references_relationship_to_a_real_entity(self):
        _make_entity("CUS-00042")

        created = entity_mentions.link_entity_reference("PIN-1", "CUS-00042", created_by="EMP-1")

        assert created is True
        rels = _relationships_from("PIN-1")
        assert len(rels) == 1
        assert rels[0].target_id == "CUS-00042"
        assert rels[0].relationship_type == REFERENCES
        assert rels[0].created_by == "EMP-1"

    def test_returns_false_and_creates_nothing_when_ref_id_does_not_resolve(self):
        created = entity_mentions.link_entity_reference("PIN-1", "CUS-99999")

        assert created is False
        assert _relationships_from("PIN-1") == []

    def test_returns_false_when_ref_id_is_none(self):
        created = entity_mentions.link_entity_reference("PIN-1", None)

        assert created is False
        assert _relationships_from("PIN-1") == []

    def test_returns_false_when_ref_id_is_empty_string(self):
        created = entity_mentions.link_entity_reference("PIN-1", "")

        assert created is False
        assert _relationships_from("PIN-1") == []

    def test_returns_false_when_ref_id_equals_source_id(self):
        _make_entity("PIN-1")

        created = entity_mentions.link_entity_reference("PIN-1", "PIN-1")

        assert created is False
        assert _relationships_from("PIN-1") == []

    def test_created_by_defaults_to_none_when_not_given(self):
        _make_entity("CUS-00042")

        entity_mentions.link_entity_reference("PIN-1", "CUS-00042")

        rels = _relationships_from("PIN-1")
        assert rels[0].created_by is None
